import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mic, MicOff, Sparkles, X } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { useSpeech } from './useSpeech'
import { VOICE_EXAMPLES, resolveVoice } from '../services/voiceIntents'

/**
 * Hands-free assistant. Tap the mic, speak, and the answer is spoken back.
 *
 * Answers come from `resolveVoice`, which reads data the app already holds.
 * The cloud assistant (OpenAI Realtime + backend tools) replaces that resolver
 * later; the surface here stays the same.
 */
export function VoiceAssistant() {
  const navigate = useNavigate()
  const { bike, routes, rides, stats, online, engine } = useAppState()
  const { state, transcript, start, stop, speak, supported } = useSpeech()
  const [open, setOpen] = useState(false)
  const [reply, setReply] = useState<string | null>(null)
  const [heard, setHeard] = useState<string | null>(null)

  const run = useCallback(
    (text: string) => {
      setHeard(text)
      const answer = resolveVoice(text, { bike, routes, rides, stats, online, engine })
      setReply(answer.say)
      speak(answer.say)
      if (answer.go) {
        setOpen(false)
        navigate(answer.go)
      }
    },
    [bike, routes, rides, stats, online, engine, speak, navigate],
  )

  const listening = state === 'listening'
  const toggleMic = () => {
    if (listening) stop()
    else {
      setReply(null)
      setHeard(null)
      start(run)
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        aria-label="Voice assistant"
        onClick={() => setOpen(true)}
        className="absolute bottom-[104px] right-5 z-30 flex h-14 w-14 items-center justify-center rounded-full shadow-[0_10px_28px_rgba(0,0,0,0.45)]"
        style={{ background: 'var(--accent)', color: 'var(--accent-contrast)' }}
      >
        <Mic size={22} strokeWidth={1.9} />
      </button>
    )
  }

  return (
    <div className="absolute inset-0 z-40 flex flex-col justify-end bg-black/55 backdrop-blur-[2px]">
      <button type="button" aria-label="Close voice assistant" className="flex-1" onClick={() => setOpen(false)} />

      <section
        aria-label="Voice assistant"
        className="relative rounded-t-[28px] bg-panel px-6 pb-[max(24px,env(safe-area-inset-bottom))] pt-6"
        style={{ animation: 'enter 200ms ease-out both' }}
      >
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles size={15} style={{ color: 'var(--accent-text)' }} />
            <span className="label">Ride assistant</span>
          </div>
          <button type="button" aria-label="Close" onClick={() => setOpen(false)} className="text-ash">
            <X size={18} />
          </button>
        </header>

        <div className="mt-6 flex flex-col items-center">
          <button
            type="button"
            aria-label={listening ? 'Stop listening' : 'Start listening'}
            aria-pressed={listening}
            disabled={!supported}
            onClick={toggleMic}
            className="relative flex h-[84px] w-[84px] items-center justify-center rounded-full disabled:opacity-40"
            style={{
              background: listening ? 'var(--accent)' : 'var(--surface-raised)',
              color: listening ? 'var(--accent-contrast)' : '#F1F2F3',
            }}
          >
            {listening ? (
              <span
                className="pointer-events-none absolute inset-0 rounded-full"
                style={{ border: '2px solid var(--accent)', animation: 'pulse 1100ms ease-in-out infinite alternate' }}
              />
            ) : null}
            {supported ? <Mic size={30} strokeWidth={1.7} /> : <MicOff size={30} strokeWidth={1.7} />}
          </button>

          <p className="mt-4 text-center text-[12px] leading-relaxed text-ash">
            {state === 'unsupported'
              ? 'Speech recognition is unavailable on this device.'
              : state === 'denied'
                ? 'Speech recognition was refused here. Android WebView has no recogniser \u2014 tap a prompt instead.'
                : listening
                  ? 'Listening\u2026'
                  : 'Tap to speak'}
          </p>
        </div>

        {listening && transcript ? (
          <p className="mt-5 text-center text-[15px] leading-relaxed text-bone">{transcript}</p>
        ) : null}

        {heard && !listening ? (
          <div className="mt-6 space-y-3">
            <p className="text-[13px] leading-relaxed text-ash">&ldquo;{heard}&rdquo;</p>
            {reply ? <p className="text-[15px] leading-relaxed text-bone">{reply}</p> : null}
          </div>
        ) : null}

        {!heard && !listening ? (
          <ul className="mt-6 space-y-2">
            {VOICE_EXAMPLES.map((example) => (
              <li key={example}>
                <button type="button" onClick={() => run(example)} className="chip w-full justify-start text-left">
                  {example}
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <p className="mt-6 text-center font-mono text-[9px] uppercase tracking-[0.12em] text-ash">
          On-device speech &middot; cloud assistant not connected
        </p>
      </section>
    </div>
  )
}
