import type {
  FsCompareResult,
  FsMode,
  FsPresets,
  FsRider,
  FsRiderJoy,
  FsRouteResult,
  LatLng,
} from '../domain/types'
import { http } from './http'

/**
 * Client for the FLOWSTATE fun-fit route engine.
 *
 * The engine scores a road by how well its lean-angle demand fits the rider's
 * own measured skill, and deletes anything past skill + 2 sigma rather than
 * making it expensive. There is no offline stand-in here on purpose: when the
 * backend is unreachable the planner says so instead of inventing a route.
 */

/** Coverage box the engine was built for (docs 25 §1): Bavaria / Alpine foothills. */
export const COVERAGE = { latMin: 47.38, latMax: 48.03, lonMin: 10.72, lonMax: 11.96 }

export const inCoverage = (p: LatLng) =>
  p.lat >= COVERAGE.latMin && p.lat <= COVERAGE.latMax &&
  p.lng >= COVERAGE.lonMin && p.lng <= COVERAGE.lonMax

/** The engine returns [lon, lat]; the map draws {lat, lng}. */
export const toLatLng = (pair: [number, number]): LatLng => ({ lat: pair[1], lng: pair[0] })

export const pathToLatLng = (path: [number, number][]): LatLng[] => path.map(toLatLng)

export interface FsStatus {
  source: string
  cells: number
  edges: number
  riders: number
  engine: string
  mock?: boolean
}

export const flowstate = {
  status: () => http.get<FsStatus>('/api/status'),
  riders: () => http.get<FsRider[]>('/api/riders'),
  presets: () => http.get<FsPresets>('/api/presets'),
  modes: () => http.get<FsMode[]>('/api/modes'),

  route: (a: [number, number], b: [number, number], riderKey: string, zStar: number, mode: string) =>
    http.post<FsRouteResult>('/api/route', { a, b, rider_key: riderKey, z_star: zStar, mode }),

  /**
   * A -> stops -> B, in the order the rider put them in. One engine plan per
   * leg, stitched by the backend; the summary adds the legs up rather than
   * pretending the whole line was scored at once.
   */
  routeVia: (points: [number, number][], riderKey: string, zStar: number, mode: string) =>
    http.post<FsRouteResult>('/api/route/via', {
      points,
      rider_key: riderKey,
      z_star: zStar,
      mode,
    }, 45000),

  loop: (start: [number, number], hours: number, riderKey: string, zStar: number, mode: string) =>
    http.post<FsRouteResult>('/api/loop', { start, hours, rider_key: riderKey, z_star: zStar, mode }),

  compare: (a: [number, number], b: [number, number], riderKey: string, mode: string) =>
    http.post<FsCompareResult>('/api/compare', { a, b, rider_key: riderKey, lo: 0.15, hi: 0.9, mode }),

  riderJoy: (riderKey: string) => http.get<FsRiderJoy>(`/api/rider_joy?rider_key=${riderKey}`),
}
