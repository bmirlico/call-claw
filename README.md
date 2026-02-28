# CallClaw 🦅
> AI agent that joins Google Meet, executes real actions, and remembers everything across calls.

## Stack
- **Recall.ai** — bot joins Google Meet via Output Media (headless Chromium)
- **Mistral** — routing, reasoning, post-call summaries
- **ElevenLabs** — voice responses (eleven_turbo_v2)
- **OpenClaw** — local AI agent for computer use (web search, browser, file creation)
- **FastAPI + Redis** — backend + buffer/memory
- **React + TypeScript + Vite** — bot's camera webpage

## Start everything

```bash
redis-server &
openclaw start &
cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000 &
cd frontend && npm run dev &
ngrok http 8000   # update .env BACKEND_URL + frontend/.env VITE_BACKEND_URL
ngrok http 5173   # update .env FRONTEND_URL
```

## Send bot to a meeting

```bash
curl -X POST http://localhost:8000/bot/join \
  -H "Content-Type: application/json" \
  -d '{"meeting_url": "https://meet.google.com/your-id", "team_id": "team_demo"}'
```

Admit the bot in the Google Meet waiting room. Say **"Hey CallClaw, [request]"**.

## End call + save memory

```bash
curl -X POST http://localhost:8000/bot/end \
  -d '{"bot_id": "your-bot-id", "team_id": "team_demo"}'
```

## Seed demo memory (for Scenario 4)

```bash
curl -X DELETE http://localhost:8000/memory/team_demo
curl -X POST http://localhost:8000/memory/seed \
  -H "Content-Type: application/json" \
  -d '{"decisions":["Switch to HubSpot"],"action_items":[{"task":"Migration ticket","assignee":"backend","tool":"Linear"}],"key_context":"Team chose HubSpot Enterprise."}'
```

## API docs

http://localhost:8000/docs
