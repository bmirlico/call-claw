export type AppStatus =
  | 'initializing'
  | 'connected'
  | 'listening'
  | 'reconnecting'
  | 'speaking'
  | 'error'

export interface TranscriptSegment {
  speaker: string
  text: string
}

export interface LastAction {
  type: string
  text: string
  timestamp: number
}

export interface ProcessResponse {
  action: boolean
  audio_b64?: string
  response_text?: string
  action_type?: string
}

// Shape of Recall.ai WebSocket transcript message
export interface RecallTranscriptMessage {
  transcript?: {
    words?: Array<{
      text: string
      speaker?: string
    }>
  }
}
