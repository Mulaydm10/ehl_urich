import { useEffect, useMemo, useRef, useState } from 'react'
import { Copy, Trash2 } from 'lucide-react'
import { GhostButton } from './primitives'
import type { BikeLinkClient, LinkTraceEvent } from '../services/bikeLink'

const LEVEL_TONE: Record<LinkTraceEvent['level'], string> = {
  info: 'text-ash',
  warn: 'text-amber-400',
  error: 'text-red-400',
}

const clock = (at: number) => new Date(at).toISOString().slice(11, 23)

/** Everything about an event except the envelope, as one compact line. */
function detail(e: LinkTraceEvent): string {
  const skip = new Set(['seq', 'at', 'op', 'level', 'source', 'session'])
  const parts: string[] = []
  for (const [k, v] of Object.entries(e)) {
    if (skip.has(k) || v == null) continue
    parts.push(`${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
  }
  return parts.join(' ')
}

/**
 * Live radio log for the bike link: every scan result, GATT callback, MTU
 * change, chunk write and failure the phone saw, newest last. The same events
 * go to the backend trail (GET /api/bmw/link/debug), so a test next to the
 * bike can be followed from the app and from the Mac at the same time.
 */
export function BikeLinkLog({ link }: { link: BikeLinkClient }) {
  const [events, setEvents] = useState<LinkTraceEvent[]>(() => link.trace())
  const [errorsOnly, setErrorsOnly] = useState(false)
  const [copied, setCopied] = useState(false)
  const endRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setEvents(link.trace())
    return link.onTrace(() => setEvents(link.trace()))
  }, [link])

  const shown = useMemo(
    () => (errorsOnly ? events.filter((e) => e.level !== 'info') : events),
    [events, errorsOnly],
  )

  useEffect(() => { endRef.current?.scrollIntoView({ block: 'nearest' }) }, [shown.length])

  const asText = () => shown.map((e) => `${clock(e.at)} ${e.level} ${e.op} ${detail(e)}`).join('\n')

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <GhostButton compact onClick={() => setErrorsOnly((v) => !v)}>
          {errorsOnly ? 'Show all' : 'Problems only'}
        </GhostButton>
        <GhostButton compact onClick={async () => {
          await navigator.clipboard.writeText(asText())
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}><Copy size={14} className="mr-1.5" />{copied ? 'Copied' : 'Copy log'}</GhostButton>
        <GhostButton compact onClick={() => { void link.clearTrace().then(() => setEvents(link.trace())) }}>
          <Trash2 size={14} className="mr-1.5" />Clear
        </GhostButton>
        <span className="caption ml-auto">{shown.length} events</span>
      </div>

      {shown.length === 0 ? (
        <p className="caption">
          No radio events yet. Scan, connect or send a route and every callback shows up here
          and in the backend trail.
        </p>
      ) : (
        <div className="max-h-64 overflow-y-auto rounded-md bg-black/30 p-3 font-mono text-[11px] leading-relaxed">
          {shown.map((e) => (
            <div key={`${e.source}-${e.seq}-${e.at}`} className={LEVEL_TONE[e.level] ?? 'text-ash'}>
              <span className="opacity-60">{clock(e.at)}</span>{' '}
              <span className="font-medium">{e.op}</span>{' '}
              <span className="opacity-80">{detail(e)}</span>
            </div>
          ))}
          <div ref={endRef} />
        </div>
      )}
    </div>
  )
}
