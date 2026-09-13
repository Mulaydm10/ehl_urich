import type {
  AvoidanceId,
  Bike,
  CurvatureMode,
  GroupRide,
  MapRegion,
  Ride,
  RideSample,
  RiderProfile,
  Route,
  SeasonStats,
  TransferResult,
} from '../domain/types'
import * as mock from '../data/mock'
import { http, markLive } from './http'

export interface PlanRouteInput {
  origin: string
  destination: string
  via: string[]
  mode: CurvatureMode
  avoid: AvoidanceId[]
  roundTrip: boolean
  bikeId: string
}

/** Live vehicle status for one bike. Everything is null on a phone-only bike. */
export interface VehicleStatus {
  ok: boolean
  bikeId: string
  live: boolean
  note: string
  fuelPercent: number | null
  rangeKm: number | null
  odometerKm: number | null
  batteryVolt: number | null
  tyrePressureBar: { front: number; rear: number } | null
  serviceDueKm: number | null
  serviceDueDate: string | null
  recall: string | null
}

/**
 * Everything the UI needs from the BMW side of the backend. Two implementations:
 * `httpApi` talks to flowstate/app/api.py, `mockApi` is the offline fallback the
 * app drops to when that backend is unreachable.
 */
export interface BmwApi {
  getProfile(): Promise<RiderProfile>
  getBikes(): Promise<Bike[]>
  getRoutes(): Promise<Route[]>
  getRides(): Promise<Ride[]>
  getGroupRide(): Promise<GroupRide>
  getMapRegions(): Promise<MapRegion[]>
  getSeasonStats(): Promise<SeasonStats>
  getVehicleStatus(bikeId: string): Promise<VehicleStatus>
  planRoute(input: PlanRouteInput): Promise<Route>
  importRoute(fileName: string): Promise<Route>
  exportRoute(routeId: string, target: string): Promise<string>
  sendRouteToBike(routeId: string, bike: Bike): Promise<TransferResult>
  startMapDownload(regionId: string): Promise<MapRegion>
  startRide(bikeId: string, title: string): Promise<string>
  pushRideSample(rideId: string, sample: RideSample): Promise<void>
  stopRide(rideId: string): Promise<Ride | null>
}

const delay = <T,>(value: T, ms = 260): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms))

const CURVINESS_BY_MODE: Record<CurvatureMode, number> = {
  fastest: 38,
  fast_curvy: 62,
  curvy: 81,
  extra_curvy: 94,
}

const statusFromBike = (bike: Bike): VehicleStatus => ({
  ok: true,
  bikeId: bike.id,
  live: bike.connection === 'connected',
  note:
    bike.connection === 'phone_only'
      ? 'This bike has no connectivity module; the phone shows ride data only.'
      : '',
  fuelPercent: bike.fuelPercent,
  rangeKm: bike.rangeKm,
  odometerKm: bike.odometerKm,
  batteryVolt: bike.batteryVolt,
  tyrePressureBar: bike.tyrePressureBar,
  serviceDueKm: bike.serviceDueKm,
  serviceDueDate: bike.serviceDueDate,
  recall: bike.recall,
})

export const mockApi: BmwApi = {
  getProfile: () => delay(mock.profile),
  getBikes: () => delay(mock.bikes),
  getRoutes: () => delay(mock.routes),
  getRides: () => delay(mock.rides),
  getGroupRide: () => delay(mock.groupRide),
  getMapRegions: () => delay(mock.mapRegions),
  getSeasonStats: () => delay(mock.seasonStats),

  getVehicleStatus: (bikeId) => {
    const bike = mock.bikes.find((b) => b.id === bikeId)
    if (!bike) throw new Error(`Unknown bike ${bikeId}`)
    return delay(statusFromBike(bike))
  },

  planRoute: (input) => {
    const base = mock.routes[0]
    const factor = { fastest: 0.82, fast_curvy: 0.95, curvy: 1, extra_curvy: 1.18 }[input.mode]
    return delay(
      {
        ...base,
        id: `r-${Date.now()}`,
        name: input.roundTrip
          ? `${input.origin} round trip`
          : `${input.origin} – ${input.destination}`,
        origin: input.origin,
        destination: input.roundTrip ? input.origin : input.destination,
        via: input.via,
        mode: input.mode,
        avoid: input.avoid,
        roundTrip: input.roundTrip,
        distanceKm: Math.round(base.distanceKm * factor),
        durationMin: Math.round(base.durationMin * factor),
        curvinessScore: CURVINESS_BY_MODE[input.mode],
        source: 'planned',
        savedAt: 'just now',
      },
      420,
    )
  },

  importRoute: (fileName) =>
    delay({ ...mock.routes[4], id: `r-${Date.now()}`, author: fileName, savedAt: 'Imported just now' }, 500),

  exportRoute: (routeId, target) => delay(`${routeId}-${target}.gpx`, 400),

  sendRouteToBike: (_routeId, bike) =>
    delay(
      bike.hasConnectedRideNavigator
        ? {
            ok: true,
            target: 'ConnectedRide Navigator' as const,
            message: `Route on ${bike.model}. Scroll it with the handlebar wheel.`,
          }
        : {
            ok: false,
            target: 'phone' as const,
            message: `${bike.model} has no ConnectedRide Navigator — navigating on the phone instead.`,
          },
      900,
    ),

  startMapDownload: (regionId) => {
    const region = mock.mapRegions.find((r) => r.id === regionId)
    if (!region) throw new Error(`Unknown region ${regionId}`)
    return delay({ ...region, status: 'downloading' as const, progress: Math.max(region.progress, 5) }, 300)
  },

  startRide: (bikeId) => delay(`live-offline-${bikeId}-${Date.now()}`, 120),
  pushRideSample: () => delay(undefined, 20),
  stopRide: () => delay(null, 120),
}

/** Backend-backed implementation. Used whenever /health answers. */
export const httpApi: BmwApi = {
  getProfile: () => http.get<RiderProfile>('/api/bmw/profile'),
  getBikes: () => http.get<Bike[]>('/api/bmw/bikes'),
  getRoutes: () => http.get<Route[]>('/api/bmw/routes'),
  getRides: () => http.get<Ride[]>('/api/bmw/rides'),
  getGroupRide: () => http.get<GroupRide>('/api/bmw/group'),
  getMapRegions: () => http.get<MapRegion[]>('/api/bmw/maps'),
  getSeasonStats: () => http.get<SeasonStats>('/api/bmw/stats'),
  getVehicleStatus: (bikeId) => http.get<VehicleStatus>(`/api/bmw/bikes/${bikeId}/status`),

  planRoute: (input) => http.post<Route>('/api/bmw/plan', input),
  importRoute: (fileName) => http.post<Route>('/api/bmw/import', { fileName }),

  exportRoute: async (routeId, target) => {
    const res = await http.post<{ ok: boolean; file: string }>('/api/bmw/export', { routeId, target })
    return res.file
  },

  sendRouteToBike: (routeId, bike) =>
    http.post<TransferResult>('/api/bmw/handoff', { routeId, bikeId: bike.id }),

  startMapDownload: async (regionId) => {
    const res = await http.post<{ ok: boolean; region: MapRegion; note?: string }>(
      `/api/bmw/maps/${regionId}/download`,
      {},
    )
    if (!res.ok) throw new Error(res.note ?? `Unknown region ${regionId}`)
    return res.region
  },

  startRide: async (bikeId, title) => {
    const res = await http.post<{ ok: boolean; rideId: string }>('/api/bmw/rides/start', { bikeId, title })
    return res.rideId
  },

  pushRideSample: async (rideId, sample) => {
    await http.post('/api/bmw/rides/sample', { rideId, sample })
  },

  stopRide: async (rideId) => {
    const res = await http.post<{ ok: boolean; ride?: Ride }>(`/api/bmw/rides/${rideId}/stop`, {})
    return res.ride ?? null
  },
}

/**
 * Probe the backend once at startup and pick the implementation. The app is
 * fully usable either way — offline it runs on the bundled mock and says so.
 */
export async function resolveApi(): Promise<{ api: BmwApi; online: boolean; engine: string }> {
  try {
    const health = await http.get<{ ok: boolean; engine: string }>('/health')
    markLive(true)
    return { api: httpApi, online: true, engine: health.engine }
  } catch {
    markLive(false)
    return { api: mockApi, online: false, engine: 'offline' }
  }
}
