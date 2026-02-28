import redis
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from config import settings
from services import recall_service, mistral_service, elevenlabs_service, openclaw_service
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

    ALWAYS call this at the end of a call — it's what builds memory.
    """
    bot_id = request.bot_id
    team_id = request.team_id

    transcript = buffer_manager.get_full_transcript(bot_id)
    summary = memory_service.save_call_summary(team_id, bot_id, transcript)

    await recall_service.remove_bot(bot_id)

    for key in [f"bot:active:{bot_id}", f"buffer:{bot_id}", f"cooldown:{bot_id}"]:
        r.delete(key)

    return {
        "success": True,
        "summary": summary,
        "memory_saved": bool(summary),
    }


@app.post("/process")
async def process_transcript(request: ProcessRequest) -> dict:
    """
    Main endpoint — called by the bot's React webpage on every transcript segment.

    Flow:
    1. Add segment to 2-min rolling buffer
    2. Check cooldown (5s dedup lock)
    3. Ask Mistral: should we act? (uses buffer + team memory as context)
    4. If yes: play confirmation audio immediately
    5. Execute action via OpenClaw
    6. Generate vocal response via Mistral + ElevenLabs
    7. Return both audio base64 strings to the React frontend

    Returns:
    - { "action": false } — nothing to do
    - { "action": true, "confirmation_audio_b64": "...", "response_audio_b64": "..." }
    """
    bot_id = request.bot_id
    team_id = request.team_id
    speaker = request.speaker
    text = request.text.strip()

    # Skip very short segments (noise, filler words)
    if len(text.split()) < 3:
        return {"action": False}

    buffer_manager.add_segment(bot_id, speaker, text)

    # Cooldown check — prevents double-trigger when multiple segments
    # arrive rapidly from the same utterance
    cooldown_key = f"cooldown:{bot_id}"
    if r.get(cooldown_key):
        return {"action": False}

    buffer = buffer_manager.get_buffer(bot_id)
    team_memory = memory_service.get_team_memory(team_id)

    # Mistral routing decision
    decision = await mistral_service.should_act(bot_id, buffer, team_memory)

    if not decision.get("should_act") or decision.get("confidence", 0) < 0.85:
        return {"action": False}

    # Lock immediately to prevent concurrent processing
    r.setex(cooldown_key, 5, "1")

    action_type = decision.get("action_type", "generic")
    instruction = decision.get("raw_instruction", "")

    print(
        f"[ACTION] type={action_type} | trigger='{decision.get('trigger_phrase', '')}'"
        f"\n         instruction={instruction[:100]}"
    )

    # Generate confirmation audio immediately (while action is executing)
    confirmation_text = _get_confirmation(action_type)
    confirmation_audio = elevenlabs_service.generate_audio_base64(confirmation_text)

    # Execute action — memory recall uses stored context, others go to OpenClaw
    if action_type == "recall_memory":
        result = team_memory or "I don't have memory of past calls yet."
    else:
        result = await openclaw_service.execute(action_type, instruction)

    # Mistral formulates a natural vocal response from the raw result
    response_text = await mistral_service.formulate_response(
        instruction, result, team_memory
    )
    response_audio = elevenlabs_service.generate_audio_base64(response_text)

    return {
        "action": True,
        "confirmation_audio_b64": confirmation_audio,
        "response_audio_b64": response_audio,
        "response_text": response_text,
        "action_type": action_type,
    }


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

    Example body:
    {
      "team_id": "team_demo",
      "decisions": ["Switch to HubSpot for CRM"],
      "action_items": [{"task": "Create migration ticket", "assignee": "backend team", "tool": "Linear"}],
      "key_context": "Team reviewed CRM options and chose HubSpot Enterprise over Salesforce."
    }
    """
    record = memory_service.seed_memory(
        team_id=request.team_id,
        decisions=request.decisions,
        action_items=request.action_items,
        key_context=request.key_context,
    )
    return {"success": True, "record": record}


def _get_confirmation(action_type: str) -> str:
    return {
        "web_search": "Let me look that up...",
        "create_ticket": "Creating the ticket...",
        "create_doc": "Preparing the document...",
        "send_email": "Drafting the email...",
        "recall_memory": "Checking my notes from past calls...",
        "generic": "On it...",
    }.get(action_type, "On it...")


@app.on_event("startup")
async def warmup() -> None:
    """Pre-warm ElevenLabs on startup to reduce first-response latency."""
    try:
        elevenlabs_service.generate_audio_base64("CallClaw ready.")
        print("✅ ElevenLabs warmed up")
    except Exception as e:
        print(f"⚠️  ElevenLabs warmup failed (check API key): {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
