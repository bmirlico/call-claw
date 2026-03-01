import { useRef, useCallback } from 'react'
import type { RecallTranscriptMessage } from '../types'

const RECALL_WS_URL = 'wss://meeting-data.bot.recall.ai/api/v1/transcript'

interface UseTranscriptOptions {
  onSegment: (speaker: string, text: string) => void
  onStatusChange: (status: 'listening' | 'reconnecting') => void
}

export function useTranscript({ onSegment, onStatusChange }: UseTranscriptOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback((): void => {
    // Prevent duplicate connections (React StrictMode calls effects twice)
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
      return
    }

    try {
      wsRef.current = new WebSocket(RECALL_WS_URL)

      wsRef.current.onopen = () => {
        console.log('[TRANSCRIPT] WebSocket connected')
        onStatusChange('listening')
      }

      wsRef.current.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string) as RecallTranscriptMessage
          const words = data?.transcript?.words
          if (!words || words.length === 0) return

          const text = words.map((w) => w.text).join(' ').trim()
          const speaker = words[0]?.speaker ?? 'Unknown'

          if (!text || text.split(' ').length < 3) return

          onSegment(speaker, text)
        } catch (err) {
          console.error('[TRANSCRIPT] Parse error:', err)
        }
      }

      wsRef.current.onclose = (event: CloseEvent) => {
        console.log(`[TRANSCRIPT] WebSocket closed (${event.code}) — reconnecting in 2s`)
        onStatusChange('reconnecting')
        reconnectTimerRef.current = setTimeout(connect, 2000)
      }

      wsRef.current.onerror = (err: Event) => {
        console.error('[TRANSCRIPT] WebSocket error:', err)
      }
    } catch (err) {
      console.error('[TRANSCRIPT] Failed to open WebSocket:', err)
      reconnectTimerRef.current = setTimeout(connect, 3000)
    }
  }, [onSegment, onStatusChange])

  const disconnect = useCallback((): void => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
    }
    wsRef.current?.close()
  }, [])

  return { connect, disconnect }
}
