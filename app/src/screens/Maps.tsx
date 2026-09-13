import { useState } from 'react'
import { Check, Download, RefreshCw } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { BackHeader, Bar, EmptyState, Feedback, GhostButton } from '../components/primitives'

export function MapsScreen() {
  const { regions, api, updateRegion } = useAppState()
  const [pendingIds, setPendingIds] = useState<string[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const installed = regions.filter((r) => r.status === 'installed')

  return (
    <div className="pb-8">
      <BackHeader to="/more" title="Offline maps" detail="Your roads, even without a signal." />
      <div className="metric-hero">
        <div className="flex items-baseline justify-center gap-2"><span className="readout">{(installed.reduce((size, r) => size + r.sizeMb, 0) / 1000).toFixed(2)}</span><span className="text-[18px] font-light text-ash">GB</span></div>
        <span className="label">Stored on your phone</span>
        <p className="caption mt-4">{installed.length} {installed.length === 1 ? 'region' : 'regions'} ready for the road</p>
      </div>
      {!regions.length ? <div className="p-5"><EmptyState title="No offline regions">Available map regions will appear here.</EmptyState></div> : null}
      <div className="data-list mx-6">
        {regions.map((r) => (
          <section key={r.id} className="py-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <h2 className="text-[16px] font-medium tracking-[-0.02em]">{r.name}</h2>
                <p className="caption mt-1">{r.sizeMb} MB</p>
              </div>
              {r.status === 'installed' ? <span className="flex items-center gap-1.5 text-caption text-ash"><Check size={14} /> Ready</span>
                : r.status === 'downloading' ? <span className="font-mono text-[12px] text-accent-text">{Math.round(r.progress)}%</span>
                : <GhostButton compact busy={pendingIds.includes(r.id)} aria-label={`${r.status === 'failed' ? 'Retry' : 'Download'} ${r.name}`} onClick={async () => {
                  setPendingIds((ids) => [...ids, r.id])
                  setErrors((current) => ({ ...current, [r.id]: '' }))
                  try { updateRegion(await api.startMapDownload(r.id)) }
                  catch { setErrors((current) => ({ ...current, [r.id]: 'Download could not start. Try again. Your installed regions remain available.' })) }
                  finally { setPendingIds((ids) => ids.filter((id) => id !== r.id)) }
                }}>
                  {r.status === 'failed' ? <RefreshCw size={14} /> : <Download size={14} />}{r.status === 'failed' ? 'Retry' : 'Download'}
                </GhostButton>}
            </div>
            {errors[r.id] ? <div className="mt-3"><Feedback tone="error">{errors[r.id]}</Feedback></div> : null}
            {r.updatedAt ? <p className="caption mt-3">Updated {r.updatedAt}</p> : null}
            {r.status === 'downloading' ? <div className="mt-4" role="progressbar" aria-label={`Downloading ${r.name}`} aria-valuenow={r.progress} aria-valuemin={0} aria-valuemax={100}><Bar ratio={r.progress / 100} /><p className="caption mt-2">Downloading region…</p></div> : null}
            {r.status === 'failed' ? <div className="notice mt-4 border-alert/25 bg-alert/[0.05]"><p className="font-medium">Download interrupted</p><p className="caption mt-1">{r.error ?? 'Download failed.'}</p></div> : null}
          </section>
        ))}
      </div>
    </div>
  )
}
