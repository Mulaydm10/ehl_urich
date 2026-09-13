import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Sparkles } from 'lucide-react'
import { BackHeader, Chip, Feedback, GhostButton, PrimaryButton, SectionTitle } from '../components/primitives'
import { useAppState } from '../state/AppState'
import { getPreference, setPreference } from '../services/ridePreference'
import {
  DEFAULT_PREFERENCE,
  UNANSWERABLE,
  dialFor,
  explain,
  modeKeyFor,
  preferenceForBike,
} from '../domain/ridePreference'
import type { ClimbWant, CurveWant, IntentWant, RidePreference, TrafficWant } from '../domain/ridePreference'

const COMFORT: { value: number; label: string; caption: string }[] = [
  { value: 1, label: '1', caption: 'Only roads like the ones I ride every day.' },
  { value: 2, label: '2', caption: 'A little more than usual.' },
  { value: 3, label: '3', caption: 'My normal riding, at its best.' },
  { value: 4, label: '4', caption: 'Push me past my habit.' },
  { value: 5, label: '5', caption: 'As far as my own gate allows.' },
]

const CURVES: { value: CurveWant; label: string }[] = [
  { value: 'few', label: 'Open and flowing' },
  { value: 'some', label: 'A normal mix' },
  { value: 'relentless', label: 'Corner after corner' },
]

const CLIMB: { value: ClimbWant; label: string }[] = [
  { value: 'flat', label: 'Stay low' },
  { value: 'rolling', label: 'Rolling' },
  { value: 'high', label: 'Up into the passes' },
]

const TRAFFIC: { value: TrafficWant; label: string }[] = [
  { value: 'either', label: "Doesn't matter" },
  { value: 'quiet', label: 'Roads nobody rides' },
]

const INTENT: { value: IntentWant; label: string }[] = [
  { value: 'scenic', label: 'Scenic' },
  { value: 'challenge', label: 'A challenge' },
  { value: 'either', label: 'Whatever fits best' },
]

export function RideProfileScreen() {
  const { bike } = useAppState()
  const navigate = useNavigate()
  const [pref, setPref] = useState<RidePreference>(
    () => getPreference() ?? preferenceForBike(bike) ?? DEFAULT_PREFERENCE,
  )
  const [saved, setSaved] = useState(false)

  const set = <K extends keyof RidePreference>(key: K, value: RidePreference[K]) => {
    setPref((p) => ({ ...p, [key]: value }))
    setSaved(false)
  }

  const modeKey = modeKeyFor(pref)

  return (
    <div className="pb-10">
      <BackHeader
        to="/thrill"
        title="Your ride profile"
        detail="What kind of difficulty you want, in the terms the engine actually measures."
      />

      <SectionTitle
        title="How hard should it be"
        subtitle="This sets the thrill dial, not the safety gate."
      />
      <div className="flex flex-wrap gap-2 px-6">
        {COMFORT.map((c) => (
          <Chip key={c.value} active={c.value === pref.comfort} onClick={() => set('comfort', c.value)}>
            {c.label}
          </Chip>
        ))}
      </div>
      <p className="caption mx-6 mt-3">
        {COMFORT.find((c) => c.value === pref.comfort)?.caption} Dial: {dialFor(pref)}.
      </p>

      <SectionTitle title="How many corners" subtitle="Direction changes per kilometre, from the crowd's own rides." />
      <div className="flex flex-wrap gap-2 px-6">
        {CURVES.map((c) => (
          <Chip key={c.value} active={c.value === pref.curves} onClick={() => set('curves', c.value)}>
            {c.label}
          </Chip>
        ))}
      </div>

      <SectionTitle title="How high" subtitle="Mean elevation of the cells the route crosses." />
      <div className="flex flex-wrap gap-2 px-6">
        {CLIMB.map((c) => (
          <Chip key={c.value} active={c.value === pref.climb} onClick={() => set('climb', c.value)}>
            {c.label}
          </Chip>
        ))}
      </div>

      <SectionTitle title="How busy" subtitle="How often the crowd has ridden the road." />
      <div className="flex flex-wrap gap-2 px-6">
        {TRAFFIC.map((c) => (
          <Chip key={c.value} active={c.value === pref.traffic} onClick={() => set('traffic', c.value)}>
            {c.label}
          </Chip>
        ))}
      </div>

      <SectionTitle title="Scenic or a challenge" />
      <div className="flex flex-wrap gap-2 px-6">
        {INTENT.map((c) => (
          <Chip key={c.value} active={c.value === pref.intent} onClick={() => set('intent', c.value)}>
            {c.label}
          </Chip>
        ))}
      </div>

      <div className="panel mx-6 mt-6 p-5">
        <div className="label">What the engine will be asked</div>
        <ul className="mt-3 space-y-2">
          {explain(pref).map((line) => (
            <li key={line} className="caption leading-relaxed">{line}</li>
          ))}
        </ul>
        <p className="caption mt-3 font-mono text-[11px] text-ash">mode = {modeKey ?? 'flow'}</p>
      </div>

      <div className="panel mx-6 mt-4 p-5">
        <div className="label">What it cannot ask for</div>
        <ul className="mt-3 space-y-2">
          {UNANSWERABLE.map((u) => (
            <li key={u.want} className="caption leading-relaxed">
              <span className="text-bone">{u.want}</span> — {u.why}
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-3 px-6 py-6">
        <PrimaryButton
          onClick={() => {
            setPreference(pref)
            setSaved(true)
            navigate('/thrill')
          }}
        >
          <span className="inline-flex items-center justify-center gap-2">
            <Sparkles size={16} /> Use this profile
          </span>
        </PrimaryButton>
        <GhostButton
          onClick={() => {
            const fromBike = preferenceForBike(bike)
            setPref(fromBike)
            setSaved(false)
          }}
        >
          {bike ? `Start from the ${bike.model}` : 'Reset to the defaults'}
        </GhostButton>
        {saved ? (
          <Feedback tone="success">
            <span className="inline-flex items-center gap-2"><Check size={14} /> Saved on this phone.</span>
          </Feedback>
        ) : null}
      </div>
    </div>
  )
}
