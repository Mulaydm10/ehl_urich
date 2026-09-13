/**
 * Client for the live ride co-pilot (flowstate/app/copilot.py).
 *
 * The phone sends where it is; the backend decides — from FLOWSTATE's own
 * numbers, not from a model — whether anything is worth saying. At most one
 * suggestion comes back per tick, already phrased for speech.
 *
 * There is no offline stand-in. With no backend the co-pilot reports that it
 * is not watching, rather than inventing a reroute while the rider is moving.
 */
import type { FsRouteResult } from '../domain/types'
import { http } from './http'

export interface CopilotSuggestion {
  id: string
  /** off_route | gate_ahead | dull_ahead | scenic_detour | fuel | stopped */
  kind: string
  title: string
  detail: string
  say: string
  action: { tool: string; args: Record<string, unknown> } | null
  evidence: Record<string, unknown>
  /** False when the sentence is the rules engine's own wording (no model). */
  narrated: boolean
}

export interface CopilotTickResult {
  ok: boolean
  suggestion: CopilotSuggestion | null
  /** Why nothing was said — shown in the co-pilot's own status line. */
  why?: string
  considered?: string[]
  engine?: string
}

export interface CopilotTickBody {
  session: string
  lat: number
  lon: number
  speed_kmh?: number | null
  heading_deg?: number | null
  rider_key?: string
  thrill?: number
  mode?: string
  bike_id?: string | null
  route?: CopilotRoute | null
}

/** The plan the rider is following, in the shape the backend triggers read. */
export interface CopilotRoute {
  path: [number, number][]
  segments: FsRouteResult['segments']
  refusals: FsRouteResult['refusals']
  destination: [number, number] | null
  remaining_km: number | null
}

export const copilot = {
  tick: (body: CopilotTickBody) => http.post<CopilotTickResult>('/api/copilot/tick', body, 20000),
  dismiss: (session: string, kind: string) =>
    http.post<unknown>('/api/copilot/dismiss', { session, kind }),
  reset: (session: string) => http.post<unknown>('/api/copilot/reset', { session, kind: 'all' }),
  runTool: (name: string, args: Record<string, unknown>) =>
    http.post<{ ok?: boolean; result?: unknown }>('/api/assistant/tool', { name, args }, 45000),
}

/**
 * The route the rider is currently on.
 *
 * Held outside React, like the assistant's pending plan: the producer (Thrill,
 * or the assistant planning by voice) and the consumer (the co-pilot on the
 * Ride screen) never render together. Subscribers exist so the Ride screen can
 * show "following a plan" the moment one is set.
 */
let active: FsRouteResult | null = null
const listeners = new Set<(r: FsRouteResult | null) => void>()

export function setActiveRoute(route: FsRouteResult | null): void {
  active = route && route.ok ? route : null
  listeners.forEach((fn) => fn(active))
}

export const getActiveRoute = (): FsRouteResult | null => active

export function subscribeActiveRoute(fn: (r: FsRouteResult | null) => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/**
 * The last GPS fix, published by whichever screen is watching.
 *
 * Mid-ride tools need to know where the bike is, and the rider may be talking
 * to the assistant from any screen. Keeping the fix here — next to the active
 * route — means the assistant never has to open a second GPS watch, and never
 * has to ask the model where the rider is.
 */
export interface LiveFix {
  lat: number
  lon: number
  speedKmh: number | null
  headingDeg: number | null
  at: number
}

/**
 * A fix older than this is not where the bike is, it is where it was. Location
 * switched off mid-ride leaves the last fix behind, and a tool answered from it
 * is a confident lie: "a stop 20 km ahead" measured from a road the rider may
 * have left. Past this age the fix is treated as absent.
 */
export const FIX_MAX_AGE_MS = 60_000

let fix: LiveFix | null = null

export const setLiveFix = (next: LiveFix | null): void => {
  fix = next
}

export const getLiveFix = (): LiveFix | null => fix

/** The fix only if it is recent enough to answer a mid-ride question with. */
export const getFreshFix = (now: number = Date.now()): LiveFix | null =>
  fix && now - fix.at <= FIX_MAX_AGE_MS ? fix : null

/** How many cells of the current plan are worth sending as "the road ahead". */
const CELLS_SENT = 400
/** Points of the plan's line to send; enough shape to measure along, small
 *  enough to post every time the rider speaks. */
const LINE_POINTS = 120

/** Thin a path to at most `LINE_POINTS`, always keeping both ends. */
function thin(path: [number, number][]): [number, number][] {
  if (path.length <= LINE_POINTS) return path.map((p) => [p[1], p[0]])
  const step = (path.length - 1) / (LINE_POINTS - 1)
  const out: [number, number][] = []
  for (let i = 0; i < LINE_POINTS; i += 1) {
    const p = path[Math.round(i * step)]
    out.push([p[1], p[0]])
  }
  return out
}

export interface RideContext {
  lat: number
  lon: number
  speed_kmh: number | null
  heading_deg: number | null
  rider_key: string
  thrill: number
  mode: string
  navigating: boolean
  route: {
    destination: [number, number] | null
    cells: string[]
    /** The planned line as [lat, lon], thinned. */
    line: [number, number][]
    km: number | null
    minutes: number | null
  } | null
}

/**
 * What the rider asked the next plan to be: the dial and the mode chosen on
 * Thrill, or built from his ride profile.
 *
 * Kept here because a re-plan can start anywhere — a complaint chip, a typed
 * sentence, the voice model — and all of them must ask for the same thing the
 * screen says they are asking for. Without it a reroute silently fell back to
 * `flow` while Navigate claimed the rider's own weights.
 */
let wanted: { riderKey?: string; thrill?: number; mode?: string } = {}

export const setRideWants = (next: { riderKey?: string; thrill?: number; mode?: string }): void => {
  wanted = next
}

export const getRideWants = () => wanted

/**
 * Everything a mid-ride tool needs: where the bike is, and the plan it is on.
 * Null with no fix — the backend then says it cannot re-plan from here, which
 * is the truth, rather than re-planning from somewhere invented.
 */
export function rideContext(
  opts: { riderKey?: string; thrill?: number; mode?: string } = {},
): RideContext | null {
  const live = getFreshFix()
  if (!live) return null
  const r = getActiveRoute()
  const summary = r && !Array.isArray(r.summary) ? r.summary : null
  const last = r?.path[r.path.length - 1]
  return {
    lat: live.lat,
    lon: live.lon,
    speed_kmh: live.speedKmh,
    heading_deg: live.headingDeg,
    rider_key: opts.riderKey ?? wanted.riderKey ?? 'userA',
    thrill: opts.thrill ?? wanted.thrill ?? r?.z_star ?? 0.5,
    mode: opts.mode ?? wanted.mode ?? 'flow',
    navigating: !!r,
    route: r && last
      ? {
          destination: [last[1], last[0]],
          cells: r.cells.slice(0, CELLS_SENT),
          line: thin(r.path),
          km: summary?.km ?? null,
          minutes: summary?.minutes ?? null,
        }
      : null,
  }
}

/** Trim a planned route to what the triggers need, so ticks stay small. */
export function toCopilotRoute(r: FsRouteResult | null): CopilotRoute | null {
  if (!r || !r.ok || r.path.length < 2) return null
  const last = r.path[r.path.length - 1]
  const summary = Array.isArray(r.summary) ? null : r.summary
  return {
    path: r.path,
    segments: r.segments,
    refusals: r.refusals,
    destination: [last[1], last[0]],
    remaining_km: summary?.km ?? null,
  }
}
