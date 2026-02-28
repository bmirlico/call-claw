import base64
from elevenlabs.client import ElevenLabs
from config import settings

client = ElevenLabs(api_key=settings.elevenlabs_api_key)


def generate_audio_base64(text: str) -> str:
    """
    Converts text to speech using ElevenLabs and returns base64-encoded MP3.

    Flow:
    1. FastAPI returns this base64 string to the React frontend
    2. React decodes it and plays via AudioContext
    3. Recall.ai's headless Chromium captures the AudioContext output
    4. Recall.ai injects that audio into the Google Meet call
    5. All participants hear CallClaw speak
    """
    audio_generator = client.generate(
        text=text,
        voice=settings.elevenlabs_voice_id,
        model="eleven_turbo_v2",  # lowest latency ElevenLabs model
        output_format="mp3_44100_128",
    )

    audio_bytes = b"".join(chunk for chunk in audio_generator if chunk)
    return base64.b64encode(audio_bytes).decode("utf-8")
