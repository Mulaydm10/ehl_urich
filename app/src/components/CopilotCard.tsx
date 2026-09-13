import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Compass, Fuel, MapPinOff, Navigation, PauseCircle, ShieldAlert, Sparkles } from 'lucide-react'
import { setPendingPlan } from '../services/assistant'
import { speak } from './useSpeech'
import { useCopilot } from './useCopilot'

/**
 * The co-pilot, on the Ride screen: a switch, an honest status line, and at
 * most one suggestion at a time.
 *
 * Nothing here decides anything. The card shows what the backend's triggers
 * produced, including their evidence, and offers the two answers a rider can
 * give at 80 km/h: take it, or not now. "Not now" is sent back to the backend,
 * which parks that kind of suggestion for half an hour — a co-pilot you have
 * to argue with is a co-pilot you switch off.
 */

const ICON: Record<string, typeof Compass> = {
  off_route: Navigation,
  gate_ahead: ShieldAlert,
  dull_ahead: Compass,
  scenic_detour: Sparkles,
  fuel: Fuel,
  stopped: PauseCircle,
}

const STATUS: Record<string, string> = {
  off: 'Off. Switch on before you set off and it watches the ride.',
  no_gps: 'Waiting for a GPS fix. Nothing is suggested without one.',
  watching: 'Watching the ride.',
  unreachable: 'Backend unreachable — not watching. No suggestions are invented offline.',
}

export function CopilotCard({ riderKey = 'userA', thrill = 0.5, mode = 'flow', bikeId = null }: {
  riderKey?: string
  thrill?: number
  mode?: string
  bikeId?: string | null
}) {
  const [on, setOn] = useState(false)
  const [voice, setVoice] = useState(true)
  const navigate = useNavigate()
  const { state, suggestion, why, route, ticks, accept, dismiss, busy } = useCopilot(on, {
    riderKey, thrill, mode, bikeId,
  })

  const spokenId = useRef<string | null>(null)
  useEffect(() => {
    if (!voice || !suggestion || suggestion.id === spokenId.current) return
    spokenId.current = suggestion.id
    speak(suggestion.say)
  }, [voice, suggestion])

  const onAccept = useCallback(async () => {
    const plan = await accept()
    if (plan) {
      setPendingPlan(plan)
      navigate('/thrill')
    }
  }, [accept, navigate])

  const Icon = suggestion ? (ICON[suggestion.kind] ?? Compass) : Compass

  return (
    <section className="panel mx-6 overflow-hidden" aria-label="Ride co-pilot">
      <div className="flex items-center gap-3 px-5 py-4">
        <span className="action-orb h-9 w-9 shrink-0"><Compass size={18} strokeWidth={1.5} /></span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[14px] font-medium">Ride co-pilot</h2>
          <p className="caption mt-1">{STATUS[state]}</p>
        </div>
        <button
          type="button"
          onClick={() => setOn((v) => !v)}
          aria-pressed={on}
          className="rounded-control border border-white/20 px-3 py-1.5 text-[11px] uppercase tracking-[0.1em]"
        >
          {on ? 'Stop' : 'Start'}
        </button>
      </div>

      {on ? (
        <div className="flex items-center justify-between border-t border-white/[0.065] px-5 py-3">
          <span className="caption text-[10px]">
            {route ? 'Following a planned route' : 'No plan loaded — plan one on Thrill for reroute advice'}
            {ticks ? ` · ${ticks} check${ticks === 1 ? '' : 's'}` : ''}
          </span>
          <button
            type="button"
            onClick={() => setVoice((v) => !v)}
            aria-pressed={voice}
            className="caption text-[10px] uppercase tracking-[0.1em] underline-offset-4 hover:underline"
          >
            {voice ? 'Speaks aloud' : 'Silent'}
          </button>
        </div>
      ) : null}

      {suggestion ? (
        <div className="border-t border-white/[0.065] px-5 py-5" aria-live="polite">
          <div className="flex items-start gap-3">
            <Icon size={18} className="mt-0.5 shrink-0" />
            <div className="min-w-0">
              <h3 className="text-[14px] font-medium">{suggestion.title}</h3>
              <p className="mt-1.5 text-[13px] text-ash">{suggestion.say}</p>
              <p className="caption mt-2 text-[10px]">{suggestion.detail}</p>
              <span className="mt-2 inline-flex rounded-control bg-white/[0.06] px-2 py-0.5 text-[9px] uppercase tracking-[0.1em] text-ash">
                FLOWSTATE trigger · {suggestion.kind}
                {suggestion.narrated ? ' · worded by the assistant' : ' · no model, rules wording'}
              </span>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            {suggestion.action ? (
              <button
                type="button"
                onClick={() => void onAccept()}
                disabled={busy}
                className="flex-1 rounded-control bg-white px-4 py-2.5 text-[12px] font-medium text-black disabled:opacity-50"
              >
                {busy ? 'Planning…' : 'Take it'}
              </button>
            ) : null}
            <button
              type="button"
              onClick={dismiss}
              className="flex-1 rounded-control border border-white/20 px-4 py-2.5 text-[12px]"
            >
              Not now
            </button>
          </div>
        </div>
      ) : on ? (
        <div className="flex items-center gap-2 border-t border-white/[0.065] px-5 py-4">
          <MapPinOff size={13} className="shrink-0 text-ash" />
          <p className="caption text-[10px]">{why ?? 'Nothing to say yet.'}</p>
        </div>
      ) : null}
    </section>
  )
}
