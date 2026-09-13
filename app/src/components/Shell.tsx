import { Link, useLocation } from 'react-router-dom'
import { useRef, useEffect } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Compass, Gauge, Map, MoreHorizontal, Warehouse } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { VoiceAssistant } from './VoiceAssistant'

const TABS = [
  { to: '/', label: 'Ride', Icon: Gauge },
  { to: '/plan', label: 'Plan', Icon: Map },
  { to: '/discover', label: 'Discover', Icon: Compass },
  { to: '/garage', label: 'Garage', Icon: Warehouse },
  { to: '/more', label: 'More', Icon: MoreHorizontal },
]

function StatusBar() {
  const { online, engine } = useAppState()
  return <div className="flex shrink-0 items-center justify-between px-6 pb-1 pt-[max(20px,env(safe-area-inset-top))]">
    <span className="text-[9px] font-medium uppercase tracking-[0.2em] text-bone">BMW Motorrad</span>
    <span className="font-mono text-[8px] uppercase tracking-[0.12em] text-ash" title={online ? `Route engine: ${engine}` : 'Running on bundled data'}>
      {online ? `Live \u00b7 ${engine}` : 'Offline data'}
    </span>
  </div>
}

function TabBar() {
  const { pathname } = useLocation()
  return <nav aria-label="Main navigation" className="absolute inset-x-0 bottom-0 z-20 border-t border-white/[0.06] bg-[#1c1d20]/95 px-3 pb-[max(12px,env(safe-area-inset-bottom))] backdrop-blur-2xl">
    <div className="grid grid-cols-5">
      {TABS.map(({ to, label, Icon }) => {
        const active = to === '/' ? (pathname === '/' || pathname.startsWith('/ride/'))
          : to === '/plan' ? (pathname.startsWith('/plan') || pathname.startsWith('/thrill'))
          : to === '/more'
          ? ['/more', '/maps', '/group', '/handoff'].some((path) => pathname.startsWith(path))
          : pathname.startsWith(to)
        return <Link key={to} to={to} aria-current={active ? 'page' : undefined} className="nav-tab">
          <Icon size={21} strokeWidth={active ? 1.8 : 1.5} />
          <span className="text-[9px] font-medium tracking-normal">{label}</span>
        </Link>
      })}
    </div>
  </nav>
}

export function Shell({ children }: { children: ReactNode }) {
  const { bikeProfile } = useAppState()
  const { pathname } = useLocation()
  const main = useRef<HTMLElement>(null)
  useEffect(() => { main.current?.scrollTo({ top: 0 }) }, [pathname])
  const lightAccent = bikeProfile?.character === 'heritage' || bikeProfile?.character === 'urban_electric'
  const theme = {
    '--accent': bikeProfile?.accent ?? '#1C69D4',
    '--accent-contrast': lightAccent ? '#191a1c' : '#FFFFFF',
    '--accent-text': 'color-mix(in srgb, var(--accent) 65%, white)',
    '--accent-soft': 'color-mix(in srgb, var(--accent) 10%, transparent)',
  } as CSSProperties

  return <div className="flex min-h-dvh justify-center bg-[#121315] md:py-6" style={theme}>
    <div className="relative flex h-dvh w-full max-w-[420px] flex-col overflow-hidden bg-void md:h-[min(900px,calc(100dvh-48px))] md:rounded-[32px] md:border md:border-white/[0.08] md:shadow-[0_24px_80px_rgba(0,0,0,0.4)]">
      <StatusBar />
      <main ref={main} id="main-content" className="scroll-hide min-h-0 flex-1 overflow-y-auto overflow-x-hidden pb-[172px] scroll-pb-[172px] scroll-pt-4"><div key={pathname} className="screen-enter">{children}</div></main>
      <VoiceAssistant />
      <TabBar />
    </div>
  </div>
}
