import httpx
from config import settings

BASE_URL = f"https://{settings.recall_region}.recall.ai/api/v1"
HEADERS = {
    "Authorization": f"Token {settings.recall_api_key}",
    "Content-Type": "application/json",
}


async def create_bot(meeting_url: str, team_id: str) -> dict:
    """
    Creates a Recall.ai bot and sends it into the Google Meet.

    The bot is configured with Output Media (camera: webpage).
    This means Recall.ai launches a headless Chromium that loads our
    React frontend URL. That page:
    1. Receives the call audio via getUserMedia() (Recall.ai injects it)
    2. Connects to wss://meeting-data.bot.recall.ai for real-time transcriptions
    3. Sends transcript segments to our FastAPI /process endpoint
    4. Plays ElevenLabs audio via AudioContext
    5. Recall.ai captures that audio and injects it into the call

    The frontend URL receives team_id as a URL param for memory scoping.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{BASE_URL}/bot",
            headers=HEADERS,
            json={
                "meeting_url": meeting_url,
                "bot_name": "CallClaw",
                "output_media": {
                    "camera": {
                        "kind": "webpage",
                        "config": {
                            # Recall.ai loads this URL in headless Chromium
                            # Pass team_id so the frontend can scope memory correctly
                            "url": f"{settings.frontend_url}?team_id={team_id}"
                        },
                    }
                },
                "recording_config": {
                    "transcript": {"provider": {"meeting_captions": {}}},
                    "realtime_endpoints": [
                        {
                            "type": "websocket",
                            "url": "wss://meeting-data.bot.recall.ai/api/v1/transcript",
                            "events": ["transcript.data"],
                        }
                    ],
                },
            },
        )
        response.raise_for_status()
        return response.json()


async def get_bot_status(bot_id: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{BASE_URL}/bot/{bot_id}",
            headers=HEADERS,
        )
        response.raise_for_status()
        return response.json()


async def remove_bot(bot_id: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.delete(
            f"{BASE_URL}/bot/{bot_id}",
            headers=HEADERS,
        )
        return response.status_code == 204
