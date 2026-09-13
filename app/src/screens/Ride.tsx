import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowUpRight, BatteryMedium, Bluetooth, ChevronDown, ChevronRight, Fuel, Gauge, Map, Route, Send, SlidersHorizontal, Users, Wrench } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { BikeImage } from '../components/BikeImage'
import { EmptyState, SectionTitle, Unavailable } from '../components/primitives'
import { RouteMap } from '../components/RouteMap'
import { LiveMap } from '../components/LiveMap'
import { Telemetry } from '../components/Telemetry'
import { CopilotCard } from '../components/CopilotCard'

const CONNECTION_LABEL = { connected: 'Connected', last_seen: 'Last seen', phone_only: 'Phone only' } as const
const ACTIONS = [
  { to: '/plan', label: 'Plan', Icon: Route },
  { to: '/handoff', label: 'Handoff', Icon: Send },
  { to: '/group', label: 'Group', Icon: Users },
  { to: '/maps', label: 'Maps', Icon: Map },
]

export function RideScreen() {
  const { bike, bikeProfile, rides, routes, stats, rider } = useAppState()
  if (!bike || !bikeProfile || !stats) return null
  const lastRide = rides.find((r) => r.bikeId === bike.id)
  const matched = routes.filter((r) => r.mode === bikeProfile.suggestedMode)
  const suggested = [...matched, ...routes.filter((r) => !matched.includes(r))].slice(0, 3)
  const energy = bike.fuelPercent
  const lowFuel = energy !== null && energy < 35
  const EnergyIcon = bikeProfile.character === 'urban_electric' ? BatteryMedium : Fuel

  return <div className="pb-8">
    <section aria-label="Your motorcycle">
      <header className="flex items-center justify-between px-6 pb-1 pt-6">
        <div>
          <Link to="/garage" className="inline-flex items-center gap-3 rounded-control">
            <h1 className="text-[28px] font-medium leading-tight tracking-[-0.045em]">{bike.model}</h1>
            <ChevronDown size={15} className="text-ash" />
          </Link>
          <p className="caption mt-1.5">{bike.variant}</p>
        </div>
        <Link to="/more" className="icon-button h-9 w-9 bg-transparent" aria-label="Rider profile"><span className="flex h-8 w-8 items-center justify-center rounded-full border border-white/20 font-mono text-[10px] text-ash">{rider?.displayName.slice(0, 1) ?? 'R'}</span></Link>
      </header>
      <div className="vehicle-hero"><BikeImage bike={bike} priority /></div>
      <div className="pt-3 text-center">
        <div className="hero-range"><span className="readout">{bike.rangeKm ?? '--'}</span><span className="text-[18px] font-light text-ash">km</span></div>
        <p className="label mt-1.5">{bike.connection === 'phone_only' ? 'Range unavailable' : 'Estimated range'}</p>
      </div>
      <div className="mt-5 flex items-center justify-center gap-1.5 px-4" aria-label="Motorcycle status">
        <span className="status-pill" data-live={bike.connection === 'connected'}><Bluetooth size={11} />{CONNECTION_LABEL[bike.connection]}</span>
        <span className="status-pill" aria-label={`${bikeProfile.energyLabel}: ${energy ?? '--'} percent`}><EnergyIcon size={11} />{energy ?? '--'}%</span>
        <Link to="/garage" className="status-pill" aria-label={`Next service: ${bike.serviceDueKm ?? '--'} km`}><Wrench size={11} />{bike.serviceDueKm?.toLocaleString('en-GB') ?? '--'} km</Link>
      </div>
      <nav className="quick-actions" aria-label="Quick actions">
        {ACTIONS.map(({ to, label, Icon }) => <Link to={to} key={to} className="quick-action"><span className="action-orb"><Icon size={22} strokeWidth={1.5} /></span><span>{label}</span></Link>)}
      </nav>
    </section>

    <section className="panel mx-6 overflow-hidden" aria-label="Motorcycle controls">
      <Link to="/garage" className="control-row"><Gauge size={21} strokeWidth={1.5} /><div><h2>Vehicle status</h2><p>{bike.connection === 'phone_only' ? 'Live data unavailable' : `${bike.lastSeen} · ${bike.odometerKm?.toLocaleString('en-GB') ?? '--'} km`}</p></div><ChevronRight size={15} /></Link>
      <details className="group">
        <summary className="control-row list-none border-t border-white/[0.065]"><SlidersHorizontal size={21} strokeWidth={1.5} /><div className="flex-1"><h2>Ride modes</h2><p>{bikeProfile.rideModes.join(' · ')}</p></div><ChevronDown size={15} className="group-open:rotate-180" /></summary>
        <p className="caption px-5 pb-5">Available on your {bike.model}. Select your riding mode on the motorcycle.</p>
      </details>
    </section>

    <div className="space-y-3 px-6">
      {bike.recall ? <div className="notice mt-5 flex items-start gap-3"><AlertTriangle size={17} className="mt-0.5 shrink-0" /><div><div className="font-medium">Recall notice</div><p className="mt-1 text-ash">{bike.recall}</p></div></div> : null}
      {lowFuel ? <div className="notice mt-5 flex items-center gap-3"><Fuel size={17} className="shrink-0" /><p>Low fuel reserve. Your planner includes a fuel stop.</p></div> : null}
      {bike.connection === 'phone_only' ? <div className="pt-5"><Unavailable note="Phone only. Live instruments, service data and TFT handoff are unavailable." /></div> : null}
    </div>

    <SectionTitle title="Co-pilot" subtitle="Watches the ride and speaks up when the engine finds something" />
    <CopilotCard bikeId={bike.id} />

    <SectionTitle title="Live telemetry" subtitle="Speed and lean from the bike when authorised, else the phone" />
    <Telemetry />

    <SectionTitle title="At a glance" subtitle={bikeProfile.tagline} />
    <section className="panel mx-6 grid grid-cols-2 overflow-hidden" aria-label="Motorcycle instruments">
      {bikeProfile.tiles.map((tile) => { const reading = tile.read(bike); return <div key={tile.id} className="min-w-0 border-b border-white/[0.065] px-5 py-6 odd:border-r last:col-span-2 last:border-b-0 last:border-r-0">
        <div className="label">{tile.label}</div><div className="mt-3 flex flex-wrap items-baseline gap-1.5"><span className={`readout ${reading.value.length > 6 ? 'text-[25px]' : 'text-[32px]'}`}>{reading.value}</span>{reading.unit ? <span className="unit">{reading.unit}</span> : null}</div>
        {reading.hint ? <p className="caption mt-2 text-[10px]">{reading.hint}</p> : null}
      </div> })}
    </section>

    <SectionTitle title="Where you are" subtitle="Device GPS on satellite, terrain or street tiles" />
    <section className="panel mx-6 overflow-hidden" aria-label="Live position">
      <LiveMap route={lastRide?.path ?? []} height={230} />
    </section>

    <SectionTitle title="Last ride" action={lastRide ? <Link to={`/ride/${lastRide.id}`} className="text-action">View <ChevronRight size={14} /></Link> : undefined} />
    {lastRide ? <Link to={`/ride/${lastRide.id}`} className="panel mx-6 block overflow-hidden">
      <RouteMap path={lastRide.path} height={160} />
      <div className="p-5"><p className="label">{lastRide.date}</p><h3 className="mt-2 text-[18px] font-medium">{lastRide.title}</h3>
        <div className="mt-5 flex items-end justify-between"><div><span className="readout text-[40px]">{lastRide.distanceKm}</span><span className="unit ml-2">km</span></div><span className="caption">{Math.floor(lastRide.durationMin / 60)} h {lastRide.durationMin % 60} min</span><ArrowUpRight size={19} className="text-ash" /></div>
      </div>
    </Link> : <div className="mx-6"><EmptyState title="Your first ride starts here">No recorded rides for your {bike.model} yet. Plan a route to get started.</EmptyState></div>}

    <SectionTitle title="Made for your BMW" subtitle={bikeProfile.suggestionHeadline} />
    <div className="data-list mx-6">
      {suggested.map((r) => <Link to={`/plan?route=${r.id}`} key={r.id} className="list-link"><Route size={19} strokeWidth={1.5} className="shrink-0 text-ash" /><div className="min-w-0 flex-1"><p className="text-[14px] font-medium">{r.name}</p><p className="caption mt-1">{r.region} · {r.distanceKm} km</p></div><ChevronRight size={15} className="shrink-0 text-ash" /></Link>)}
    </div>

    <SectionTitle title={`Season ${stats.year}`} subtitle="Your totals across all motorcycles" />
    <div className="panel mx-6 grid grid-cols-2 gap-x-6 gap-y-7 p-5">
      {[
        ['Rides', String(stats.rides)], ['Distance · km', stats.distanceKm.toLocaleString('de-DE')],
        ['Passes', String(stats.passesRidden)], ['Best curviness', String(stats.topCurviness)],
      ].map(([k, v]) => <div key={k}><div className="label">{k}</div><div className="readout mt-3 text-[36px]">{v}</div></div>)}
    </div><p className="caption px-6 pt-4">{stats.countries.join(' · ')}</p>
  </div>
}
