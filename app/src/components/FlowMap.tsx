import type { FsRefusal, FsSegment } from '../domain/types'

/**
 * Map for FLOWSTATE results. Two jobs the normal RouteMap cannot do: colour a
 * route by how well each stretch fits the rider (flow), and show the roads the
 * safety gate refused outright as pins the rider can see rather than a silent
 * detour.
 *
 * Coordinates are the engine's own [lon, lat] pairs.
 */

export interface FlowLine {
  segments: FsSegment[]
  /** A dimmed comparison line drawn underneath, e.g. the Cruise route. */
  muted?: boolean
  label?: string
}

const flowColour = (flow: number) => {
  // low fit -> cold grey, high fit -> the bike's accent
  const t = Math.min(1, Math.max(0, flow))
  return `color-mix(in srgb, var(--accent) ${Math.round(t * 100)}%, #6C7075)`
}

export function FlowMap({
  lines,
  refusals = [],
  height = 220,
  width = 390,
}: {
  lines: FlowLine[]
  refusals?: FsRefusal[]
  height?: number
  width?: number
}) {
  const all = lines.flatMap((l) => l.segments.flatMap((s) => [s.from, s.to]))
  if (!all.length) {
    return (
      <div className="flex items-center justify-center bg-bitumen p-5 text-caption text-ash" style={{ height }} role="status">
        No route to draw
      </div>
    )
  }

  const lons = all.map((p) => p[0])
  const lats = all.map((p) => p[1])
  const minLon = Math.min(...lons, ...refusals.map((r) => r.lon))
  const maxLon = Math.max(...lons, ...refusals.map((r) => r.lon))
  const minLat = Math.min(...lats, ...refusals.map((r) => r.lat))
  const maxLat = Math.max(...lats, ...refusals.map((r) => r.lat))
  const pad = 26
  const s = Math.min(
    (width - pad * 2) / Math.max(maxLon - minLon, 1e-6),
    (height - pad * 2) / Math.max(maxLat - minLat, 1e-6),
  )
  const ox = pad + (width - pad * 2 - (maxLon - minLon) * s) / 2
  const oy = pad + (height - pad * 2 - (maxLat - minLat) * s) / 2
  const px = (lon: number) => ox + (lon - minLon) * s
  const py = (lat: number) => height - (oy + (lat - minLat) * s)

  const first = lines[lines.length - 1].segments[0]
  const last = lines[lines.length - 1].segments.slice(-1)[0]

  return (
    <div className="relative overflow-hidden bg-[#222426]" style={{ height }}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet"
        className="absolute inset-0 h-full w-full" role="img" aria-label="Fun-fit route">
        {[0.2, 0.4, 0.6, 0.8].map((f) => (
          <line key={f} x1={0} y1={height * f} x2={width} y2={height * f} stroke="rgba(255,255,255,0.04)" />
        ))}
        {lines.map((line, li) =>
          line.segments.map((seg, i) => (
            <line
              key={`${li}-${i}`}
              x1={px(seg.from[0])} y1={py(seg.from[1])}
              x2={px(seg.to[0])} y2={py(seg.to[1])}
              stroke={line.muted ? '#5A5E64' : flowColour(seg.flow)}
              strokeWidth={line.muted ? 1.8 : 3}
              strokeLinecap="round"
              strokeDasharray={line.muted ? '4 4' : undefined}
            />
          )),
        )}
        <circle cx={px(first.from[0])} cy={py(first.from[1])} r={5} fill="#EEF3F8" />
        <circle cx={px(last.to[0])} cy={py(last.to[1])} r={5} fill="none" stroke="#EEF3F8" strokeWidth={2} />
        {refusals.map((r, i) => (
          <g key={`${r.cell}-${i}`}>
            <title>{r.reason}</title>
            <circle cx={px(r.lon)} cy={py(r.lat)} r={6} fill="#E1252E" stroke="#05080D" strokeWidth={1.5} />
            <line x1={px(r.lon) - 2.5} y1={py(r.lat) - 2.5} x2={px(r.lon) + 2.5} y2={py(r.lat) + 2.5}
              stroke="#fff" strokeWidth={1.4} />
            <line x1={px(r.lon) + 2.5} y1={py(r.lat) - 2.5} x2={px(r.lon) - 2.5} y2={py(r.lat) + 2.5}
              stroke="#fff" strokeWidth={1.4} />
          </g>
        ))}
      </svg>
      <div className="pointer-events-none absolute bottom-3 left-4 flex items-center gap-3 font-mono text-[8px] uppercase tracking-[0.12em] text-ash">
        {lines.filter((l) => l.label).map((l) => (
          <span key={l.label} className="flex items-center gap-1.5">
            <span className="inline-block h-[2px] w-4 rounded-full"
              style={{ background: l.muted ? '#5A5E64' : 'var(--accent)' }} />
            {l.label}
          </span>
        ))}
      </div>
    </div>
  )
}
