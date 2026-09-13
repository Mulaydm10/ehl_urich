import { useEffect, useRef } from 'react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { AlertCircle, Check, ChevronLeft, LoaderCircle } from 'lucide-react'
import { Link } from 'react-router-dom'

export function PageHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <header className="page-header">
      <div className="label">{eyebrow}</div>
      <h1 className="page-title">{title}</h1>
      {children ? <div className="caption mt-3">{children}</div> : null}
    </header>
  )
}

export function BackHeader({ to, title, detail }: { to: string; title: string; detail?: ReactNode }) {
  return (
    <header className="back-header">
      <Link to={to} className="icon-button" aria-label="Back">
        <ChevronLeft size={21} />
      </Link>
      <div className="min-w-0 py-3">
        <h1 className="text-[22px] font-medium leading-tight tracking-[-0.025em]">{title}</h1>
        {detail ? <div className="caption mt-1">{detail}</div> : null}
      </div>
    </header>
  )
}

/** Switch between the two planners: classic curvature routing and FLOWSTATE fun-fit. */
export function PlannerSwitch({ current }: { current: 'plan' | 'thrill' }) {
  const tabs: { to: string; key: 'plan' | 'thrill'; label: string }[] = [
    { to: '/plan', key: 'plan', label: 'Route' },
    { to: '/thrill', key: 'thrill', label: 'Fun-fit' },
  ]
  return (
    <div className="mx-6 mb-1 grid grid-cols-2 gap-1 rounded-full bg-white/[0.05] p-1">
      {tabs.map((t) => (
        <Link key={t.key} to={t.to} aria-current={t.key === current ? 'page' : undefined}
          className={`rounded-full py-2 text-center text-[12px] font-medium transition-colors ${
            t.key === current ? 'bg-white/[0.1] text-bone' : 'text-ash'
          }`}>
          {t.label}
        </Link>
      ))}
    </div>
  )
}

export function SectionTitle({ title, action, subtitle }: { title: string; action?: ReactNode; subtitle?: string }) {
  return (
    <div className="section-title">
      <div className="min-w-0">
        <h2>{title}</h2>
        {subtitle ? <p className="caption mt-1.5">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  )
}

export function Readout({ value, unit, size = 'md' }: { value: string; unit?: string; size?: 'sm' | 'md' | 'lg' }) {
  const cls = { sm: 'text-[24px]', md: 'text-[36px]', lg: 'text-[56px]' }[size]
  return (
    <div className="flex items-baseline gap-1.5">
      <span className={`readout ${cls}`}>{value}</span>
      {unit ? <span className="unit">{unit}</span> : null}
    </div>
  )
}

export function Bar({ ratio, tone = 'accent' }: { ratio: number; tone?: 'accent' | 'warn' | 'alert' }) {
  const bg = tone === 'accent' ? 'var(--accent)' : tone === 'warn' ? '#C6C7CB' : '#E1E2E5'
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-white/[0.1]">
      <div className="h-full w-full origin-left rounded-full transition-transform duration-200 ease-out"
        style={{ transform: `scaleX(${Math.min(1, Math.max(0, ratio))})`, background: bg }} />
    </div>
  )
}

export function Chip({ active, onClick, children, disabled = false }: { active: boolean; onClick: () => void; children: ReactNode; disabled?: boolean }) {
  return <button type="button" onClick={onClick} disabled={disabled} aria-pressed={active} data-active={active} className="chip">{active ? <Check size={12} strokeWidth={2} aria-hidden="true" /> : null}{children}</button>
}

type ActionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean; compact?: boolean }

function ActionButton({ children, busy = false, compact = false, disabled, className = '', variant, ...props }:
  ActionButtonProps & { variant: 'primary' | 'secondary' }) {
  return (
    <button {...props} type="button" disabled={disabled || busy} aria-busy={busy || undefined}
      className={`button button-${variant} ${compact ? 'button-compact' : ''} ${className}`}>
      {busy ? <LoaderCircle size={16} className="shrink-0 loading-pulse" aria-hidden="true" /> : null}
      {children}
    </button>
  )
}

export function PrimaryButton(props: ActionButtonProps) { return <ActionButton {...props} variant="primary" /> }
export function GhostButton(props: ActionButtonProps) { return <ActionButton {...props} variant="secondary" /> }

export function Unavailable({ note }: { note: string }) {
  return (
    <div className="notice flex items-center gap-3 bg-bitumen">
      <span className="readout shrink-0 text-[24px] text-ash">--</span>
      <span className="caption">{note}</span>
    </div>
  )
}

export function Feedback({ tone = 'info', children }: { tone?: 'info' | 'success' | 'error'; children: ReactNode }) {
  const element = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const node = element.current
    const main = node?.closest('main')
    if (node && main) {
      const bounds = node.getBoundingClientRect()
      const viewport = main.getBoundingClientRect()
      const tabs = main.parentElement?.querySelector('nav[aria-label="Main navigation"]')
      const visibleBottom = viewport.bottom - (tabs?.getBoundingClientRect().height ?? 0)
      if (bounds.bottom > visibleBottom || bounds.top < viewport.top) node.scrollIntoView({ block: 'nearest', behavior: 'instant' })
    }
  }, [])
  return <div ref={element} className="feedback" data-tone={tone} role={tone === 'error' ? 'alert' : 'status'}>
    {tone === 'error' ? <AlertCircle size={17} className="mt-0.5 shrink-0 text-alert" /> : <Check size={17} className="mt-0.5 shrink-0 text-accent-text" />}
    <div className="min-w-0">{children}</div>
  </div>
}

export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="empty-state" role="status">
    <div className="readout mb-4 text-[36px] text-ash">--</div>
    <h2 className="text-[17px] font-medium tracking-[-0.02em]">{title}</h2>
    <p className="caption mt-2">{children}</p>
    {action ? <div className="mt-4">{action}</div> : null}
  </div>
}
