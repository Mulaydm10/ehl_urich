export function CurvinessGauge({ score, size = 96 }: { score: number; size?: number }) {
  const r = size / 2 - 6
  const c = 2 * Math.PI * r
  const sweep = 0.78
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-[140deg]">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="rgba(255,255,255,0.09)"
          strokeWidth={3}
          strokeDasharray={`${c * sweep} ${c}`}
          strokeLinecap="butt"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={3}
          strokeDasharray={`${c * sweep * (score / 100)} ${c}`}
          strokeLinecap="butt"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="readout text-[30px]">{score}</span>
        <span className="text-[9px] font-medium uppercase tracking-[0.04em] text-ash">curviness</span>
      </div>
    </div>
  )
}
