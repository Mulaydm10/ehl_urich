import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mic, MicOff, Sparkles, X } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { useSpeech } from './useSpeech'
import { VOICE_EXAMPLES, resolveVoice } from '../services/voiceIntents'
import {
  type AssistantStatus,
  askAssistant,
  getAssistantStatus,
  routeForScreen,
} from '../services/assistant'

/**
 * Hands-free assistant. Tap the mic, speak, and the answer is spoken back.
 *
 * When the backend has an OpenAI key it does the thinking: the model calls the
 * app's own functions (plan a route, read the bike, open a screen) and the
 * reply can navigate the app or switch bikes. Without a key, or with the
 * backend unreachable, `resolveVoice` answers on-device from data already
 * loaded, so the panel never invents numbers.
 */
export function VoiceAssistant() {
  const navigate = useNavigate()
  const { bike, bikes, routes, rides, stats, online, engine, selectBike } = useAppState()
  const { state, transcript, start, stop, speak, supported } = useSpeech()
  const [open, setOpen] = useState(false)
  const [reply, setReply] = useState<string | null>(null)
  const [heard, setHeard] = useState<string | null>(null)
  const [thinking, setThinking] = useState(false)
  const [cloud, setCloud] = useState<AssistantStatus | null>(null)
  const [usedCloud, setUsedCloud] = useState(false)
  const [typed, setTyped] = useState('')

  useEffect(() => {
    let alive = true
    void getAssistantStatus().then((s) => {
      if (alive) setCloud(s)
    })
    return () => {
      alive = false
    }
  }, [online])

  const runLocal = useCallback(
    (text: string) => {
      const answer = resolveVoice(text, { bike, routes, rides, stats, online, engine })
      setUsedCloud(false)
      setReply(answer.say)
      speak(answer.say)
      if (answer.go) {
        setOpen(false)
        navigate(answer.go)
      }
    },
    [bike, routes, rides, stats, online, engine, speak, navigate],
  )

  const run = useCallback(
    async (text: string) => {
      setHeard(text)
      setReply(null)
      if (!cloud?.enabled) {
        runLocal(text)
        return
      }
      setThinking(true)
      const answer = await askAssistant(text, {
        bikeId: bike?.id ?? null,
        bikes: bikes.map((b) => ({ id: b.id, model: b.model })),
        online,
        engine,
      })
      setThinking(false)
      if (!answer) {
        runLocal(text)
        return
      }
      setUsedCloud(true)
      setReply(answer.say)
      speak(answer.say)
      for (const action of answer.actions) {
        if (action.type === 'select_bike') selectBike(action.bikeId)
        if (action.type === 'navigate') {
          const path = routeForScreen(action.screen)
          if (path) {
            setOpen(false)
            navigate(path)
          }
        }
      }
    },
    [cloud, bike, bikes, online, engine, speak, navigate, selectBike, runLocal],
  )

  const listening = state === 'listening'
  const toggleMic = () => {
    if (listening) stop()
    else {
      setReply(null)
      setHeard(null)
      start((text) => {
        void run(text)
      })
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
            {thinking
              ? 'Thinking\u2026'
              : state === 'unsupported'
              ? 'Speech recognition is unavailable on this device.'
              : state === 'denied'
                ? 'Speech recognition was refused here. Android WebView has no recogniser \u2014 tap a prompt instead.'
                : listening
                  ? 'Listening\u2026'
                  : 'Tap to speak'}
          </p>
        </div>

        <form
          className="mt-5 flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            const text = typed.trim()
            if (!text || thinking) return
            setTyped('')
            void run(text)
          }}
        >
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="or type a command"
            aria-label="Type a command for the assistant"
            className="h-11 flex-1 rounded-full bg-[var(--surface-raised)] px-4 text-[13px] text-bone outline-none placeholder:text-ash"
          />
          <button
            type="submit"
            disabled={!typed.trim() || thinking}
            className="h-11 rounded-full px-4 text-[12px] font-medium disabled:opacity-40"
            style={{ background: 'var(--accent)', color: 'var(--accent-contrast)' }}
          >
            Ask
          </button>
        </form>

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
                <button
                  type="button"
                  onClick={() => {
                    void run(example)
                  }}
                  className="chip w-full justify-start text-left"
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <p className="mt-6 text-center font-mono text-[9px] uppercase tracking-[0.12em] text-ash">
          {cloud?.enabled
            ? `Cloud assistant \u00b7 ${cloud.model ?? 'openai'} \u00b7 ${usedCloud ? 'answered live' : 'ready'}`
            : 'On-device answers \u00b7 cloud assistant not configured on the server'}
        </p>
      </section>
    </div>
  )
}
