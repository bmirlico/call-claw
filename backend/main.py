import re
import redis
import json
import asyncio
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from config import settings
from services import recall_service, mistral_service, elevenlabs_service, openclaw_service, linear_service, gmail_service
from services.buffer_manager import buffer_manager
from services.memory_service import memory_service

app = FastAPI(title="CallClaw", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

r = redis.from_url(settings.redis_url)

# Pre-cached confirmation audio (populated at startup)
CONFIRMATION_CACHE: dict[str, str] = {}

CONFIRMATIONS = {
    "web_search": "OK, let me look that up.",
    "create_ticket": "Sure, creating the ticket.",
    "create_doc": "Got it, preparing the document.",
    "send_email": "On it, drafting the email.",
    "recall_memory": "Let me check my notes.",
    "generic": "OK, on it.",
}


# ── Request models ─────────────────────────────────────────────────────────────

class JoinCallRequest(BaseModel):
    meeting_url: str
    team_id: str = settings.default_team_id


class ProcessRequest(BaseModel):
    bot_id: str
    speaker: str
    text: str
    team_id: str = settings.default_team_id


class EndCallRequest(BaseModel):
    bot_id: str
    team_id: str = settings.default_team_id


class SeedMemoryRequest(BaseModel):
    team_id: str = settings.default_team_id
    decisions: list[str]
    action_items: list[dict]
    key_context: str


# ── Background action execution ───────────────────────────────────────────────

async def _execute_linear_ticket(decision: dict, instruction: str) -> str:
    """
    Extracts structured fields from Mistral's decision and calls Linear API directly.
    Falls back to extracting from raw_instruction if structured fields are missing.
    """
    title = decision.get("ticket_title")
    if not title:
        # Mistral-small sometimes omits structured fields — extract from instruction
        print(f"[LINEAR] No ticket_title in decision, extracting from instruction")
        title = instruction[:120] if instruction else "Untitled ticket"

    description = decision.get("ticket_description", "")
    priority = decision.get("ticket_priority", 3)

    result = await linear_service.create_ticket(title, description, priority)

    if result["success"]:
        return (
            f"Ticket {result['identifier']} created: \"{result['title']}\" "
            f"(priority: {result['priority_label']}). "
            f"URL: {result['url']}"
        )

    print(f"[LINEAR] Direct API failed: {result['error']} — falling back to OpenClaw")
    return await openclaw_service.execute("create_ticket", instruction)


async def _execute_send_email(decision: dict, instruction: str) -> str:
    """
    Extracts structured fields from Mistral's decision and sends via Maton Gmail API.
    Falls back to OpenClaw if fields are missing or API fails.
    """
    to = decision.get("email_to")
    subject = decision.get("email_subject")
    body = decision.get("email_body")

    if not to or not subject:
        print("[GMAIL] No structured fields — falling back to OpenClaw")
        return await openclaw_service.execute("send_email", instruction)

    if not body:
        body = instruction

    result = await gmail_service.send_email(to, subject, body)

    if result["success"]:
        return (
            f"Email sent to {result['to']} with subject \"{result['subject']}\". "
            f"Message ID: {result['message_id']}"
        )

    print(f"[GMAIL] Direct API failed: {result['error']} — falling back to OpenClaw")
    return await openclaw_service.execute("send_email", instruction)


async def _execute_action_background(
    action_id: str,
    bot_id: str,
    action_type: str,
    instruction: str,
    team_id: str,
    team_memory: str,
    decision: dict | None = None,
) -> None:
    """
    Runs in background after /process returns the instant confirmation.
    Executes the action, generates response audio, stores result in Redis,
    and sends a chat message to the Meet.
    """
    try:
        # Execute action
        if action_type == "recall_memory":
            result = team_memory or "I don't have memory of past calls yet."
        elif action_type == "create_ticket" and decision:
            result = await _execute_linear_ticket(decision, instruction)
        elif action_type == "send_email" and decision:
            result = await _execute_send_email(decision, instruction)
        else:
            result = await openclaw_service.execute(action_type, instruction)

        # Mistral formulates a natural vocal response
        response_text = await mistral_service.formulate_response(
            instruction, result, team_memory
        )

        # Generate response audio
        audio = elevenlabs_service.generate_audio_base64(response_text)

        # Store result in Redis (TTL 5 min)
        r.setex(
            f"action:{action_id}",
            300,
            json.dumps({
                "ready": True,
                "audio_b64": audio,
                "response_text": response_text,
                "action_type": action_type,
            }),
        )

        # Clear old buffer (removes old trigger phrases that could re-trigger)
        # then inject only the response so follow-up questions have context
        buffer_manager.clear(bot_id)
        buffer_manager.add_segment(bot_id, "CallClaw", response_text)

        # Release cooldown immediately so bot can listen for next question
        r.delete(f"cooldown:{bot_id}")

        print(f"[ACTION] Result ready: {action_id} | {response_text[:80]}")

        # Send URLs to Meet chat (only if the result contains links)
        urls = re.findall(r'https?://[^\s<>"\')\]]+', result)
        if urls:
            real_bot_id = r.get(f"team:active_bot:{team_id}")
            if real_bot_id:
                chat_text = "\n".join(urls[:3])
                await recall_service.send_chat_message(
                    real_bot_id.decode(), chat_text
                )

    except Exception as e:
        print(f"[ACTION] Background error: {e}")
        # Store error result so frontend stops polling
        r.setex(
            f"action:{action_id}",
            300,
            json.dumps({
                "ready": True,
                "audio_b64": CONFIRMATION_CACHE.get("generic", ""),
                "response_text": "Sorry, something went wrong.",
                "action_type": action_type,
            }),
        )
    # No post-action cooldown — frontend 8s lockout + Mistral routing handle it


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}


@app.post("/bot/join")
async def join_call(request: JoinCallRequest) -> dict:
    """
    Sends the CallClaw bot into a Google Meet.
    After calling this, go to the Meet and click 'Admit' in the waiting room.
    """
    try:
        bot = await recall_service.create_bot(request.meeting_url, request.team_id)
        bot_id = bot["id"]

        r.setex(
            f"bot:active:{bot_id}",
            7200,
            json.dumps({"meeting_url": request.meeting_url, "team_id": request.team_id}),
        )

        # Store mapping for chat messages (frontend doesn't know the real bot_id)
        r.setex(f"team:active_bot:{request.team_id}", 7200, bot_id)

        team_memory = memory_service.get_team_memory(request.team_id)

        return {
            "bot_id": bot_id,
            "status": "joining",
            "has_past_memory": bool(team_memory),
            "message": (
                "CallClaw is joining. "
                "Accept it from the Google Meet waiting room."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bot/status/{bot_id}")
async def bot_status(bot_id: str) -> dict:
    try:
        return await recall_service.get_bot_status(bot_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/bot/end")
async def end_call(request: EndCallRequest) -> dict:
    """
    Ends the call:
    1. Gets full transcript from buffer
    2. Generates structured summary via Mistral
    3. Saves summary to Redis memory (persists for next call)
    4. Removes bot from Meet
    5. Cleans up Redis keys
    """
    bot_id = request.bot_id
    team_id = request.team_id

    transcript = buffer_manager.get_full_transcript(bot_id)
    summary = memory_service.save_call_summary(team_id, bot_id, transcript)

    await recall_service.remove_bot(bot_id)

    for key in [f"bot:active:{bot_id}", f"buffer:{bot_id}", f"cooldown:{bot_id}",
                f"team:active_bot:{team_id}"]:
        r.delete(key)

    return {
        "success": True,
        "summary": summary,
        "memory_saved": bool(summary),
    }


@app.post("/process")
async def process_transcript(request: ProcessRequest) -> dict:
    """
    Two-phase endpoint:
    Phase 1 (this response, ~1s): Mistral routing → return cached confirmation audio
    Phase 2 (background task): OpenClaw → Mistral response → ElevenLabs → Redis

    Returns:
    - { "action": false }
    - { "action": true, "confirmation_audio_b64": "...", "action_id": "...", "action_type": "..." }
    """
    bot_id = request.bot_id
    team_id = request.team_id
    speaker = request.speaker
    text = request.text.strip()

    if len(text.split()) < 3:
        return {"action": False}

    buffer_manager.add_segment(bot_id, speaker, text)

    cooldown_key = f"cooldown:{bot_id}"
    if not r.set(cooldown_key, "1", nx=True, ex=10):
        return {"action": False}

    buffer = buffer_manager.get_buffer(bot_id)
    team_memory = memory_service.get_team_memory(team_id)

    decision = await mistral_service.should_act(bot_id, buffer, team_memory)

    if not decision.get("should_act") or decision.get("confidence", 0) < 0.85:
        r.delete(cooldown_key)
        return {"action": False}

    action_type = decision.get("action_type", "generic")
    instruction = decision.get("raw_instruction", "")

    print(
        f"[ACTION] type={action_type} | trigger='{decision.get('trigger_phrase', '')}'"
        f"\n         instruction={instruction[:100]}"
        f"\n         decision_keys={list(decision.keys())}"
    )

    # Generate action_id and launch background task
    action_id = str(uuid4())[:8]

    asyncio.create_task(
        _execute_action_background(
            action_id=action_id,
            bot_id=bot_id,
            action_type=action_type,
            instruction=instruction,
            team_id=team_id,
            team_memory=team_memory,
            decision=decision,
        )
    )

    # Return instantly with cached confirmation audio
    return {
        "action": True,
        "confirmation_audio_b64": CONFIRMATION_CACHE.get(action_type, CONFIRMATION_CACHE.get("generic", "")),
        "action_id": action_id,
        "action_type": action_type,
    }


@app.get("/action/{action_id}")
async def get_action_result(action_id: str) -> dict:
    """Polled by frontend to get the background action result."""
    data = r.get(f"action:{action_id}")
    if not data:
        return {"ready": False}
    return json.loads(data)


@app.get("/memory/{team_id}")
async def get_memory(team_id: str) -> dict:
    """Debug: view current team memory in raw format."""
    return {"memory": memory_service.get_team_memory(team_id)}


@app.delete("/memory/{team_id}")
async def clear_memory(team_id: str) -> dict:
    """Reset all memory for a team. Call this before every demo run."""
    memory_service.clear_team_memory(team_id)
    return {"success": True}


@app.post("/memory/seed")
async def seed_memory(request: SeedMemoryRequest) -> dict:
    """
    Seeds a fake past call into memory.
    Use before the demo to enable Scenario 4 (memory recall).
    """
    record = memory_service.seed_memory(
        team_id=request.team_id,
        decisions=request.decisions,
        action_items=request.action_items,
        key_context=request.key_context,
    )
    return {"success": True, "record": record}


@app.on_event("startup")
async def warmup() -> None:
    """Pre-generate confirmation audio clips for instant responses."""
    try:
        for action_type, text in CONFIRMATIONS.items():
            CONFIRMATION_CACHE[action_type] = elevenlabs_service.generate_audio_base64(text)
        print(f"Pre-cached {len(CONFIRMATION_CACHE)} confirmation audio clips")
    except Exception as e:
        print(f"ElevenLabs warmup failed (check API key): {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
