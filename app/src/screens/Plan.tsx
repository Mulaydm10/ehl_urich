import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ChevronDown, Download, Fuel, Send, Upload } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { RouteMap } from '../components/RouteMap'
import type { MapMarker } from '../components/RouteMap'
import { Chip, EmptyState, Feedback, GhostButton, PageHeader, PlannerSwitch, PrimaryButton, SectionTitle } from '../components/primitives'
import { TelemetryRow } from '../components/Cluster'
import type { AvoidanceId, CurvatureMode, PoiLayerId, TransferResult } from '../domain/types'

const MODES: { id: CurvatureMode; label: string }[] = [
  { id: 'fastest', label: 'Fastest' },
  { id: 'fast_curvy', label: 'Fast + curvy' },
  { id: 'curvy', label: 'Curvy' },
  { id: 'extra_curvy', label: 'Extra curvy' },
]

const AVOID: { id: AvoidanceId; label: string }[] = [
  { id: 'closures', label: 'Closures' },
  { id: 'tolls', label: 'Tolls' },
  { id: 'ferries', label: 'Ferries' },
  { id: 'motorways', label: 'Motorways' },
  { id: 'main_roads', label: 'Main roads' },
  { id: 'narrow_roads', label: 'Narrow' },
  { id: 'unpaved', label: 'Unpaved' },
]

const LAYERS: { id: PoiLayerId; label: string }[] = [
  { id: 'fuel', label: 'Fuel' },
  { id: 'passes', label: 'Passes' },
  { id: 'twisty', label: 'Twisty' },
  { id: 'dealers', label: 'BMW dealer' },
  { id: 'hotels', label: 'Biker hotel' },
  { id: 'food', label: 'Food' },
]

function ElevationProfile({ points, ascent }: { points: { km: number; elevationM: number }[]; ascent: number }) {
  const w = 360
  const h = 84
  const max = Math.max(...points.map((p) => p.elevationM))
  const min = Math.min(...points.map((p) => p.elevationM))
  const maxKm = points[points.length - 1].km
  const xy = points.map((p) => ({
    x: (p.km / maxKm) * w,
    y: h - ((p.elevationM - min) / Math.max(max - min, 1)) * (h - 10) - 4,
  }))
  const line = xy.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  return (
    <div className="px-6 pt-2">
      <div className="flex items-end justify-between">
        <span className="label">Elevation · {ascent} m ascent</span>
        <span className="text-[11px] font-medium text-ash">
          {min} – {max} m
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="mt-1 w-full" preserveAspectRatio="none" height={h}>
        <path d={`${line} L${w},${h} L0,${h} Z`} fill="#B9BCC1" opacity={0.06} />
        <path d={line} fill="none" stroke="#B9BCC1" strokeWidth={1.6} />
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={w * f} y1={0} x2={w * f} y2={h} stroke="rgba(255,255,255,0.06)" />
        ))}
      </svg>
    </div>
  )
}

export function PlanScreen() {
  const { routes, activeRouteId, setActiveRouteId, addRoute, plan, bike, bikeProfile, api } = useAppState()
  const [params, setParams] = useSearchParams()
  const routeParam = params.get('route')
  const [mode, setMode] = useState<CurvatureMode>('curvy')
  const [avoid, setAvoid] = useState<AvoidanceId[]>(['motorways', 'tolls'])
  const [layers, setLayers] = useState<PoiLayerId[]>(['fuel', 'passes'])
  const [roundTrip, setRoundTrip] = useState(false)
  const [origin, setOrigin] = useState('München')
  const [destination, setDestination] = useState('Garmisch-Partenkirchen')
  const [pendingAction, setPendingAction] = useState<'plan' | 'send' | 'import' | 'export' | null>(null)
  const busy = pendingAction !== null
  const [transfer, setTransfer] = useState<TransferResult | null>(null)
  const [feedback, setFeedback] = useState<{ area: 'plan' | 'transfer' | 'file'; error: boolean; message: string } | null>(null)

  const route = useMemo(
    () => routes.find((r) => r.id === (routeParam ?? activeRouteId)) ?? routes[0],
    [routes, routeParam, activeRouteId],
  )

  const [editingRouteId, setEditingRouteId] = useState<string | null>(null)
  if (route && editingRouteId !== route.id) {
    setEditingRouteId(route.id)
    setOrigin(route.origin)
    setDestination(route.destination)
    setRoundTrip(route.roundTrip)
    setMode(route.mode)
    setAvoid(route.avoid)
  }

  if (!route || !bike || !bikeProfile) return <div className="pb-8"><PageHeader eyebrow="Route planner" title="Your next ride" /><div className="px-6"><EmptyState title="No route selected" action={<Link to="/discover" className="button button-secondary">Browse routes</Link>}>Choose a route from Discover to open it in the planner.</EmptyState></div></div>

  const markers: MapMarker[] = route.pois
    .filter((p) => layers.includes(p.layer))
    .map((p) => ({ id: p.id, t: p.atKm / route.distanceKm, label: p.name, tone: p.layer === 'fuel' ? 'warn' : 'bone' }))

  const rangeKm = bike.rangeKm
  const needsFuel = rangeKm !== null && rangeKm < route.distanceKm

  const onPlan = async () => {
    if (!origin.trim() || (!roundTrip && !destination.trim())) {
      setFeedback({ area: 'plan', error: true, message: 'Enter a start and destination to calculate your route.' })
      return
    }
    setPendingAction('plan')
    setTransfer(null)
    setFeedback(null)
    try {
      const r = await plan({ origin: origin.trim(), destination: destination.trim(), via: [], mode, avoid, roundTrip })
      setActiveRouteId(r.id)
      setParams({})
      setFeedback({ area: 'plan', error: false, message: `Route updated · ${r.distanceKm} km · ${r.curvinessScore} curviness` })
    } catch {
      setFeedback({ area: 'plan', error: true, message: 'Route calculation failed. Your previous route is still here. Try again.' })
    } finally { setPendingAction(null) }
  }

  const onSend = async () => {
    setPendingAction('send')
    setTransfer(null)
    setFeedback(null)
    try { setTransfer(await api.sendRouteToBike(route.id, bike)) }
    catch { setFeedback({ area: 'transfer', error: true, message: 'The route could not be sent. Try again when the connection is available.' }) }
    finally { setPendingAction(null) }
  }

  return (
    <div className="pb-8">
      <PageHeader eyebrow="Navigation" title="Plan your ride" />
      <PlannerSwitch current="plan" />
      <section className="map-section">
        <RouteMap path={route.path} markers={markers} height={170} active />
        <div className="p-5">
          <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h2 className="text-[18px] font-medium tracking-[-0.025em]">{route.name}</h2><p className="caption mt-1">{route.roundTrip ? 'Round trip' : `${route.origin} → ${route.destination}`}</p></div><span className="status-pill shrink-0" data-live>Selected</span></div>
          <div className="mt-6 grid grid-cols-3 gap-4">
            {[[String(route.distanceKm), 'km'], [`${Math.floor(route.durationMin / 60)}:${String(route.durationMin % 60).padStart(2, '0')}`, 'hours'], [String(route.curvinessScore), 'curviness']].map(([value, unit]) => <div key={unit}><span className="readout text-[32px]">{value}</span><span className="label mt-2 block">{unit}</span></div>)}
          </div>
        </div>
      </section>

      <div className="panel mx-6 mt-5 overflow-hidden">
        {[
          { label: 'From', value: origin, set: setOrigin },
          { label: 'To', value: destination, set: setDestination },
        ].map(({ label, value, set }) => (
          <label key={label} className="field">
            <span className="label w-10 shrink-0">{label}</span>
            <input value={label === 'To' && roundTrip ? origin : value} disabled={busy || (label === 'To' && roundTrip)} onChange={(e) => { set(e.target.value); if (feedback?.area === 'plan') setFeedback(null) }} autoComplete="off" />
          </label>
        ))}
      </div>

      <SectionTitle title="Route character" action={<span className="text-caption font-medium text-accent-text">{MODES.find((m) => m.id === mode)?.label}</span>} />
      <div className="px-6">
        <label className="block py-1">
          <span className="sr-only">Route curvature</span>
          <input type="range" min={0} max={3} step={1} value={MODES.findIndex((m) => m.id === mode)}
            aria-valuetext={MODES.find((m) => m.id === mode)?.label}
            onChange={(e) => setMode(MODES[Number(e.target.value)].id)} className="curvature-slider" disabled={busy} style={{ '--slider-fill': `${MODES.findIndex((m) => m.id === mode) / 3 * 100}%` } as CSSProperties} />
        </label>
        <div className="grid grid-cols-4 gap-2 text-[10px] text-ash [&>span:last-child]:text-right [&>span:nth-child(2)]:text-center [&>span:nth-child(3)]:text-center">
          {MODES.map((m) => <span key={m.id} className={m.id === mode ? 'font-medium text-bone' : ''}>{m.label}</span>)}
        </div>
        <div className="mt-5 flex items-center justify-between gap-4 border-y border-white/[0.07] py-3">
          <span className="caption">Finish where you started</span>
          <Chip disabled={busy} active={roundTrip} onClick={() => setRoundTrip(!roundTrip)}>Round trip</Chip>
        </div>
      </div>

      <div className="px-6 py-5">
        <PrimaryButton onClick={onPlan} disabled={busy} busy={pendingAction === 'plan'}>{pendingAction === 'plan' ? 'Calculating route…' : 'Calculate route'}</PrimaryButton>
        {feedback?.area === 'plan' ? <div className="mt-3"><Feedback tone={feedback.error ? 'error' : 'success'}>{feedback.message}</Feedback></div> : null}
      </div>
      <details className="settings-disclosure">
        <summary><span><span className="block text-[15px] font-medium">Road preferences</span><span className="caption mt-1 block">{avoid.length} {avoid.length === 1 ? 'avoidance' : 'avoidances'} selected</span></span><ChevronDown size={17} className="shrink-0 text-ash" /></summary>
        <div className="flex flex-wrap gap-2">
          {AVOID.map((a) => <Chip disabled={busy} key={a.id} active={avoid.includes(a.id)} onClick={() => setAvoid((p) => p.includes(a.id) ? p.filter((x) => x !== a.id) : [...p, a.id])}>{a.label}</Chip>)}
        </div>
      </details>
      <details className="settings-disclosure">
        <summary><span><span className="block text-[15px] font-medium">Places along the route</span><span className="caption mt-1 block">{layers.length} map layers visible</span></span><ChevronDown size={17} className="shrink-0 text-ash" /></summary>
        <div className="flex flex-wrap gap-2">
          {LAYERS.map((l) => <Chip disabled={busy} key={l.id} active={layers.includes(l.id)} onClick={() => setLayers((p) => p.includes(l.id) ? p.filter((x) => x !== l.id) : [...p, l.id])}>{l.label}</Chip>)}
        </div>
      </details>

      <div className="pt-4">
        <ElevationProfile points={route.elevation} ascent={route.ascentM} />
      </div>

      <div className="panel mx-6 mt-6">
        <TelemetryRow
          items={[
            { label: 'Bike', value: bike.model, text: true },
            { label: 'Range', value: rangeKm === null ? '--' : String(rangeKm), unit: 'km' },
            { label: 'Stops', value: String(route.pois.filter((p) => p.layer === 'fuel').length) },
          ]}
        />
      </div>

      {needsFuel ? (
        <div className="mx-6 mt-3 flex items-center gap-4 notice border-warn/25 bg-warn/[0.05]">
          <Fuel size={16} className="shrink-0 text-warn" />
          <span className="text-[13px] text-bone">
            {route.distanceKm} km exceeds the {bike.model}'s {rangeKm} km range — one fuel stop inserted at{' '}
            {Math.round((rangeKm ?? 0) * 0.8)} km.
          </span>
        </div>
      ) : null}

      {route.pois.filter((p) => layers.includes(p.layer)).length ? (
        <div className="mt-4 px-6">
          <div className="label pb-3">Along the route</div>
          <div className="panel divide-y divide-white/[0.06] px-4">
            {route.pois
              .filter((p) => layers.includes(p.layer))
              .map((p) => (
                <div key={p.id} className="flex items-center justify-between gap-4 py-3">
                  <div>
                    <div className="text-[13px] text-bone">{p.name}</div>
                    <div className="caption mt-1">{p.note ?? p.layer}</div>
                  </div>
                  <span className="shrink-0 font-mono text-[11px] text-ash">{p.atKm} km</span>
                </div>
              ))}
          </div>
        </div>
      ) : null}

      <div className="mt-6 space-y-3 border-t border-white/[0.065] px-6 pt-6">
        <div className="label pb-1">ConnectedRide Navigator</div>
        <PrimaryButton onClick={onSend} busy={pendingAction === 'send'} disabled={busy || !bike.hasConnectedRideNavigator}>
          <span className="inline-flex items-center justify-center gap-2">
            <Send size={16} /> {pendingAction === 'send' ? 'Sending route…' : 'Send to bike'}
          </span>
        </PrimaryButton>
        {!bike.hasConnectedRideNavigator ? (
          <div className="caption">No ConnectedRide Navigator paired with this BMW — export GPX instead.</div>
        ) : null}
        {transfer ? <Feedback tone={transfer.ok ? 'success' : 'info'}>{transfer.message}</Feedback> : null}
        {feedback?.area === 'transfer' ? <Feedback tone={feedback.error ? 'error' : 'info'}>{feedback.message}</Feedback> : null}
        <div className="grid grid-cols-2 gap-2">
          <GhostButton
            busy={pendingAction === 'export'} disabled={busy}
            onClick={async () => {
              setPendingAction('export')
              setFeedback(null)
              try {
                const url = await api.exportRoute(route.id, 'ConnectedRide Navigator')
                if (!url) throw new Error('Export unavailable')
                setFeedback({ area: 'file', error: false, message: 'GPX export prepared. File downloads are not available in this preview.' })
              } catch { setFeedback({ area: 'file', error: true, message: 'Could not prepare the GPX export. Try again.' }) }
              finally { setPendingAction(null) }
            }}
          >
            <span className="inline-flex items-center gap-2">
              <Download size={15} /> Export GPX
            </span>
          </GhostButton>
          <GhostButton
            busy={pendingAction === 'import'} disabled={busy}
            onClick={async () => {
              setPendingAction('import')
              setFeedback(null)
              try {
                const r = await api.importRoute('kurviger_route.gpx')
                addRoute(r)
                setParams({})
                setFeedback({ area: 'file', error: false, message: `Imported ${r.name}` })
              } catch { setFeedback({ area: 'file', error: true, message: 'Could not import the sample GPX. Try again.' }) }
              finally { setPendingAction(null) }
            }}
          >
            <span className="inline-flex items-center gap-2">
              <Upload size={15} /> Sample GPX
            </span>
          </GhostButton>
        </div>
        {feedback?.area === 'file' ? <Feedback tone={feedback.error ? 'error' : 'info'}>{feedback.message}</Feedback> : null}
      </div>
    </div>
  )
}
