import type { LatLng } from '../domain/types'

export interface MapMarker {
  id: string
  /** 0..1 position along the drawn path. */
  t: number
  label: string
  tone: 'accent' | 'bone' | 'warn' | 'alert'
}

const TONES: Record<MapMarker['tone'], string> = {
  accent: 'var(--accent)',
  bone: '#EEF3F8',
  warn: '#B8BBC1',
  alert: '#E1E2E5',
}

function project(path: LatLng[], w: number, h: number, pad = 18) {
  const lats = path.map((p) => p.lat)
  const lngs = path.map((p) => p.lng)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const minLng = Math.min(...lngs)
  const maxLng = Math.max(...lngs)
  const sx = (w - pad * 2) / Math.max(maxLng - minLng, 1e-6)
  const sy = (h - pad * 2) / Math.max(maxLat - minLat, 1e-6)
  const s = Math.min(sx, sy)
  const ox = pad + ((w - pad * 2) - (maxLng - minLng) * s) / 2
  const oy = pad + ((h - pad * 2) - (maxLat - minLat) * s) / 2
  return path.map((p) => ({
    x: ox + (p.lng - minLng) * s,
    y: h - (oy + (p.lat - minLat) * s),
  }))
}

export function RouteMap({
  path,
  markers = [],
  height = 240,
  width = 390,
  showStartEnd = true,
  attribution = true,
  active = false,
}: {
  path: LatLng[]
  markers?: MapMarker[]
  height?: number
  width?: number
  showStartEnd?: boolean
  attribution?: boolean
  active?: boolean
}) {
  if (!path.length) return <div className="flex items-center justify-center bg-bitumen p-5 text-caption text-ash" style={{ height }} role="status">Route preview unavailable</div>
  const w = width
  const pts = project(path, w, height, attribution ? 36 : 18)
  const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const at = (t: number) => pts[Math.min(pts.length - 1, Math.max(0, Math.round(t * (pts.length - 1))))]

  return (
    <div className="relative overflow-hidden bg-[#222426]" style={{ height }}>
      <svg
        viewBox={`0 0 ${w} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="absolute inset-0 h-full w-full"
        role="img"
        aria-label="Route overview"
      >
        {[0.2, 0.4, 0.6, 0.8].map((f) => (
          <line
            key={f}
            x1={0}
            y1={height * f}
            x2={w}
            y2={height * f}
            stroke="rgba(255,255,255,0.04)"
            strokeWidth={1}
          />
        ))}
        {attribution ? [0.2, 0.4, 0.6, 0.8].map((f) => <line key={`v-${f}`} x1={w * f} y1={0} x2={w * f} y2={height} stroke="rgba(255,255,255,0.025)" />) : null}
        <path d={d} fill="none" stroke="rgba(0,0,0,0.3)" strokeWidth={7} strokeLinejoin="round" />
        <path d={d} fill="none" stroke={active ? 'var(--accent-text)' : '#B9BCC1'} strokeWidth={2.2} strokeLinejoin="round" />
        {showStartEnd ? (
          <>
            {attribution ? [pts[0], pts[pts.length - 1]].map((p, i) => <text key={i} x={p.x + (p.x > w / 2 ? 12 : -12)} y={p.y + 4} fill="#B5B8BE" fontFamily="Inter, sans-serif" fontSize={10} textAnchor={p.x > w / 2 ? 'start' : 'end'}>{i === 0 ? 'A' : 'B'}</text>) : null}
            <circle cx={pts[0].x} cy={pts[0].y} r={5} fill="#EEF3F8" />
            <circle
              cx={pts[pts.length - 1].x}
              cy={pts[pts.length - 1].y}
              r={5}
              fill="none"
              stroke="#EEF3F8"
              strokeWidth={2}
            />
          </>
        ) : null}
        {markers.map((m) => {
          const p = at(m.t)
          return (
            <g key={m.id}>
              <title>{m.label}</title>
              <circle cx={p.x} cy={p.y} r={4.5} fill={TONES[m.tone]} stroke="#05080D" strokeWidth={1.5} />
            </g>
          )
        })}
      </svg>
      {attribution ? (
        <>
          <div className="pointer-events-none absolute left-4 top-3 font-mono text-[8px] text-ash">{path[0].lat.toFixed(2)}° N · {path[0].lng.toFixed(2)}° E</div>
          <div className="pointer-events-none absolute right-4 top-3 flex flex-col items-center gap-0.5 text-[9px] text-ash" aria-hidden="true"><span>↑</span>N</div>
          <div className="pointer-events-none absolute bottom-3 left-4 font-mono text-[8px] uppercase tracking-[0.12em] text-ash">Route overview</div>
        </>
      ) : null}
    </div>
  )
}
