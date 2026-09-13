import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Download, ImageOff } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { RouteMap } from '../components/RouteMap'
import { LeanArc, TelemetryRow } from '../components/Cluster'
import { BackHeader, EmptyState, Feedback, GhostButton, SectionTitle } from '../components/primitives'
import type { RideSample } from '../domain/types'

function Trace({
  samples,
  pick,
  label,
  unit,
}: {
  samples: RideSample[]
  pick: (s: RideSample) => number
  label: string
  unit: string
}) {
  const w = 360
  const h = 70
  const vals = samples.map(pick)
  const max = Math.max(...vals)
  const min = Math.min(...vals)
  const d = vals
    .map((v, i) => {
      const x = (i / (vals.length - 1)) * w
      const y = h - ((v - min) / Math.max(max - min, 1)) * (h - 8) - 4
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <div className="panel mx-6 mt-4 p-5">
      <div className="flex justify-between">
        <span className="label">{label}</span>
        <span className="font-mono text-[10px] text-ash">
          sample peak {Math.round(max)} {unit}
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} height={h} preserveAspectRatio="none" className="mt-4 w-full" role="img" aria-label={`${label} over the ride, ${Math.round(min)} to ${Math.round(max)} ${unit}`}>
        {[0.33, 0.66].map((f) => (
          <line key={f} x1={0} y1={h * f} x2={w} y2={h * f} stroke="rgba(255,255,255,0.06)" />
        ))}
        <path d={d} fill="none" stroke="#B9BCC1" strokeWidth={1.6} />
      </svg>
      <div className="mt-2 flex justify-between font-mono text-[9px] text-ash"><span>0</span><span>{samples[samples.length - 1].km} km</span></div>
    </div>
  )
}

export function RideDetailScreen() {
  const { rideId } = useParams()
  const { rides, bikes, bike, api } = useAppState()
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<{ error: boolean; message: string } | null>(null)
  const ride = rides.find((r) => r.id === rideId && r.bikeId === bike?.id)
  if (!ride) {
    const owner = bikes.find((b) => b.id === rides.find((r) => r.id === rideId)?.bikeId)
    return <div className="pb-8">
      <BackHeader to="/more" title="Ride unavailable" detail={bike?.model} />
      <div className="p-5"><EmptyState title={owner ? `Recorded on ${owner.model}` : 'Ride not found'} action={<Link to="/garage" className="button button-secondary">Choose a motorcycle</Link>}>
        {owner ? `Select the ${owner.model} in your garage to view its ride. No telemetry is available for your ${bike?.model} here.` : 'This ride is no longer in your history.'}
      </EmptyState></div>
    </div>
  }

  return (
    <div className="pb-8">
      <BackHeader to="/" title={ride.title} detail={`${ride.date} · ${bike?.model}`} />

      <div className="metric-hero"><div className="flex items-baseline justify-center gap-2"><span className="readout">{ride.distanceKm}</span><span className="text-[18px] font-light text-ash">km</span></div><span className="label">Distance ridden</span></div>
      <div className="map-section"><RouteMap path={ride.path} height={190} /></div>
      <section className="panel mx-6 mt-5 overflow-hidden" aria-label="Ride statistics">
        <TelemetryRow items={[
          { label: 'Moving time', value: `${Math.floor(ride.durationMin / 60)}:${String(ride.durationMin % 60).padStart(2, '0')}`, unit: 'h' },
          { label: 'Curviness', value: String(ride.curvinessScore) },
        ]} />
        <div className="border-t border-white/[0.065]"><TelemetryRow items={[
          { label: 'Average', value: String(ride.avgSpeedKmh), unit: 'km/h' },
          { label: 'Top speed', value: String(ride.topSpeedKmh), unit: 'km/h' },
          { label: 'Ascent', value: String(ride.ascentM), unit: 'm' },
        ]} /></div>
      </section>

      <SectionTitle title="Lean angle" subtitle="Peak lean through the corners." />
      <div className="panel mx-6 flex flex-wrap items-center gap-4 p-5">
        <LeanArc left={ride.maxLeanLeftDeg} right={ride.maxLeanRightDeg} size={148} />
        <div className="flex-1 space-y-2">
          <div>
            <div className="label">Peak left</div>
            <div className="readout text-[42px]">{ride.maxLeanLeftDeg}°</div>
          </div>
          <div>
            <div className="label">Peak right</div>
            <div className="readout text-[42px]">{ride.maxLeanRightDeg}°</div>
          </div>
        </div>
      </div>

      <Trace samples={ride.samples} pick={(s) => s.speedKmh} label="Speed" unit="km/h" />
      <Trace samples={ride.samples} pick={(s) => s.altitudeM} label="Altitude" unit="m" />
      <Trace samples={ride.samples} pick={(s) => s.rpm} label="Engine speed" unit="rpm" />

      {ride.photos.length ? (
        <>
          <SectionTitle title="Photo locations" subtitle="Images are unavailable for this ride." />
          <div className="data-list mx-6">
            {ride.photos.map((p) => <div key={p.id} className="flex items-center gap-3 py-4">
              <ImageOff size={19} strokeWidth={1.5} className="shrink-0 text-ash" />
              <span className="flex-1 text-[13px]">{p.caption}</span>
              <span className="font-mono text-[11px] text-ash">{p.atKm} km</span>
            </div>)}
          </div>
        </>
      ) : null}

      <div className="px-6 pt-5">
        <GhostButton busy={busy} onClick={async () => {
          setBusy(true)
          setFeedback(null)
          try {
            const url = await api.exportRoute(ride.id, 'GPX track')
            if (!url) throw new Error('Export unavailable')
            setFeedback({ error: false, message: 'GPX export prepared. File downloads are not available in this preview.' })
          } catch { setFeedback({ error: true, message: 'Could not prepare this ride export. Try again.' }) }
          finally { setBusy(false) }
        }}>
          <span className="inline-flex items-center gap-2">
            <Download size={15} /> Export ride as GPX
          </span>
        </GhostButton>
        {feedback ? <div className="mt-3"><Feedback tone={feedback.error ? 'error' : 'info'}>{feedback.message}</Feedback></div> : null}
      </div>
    </div>
  )
}
