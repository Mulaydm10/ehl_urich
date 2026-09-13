// Geometry along a [lon, lat] polyline. Used only to place the simulated
// rider on the engine's own path and to scale the engine's km/minutes by the
// fraction of the line still ahead; no route figures are produced here.
import type { LonLat } from './api'

const R = 6371.0088

export function haversineKm(a: LonLat, b: LonLat): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b[1] - a[1])
  const dLon = toRad(b[0] - a[0])
  const la1 = toRad(a[1])
  const la2 = toRad(b[1])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)))
}

/** Cumulative km at each vertex; cum[0] = 0. */
export function cumulativeKm(path: LonLat[]): number[] {
  const out = [0]
  for (let i = 1; i < path.length; i++) out.push(out[i - 1] + haversineKm(path[i - 1], path[i]))
  return out
}

/** Point at fraction t in [0,1] of the line's length, plus the vertex index passed. */
export function pointAt(path: LonLat[], cum: number[], t: number): { point: LonLat; index: number } {
  if (path.length === 0) return { point: [0, 0], index: 0 }
  if (path.length === 1) return { point: path[0], index: 0 }
  const total = cum[cum.length - 1]
  const d = Math.max(0, Math.min(1, t)) * total
  let i = 1
  while (i < cum.length - 1 && cum[i] < d) i++
  const seg = cum[i] - cum[i - 1]
  const f = seg > 0 ? (d - cum[i - 1]) / seg : 0
  const a = path[i - 1]
  const b = path[i]
  return { point: [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f], index: i - 1 }
}

export function toLatLng(p: LonLat): [number, number] {
  return [p[1], p[0]]
}

/** Index of the path vertex closest to `p` (planar approximation, fine at route scale). */
export function nearestIndex(path: LonLat[], p: LonLat): number {
  let best = 0
  let bestD = Infinity
  const k = Math.cos((p[1] * Math.PI) / 180)
  for (let i = 0; i < path.length; i++) {
    const dx = (path[i][0] - p[0]) * k
    const dy = path[i][1] - p[1]
    const d = dx * dx + dy * dy
    if (d < bestD) { bestD = d; best = i }
  }
  return best
}
