import redis
import json
from datetime import datetime
from mistralai import Mistral
from config import settings

r = redis.from_url(settings.redis_url)
client = Mistral(api_key=settings.mistral_api_key)

SUMMARY_SYSTEM = """
You are analyzing a meeting transcript. Extract structured information.
Respond ONLY with valid JSON, nothing else. No markdown, no backticks.

Required format:
{
  "decisions": ["decision 1", "decision 2"],
  "action_items": [
    {"task": "description", "assignee": "name or null", "tool": "Linear|Notion|null"}
  ],
  "topics": ["topic 1", "topic 2"],
  "key_context": "2-3 sentence summary of what was discussed and decided"
}

Be concise and factual. Only include things explicitly mentioned in the transcript.
"""


class MemoryService:
    """
    Saves structured summaries after each call and retrieves them
    for the next call. This is what makes CallClaw remember decisions
    across meetings — the core product differentiator.
    """

    def save_call_summary(
        self, team_id: str, bot_id: str, transcript: list[dict]
    ) -> dict:
        """
        Called at the end of every call.
        Sends the full transcript to Mistral, gets a structured summary,
        and stores it in Redis keyed by team_id.
        """
        if not transcript:
            return {}

        formatted = "\n".join(
            f"{seg['speaker']}: {seg['text']}" for seg in transcript
        )

        try:
            response = client.chat.complete(
                model="mistral-large-latest",
                messages=[
                    {"role": "system", "content": SUMMARY_SYSTEM},
                    {"role": "user", "content": f"Transcript:\n{formatted}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            summary = json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[MEMORY] Summary error: {e}")
            summary = {
                "decisions": [],
                "action_items": [],
                "topics": [],
                "key_context": "",
            }

        record = {
            "bot_id": bot_id,
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%B %d, %Y"),
            **summary,
        }

        history_key = f"memory:{team_id}:history"
        r.rpush(history_key, json.dumps(record))
        r.ltrim(history_key, -10, -1)  # keep last 10 calls only
        r.expire(history_key, 30 * 24 * 3600)  # 30-day TTL

        print(
            f"[MEMORY] Saved for {team_id}: "
            f"{len(summary.get('decisions', []))} decisions, "
            f"{len(summary.get('action_items', []))} action items"
        )
        return record

    def get_team_memory(self, team_id: str) -> str:
        """
        Returns formatted memory of past calls to inject into Mistral context.
        Called on every /process request so Mistral always has full context.
        """
        history_key = f"memory:{team_id}:history"
        records = r.lrange(history_key, 0, -1)
        if not records:
            return ""

        lines = ["=== PAST MEETING MEMORY ==="]
        for rec in records:
            record = json.loads(rec)
            lines.append(f"\n📅 {record.get('date', 'Previous call')}:")
            if record.get("key_context"):
                lines.append(f"  Context: {record['key_context']}")
            if record.get("decisions"):
                lines.append("  Decisions:")
                for d in record["decisions"]:
                    lines.append(f"    • {d}")
            if record.get("action_items"):
                lines.append("  Action items:")
                for item in record["action_items"]:
                    assignee = f" ({item['assignee']})" if item.get("assignee") else ""
                    lines.append(f"    → {item['task']}{assignee}")
        lines.append("=== END OF MEMORY ===\n")
        return "\n".join(lines)

    def seed_memory(
        self,
        team_id: str,
        decisions: list[str],
        action_items: list[dict],
        key_context: str,
    ) -> dict:
        """
        Seeds a fake past call into memory.
        Use this before the demo to enable Scenario 4 (memory recall).
        """
        record = {
            "bot_id": "seed",
            "timestamp": datetime.now().isoformat(),
            "date": "Last week",
            "decisions": decisions,
            "action_items": action_items,
            "topics": [],
            "key_context": key_context,
        }
        history_key = f"memory:{team_id}:history"
        r.rpush(history_key, json.dumps(record))
        r.expire(history_key, 30 * 24 * 3600)
        return record

    def clear_team_memory(self, team_id: str) -> None:
        r.delete(f"memory:{team_id}:history")


memory_service = MemoryService()
