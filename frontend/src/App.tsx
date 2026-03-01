import { useState, useEffect, useRef, useCallback } from 'react'
import { useAudioPlayer } from './hooks/useAudioPlayer'
import { useTranscript } from './hooks/useTranscript'
import type {
  AppStatus,
  TranscriptSegment,
  LastAction,
  ProcessResponse,
  ActionResult,
} from './types'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL as string

const params = new URLSearchParams(window.location.search)
const BOT_ID = params.get('bot_id') ?? 'local_test'
const TEAM_ID = params.get('team_id') ?? 'team_demo'

async function pollActionResult(actionId: string): Promise<ActionResult | null> {
  const maxAttempts = 30
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, 1000))
    try {
      const res = await fetch(`${BACKEND_URL}/action/${actionId}`)
      if (!res.ok) continue
      const data = (await res.json()) as ActionResult
      if (data.ready) return data
    } catch {
      // retry
    }
  }
  return null
}

export default function App() {
  const [status, setStatus] = useState<AppStatus>('initializing')
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([])
  const [lastAction, setLastAction] = useState<LastAction | null>(null)

  const isProcessingRef = useRef(false)
  const isSpeakingRef = useRef(false)
  const transcriptRef = useRef<HTMLDivElement>(null)
  const { init: initAudio, playBase64 } = useAudioPlayer()

  const pendingRef = useRef<{ speaker: string; text: string } | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight
    }
  }, [transcript])

  const processSegment = useCallback(
    async (speaker: string, text: string): Promise<void> => {
      if (isProcessingRef.current || isSpeakingRef.current) return
      isProcessingRef.current = true

      try {
        const res = await fetch(`${BACKEND_URL}/process`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ bot_id: BOT_ID, team_id: TEAM_ID, speaker, text }),
        })

        if (!res.ok) {
          console.error('[APP] /process error:', res.status)
          return
        }

        const data = (await res.json()) as ProcessResponse

        if (data.action && data.action_id) {
          console.log(`[ACTION] ${data.action_type} — playing confirmation`)
          isSpeakingRef.current = true
          setStatus('speaking')
          setLastAction({
            type: data.action_type ?? 'generic',
            text: 'Processing...',
            timestamp: Date.now(),
          })

          // Phase 1: Play cached confirmation immediately
          if (data.confirmation_audio_b64) {
            await playBase64(data.confirmation_audio_b64)
          }

          // Phase 2: Poll for the action result
          const result = await pollActionResult(data.action_id)

          if (result?.audio_b64) {
            // Update action card with final response
            setLastAction({
              type: result.action_type ?? data.action_type ?? 'generic',
              text: result.response_text ?? '',
              timestamp: Date.now(),
            })

            // Play response audio
            await playBase64(result.audio_b64)
          }

          // Brief pause to absorb bot's own voice echo in transcript
          await new Promise((r) => setTimeout(r, 3000))
          isSpeakingRef.current = false
          setStatus('listening')
        }
      } catch (err) {
        console.error('[APP] processSegment error:', err)
      } finally {
        isProcessingRef.current = false
      }
    },
    [playBase64]
  )

  const handleSegment = useCallback(
    (speaker: string, text: string): void => {
      if (isSpeakingRef.current) return

      setTranscript((prev) => [...prev.slice(-20), { speaker, text }])

      pendingRef.current = { speaker, text }
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        const seg = pendingRef.current
        if (seg && !isSpeakingRef.current) {
          pendingRef.current = null
          processSegment(seg.speaker, seg.text)
        }
      }, 1500)
    },
    [processSegment]
  )

  const { connect, disconnect } = useTranscript({
    onSegment: handleSegment,
    onStatusChange: setStatus,
  })

  useEffect(() => {
    const init = async () => {
      try {
        await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
        await initAudio()
        connect()
        setStatus('connected')
      } catch (err) {
        console.error('[APP] Init error:', err)
        setStatus('error')
      }
    }

    init()
    return () => {
      disconnect()
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [initAudio, connect, disconnect])

  const statusConfig: Record<AppStatus, { color: string; label: string; pulse: boolean }> = {
    initializing: { color: '#475569', label: 'Initializing...', pulse: false },
    connected: { color: '#2563eb', label: 'Connected', pulse: false },
    listening: { color: '#16a34a', label: 'Listening', pulse: true },
    reconnecting: { color: '#d97706', label: 'Reconnecting...', pulse: false },
    speaking: { color: '#7c3aed', label: 'Speaking', pulse: true },
    error: { color: '#dc2626', label: 'Error — check console', pulse: false },
  }

  const { color, label, pulse } = statusConfig[status]

  const actionColors: Record<string, string> = {
    web_search: '#3b82f6',
    create_ticket: '#f59e0b',
    create_doc: '#10b981',
    send_email: '#6366f1',
    recall_memory: '#8b5cf6',
    generic: '#64748b',
  }

  return (
    <div
      style={{
        background: '#0f172a',
        color: '#e2e8f0',
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        gap: '20px',
      }}
    >
      {/* Logo + title */}
      <div style={{ textAlign: 'center' }}>
        <svg width="56" height="56" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="32" cy="32" r="30" stroke="#3b82f6" strokeWidth="2" fill="#1e293b"/>
          <path d="M20 38 L32 18 L44 38" stroke="#3b82f6" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
          <path d="M24 34 L32 22 L40 34" fill="#3b82f6" opacity="0.3"/>
          <circle cx="28" cy="32" r="2" fill="#60a5fa"/>
          <circle cx="36" cy="32" r="2" fill="#60a5fa"/>
          <path d="M22 40 L18 48" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round"/>
          <path d="M32 40 L32 48" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round"/>
          <path d="M42 40 L46 48" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round"/>
        </svg>
        <h1 style={{ fontSize: '26px', fontWeight: 700, marginTop: '8px', letterSpacing: '-0.5px' }}>
          CallClaw
        </h1>
        <p style={{ color: '#475569', fontSize: '12px', marginTop: '4px' }}>
          Operational memory for your team
        </p>
      </div>

      {/* Status indicator */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 18px',
          borderRadius: '20px',
          background: '#1e293b',
          fontSize: '13px',
        }}
      >
        <div
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: color,
            animation: pulse ? 'pulse 1.5s ease-in-out infinite' : 'none',
          }}
        />
        {label}
      </div>

      {/* Last action card */}
      {lastAction && (
        <div
          style={{
            background: '#1e293b',
            borderRadius: '10px',
            padding: '14px 18px',
            maxWidth: '420px',
            width: '100%',
            borderLeft: `3px solid ${actionColors[lastAction.type] ?? '#64748b'}`,
          }}
        >
          <div
            style={{
              color: actionColors[lastAction.type] ?? '#64748b',
              fontSize: '10px',
              textTransform: 'uppercase',
              letterSpacing: '1.2px',
              marginBottom: '6px',
              fontWeight: 600,
            }}
          >
            {lastAction.type.replace(/_/g, ' ')}
          </div>
          <div style={{ fontSize: '13px', lineHeight: 1.6, color: '#cbd5e1' }}>
            {lastAction.text}
          </div>
        </div>
      )}

      {/* Live transcript */}
      <div
        ref={transcriptRef}
        style={{
          background: '#1e293b',
          borderRadius: '10px',
          padding: '14px 18px',
          maxWidth: '420px',
          width: '100%',
          maxHeight: '160px',
          overflowY: 'auto',
        }}
      >
        <div
          style={{
            color: '#475569',
            fontSize: '10px',
            textTransform: 'uppercase',
            letterSpacing: '1px',
            marginBottom: '8px',
            fontWeight: 600,
          }}
        >
          Live transcript
        </div>
        {transcript.length === 0 ? (
          <div style={{ color: '#334155', fontStyle: 'italic', fontSize: '12px' }}>
            Waiting for conversation...
          </div>
        ) : (
          transcript.slice(-8).map((seg, i) => (
            <div key={i} style={{ marginBottom: '4px', fontSize: '12px', lineHeight: 1.5 }}>
              <span style={{ color: '#60a5fa', fontWeight: 600 }}>{seg.speaker}: </span>
              <span style={{ color: '#94a3b8' }}>{seg.text}</span>
            </div>
          ))
        )}
      </div>

      {/* Debug info */}
      <div style={{ color: '#1e293b', fontSize: '10px' }}>
        bot: {BOT_ID} · team: {TEAM_ID}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.85); }
        }
      `}</style>
    </div>
  )
}
