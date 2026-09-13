import { useEffect, useState } from 'react'
import { Layers } from 'lucide-react'
import { MapContainer, TileLayer, ZoomControl, useMap } from 'react-leaflet'
import type { LatLngBoundsExpression, LatLngExpression } from 'leaflet'
import 'leaflet/dist/leaflet.css'

/**
 * Real basemap tiles for every map in the app.
 *
 * Keyless providers only, so the app works without an account and the APK can
 * be pointed at any network. Esri's public tile services cover satellite and a
 * dark canvas; OpenTopoMap carries the terrain relief for the mountain/scenic
 * modes; OpenStreetMap is the plain street map. All require the attribution
 * rendered below. (CARTO's dark tiles now demand an API key, so they are out.)
 */

export type BaseMapStyle = 'satellite' | 'dark' | 'terrain' | 'street'

interface TileDef {
  label: string
  url: string
  attribution: string
  maxZoom: number
  /** Optional labels/roads drawn over an imagery base. */
  overlay?: string
}

const TILES: Record<BaseMapStyle, TileDef> = {
  satellite: {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
    overlay: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
    maxZoom: 18,
  },
  dark: {
    label: 'Dark',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri',
    maxZoom: 16,
  },
  terrain: {
    label: 'Terrain',
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap, SRTM | &copy; OpenTopoMap (CC-BY-SA)',
    maxZoom: 17,
  },
  street: {
    label: 'Street',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  },
}

const STYLE_ORDER: BaseMapStyle[] = ['satellite', 'dark', 'terrain', 'street']

/** Keeps the viewport on the drawn geometry as it changes. */
function FitBounds({ bounds, padding = 28 }: { bounds: LatLngBoundsExpression | null; padding?: number }) {
  const map = useMap()
  useEffect(() => {
    if (!bounds) return
    map.fitBounds(bounds, { padding: [padding, padding] })
  }, [map, bounds, padding])
  return null
}

export function BaseMap({
  bounds,
  center,
  zoom = 11,
  height = 240,
  width,
  style = 'dark',
  interactive = false,
  attribution = true,
  switcher = true,
  padding,
  children,
}: {
  /** Fit the view to this geometry; takes precedence over center/zoom. */
  bounds?: LatLngBoundsExpression | null
  center?: LatLngExpression
  zoom?: number
  height?: number
  /** Constrain to a fixed width for square route thumbnails. */
  width?: number
  style?: BaseMapStyle
  /** Route thumbnails stay static; full-screen maps pan and zoom. */
  interactive?: boolean
  /** Small thumbnails hide the attribution chip to save space. */
  attribution?: boolean
  /** Show the Satellite/Dark/Terrain/Street picker (interactive maps only). */
  switcher?: boolean
  padding?: number
  children?: React.ReactNode
}) {
  const [active, setActive] = useState<BaseMapStyle>(style)
  const [pickerOpen, setPickerOpen] = useState(false)
  useEffect(() => setActive(style), [style])
  const tiles = TILES[active]

  return (
    <div className="relative overflow-hidden bg-[#1A1C1E]" style={{ height, width }}>
      <MapContainer
        center={center ?? [47.7, 11.3]}
        zoom={zoom}
        zoomControl={false}
        dragging={interactive}
        scrollWheelZoom={interactive}
        doubleClickZoom={interactive}
        touchZoom={interactive}
        keyboard={interactive}
        attributionControl={false}
        style={{ height: '100%', width: '100%', background: '#1A1C1E' }}
      >
        <TileLayer key={active} url={tiles.url} attribution={tiles.attribution} maxZoom={tiles.maxZoom} />
        {tiles.overlay ? <TileLayer key={`${active}-ovl`} url={tiles.overlay} maxZoom={tiles.maxZoom} /> : null}
        <FitBounds bounds={bounds ?? null} padding={padding} />
        {interactive ? <ZoomControl position="bottomleft" /> : null}
        {children}
      </MapContainer>

      {/* Collapsed to a single chip so it never collides with the status
          controls other maps place along the top edge on a phone. */}
      {switcher && interactive ? (
        <div className="absolute right-2 top-2 z-[400] flex flex-col items-end gap-1">
          <button
            type="button"
            aria-label="Basemap style"
            aria-expanded={pickerOpen}
            onClick={() => setPickerOpen((o) => !o)}
            className="flex items-center gap-1.5 rounded-control bg-void/85 px-2.5 py-1.5 font-mono text-[9px] uppercase tracking-[0.08em] text-bone backdrop-blur"
          >
            <Layers size={12} strokeWidth={1.9} />
            {tiles.label}
          </button>
          {pickerOpen ? (
            <div className="flex flex-col overflow-hidden rounded-control bg-void/90 backdrop-blur">
              {STYLE_ORDER.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    setActive(s)
                    setPickerOpen(false)
                  }}
                  className={`px-3 py-1.5 text-right font-mono text-[9px] uppercase tracking-[0.08em] ${active === s ? 'bg-accent text-white' : 'text-ash'}`}
                >
                  {TILES[s].label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {attribution ? (
        <div className="pointer-events-none absolute bottom-0 right-0 z-[400] bg-black/45 px-1.5 py-0.5 font-mono text-[7px] text-ash"
          dangerouslySetInnerHTML={{ __html: tiles.attribution }} />
      ) : null}
    </div>
  )
}
