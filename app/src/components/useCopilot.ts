/**
 * The live co-pilot loop, phone side.
 *
 * One job: turn the existing GPS watch into a slow, cheap heartbeat to
 * /api/copilot/tick and hold whatever suggestion comes back. All the
 * judgement — whether there is anything to say, and how it is worded — lives
 * on the backend next to the routing engine. Here we only decide when to
 * bother it: not more often than TICK_MS, and only when the rider has
 * actually moved, so a bike parked outside a cafe costs nothing.
 *
 * It reuses useLivePosition rather than opening a second watchPosition: two
 * GPS watchers on one phone is battery the rider notices.
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { FsRouteResult } from '../domain/types'
import {
  copilot,
  getActiveRoute,
  setActiveRoute,
  setLiveFix,
  subscribeActiveRoute,
  toCopilotRoute,
  type CopilotSuggestion,
} from '../services/copilot'
import { useLivePosition, type LivePosition, type LiveState } from './useLivePosition'

const TICK_MS = 20000
const MOVED_M = 40          // below this the fix is GPS noise, not progress
const IDLE_TICK_MS = 120000 // ... but still check in occasionally when parked

export type CopilotState =
  | 'off'
  | 'no_gps'
  | 'watching'
  | 'unreachable'

export interface CopilotView {
  state: CopilotState
  /** The suggestion currently on screen, if any. */
  suggestion: CopilotSuggestion | null
  /** The backend's own reason for staying quiet — shown verbatim. */
  why: string | null
  route: FsRouteResult | null
  /** The fix the loop is running on, for screens that draw it. */
  position: LivePosition | null
  ticks: number
  accept: () => Promise<FsRouteResult | null>
  dismiss: () => void
  busy: boolean
}

function metres(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const r = 6371008.8
  const p1 = (a.lat * Math.PI) / 180
  const p2 = (b.lat * Math.PI) / 180
  const dp = p2 - p1
  const dl = ((b.lng - a.lng) * Math.PI) / 180
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * r * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))))
}

const gpsState = (s: LiveState): CopilotState =>
  s === 'tracking' ? 'watching' : 'no_gps'

export function useCopilot(
  enabled: boolean,
  opts: { riderKey?: string; thrill?: number; mode?: string; bikeId?: string | null } = {},
): CopilotView {
  const { state: liveState, position } = useLivePosition(enabled)
  const [suggestion, setSuggestion] = useState<CopilotSuggestion | null>(null)
  const [why, setWhy] = useState<string | null>(null)
  const [reachable, setReachable] = useState(true)
  const [ticks, setTicks] = useState(0)
  const [busy, setBusy] = useState(false)
  const [route, setRoute] = useState<FsRouteResult | null>(() => getActiveRoute())

  const session = `ride-${useId()}`
  const lastSentAt = useRef(0)
  const lastSentAtPos = useRef<{ lat: number; lng: number } | null>(null)
  const inFlight = useRef(false)
  const opt = useRef(opts)
  useEffect(() => {
    opt.current = opts
  })

  useEffect(() => subscribeActiveRoute(setRoute), [])

  // Publish the fix so the assistant's mid-ride tools can re-plan from where
  // the bike actually is, whichever screen the rider is talking from.
  useEffect(() => {
    if (!enabled) {
      setLiveFix(null)
      return
    }
    if (position) {
      setLiveFix({
        lat: position.lat,
        lon: position.lng,
        speedKmh: position.speedKmh,
        headingDeg: position.headingDeg,
        at: position.at,
      })
    }
  }, [enabled, position])

  useEffect(() => {
    if (!enabled) {
      setSuggestion(null)
      setWhy(null)
      lastSentAt.current = 0
      lastSentAtPos.current = null
    }
  }, [enabled])

  useEffect(() => {
    if (!enabled || !position || inFlight.current) return
    const now = Date.now()
    const since = now - lastSentAt.current
    const moved = lastSentAtPos.current
      ? metres(lastSentAtPos.current, { lat: position.lat, lng: position.lng })
      : Infinity
    if (since < TICK_MS) return
    if (moved < MOVED_M && since < IDLE_TICK_MS) return

    inFlight.current = true
    lastSentAt.current = now
    lastSentAtPos.current = { lat: position.lat, lng: position.lng }
    void (async () => {
      try {
        const res = await copilot.tick({
          session,
          lat: position.lat,
          lon: position.lng,
          speed_kmh: position.speedKmh,
          heading_deg: position.headingDeg,
          rider_key: opt.current.riderKey ?? 'userA',
          thrill: opt.current.thrill ?? 0.5,
          mode: opt.current.mode ?? 'flow',
          bike_id: opt.current.bikeId ?? null,
          route: toCopilotRoute(getActiveRoute()),
        })
        setReachable(true)
        setTicks((n) => n + 1)
        setWhy(res.why ?? null)
        if (res.suggestion) setSuggestion(res.suggestion)
      } catch {
        setReachable(false)
      } finally {
        inFlight.current = false
      }
    })()
  }, [enabled, position, session])

  const dismiss = useCallback(() => {
    const current = suggestion
    setSuggestion(null)
    if (current) void copilot.dismiss(session, current.kind).catch(() => {})
  }, [session, suggestion])

  /**
   * Run the suggestion's own tool on the backend and return the new plan. The
   * caller decides what to do with it (draw it, navigate to it) — this hook
   * does not know about screens.
   */
  const accept = useCallback(async (): Promise<FsRouteResult | null> => {
    const current = suggestion
    if (!current?.action) {
      setSuggestion(null)
      return null
    }
    setBusy(true)
    try {
      const res = await copilot.runTool(current.action.tool, current.action.args)
      const plan = (res as { result?: FsRouteResult }).result
      setSuggestion(null)
      if (plan?.ok && Array.isArray(plan.path) && plan.path.length > 1) {
        setActiveRoute(plan)
        return plan
      }
      return null
    } catch {
      return null
    } finally {
      setBusy(false)
    }
  }, [suggestion])

  const state: CopilotState = !enabled
    ? 'off'
    : !reachable
      ? 'unreachable'
      : gpsState(liveState)

  return { state, suggestion, why, route, position, ticks, accept, dismiss, busy }
}
