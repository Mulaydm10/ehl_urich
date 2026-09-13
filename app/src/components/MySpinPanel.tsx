import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAppState } from '../state/AppState'
import { StatusLed } from './Cluster'
import { Feedback, GhostButton } from './primitives'
import { resolveMySpin, type MySpinAccess, type MySpinState } from '../services/mySpin'

/**
 * mySPIN connection + authorization readout. This is the honest answer to
 * "does the bike know it's for this app": it shows whether the SDK is present,
 * whether registerApplication succeeded, whether the head unit connected, and —
 * per vehicle-data key — whether it granted or denied this app. On an
 * unregistered app most keys come back denied, and we show exactly that.
 */
export function MySpinPanel() {
  const { online } = useAppState()
  const client = useMemo(() => resolveMySpin(() => online), [online])
  const [state, setState] = useState<MySpinState | null>(null)
  const [access, setAccess] = useState<MySpinAccess[]>([])
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setState(await client.getState())
    setAccess(client.access)
  }, [client])

  useEffect(() => {
    void refresh()
    const off = client.onState((s) => { setState(s); setAccess(client.access) })
    const offTrace = client.onTrace(() => setAccess(client.access))
    return () => { off(); offTrace() }
  }, [client, refresh])

  if (!state) return null

  const connect = async () => {
    setBusy(true)
    setNote(null)
    try {
      await client.register()
      await client.subscribe()
      await refresh()
      const granted = client.access.filter((a) => a.granted).length
      setNote(client.available
        ? `mySPIN: ${granted} of ${client.access.length} vehicle-data keys granted by the head unit.`
        : 'Bosch mySPIN SDK is not bundled in this build; no vehicle data can be read on this phone.')
    } catch (e) {
      setNote(e instanceof Error ? e.message : 'mySPIN registration failed.')
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[14px] font-medium">Vehicle data · mySPIN</div>
          <StatusLed on={state.connected} tone={state.connected ? 'ok' : 'warn'}>
            {!state.sdkPresent ? 'SDK not bundled' : state.connected ? `Connected${state.isTwoWheeler ? ' · two-wheeler' : ''}` : state.registered ? 'Registered · waiting for head unit' : 'Not registered'}
          </StatusLed>
        </div>
        <GhostButton compact busy={busy} onClick={connect}>{state.registered ? 'Re-check' : 'Connect mySPIN'}</GhostButton>
      </div>

      {!state.sdkPresent ? (
        <div className="notice">
          <div className="text-[13px] font-medium">Authorization not solved</div>
          <p className="caption mt-1">The head unit only grants vehicle data (speed, RPM, gear, lean) to an app whose identity is on its whitelist. This build isn't a registered mySPIN app, so it can read at most the three generic keys and only next to a real bike.</p>
        </div>
      ) : null}

      {access.length ? (
        <div className="data-list">
          {access.map((a) => (
            <div key={a.key} className="grid grid-cols-[1fr_auto] items-baseline gap-4 py-2">
              <span className="text-[13px]">{a.key}</span>
              <span className="caption" data-live={a.granted}>{a.granted ? 'granted' : 'denied'}</span>
            </div>
          ))}
        </div>
      ) : null}

      {note ? <Feedback tone="info">{note}</Feedback> : null}
    </div>
  )
}
