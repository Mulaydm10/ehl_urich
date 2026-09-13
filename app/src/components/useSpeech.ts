import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Thin wrapper over the browser Web Speech API (SpeechRecognition +
 * speechSynthesis). No key, works offline on supporting engines. This is the
 * local-only layer; a later branch swaps recognition/answers for the
 * OpenAI Realtime API served from the Mac backend.
 */

interface SpeechRecognitionResultLike {
  0: { transcript: string }
  isFinal: boolean
}
interface SpeechRecognitionEventLike {
  resultIndex: number
  results: { length: number; [index: number]: SpeechRecognitionResultLike }
}
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  abort(): void
  onresult: ((e: SpeechRecognitionEventLike) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export type ListenState = 'idle' | 'listening' | 'unsupported' | 'denied'

/** Say a line through the device's own voice, without starting a recogniser. */
export function speak(text: string): void {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.lang = 'en-US'
  u.rate = 1.02
  window.speechSynthesis.speak(u)
}

export function useSpeech() {
  const [state, setState] = useState<ListenState>('idle')
  const [transcript, setTranscript] = useState('')
  const recognition = useRef<SpeechRecognitionLike | null>(null)
  const onFinal = useRef<(text: string) => void>(() => {})

  useEffect(() => {
    const Ctor = getRecognitionCtor()
    if (!Ctor) {
      setState('unsupported')
      return
    }
    const rec = new Ctor()
    rec.lang = 'en-US'
    rec.continuous = false
    rec.interimResults = true
    rec.onresult = (e) => {
      let text = ''
      for (let i = e.resultIndex; i < e.results.length; i += 1) text += e.results[i][0].transcript
      setTranscript(text)
      if (e.results[e.results.length - 1]?.isFinal) onFinal.current(text.trim())
    }
    rec.onerror = (e) => setState(e.error === 'not-allowed' || e.error === 'service-not-allowed' ? 'denied' : 'idle')
    rec.onend = () => setState((s) => (s === 'listening' ? 'idle' : s))
    recognition.current = rec
    return () => rec.abort()
  }, [])

  const start = useCallback((handler: (text: string) => void) => {
    const rec = recognition.current
    if (!rec) return
    onFinal.current = handler
    setTranscript('')
    try {
      rec.start()
      setState('listening')
    } catch {
      /* already started */
    }
  }, [])

  const stop = useCallback(() => {
    recognition.current?.stop()
    setState('idle')
  }, [])

  return { state, transcript, start, stop, speak, supported: state !== 'unsupported' }
}
