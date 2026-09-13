import { Check } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { BikeImage } from '../components/BikeImage'
import { StatusLed } from '../components/Cluster'
import { PageHeader, SectionTitle, Unavailable } from '../components/primitives'

export function GarageScreen() {
  const { bikes, bike, selectBike, rider } = useAppState()
  if (!bike || !rider) return null

  return (
    <div className="pb-8">
      <PageHeader eyebrow={`${bikes.length} BMW motorcycles`} title="Your garage">A different way to ride.</PageHeader>
      <div className="space-y-2 px-6">
        {bikes.map((b) => {
          const active = b.id === bike.id
          return (
            <button key={b.id} type="button" onClick={() => selectBike(b.id)} aria-pressed={active}
              className="bike-option">
              <BikeImage bike={b} className="h-[102px] w-[114px] shrink-0" decorative priority />
              <span className="min-w-0 flex-1">
                <span className="flex items-start justify-between gap-2">
                  <span className="text-[16px] font-medium leading-tight tracking-[-0.025em]">{b.model}</span>
                  <span className={`flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full ${active ? 'bg-accent text-[var(--accent-contrast)]' : 'border border-white/15'}`} aria-hidden="true">{active ? <Check size={11} strokeWidth={2.5} /> : null}</span>
                </span>
                <span className="caption mt-1 block text-[10px]">{b.variant}</span>
                <span className="mt-3 flex items-baseline gap-1.5"><span className="readout text-[26px]">{b.rangeKm ?? '--'}</span><span className="unit">km</span></span>
                <span className="mt-2 block"><StatusLed on={active && b.connection === 'connected'}>{{ connected: 'Connected', last_seen: 'Last seen', phone_only: 'Phone only' }[b.connection]}</StatusLed></span>
              </span>
            </button>
          )
        })}
      </div>

      <SectionTitle title="Vehicle status" subtitle={bike.model} />
      <div className="data-list mx-6">
        {[
          ['Odometer', bike.odometerKm === null ? '--' : `${bike.odometerKm.toLocaleString('de-DE')} km`],
          ['Service due', bike.serviceDueKm === null ? '--' : `${bike.serviceDueKm.toLocaleString('de-DE')} km`],
          ['Service date', bike.serviceDueDate ?? '--'],
          ['Tyre pressure', bike.tyrePressureBar === null ? '--' : `${bike.tyrePressureBar.front.toFixed(1)} / ${bike.tyrePressureBar.rear.toFixed(1)} bar`],
          ['12V battery', bike.batteryVolt === null ? '--' : `${bike.batteryVolt.toFixed(1)} V`],
          ['ConnectedRide Navigator', bike.connection === 'phone_only' ? '--' : bike.hasConnectedRideNavigator ? 'Paired' : 'Not paired'],
          ['Recall', bike.connection === 'phone_only' ? '--' : bike.recall ?? 'None open'],
        ].map(([k, v]) => (
          <div key={k} className="grid grid-cols-[1fr_1.1fr] items-baseline gap-4 py-4">
            <span className="text-[13px] text-ash">{k}</span>
            <span className="text-right text-[13px] font-medium leading-relaxed text-bone">{v}</span>
          </div>
        ))}
      </div>
      {bike.connection === 'phone_only' ? <div className="mx-6 mt-4"><Unavailable note="This BMW has no Connectivity module. Live vehicle data is unavailable." /></div> : null}
      <p className="caption px-6 pt-5">{rider.homeDealer} · Member since {rider.memberSince}</p>
    </div>
  )
}
