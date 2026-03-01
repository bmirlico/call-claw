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

When action_type is "create_ticket", ALSO include these fields:
{
  "action_type": "create_ticket",
  "ticket_title": "Safari login bug: session timeout every 10 min",
  "ticket_description": "Users on Safari experiencing session timeouts every 10 minutes. Needs investigation by backend team.",
  "ticket_priority": 2
}
ticket_priority values: 1=Urgent, 2=High, 3=Normal, 4=Low

When action_type is "send_email", ALSO include these fields:
{
  "action_type": "send_email",
  "email_to": "recipient@example.com",
  "email_subject": "Meeting Summary",
  "email_body": "Hi team, here is a summary of our discussion today..."
}
email_body should be a professional, well-written email body (not just a single line).

Activation rules:
- should_act = true ONLY when someone explicitly addresses "CallClaw", "Hey CallClaw", or "Claw"
- A concrete executable action must be requested
- confidence must be >= 0.85 to act
- Normal human conversation → should_act = false

action_type values:
- web_search    → find info, pricing, comparisons online
- create_ticket → create issue in Linear
- create_doc    → create a Notion page
- send_email    → send an email via Gmail
- recall_memory → user asks about past decisions or past calls
- generic       → any other browser/computer action

raw_instruction must be a complete, self-contained instruction. Follow these templates:

- web_search: "Search the web for [specific query]. Return a concise answer with source URLs."
- create_ticket: "Create a Linear ticket with title '[title]', description '[details from conversation]', priority [1=urgent,2=high,3=normal,4=low]. Include the ticket URL in your response."
- create_doc: "Search Notion for the 'CallClaw' parent page, then create a child page under it titled '[title]'. Content should include: [summarize the key decisions, action items, and context from the conversation]. Include the page URL in your response."
- send_email: "Send an email to [email address] with subject '[subject]'. Body: [compose a professional summary of what was discussed/decided]. Confirm when sent."
- recall_memory: (no instruction needed, handled locally)
- generic: "[full instruction with context]"

IMPORTANT: Always include enough conversational context in raw_instruction so the executor can act without seeing the transcript.
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
- NEVER include URLs in your response — they will be spoken aloud by text-to-speech
- Instead of a URL, say "I've shared the link in the chat" or "check the chat for the link"
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
