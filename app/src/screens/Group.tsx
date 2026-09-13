import { Link } from 'react-router-dom'
import { ArrowUpRight, Flag } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { RouteMap } from '../components/RouteMap'
import type { MapMarker } from '../components/RouteMap'
import { StatusLed } from '../components/Cluster'
import { BackHeader, EmptyState, SectionTitle } from '../components/primitives'

const TONE = {
  riding: 'ok',
  stopped: 'warn',
  lost_signal: 'alert',
  arrived: 'ok',
} as const

export function GroupScreen() {
  const { group, routes } = useAppState()
  if (!group || !routes.length) return <div><BackHeader to="/more" title="Group ride" /><div className="p-5"><EmptyState title="No group ride scheduled">Your group route and riders will appear here.</EmptyState></div></div>
  const route = routes.find((r) => r.id === group.routeId) ?? routes[0]

  const markers: MapMarker[] = group.riders.map((r, i) => ({
    id: r.id,
    t: Math.max(0, 0.6 - r.distanceBehindKm / route.distanceKm) + i * 0.001,
    label: r.name,
    tone: r.status === 'lost_signal' ? 'alert' : r.status === 'stopped' ? 'warn' : 'accent',
  }))

  return (
    <div className="pb-8">
      <BackHeader to="/more" title={group.name} detail={group.startsAt} />

      <section className="map-section">
        <RouteMap path={route.path} markers={markers} height={220} active />
        <div className="flex items-center justify-between p-5"><div><p className="label">Together on the road</p><h2 className="mt-2 text-[17px] font-medium">{route.name}</h2></div><div className="text-right"><span className="readout text-[36px]">{group.riders.length}</span><p className="label mt-1">riders</p></div></div>
      </section>

      <div className="mx-6 mt-4 flex items-center justify-between gap-4 rounded-panel bg-panel p-5">
        <div>
          <div className="label flex items-center gap-2"><Flag size={12} /> Regroup</div>
          <div className="mt-1 text-[16px] font-medium tracking-[-0.02em]">{group.regroupPoint}</div>
        </div>
        <div className="readout shrink-0 text-[32px]">
          {group.regroupAtKm}
          <span className="ml-1 text-[11px] font-medium text-ash">km</span>
        </div>
      </div>

      <SectionTitle title="Your group" subtitle="Registered BMW motorcycles" />
      <div className="data-list mx-6">
        {group.riders.map((r) => (
          <div key={r.id} className="py-4">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0"><h3 className="text-[16px] font-medium">{r.name}</h3><p className="caption mt-1">{r.bike}</p></div>
              <div className="shrink-0 text-right"><span className="readout text-[28px]">{r.distanceBehindKm.toFixed(1)}</span><p className="caption">km behind</p></div>
            </div>
            <div className="mt-3 flex items-center justify-between gap-4">
              <StatusLed on={r.status === 'riding'} tone={TONE[r.status]}>{r.status.replace('_', ' ')}</StatusLed>
              <span className="caption">Phone {r.batteryPercent}%</span>
            </div>
          </div>
        ))}
      </div>

      <div className="px-6 pt-5">
        <Link to={`/plan?route=${route.id}`} className="button button-primary">Review group route <ArrowUpRight size={17} /></Link>
      </div>
    </div>
  )
}
