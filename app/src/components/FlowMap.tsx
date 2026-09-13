import { Polyline, CircleMarker, Tooltip } from 'react-leaflet'
import type { LatLngExpression, LatLngBoundsExpression } from 'leaflet'
import type { FsRefusal, FsSegment } from '../domain/types'
import { BaseMap, type BaseMapStyle } from './BaseMap'
import { useAccent, mixHex } from './useAccent'

/**
 * Map for FLOWSTATE results on a real OpenStreetMap basemap. Two jobs the plain
 * RouteMap cannot do: colour a route by how well each stretch fits the rider
 * (flow), and show the roads the safety gate refused outright as red pins the
 * rider can see rather than a silent detour.
 *
 * The engine hands back [lon, lat]; Leaflet wants [lat, lon].
 */

export interface FlowLine {
  segments: FsSegment[]
  /** A dimmed comparison line drawn underneath, e.g. the Cruise route. */
  muted?: boolean
  label?: string
}

export function FlowMap({
  lines,
  refusals = [],
  height = 220,
  style = 'terrain',
  interactive = false,
}: {
  lines: FlowLine[]
  refusals?: FsRefusal[]
  height?: number
  width?: number
  style?: BaseMapStyle
  interactive?: boolean
}) {
  const accent = useAccent()
  const all = lines.flatMap((l) => l.segments.flatMap((s) => [s.from, s.to]))
  if (!all.length) {
    return (
      <div className="flex items-center justify-center bg-bitumen p-5 text-caption text-ash" style={{ height }} role="status">
        No route to draw
      </div>
    )
  }

  // low fit -> cold grey, high fit -> the bike's accent
  const flowColour = (flow: number) => mixHex('#6C7075', accent, flow)

  const pts: LatLngExpression[] = [
    ...all.map((p) => [p[1], p[0]] as LatLngExpression),
    ...refusals.map((r) => [r.lat, r.lon] as LatLngExpression),
  ]
  const bounds = pts as LatLngBoundsExpression

  const main = lines.filter((l) => l.segments.length).slice(-1)[0]
  const first = main.segments[0]
  const last = main.segments.slice(-1)[0]

  const legend = lines.filter((l) => l.label)

  return (
    <div className="relative">
    <BaseMap bounds={bounds} height={height} style={style} interactive={interactive}>
      {lines.map((line, li) =>
        line.segments.map((seg, i) => (
          <Polyline
            key={`${li}-${i}`}
            positions={[
              [seg.from[1], seg.from[0]],
              [seg.to[1], seg.to[0]],
            ]}
            pathOptions={{
              color: line.muted ? '#5A5E64' : flowColour(seg.flow),
              weight: line.muted ? 2.2 : 4,
              opacity: line.muted ? 0.7 : 1,
              dashArray: line.muted ? '4 5' : undefined,
              lineCap: 'round',
            }}
          />
        )),
      )}
      <CircleMarker center={[first.from[1], first.from[0]]} radius={6}
        pathOptions={{ color: '#05080D', weight: 2, fillColor: '#EEF3F8', fillOpacity: 1 }}>
        <Tooltip>Start</Tooltip>
      </CircleMarker>
      <CircleMarker center={[last.to[1], last.to[0]]} radius={6}
        pathOptions={{ color: '#EEF3F8', weight: 2, fillColor: '#1A1C1E', fillOpacity: 1 }}>
        <Tooltip>Finish</Tooltip>
      </CircleMarker>
      {refusals.map((r, i) => (
        <CircleMarker key={`${r.cell}-${i}`} center={[r.lat, r.lon]} radius={7}
          pathOptions={{ color: '#05080D', weight: 1.5, fillColor: '#E1252E', fillOpacity: 1 }}>
          <Tooltip>{r.reason}</Tooltip>
        </CircleMarker>
      ))}
    </BaseMap>
    {legend.length ? (
      <div className="pointer-events-none absolute left-2 top-2 z-[400] flex items-center gap-3 rounded bg-black/55 px-2 py-1 font-mono text-[8px] uppercase tracking-[0.12em] text-bone">
        {legend.map((l) => (
          <span key={l.label} className="flex items-center gap-1.5">
            <span className="inline-block h-[2px] w-4 rounded-full"
              style={{ background: l.muted ? '#5A5E64' : accent }} />
            {l.label}
          </span>
        ))}
      </div>
    ) : null}
    </div>
  )
}
