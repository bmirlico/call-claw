import { useRef, useCallback } from 'react'

export function useAudioPlayer() {
  const audioContextRef = useRef<AudioContext | null>(null)

  const init = useCallback(async (): Promise<void> => {
    audioContextRef.current = new AudioContext()
  }, [])

  const playBase64 = useCallback((b64Audio: string): Promise<void> => {
    return new Promise(async (resolve) => {
      const ctx = audioContextRef.current
      if (!ctx) {
        resolve()
        return
      }

      try {
        // Resume context if suspended by browser autoplay policy
        if (ctx.state === 'suspended') {
          await ctx.resume()
        }

        // Decode base64 → ArrayBuffer
        const binary = atob(b64Audio)
        const bytes = new Uint8Array(binary.length)
        for (let i = 0; i < binary.length; i++) {
          bytes[i] = binary.charCodeAt(i)
        }

        // Decode MP3 → AudioBuffer → play
        // Recall.ai captures this AudioContext output and injects it into the call
        const audioBuffer = await ctx.decodeAudioData(bytes.buffer)
        const source = ctx.createBufferSource()
        source.buffer = audioBuffer
        source.connect(ctx.destination)
        source.onended = () => resolve()
        source.start(0)
      } catch (err) {
        console.error('[AUDIO] Playback error:', err)
        resolve()
      }
    })
  }, [])

  return { init, playBase64 }
}
