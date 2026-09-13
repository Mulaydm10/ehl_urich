import { Link } from 'react-router-dom'
import { useState } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { RouteMap } from '../components/RouteMap'
import { EmptyState, GhostButton, PageHeader } from '../components/primitives'

const FILTERS = ['All', 'BMW curated', 'Community', 'Imported'] as const

export function DiscoverScreen() {
  const { routes, bikeProfile } = useAppState()
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('All')
  const shown = routes.filter((r) => filter === 'All' ? true : filter === 'BMW curated' ? r.source === 'curated' : filter === 'Community' ? r.source === 'community' : r.source === 'imported')

  return (
    <div className="pb-8">
      <PageHeader eyebrow="Discover" title="Find a route">{bikeProfile?.suggestionHeadline}</PageHeader>
      <div className="filter-tabs mb-5" role="group" aria-label="Route source">
        {FILTERS.map((f) => <button key={f} type="button" className="filter-tab" aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>)}
      </div>
      <div className="px-6 screen-enter" key={filter}>
        {shown.map((r, i) => i === 0 ? (
          <Link key={r.id} to={`/plan?route=${r.id}`} className="panel mb-5 block overflow-hidden">
            <RouteMap path={r.path} height={180} />
            <div className="p-5">
              <div className="flex items-center justify-between gap-3"><span className="label">{r.region}</span><ArrowUpRight size={17} className="text-bone" /></div>
              <h2 className="mt-2 text-title">{r.name}</h2>
              <p className="caption mt-1">{r.source === 'curated' ? 'BMW curated' : r.source === 'planned' ? 'Saved route' : r.source === 'imported' ? 'Imported GPX' : 'Community'}{r.author ? ` · ${r.author}` : ''}</p>
              <div className="mt-4 grid grid-cols-3 gap-3 border-t border-white/[0.065] pt-4">
                {[[String(r.distanceKm), 'km'], [`${Math.floor(r.durationMin / 60)}:${String(r.durationMin % 60).padStart(2, '0')}`, 'hours'], [String(r.curvinessScore), 'curviness']].map(([v, u]) => (
                  <div key={u}><div className={`readout text-[32px] ${u === 'curviness' ? 'text-bone' : ''}`}>{v}</div><div className="caption mt-1">{u}</div></div>
                ))}
              </div>
            </div>
          </Link>
        ) : (
          <Link key={r.id} to={`/plan?route=${r.id}`} className="list-link border-b border-white/[0.065]">
            <div className="w-[88px] shrink-0 overflow-hidden rounded-lg"><RouteMap path={r.path} width={88} height={88} showStartEnd={false} attribution={false} /></div>
            <div className="min-w-0 flex-1">
              <p className="caption">{r.region}</p>
              <h2 className="mt-1 text-[16px] font-medium leading-tight tracking-[-0.02em]">{r.name}</h2>
              <p className="caption mt-2">{r.distanceKm} km <span className="px-1">·</span> <span className="text-bone">{r.curvinessScore} curviness</span></p>
            </div>
            <ArrowUpRight size={15} className="shrink-0 text-ash" />
          </Link>
        ))}
        {!shown.length ? <EmptyState title="No routes in this collection" action={<GhostButton onClick={() => setFilter('All')}>Show all routes</GhostButton>}>Try another collection to find your next ride.</EmptyState> : null}
      </div>
    </div>
  )
}
