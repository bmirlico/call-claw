# 🦅 CallClaw

> **AI agent that joins your Google Meet, executes real actions mid-call, and remembers everything across meetings.**

Built for the [**Mistral Worldwide Hackathon — Online Edition**](https://luma.com/mistralhack-online) 🏆

---

## 🎥 Demo

[![CallClaw Demo](https://img.youtube.com/vi/aBWHr-J6LGM/maxresdefault.jpg)](https://youtu.be/aBWHr-J6LGM)

👉 **[Watch the full demo on YouTube](https://youtu.be/aBWHr-J6LGM)**

---

## 🎬 What It Does

Say **"Hey CallClaw"** during a Google Meet and it will:

| Scenario | Trigger Example | What Happens |
|----------|----------------|--------------|
| 🔍 **Web Search** | "Hey CallClaw, what's HubSpot Enterprise pricing?" | Searches the web, speaks a concise answer |
| 🎫 **Create Ticket** | "Hey CallClaw, create a ticket for the Safari login bug, high priority" | Creates a Linear issue via direct API (~3s) |
| 📝 **Create Doc** | "Hey CallClaw, make a Notion page with today's decisions" | Creates a structured Notion page |
| 📧 **Send Email** | "Hey CallClaw, email the team a recap of this meeting" | Sends a real email via Gmail API (~2s) |
| 🧠 **Recall Memory** | "Hey CallClaw, what did we decide last week about the CRM?" | Recalls decisions from past meetings |

The ⭐ **killer feature** is **cross-call memory** — CallClaw remembers decisions, action items, and context from previous meetings and uses them to inform future responses.

---

## 🏗️ Architecture

```
Google Meet
  └─ Recall.ai Bot (headless Chromium running our React page)
       ├─ getUserMedia() → receives call audio
       ├─ WebSocket → wss://meeting-data.bot.recall.ai → real-time transcript
       └─ AudioContext.play() → audio captured and injected into the call

React (TypeScript) ←→ FastAPI (Python)
  POST /process → [BufferManager 2-min window]
               → [Mistral Small: should we act?] ←── routing decision (~1s)
               → Phase 1: return cached confirmation audio instantly
               → Phase 2 (background):
                    ├─ [Direct API: Linear / Gmail] (~2-3s)
                    ├─ [OpenClaw Agent: web search, Notion, browser] (~15-45s)
                    ├─ [Mistral Large: formulate vocal response]
                    ├─ [ElevenLabs: generate speech]
                    └─ Store result in Redis → frontend polls → plays audio

Redis
  ├─ buffer:{bot_id}           → 2-min sliding transcript window
  ├─ cooldown:{bot_id}         → dedup lock (prevents double-triggers)
  ├─ action:{action_id}        → background action results (5-min TTL)
  └─ memory:{team_id}:history  → cross-call memory (last 10 calls, 30-day TTL)
```

### 🔑 Key Design Decisions

- **Two-Phase Response** — The bot says "Let me look that up..." instantly (pre-cached audio) while the actual action runs in the background. No awkward silence.
- **Direct API Bypasses** — Linear (GraphQL) and Gmail (Maton proxy) are called directly for speed & reliability (~2-3s). OpenClaw handles complex multi-step tasks (web search, Notion, browser automation).
- **Mistral Dual-Model** — `mistral-small-latest` for fast routing decisions, `mistral-large-latest` for reasoning and response formulation.
- **PCM Audio** — ElevenLabs outputs raw PCM 24kHz (not MP3) for zero-decode-overhead playback in the browser.
- **Buffer + Cooldown** — 2-minute sliding window gives Mistral enough conversational context. Cooldown prevents re-triggering on the same utterance. Buffer is cleared post-action.

---

## 🛠️ Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| 🤖 **AI Routing & Reasoning** | [Mistral](https://mistral.ai) | Intent detection, response formulation, post-call summaries |
| 🎙️ **Voice Synthesis** | [ElevenLabs](https://elevenlabs.io) | Text-to-speech (`eleven_flash_v2_5`, PCM 24kHz) |
| 📞 **Meeting Integration** | [Recall.ai](https://recall.ai) | Bot joins Google Meet, real-time transcript via WebSocket |
| 🤖 **Agent Execution** | [OpenClaw](https://openclaw.com) | Local AI agent daemon — web search, browser, Notion |
| 🎫 **Ticket Creation** | [Linear API](https://linear.app) | Direct GraphQL mutations |
| 📧 **Email Sending** | [Maton](https://maton.ai) + Gmail API | Managed OAuth proxy for Gmail |
| ⚡ **Backend** | FastAPI + Redis | API endpoints, transcript buffer, cross-call memory |
| 🖥️ **Frontend** | React + TypeScript + Vite | Bot's camera webpage (AudioContext, WebSocket) |
| 🌐 **Tunneling** | ngrok | Exposes local servers to Recall.ai |

---

## 📁 Project Structure

```
call-claw/
├── 📄 .env                              # API keys & URLs
├── 📄 CLAUDE.md                          # Full implementation spec
│
├── 🐍 backend/
│   ├── main.py                           # FastAPI app — all endpoints + background tasks
│   ├── config.py                         # Pydantic settings from .env
│   ├── requirements.txt                  # Python deps
│   └── services/
│       ├── buffer_manager.py             # 2-min rolling transcript window (Redis)
│       ├── memory_service.py             # Cross-call memory — summaries via Mistral
│       ├── mistral_service.py            # Routing (small) + response formulation (large)
│       ├── elevenlabs_service.py         # TTS → base64 PCM
│       ├── openclaw_service.py           # Local OpenClaw agent HTTP calls
│       ├── recall_service.py             # Recall.ai bot create/status/remove/chat
│       ├── linear_service.py             # Direct Linear GraphQL API
│       └── gmail_service.py              # Direct Maton Gmail API proxy
│
└── ⚛️ frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── src/
        ├── main.tsx                      # React entry
        ├── App.tsx                       # Main component — polling, audio, UI
        ├── types.ts                      # TypeScript interfaces
        └── hooks/
            ├── useAudioPlayer.ts         # AudioContext + PCM decoding
            └── useTranscript.ts          # Recall.ai WebSocket connection
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Node.js 22+
- Redis (`brew install redis`)
- ngrok account ([ngrok.com](https://ngrok.com))
- OpenClaw (`npm install -g openclaw && openclaw onboard`)

### 1️⃣ Clone & Install

```bash
git clone https://github.com/bmirlico/call-claw.git
cd call-claw

# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 2️⃣ Configure Environment

Copy and fill in your API keys:

```bash
# Backend — call-claw/.env
RECALL_API_KEY=           # https://recall.ai → Dashboard → API Keys
RECALL_REGION=eu-central-1
MISTRAL_API_KEY=          # https://console.mistral.ai → API Keys
ELEVENLABS_API_KEY=       # https://elevenlabs.io → Profile → API Key
ELEVENLABS_VOICE_ID=cgSgspJ2msm6clMCkdW9
OPENCLAW_GATEWAY_TOKEN=   # openclaw config get gateway.auth.token
OPENCLAW_GATEWAY_URL=http://127.0.0.1:18789
LINEAR_API_KEY=           # https://linear.app → Settings → API
LINEAR_TEAM_ID=           # Your Linear team UUID
MATON_API_KEY=            # https://maton.ai → Settings
REDIS_URL=redis://localhost:6379
FRONTEND_URL=             # ngrok frontend URL (step 3)
BACKEND_URL=              # ngrok backend URL (step 3)
DEFAULT_TEAM_ID=team_demo

# Frontend — call-claw/frontend/.env
VITE_BACKEND_URL=         # same as BACKEND_URL above
```

### 3️⃣ Start All Services

```bash
# Terminal 1 — Redis
redis-server

# Terminal 2 — OpenClaw daemon
openclaw start

# Terminal 3 — Backend
cd backend && source venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 4 — Frontend
cd frontend && npm run dev

# Terminal 5 — ngrok (backend)
ngrok http 8000
# → copy URL into .env BACKEND_URL + frontend/.env VITE_BACKEND_URL

# Terminal 6 — ngrok (frontend)
ngrok http 5173
# → copy URL into .env FRONTEND_URL
```

### 4️⃣ Send Bot to a Meeting

```bash
# Seed memory for the recall demo
curl -X POST http://localhost:8000/memory/seed \
  -H "Content-Type: application/json" \
  -d '{
    "decisions": ["Switch to HubSpot for CRM"],
    "action_items": [{"task": "Create migration ticket", "assignee": "backend team", "tool": "Linear"}],
    "key_context": "Team chose HubSpot Enterprise over Salesforce."
  }'

# Join a Google Meet
curl -X POST http://localhost:8000/bot/join \
  -H "Content-Type: application/json" \
  -d '{"meeting_url": "https://meet.google.com/your-meeting-id"}'
```

Then admit the bot from the Google Meet waiting room and say **"Hey CallClaw, ..."**

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/bot/join` | Send bot to a Google Meet |
| `GET` | `/bot/status/{bot_id}` | Check bot status |
| `POST` | `/bot/end` | End call + generate summary + save memory |
| `POST` | `/process` | Process transcript segment (two-phase) |
| `GET` | `/action/{action_id}` | Poll for background action result |
| `GET` | `/memory/{team_id}` | View team memory (debug) |
| `DELETE` | `/memory/{team_id}` | Clear team memory |
| `POST` | `/memory/seed` | Seed fake past call for demos |

Full Swagger docs: `http://localhost:8000/docs`

---

## 🧠 How Cross-Call Memory Works

1. **During the call** — Every transcript segment feeds a 2-minute sliding buffer in Redis
2. **End of call** — Full transcript is sent to Mistral Large, which extracts:
   - Decisions made
   - Action items (with assignees)
   - Key context (2-3 sentence summary)
3. **Stored in Redis** — Last 10 calls per team, 30-day TTL
4. **Next call** — Memory is injected into Mistral's context on every `/process` request
5. **Recall** — "Hey CallClaw, what did we decide last week?" → references specific decisions with dates

---

## ⚡ Performance

| Action | Latency | Method |
|--------|---------|--------|
| 🧠 Memory Recall | ~3s | Local Redis lookup + Mistral response |
| 🎫 Linear Ticket | ~4s | Direct GraphQL API |
| 📧 Gmail Send | ~3s | Direct Maton API proxy |
| 🔍 Web Search | ~20-30s | OpenClaw agent (browser) |
| 📝 Notion Page | ~30-45s | OpenClaw agent (API) |

Confirmation audio ("Let me look that up...") plays instantly for all actions — pre-cached at startup.

---

## 👨‍💻 Author

**Bastien Mirlicourtois** — built in 48h for the Mistral Worldwide Hackathon

---

*Powered by [Mistral](https://mistral.ai) 🤖*
