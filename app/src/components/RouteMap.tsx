import { Polyline, CircleMarker, Tooltip } from 'react-leaflet'
import type { LatLngBoundsExpression, LatLngExpression } from 'leaflet'
import type { LatLng } from '../domain/types'
import { BaseMap, type BaseMapStyle } from './BaseMap'
import { useAccent } from './useAccent'

export interface MapMarker {
  id: string
  /** 0..1 position along the drawn path. */
  t: number
  label: string
  tone: 'accent' | 'bone' | 'warn' | 'alert'
}

/**
 * Route overview on a real OpenStreetMap basemap (see BaseMap for the keyless
 * tile providers). The path arrives as {lat,lng}; Leaflet wants [lat,lng].
 */
export function RouteMap({
  path,
  markers = [],
  height = 240,
  width,
  showStartEnd = true,
  attribution = true,
  active = false,
  style = 'dark',
  interactive = false,
}: {
  path: LatLng[]
  markers?: MapMarker[]
  height?: number
  width?: number
  showStartEnd?: boolean
  attribution?: boolean
  active?: boolean
  style?: BaseMapStyle
  interactive?: boolean
}) {
  const accent = useAccent()
  const tones: Record<MapMarker['tone'], string> = {
    accent,
    bone: '#EEF3F8',
    warn: '#F2B04A',
    alert: '#E1252E',
  }
  if (!path.length)
    return (
      <div className="flex items-center justify-center bg-bitumen p-5 text-caption text-ash" style={{ height, width }} role="status">
        Route preview unavailable
      </div>
    )

  const line: LatLngExpression[] = path.map((p) => [p.lat, p.lng])
  const bounds = line as LatLngBoundsExpression
  const at = (t: number) => path[Math.min(path.length - 1, Math.max(0, Math.round(t * (path.length - 1))))]
  const start = path[0]
  const end = path[path.length - 1]

  const map = (
    <BaseMap bounds={bounds} height={height} width={width} style={style} interactive={interactive} attribution={attribution}>
      <Polyline positions={line} pathOptions={{ color: '#05080D', weight: 7, opacity: 0.35 }} />
      <Polyline positions={line} pathOptions={{ color: active ? accent : '#DCA0FF', weight: 3.4 }} />
      {showStartEnd ? (
        <>
          <CircleMarker center={[start.lat, start.lng]} radius={6}
            pathOptions={{ color: '#05080D', weight: 2, fillColor: '#EEF3F8', fillOpacity: 1 }}>
            <Tooltip>Start</Tooltip>
          </CircleMarker>
          <CircleMarker center={[end.lat, end.lng]} radius={6}
            pathOptions={{ color: '#EEF3F8', weight: 2, fillColor: '#1A1C1E', fillOpacity: 1 }}>
            <Tooltip>Finish</Tooltip>
          </CircleMarker>
        </>
      ) : null}
      {markers.map((m) => {
        const p = at(m.t)
        return (
          <CircleMarker key={m.id} center={[p.lat, p.lng]} radius={5}
            pathOptions={{ color: '#05080D', weight: 1.5, fillColor: tones[m.tone], fillOpacity: 1 }}>
            <Tooltip>{m.label}</Tooltip>
          </CircleMarker>
        )
      })}
    </BaseMap>
  )

  return map
}
