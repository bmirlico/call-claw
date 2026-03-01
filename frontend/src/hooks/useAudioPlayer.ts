import { useRef, useCallback } from 'react'

const SAMPLE_RATE = 24000 // Must match ElevenLabs pcm_24000 output

export function useAudioPlayer() {
  const audioContextRef = useRef<AudioContext | null>(null)

  const init = useCallback(async (): Promise<void> => {
    audioContextRef.current = new AudioContext({
      sampleRate: SAMPLE_RATE,
      latencyHint: 'interactive',
    })
  }, [])

  const playBase64 = useCallback((b64Audio: string): Promise<void> => {
    return new Promise(async (resolve) => {
      const ctx = audioContextRef.current
      if (!ctx) {
        resolve()
        return
      }

      try {
        if (ctx.state === 'suspended') {
          await ctx.resume()
        }

        // Decode base64 → raw bytes
        const binary = atob(b64Audio)
        const bytes = new Uint8Array(binary.length)
        for (let i = 0; i < binary.length; i++) {
          bytes[i] = binary.charCodeAt(i)
        }

        // PCM 16-bit signed little-endian → Float32 AudioBuffer
        // No MP3 decoding needed — direct sample conversion
        const int16 = new Int16Array(bytes.buffer)
        const audioBuffer = ctx.createBuffer(1, int16.length, SAMPLE_RATE)
        const channelData = audioBuffer.getChannelData(0)
        for (let i = 0; i < int16.length; i++) {
          channelData[i] = int16[i] / 32768
        }

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
