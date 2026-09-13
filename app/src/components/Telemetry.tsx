import { Gauge, MountainSnow, Radio } from 'lucide-react'
import { useTelemetry, type TelemetrySource } from './useTelemetry'

/**
 * Live ride telemetry, each reading badged with where it actually comes from:
 *   Bike · mySPIN   — the head unit delivered it to an authorised app
 *   Phone GPS       — derived from the phone's GNSS speed
 *   Phone sensors   — derived from the phone's gyro / accelerometer
 * Nothing is invented: a field the phone can't measure and the bike won't grant
 * stays "--".
 */
const SOURCE_LABEL: Record<TelemetrySource, string> = {
  bike: 'Bike · mySPIN',
  phone: 'Phone sensors',
  none: 'No source',
}

function SourceBadge({ source, gps }: { source: TelemetrySource; gps?: boolean }) {
  const label = source === 'phone' && gps ? 'Phone GPS' : SOURCE_LABEL[source]
  return (
    <span className="mt-2 inline-flex items-center gap-1 rounded-control bg-white/[0.06] px-2 py-0.5 text-[9px] uppercase tracking-[0.1em] text-ash"
      data-live={source === 'bike'}>
      {source === 'bike' ? <Radio size={9} /> : null}{label}
    </span>
  )
}

function Tile({ label, value, unit, children }: { label: string; value: string; unit?: string; children?: React.ReactNode }) {
  return (
    <div className="min-w-0 border-b border-white/[0.065] px-5 py-6 odd:border-r last:border-b-0">
      <div className="label flex items-center gap-1.5">{children}{label}</div>
      <div className="mt-3 flex flex-wrap items-baseline gap-1.5">
        <span className="readout text-[32px]">{value}</span>
        {unit ? <span className="unit">{unit}</span> : null}
      </div>
    </div>
  )
}

export function Telemetry({ enabled = true }: { enabled?: boolean }) {
  const t = useTelemetry(enabled)
  const speed = t.speedKmh == null ? '--' : String(Math.round(t.speedKmh))
  const lean = t.leanDeg == null ? '--' : String(Math.round(Math.abs(t.leanDeg)))
  const g = t.gForce == null ? '--' : t.gForce.toFixed(2)

  return (
    <section className="panel mx-6 overflow-hidden" aria-label="Live telemetry">
      <div className="grid grid-cols-2">
        <div className="min-w-0 border-b border-r border-white/[0.065] px-5 py-6">
          <div className="label flex items-center gap-1.5"><Gauge size={12} />Speed</div>
          <div className="mt-3 flex flex-wrap items-baseline gap-1.5">
            <span className="readout text-[32px]">{speed}</span><span className="unit">km/h</span>
          </div>
          <SourceBadge source={t.speedSource} gps />
        </div>
        <div className="min-w-0 border-b border-white/[0.065] px-5 py-6">
          <div className="label flex items-center gap-1.5"><MountainSnow size={12} />Lean</div>
          <div className="mt-3 flex flex-wrap items-baseline gap-1.5">
            <span className="readout text-[32px]">{lean}</span><span className="unit">°</span>
          </div>
          <SourceBadge source={t.leanSource} />
        </div>
        <Tile label="G-force" value={g} unit="g" />
        {t.rpm != null ? <Tile label="Engine" value={String(Math.round(t.rpm))} unit="rpm" /> : (
          <div className="min-w-0 px-5 py-6">
            <div className="label">Engine</div>
            <div className="mt-3 flex flex-wrap items-baseline gap-1.5"><span className="readout text-[32px] text-ash">--</span><span className="unit">rpm</span></div>
            <span className="mt-2 inline-flex rounded-control bg-white/[0.06] px-2 py-0.5 text-[9px] uppercase tracking-[0.1em] text-ash">Bike only · not granted</span>
          </div>
        )}
      </div>
      <p className="caption px-5 py-3 text-[10px]">
        {t.bikeConnected
          ? 'Live from the bike over mySPIN.'
          : 'Bike telemetry needs an authorised mySPIN link; showing phone-measured values until then.'}
      </p>
    </section>
  )
}
