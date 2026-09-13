import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { AlertTriangle, Info, OctagonX } from 'lucide-react'

export function Section({ title, icon: Icon, right, children, tone }: {
  title: string; icon?: LucideIcon; right?: ReactNode; children: ReactNode; tone?: 'red' | 'blue'
}) {
  const bar = tone === 'red' ? 'bg-mred' : tone === 'blue' ? 'bg-mlight' : 'bg-accent'
  return (
    <section className="hairline animate-rise border-b px-4 py-3.5">
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-ash">
          <span className={`h-3 w-[2px] rounded-full ${bar}`} />
          {Icon ? <Icon size={12} strokeWidth={2.2} className="text-dim" /> : null}
          {title}
        </h2>
        {right ? <div className="min-w-0 truncate text-right">{right}</div> : null}
      </div>
      {children}
    </section>
  )
}

export function Stat({ label, value, unit, tone, big }: {
  label: string; value: ReactNode; unit?: string; tone?: 'red' | 'blue' | 'mint'; big?: boolean
}) {
  const color = tone === 'red' ? 'text-mred' : tone === 'blue' ? 'text-mlight' : tone === 'mint' ? 'text-mint' : 'text-bone'
  return (
    <div className="hairline rounded-lg border bg-raised/40 px-2.5 py-2 shadow-card transition-colors hover:bg-raised/60">
      <div className="text-[10px] uppercase tracking-wider text-dim">{label}</div>
      <div className={`tabular font-mono leading-tight ${big ? 'text-[20px]' : 'text-[15px]'} ${color}`}>
        {value}{unit ? <span className="ml-0.5 text-[10px] font-normal text-dim">{unit}</span> : null}
      </div>
    </div>
  )
}

export function Chip({ active, onClick, children, color, disabled, title, size = 'md' }: {
  active?: boolean; onClick?: () => void; children: ReactNode; color?: string; disabled?: boolean; title?: string; size?: 'sm' | 'md'
}) {
  const pad = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-[12px]'
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={title}
      className={`rounded-full border font-medium transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-35 ${pad}
        ${active ? 'border-transparent text-void shadow-[0_2px_10px_-2px_rgba(28,105,212,0.6)]' : 'hairline bg-raised/40 text-bone hover:border-ash/60 hover:bg-raised/70'}`}
      style={active ? { background: color ?? '#6DB6E8' } : undefined}>
      {children}
    </button>
  )
}

export function Notice({ kind, children }: { kind: 'error' | 'warn' | 'info'; children: ReactNode }) {
  const cls = kind === 'error' ? 'border-mred/50 bg-mred/10 text-bone' : kind === 'warn' ? 'border-amber/50 bg-amber/10' : 'border-accent/50 bg-accent/10'
  const Icon = kind === 'error' ? OctagonX : kind === 'warn' ? AlertTriangle : Info
  const ic = kind === 'error' ? 'text-mred' : kind === 'warn' ? 'text-amber' : 'text-mlight'
  return (
    <div className={`animate-rise flex gap-2 rounded-lg border px-3 py-2 text-[12px] leading-snug ${cls}`}>
      <Icon size={14} className={`mt-0.5 shrink-0 ${ic}`} />
      <div className="min-w-0">{children}</div>
    </div>
  )
}

export function Verdict({ v }: { v: string }) {
  const cls = v === 'accepted' ? 'bg-mint/15 text-mint ring-mint/30'
    : v === 'failed' ? 'bg-mred/15 text-mred ring-mred/30'
    : v === 'rejected' ? 'bg-amber/10 text-amber ring-amber/30'
    : 'bg-raised text-ash ring-line'
  return <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1 ${cls}`}>{v.replace('_', ' ')}</span>
}

/** Thin horizontal bar, share in [0,1]. */
export function Bar({ share, color }: { share: number | null | undefined; color: string }) {
  const w = share == null || Number.isNaN(share) ? 0 : Math.max(0, Math.min(1, share)) * 100
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-line">
      <div className="h-full rounded-full transition-[width] duration-500 ease-out" style={{ width: `${w}%`, background: color }} />
    </div>
  )
}

export const fmt = (v: number | null | undefined, d = 1): string =>
  v == null || Number.isNaN(v) ? '—' : v.toFixed(d)
export const pct = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v) ? '—' : `${Math.round(v * 100)}%`
