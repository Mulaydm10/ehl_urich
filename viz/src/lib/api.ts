// HTTP client for flowstate/app/api.py. Every number shown in the dashboard
// comes back from one of these calls; nothing here computes or guesses route
// values. Coverage box mirrors assistant.COVERAGE / router bounds.

export const COVERAGE = { lat: [47.38, 48.03] as const, lon: [10.72, 11.96] as const }

export function inCoverage(lat: number, lon: number): boolean {
  return lat >= COVERAGE.lat[0] && lat <= COVERAGE.lat[1] &&
    lon >= COVERAGE.lon[0] && lon <= COVERAGE.lon[1]
}

export type LonLat = [number, number]

export interface Refusal {
  cell: string
  lat: number
  lon: number
  demand: number
  reason: string
}

export interface Segment {
  from: LonLat
  to: LonLat
  flow: number
  demand: number
}

export interface Summary {
  km?: number
  minutes?: number
  n_cells?: number
  mean_demand?: number
  max_demand?: number
  mean_flow?: number
  peak_flow?: number
  final_flow?: number
  fun_score?: number
  gate_deg?: number | null
  n_refused_nearby?: number
  grip_lat_p95?: number | null
  grip_lat_max?: number | null
  is_loop?: boolean
  budget_min?: number
  [k: string]: unknown
}

export interface Plan {
  ok: boolean
  note?: string | null
  cells?: string[]
  path: LonLat[]
  segments: Segment[]
  refusals: Refusal[]
  summary: Summary | []
  rider?: string
  z_star?: number
  explain?: string[]
}

export type Verdict = 'accepted' | 'rejected' | 'not_searched' | 'failed'

export interface Candidate {
  index: number
  thrill: number
  mode: string
  ok: boolean
  in_search: boolean
  verdict: Verdict
  why: string
  shares_current_road: number | null
  km: number | null
  minutes: number | null
  fun_score: number | null
  mean_demand: number | null
  max_demand: number | null
  path: LonLat[]
  cells: string[]
  segments: Segment[]
  refusals: Refusal[]
  summary: Summary
  explain: string[]
  note: string | null
}

export interface RerouteMeta {
  change: string
  from: [number, number]
  destination: [number, number] | null
  kept_destination: boolean
  thrill_from: number
  thrill_to: number
  mode_from: string
  mode_to: string
  shares_current_road: number | null
  variants_tried: { thrill: number; mode: string; ok: boolean; km?: number; note?: string }[]
}

export interface RerouteResult extends Plan {
  candidates: Candidate[]
  reroute: RerouteMeta
}

export interface Rider {
  key: string
  skill: number
  sigma: number
  gate: number
  hardest_ridden?: number
  gate_agreement?: number
  n_cells?: number
  n_corners?: number
  grip_p95?: number
  [k: string]: unknown
}

export interface Mode {
  key: string
  verdict: string
  phase4: boolean
  offered: boolean
}

export interface Presets {
  routes: { key: string; label: string; a: [number, number]; b: [number, number]; why?: string }[]
  loops: { key: string; label: string; start: [number, number] }[]
  dial: Record<string, number>
}

export interface Health {
  ok: boolean
  engine: string
}

export interface Status {
  engine: string
  source?: string
  mock?: boolean
  cells?: number
  edges?: number
  [k: string]: unknown
}

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, message: string, body: unknown) {
    super(message)
    this.status = status
    this.body = body
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch (e) {
    throw new ApiError(0, `Backend unreachable at ${BASE || window.location.origin}: ${String(e)}`, null)
  }
  const text = await res.text()
  let body: unknown = null
  try { body = text ? JSON.parse(text) : null } catch { body = text }
  if (!res.ok) {
    const b = body as { note?: string; error?: string } | null
    throw new ApiError(res.status, b?.note || b?.error || `HTTP ${res.status}`, body)
  }
  return body as T
}

export const api = {
  health: () => call<Health>('/health'),
  status: () => call<Status>('/api/status'),
  riders: () => call<Rider[]>('/api/riders'),
  modes: () => call<Mode[]>('/api/modes'),
  presets: () => call<Presets>('/api/presets'),
  route: (a: [number, number], b: [number, number], rider_key: string, z_star: number, mode: string) =>
    call<Plan>('/api/route', { method: 'POST', body: JSON.stringify({ a, b, rider_key, z_star, mode }) }),
  loop: (start: [number, number], hours: number, rider_key: string, z_star: number, mode: string) =>
    call<Plan>('/api/loop', { method: 'POST', body: JSON.stringify({ start, hours, rider_key, z_star, mode }) }),
  rerouteCandidates: (body: {
    lat: number; lon: number; rider_key: string; thrill: number; mode: string; change: string
    destination: [number, number] | null; current_cells: string[]; hours?: number
  }) => call<RerouteResult>('/api/viz/reroute_candidates', { method: 'POST', body: JSON.stringify(body) }),
}

export function summaryOf(p: Plan | null | undefined): Summary {
  return p && p.summary && !Array.isArray(p.summary) ? p.summary : {}
}
