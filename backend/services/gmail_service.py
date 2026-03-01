import base64
import httpx
from email.mime.text import MIMEText
from config import settings


async def send_email(to: str, subject: str, body: str) -> dict:
    """
    Sends an email via Maton Gmail API (managed OAuth proxy).
    Bypasses OpenClaw for reliability and speed (~2-3s vs 45s+ timeout).
    """
    headers = {
        "Authorization": f"Bearer {settings.maton_api_key}",
        "Content-Type": "application/json",
    }

    # Get sender email address
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            profile = await client.get(
                "https://gateway.maton.ai/google-mail/gmail/v1/users/me/profile",
                headers=headers,
            )
            profile.raise_for_status()
            sender = profile.json()["emailAddress"]
    except Exception as e:
        print(f"[GMAIL] Failed to get sender profile: {e}")
        sender = "noreply@callclaw.ai"

    # Build RFC 2822 email
    msg = MIMEText(body)
    msg["To"] = to
    msg["From"] = sender
    msg["Subject"] = subject

    # Base64url encode
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://gateway.maton.ai/google-mail/gmail/v1/users/me/messages/send",
                headers=headers,
                json={"raw": raw},
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "message_id": data.get("id", "unknown"),
                "to": to,
                "subject": subject,
            }
    except Exception as e:
        print(f"[GMAIL] Send failed: {e}")
        return {"success": False, "error": str(e)}
