import json
from mistralai import Mistral
from config import settings

client = Mistral(api_key=settings.mistral_api_key)

DETECTION_SYSTEM = """
You are an AI assistant named CallClaw embedded in a Google Meet call.
You receive the last 2 minutes of transcript AND memory from past calls.

Respond ONLY with valid JSON. No markdown, no explanation.

Required format:
{
  "should_act": true,
  "confidence": 0.95,
  "trigger_phrase": "Hey CallClaw, search HubSpot pricing",
  "action_type": "web_search",
  "raw_instruction": "Search the web for HubSpot Sales Hub Enterprise pricing and return a concise comparison"
}

Activation rules:
- should_act = true ONLY when someone explicitly addresses "CallClaw", "Hey CallClaw", or "Claw"
- A concrete executable action must be requested
- confidence must be >= 0.85 to act
- Normal human conversation → should_act = false

action_type values:
- web_search    → find info, pricing, comparisons online
- create_ticket → create issue in Linear or Jira
- create_doc    → create or edit a Google Doc
- send_email    → draft or send an email
- recall_memory → user asks about past decisions or past calls
- generic       → any other browser/computer action

raw_instruction must be a complete natural language instruction with all context
needed to execute independently — include the request AND the conversational context.
"""

RESPONSE_SYSTEM = """
You are CallClaw, an AI assistant inside a Google Meet call.
You just executed an action. Formulate a short vocal response.

Rules:
- Maximum 3 short sentences
- Natural, direct tone — not robotic
- Briefly confirm what you did, then give the result concisely
- Match the conversation language exactly (French → respond French, English → English)
- If referencing past call memory, be specific: mention dates and decisions
- NEVER start with "Of course", "Certainly", "Sure", or "Absolutely"
- NEVER say "I apologize" or "I'm sorry"
"""


async def should_act(
    bot_id: str, buffer: str, team_memory: str = ""
) -> dict:
    """
    Asks Mistral whether the agent should intervene based on
    the current conversation buffer and past call memory.
    Uses mistral-small for speed (routing decision, not reasoning).
    """
    context = (
        f"{team_memory}\n\nLast 2 minutes:\n{buffer}"
        if team_memory
        else f"Conversation:\n{buffer}"
    )
    try:
        response = client.chat.complete(
            model="mistral-small-latest",  # faster for routing
            messages=[
                {"role": "system", "content": DETECTION_SYSTEM},
                {"role": "user", "content": context},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[MISTRAL] Detection error: {e}")
        return {"should_act": False, "confidence": 0}


async def formulate_response(
    instruction: str, result: str, team_memory: str = ""
) -> str:
    """
    Asks Mistral to turn the raw action result into a natural vocal response.
    Uses mistral-large for better quality.
    """
    try:
        context = f"Past call memory:\n{team_memory}\n\n" if team_memory else ""
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=[
                {"role": "system", "content": RESPONSE_SYSTEM},
                {
                    "role": "user",
                    "content": f"{context}Action executed: {instruction}\nResult: {result}",
                },
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[MISTRAL] Response error: {e}")
        return "Done."
