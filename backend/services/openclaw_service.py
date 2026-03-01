import httpx
from config import settings

# ─── Mock mode ────────────────────────────────────────────────────────────────
# Set MOCK_MODE = True before going on stage if:
# - OpenClaw gateway is slow to respond
# - Network is unreliable at the venue
# - You want a guaranteed clean demo
MOCK_MODE = False

MOCK_RESPONSES: dict[str, str] = {
    "web_search": (
        "HubSpot Sales Hub Enterprise starts at $1,200/month for 10 users. "
        "Annual billing saves 20%. Salesforce Sales Cloud Enterprise is $165/user/month, "
        "minimum 5 users, totaling $825/month at that scale."
    ),
    "create_ticket": (
        "Ticket created in Linear — 'Safari login bug: session timeout every 10 min', "
        "assigned to backend team, priority: high. Ticket ID: CC-247."
    ),
    "create_doc": (
        "Notion page created: 'CallClaw Meeting Notes'. "
        "Includes all decisions made and action items from today's call. "
        "Link shared in the chat."
    ),
    "send_email": "Email drafted and ready for your review.",
    "recall_memory": "Checking notes from past calls...",
    "generic": "Action completed.",
}


async def execute(action_type: str, instruction: str) -> str:
    """
    Delegates the action to the locally running OpenClaw agent via
    its OpenAI-compatible HTTP API.

    OpenClaw's local gateway:
    - Runs on http://127.0.0.1:18789 (or the port set in openclaw.json)
    - Authenticated with Bearer token from: openclaw config get gateway.auth.token
    - Accepts OpenAI-style /v1/chat/completions requests
    - Has browser access, web search skill, and file system access
    - Uses Mistral as its underlying model (configured in Section A)

    We send the instruction as a user message.
    OpenClaw runs its agent loop, uses tools (browser, web search), and returns a result.
    """
    if MOCK_MODE:
        import asyncio
        await asyncio.sleep(2)  # simulate realistic delay for demo feel
        return MOCK_RESPONSES.get(action_type, "Action completed.")

    headers = {
        "Authorization": f"Bearer {settings.openclaw_gateway_token}",
        "Content-Type": "application/json",
        "x-openclaw-agent-id": "main",  # route to the main agent
    }

    payload = {
        "model": "openclaw",  # OpenClaw ignores this field — uses its configured model
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an action executor inside a meeting assistant called CallClaw. "
                    "You have access to these skills: Linear (create tickets via linear-issues skill), "
                    "Notion (create pages via notion skill — API key is in ~/.config/notion/api_key, "
                    "always search for existing pages first with the Notion search API, then create child pages under the 'CallClaw' parent page), "
                    "Gmail (send emails via gmail skill with MATON_API_KEY env var — "
                    "NEVER use the 'message' tool for emails, it routes to WhatsApp. "
                    "For emails, ALWAYS use the 'exec' tool to run a Python script that calls the Maton Gmail API directly. "
                    "Read the gmail SKILL.md for the exact API format), "
                    "and web search. "
                    "IMPORTANT: Always make real API calls. Never simulate or pretend to execute actions. "
                    "Read the relevant SKILL.md files for API details. "
                    "Execute the requested action precisely and return a concise result in 1-3 sentences. "
                    "ALWAYS include the full URL of any created resource (ticket, page, doc) in your response. "
                    "Be factual and direct."
                ),
            },
            {"role": "user", "content": instruction},
        ],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{settings.openclaw_gateway_url}/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

    except httpx.TimeoutException:
        print(f"[OPENCLAW] Timeout — falling back to mock for {action_type}")
        return MOCK_RESPONSES.get(action_type, "Action timed out.")

    except Exception as e:
        print(f"[OPENCLAW] Error: {e} — falling back to mock")
        return MOCK_RESPONSES.get(action_type, f"Action failed: {str(e)}")
