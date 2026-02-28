import redis
import json
from datetime import datetime
from config import settings

r = redis.from_url(settings.redis_url)
BUFFER_WINDOW_SECONDS = 120  # 2-minute sliding window


class BufferManager:
    """
    Maintains a 2-minute rolling transcript window per bot in Redis.
    This gives Mistral enough context to understand requests like
    "and the pricing?" without re-explaining the full conversation.
    """

    def add_segment(self, bot_id: str, speaker: str, text: str) -> None:
        key = f"buffer:{bot_id}"
        segment = {
            "speaker": speaker,
            "text": text,
            "timestamp": datetime.now().timestamp(),
        }
        r.rpush(key, json.dumps(segment))
        r.expire(key, 3600)
        self._cleanup(bot_id)

    def get_buffer(self, bot_id: str) -> str:
        """Returns formatted transcript of the last 2 minutes."""
        key = f"buffer:{bot_id}"
        segments = r.lrange(key, 0, -1)
        if not segments:
            return ""
        lines = [
            f"{json.loads(s)['speaker']}: {json.loads(s)['text']}"
            for s in segments
        ]
        return "\n".join(lines)

    def get_full_transcript(self, bot_id: str) -> list[dict]:
        """Returns all segments — used for post-call summary generation."""
        key = f"buffer:{bot_id}"
        segments = r.lrange(key, 0, -1)
        return [json.loads(s) for s in segments]

    def _cleanup(self, bot_id: str) -> None:
        """Removes segments older than BUFFER_WINDOW_SECONDS."""
        key = f"buffer:{bot_id}"
        cutoff = datetime.now().timestamp() - BUFFER_WINDOW_SECONDS
        for s in r.lrange(key, 0, -1):
            seg = json.loads(s)
            if seg["timestamp"] < cutoff:
                r.lrem(key, 1, s)
            else:
                break


buffer_manager = BufferManager()
