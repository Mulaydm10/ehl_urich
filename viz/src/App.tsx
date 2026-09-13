import { useEffect, useMemo, useRef, useState } from 'react'
import RouteMap, { CAND_COLORS } from './components/RouteMap'
import { Activity, FlaskConical, Flag, Gauge, GitFork, Layers, Loader2, MapPin, Mic, Pause, Play, Plus, Route, ShieldAlert, ShieldCheck, SlidersHorizontal, Smartphone, User, WifiOff, X } from 'lucide-react'
import { Bar, Chip, Notice, Section, Stat, Verdict, fmt, pct } from './components/ui'
import {
  ApiError, COVERAGE, api, inCoverage, planFromResult, summaryOf,
  type Candidate, type Feed, type FeedEvent, type Health, type Mode, type Plan, type Presets, type RerouteResult, type Rider, type Status,
} from './lib/api'
import { cumulativeKm, nearestIndex, pointAt } from './lib/geo'

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
const MAX_VIA = 6 // flowstate/app/via.py MAX_VIA
const FEED_POLL_MS = 1000
const STEP_MS = 1300
const sleep = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms))

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
  const backendUp = !!health
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
  const [pick, setPick] = useState<'start' | 'dest' | 'via' | null>(null)
  // Stops on the way, in the order the rider added them. The engine plans one
  // leg per pair and never reorders them (flowstate/app/via.py).
  const [via, setVia] = useState<[number, number][]>([])
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
    via.forEach((v, i) => { if (!inCoverage(v[0], v[1])) bad.push(`stop ${i + 1} ${v[0].toFixed(3)}, ${v[1].toFixed(3)}`) })
    return bad
  }, [start, dest, via])

  const planWith = async (stops: [number, number][]) => {
    if (!start || !dest) return
    setPlanning(true); setActiveErr(null); setReroute(null); setSelected(null)
    try {
      const p = stops.length
        ? await api.routeVia([start, ...stops, dest], riderKey, thrill, mode)
        : await api.route(start, dest, riderKey, thrill, mode)
      if (!p.ok) { setActive(null); setActiveErr(p.note || 'The engine returned no route.'); return }
      setActive(p)
      setActiveLabel(`${mode} @ ${thrill.toFixed(2)}${stops.length ? ` · through ${stops.length} stop${stops.length === 1 ? '' : 's'}` : ''}`)
      setT(0); setPlaying(false)
    } catch (e) { setActive(null); setActiveErr(errText(e)) }
    finally { setPlanning(false) }
  }
  const plan = () => planWith(via)

  // Adding or removing a stop re-plans immediately, the way Navigate does on
  // the phone: the line on screen always matches the list of stops.
  const setStops = (next: [number, number][]) => {
    setVia(next)
    if (active || activeErr) void planWith(next)
  }

  // ---- phone feed state (logic below, after the reroute state it drives)
  const [feed, setFeed] = useState<Feed | null>(null)
  const [events, setEvents] = useState<FeedEvent[]>([])
  const [followPhone, setFollowPhone] = useState(true)
  const [stage, setStage] = useState<string | null>(null)
  const seq = useRef(0)
  const queue = useRef<Promise<void>>(Promise.resolve())
  const phoneRide = feed?.ride ?? null
  const following = followPhone && !!feed?.phone_live && !!phoneRide

  // ---- simulated ride --------------------------------------------------
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(120)
  const summary = summaryOf(active)
  const cum = useMemo(() => (active?.path ? cumulativeKm(active.path) : [0]), [active])
  const simPos = useMemo(() => (active?.path?.length ? pointAt(active.path, cum, t) : null), [active, cum, t])
  const raf = useRef<number | null>(null)
  const last = useRef<number>(0)
  useEffect(() => {
    if (!playing || !active || !summary.minutes || following) return
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
  }, [playing, speed, active, summary.minutes, following])

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

  // ---- phone feed: the ride the phone is on and the tools its assistant ran
  // (voice or typed). Polled from /api/viz/feed; every position and plan
  // shown in this mode is what the phone posted / the engine returned.
  const onToolEvent = async (ev: Extract<FeedEvent, { kind: 'tool' }>) => {
    const result = ev.result as { error?: string } | null
    const plan = planFromResult(ev.result)
    if (ev.tool === 'plan_route' || ev.tool === 'plan_loop') {
      if (!plan) return
      setReroute(null); setSelected(null); setRerouteErr(null)
      setActive(plan); setT(0); setPlaying(false)
      setActiveLabel(`${String(ev.args.mode ?? 'flow')} @ ${Number(ev.args.thrill ?? 0.5).toFixed(2)} — planned by the phone's assistant`)
      return
    }
    if (ev.tool !== 'reroute_from_here') return
    if (!plan?.reroute || !ev.ride) { setRerouteErr(result?.error ?? 'reroute returned no plan'); return }
    const m = plan.reroute
    setStage(`assistant asked for “${m.change}” — re-running the same search, keeping every candidate`)
    setRerouting(true); setRerouteErr(null); setPlaying(false)
    try {
      const res = await api.rerouteCandidates({
        lat: ev.ride.lat, lon: ev.ride.lon, rider_key: ev.ride.rider_key ?? 'userA',
        thrill: ev.ride.thrill ?? 0.5, mode: ev.ride.mode ?? 'flow', change: m.change,
        destination: m.destination, current_cells: ev.ride.route?.cells ?? [],
      })
      setReroute(res); setRerouting(false)
      for (const c of res.candidates) {
        setSelected(c.index)
        setStage(`pass ${c.index + 1}/${res.candidates.length}: ${c.mode} @ ${c.thrill.toFixed(2)} — ${c.verdict.replace('_', ' ')}`)
        await sleep(STEP_MS)
      }
      const win = res.candidates.find((c) => c.verdict === 'accepted') ?? null
      setSelected(win ? win.index : null)
      setStage(win ? `the phone follows pass ${win.index + 1}: ${m.mode_to} @ ${m.thrill_to.toFixed(2)}` : 'no candidate was usable')
      await sleep(STEP_MS)
      setActive(plan); setT(0)
      setActiveLabel(`${m.mode_to} @ ${m.thrill_to.toFixed(2)} — re-planned by voice${m.reason ? ` (“${m.reason}”)` : ''}`)
    } catch (e) {
      setReroute(null); setRerouteErr(errText(e))
    } finally { setRerouting(false); setStage(null) }
  }

  useEffect(() => {
    if (!backendUp) return
    let stop = false
    const poll = async () => {
      try {
        const f = await api.feed(seq.current)
        if (stop) return
        setFeed(f)
        if (f.events.length) {
          seq.current = f.seq
          setEvents((prev) => [...prev, ...f.events].slice(-40))
          for (const ev of f.events) if (ev.kind === 'tool') queue.current = queue.current.then(() => onToolEvent(ev))
        }
      } catch { if (!stop) setFeed(null) }
    }
    void poll()
    const id = window.setInterval(() => void poll(), FEED_POLL_MS)
    return () => { stop = true; window.clearInterval(id) }
  }, [backendUp]) // eslint-disable-line react-hooks/exhaustive-deps

  // The phone's own route, when we have no plan from a tool call yet.
  useEffect(() => {
    if (!following || active || !phoneRide?.route?.path?.length) return
    const r = phoneRide.route
    setActive({ ok: true, path: r.path, segments: r.segments ?? [], refusals: r.refusals ?? [], summary: [], cells: [] })
    setActiveLabel(`${phoneRide.mode} @ ${phoneRide.thrill.toFixed(2)} — route the phone reports it is following`)
  }, [following, active, phoneRide])

  const riderPos = useMemo(() => {
    if (!following || !phoneRide) return simPos
    const point: [number, number] = [phoneRide.lon, phoneRide.lat]
    return { point, index: active?.path?.length ? nearestIndex(active.path, point) : 0 }
  }, [following, phoneRide, simPos, active])

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
  const engineIsMock = !!status?.mock || (health?.engine ?? '').includes('mock')

  const progressPct = Math.round(t * 100)
  const thrillTone = thrill < 0.35 ? 'text-mint' : thrill < 0.7 ? 'text-amber' : 'text-mred'

  return (
    <div className="grid h-full grid-cols-[328px_1fr_372px] grid-rows-[52px_1fr]">
      {/* header */}
      <header className="hairline col-span-3 flex items-center justify-between border-b bg-panel/80 px-4 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-mlight to-accent shadow-glow">
            <Route size={15} strokeWidth={2.4} className="text-white" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-semibold tracking-tight">FLOWSTATE</span>
            <span className="text-ash">route engine viewer</span>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[12px]">
          <span className={`hairline inline-flex items-center gap-2 rounded-full border px-2.5 py-1 ${backendUp ? 'bg-mint/10 text-mint' : 'bg-mred/10 text-mred'}`}>
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${backendUp ? 'bg-mint animate-pulse2' : 'bg-mred'}`} />
            {backendUp ? <>backend up · <span className="font-mono">{health?.engine}</span></> : 'backend unreachable'}
          </span>
          {engineIsMock ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-amber/40 bg-amber/10 px-2.5 py-1 text-amber" title="Geometry and figures are deterministic stand-ins, not crowd data">
              <FlaskConical size={12} /> mock engine · synthetic geometry
            </span>
          ) : null}
          {backendUp ? (
            <span className={`hairline inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${feed?.phone_live ? 'bg-mlight/10 text-mlight' : 'text-dim'}`}
              title="From /api/copilot/tick: the phone posts its position every few seconds while navigating">
              <Smartphone size={12} />
              {feed?.phone_live ? <>phone riding · <span className="tabular font-mono">{phoneRide?.speed_kmh != null ? `${fmt(phoneRide.speed_kmh, 0)} km/h` : '—'}</span></>
                : feed?.ride_age_s != null ? `phone last seen ${fmt(feed.ride_age_s, 0)} s ago` : 'no phone connected'}
            </span>
          ) : null}
          {status?.cells ? <span className="tabular font-mono text-[11px] text-dim">{status.cells.toLocaleString()} cells · {status.edges?.toLocaleString()} edges</span> : null}
        </div>
      </header>

      {/* left: controls */}
      <aside className="hairline overflow-y-auto border-r bg-panel/60">
        {bootErr ? (
          <div className="p-4"><Notice kind="error">{bootErr}<br /><button className="mt-1 underline" onClick={() => void boot()}>retry</button></Notice></div>
        ) : null}

        <Section title="Phone" icon={Mic} tone="blue" right={
          <button type="button" onClick={() => setFollowPhone((v) => !v)} className={`rounded-full px-2 py-0.5 text-[10.5px] transition-colors ${followPhone ? 'bg-mlight/15 text-mlight' : 'bg-raised/60 text-dim'}`}>
            {followPhone ? 'following phone' : 'follow phone: off'}
          </button>}>
          <p className="text-[11px] leading-snug text-dim">
            {following
              ? <>Position and route come from the phone's live reports; the timeline below is off. When the rider talks to the assistant, its tool calls appear here and the map replays the engine's search on its own.</>
              : feed?.ride ? <>The phone's last report is {fmt(feed.ride_age_s, 0)} s old, so the simulated rider is shown instead. Assistant tool calls still arrive here.</>
              : <>Waiting for the phone: nothing arrives until it navigates (position reports) or the rider uses the assistant. Meanwhile the controls below drive a simulated ride.</>}
          </p>
          {events.length ? (
            <ul className="mt-2 max-h-[200px] space-y-1.5 overflow-y-auto pr-1">
              {[...events].reverse().slice(0, 12).map((ev) => (
                <li key={ev.seq} className="hairline animate-rise rounded-lg border bg-void/50 px-2.5 py-1.5 text-[11.5px]">
                  {ev.kind === 'say' ? (
                    <>
                      <div className="flex items-center gap-1.5 text-mlight"><Mic size={11} /> <span className="truncate">“{ev.text}”</span></div>
                      {ev.say ? <div className="mt-0.5 text-ash">→ {ev.say}</div> : null}
                      {ev.tools_used.length ? <div className="mt-0.5 font-mono text-[10.5px] text-dim">{ev.tools_used.join(', ')}</div> : null}
                    </>
                  ) : (
                    <>
                      <div className="flex items-center gap-1.5"><GitFork size={11} className="text-amber" /> <span className="font-mono">{ev.tool}</span>
                        <span className="ml-auto text-[10px] text-dim">{ev.source === 'tool' ? 'live voice' : 'typed / chat'}</span></div>
                      {Object.keys(ev.args).length ? <div className="mt-0.5 break-all font-mono text-[10.5px] text-dim">{JSON.stringify(ev.args)}</div> : null}
                      {(() => { const r = ev.result as { error?: string } | null; return r?.error ? <div className="mt-0.5 text-mred">{r.error}</div> : null })()}
                    </>
                  )}
                </li>
              ))}
            </ul>
          ) : null}
        </Section>

        <Section title="Rider" icon={User}>
          <div className="flex flex-wrap gap-1.5">
            {riders.map((r) => <Chip key={r.key} active={r.key === riderKey} onClick={() => setRiderKey(r.key)}>{String(r.label ?? r.key)}</Chip>)}
          </div>
          {rider ? (
            <div className="mt-2.5 grid grid-cols-3 gap-1.5">
              <Stat label="skill" value={fmt(rider.skill)} unit="°" />
              <Stat label="sigma" value={fmt(rider.sigma)} unit="°" />
              <Stat label="gate" value={fmt(rider.gate)} unit="°" tone="red" />
              <Stat label="hardest ridden" value={fmt(rider.hardest_ridden)} unit="°" />
              <Stat label="gate agreement" value={pct(rider.gate_agreement)} />
              <Stat label="grip p95" value={pct(rider.grip_p95)} />
            </div>
          ) : (
            <div className="mt-2.5 grid grid-cols-3 gap-1.5">{[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton h-[46px] rounded-lg" />)}</div>
          )}
          <p className="mt-2 text-[11px] leading-snug text-dim">gate = skill + 2σ. Roads whose crowd p90 lean demand exceeds the gate are deleted from the graph, not penalised.</p>
        </Section>

        <Section title="Thrill dial" icon={Gauge} right={<span className={`tabular font-mono text-[15px] font-semibold ${thrillTone}`}>{thrill.toFixed(2)}</span>}>
          <input type="range" min={0.15} max={0.9} step={0.01} value={thrill} onChange={(e) => setThrill(Number(e.target.value))} className="thrill w-full" aria-label="thrill dial" />
          <div className="mt-1.5 flex gap-1.5">
            {Object.entries(presets?.dial ?? {}).map(([k, v]) => <Chip key={k} active={Math.abs(thrill - v) < 0.005} onClick={() => setThrill(v)}>{k} <span className="font-mono opacity-70">{v.toFixed(2)}</span></Chip>)}
          </div>
        </Section>

        <Section title="Mode" icon={SlidersHorizontal}>
          <div className="flex flex-wrap gap-1.5">
            {modes.map((m) => (
              <Chip key={m.key} active={modeSel === m.key} disabled={!m.offered} onClick={() => setModeSel(m.key)}
                title={`${m.verdict}${m.offered ? '' : ' — not offered by the mode scan'}`}>
                {m.key}{!m.offered ? ` (${m.verdict})` : ''}
              </Chip>
            ))}
            <Chip active={modeSel === 'custom'} onClick={() => setModeSel('custom')} color="#C77DFF"><span className="font-mono">custom:</span></Chip>
          </div>
          {modeSel === 'custom' ? (
            <div className="mt-2 animate-rise">
              <input value={customText} onChange={(e) => setCustomText(e.target.value)} spellCheck={false}
                className="hairline w-full rounded-lg border bg-void/70 px-2.5 py-2 font-mono text-[12px] text-bone transition-shadow focus:border-[#C77DFF]/60 focus:outline-none focus:ring-2 focus:ring-[#C77DFF]/20" />
              <p className="mt-1 text-[11px] leading-snug text-dim">Sent verbatim to the engine; whether it is accepted is decided by modes.custom_columns, and its answer is shown under Route.</p>
            </div>
          ) : null}
        </Section>

        <Section title="Route" icon={MapPin}>
          <div className="flex flex-wrap gap-1.5">
            {(presets?.routes ?? []).map((r) => (
              <Chip key={r.key} active={!!start && !!dest && start[0] === r.a[0] && start[1] === r.a[1] && dest[0] === r.b[0] && dest[1] === r.b[1]}
                onClick={() => { setStart(r.a); setDest(r.b) }} title={r.why}>{r.label}</Chip>
            ))}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-1.5 text-[12px]">
            {([['start', 'A', start, '#F1F2F3'], ['dest', 'B', dest, '#6DB6E8']] as const).map(([k, lab, val, col]: readonly [typeof pick, string, [number, number] | null, string]) => (
              <button type="button" key={k} onClick={() => setPick(pick === k ? null : k)}
                className={`hairline rounded-lg border px-2.5 py-2 text-left transition-all ${pick === k ? 'shadow-glow' : 'hover:border-ash/50'}`}>
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-dim">
                  <span className="grid h-4 w-4 place-items-center rounded font-bold text-void" style={{ background: col }}>{lab}</span>
                  {pick === k ? <span className="text-mlight animate-pulse2">click the map</span> : lab === 'A' ? 'start' : 'destination'}
                </div>
                <div className="tabular mt-1 font-mono">{val ? `${val[0].toFixed(3)}, ${val[1].toFixed(3)}` : '—'}</div>
              </button>
            ))}
          </div>
          {outside.length ? (
            <div className="mt-2"><Notice kind="warn">Outside the covered box (lat {COVERAGE.lat[0]}–{COVERAGE.lat[1]}, lon {COVERAGE.lon[0]}–{COVERAGE.lon[1]}): {outside.join('; ')}. The engine has no cells there, so nothing will be drawn.</Notice></div>
          ) : null}
          <button type="button" onClick={() => void plan()} disabled={!backendUp || planning || !start || !dest} className="btn-primary mt-2.5 w-full">
            <span className="inline-flex items-center justify-center gap-2">
              {planning ? <Loader2 size={14} className="animate-spin" /> : <Route size={14} />}
              {planning ? 'planning…' : via.length ? `Plan through ${via.length} stop${via.length === 1 ? '' : 's'}` : 'Plan route'}
            </span>
          </button>
          {activeErr ? <div className="mt-2"><Notice kind="error">{activeErr}</Notice></div> : null}
          <div className="hairline mt-2.5 rounded-lg border bg-void/40 p-2.5">
            <div className="flex items-center justify-between text-[11px] uppercase tracking-wider text-dim">
              <span className="inline-flex items-center gap-1.5"><Flag size={11} className="text-amber" /> stops on the way</span>
              <button type="button" onClick={() => setPick(pick === 'via' ? null : 'via')} disabled={via.length >= MAX_VIA}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] normal-case tracking-normal transition-colors disabled:opacity-40 ${pick === 'via' ? 'bg-amber/20 text-amber' : 'bg-raised/60 text-ash hover:text-bone'}`}>
                <Plus size={10} /> {pick === 'via' ? 'click the map' : 'add stop'}
              </button>
            </div>
            {via.length ? (
              <ul className="mt-2 space-y-1">
                {via.map((v, i) => (
                  <li key={`${i}-${v[0]}-${v[1]}`} className="hairline flex items-center gap-2 rounded-md border bg-raised/40 px-2 py-1 text-[11.5px]">
                    <span className="grid h-4 w-4 place-items-center rounded bg-amber font-mono text-[10px] font-bold text-void">{i + 1}</span>
                    <span className="tabular font-mono">{v[0].toFixed(3)}, {v[1].toFixed(3)}</span>
                    <span className="ml-auto tabular font-mono text-[10.5px] text-dim">{active?.legs?.[i] ? `leg ${fmt(active.legs[i].km)} km` : ''}</span>
                    <button type="button" onClick={() => setStops(via.filter((_, j) => j !== i))} disabled={planning}
                      className="text-dim transition-colors hover:text-mred disabled:opacity-40" aria-label={`remove stop ${i + 1}`}><X size={12} /></button>
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="mt-1.5 text-[11px] leading-snug text-dim">
              {via.length
                ? <>Each pair is one engine call (A→1→…→B) in the order you added them — nothing is reordered, and a leg that cannot be planned fails the whole route. Distance and time are the legs’ sums; the fun score is their distance-weighted mean, not a score for the whole line.</>
                : <>Up to {MAX_VIA} stops. Adding or removing one re-plans straight away; with none, the plain A→B call is used.</>}
            </p>
          </div>
          {active?.explain?.length ? (
            <ul className="hairline mt-2.5 space-y-1 rounded-lg border bg-void/40 px-3 py-2 text-[11.5px] leading-snug text-ash">
              {active.explain.map((l, i) => <li key={i} className={l.startsWith('    ') ? 'pl-3 text-mred' : ''}>{l.trim()}</li>)}
            </ul>
          ) : null}
        </Section>
      </aside>

      {/* centre: map + timeline */}
      <main className="relative">
        <RouteMap active={active} riddenIndex={riderPos?.index ?? 0} candidates={reroute?.candidates ?? []} selected={selected} onSelect={setSelected}
          rider={riderPos?.point ?? null} start={start} dest={dest} coverage={COVERAGE}
          via={via} onRemoveVia={(i) => setStops(via.filter((_, j) => j !== i))}
          onPick={pick ? (lat, lon) => {
            const p: [number, number] = [Number(lat.toFixed(4)), Number(lon.toFixed(4))]
            if (pick === 'start') setStart(p)
            else if (pick === 'dest') setDest(p)
            else setStops([...via, p])
            setPick(null)
          } : undefined} />

        {stage ? (
          <div className="glass pointer-events-none absolute left-1/2 top-3 z-[500] flex -translate-x-1/2 animate-rise items-center gap-2 rounded-full px-4 py-1.5 text-[12px]">
            <Mic size={12} className="text-mlight" /> <span className="text-bone">{stage}</span>
          </div>
        ) : null}
        {pick && !stage ? (
          <div className="glass pointer-events-none absolute left-1/2 top-3 z-[500] -translate-x-1/2 animate-rise rounded-full px-4 py-1.5 text-[12px]">
            Click the map to {pick === 'via' ? <>add <span className="font-semibold text-amber">stop {via.length + 1}</span></> : <>set <span className="font-semibold text-mlight">{pick === 'start' ? 'A · start' : 'B · destination'}</span></>}
          </div>
        ) : null}

        {!backendUp ? (
          <div className="pointer-events-none absolute inset-0 z-[500] flex items-center justify-center bg-void/70 backdrop-blur-sm">
            <div className="glass animate-rise max-w-[520px] rounded-2xl px-7 py-5 text-center">
              <WifiOff size={22} className="mx-auto text-mred" />
              <div className="mt-2 text-[16px] font-semibold text-mred">Backend unreachable</div>
              <div className="mt-1.5 text-ash">Nothing is drawn without a live engine response.</div>
              <div className="mt-2 space-y-1 text-[11.5px] text-dim">
                <div><span className="font-mono text-bone">cd flowstate && FLOWSTATE_MOCK=1 ./run_api.sh</span> (Mac)</div>
                <div><span className="font-mono text-bone">FLOWSTATE_MOCK=1 python3 -m uvicorn api:app --app-dir app --port 8090</span></div>
              </div>
            </div>
          </div>
        ) : null}

        {reroute?.candidates.length ? (
          <div className="glass absolute left-3 top-3 z-[500] animate-rise rounded-xl px-3.5 py-2.5 text-[11.5px]">
            <div className="mb-1.5 flex items-center gap-1.5 text-ash"><GitFork size={12} /> {reroute.candidates.length} deterministic engine passes · “{CHANGES.find((c) => c.key === reroute.reroute.change)?.label}”</div>
            {reroute.candidates.map((c) => (
              <button type="button" key={c.index} onClick={() => setSelected(c.index === selected ? null : c.index)}
                className={`flex w-full items-center gap-2 rounded-md px-1.5 py-0.5 text-left transition-colors ${c.index === selected ? 'bg-raised/80' : 'hover:bg-raised/50'}`}>
                <span className="inline-block h-[3px] w-5 rounded-full" style={{ background: CAND_COLORS[c.index % CAND_COLORS.length], opacity: c.verdict === 'accepted' ? 1 : 0.7 }} />
                <span className="tabular font-mono">#{c.index + 1}</span> {c.mode} <span className="font-mono text-dim">@ {c.thrill.toFixed(2)}</span>
                <span className={`ml-auto ${c.verdict === 'accepted' ? 'text-mint' : 'text-dim'}`}>{c.verdict.replace('_', ' ')}</span>
              </button>
            ))}
            <div className="mt-1.5 flex items-center gap-2 px-1.5 text-dim"><span className="inline-block h-[3px] w-5 rounded-full bg-accent" /> active route <span className="ml-3 inline-block h-[3px] w-5 rounded-full bg-bone" /> ridden</div>
          </div>
        ) : null}

        <div className="glass absolute bottom-3 left-3 right-3 z-[500] rounded-2xl px-4 py-3">
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => setPlaying((p) => !p)} disabled={!active || following}
              className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-gradient-to-b from-[#2a7be0] to-accent text-white shadow-glow transition-transform hover:scale-105 disabled:opacity-40 disabled:hover:scale-100"
              aria-label={playing ? 'pause' : 'play'}>
              {playing ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" className="ml-0.5" />}
            </button>
            <div className="flex flex-1 flex-col">
              <input type="range" min={0} max={1000} value={Math.round(t * 1000)} onChange={(e) => { setT(Number(e.target.value) / 1000) }}
                disabled={!active || following} className="w-full" aria-label="timeline" style={{ ['--fill' as string]: `${progressPct}%` }} />
              <div className="tabular -mt-1 flex justify-between font-mono text-[10px] text-dim">
                <span>0</span><span className="text-mlight">{progressPct}%</span><span>{summary.minutes != null ? `${fmt(summary.minutes, 0)} min` : '—'}</span>
              </div>
            </div>
            <div className="hairline flex overflow-hidden rounded-lg border">
              {SPEEDS.map((s) => (
                <button type="button" key={s} onClick={() => setSpeed(s)}
                  className={`tabular px-2.5 py-1.5 font-mono text-[11px] transition-colors ${speed === s ? 'bg-accent text-white' : 'text-ash hover:bg-raised/60'}`}>{s}×</button>
              ))}
            </div>
            {following ? (
              <div className="grid w-[320px] grid-cols-3 gap-1.5">
                <Stat label="speed" value={fmt(phoneRide?.speed_kmh, 0)} unit="km/h" />
                <Stat label="km left" value={fmt(phoneRide?.route?.remaining_km)} unit="km" tone="blue" />
                <Stat label="fix age" value={fmt(feed?.ride_age_s, 0)} unit="s" tone="blue" />
              </div>
            ) : (
              <div className="grid w-[320px] grid-cols-3 gap-1.5">
                <Stat label="elapsed" value={summary.minutes != null ? fmt(summary.minutes * t, 0) : '—'} unit="min" />
                <Stat label="km left" value={summary.km != null ? fmt(summary.km * (1 - t)) : '—'} unit="km" tone="blue" />
                <Stat label="min left" value={summary.minutes != null ? fmt(summary.minutes * (1 - t), 0) : '—'} unit="min" tone="blue" />
              </div>
            )}
            <button type="button" onClick={() => void doReroute()} disabled={!active || rerouting || !riderPos} className="btn-ghost shrink-0">
              <span className="inline-flex items-center gap-1.5">{rerouting ? <Loader2 size={13} className="animate-spin" /> : <GitFork size={13} />}{rerouting ? 'planning…' : 'Re-plan from here'}</span>
            </button>
          </div>
          <div className="mt-1.5 flex justify-between text-[10.5px] text-dim">
            <span>{active ? <>active: <span className="text-ash">{activeLabel}</span> · {fmt(summary.km)} km · {fmt(summary.minutes, 0)} min from the engine</> : 'no active route'}{riderPos ? <> · rider at <span className="tabular font-mono">{riderPos.point[1].toFixed(4)}, {riderPos.point[0].toFixed(4)}</span></> : ''}</span>
            <span>{following ? 'position and km left are what the phone reported (GPS + its own remaining_km)' : 'remaining = engine total × share of the line still ahead (simulated position, not GPS)'}</span>
          </div>
        </div>
      </main>

      {/* right: candidates + safety gate */}
      <aside className="hairline overflow-y-auto border-l bg-panel/60">
        <Section title="Re-plan" icon={GitFork} right={<span className="text-[10px] text-dim">deterministic passes, not agents</span>}>
          <div className="flex flex-wrap gap-1.5">
            {CHANGES.map((c) => <Chip key={c.key} active={change === c.key} onClick={() => setChange(c.key)} title={c.order}>{c.label}</Chip>)}
          </div>
          <p className="mt-2 text-[11px] leading-snug text-dim">{CHANGES.find((c) => c.key === change)?.order}. Every variant is planned from the rider's live position; the winner is exactly the one the phone's tool would return.</p>
          {rerouteErr ? <div className="mt-2"><Notice kind="error">{rerouteErr}</Notice></div> : null}
          {reroute ? (
            <div className="hairline mt-2 rounded-lg border bg-void/40 px-3 py-2 text-[11.5px] text-ash">
              <div>from <span className="tabular font-mono text-bone">{reroute.reroute.from[0].toFixed(4)}, {reroute.reroute.from[1].toFixed(4)}</span> → {reroute.reroute.destination ? <span className="tabular font-mono text-bone">{reroute.reroute.destination[0]}, {reroute.reroute.destination[1]}</span> : 'loop'}</div>
              <div>winner <span className="text-bone">{reroute.reroute.mode_to} @ {reroute.reroute.thrill_to}</span> · shared road {pct(reroute.reroute.shares_current_road)}</div>
            </div>
          ) : null}
        </Section>

        {reroute ? (
          <Section title={`Candidates (${reroute.candidates.length})`} icon={Layers}>
            <div className="space-y-2">
              {reroute.candidates.map((c) => {
                const color = CAND_COLORS[c.index % CAND_COLORS.length]
                const isSel = c.index === selected
                const maxKm = Math.max(...reroute.candidates.map((x) => x.km ?? 0), 1)
                return (
                  <button type="button" key={c.index} onClick={() => setSelected(isSel ? null : c.index)}
                    className={`hairline w-full rounded-xl border p-3 text-left transition-all duration-200 ${isSel ? 'bg-raised/70 shadow-card' : 'bg-void/30 hover:bg-raised/40 hover:border-ash/40'}`}
                    style={isSel ? { borderColor: color, boxShadow: `0 0 0 1px ${color}40, 0 8px 24px -10px ${color}80` } : undefined}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="grid h-5 w-5 place-items-center rounded-md font-mono text-[10px] font-bold text-void" style={{ background: color }}>{c.index + 1}</span>
                        <span className="font-semibold">{c.mode}</span>
                        <span className="tabular font-mono text-[11px] text-dim">@ {c.thrill.toFixed(2)}</span>
                      </div>
                      <Verdict v={c.verdict} />
                    </div>
                    {c.ok ? (
                      <>
                        <div className="tabular mt-2 grid grid-cols-4 gap-1 font-mono text-[12px]">
                          <span>{fmt(c.km)} <span className="text-dim">km</span></span>
                          <span>{fmt(c.minutes, 0)} <span className="text-dim">min</span></span>
                          <span>{fmt(c.fun_score, 0)} <span className="text-dim">fun</span></span>
                          <span>{pct(c.shares_current_road)} <span className="text-dim">shared</span></span>
                        </div>
                        <div className="mt-1.5 grid grid-cols-2 gap-2">
                          <Bar share={(c.km ?? 0) / maxKm} color={color} />
                          <Bar share={c.shares_current_road} color="#6b6e76" />
                        </div>
                      </>
                    ) : null}
                    <div className="mt-1.5 text-[11px] leading-snug text-ash">{c.why}</div>
                    {c.refusals.length ? <div className="mt-1 inline-flex items-center gap-1 text-[11px] text-mred"><ShieldAlert size={11} /> {c.refusals.length} road(s) refused near this line</div> : null}
                  </button>
                )
              })}
            </div>
            {selectedCand?.ok ? (
              <button type="button" onClick={follow}
                className="mt-2.5 w-full rounded-lg px-3 py-2 text-[13px] font-semibold text-void transition-all hover:brightness-110 hover:-translate-y-px"
                style={{ background: CAND_COLORS[selectedCand.index % CAND_COLORS.length], boxShadow: `0 6px 16px -6px ${CAND_COLORS[selectedCand.index % CAND_COLORS.length]}` }}>
                Follow candidate #{selectedCand.index + 1} from here
              </button>
            ) : null}
            <p className="mt-2 text-[10.5px] leading-snug text-dim">Bars: km relative to the longest variant, and shared road. fun_score is only comparable at the same dial setting (router.py). Shared road = engine's cell overlap with the route being ridden.{engineIsMock ? ' The mock engine numbers its cells c0…cN on every line, so shared-road is not meaningful here and mode is ignored.' : ''}</p>
          </Section>
        ) : null}

        <Section title={selectedCand ? `Route figures · candidate #${selectedCand.index + 1}` : 'Route figures · active route'} icon={Activity} tone="blue">
          {shownPlan ? (
            <div className="grid grid-cols-3 gap-1.5">
              <Stat label="km" value={fmt(shownSummary.km)} big />
              <Stat label="minutes" value={fmt(shownSummary.minutes, 0)} big />
              <Stat label="fun score" value={fmt(shownSummary.fun_score, 0)} big tone="mint" />
              <Stat label="mean demand" value={fmt(shownSummary.mean_demand)} unit="°" />
              <Stat label="max demand" value={fmt(shownSummary.max_demand)} unit="°" tone={shownSummary.max_demand != null && shownSummary.gate_deg != null && shownSummary.max_demand > shownSummary.gate_deg ? 'red' : undefined} />
              <Stat label="gate" value={fmt(shownSummary.gate_deg)} unit="°" tone="red" />
              <Stat label="peak flow" value={fmt(shownSummary.peak_flow, 2)} />
              <Stat label="mean flow" value={fmt(shownSummary.mean_flow, 2)} />
              <Stat label="grip p95" value={pct(shownSummary.grip_lat_p95)} />
            </div>
          ) : <p className="text-dim">Plan a route to see the engine's figures.</p>}
        </Section>

        <Section title="Safety gate" icon={ShieldAlert} tone="red" right={rider ? <span className="tabular font-mono text-[11px] text-mred">gate {fmt(rider.gate)}° = {fmt(rider.skill)} + 2×{fmt(rider.sigma)}</span> : null}>
          {shownPlan ? (
            shownPlan.refusals.length ? (
              <ul className="space-y-1.5">
                {shownPlan.refusals.map((r, i) => (
                  <li key={i} className="animate-rise rounded-lg border border-mred/40 bg-mred/[0.06] px-3 py-2 text-[11.5px] leading-snug" style={{ boxShadow: 'inset 3px 0 0 #E7222E' }}>
                    <div className="tabular flex justify-between font-mono text-[11px] text-dim"><span>cell {r.cell}</span><span>{r.lat.toFixed(4)}, {r.lon.toFixed(4)}</span></div>
                    <div className="mt-0.5">{r.reason}</div>
                    <div className="tabular mt-0.5 font-mono text-mred">demand {fmt(r.demand)}°</div>
                  </li>
                ))}
              </ul>
            ) : <p className="inline-flex items-center gap-1.5 text-mint"><ShieldCheck size={13} /> {shownSummary.n_refused_nearby === 0 ? 'The engine refused no roads near this line.' : 'No refusals returned for this plan.'}</p>
          ) : <p className="text-dim">Refusals appear here once a plan is loaded: roads the gate deleted from the graph, with the engine's written reason.</p>}
        </Section>
      </aside>
    </div>
  )
}
