import L from 'leaflet'
import { Layers, Mountain, Moon, Satellite } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, Marker, Pane, Polyline, ScaleControl, TileLayer, Tooltip, ZoomControl, useMap, useMapEvents } from 'react-leaflet'
import type { Candidate, LonLat, Plan, Refusal } from '../lib/api'
import { toLatLng } from '../lib/geo'

// All keyless Esri services (CARTO's Dark Matter now watermarks tiles served
// without an API key). Each style is a stack: relief/imagery, then labels.
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services'
const tile = (svc: string) => `${ESRI}/${svc}/MapServer/tile/{z}/{y}/{x}`
const ATTR = 'Tiles &copy; Esri &mdash; Esri, Maxar, Earthstar Geographics, DeLorme, NAVTEQ'

export type Basemap = 'terrain' | 'dark' | 'satellite'
interface Layer { url: string; opacity?: number; className?: string; maxZoom: number }
const STYLES: Record<Basemap, { label: string; icon: typeof Mountain; layers: Layer[] }> = {
  terrain: {
    label: 'Terrain', icon: Mountain,
    layers: [
      { url: tile('Elevation/World_Hillshade_Dark'), maxZoom: 16, className: 'tile-relief' },
      { url: tile('Canvas/World_Dark_Gray_Base'), maxZoom: 16, opacity: 0.55, className: 'tile-roads' },
      { url: tile('Canvas/World_Dark_Gray_Reference'), maxZoom: 16, className: 'tile-labels' },
    ],
  },
  dark: {
    label: 'Dark', icon: Moon,
    layers: [
      { url: tile('Canvas/World_Dark_Gray_Base'), maxZoom: 16 },
      { url: tile('Canvas/World_Dark_Gray_Reference'), maxZoom: 16 },
    ],
  },
  satellite: {
    label: 'Satellite', icon: Satellite,
    layers: [
      { url: tile('World_Imagery'), maxZoom: 18, className: 'tile-imagery' },
      { url: tile('Reference/World_Transportation'), maxZoom: 18, opacity: 0.7 },
      { url: tile('Reference/World_Boundaries_and_Places'), maxZoom: 18 },
    ],
  },
}

function BasemapPicker({ value, onChange }: { value: Basemap; onChange: (b: Basemap) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (ref.current) { L.DomEvent.disableClickPropagation(ref.current); L.DomEvent.disableScrollPropagation(ref.current) }
  }, [])
  return (
    <div className="leaflet-top leaflet-left pointer-events-none" style={{ top: 10, left: 10 }}>
      <div className="leaflet-control pointer-events-auto">
        <div ref={ref} className="basemap-picker" onMouseLeave={() => setOpen(false)}>
          <button type="button" className="basemap-btn" onClick={() => setOpen((o) => !o)} title="Basemap">
            <Layers size={14} /> <span>{STYLES[value].label}</span>
          </button>
          {open ? (
            <div className="basemap-menu">
              {(Object.keys(STYLES) as Basemap[]).map((k) => {
                const Icon = STYLES[k].icon
                return (
                  <button type="button" key={k} className={`basemap-item ${k === value ? 'is-on' : ''}`}
                    onClick={() => { onChange(k); setOpen(false) }}>
                    <Icon size={13} /> {STYLES[k].label}
                  </button>
                )
              })}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export const CAND_COLORS = ['#F5A524', '#3ED598', '#C77DFF', '#6DB6E8', '#FF7A59', '#FFD166']

const riderIcon = L.divIcon({
  className: '', html: '<div style="position:relative;width:16px;height:16px"><div class="rider-ring"></div><div class="rider-dot"></div></div>',
  iconSize: [16, 16], iconAnchor: [8, 8],
})
const refusalIcon = L.divIcon({ className: '', html: '<div class="refusal-dot"></div>', iconSize: [12, 12], iconAnchor: [6, 6] })
const endIcon = (label: string, color: string) => L.divIcon({
  className: '', html: `<div class="end-pin" style="background:${color}">${label}</div>`, iconSize: [0, 0], iconAnchor: [0, 0],
})
const viaIcon = (n: number) => endIcon(String(n), '#F5A524')

/** Polyline that draws itself on when its geometry changes. */
function DrawOnLine({ path, color, weight, opacity, dashed, animate, onClick, children }: {
  path: LonLat[]; color: string; weight: number; opacity: number; dashed?: boolean; animate: boolean
  onClick?: () => void; children?: React.ReactNode
}) {
  const ref = useRef<L.Polyline>(null)
  const latlngs = useMemo(() => path.map(toLatLng), [path])
  useEffect(() => {
    const el = ref.current?.getElement() as SVGPathElement | undefined
    if (!el || !animate) return
    const len = el.getTotalLength()
    el.classList.remove('draw-on')
    el.style.strokeDasharray = `${len}`
    el.style.strokeDashoffset = `${len}`
    // force a reflow so the animation restarts on every new line
    void el.getBoundingClientRect()
    el.classList.add('draw-on')
    const done = () => { el.style.strokeDasharray = dashed ? '6 8' : ''; el.style.strokeDashoffset = '' }
    el.addEventListener('animationend', done, { once: true })
    return () => el.removeEventListener('animationend', done)
  }, [latlngs, animate, dashed])
  return (
    <Polyline ref={ref} positions={latlngs} className="cand-line"
      pathOptions={{ color, weight, opacity, dashArray: dashed && !animate ? '6 8' : undefined, lineCap: 'round', lineJoin: 'round' }}
      eventHandlers={onClick ? { click: onClick } : undefined}>
      {children}
    </Polyline>
  )
}

function FitOnce({ bounds }: { bounds: L.LatLngBounds | null }) {
  const map = useMap()
  const key = bounds ? bounds.toBBoxString() : ''
  useEffect(() => {
    if (bounds && bounds.isValid()) map.flyToBounds(bounds, { padding: [40, 40], duration: 0.6, maxZoom: 13 })
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

function ClickPicker({ onPick }: { onPick?: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onPick?.(e.latlng.lat, e.latlng.lng) })
  return null
}

export interface RouteMapProps {
  active: Plan | null
  /** index of the last active-path vertex the simulated rider has passed */
  riddenIndex: number
  candidates: Candidate[]
  selected: number | null
  onSelect: (i: number) => void
  rider: LonLat | null
  start: [number, number] | null
  dest: [number, number] | null
  /** stops the rider put on the way, in his own order */
  via: [number, number][]
  onRemoveVia?: (i: number) => void
  onPick?: (lat: number, lon: number) => void
  coverage: { lat: readonly [number, number]; lon: readonly [number, number] }
}

export default function RouteMap(p: RouteMapProps) {
  const [basemap, setBasemap] = useState<Basemap>('terrain')
  const style = STYLES[basemap]
  const bounds = useMemo(() => {
    const pts: [number, number][] = []
    if (p.active?.path?.length) pts.push(...p.active.path.map(toLatLng))
    for (const c of p.candidates) if (c.path.length) pts.push(...c.path.map(toLatLng))
    if (!pts.length) return null
    return L.latLngBounds(pts)
  }, [p.active, p.candidates])

  const refusals: (Refusal & { src: string })[] = useMemo(() => {
    const out: (Refusal & { src: string })[] = []
    const sel = p.selected != null ? p.candidates.find((c) => c.index === p.selected) : null
    const source = sel ?? p.active
    for (const r of source?.refusals ?? []) out.push({ ...r, src: sel ? `candidate ${sel.index + 1}` : 'active route' })
    return out
  }, [p.active, p.candidates, p.selected])

  const ridden = useMemo(() => {
    const path = p.active?.path
    if (!path?.length || !p.rider) return []
    return [...path.slice(0, p.riddenIndex + 1), p.rider]
  }, [p.active, p.riddenIndex, p.rider])

  const coverageRect: [number, number][] = [
    [p.coverage.lat[0], p.coverage.lon[0]], [p.coverage.lat[0], p.coverage.lon[1]],
    [p.coverage.lat[1], p.coverage.lon[1]], [p.coverage.lat[1], p.coverage.lon[0]], [p.coverage.lat[0], p.coverage.lon[0]],
  ]

  return (
    <MapContainer center={[47.7, 11.3]} zoom={9} className="h-full w-full" zoomControl={false} attributionControl>
      {style.layers.map((l, i) => (
        <TileLayer key={`${basemap}-${i}`} url={l.url} attribution={i === 0 ? ATTR : undefined}
          maxZoom={l.maxZoom} opacity={l.opacity ?? 1} className={l.className} />
      ))}
      <BasemapPicker value={basemap} onChange={setBasemap} />
      <div className="map-vignette" />
      <ZoomControl position="topright" />
      <ScaleControl position="topright" imperial={false} />
      <Polyline positions={coverageRect} pathOptions={{ color: '#6DB6E8', weight: 1, opacity: 0.3, dashArray: '4 8' }} />
      <FitOnce bounds={bounds} />
      <ClickPicker onPick={p.onPick} />

      {p.active?.path?.length ? (
        <>
          <Polyline positions={p.active.path.map(toLatLng)} className="cand-line"
            pathOptions={{ color: '#1C69D4', weight: 14, opacity: p.candidates.length ? 0.1 : 0.22, lineCap: 'round', lineJoin: 'round', interactive: false }} />
          <DrawOnLine path={p.active.path} color="#1C69D4" weight={5} opacity={p.candidates.length ? 0.5 : 0.95} animate>
            <Tooltip sticky>active route</Tooltip>
          </DrawOnLine>
          {!p.candidates.length ? (
            <Pane name="flow" style={{ zIndex: 450 }}>
              <Polyline positions={p.active.path.map(toLatLng)} className="flow-line"
                pathOptions={{ color: '#BFD9FF', weight: 2, opacity: 0.9, dashArray: '2 14', lineCap: 'round', interactive: false }} />
            </Pane>
          ) : null}
          {ridden.length > 1 ? (
            <Polyline positions={ridden.map(toLatLng)}
              pathOptions={{ color: '#F1F2F3', weight: 5, opacity: p.candidates.length ? 0.35 : 0.85, lineCap: 'round', lineJoin: 'round', interactive: false }} />
          ) : null}
        </>
      ) : null}

      {p.candidates.filter((c) => c.path.length).map((c) => {
        const isSel = c.index === p.selected
        const color = CAND_COLORS[c.index % CAND_COLORS.length]
        return (
          <span key={`${c.index}-${c.path.length}-${c.path[0]?.join(',')}`}>
            {isSel ? (
              <Polyline positions={c.path.map(toLatLng)} className="cand-line"
                pathOptions={{ color, weight: 16, opacity: 0.18, lineCap: 'round', lineJoin: 'round', interactive: false }} />
            ) : null}
            <DrawOnLine path={c.path} color={color}
              weight={isSel ? 6 : 3} opacity={isSel ? 1 : p.selected == null ? 0.8 : 0.3}
              dashed={c.verdict !== 'accepted'} animate onClick={() => p.onSelect(c.index)}>
              <Tooltip sticky>
                <span className="font-mono">#{c.index + 1}</span> {c.mode} @ {c.thrill.toFixed(2)} — {c.verdict}{c.km != null ? ` · ${c.km} km` : ''}
              </Tooltip>
            </DrawOnLine>
          </span>
        )
      })}

      {refusals.map((r, i) => (
        <Marker key={`ref-${i}`} position={[r.lat, r.lon]} icon={refusalIcon}>
          <Tooltip direction="top" offset={[0, -8]} className="refusal-tip">
            <div>
              <div className="font-semibold text-mred">Refused ({r.src})</div>
              <div>{r.reason}</div>
              <div className="text-ash mt-1">cell {r.cell} · demand {r.demand.toFixed(1)}°</div>
            </div>
          </Tooltip>
        </Marker>
      ))}

      {p.via.map((v, i) => (
        <Marker key={`via-${i}-${v[0]}-${v[1]}`} position={v} icon={viaIcon(i + 1)}
          eventHandlers={p.onRemoveVia ? { click: () => p.onRemoveVia?.(i) } : undefined}>
          <Tooltip direction="top" offset={[0, -10]}>stop {i + 1} of {p.via.length}{p.onRemoveVia ? ' — click to remove' : ''}</Tooltip>
        </Marker>
      ))}
      {p.start ? <Marker position={p.start} icon={endIcon('A', '#F1F2F3')} /> : null}
      {p.dest ? <Marker position={p.dest} icon={endIcon('B', '#6DB6E8')} /> : null}
      {p.rider ? <Marker position={toLatLng(p.rider)} icon={riderIcon} zIndexOffset={1000} /> : null}
    </MapContainer>
  )
}
