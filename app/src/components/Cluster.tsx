/** Instrument-cluster primitives: arc gauges, segmented bars, lean arc, telemetry rows. */

export function ArcGauge({
  value,
  max,
  label,
  unit,
  redlineFrom,
  warning = false,
  size = 168,
}: {
  /** `null` renders an explicit no-data cluster instead of a zero reading. */
  value: number | null
  max: number
  label: string
  unit: string
  redlineFrom?: number
  warning?: boolean
  size?: number
}) {
  const r = size / 2 - 14
  const cx = size / 2
  const cy = size / 2
  const start = 225
  const sweep = 270
  const polar = (deg: number, radius: number) => {
    const a = ((deg - 90) * Math.PI) / 180
    return { x: cx + radius * Math.cos(a), y: cy + radius * Math.sin(a) }
  }
  const arc = (from: number, to: number, radius: number) => {
    const p1 = polar(from, radius)
    const p2 = polar(to, radius)
    const large = to - from > 180 ? 1 : 0
    return `M${p1.x} ${p1.y} A${radius} ${radius} 0 ${large} 1 ${p2.x} ${p2.y}`
  }
  const ratio = value === null ? 0 : Math.min(1, Math.max(0, value / max))
  const ticks = Array.from({ length: 21 }, (_, i) => i / 20)
  const needleTip = polar(start + sweep * ratio, r - 6)
  const needleTail = polar(start + sweep * ratio, r - 26)

  return (
    <div className="relative aspect-square max-w-full shrink-0" style={{ width: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="h-full w-full" aria-hidden="true">
        <path d={arc(start, start + sweep, r)} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={5} />
        {redlineFrom !== undefined && value !== null ? (
          <path
            d={arc(start + sweep * (redlineFrom / max), start + sweep, r)}
            fill="none"
            stroke="rgba(231,34,46,0.5)"
            strokeWidth={5}
          />
        ) : null}
        {value === null ? null : (
          <path
            d={arc(start, start + sweep * Math.max(ratio, 0.001), r)}
            fill="none"
            stroke={warning ? '#FFB020' : 'var(--accent)'}
            strokeWidth={5}
          />
        )}
        {ticks.map((t, i) => {
          const outer = polar(start + sweep * t, r - 9)
          const inner = polar(start + sweep * t, r - (i % 5 === 0 ? 20 : 14))
          return (
            <line
              key={t}
              x1={outer.x}
              y1={outer.y}
              x2={inner.x}
              y2={inner.y}
              stroke={i % 5 === 0 ? 'rgba(238,243,248,0.7)' : 'rgba(238,243,248,0.22)'}
              strokeWidth={i % 5 === 0 ? 1.6 : 1}
            />
          )
        })}
        {value !== null ? <g><text x={24} y={size - 6} fill="#A1A4AB" fontFamily="Inter, sans-serif" fontSize={9}>0</text>
        <text x={size - 24} y={size - 6} textAnchor="end" fill="#A1A4AB" fontFamily="Inter, sans-serif" fontSize={9}>{max}</text></g> : null}
        {value === null ? null : (
          <line
            x1={needleTail.x}
            y1={needleTail.y}
            x2={needleTip.x}
            y2={needleTip.y}
            stroke="#F5F5F7"
            strokeWidth={2}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 pb-2">
        <span className="readout text-[52px]">{value === null ? '--' : Math.round(value)}</span>
        <span className="unit">{unit}</span>
      </div>
      <span className="label absolute inset-x-0 bottom-0 text-center">{label}</span>
    </div>
  )
}

export function SegmentBar({ ratio, segments = 20, tone }: { ratio: number | null; segments?: number; tone?: string }) {
  const filled = ratio === null ? 0 : Math.round(ratio * segments)
  return (
    <span className="flex gap-[2px]" aria-hidden="true">
      {Array.from({ length: segments }, (_, i) => (
        <span
          key={i}
          className="h-1.5 min-w-0 flex-1 rounded-[1px]"
          style={{
            background:
              ratio === null
                ? 'rgba(255,255,255,0.06)'
                : i < filled
                  ? (tone ?? 'var(--accent)')
                  : 'rgba(255,255,255,0.09)',
          }}
        />
      ))}
    </span>
  )
}

export function LeanArc({ left, right, size = 150 }: { left: number; right: number; size?: number }) {
  const cx = size / 2
  const cy = size * 0.72
  const r = size * 0.42
  const polar = (deg: number, radius = r) => {
    const a = ((deg - 180) * Math.PI) / 180
    return { x: cx + radius * Math.cos(a), y: cy + radius * Math.sin(a) }
  }
  const arcPath = (from: number, to: number) => {
    const p1 = polar(from)
    const p2 = polar(to)
    return `M${p1.x} ${p1.y} A${r} ${r} 0 0 1 ${p2.x} ${p2.y}`
  }
  const leftDeg = 90 - Math.min(60, left) * 1.5
  const rightDeg = 90 + Math.min(60, right) * 1.5

  return (
    <div className="relative shrink-0" style={{ width: size, height: size * 0.78 }}>
      <svg width={size} height={size * 0.78}>
        <path d={arcPath(0, 180)} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={5} />
        <path d={arcPath(leftDeg, 90)} fill="none" stroke="#B8BBC1" strokeWidth={3} />
        <path d={arcPath(90, rightDeg)} fill="none" stroke="#B8BBC1" strokeWidth={3} />
        {[0, 15, 30, 45, 60].flatMap((deg) =>
          [90 - deg * 1.5, 90 + deg * 1.5].map((d, side) => {
            const o = polar(d, r + 6)
            const i2 = polar(d, r - 2)
            return (
              <line
                key={`${deg}-${d}-${side}`}
                x1={o.x}
                y1={o.y}
                x2={i2.x}
                y2={i2.y}
                stroke="rgba(238,243,248,0.4)"
                strokeWidth={1}
              />
            )
          }),
        )}
        <line x1={cx} y1={cy} x2={polar(leftDeg, r - 12).x} y2={polar(leftDeg, r - 12).y} stroke="#F5F5F7" strokeWidth={2} />
        <line
          x1={cx}
          y1={cy}
          x2={polar(rightDeg, r - 12).x}
          y2={polar(rightDeg, r - 12).y}
          stroke="#F5F5F7"
          strokeWidth={2}
        />
      </svg>
      <div className="absolute inset-x-0 bottom-0 flex justify-between px-2 text-[12px] font-semibold text-bone">
        <span>
          {left}
          <span className="text-ash">° L</span>
        </span>
        <span>
          {right}
          <span className="text-ash">° R</span>
        </span>
      </div>
    </div>
  )
}

export function TelemetryRow({ items }: { items: { label: string; value: string; unit?: string; text?: boolean }[] }) {
  return (
    <div className="telemetry-row" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
      {items.map((it) => (
        <div key={it.label} className="telemetry-cell">
          <div className="label">{it.label}</div>
          <div className={`telemetry-value ${it.value.includes(" / ") ? "block" : ""}`}>
            <span className={it.text ? 'text-[13px] font-medium leading-snug' : `readout ${it.value.includes(" / ") ? "telemetry-pair" : "text-[30px]"} ${it.value === '--' ? 'text-ash' : ''}`}>{it.value}</span>
            {it.unit ? <span className="unit">{it.unit}</span> : null}
          </div>
        </div>
      ))}
    </div>
  )
}

export function StatusLed({ on, tone = 'ok', children }: { on: boolean; tone?: 'ok' | 'warn' | 'alert'; children: string }) {
  const color = tone === 'ok' ? 'var(--accent-text)' : '#999BA1'
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-[11px] font-medium text-ash">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: on ? color : 'rgba(255,255,255,0.25)' }} />
      {children}
    </span>
  )
}
