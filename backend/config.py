from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Recall.ai
    recall_api_key: str = "TODO_fill_this"
    recall_region: str = "eu-central-1"

    # Mistral
    mistral_api_key: str = "TODO_fill_this"

    # ElevenLabs
    elevenlabs_api_key: str = "TODO_fill_this"
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"

    # OpenClaw local gateway
    openclaw_gateway_token: str = "TODO_fill_this"
    openclaw_gateway_url: str = "http://127.0.0.1:18789"

    # Linear (direct API — bypasses OpenClaw for speed)
    linear_api_key: str = "TODO_fill_this"
    linear_team_id: str = "TODO_fill_this"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # URLs
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    # App
    default_team_id: str = "team_demo"

    class Config:
        env_file = "../.env"


settings = Settings()
