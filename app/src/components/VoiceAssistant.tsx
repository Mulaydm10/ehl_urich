import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Mic, MicOff, Sparkles, X } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { useSpeech } from './useSpeech'
import { VOICE_EXAMPLES, resolveVoice } from '../services/voiceIntents'
import {
  type AssistantAction,
  type AssistantStatus,
  askAssistant,
  getAssistantStatus,
  routeForScreen,
  setPendingPlan,
} from '../services/assistant'
import { rideContext, setActiveRoute } from '../services/copilot'
import { describeReroute, matchComplaint, reroute, type RerouteVia } from '../services/navigate'
import {
  type RealtimeHandle,
  type RealtimeState,
  realtimeSupported,
  startRealtime,
} from '../services/realtime'

/**
 * Hands-free assistant. Tap the mic, speak, and the answer is spoken back.
 *
 * Three tiers, best first, each falling back to the next:
 *   1. OpenAI Realtime - a live audio session; the rider talks, the model
 *      talks back and calls the app's own functions while it does.
 *   2. The typed cloud assistant - same model family, same tools, with the
 *      device reading the answer out.
 *   3. resolveVoice on-device, from data already loaded, so the panel never
 *      invents numbers when the backend is unreachable.
 */
export function VoiceAssistant() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const navigating = pathname === '/navigate'
  const { bike, bikes, routes, rides, stats, online, engine, selectBike } = useAppState()
  const { state, transcript, start, stop, speak, supported } = useSpeech()
  const [open, setOpen] = useState(false)
  const [reply, setReply] = useState<string | null>(null)
  const [heard, setHeard] = useState<string | null>(null)
  const [thinking, setThinking] = useState(false)
  const [cloud, setCloud] = useState<AssistantStatus | null>(null)
  const [usedCloud, setUsedCloud] = useState(false)
  // Which of the app's own tools answered, so the footer names them rather
  // than leaving the rider to guess whether the engine was involved.
  const [usedTools, setUsedTools] = useState<string[]>([])
  const [cloudFailed, setCloudFailed] = useState(false)
  const [typed, setTyped] = useState('')
  const [live, setLive] = useState<RealtimeState | null>(null)
  const [liveDetail, setLiveDetail] = useState<string | null>(null)
  const liveRef = useRef<RealtimeHandle | null>(null)

  useEffect(() => {
    let alive = true
    void getAssistantStatus().then((s) => {
      if (alive) setCloud(s)
    })
    return () => {
      alive = false
    }
  }, [online])

  const applyActions = useCallback(
    (actions: AssistantAction[]) => {
      let go: string | null = null
      let planned = false
      for (const action of actions) {
        if (action.type === 'select_bike') selectBike(action.bikeId)
        if (action.type === 'show_route') {
          // Whatever was just planned is now the plan being ridden, so the
          // co-pilot measures against it and Navigate draws it.
          setActiveRoute(action.plan)
          setPendingPlan(action.plan)
          planned = true
        }
        if (action.type === 'navigate') go = routeForScreen(action.screen) ?? go
      }
      // A fresh plan wins over whichever screen the model asked for: Thrill is
      // the only screen that can draw it, and being told about a route that is
      // nowhere on screen is worse than ignoring the model's choice. Mid-ride
      // is the exception: a rider following a route must not be thrown onto a
      // planning screen because they asked for a different road.
      if (planned) go = navigating ? null : '/thrill'
      if (navigating) {
        setOpen(false)
        return
      }
      if (go) {
        setOpen(false)
        navigate(go)
      }
    },
    [navigate, navigating, selectBike],
  )

  /**
   * A complaint about the road, answered without the model.
   *
   * `reroute_from_here` is the engine, not OpenAI, so this keeps working with
   * no key and with the cloud assistant down — which is exactly when a rider
   * mid-ride still wants off a road. Returns false when the sentence was not
   * about the road, so the normal fallback runs.
   */
  const runComplaint = useCallback(
    async (text: string, via: RerouteVia): Promise<boolean> => {
      const change = matchComplaint(text)
      const ctx = rideContext()
      if (!change || !ctx) return false
      setThinking(true)
      const res = await reroute(change, text, ctx, via)
      setThinking(false)
      setUsedCloud(false)
      if ('error' in res) {
        setReply(res.error)
        speak(res.error)
        return true
      }
      setActiveRoute(res.plan)
      const said = describeReroute(res)
      setReply(said)
      speak(said)
      if (!navigating) {
        setPendingPlan(res.plan)
        setOpen(false)
        navigate('/navigate')
      }
      return true
    },
    [navigate, navigating, speak],
  )

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
    async (text: string, via: RerouteVia = 'typed') => {
      setHeard(text)
      setReply(null)
      if (!cloud?.enabled) {
        if (await runComplaint(text, via)) return
        runLocal(text)
        return
      }
      setThinking(true)
      const answer = await askAssistant(text, {
        bikeId: bike?.id ?? null,
        bikes: bikes.map((b) => ({ id: b.id, model: b.model })),
        online,
        engine,
        ride: rideContext(),
      }, via === 'voice' ? 'voice' : 'typed')
      setThinking(false)
      if (!answer) {
        setCloudFailed(true)
        setUsedCloud(false)
        if (await runComplaint(text, via)) return
        runLocal(text)
        return
      }
      setCloudFailed(false)
      setUsedCloud(true)
      setUsedTools(answer.toolsUsed)
      setReply(answer.say)
      speak(answer.say)
      applyActions(answer.actions)
    },
    [cloud, bike, bikes, online, engine, speak, runLocal, runComplaint, applyActions],
  )

  const canGoLive = !!cloud?.realtime?.enabled && realtimeSupported()

  const endLive = useCallback(() => {
    liveRef.current?.stop()
    liveRef.current = null
    setLive(null)
  }, [])

  // Hanging up on unmount matters: an open session holds the microphone and
  // keeps billing for it.
  useEffect(() => endLive, [endLive])

  const beginLive = useCallback(async () => {
    setReply(null)
    setHeard(null)
    setLiveDetail(null)
    setLive('connecting')
    const handle = await startRealtime(
      () => ({
        bikeId: bike?.id ?? null,
        bikes: bikes.map((b) => ({ id: b.id, model: b.model })),
        online,
        engine,
        ride: rideContext(),
      }),
      {
        onState: (next, detail) => {
          setLive(next === 'closed' ? null : next)
          if (detail) setLiveDetail(detail)
        },
        onHeard: setHeard,
        onReply: (text) => {
          // The audio is already playing from OpenAI; this is just the caption.
          setUsedCloud(true)
          setCloudFailed(false)
          setReply(text)
        },
        onActions: applyActions,
      },
    )
    liveRef.current = handle
  }, [bike, bikes, online, engine, applyActions])

  const listening = state === 'listening'
  const micOn = listening || live === 'live' || live === 'connecting'

  const toggleMic = () => {
    if (canGoLive) {
      if (liveRef.current || live === 'connecting') endLive()
      else void beginLive()
      return
    }
    if (listening) stop()
    else {
      setReply(null)
      setHeard(null)
      start((text) => {
        void run(text, 'voice')
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
        {live === 'live' ? (
          <span
            className="pointer-events-none absolute inset-0 rounded-full"
            style={{ border: '2px solid var(--accent)', animation: 'pulse 1100ms ease-in-out infinite alternate' }}
          />
        ) : null}
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
            aria-label={micOn ? 'Stop listening' : 'Start listening'}
            aria-pressed={micOn}
            disabled={!supported && !canGoLive}
            onClick={toggleMic}
            className="relative flex h-[84px] w-[84px] items-center justify-center rounded-full disabled:opacity-40"
            style={{
              background: micOn ? 'var(--accent)' : 'var(--surface-raised)',
              color: micOn ? 'var(--accent-contrast)' : '#F1F2F3',
            }}
          >
            {micOn ? (
              <span
                className="pointer-events-none absolute inset-0 rounded-full"
                style={{ border: '2px solid var(--accent)', animation: 'pulse 1100ms ease-in-out infinite alternate' }}
              />
            ) : null}
            {supported || canGoLive ? <Mic size={30} strokeWidth={1.7} /> : <MicOff size={30} strokeWidth={1.7} />}
          </button>

          <p className="mt-4 text-center text-[12px] leading-relaxed text-ash">
            {thinking
              ? 'Thinking\u2026'
              : live === 'connecting'
              ? 'Opening the live voice link\u2026'
              : live === 'live'
              ? 'Live \u2014 just talk. Tap to hang up.'
              : live === 'error'
              ? liveDetail ?? 'Live voice failed.'
              : canGoLive
              ? 'Tap to talk live'
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

        {!heard && !listening && !live ? (
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
          {!cloud?.enabled
            ? 'On-device answers \u00b7 cloud assistant not configured on the server'
            : cloudFailed
              ? 'Cloud assistant unreachable \u00b7 answered on-device'
              : live === 'live'
                ? `Realtime voice \u00b7 ${cloud.realtime?.model ?? 'openai'} \u00b7 speaking live`
                : `Cloud assistant \u00b7 ${cloud.model ?? 'openai'} \u00b7 ${
                    usedCloud
                      ? usedTools.length
                        ? `answered live · ${usedTools.join(', ')}`
                        : 'answered live'
                      : canGoLive
                        ? 'realtime voice ready'
                        : 'ready'
                  }`}
        </p>
      </section>
    </div>
  )
}
