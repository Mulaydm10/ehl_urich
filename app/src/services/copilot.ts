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
