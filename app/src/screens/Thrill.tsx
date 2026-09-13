import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Gauge, Navigation, RefreshCw } from 'lucide-react'
import { FlowMap } from '../components/FlowMap'
import { Chip, Feedback, GhostButton, PageHeader, PlannerSwitch, PrimaryButton, SectionTitle } from '../components/primitives'
import { takePendingPlan } from '../services/assistant'
import { setActiveRoute } from '../services/copilot'
import { fitFor } from '../domain/bikeFit'
import { useAppState } from '../state/AppState'
import { flowstate } from '../services/flowstate'
import type {
  FsCompareResult,
  FsMode,
  FsPresetLoop,
  FsPresetRoute,
  FsPresets,
  FsRider,
  FsRouteResult,
  FsRouteSummary,
  ThrillPreset,
} from '../domain/types'

const DIALS: ThrillPreset[] = ['Cruise', 'Flow', 'Send it']
const HOURS = [1, 1.5, 2, 3]

const summaryOf = (r: FsRouteResult | null): FsRouteSummary | null =>
  r && r.ok && !Array.isArray(r.summary) ? r.summary : null

function Figures({ summary }: { summary: FsRouteSummary }) {
  const cells: [string, string, string][] = [
    [summary.km.toFixed(0), 'km', 'distance'],
    [summary.minutes.toFixed(0), 'min', 'riding time'],
    [summary.fun_score.toFixed(0), '', 'fun score'],
  ]
  return (
    <div className="grid grid-cols-3 gap-4 px-6 pt-5">
      {cells.map(([value, unit, label]) => (
        <div key={label}>
          <div className="flex items-baseline gap-1">
            <span className="readout text-[30px]">{value}</span>
            {unit ? <span className="unit">{unit}</span> : null}
          </div>
          <span className="label mt-2 block">{label}</span>
        </div>
      ))}
    </div>
  )
}

function DemandRow({ summary }: { summary: FsRouteSummary }) {
  const grip = summary.grip_lat_p95
  return (
    <div className="panel mx-6 mt-5 divide-y divide-white/[0.06] px-4">
      {[
        ['Mean lean asked', `${summary.mean_demand.toFixed(1)}°`],
        ['Peak lean asked', `${summary.max_demand.toFixed(1)}°`],
        ['Your safety gate', `${summary.gate_deg.toFixed(1)}°`],
        ['Grip used at p95', grip === null ? '--' : `${Math.round(grip * 100)}%`],
      ].map(([label, value]) => (
        <div key={label} className="flex items-center justify-between gap-4 py-3">
          <span className="caption">{label}</span>
          <span className="font-mono text-[13px] text-bone">{value}</span>
        </div>
      ))}
    </div>
  )
}

function RiderCard({ rider }: { rider: FsRider }) {
  return (
    <div className="panel mx-6 mt-5 p-5">
      <div className="label">Rider profile · measured from telemetry</div>
      <div className="mt-4 grid grid-cols-3 gap-4">
        {[
          [rider.skill.toFixed(1), 'skill °'],
          [rider.sigma.toFixed(1), 'sigma °'],
          [rider.gate.toFixed(1), 'gate °'],
        ].map(([value, label]) => (
          <div key={label}>
            <span className="readout text-[24px]">{value}</span>
            <span className="label mt-2 block">{label}</span>
          </div>
        ))}
      </div>
      <p className="caption mt-4">
        The gate is your own habitual lean plus two standard deviations — {rider.gate.toFixed(1)}°.
        The hardest road you have actually ridden asked {rider.hardest_ridden.toFixed(1)}°, so the
        gate sits {rider.gate_agreement.toFixed(2)}× that. Roads past it are removed from the graph,
        not just made expensive. Measured on {rider.n_corners.toLocaleString()} corners across{' '}
        {rider.n_cells.toLocaleString()} cells of your own riding.
      </p>
    </div>
  )
}

export function ThrillScreen() {
  const { bike } = useAppState()
  const [riders, setRiders] = useState<FsRider[]>([])
  const [presets, setPresets] = useState<FsPresets | null>(null)
  const [modes, setModes] = useState<FsMode[]>([])
  const [unreachable, setUnreachable] = useState(false)
  const [loading, setLoading] = useState(true)

  const [result, setResult] = useState<FsRouteResult | null>(() => takePendingPlan())
  // A route the assistant planned arrives already shaped. The controls here
  // describe the *next* plan, so at least point them at the right kind of
  // ride rather than leaving A -> B selected under a loop.
  const [assistantPlan, setAssistantPlan] = useState(() => result !== null)

  const [riderKey, setRiderKey] = useState('userA')
  const [mode, setMode] = useState('flow')
  const [tab, setTab] = useState<'ab' | 'loop'>(() =>
    summaryOf(result)?.is_loop ? 'loop' : 'ab',
  )

  const [pair, setPair] = useState<FsPresetRoute | null>(null)
  const [loopStart, setLoopStart] = useState<FsPresetLoop | null>(null)
  const [hours, setHours] = useState(2)
  const [dial, setDial] = useState<ThrillPreset>('Flow')

  const fit = fitFor(bike)
  const fitApplied = !!fit && dial === fit.dial && mode === fit.mode

  const [busy, setBusy] = useState(false)
  const [comparison, setComparison] = useState<FsCompareResult | null>(null)
  const [note, setNote] = useState<string | null>(null)

  // Whatever is on screen here is the plan the rider is following, so it is
  // also the plan the co-pilot measures the ride against.
  useEffect(() => {
    setActiveRoute(result)
  }, [result])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [rs, ps, ms] = await Promise.all([
          flowstate.riders(),
          flowstate.presets(),
          flowstate.modes(),
        ])
        if (cancelled) return
        setRiders(rs)
        setPresets(ps)
        setModes(ms.filter((m) => m.offered))
        setPair(ps.routes[0] ?? null)
        setLoopStart(ps.loops[0] ?? null)
        setUnreachable(false)
      } catch {
        if (!cancelled) setUnreachable(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const zStar = presets?.dial[dial] ?? 0.5

  const runPlan = useCallback(async () => {
    setBusy(true)
    setNote(null)
    setComparison(null)
    setAssistantPlan(false)
    try {
      const r =
        tab === 'ab' && pair
          ? await flowstate.route(pair.a, pair.b, riderKey, zStar, mode)
          : loopStart
            ? await flowstate.loop(loopStart.start, hours, riderKey, zStar, mode)
            : null
      setResult(r)
      if (r && !r.ok) setNote(r.note)
    } catch {
      setResult(null)
      setNote('The route engine did not answer. Nothing is being guessed — try again when the backend is reachable.')
    } finally {
      setBusy(false)
    }
  }, [tab, pair, loopStart, hours, riderKey, zStar, mode])

  const runCompare = useCallback(async () => {
    if (!pair) return
    setBusy(true)
    setNote(null)
    setResult(null)
    setAssistantPlan(false)
    try {
      const c = await flowstate.compare(pair.a, pair.b, riderKey, mode)
      setComparison(c)
      if (!c.high.ok) setNote(c.high.note)
    } catch {
      setComparison(null)
      setNote('The route engine did not answer. Nothing is being guessed — try again when the backend is reachable.')
    } finally {
      setBusy(false)
    }
  }, [pair, riderKey, mode])

  const rider = riders.find((r) => r.key === riderKey) ?? null
  const shown = comparison?.high ?? result
  const summary = summaryOf(shown)

  if (loading) {
    return (
      <div className="pb-8">
        <PageHeader eyebrow="Find your thrill" title="Fun-fit planner" />
        <PlannerSwitch current="thrill" />
        <div className="loading-pulse mx-6 mt-4 h-44 rounded-panel bg-panel" aria-hidden="true" />
      </div>
    )
  }

  if (unreachable) {
    return (
      <div className="pb-8">
        <PageHeader eyebrow="Find your thrill" title="Fun-fit planner" />
        <PlannerSwitch current="thrill" />
        <div className="mx-6 mt-4">
          <Feedback tone="error">
            The fun-fit route engine is not reachable from here. It runs next to the crowd data and
            is not mirrored into the app, so no route is shown rather than an invented one. Rest of
            the app keeps working.
          </Feedback>
          <div className="mt-4">
            <GhostButton onClick={() => window.location.reload()}>
              <span className="inline-flex items-center gap-2"><RefreshCw size={15} /> Retry</span>
            </GhostButton>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="pb-8">
      <PageHeader eyebrow="Find your thrill" title="Fun-fit planner">
        Roads scored by how well their lean-angle demand fits your own measured riding — not by how
        twisty they look. Covers Bavaria and the Alpine foothills.
      </PageHeader>

      <PlannerSwitch current="thrill" />

      {result?.ok ? (
        <Link
          to="/navigate"
          className="mx-6 mt-4 flex items-center justify-center gap-2 rounded-control bg-accent px-4 py-3 text-[13px] font-medium text-[var(--accent-contrast)]"
        >
          <Navigation size={16} strokeWidth={1.8} />
          Ride it hands-free
        </Link>
      ) : null}

      {fit && bike ? (
        <div className="panel mx-6 mt-4 p-4">
          <div className="label">Fit to your bike · preset, not measured</div>
          <p className="mt-2 text-[14px] font-medium text-bone">
            {bike.model}: {fit.headline}
          </p>
          <p className="caption mt-1">{fit.why}</p>
          <button
            type="button"
            onClick={() => {
              setDial(fit.dial)
              if (modes.some((m) => m.key === fit.mode)) setMode(fit.mode)
            }}
            className="mt-3 rounded-control border border-white/20 px-3 py-1.5 text-[11px] uppercase tracking-[0.1em]"
          >
            {fitApplied ? 'Applied' : `Use ${fit.dial} · ${fit.mode}`}
          </button>
          <p className="caption mt-2">
            Your safety gate is unchanged — the bike cannot raise the lean you are allowed.
          </p>
        </div>
      ) : null}

      {assistantPlan ? (
        <p className="caption mx-6 mt-4 rounded-panel border border-white/[0.08] bg-panel p-4">
          Showing the {summaryOf(result)?.is_loop ? 'loop' : 'route'} the assistant planned. The
          controls below set up your next plan and do not describe this one.
        </p>
      ) : null}

      <div className="mt-4 flex gap-2 px-6">
        <Chip active={tab === 'ab'} onClick={() => setTab('ab')}>A → B</Chip>
        <Chip active={tab === 'loop'} onClick={() => setTab('loop')}>Loop</Chip>
      </div>

      <SectionTitle title="Rider" subtitle="Skill and safety gate come from this rider's telemetry." />
      <div className="flex flex-wrap gap-2 px-6">
        {riders.map((r) => (
          <Chip key={r.key} active={r.key === riderKey} onClick={() => setRiderKey(r.key)}>{r.label}</Chip>
        ))}
      </div>

      {tab === 'ab' ? (
        <>
          <SectionTitle title="Start and finish" />
          <div className="space-y-2 px-6">
            {presets?.routes.map((p) => (
              <button key={p.key} type="button" onClick={() => setPair(p)}
                className="panel w-full p-4 text-left" data-active={p.key === pair?.key}
                style={{ borderColor: p.key === pair?.key ? 'var(--accent)' : undefined }}>
                <div className="text-[14px] font-medium text-bone">{p.label}</div>
                <div className="caption mt-1">{p.why}</div>
              </button>
            ))}
          </div>
        </>
      ) : (
        <>
          <SectionTitle title="Start" />
          <div className="flex flex-wrap gap-2 px-6">
            {presets?.loops.map((l) => (
              <Chip key={l.key} active={l.key === loopStart?.key} onClick={() => setLoopStart(l)}>{l.label}</Chip>
            ))}
          </div>
          <SectionTitle title="Time budget" />
          <div className="flex flex-wrap gap-2 px-6">
            {HOURS.map((h) => (
              <Chip key={h} active={h === hours} onClick={() => setHours(h)}>{h} h</Chip>
            ))}
          </div>
        </>
      )}

      <SectionTitle title="Thrill dial" subtitle="How far past your habit the route should push." />
      <div className="flex gap-2 px-6">
        {DIALS.map((d) => (
          <Chip key={d} active={d === dial} onClick={() => setDial(d)}>{d}</Chip>
        ))}
      </div>

      {modes.length > 1 ? (
        <>
          <SectionTitle title="Character" subtitle="Only modes the backend validated are offered." />
          <div className="flex flex-wrap gap-2 px-6">
            {modes.map((m) => (
              <Chip key={m.key} active={m.key === mode} onClick={() => setMode(m.key)}>{m.key}</Chip>
            ))}
          </div>
          {mode === 'mountain' ? (
            <p className="caption mt-3 px-6">
              Leans the route towards higher ground where the network offers a choice.
            </p>
          ) : null}
        </>
      ) : null}

      <div className="space-y-3 px-6 py-6">
        <PrimaryButton onClick={runPlan} busy={busy} disabled={busy}>
          <span className="inline-flex items-center justify-center gap-2">
            <Gauge size={16} /> {tab === 'ab' ? 'Plan this route' : 'Build the loop'}
          </span>
        </PrimaryButton>
        {tab === 'ab' ? (
          <GhostButton onClick={runCompare} busy={busy} disabled={busy}>
            Compare Cruise and Send it
          </GhostButton>
        ) : null}
        {note ? <Feedback tone="error">{note}</Feedback> : null}
      </div>

      {comparison?.headline ? (
        <div className="mx-6 mb-4 rounded-panel border border-white/[0.08] bg-panel p-5">
          <div className="label">Same two points</div>
          <p className="mt-2 text-[15px] leading-snug text-bone">{comparison.headline}</p>
          {comparison.overlap !== undefined ? (
            <p className="caption mt-3">
              {Math.round(comparison.overlap * 100)}% of the road is shared between the two settings.
            </p>
          ) : null}
        </div>
      ) : null}

      {shown && shown.ok ? (
        <section className="map-section">
          <FlowMap
            lines={
              comparison
                ? [
                    { segments: comparison.low.segments, muted: true, label: 'Cruise' },
                    { segments: comparison.high.segments, label: 'Send it' },
                  ]
                : [{ segments: shown.segments, label: dial }]
            }
            refusals={shown.refusals}
            height={250}
            interactive
          />
          {summary ? (
            <>
              <Figures summary={summary} />
              {summary.is_loop && summary.distinct_share !== undefined ? (
                <p className="caption mt-4 px-6">
                  {Math.round(summary.distinct_share * 100)}% of the loop is road you ride only once
                  {summary.budget_min ? `, against a ${summary.budget_min} minute budget` : ''}.
                </p>
              ) : null}
            </>
          ) : null}
        </section>
      ) : null}

      {summary ? <DemandRow summary={summary} /> : null}

      {shown && shown.refusals.length ? (
        <div className="mx-6 mt-5 rounded-panel border border-alert/30 bg-alert/[0.06] p-4">
          <div className="flex items-center gap-2">
            <AlertTriangle size={15} className="shrink-0 text-alert" />
            <span className="text-[13px] font-medium text-bone">
              {shown.refusals.length} road{shown.refusals.length === 1 ? '' : 's'} refused outright
            </span>
          </div>
          <ul className="mt-3 space-y-2">
            {shown.refusals.map((r, i) => (
              <li key={`${r.cell}-${i}`} className="caption">{r.reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {shown && shown.explain.length ? (
        <>
          <SectionTitle title="Why this route" />
          <ul className="space-y-3 px-6">
            {shown.explain.map((line, i) => (
              <li key={i} className="caption leading-relaxed">{line}</li>
            ))}
          </ul>
        </>
      ) : null}

      {rider ? <RiderCard rider={rider} /> : null}
    </div>
  )
}
