import type {
  Bike,
  ElevationPoint,
  GroupRide,
  LatLng,
  MapRegion,
  Poi,
  Ride,
  RideSample,
  RiderProfile,
  Route,
  SeasonStats,
} from '../domain/types'

/** Deterministic pseudo-random so mock screens never flicker between renders. */
const rand = (seed: number) => {
  let s = seed
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648
    return s / 2147483648
  }
}

const makePath = (seed: number, from: LatLng, to: LatLng, wiggle: number, points = 220): LatLng[] => {
  const r = rand(seed)
  const dLat = to.lat - from.lat
  const dLng = to.lng - from.lng
  const len = Math.hypot(dLat, dLng) || 1
  // Unit vector perpendicular to the straight line, so detours read as bends in a road.
  const px = -dLat / len
  const py = dLng / len
  const phase = r() * Math.PI * 2
  const drift = (r() - 0.5) * wiggle * 4

  return Array.from({ length: points }, (_, i) => {
    const t = i / (points - 1)
    const envelope = Math.sin(t * Math.PI) // detours fade out at both ends
    const bend =
      Math.sin(t * Math.PI * 1.3 + phase) * wiggle * 6 +
      Math.sin(t * Math.PI * 5.7 + phase * 2) * wiggle * 2.2 +
      Math.sin(t * Math.PI * 13.1 + phase * 3) * wiggle * 0.8
    const offset = (bend + drift) * envelope
    return {
      lat: from.lat + dLat * t + py * offset * 0.7,
      lng: from.lng + dLng * t + px * offset,
    }
  })
}

const makeElevation = (seed: number, distanceKm: number, peak: number): ElevationPoint[] => {
  const r = rand(seed)
  const steps = 60
  return Array.from({ length: steps }, (_, i) => {
    const t = i / (steps - 1)
    const base = 480 + Math.sin(t * Math.PI) * peak + Math.sin(t * Math.PI * 5) * peak * 0.16
    return {
      km: Number((t * distanceKm).toFixed(1)),
      elevationM: Math.round(base + (r() - 0.5) * 40),
      speedLimit: [50, 70, 80, 100][Math.floor(r() * 4)],
    }
  })
}

const makeSamples = (seed: number, distanceKm: number, sporty: number): RideSample[] => {
  const r = rand(seed)
  const steps = 120
  return Array.from({ length: steps }, (_, i) => {
    const t = i / (steps - 1)
    const twist = Math.sin(t * Math.PI * 9)
    return {
      km: Number((t * distanceKm).toFixed(1)),
      speedKmh: Math.round(60 + Math.sin(t * Math.PI * 4) * 35 + r() * 20),
      leanLeftDeg: Math.max(0, Math.round((twist > 0 ? twist : 0) * sporty + r() * 6)),
      leanRightDeg: Math.max(0, Math.round((twist < 0 ? -twist : 0) * sporty + r() * 6)),
      altitudeM: Math.round(500 + Math.sin(t * Math.PI) * 900 + r() * 60),
      rpm: Math.round(3500 + Math.sin(t * Math.PI * 6) * 2200 + r() * 500),
    }
  })
}

export const profile: RiderProfile = {
  bmwId: 'rider@example.com',
  displayName: 'Jacob',
  memberSince: '2019',
  homeDealer: 'BMW Motorrad München',
}

export const bikes: Bike[] = [
  {
    id: 'gs',
    model: 'R 1300 GS',
    variant: 'Adventure · Racing Blue',
    vin: 'WB10A0308PZ***421',
    imageTint: '#2E9CE8',
    connection: 'connected',
    lastSeen: 'Live · 2 min ago',
    fuelPercent: 68,
    rangeKm: 412,
    odometerKm: 24817,
    tankLitres: 19,
    consumptionLper100: 4.7,
    serviceDueKm: 3183,
    serviceDueDate: '14 Apr 2026',
    recall: null,
    tyrePressureBar: { front: 2.4, rear: 2.8 },
    batteryVolt: 12.9,
    hasConnectedRideNavigator: true,
  },
  {
    id: 'xr',
    model: 'S 1000 XR',
    variant: 'M Package · Light White',
    vin: 'WB10E1308MZ***077',
    imageTint: '#E7222E',
    connection: 'last_seen',
    lastSeen: 'Last seen yesterday, 19:42',
    fuelPercent: 31,
    rangeKm: 143,
    odometerKm: 11294,
    tankLitres: 20,
    consumptionLper100: 6.1,
    serviceDueKm: 706,
    serviceDueDate: '02 Mar 2026',
    recall: 'Recall 0061240200 — rear brake line clip inspection',
    tyrePressureBar: { front: 2.5, rear: 2.9 },
    batteryVolt: 12.4,
    hasConnectedRideNavigator: true,
  },
  {
    id: 'nine',
    model: 'R 12 nineT',
    variant: 'Option 719 Aluminium',
    vin: 'WB10J0107RZ***903',
    imageTint: '#C9A227',
    connection: 'phone_only',
    lastSeen: 'No connectivity module',
    fuelPercent: null,
    rangeKm: null,
    odometerKm: null,
    tankLitres: 16,
    consumptionLper100: 5.4,
    serviceDueKm: null,
    serviceDueDate: null,
    recall: null,
    tyrePressureBar: null,
    batteryVolt: null,
    hasConnectedRideNavigator: false,
  },
  {
    id: 'ce04',
    model: 'CE 04',
    variant: 'Avantgarde · Magellan Grey',
    vin: 'WB10K0400NZ***155',
    imageTint: '#8BFF2E',
    connection: 'connected',
    lastSeen: 'Live · charging',
    fuelPercent: 54,
    rangeKm: 72,
    odometerKm: 6042,
    tankLitres: 8.9,
    consumptionLper100: 12.4,
    serviceDueKm: 1958,
    serviceDueDate: '30 Jun 2026',
    recall: null,
    tyrePressureBar: { front: 2.2, rear: 2.5 },
    batteryVolt: 12.7,
    hasConnectedRideNavigator: false,
  },
]

const alpinePois: Poi[] = [
  { id: 'p1', name: 'Aral Bad Tölz', layer: 'fuel', atKm: 46, note: 'Last fuel before the pass' },
  { id: 'p2', name: 'Sylvenstein dam viewpoint', layer: 'twisty', atKm: 71 },
  { id: 'p3', name: 'Achenpass · 941 m', layer: 'passes', atKm: 88 },
  { id: 'p4', name: 'Gasthof Alpenrose', layer: 'food', atKm: 103, note: 'Biker-friendly, big parking' },
  { id: 'p5', name: 'BMW Motorrad Garmisch', layer: 'dealers', atKm: 141 },
  { id: 'p6', name: 'Hotel Zugspitze (BMW partner)', layer: 'hotels', atKm: 147 },
]

export const routes: Route[] = [
  {
    id: 'r-alpine',
    name: 'Alpine Passes Loop',
    region: 'Bavaria · Tyrol',
    origin: 'München',
    destination: 'München',
    via: ['Bad Tölz', 'Achenpass', 'Sylvenstein', 'Garmisch'],
    distanceKm: 294,
    durationMin: 348,
    ascentM: 3120,
    curvinessScore: 83,
    mode: 'curvy',
    avoid: ['motorways', 'tolls'],
    roundTrip: true,
    segments: [
      { fromKm: 0, toKm: 42, mode: 'fastest', road: 'B11 out of the city' },
      { fromKm: 42, toKm: 188, mode: 'extra_curvy', road: 'Achenpass / Sylvenstein' },
      { fromKm: 188, toKm: 294, mode: 'fast_curvy', road: 'Loisach valley home' },
    ],
    elevation: makeElevation(7, 294, 1150),
    path: makePath(11, { lat: 48.137, lng: 11.575 }, { lat: 47.492, lng: 11.096 }, 0.09),
    pois: alpinePois,
    source: 'planned',
    savedAt: '2 days ago',
  },
  {
    id: 'r-stelvio',
    name: 'Stelvio Back Road',
    region: 'South Tyrol',
    origin: 'Bormio',
    destination: 'Prad am Stilfserjoch',
    via: ['Passo dello Stelvio'],
    distanceKm: 49,
    durationMin: 96,
    ascentM: 1840,
    curvinessScore: 97,
    mode: 'extra_curvy',
    avoid: ['unpaved'],
    roundTrip: false,
    segments: [{ fromKm: 0, toKm: 49, mode: 'extra_curvy', road: 'SS38 · 48 hairpins' }],
    elevation: makeElevation(3, 49, 1700),
    path: makePath(5, { lat: 46.467, lng: 10.373 }, { lat: 46.617, lng: 10.588 }, 0.03),
    pois: [
      { id: 's1', name: 'Passo dello Stelvio · 2757 m', layer: 'passes', atKm: 24 },
      { id: 's2', name: 'Tibet Hütte', layer: 'food', atKm: 26 },
      { id: 's3', name: 'Agip Prad', layer: 'fuel', atKm: 46 },
    ],
    source: 'curated',
    author: 'BMW Motorrad Touring',
    savedAt: 'Saved 1 week ago',
  },
  {
    id: 'r-gravel',
    name: 'Bohemian Gravel Link',
    region: 'Bavarian Forest',
    origin: 'Zwiesel',
    destination: 'Bayerisch Eisenstein',
    via: ['Arber forest tracks'],
    distanceKm: 112,
    durationMin: 178,
    ascentM: 1420,
    curvinessScore: 74,
    mode: 'curvy',
    avoid: ['tolls'],
    roundTrip: false,
    segments: [
      { fromKm: 0, toKm: 38, mode: 'curvy', road: 'Forest asphalt' },
      { fromKm: 38, toKm: 74, mode: 'curvy', road: 'Gravel service road' },
      { fromKm: 74, toKm: 112, mode: 'fast_curvy', road: 'B11 border run' },
    ],
    elevation: makeElevation(9, 112, 780),
    path: makePath(13, { lat: 49.017, lng: 13.236 }, { lat: 49.122, lng: 13.204 }, 0.05),
    pois: [
      { id: 'g1', name: 'Großer Arber gravel start', layer: 'twisty', atKm: 38 },
      { id: 'g2', name: 'Shell Zwiesel', layer: 'fuel', atKm: 4 },
      { id: 'g3', name: 'Waldhaus (GS meetup)', layer: 'events', atKm: 66 },
    ],
    source: 'community',
    author: 'gs_rider_muc',
    savedAt: 'Saved 3 weeks ago',
  },
  {
    id: 'r-city',
    name: 'Isar Night Loop',
    region: 'München',
    origin: 'München Ost',
    destination: 'München Ost',
    via: ['Isar riverside', 'Olympiapark'],
    distanceKm: 38,
    durationMin: 62,
    ascentM: 140,
    curvinessScore: 41,
    mode: 'fastest',
    avoid: ['motorways'],
    roundTrip: true,
    segments: [{ fromKm: 0, toKm: 38, mode: 'fastest', road: 'City boulevards' }],
    elevation: makeElevation(17, 38, 90),
    path: makePath(21, { lat: 48.12, lng: 11.62 }, { lat: 48.18, lng: 11.53 }, 0.02),
    pois: [
      { id: 'c1', name: 'Charge point Olympiapark', layer: 'parking', atKm: 18 },
      { id: 'c2', name: 'Café Kosmos', layer: 'food', atKm: 27 },
    ],
    source: 'curated',
    author: 'BMW Motorrad Urban',
    savedAt: 'Saved yesterday',
  },
  {
    id: 'r-import',
    name: 'Munich – Garmisch-Partenkirchen',
    region: 'Imported GPX',
    origin: 'München',
    destination: 'Garmisch-Partenkirchen',
    via: [],
    distanceKm: 96,
    durationMin: 129,
    ascentM: 620,
    curvinessScore: 58,
    mode: 'fast_curvy',
    avoid: [],
    roundTrip: false,
    segments: [{ fromKm: 0, toKm: 96, mode: 'fast_curvy', road: 'B2 / B23' }],
    elevation: makeElevation(23, 96, 520),
    path: makePath(29, { lat: 48.137, lng: 11.575 }, { lat: 47.492, lng: 11.096 }, 0.02),
    pois: [{ id: 'i1', name: 'Total Murnau', layer: 'fuel', atKm: 58 }],
    source: 'imported',
    author: 'kurviger_route.gpx',
    savedAt: 'Imported today',
  },
]

export const rides: Ride[] = [
  {
    id: 'ride-1',
    title: 'Achenpass evening',
    date: 'Sat 6 Sep · 16:20',
    bikeId: 'gs',
    distanceKm: 187,
    durationMin: 214,
    avgSpeedKmh: 52,
    topSpeedKmh: 164,
    maxLeanLeftDeg: 43,
    maxLeanRightDeg: 39,
    ascentM: 1980,
    curvinessScore: 81,
    path: makePath(31, { lat: 48.137, lng: 11.575 }, { lat: 47.55, lng: 11.7 }, 0.07),
    samples: makeSamples(33, 187, 44),
    photos: [
      { id: 'ph1', atKm: 88, caption: 'Achenpass summit', tint: '#2E9CE8' },
      { id: 'ph2', atKm: 121, caption: 'Sylvenstein blue', tint: '#2E6B8C' },
    ],
  },
  {
    id: 'ride-2',
    title: 'Sunday sport run',
    date: 'Sun 31 Aug · 09:05',
    bikeId: 'xr',
    distanceKm: 226,
    durationMin: 232,
    avgSpeedKmh: 58,
    topSpeedKmh: 211,
    maxLeanLeftDeg: 51,
    maxLeanRightDeg: 48,
    ascentM: 1440,
    curvinessScore: 92,
    path: makePath(37, { lat: 48.1, lng: 11.4 }, { lat: 47.7, lng: 12.1 }, 0.08),
    samples: makeSamples(39, 226, 54),
    photos: [{ id: 'ph3', atKm: 140, caption: 'Kesselberg', tint: '#E7222E' }],
  },
  {
    id: 'ride-3',
    title: 'Commute · Isar',
    date: 'Fri 29 Aug · 07:48',
    bikeId: 'ce04',
    distanceKm: 21,
    durationMin: 38,
    avgSpeedKmh: 33,
    topSpeedKmh: 89,
    maxLeanLeftDeg: 22,
    maxLeanRightDeg: 19,
    ascentM: 80,
    curvinessScore: 28,
    path: makePath(41, { lat: 48.12, lng: 11.62 }, { lat: 48.16, lng: 11.55 }, 0.015),
    samples: makeSamples(43, 21, 24),
    photos: [],
  },
]

export const groupRide: GroupRide = {
  id: 'grp-1',
  name: 'Saturday Pass Run',
  routeId: 'r-alpine',
  startsAt: 'Today · 08:30',
  regroupPoint: 'Achenpass summit car park',
  regroupAtKm: 88,
  riders: [
    {
      id: 'u1',
      name: 'Jacob (you)',
      bike: 'R 1300 GS',
      status: 'riding',
      distanceBehindKm: 0,
      batteryPercent: 84,
      position: { lat: 47.72, lng: 11.62 },
    },
    {
      id: 'u2',
      name: 'Lena',
      bike: 'F 900 XR',
      status: 'riding',
      distanceBehindKm: 1.2,
      batteryPercent: 66,
      position: { lat: 47.735, lng: 11.605 },
    },
    {
      id: 'u3',
      name: 'Timo',
      bike: 'R 1250 RT',
      status: 'stopped',
      distanceBehindKm: 6.4,
      batteryPercent: 41,
      position: { lat: 47.78, lng: 11.58 },
    },
    {
      id: 'u4',
      name: 'Marco',
      bike: 'S 1000 XR',
      status: 'lost_signal',
      distanceBehindKm: 12.8,
      batteryPercent: 23,
      position: { lat: 47.83, lng: 11.54 },
    },
  ],
}

export const mapRegions: MapRegion[] = [
  { id: 'm1', name: 'Germany · Bavaria', sizeMb: 1840, status: 'installed', progress: 100, updatedAt: '4 Sep 2026' },
  { id: 'm2', name: 'Austria · Tyrol', sizeMb: 720, status: 'downloading', progress: 62, updatedAt: null },
  {
    id: 'm3',
    name: 'Italy · South Tyrol',
    sizeMb: 910,
    status: 'failed',
    progress: 18,
    updatedAt: null,
    error: 'Map catalog unreachable — tap to resume, the planner keeps working online',
  },
  { id: 'm4', name: 'Switzerland', sizeMb: 1120, status: 'available', progress: 0, updatedAt: null },
]

export const seasonStats: SeasonStats = {
  year: 2026,
  rides: 47,
  distanceKm: 6218,
  ridingTimeMin: 9840,
  passesRidden: 23,
  topCurviness: 97,
  countries: ['DE', 'AT', 'IT', 'CH'],
}
