import { useEffect, useMemo, useRef, useState } from 'react'
import RouteMap, { CAND_COLORS } from './components/RouteMap'
import { Chip, Notice, Section, Stat, fmt, pct } from './components/ui'
import {
  ApiError, COVERAGE, api, inCoverage, summaryOf,
  type Candidate, type Health, type Mode, type Plan, type Presets, type RerouteResult, type Rider, type Status,
} from './lib/api'
import { cumulativeKm, pointAt } from './lib/geo'

type Change = 'avoid_this_road' | 'more_fun' | 'calmer' | 'scenic' | 'mountain'
const CHANGES: { key: Change; label: string; order: string }[] = [
  { key: 'avoid_this_road', label: 'Avoid this road', order: 'thrill up → scenic → mountain → thrill down; lowest shared-road wins' },
  { key: 'more_fun', label: 'More fun', order: 'thrill +0.35, same mode' },
  { key: 'calmer', label: 'Calmer', order: 'thrill −0.35, same mode' },
  { key: 'scenic', label: 'Scenic', order: 'same thrill, scenic mode' },
  { key: 'mountain', label: 'Mountain', order: 'same thrill, mountain mode' },
]
const SPEEDS = [30, 120, 600]
const CUSTOM_EXAMPLE = 'custom:reversals_km=+2,elev_mean=+1,n_rides=-1'

function errText(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : String(e)
}

function candidateAsPlan(c: Candidate): Plan {
  return { ok: c.ok, note: c.note, cells: c.cells, path: c.path, segments: c.segments,
    refusals: c.refusals, summary: c.summary, z_star: c.thrill, explain: c.explain }
}

export default function App() {
  // ---- backend ---------------------------------------------------------
  const [health, setHealth] = useState<Health | null>(null)
  const [status, setStatus] = useState<Status | null>(null)
  const [riders, setRiders] = useState<Rider[]>([])
  const [modes, setModes] = useState<Mode[]>([])
  const [presets, setPresets] = useState<Presets | null>(null)
  const [bootErr, setBootErr] = useState<string | null>(null)

  const boot = async () => {
    setBootErr(null)
    try {
      const [h, s, r, m, p] = await Promise.all([api.health(), api.status(), api.riders(), api.modes(), api.presets()])
      setHealth(h); setStatus(s); setRiders(r); setModes(m); setPresets(p)
    } catch (e) {
      setHealth(null); setBootErr(errText(e))
    }
  }
  useEffect(() => { void boot() }, [])
  useEffect(() => {
    const id = window.setInterval(() => { api.health().then(setHealth).catch(() => setHealth(null)) }, 5000)
    return () => window.clearInterval(id)
  }, [])

  // ---- controls --------------------------------------------------------
  const [riderPick, setRiderKey] = useState<string | null>(null)
  const riderKey = riderPick ?? riders[0]?.key ?? 'userA'
  const [thrill, setThrill] = useState(0.5)
  const [modeSel, setModeSel] = useState('flow')
  const [customText, setCustomText] = useState(CUSTOM_EXAMPLE)
  const mode = modeSel === 'custom' ? customText.trim() : modeSel
  const [startPick, setStart] = useState<[number, number] | null>(null)
  const [destPick, setDest] = useState<[number, number] | null>(null)
  const [pick, setPick] = useState<'start' | 'dest' | null>(null)
  const start = startPick ?? presets?.routes[0]?.a ?? null
  const dest = destPick ?? presets?.routes[0]?.b ?? null
  const rider = riders.find((r) => r.key === riderKey) ?? null

  // ---- active plan -----------------------------------------------------
  const [active, setActive] = useState<Plan | null>(null)
  const [activeErr, setActiveErr] = useState<string | null>(null)
  const [planning, setPlanning] = useState(false)
  const [activeLabel, setActiveLabel] = useState('')

  const outside = useMemo(() => {
    const bad: string[] = []
    if (start && !inCoverage(start[0], start[1])) bad.push(`start ${start[0].toFixed(3)}, ${start[1].toFixed(3)}`)
    if (dest && !inCoverage(dest[0], dest[1])) bad.push(`destination ${dest[0].toFixed(3)}, ${dest[1].toFixed(3)}`)
    return bad
  }, [start, dest])

  const plan = async () => {
    if (!start || !dest) return
    setPlanning(true); setActiveErr(null); setReroute(null); setSelected(null)
    try {
      const p = await api.route(start, dest, riderKey, thrill, mode)
      if (!p.ok) { setActive(null); setActiveErr(p.note || 'The engine returned no route.'); return }
      setActive(p); setActiveLabel(`${mode} @ ${thrill.toFixed(2)}`); setT(0); setPlaying(false)
    } catch (e) { setActive(null); setActiveErr(errText(e)) }
    finally { setPlanning(false) }
  }

  // ---- simulated ride --------------------------------------------------
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(120)
  const summary = summaryOf(active)
  const cum = useMemo(() => (active?.path ? cumulativeKm(active.path) : [0]), [active])
  const riderPos = useMemo(() => (active?.path?.length ? pointAt(active.path, cum, t) : null), [active, cum, t])
  const raf = useRef<number | null>(null)
  const last = useRef<number>(0)
  useEffect(() => {
    if (!playing || !active || !summary.minutes) return
    const totalMs = (summary.minutes * 60 * 1000) / speed
    const step = (now: number) => {
      const dt = last.current ? now - last.current : 0
      last.current = now
      setT((v) => {
        const n = v + dt / totalMs
        if (n >= 1) { setPlaying(false); return 1 }
        return n
      })
      raf.current = requestAnimationFrame(step)
    }
    last.current = 0
    raf.current = requestAnimationFrame(step)
    return () => { if (raf.current) cancelAnimationFrame(raf.current) }
  }, [playing, speed, active, summary.minutes])

  // ---- reroute fan-out -------------------------------------------------
  const [change, setChange] = useState<Change>('avoid_this_road')
  const [reroute, setReroute] = useState<RerouteResult | null>(null)
  const [rerouteErr, setRerouteErr] = useState<string | null>(null)
  const [rerouting, setRerouting] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)

  const doReroute = async () => {
    if (!riderPos || !active) return
    setRerouting(true); setRerouteErr(null); setPlaying(false)
    try {
      const res = await api.rerouteCandidates({
        lat: riderPos.point[1], lon: riderPos.point[0], rider_key: riderKey, thrill, mode, change,
        destination: dest, current_cells: active.cells ?? [],
      })
      setReroute(res)
      const win = res.candidates.find((c) => c.verdict === 'accepted')
      setSelected(win ? win.index : null)
    } catch (e) {
      setReroute(null)
      const b = e instanceof ApiError ? (e.body as { candidates?: Candidate[]; tried?: unknown } | null) : null
      setRerouteErr(errText(e) + (b?.candidates ? ` (${b.candidates.length} variants planned, none usable)` : ''))
    } finally { setRerouting(false) }
  }

  const selectedCand = reroute?.candidates.find((c) => c.index === selected) ?? null
  const follow = () => {
    if (!selectedCand?.ok || !riderPos) return
    setStart([riderPos.point[1], riderPos.point[0]])
    setActive(candidateAsPlan(selectedCand))
    setActiveLabel(`${selectedCand.mode} @ ${selectedCand.thrill.toFixed(2)} (re-planned from live position)`)
    setThrill(selectedCand.thrill)
    if (selectedCand.mode.startsWith('custom:')) { setModeSel('custom'); setCustomText(selectedCand.mode) } else setModeSel(selectedCand.mode)
    setReroute(null); setSelected(null); setT(0)
  }

  const shownPlan: Plan | null = selectedCand ? candidateAsPlan(selectedCand) : active
  const shownSummary = summaryOf(shownPlan)
  const backendUp = !!health
  const engineIsMock = !!status?.mock || (health?.engine ?? '').includes('mock')

  return (
    <div className="grid h-full grid-cols-[320px_1fr_360px] grid-rows-[48px_1fr]">
      {/* header */}
      <header className="col-span-3 flex items-center justify-between border-b border-raised/70 bg-panel px-4">
        <div className="flex items-baseline gap-3">
          <span className="text-[15px] font-semibold tracking-tight">FLOWSTATE</span>
          <span className="text-ash">route engine viewer</span>
        </div>
        <div className="flex items-center gap-3 text-[12px]">
          <span className={`inline-block h-2 w-2 rounded-full ${backendUp ? 'bg-[#3ED598]' : 'bg-mred'}`} />
          {backendUp ? <span>backend up · engine <span className="font-mono">{health?.engine}</span></span> : <span className="text-mred">backend unreachable</span>}
          {engineIsMock ? <span className="rounded bg-[#F5A524]/20 px-2 py-0.5 text-[#F5A524]">MOCK ENGINE — geometry and figures are deterministic stand-ins, not crowd data</span> : null}
          {status?.cells ? <span className="text-ash">{status.cells} cells · {status.edges} edges</span> : null}
        </div>
      </header>

      {/* left: controls */}
      <aside className="overflow-y-auto border-r border-raised/70 bg-panel">
        {bootErr ? (
          <div className="p-4"><Notice kind="error">{bootErr}<br /><button className="mt-2 underline" onClick={() => void boot()}>retry</button></Notice></div>
        ) : null}

        <Section title="Rider">
          <div className="flex flex-wrap gap-1.5">
            {riders.map((r) => <Chip key={r.key} active={r.key === riderKey} onClick={() => setRiderKey(r.key)}>{String(r.label ?? r.key)}</Chip>)}
          </div>
          {rider ? (
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              <Stat label="skill" value={fmt(rider.skill)} unit="°" />
              <Stat label="sigma" value={fmt(rider.sigma)} unit="°" />
              <Stat label="gate" value={fmt(rider.gate)} unit="°" tone="red" />
              <Stat label="hardest ridden" value={fmt(rider.hardest_ridden)} unit="°" />
              <Stat label="gate agreement" value={pct(rider.gate_agreement)} />
              <Stat label="grip p95" value={pct(rider.grip_p95)} />
            </div>
          ) : null}
          <p className="mt-2 text-[11px] leading-snug text-ash">gate = skill + 2σ. Roads whose crowd p90 lean demand exceeds the gate are deleted from the graph, not penalised.</p>
        </Section>

        <Section title="Thrill dial" right={<span className="font-mono text-mlight">{thrill.toFixed(2)}</span>}>
          <input type="range" min={0.15} max={0.9} step={0.01} value={thrill} onChange={(e) => setThrill(Number(e.target.value))} className="w-full" />
          <div className="mt-1.5 flex gap-1.5">
            {Object.entries(presets?.dial ?? {}).map(([k, v]) => <Chip key={k} active={Math.abs(thrill - v) < 0.005} onClick={() => setThrill(v)}>{k} {v.toFixed(2)}</Chip>)}
          </div>
        </Section>

        <Section title="Mode">
          <div className="flex flex-wrap gap-1.5">
            {modes.map((m) => (
              <Chip key={m.key} active={modeSel === m.key} disabled={!m.offered} onClick={() => setModeSel(m.key)}
                title={`${m.verdict}${m.offered ? '' : ' — not offered by the mode scan'}`}>
                {m.key}{!m.offered ? ` (${m.verdict})` : ''}
              </Chip>
            ))}
            <Chip active={modeSel === 'custom'} onClick={() => setModeSel('custom')}>custom:</Chip>
          </div>
          {modeSel === 'custom' ? (
            <div className="mt-2">
              <input value={customText} onChange={(e) => setCustomText(e.target.value)} spellCheck={false}
                className="w-full rounded-md border border-raised bg-void px-2 py-1.5 font-mono text-[12px] text-bone focus:border-accent focus:outline-none" />
              <p className="mt-1 text-[11px] leading-snug text-ash">Sent verbatim to the engine; whether it is accepted is decided by modes.custom_columns, and its answer is shown under Route.</p>
            </div>
          ) : null}
        </Section>

        <Section title="Route">
          <div className="flex flex-wrap gap-1.5">
            {(presets?.routes ?? []).map((r) => (
              <Chip key={r.key} active={!!start && !!dest && start[0] === r.a[0] && start[1] === r.a[1] && dest[0] === r.b[0] && dest[1] === r.b[1]}
                onClick={() => { setStart(r.a); setDest(r.b) }} title={r.why}>{r.label}</Chip>
            ))}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-1.5 text-[12px]">
            <button type="button" onClick={() => setPick(pick === 'start' ? null : 'start')}
              className={`rounded-md border px-2 py-1.5 text-left ${pick === 'start' ? 'border-accent' : 'border-raised'}`}>
              <div className="text-[10px] uppercase text-ash">A {pick === 'start' ? '· click map' : ''}</div>
              <div className="font-mono">{start ? `${start[0].toFixed(3)}, ${start[1].toFixed(3)}` : '—'}</div>
            </button>
            <button type="button" onClick={() => setPick(pick === 'dest' ? null : 'dest')}
              className={`rounded-md border px-2 py-1.5 text-left ${pick === 'dest' ? 'border-accent' : 'border-raised'}`}>
              <div className="text-[10px] uppercase text-ash">B {pick === 'dest' ? '· click map' : ''}</div>
              <div className="font-mono">{dest ? `${dest[0].toFixed(3)}, ${dest[1].toFixed(3)}` : '—'}</div>
            </button>
          </div>
          {outside.length ? (
            <div className="mt-2"><Notice kind="warn">Outside the covered box (lat {COVERAGE.lat[0]}–{COVERAGE.lat[1]}, lon {COVERAGE.lon[0]}–{COVERAGE.lon[1]}): {outside.join('; ')}. The engine has no cells there, so nothing will be drawn.</Notice></div>
          ) : null}
          <button type="button" onClick={() => void plan()} disabled={!backendUp || planning || !start || !dest}
            className="mt-2 w-full rounded-md bg-accent px-3 py-2 text-[13px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40">
            {planning ? 'planning…' : 'Plan route'}
          </button>
          {activeErr ? <div className="mt-2"><Notice kind="error">{activeErr}</Notice></div> : null}
          {active?.explain?.length ? (
            <ul className="mt-2 space-y-1 text-[11.5px] leading-snug text-ash">
              {active.explain.map((l, i) => <li key={i} className={l.startsWith('    ') ? 'pl-3 text-mred' : ''}>{l.trim()}</li>)}
            </ul>
          ) : null}
        </Section>
      </aside>

      {/* centre: map + timeline */}
      <main className="relative">
        <RouteMap active={active} candidates={reroute?.candidates ?? []} selected={selected} onSelect={setSelected}
          rider={riderPos?.point ?? null} start={start} dest={dest} coverage={COVERAGE}
          onPick={pick ? (lat, lon) => { const p: [number, number] = [Number(lat.toFixed(4)), Number(lon.toFixed(4))]; if (pick === 'start') setStart(p); else setDest(p); setPick(null) } : undefined} />

        {!backendUp ? (
          <div className="pointer-events-none absolute inset-0 z-[500] flex items-center justify-center bg-void/70">
            <div className="rounded-lg border border-mred/60 bg-panel px-6 py-4 text-center">
              <div className="text-[15px] font-semibold text-mred">Backend unreachable</div>
              <div className="mt-1 text-ash">Nothing is drawn without a live engine response.<br />Start it with <span className="font-mono text-bone">cd flowstate && FLOWSTATE_MOCK=1 ./run_api.sh</span></div>
            </div>
          </div>
        ) : null}

        {reroute?.candidates.length ? (
          <div className="absolute left-3 top-3 z-[500] rounded-md border border-raised bg-panel/90 px-3 py-2 text-[11.5px] backdrop-blur">
            <div className="mb-1 text-ash">{reroute.candidates.length} deterministic engine passes · “{CHANGES.find((c) => c.key === reroute.reroute.change)?.label}”</div>
            {reroute.candidates.map((c) => (
              <div key={c.index} className="flex items-center gap-2">
                <span className="inline-block h-0.5 w-4" style={{ background: CAND_COLORS[c.index % CAND_COLORS.length], opacity: c.verdict === 'accepted' ? 1 : 0.7 }} />
                <span className="font-mono">#{c.index + 1}</span> {c.mode} @ {c.thrill.toFixed(2)} <span className={c.verdict === 'accepted' ? 'text-[#3ED598]' : 'text-ash'}>{c.verdict}</span>
              </div>
            ))}
            <div className="mt-1 flex items-center gap-2"><span className="inline-block h-1 w-4 bg-accent" /> active route</div>
          </div>
        ) : null}

        <div className="absolute bottom-3 left-3 right-3 z-[500] rounded-lg border border-raised bg-panel/90 px-4 py-3 backdrop-blur">
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => setPlaying((p) => !p)} disabled={!active}
              className="h-9 w-9 rounded-full bg-accent text-white disabled:opacity-40" aria-label={playing ? 'pause' : 'play'}>
              {playing ? '❚❚' : '▶'}
            </button>
            <input type="range" min={0} max={1000} value={Math.round(t * 1000)} onChange={(e) => { setT(Number(e.target.value) / 1000) }}
              disabled={!active} className="flex-1" aria-label="timeline" />
            <div className="flex gap-1">
              {SPEEDS.map((s) => <Chip key={s} active={speed === s} onClick={() => setSpeed(s)}>{s}×</Chip>)}
            </div>
            <div className="w-[300px] grid grid-cols-3 gap-1.5">
              <Stat label="elapsed" value={summary.minutes != null ? fmt(summary.minutes * t, 0) : '—'} unit="min" />
              <Stat label="km left" value={summary.km != null ? fmt(summary.km * (1 - t)) : '—'} unit="km" tone="blue" />
              <Stat label="min left" value={summary.minutes != null ? fmt(summary.minutes * (1 - t), 0) : '—'} unit="min" tone="blue" />
            </div>
            <button type="button" onClick={() => void doReroute()} disabled={!active || rerouting || !riderPos}
              className="rounded-md border border-mlight/60 px-3 py-2 text-[12px] font-semibold text-mlight transition-colors hover:bg-mlight/10 disabled:opacity-40">
              {rerouting ? 'planning…' : 'Re-plan from here'}
            </button>
          </div>
          <div className="mt-1.5 flex justify-between text-[10.5px] text-ash">
            <span>{active ? `active: ${activeLabel} · ${fmt(summary.km)} km · ${fmt(summary.minutes, 0)} min from the engine` : 'no active route'}{riderPos ? ` · rider at ${riderPos.point[1].toFixed(4)}, ${riderPos.point[0].toFixed(4)}` : ''}</span>
            <span>remaining = engine total × share of the line still ahead (simulated position, not GPS)</span>
          </div>
        </div>
      </main>

      {/* right: candidates + safety gate */}
      <aside className="overflow-y-auto border-l border-raised/70 bg-panel">
        <Section title="Re-plan" right={<span className="text-[10px] text-ash">deterministic passes, not agents</span>}>
          <div className="flex flex-wrap gap-1.5">
            {CHANGES.map((c) => <Chip key={c.key} active={change === c.key} onClick={() => setChange(c.key)} title={c.order}>{c.label}</Chip>)}
          </div>
          <p className="mt-1.5 text-[11px] leading-snug text-ash">{CHANGES.find((c) => c.key === change)?.order}. Every variant is planned from the rider's live position; the winner is exactly the one the phone's tool would return.</p>
          {rerouteErr ? <div className="mt-2"><Notice kind="error">{rerouteErr}</Notice></div> : null}
          {reroute ? (
            <div className="mt-2 text-[11.5px] text-ash">
              from {reroute.reroute.from[0].toFixed(4)}, {reroute.reroute.from[1].toFixed(4)} → {reroute.reroute.destination ? `${reroute.reroute.destination[0]}, ${reroute.reroute.destination[1]}` : 'loop'} ·
              winner {reroute.reroute.mode_to} @ {reroute.reroute.thrill_to} · shared road {pct(reroute.reroute.shares_current_road)}
            </div>
          ) : null}
        </Section>

        {reroute ? (
          <Section title={`Candidates (${reroute.candidates.length})`}>
            <div className="space-y-1.5">
              {reroute.candidates.map((c) => {
                const color = CAND_COLORS[c.index % CAND_COLORS.length]
                const isSel = c.index === selected
                return (
                  <button type="button" key={c.index} onClick={() => setSelected(isSel ? null : c.index)}
                    className={`w-full rounded-md border p-2.5 text-left transition-all duration-200 ${isSel ? 'border-transparent bg-raised' : 'border-raised/70 hover:border-ash/60'}`}
                    style={isSel ? { boxShadow: `inset 3px 0 0 ${color}` } : undefined}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
                        <span className="font-mono text-[12px]">#{c.index + 1}</span>
                        <span className="font-semibold">{c.mode}</span>
                        <span className="text-ash">@ {c.thrill.toFixed(2)}</span>
                      </div>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${c.verdict === 'accepted' ? 'bg-[#3ED598]/20 text-[#3ED598]' : c.verdict === 'failed' ? 'bg-mred/20 text-mred' : 'bg-raised text-ash'}`}>
                        {c.verdict.replace('_', ' ')}
                      </span>
                    </div>
                    {c.ok ? (
                      <div className="mt-1.5 grid grid-cols-4 gap-1 font-mono text-[12px]">
                        <span>{fmt(c.km)} <span className="text-ash">km</span></span>
                        <span>{fmt(c.minutes, 0)} <span className="text-ash">min</span></span>
                        <span>{fmt(c.fun_score, 0)} <span className="text-ash">fun</span></span>
                        <span>{pct(c.shares_current_road)} <span className="text-ash">shared</span></span>
                      </div>
                    ) : null}
                    <div className="mt-1 text-[11px] leading-snug text-ash">{c.why}</div>
                    {c.refusals.length ? <div className="mt-1 text-[11px] text-mred">{c.refusals.length} road(s) refused near this line</div> : null}
                  </button>
                )
              })}
            </div>
            {selectedCand?.ok ? (
              <button type="button" onClick={follow}
                className="mt-2 w-full rounded-md px-3 py-2 text-[13px] font-semibold text-void transition-opacity hover:opacity-90"
                style={{ background: CAND_COLORS[selectedCand.index % CAND_COLORS.length] }}>
                Follow candidate #{selectedCand.index + 1} from here
              </button>
            ) : null}
            <p className="mt-1.5 text-[10.5px] leading-snug text-ash">fun_score is only comparable at the same dial setting (router.py). Shared road = engine's cell overlap with the route being ridden.{engineIsMock ? ' The mock engine numbers its cells c0…cN on every line, so shared-road is not meaningful here and mode is ignored.' : ''}</p>
          </Section>
        ) : null}

        <Section title={selectedCand ? `Route figures · candidate #${selectedCand.index + 1}` : 'Route figures · active route'}>
          {shownPlan ? (
            <div className="grid grid-cols-3 gap-1.5">
              <Stat label="km" value={fmt(shownSummary.km)} />
              <Stat label="minutes" value={fmt(shownSummary.minutes, 0)} />
              <Stat label="fun score" value={fmt(shownSummary.fun_score, 0)} />
              <Stat label="mean demand" value={fmt(shownSummary.mean_demand)} unit="°" />
              <Stat label="max demand" value={fmt(shownSummary.max_demand)} unit="°" tone={shownSummary.max_demand != null && shownSummary.gate_deg != null && shownSummary.max_demand > shownSummary.gate_deg ? 'red' : undefined} />
              <Stat label="gate" value={fmt(shownSummary.gate_deg)} unit="°" tone="red" />
              <Stat label="peak flow" value={fmt(shownSummary.peak_flow, 2)} />
              <Stat label="mean flow" value={fmt(shownSummary.mean_flow, 2)} />
              <Stat label="grip p95" value={pct(shownSummary.grip_lat_p95)} />
            </div>
          ) : <p className="text-ash">Plan a route to see the engine's figures.</p>}
        </Section>

        <Section title="Safety gate" right={rider ? <span className="font-mono text-[11px] text-mred">gate {fmt(rider.gate)}° = {fmt(rider.skill)} + 2×{fmt(rider.sigma)}</span> : null}>
          {shownPlan ? (
            shownPlan.refusals.length ? (
              <ul className="space-y-1.5">
                {shownPlan.refusals.map((r, i) => (
                  <li key={i} className="rounded-md border border-mred/40 bg-mred/5 px-2.5 py-2 text-[11.5px] leading-snug">
                    <div className="flex justify-between font-mono text-[11px] text-ash"><span>cell {r.cell}</span><span>{r.lat.toFixed(4)}, {r.lon.toFixed(4)}</span></div>
                    <div className="mt-0.5">{r.reason}</div>
                    <div className="mt-0.5 font-mono text-mred">demand {fmt(r.demand)}°</div>
                  </li>
                ))}
              </ul>
            ) : <p className="text-ash">{shownSummary.n_refused_nearby === 0 ? 'The engine refused no roads near this line.' : 'No refusals returned for this plan.'}</p>
          ) : <p className="text-ash">Refusals appear here once a plan is loaded: roads the gate deleted from the graph, with the engine's written reason.</p>}
        </Section>
      </aside>
    </div>
  )
}
