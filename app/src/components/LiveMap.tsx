import { useEffect, useState } from 'react'
import { CircleMarker, Polyline, Tooltip, useMap } from 'react-leaflet'
import type { LatLngBoundsExpression, LatLngExpression } from 'leaflet'
import { BaseMap, type BaseMapStyle } from './BaseMap'
import { useAccent } from './useAccent'
import { useLivePosition, type LivePosition } from './useLivePosition'
import type { LatLng } from '../domain/types'

/**
 * Where the rider actually is, on real map tiles. Position comes from the
 * device GPS (keyless), the basemap from OpenStreetMap (keyless), so this works
 * on the phone without any map account. An optional route is drawn underneath
 * so the rider can see themselves against the plan.
 */

function Recenter({ position, follow }: { position: LivePosition | null; follow: boolean }) {
  const map = useMap()
  useEffect(() => {
    if (!position || !follow) return
    map.setView([position.lat, position.lng], Math.max(map.getZoom(), 14), { animate: true })
  }, [map, position, follow])
  return null
}

const STATE_NOTE = {
  idle: 'Location off',
  locating: 'Finding you…',
  tracking: 'Live',
  denied: 'Location permission denied',
  unsupported: 'Location unavailable on this device',
} as const

export function LiveMap({
  route = [],
  height = 260,
  style = 'dark',
  enabled = true,
}: {
  route?: LatLng[]
  height?: number
  style?: BaseMapStyle
  enabled?: boolean
}) {
  const accent = useAccent()
  const [follow, setFollow] = useState(true)
  const { state, position } = useLivePosition(enabled)

  const line: LatLngExpression[] = route.map((p) => [p.lat, p.lng])
  const bounds: LatLngBoundsExpression | null = !position && line.length ? (line as LatLngBoundsExpression) : null

  return (
    <div className="relative">
      <BaseMap bounds={bounds} height={height} style={style} interactive
        center={position ? [position.lat, position.lng] : undefined} zoom={position ? 14 : 11}>
        {line.length ? (
          <>
            <Polyline positions={line} pathOptions={{ color: '#05080D', weight: 7, opacity: 0.35 }} />
            <Polyline positions={line} pathOptions={{ color: '#DCA0FF', weight: 3, opacity: 0.9 }} />
          </>
        ) : null}
        {position ? (
          <>
            <CircleMarker center={[position.lat, position.lng]} radius={Math.max(10, Math.min(40, position.accuracy / 4))}
              pathOptions={{ stroke: false, fillColor: accent, fillOpacity: 0.14 }} />
            <CircleMarker center={[position.lat, position.lng]} radius={7}
              pathOptions={{ color: '#FFFFFF', weight: 2, fillColor: accent, fillOpacity: 1 }}>
              <Tooltip>±{Math.round(position.accuracy)} m</Tooltip>
            </CircleMarker>
          </>
        ) : null}
        <Recenter position={position} follow={follow} />
      </BaseMap>

      <div className="absolute left-2 top-2 z-[400] flex flex-wrap items-center gap-1.5">
        <span className="status-pill" data-live={state === 'tracking'}>{STATE_NOTE[state]}</span>
        {position?.speedKmh != null ? (
          <span className="rounded-control bg-void/85 px-2.5 py-1 font-mono text-[11px] text-bone">
            {Math.round(position.speedKmh)} km/h
          </span>
        ) : null}
        {position ? (
          <button type="button" onClick={() => setFollow((f) => !f)}
            className="rounded-control bg-void/85 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-bone">
            {follow ? 'Following' : 'Recentre'}
          </button>
        ) : null}
      </div>
    </div>
  )
}
