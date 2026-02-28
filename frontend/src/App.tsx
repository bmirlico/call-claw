import { useState, useEffect, useRef, useCallback } from 'react'
import { useAudioPlayer } from './hooks/useAudioPlayer'
import { useTranscript } from './hooks/useTranscript'
import type {
  AppStatus,
  TranscriptSegment,
  LastAction,
  ProcessResponse,
} from './types'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL as string

// Recall.ai passes bot_id and team_id as URL params when loading this page
// in headless Chromium. They won't be present when opening locally in a browser.
const params = new URLSearchParams(window.location.search)
const BOT_ID = params.get('bot_id') ?? 'local_test'
const TEAM_ID = params.get('team_id') ?? 'team_demo'

export default function App() {
  const [status, setStatus] = useState<AppStatus>('initializing')
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([])
  const [lastAction, setLastAction] = useState<LastAction | null>(null)

  const isProcessingRef = useRef(false)
  const { init: initAudio, playBase64 } = useAudioPlayer()

  const handleSegment = useCallback(
    async (speaker: string, text: string): Promise<void> => {
      // Update live transcript display
      setTranscript((prev) => [...prev.slice(-20), { speaker, text }])

      // Prevent concurrent processing of multiple segments
      if (isProcessingRef.current) return
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

        if (data.action) {
          console.log(`[ACTION] ${data.action_type}: ${data.response_text}`)
          setStatus('speaking')
          setLastAction({
            type: data.action_type ?? 'generic',
            text: data.response_text ?? '',
            timestamp: Date.now(),
          })

          // Play confirmation first ("Let me look that up...")
          if (data.confirmation_audio_b64) {
            await playBase64(data.confirmation_audio_b64)
          }

          // Then play the full response
          if (data.response_audio_b64) {
            await playBase64(data.response_audio_b64)
          }

          setStatus('listening')
        }
      } catch (err) {
        console.error('[APP] handleSegment error:', err)
      } finally {
        isProcessingRef.current = false
      }
    },
    [playBase64]
  )

  const { connect, disconnect } = useTranscript({
    onSegment: handleSegment,
    onStatusChange: setStatus,
  })

  useEffect(() => {
    const init = async () => {
      try {
        // getUserMedia is required — Recall.ai injects the mixed call audio here
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
    return () => disconnect()
  }, [initAudio, connect, disconnect])

  const statusConfig: Record<AppStatus, { color: string; label: string; pulse: boolean }> = {
    initializing: { color: '#475569', label: 'Initializing...', pulse: false },
    connected: { color: '#2563eb', label: 'Connected', pulse: false },
    listening: { color: '#16a34a', label: '🎧 Listening', pulse: true },
    reconnecting: { color: '#d97706', label: 'Reconnecting...', pulse: false },
    speaking: { color: '#7c3aed', label: '🔊 Speaking', pulse: true },
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
        <div style={{ fontSize: '56px', lineHeight: 1 }}>🦅</div>
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
