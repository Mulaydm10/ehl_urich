export type CurvatureMode = 'fastest' | 'fast_curvy' | 'curvy' | 'extra_curvy'

export type AvoidanceId =
  | 'closures'
  | 'tolls'
  | 'ferries'
  | 'motorways'
  | 'main_roads'
  | 'narrow_roads'
  | 'unpaved'

export type PoiLayerId =
  | 'fuel'
  | 'passes'
  | 'twisty'
  | 'dealers'
  | 'hotels'
  | 'food'
  | 'events'
  | 'parking'

export type BikeConnection = 'connected' | 'last_seen' | 'phone_only'

export interface LatLng {
  lat: number
  lng: number
}

/** A BMW motorcycle in the rider's BMW ID garage. */
export interface Bike {
  id: string
  model: string
  variant: string
  vin: string
  imageTint: string
  connection: BikeConnection
  lastSeen: string
  /** null when the bike has no live connectivity (phone-only mode). */
  fuelPercent: number | null
  rangeKm: number | null
  odometerKm: number | null
  tankLitres: number
  consumptionLper100: number
  serviceDueKm: number | null
  serviceDueDate: string | null
  recall: string | null
  tyrePressureBar: { front: number; rear: number } | null
  batteryVolt: number | null
  hasConnectedRideNavigator: boolean
}

export interface Poi {
  id: string
  name: string
  layer: PoiLayerId
  atKm: number
  note?: string
}

export interface RouteSegment {
  fromKm: number
  toKm: number
  mode: CurvatureMode
  road: string
}

export interface ElevationPoint {
  km: number
  elevationM: number
  speedLimit: number
}

export interface Route {
  id: string
  name: string
  region: string
  origin: string
  destination: string
  via: string[]
  distanceKm: number
  durationMin: number
  ascentM: number
  curvinessScore: number
  mode: CurvatureMode
  avoid: AvoidanceId[]
  roundTrip: boolean
  segments: RouteSegment[]
  elevation: ElevationPoint[]
  path: LatLng[]
  pois: Poi[]
  source: 'planned' | 'imported' | 'curated' | 'community'
  author?: string
  savedAt: string
}

export interface RideSample {
  km: number
  speedKmh: number
  leanLeftDeg: number
  leanRightDeg: number
  altitudeM: number
  rpm: number
}

export interface RidePhoto {
  id: string
  atKm: number
  caption: string
  tint: string
}

export interface Ride {
  id: string
  title: string
  date: string
  bikeId: string
  distanceKm: number
  durationMin: number
  avgSpeedKmh: number
  topSpeedKmh: number
  maxLeanLeftDeg: number
  maxLeanRightDeg: number
  ascentM: number
  curvinessScore: number
  path: LatLng[]
  samples: RideSample[]
  photos: RidePhoto[]
}

export interface GroupRider {
  id: string
  name: string
  bike: string
  status: 'riding' | 'stopped' | 'lost_signal' | 'arrived'
  distanceBehindKm: number
  batteryPercent: number
  position: LatLng
}

export interface GroupRide {
  id: string
  name: string
  routeId: string
  startsAt: string
  regroupPoint: string
  regroupAtKm: number
  riders: GroupRider[]
}

export interface MapRegion {
  id: string
  name: string
  sizeMb: number
  status: 'installed' | 'downloading' | 'failed' | 'available'
  progress: number
  updatedAt: string | null
  error?: string
}

export interface SeasonStats {
  year: number
  rides: number
  distanceKm: number
  ridingTimeMin: number
  passesRidden: number
  topCurviness: number
  countries: string[]
}

export interface RiderProfile {
  bmwId: string
  displayName: string
  memberSince: string
  homeDealer: string
}

export interface TransferResult {
  ok: boolean
  target: 'ConnectedRide Navigator' | 'TFT' | 'phone'
  message: string
}

// --------------------------------------------------------------------------
// FLOWSTATE fun-fit route engine (backend service.py / docs 25, 26).
// Coordinates arrive from the engine as [lon, lat]; LatLng is used in the UI.
// --------------------------------------------------------------------------

/** A dial preset: how far past habit the rider wants to be pushed. */
export type ThrillPreset = 'Cruise' | 'Flow' | 'Send it'

export interface FsRider {
  key: string
  label: string
  skill: number
  sigma: number
  gate: number
  hardest_ridden: number
  gate_agreement: number
  n_cells: number
  n_corners: number
  grip_p95: number
}

export interface FsPresetRoute {
  key: string
  label: string
  a: [number, number]
  b: [number, number]
  why: string
}

export interface FsPresetLoop {
  key: string
  label: string
  start: [number, number]
}

export interface FsPresets {
  routes: FsPresetRoute[]
  loops: FsPresetLoop[]
  dial: Record<ThrillPreset, number>
}

export interface FsMode {
  key: string
  verdict: string
  phase4: boolean
  offered: boolean
}

export interface FsRouteSummary {
  km: number
  minutes: number
  n_cells: number
  mean_demand: number
  max_demand: number
  mean_flow: number
  peak_flow: number
  fun_score: number
  grip_lat_p95: number | null
  grip_lat_max: number | null
  gate_deg: number
  n_refused_nearby: number
  imputed_cells: number
  is_loop?: boolean
  budget_min?: number
  budget_fill?: number
  distinct_share?: number
}

export interface FsRefusal {
  cell: string
  lat: number
  lon: number
  demand: number
  reason: string
}

export interface FsSegment {
  from: [number, number]
  to: [number, number]
  flow: number
  demand: number
}

/** A single planned route. `path`/segments carry [lon, lat] from the engine. */
export interface FsRouteResult {
  ok: boolean
  note: string
  cells: string[]
  path: [number, number][]
  segments: FsSegment[]
  refusals: FsRefusal[]
  summary: FsRouteSummary | []
  rider: string
  z_star: number
  explain: string[]
}

export interface FsCompareResult {
  low: FsRouteResult
  high: FsRouteResult
  lo_z: number
  hi_z: number
  overlap?: number
  km_ratio?: number
  demand_gain?: number
  headline?: string
}

export interface FsRiderJoy {
  ok: boolean
  rider: string
  verdict: string
  n_rides: number
  median_joy: number
  explain: string[]
}
