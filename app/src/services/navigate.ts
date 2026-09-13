/**
 * Navigate mode: following a plan, and changing it without stopping.
 *
 * Two things live here. The first is progress — how far is left and how long
 * that takes — measured against the plan the rider is on, using the plan's own
 * distance and time rather than a guess about traffic. The second is the
 * re-plan itself: `reroute_from_here` on the backend, which the rider can
 * reach three ways (spoken to the live voice model, typed at the assistant, or
 * by tapping a complaint on screen) and which always gets the live position
 * from the app, never from a model.
 */
import type { FsRouteResult, FsRouteSummary } from '../domain/types'
import { http } from './http'
import { rideContext, type RideContext } from './copilot'

export type RerouteChange = 'more_fun' | 'calmer' | 'scenic' | 'mountain' | 'avoid_this_road' | 'same'

export interface Reroute {
  change: RerouteChange
  reason: string | null
  destination: [number, number] | null
  kept_destination: boolean
  thrill_from: number
  thrill_to: number
  mode_from: string
  mode_to: string
  /** 0..1 of the new line that is road the rider was already going to ride. */
  shares_current_road: number | null
}

export interface RerouteResult {
  plan: FsRouteResult
  reroute: Reroute
}

interface ToolRun {
  ok?: boolean
  result?: (FsRouteResult & { reroute?: Reroute }) | { error?: string; needs?: string }
}

/** The complaints a rider actually makes, and what each one asks the engine for. */
const COMPLAINTS: { change: RerouteChange; words: string[] }[] = [
  { change: 'avoid_this_road', words: ['off this road', 'get me off', 'not this road', "don't want this road", 'do not want this road', 'anything else', 'different road', 'another road', 'avoid this'] },
  { change: 'more_fun', words: ['boring', 'dull', 'bored', 'more fun', 'spicier', 'send it', 'twistier', 'more corners', 'faster road'] },
  { change: 'calmer', words: ['too much', 'too fast', 'calm', 'easier', 'slow it down', 'scary', 'tiring', 'gentler'] },
  { change: 'scenic', words: ['scenic', 'nicer', 'prettier', 'views', 'lake', 'beautiful'] },
  { change: 'mountain', words: ['mountain', 'pass', 'climb', 'altitude', 'switchback'] },
]

/**
 * Read a spoken complaint without a model, so hands-free still works when the
 * cloud assistant is off. Null when the sentence is not about the road.
 */
export function matchComplaint(raw: string): RerouteChange | null {
  const text = raw.toLowerCase()
  for (const { change, words } of COMPLAINTS) {
    if (words.some((w) => text.includes(w))) return change
  }
  return null
}

export async function reroute(
  change: RerouteChange,
  reason: string | null,
  ctx: RideContext | null = rideContext(),
): Promise<RerouteResult | { error: string }> {
  if (!ctx) return { error: 'No GPS fix yet, so I cannot re-plan from here.' }
  let run: ToolRun
  try {
    run = await http.post<ToolRun>(
      '/api/assistant/tool',
      { name: 'reroute_from_here', args: { change, reason }, context: { ride: ctx } },
      45000,
    )
  } catch {
    return { error: 'The route engine is unreachable, so nothing was re-planned.' }
  }
  const result = run.result
  if (!result || !('ok' in result)) {
    return { error: result?.error ?? 'The engine could not re-plan from here.' }
  }
  if (!result.ok || !result.reroute) {
    return { error: result.note || 'The engine could not re-plan from here.' }
  }
  return { plan: result, reroute: result.reroute }
}

const CHANGE_SAID: Record<RerouteChange, string> = {
  more_fun: 'More corners from here',
  calmer: 'Calmer from here',
  scenic: 'The scenic way from here',
  mountain: 'Over the mountain from here',
  avoid_this_road: 'Off this road',
  same: 'Re-planned from here',
}

/**
 * What to say about a re-plan, built from the engine's numbers only.
 *
 * The overlap sentence is the honest part: the engine cannot be told to forbid
 * a road, so when the alternative still uses most of the same tarmac the rider
 * is told that instead of being sold a new route.
 */
export function describeReroute(r: RerouteResult): string {
  const s = summaryOf(r.plan)
  const bits: string[] = [CHANGE_SAID[r.reroute.change]]
  if (s) bits.push(`${Math.round(s.km)} km, ${Math.round(s.minutes)} minutes, fun ${s.fun_score.toFixed(2)}`)
  if (r.reroute.thrill_to !== r.reroute.thrill_from) bits.push(`thrill ${r.reroute.thrill_to.toFixed(2)}`)
  if (r.reroute.mode_to !== r.reroute.mode_from) bits.push(`${r.reroute.mode_to} mode`)
  const share = r.reroute.shares_current_road
  if (share != null) {
    bits.push(share >= 0.9
      ? 'but it is nearly all the same road — the engine found nothing better from here'
      : share <= 0.1
        ? 'on different roads'
        : `${Math.round(share * 100)}% of it is the same road`)
  }
  const refused = r.plan.refusals.length
  if (refused) bits.push(`${refused} road${refused === 1 ? '' : 's'} refused by your safety gate`)
  return `${bits.join(' · ')}.`
}

export const summaryOf = (r: FsRouteResult | null): FsRouteSummary | null =>
  r && !Array.isArray(r.summary) ? r.summary : null

const EARTH_M = 6371008.8

function metres(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const p1 = (aLat * Math.PI) / 180
  const p2 = (bLat * Math.PI) / 180
  const dp = p2 - p1
  const dl = ((bLon - aLon) * Math.PI) / 180
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * EARTH_M * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))))
}

export interface Progress {
  /** Metres from the rider to the nearest point of the plan. */
  offRouteM: number
  remainingKm: number
  /** From the plan's own riding time, scaled by how much of it is left. */
  remainingMin: number | null
  doneShare: number
  destination: [number, number]
}

/**
 * Where the rider is along the plan. Path points are [lon, lat] from the
 * engine. Nothing is smoothed or predicted: the number shown is the distance
 * still to ride along the planned line, so it can only be wrong if the plan is.
 */
export function progressAlong(
  plan: FsRouteResult | null,
  at: { lat: number; lon: number } | null,
): Progress | null {
  if (!plan?.ok || plan.path.length < 2 || !at) return null
  const path = plan.path
  let nearest = 0
  let best = Infinity
  for (let i = 0; i < path.length; i += 1) {
    const d = metres(at.lat, at.lon, path[i][1], path[i][0])
    if (d < best) {
      best = d
      nearest = i
    }
  }
  let remaining = 0
  for (let i = nearest; i < path.length - 1; i += 1) {
    remaining += metres(path[i][1], path[i][0], path[i + 1][1], path[i + 1][0])
  }
  let total = remaining
  for (let i = 0; i < nearest; i += 1) {
    total += metres(path[i][1], path[i][0], path[i + 1][1], path[i + 1][0])
  }
  const s = summaryOf(plan)
  const share = total > 0 ? remaining / total : 0
  const last = path[path.length - 1]
  return {
    offRouteM: best,
    remainingKm: remaining / 1000,
    remainingMin: s ? s.minutes * share : null,
    doneShare: 1 - share,
    destination: [last[1], last[0]],
  }
}
