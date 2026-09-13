import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type {
  Bike,
  GroupRide,
  MapRegion,
  Ride,
  RiderProfile,
  Route,
  SeasonStats,
} from '../domain/types'
import { mockApi, resolveApi } from '../services/api'
import type { BmwApi, PlanRouteInput } from '../services/api'
import { profileFor } from '../domain/bikeProfiles'
import type { BikeProfile } from '../domain/bikeProfiles'

interface AppStateValue {
  ready: boolean
  loadError: string | null
  retryLoading: () => void
  api: BmwApi
  /** True when the FLOWSTATE + BMW backend answered; false means bundled data. */
  online: boolean
  /** Which route engine the backend loaded, e.g. "service" or "mock". */
  engine: string
  rider: RiderProfile | null
  bikes: Bike[]
  bike: Bike | null
  bikeProfile: BikeProfile | null
  selectBike: (id: string) => void
  routes: Route[]
  rides: Ride[]
  group: GroupRide | null
  regions: MapRegion[]
  stats: SeasonStats | null
  activeRouteId: string
  setActiveRouteId: (id: string) => void
  addRoute: (route: Route) => void
  plan: (input: Omit<PlanRouteInput, 'bikeId'>) => Promise<Route>
  updateRegion: (region: MapRegion) => void
}

const AppStateContext = createContext<AppStateValue | null>(null)

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [api, setApi] = useState<BmwApi>(mockApi)
  const [online, setOnline] = useState(false)
  const [engine, setEngine] = useState('connecting')
  const [ready, setReady] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const retryLoading = () => { setLoadError(null); setLoadAttempt((attempt) => attempt + 1) }
  const [rider, setRider] = useState<RiderProfile | null>(null)
  const [bikes, setBikes] = useState<Bike[]>([])
  const [bikeId, setBikeId] = useState('gs')
  const [routes, setRoutes] = useState<Route[]>([])
  const [rides, setRides] = useState<Ride[]>([])
  const [group, setGroup] = useState<GroupRide | null>(null)
  const [regions, setRegions] = useState<MapRegion[]>([])
  const [stats, setStats] = useState<SeasonStats | null>(null)
  const [activeRouteId, setActiveRouteId] = useState('r-alpine')

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
      const resolved = await resolveApi()
      if (cancelled) return
      const active = resolved.api
      setApi(() => active)
      setOnline(resolved.online)
      setEngine(resolved.engine)
      const [p, b, rt, rd, g, mr, st] = await Promise.all([
        active.getProfile(),
        active.getBikes(),
        active.getRoutes(),
        active.getRides(),
        active.getGroupRide(),
        active.getMapRegions(),
        active.getSeasonStats(),
      ])
      if (cancelled) return
      setRider(p)
      setBikes(b)
      setRoutes(rt)
      setRides(rd)
      setGroup(g)
      setRegions(mr)
      setStats(st)
      setReady(true)
      } catch {
        if (!cancelled) setLoadError('Your garage could not be loaded. Try again.')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadAttempt])

  const bike = useMemo(() => bikes.find((b) => b.id === bikeId) ?? null, [bikes, bikeId])
  const bikeProfile = useMemo(() => (bike ? profileFor(bike) : null), [bike])

  const addRoute = useCallback((route: Route) => {
    setRoutes((prev) => [route, ...prev])
    setActiveRouteId(route.id)
  }, [])

  const plan = useCallback(
    async (input: Omit<PlanRouteInput, 'bikeId'>) => {
      const route = await api.planRoute({ ...input, bikeId })
      addRoute(route)
      return route
    },
    [api, bikeId, addRoute],
  )

  const updateRegion = useCallback((region: MapRegion) => {
    setRegions((prev) => prev.map((r) => (r.id === region.id ? region : r)))
  }, [])

  const value: AppStateValue = {
    ready,
    loadError,
    retryLoading,
    api,
    online,
    engine,
    rider,
    bikes,
    bike,
    bikeProfile,
    selectBike: setBikeId,
    routes,
    rides,
    group,
    regions,
    stats,
    activeRouteId,
    setActiveRouteId,
    addRoute,
    plan,
    updateRegion,
  }

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>
}

export function useAppState(): AppStateValue {
  const ctx = useContext(AppStateContext)
  if (!ctx) throw new Error('useAppState must be used inside AppStateProvider')
  return ctx
}
