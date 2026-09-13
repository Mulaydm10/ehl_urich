import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, HardDrive, Monitor, Users } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { EmptyState, GhostButton, SectionTitle } from '../components/primitives'
import { getBackendUrl, setBackendUrl } from '../services/http'

const LINKS = [
  { to: '/group', label: 'Group ride', note: 'Riders, route and regroup point', Icon: Users },
  { to: '/handoff', label: 'Send to bike', note: 'Navigator, TFT or phone', Icon: Monitor },
  { to: '/maps', label: 'Offline maps', note: 'Your downloaded regions', Icon: HardDrive },
]

export function MoreScreen() {
  const { rider, rides, bike, online, engine, retryLoading } = useAppState()
  const [backendUrl, setUrl] = useState(getBackendUrl)
  const [saved, setSaved] = useState(false)
  if (!rider || !bike) return null
  const bikeRides = rides.filter((ride) => ride.bikeId === bike.id)

  const applyBackend = () => {
    setBackendUrl(backendUrl)
    setSaved(true)
    retryLoading()
  }

  return (
    <div className="pb-8">
      <header className="page-header">
        <div className="flex items-center justify-between"><div><p className="label">Your BMW Motorrad</p><h1 className="page-title">{rider.displayName}</h1></div><span className="flex h-14 w-14 items-center justify-center rounded-full bg-raised text-[22px] font-light text-ash" aria-hidden="true">{rider.displayName.slice(0, 1)}</span></div>
        <p className="caption mt-4">{rider.homeDealer}<br />Member since {rider.memberSince}</p>
      </header>
      <div className="data-list mx-6">
        {LINKS.map(({ to, label, note, Icon }) => (
          <Link key={to} to={to} className="list-link">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-raised"><Icon size={20} strokeWidth={1.5} /></span>
            <div className="min-w-0 flex-1"><h2 className="text-[16px] font-medium">{label}</h2><p className="caption mt-1">{note}</p></div>
            <ChevronRight size={16} className="shrink-0 text-ash" />
          </Link>
        ))}
      </div>

      <SectionTitle title="Ride history" subtitle={bike.model} action={<span className="caption">{bikeRides.length} {bikeRides.length === 1 ? 'ride' : 'rides'}</span>} />
      <div className="data-list mx-6">
        {bikeRides.map((r) => (
          <Link key={r.id} to={`/ride/${r.id}`} className="list-link">
            <div className="min-w-0 flex-1"><p className="caption">{r.date}</p><h3 className="mt-1 text-[15px] font-medium">{r.title}</h3></div>
            <div className="readout shrink-0 text-[28px]">{r.distanceKm}<span className="unit ml-1">km</span></div>
            <ChevronRight size={15} className="shrink-0 text-ash" />
          </Link>
        ))}
      </div>

      {!bikeRides.length ? <div className="mx-6"><EmptyState title="No rides recorded">Your {bike.model} ride history will appear here.</EmptyState></div> : null}

      <SectionTitle title="Preferences" subtitle="Your current setup" />
      <div className="data-list mx-6">
        {[
          ['Units', 'Metric · km, bar, °C'],
          ['BMW Cloud sync', 'Routes and rides · on'],
          ['Ride recording', bike.connection === 'phone_only' ? 'Automatic start unavailable' : 'Automatic on bike start'],
          ['Curvature default', 'Matched to selected BMW'],
          ['Account', 'BMW ID'],
        ].map(([k, v]) => <div key={k} className="grid grid-cols-[1fr_1.15fr] items-baseline gap-4 py-4"><span className="text-[13px] font-medium">{k}</span><span className="caption text-right">{v}</span></div>)}
      </div>

      <SectionTitle title="Backend" subtitle={online ? `Connected · ${engine}` : 'Not reachable · bundled data'} />
      <div className="mx-6 rounded-3xl bg-raised p-5">
        <label htmlFor="backend-url" className="caption">Server address</label>
        <input
          id="backend-url"
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          value={backendUrl}
          onChange={(e) => { setUrl(e.target.value); setSaved(false) }}
          placeholder="http://100.x.y.z:8090"
          className="mt-2 w-full rounded-2xl bg-black/40 px-4 py-3 font-mono text-[13px] text-bone outline-none ring-1 ring-white/10 focus:ring-accent"
        />
        <p className="caption mt-3">Point the app at the machine running the FLOWSTATE + BMW server, e.g. your Mac over Tailscale. Leave empty to use the address this build shipped with.</p>
        <div className="mt-4 flex items-center gap-3">
          <GhostButton onClick={applyBackend}>Connect</GhostButton>
          {saved ? <span className="caption">{online ? `Connected · ${engine}` : 'Still not reachable'}</span> : null}
        </div>
      </div>
    </div>
  )
}
