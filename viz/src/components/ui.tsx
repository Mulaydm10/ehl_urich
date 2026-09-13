import type { ReactNode } from 'react'

export function Section({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="border-b border-raised/70 px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ash">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

export function Stat({ label, value, unit, tone }: { label: string; value: ReactNode; unit?: string; tone?: 'red' | 'blue' }) {
  return (
    <div className="rounded-md bg-raised/60 px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-ash">{label}</div>
      <div className={`font-mono text-[15px] leading-tight ${tone === 'red' ? 'text-mred' : tone === 'blue' ? 'text-mlight' : 'text-bone'}`}>
        {value}{unit ? <span className="ml-0.5 text-[10px] text-ash">{unit}</span> : null}
      </div>
    </div>
  )
}

export function Chip({ active, onClick, children, color, disabled, title }: {
  active?: boolean; onClick?: () => void; children: ReactNode; color?: string; disabled?: boolean; title?: string
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={title}
      className={`rounded-full border px-2.5 py-1 text-[12px] transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-40
        ${active ? 'border-transparent text-void' : 'border-raised bg-panel text-bone hover:border-ash'}`}
      style={active ? { background: color ?? '#1C69D4' } : undefined}>
      {children}
    </button>
  )
}

export function Notice({ kind, children }: { kind: 'error' | 'warn' | 'info'; children: ReactNode }) {
  const cls = kind === 'error' ? 'border-mred/60 bg-mred/10 text-bone' : kind === 'warn' ? 'border-[#F5A524]/60 bg-[#F5A524]/10' : 'border-accent/50 bg-accent/10'
  return <div className={`rounded-md border px-3 py-2 text-[12px] leading-snug ${cls}`}>{children}</div>
}

export const fmt = (v: number | null | undefined, d = 1): string =>
  v == null || Number.isNaN(v) ? '—' : v.toFixed(d)
export const pct = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v) ? '—' : `${Math.round(v * 100)}%`
