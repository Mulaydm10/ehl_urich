import { useCallback, useEffect, useRef, useState } from 'react'
import { CircleMarker, Polyline, Tooltip } from 'react-leaflet'
import type { LatLngBoundsExpression, LatLngExpression } from 'leaflet'
import { ArrowLeft, Compass, Loader2, Mic, MicOff, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { BaseMap } from '../components/BaseMap'
import { useAccent } from '../components/useAccent'
import { useCopilot } from '../components/useCopilot'
import { speak, useSpeech } from '../components/useSpeech'
import { useAppState } from '../state/AppState'
import { rideContext, setActiveRoute } from '../services/copilot'
import {
  describeReroute,
  matchComplaint,
  progressAlong,
  reroute,
  summaryOf,
  type Progress,
  type RerouteChange,
} from '../services/navigate'
import { http } from '../services/http'
import { realtimeSupported, startRealtime, type RealtimeHandle, type RealtimeState } from '../services/realtime'
import { getAssistantStatus, type AssistantStatus } from '../services/assistant'
import { DIAL_Z, fitFor } from '../domain/bikeFit'
import { dialFor, modeKeyFor } from '../domain/ridePreference'
import { getPreference, subscribePreference } from '../services/ridePreference'
import type { RidePreference } from '../domain/ridePreference'

/**
 * Navigate: the screen for a rider who is moving and cannot touch anything.
 *
 * It follows the plan the app already holds — no new GPS watcher, no second
 * copy of the route — and gives three ways to change it without stopping:
 * speak to the live voice model, speak to the device recogniser when the
 * cloud is unavailable, or, at a standstill, hit one of the four complaints.
 * All three land on the same `reroute_from_here` tool, so what is spoken back
 * is the engine's own numbers.
 *
 * The screen never claims more than it has: no GPS fix means no re-plan, and
 * an alternative that reuses the same tarmac says so.
 */

const STOPS_WITHIN_KM = 40

interface StopAhead {
  lat: number
  lon: number
  gem_score: number | null
  flow: number | null
  km_ahead: number
  off_route_m: number
}

const COMPLAINTS: { change: RerouteChange; label: string; said: string }[] = [
  { change: 'more_fun', label: 'Boring', said: 'this road is boring' },
  { change: 'calmer', label: 'Too much', said: 'this is too much for me' },
  { change: 'scenic', label: 'Scenic', said: 'take me somewhere nicer' },
  { change: 'avoid_this_road', label: 'Off this road', said: 'get me off this road' },
]

function Stat({ value, unit, label }: { value: string; unit?: string; label: string }) {
  return (
    <div className="min-w-0">
      <p className="font-mono text-[22px] leading-none text-bone">
        {value}
        {unit ? <span className="ml-1 text-[11px] text-ash">{unit}</span> : null}
      </p>
      <p className="mt-1 text-[9px] uppercase tracking-[0.14em] text-ash">{label}</p>
    </div>
  )
}

export function NavigateScreen() {
  const accent = useAccent()
  const { bike } = useAppState()
  const [on, setOn] = useState(true)
  // The bike shapes what a re-plan asks for: the dial and mode its character
  // suits. It cannot touch the safety gate, which is the rider's own.
  const fit = fitFor(bike)
  // The rider's own answers outrank the bike preset when they exist: they are
  // what he said, not what his model implies.
  const [pref, setPref] = useState<RidePreference | null>(() => getPreference())
  useEffect(() => subscribePreference(setPref), [])
  const { state, position, route, suggestion, why, accept, dismiss } = useCopilot(on, {
    thrill: pref ? DIAL_Z[dialFor(pref)] : fit ? DIAL_Z[fit.dial] : 0.5,
    mode: pref ? (modeKeyFor(pref) ?? 'flow') : (fit?.mode ?? 'flow'),
    bikeId: bike?.id ?? null,
  })

  const [busy, setBusy] = useState<RerouteChange | null>(null)
  const [said, setSaid] = useState<string | null>(null)
  const [heard, setHeard] = useState<string | null>(null)
  const [stops, setStops] = useState<StopAhead[] | null>(null)
  const [cloud, setCloud] = useState<AssistantStatus | null>(null)
  const [live, setLive] = useState<RealtimeState | null>(null)
  const [liveDetail, setLiveDetail] = useState<string | null>(null)
  const liveRef = useRef<RealtimeHandle | null>(null)
  const speech = useSpeech()

  useEffect(() => {
    let alive = true
    void getAssistantStatus().then((s) => {
      if (alive) setCloud(s)
    })
    return () => {
      alive = false
    }
  }, [])

  const progress: Progress | null = progressAlong(
    route,
    position ? { lat: position.lat, lon: position.lng } : null,
  )

  /** One path for every way the rider can ask for a different road. */
  const ask = useCallback(
    async (change: RerouteChange, reason: string) => {
      setBusy(change)
      const res = await reroute(change, reason)
      setBusy(null)
      if ('error' in res) {
        setSaid(res.error)
        speak(res.error)
        return
      }
      setActiveRoute(res.plan)
      setStops(null)
      const line = describeReroute(res)
      setSaid(line)
      speak(line)
    },
    [],
  )

  const loadStops = useCallback(async () => {
    const ctx = rideContext()
    if (!ctx) return
    try {
      const run = await http.post<{ result?: { stops?: StopAhead[]; error?: string } }>(
        '/api/assistant/tool',
        { name: 'stops_ahead', args: { within_km: STOPS_WITHIN_KM }, context: { ride: ctx } },
        30000,
      )
      const found = run.result?.stops ?? []
      setStops(found)
      if (run.result?.error) setSaid(run.result.error)
    } catch {
      setSaid('The route engine is unreachable, so I cannot check what is ahead.')
    }
  }, [])

  const onHeard = useCallback(
    (text: string) => {
      setHeard(text)
      const change = matchComplaint(text)
      if (change) void ask(change, text)
      else if (/stop|coffee|nice|view/i.test(text)) void loadStops()
    },
    [ask, loadStops],
  )

  const canGoLive = !!cloud?.realtime?.enabled && realtimeSupported()

  const endLive = useCallback(() => {
    liveRef.current?.stop()
    liveRef.current = null
    setLive(null)
  }, [])
  useEffect(() => endLive, [endLive])

  const beginLive = useCallback(async () => {
    setLive('connecting')
    const handle = await startRealtime(
      () => ({ bikeId: bike?.id ?? null, navigate: true, ride: rideContext() }),
      {
        onState: (next, detail) => {
          setLive(next === 'closed' ? null : next)
          if (detail) setLiveDetail(detail)
        },
        onHeard: setHeard,
        onReply: setSaid,
        // A route the voice model planned is applied without a tap: the rider
        // is moving, and staying on Navigate is the point of the screen.
        onActions: (actions) => {
          for (const action of actions) {
            if (action.type === 'show_route') {
              setActiveRoute(action.plan)
              setStops(null)
            }
          }
        },
      },
    )
    liveRef.current = handle
  }, [bike])

  // Hands-free listening without the cloud: the device recogniser, restarted
  // each time it closes, so the rider never has to reach for the screen.
  const [localMic, setLocalMic] = useState(false)
  useEffect(() => {
    if (!localMic || speech.state === 'listening' || !speech.supported) return
    const id = window.setTimeout(() => speech.start(onHeard), 400)
    return () => window.clearTimeout(id)
  }, [localMic, speech, onHeard])

  const line: LatLngExpression[] = (route?.path ?? []).map((p) => [p[1], p[0]])
  const bounds: LatLngBoundsExpression | null =
    !position && line.length ? (line as LatLngBoundsExpression) : null
  const summary = summaryOf(route)
  const offRoute = progress != null && progress.offRouteM > 150

  return (
    <div className="pb-24">
      <div className="flex items-center gap-3 px-6 pb-3 pt-2">
        <Link to="/thrill" aria-label="Back to planning" className="action-orb h-9 w-9">
          <ArrowLeft size={18} strokeWidth={1.5} />
        </Link>
        <div className="min-w-0 flex-1">
          <p className="label">Navigate</p>
          <h1 className="truncate text-title">
            {route ? 'Following the plan' : 'No route loaded'}
          </h1>
        </div>
        <button
          type="button"
          onClick={() => setOn((v) => !v)}
          aria-pressed={on}
          className="rounded-control border border-white/20 px-3 py-1.5 text-[11px] uppercase tracking-[0.1em]"
        >
          {on ? 'Stop' : 'Start'}
        </button>
      </div>

      <div className="relative">
        <BaseMap
          bounds={bounds}
          height={320}
          style="dark"
          interactive
          center={position ? [position.lat, position.lng] : undefined}
          zoom={position ? 14 : 11}
        >
          {line.length ? (
            <>
              <Polyline positions={line} pathOptions={{ color: '#05080D', weight: 8, opacity: 0.4 }} />
              <Polyline positions={line} pathOptions={{ color: accent, weight: 4, opacity: 0.95 }} />
            </>
          ) : null}
          {(stops ?? []).map((s) => (
            <CircleMarker
              key={`${s.lat},${s.lon}`}
              center={[s.lat, s.lon]}
              radius={6}
              pathOptions={{ color: '#F7D154', weight: 2, fillColor: '#F7D154', fillOpacity: 0.8 }}
            >
              <Tooltip>{`${s.km_ahead} km ahead`}</Tooltip>
            </CircleMarker>
          ))}
          {position ? (
            <CircleMarker
              center={[position.lat, position.lng]}
              radius={8}
              pathOptions={{ color: '#FFFFFF', weight: 2, fillColor: accent, fillOpacity: 1 }}
            />
          ) : null}
        </BaseMap>

        <div className="absolute left-2 top-2 z-[400] flex flex-wrap gap-1.5">
          <span className="status-pill" data-live={state === 'watching'}>
            {state === 'watching'
              ? 'Live'
              : state === 'no_gps'
                ? 'Waiting for GPS'
                : state === 'unreachable'
                  ? 'Backend unreachable'
                  : 'Navigate off'}
          </span>
          {offRoute ? (
            <span className="rounded-control bg-void/85 px-2.5 py-1 font-mono text-[10px] text-bone">
              {Math.round(progress?.offRouteM ?? 0)} m off route
            </span>
          ) : null}
        </div>
      </div>

      <section className="panel mx-6 mt-4 grid grid-cols-3 gap-3 px-5 py-4" aria-label="Ride figures">
        <Stat
          value={position?.speedKmh != null ? String(Math.round(position.speedKmh)) : '—'}
          unit="km/h"
          label="Phone GPS"
        />
        <Stat
          value={progress ? progress.remainingKm.toFixed(1) : '—'}
          unit="km"
          label="Remaining"
        />
        <Stat
          value={progress?.remainingMin != null ? String(Math.round(progress.remainingMin)) : '—'}
          unit="min"
          label="Riding time"
        />
      </section>
      {pref ? (
        <p className="caption mx-6 mt-2">
          Following your ride profile — {dialFor(pref).toLowerCase()} dial, weighted on{' '}
          {(modeKeyFor(pref) ?? 'flow').replace('custom:', '')}. Your safety gate is unchanged.
        </p>
      ) : fit && bike ? (
        <p className="caption mx-6 mt-2">
          Tuned for the {bike.model} — {fit.dial.toLowerCase()} dial, {fit.mode} mode. Bike preset,
          not bike data; your safety gate is unchanged.
        </p>
      ) : null}
      {summary ? (
        <p className="caption mx-6 mt-2">
          Plan: {Math.round(summary.km)} km · fun {summary.fun_score.toFixed(2)} · asks{' '}
          {summary.max_demand.toFixed(0)}° of lean{' '}
          {route && route.refusals.length ? `· ${route.refusals.length} roads refused by your gate` : ''}
        </p>
      ) : (
        <p className="caption mx-6 mt-2">
          Plan a route on Thrill, or ask the assistant — Navigate follows whatever is planned.
        </p>
      )}

      <section className="panel mx-6 mt-4 px-5 py-4" aria-label="Hands-free voice">
        <div className="flex items-center gap-3">
          <span className="action-orb h-9 w-9 shrink-0">
            {live === 'live' || speech.state === 'listening' ? (
              <Mic size={18} strokeWidth={1.5} />
            ) : live === 'connecting' ? (
              <Loader2 size={18} className="animate-spin" strokeWidth={1.5} />
            ) : (
              <MicOff size={18} strokeWidth={1.5} />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-[14px] font-medium">Hands-free</h2>
            <p className="caption mt-1">
              {live === 'live'
                ? 'Listening. Say what you want changed.'
                : live === 'connecting'
                  ? 'Opening the live voice session…'
                  : liveDetail
                    ? liveDetail
                    : localMic
                      ? speech.supported
                        ? 'Listening on the device. Works without the cloud.'
                        : 'This device has no speech recogniser.'
                      : canGoLive
                        ? 'Live voice available.'
                        : 'Live voice is off on the server; the device recogniser still works.'}
            </p>
          </div>
          {canGoLive ? (
            <button
              type="button"
              onClick={() => (live ? endLive() : void beginLive())}
              className="rounded-control border border-white/20 px-3 py-1.5 text-[11px] uppercase tracking-[0.1em]"
            >
              {live ? 'Stop' : 'Talk'}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                setLocalMic((v) => !v)
                if (localMic) speech.stop()
              }}
              aria-pressed={localMic}
              className="rounded-control border border-white/20 px-3 py-1.5 text-[11px] uppercase tracking-[0.1em]"
            >
              {localMic ? 'Stop' : 'Listen'}
            </button>
          )}
        </div>
        {heard ? <p className="caption mt-3">Heard: “{heard}”</p> : null}
        {said ? <p className="mt-2 text-[13px] text-bone">{said}</p> : null}
      </section>

      <section className="mx-6 mt-4" aria-label="Change the road">
        <div className="grid grid-cols-2 gap-2">
          {COMPLAINTS.map((c) => (
            <button
              key={c.change}
              type="button"
              disabled={!!busy || !position}
              onClick={() => void ask(c.change, c.said)}
              className="rounded-control border border-white/12 bg-panel px-3 py-3 text-left text-[13px] disabled:opacity-40"
            >
              {busy === c.change ? 'Re-planning…' : c.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled={!route || !position}
          onClick={() => void loadStops()}
          className="mt-2 flex w-full items-center gap-2 rounded-control border border-white/12 bg-panel px-3 py-3 text-left text-[13px] disabled:opacity-40"
        >
          <Sparkles size={15} strokeWidth={1.6} />
          Scenic stops on the way
        </button>
        {stops ? (
          stops.length ? (
            <ul className="mt-2 space-y-1.5">
              {stops.map((s) => (
                <li key={`${s.lat},${s.lon}`} className="flex items-baseline justify-between rounded-control bg-panel px-3 py-2">
                  <span className="font-mono text-[12px] text-bone">{s.km_ahead} km ahead</span>
                  <span className="caption">
                    {s.off_route_m} m off the line
                    {s.gem_score != null ? ` · gem ${s.gem_score.toFixed(2)}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="caption mt-2">
              Nothing crowd-rated within {STOPS_WITHIN_KM} km of the road ahead.
            </p>
          )
        ) : null}
        {!position ? (
          <p className="caption mt-2">
            No GPS fix yet — nothing can be re-planned from here until there is one.
          </p>
        ) : null}
      </section>

      {suggestion ? (
        <section className="panel mx-6 mt-4 px-5 py-4" aria-label="Co-pilot suggestion">
          <div className="flex items-start gap-3">
            <span className="action-orb h-9 w-9 shrink-0"><Compass size={18} strokeWidth={1.5} /></span>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] text-bone">{suggestion.say}</p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => void accept()}
                  className="rounded-control bg-accent px-3 py-1.5 text-[11px] uppercase tracking-[0.1em] text-[var(--accent-contrast)]"
                >
                  Take it
                </button>
                <button
                  type="button"
                  onClick={dismiss}
                  className="rounded-control border border-white/20 px-3 py-1.5 text-[11px] uppercase tracking-[0.1em]"
                >
                  Not now
                </button>
              </div>
            </div>
          </div>
        </section>
      ) : why ? (
        <p className="caption mx-6 mt-4">{why}</p>
      ) : null}
    </div>
  )
}
