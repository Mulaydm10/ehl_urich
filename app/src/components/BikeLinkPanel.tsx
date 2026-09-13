import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bluetooth, BluetoothOff, RefreshCw } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { StatusLed } from './Cluster'
import { Feedback, GhostButton, Unavailable } from './primitives'
import { resolveBikeLink } from '../services/bikeLink'
import type { BikeLinkClient, LinkCapabilities, LinkStatus } from '../services/bikeLink'

const TRANSPORT_LABEL = { stand_in: 'Stand-in transport', native_ble: 'Phone Bluetooth', offline: 'No link available' } as const

/** Re-resolve the link client whenever the backend comes or goes. */
export function useBikeLink(): { link: BikeLinkClient; status: LinkStatus | null; caps: LinkCapabilities | null; refresh: () => Promise<void>; error: string | null } {
  const { online, bike } = useAppState()
  const link = useMemo(() => resolveBikeLink(() => online), [online])
  const [status, setStatus] = useState<LinkStatus | null>(null)
  const [caps, setCaps] = useState<LinkCapabilities | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([link.status(), bike ? link.capabilities(bike.id) : Promise.resolve(null)])
      setStatus(s)
      setCaps(c)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bike link unreachable.')
    }
  }, [link, bike])

  useEffect(() => {
    void refresh()
    return link.onChange(() => { void refresh() })
  }, [link, refresh])

  return { link, status, caps, refresh, error }
}

/**
 * Adapter / scan / connect UI for the local bike link. Says "stand-in" wherever
 * the transport is a stand-in; never shows a real-looking connection that isn't.
 */
export function BikeLinkPanel({ compact = false }: { compact?: boolean }) {
  const { link, status, caps, refresh, error } = useBikeLink()
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const act = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key)
    setNote(null)
    try { await fn(); await refresh() }
    catch (e) { setNote(e instanceof Error ? e.message : 'Bike link action failed.') }
    finally { setBusy(null) }
  }

  if (!status) return <div className="notice caption">{error ?? 'Checking bike link…'}</div>

  const { adapter, connection, devices } = status
  const connected = connection.state === 'connected'
  const noRadio = adapter.present === false
  const standIn = status.standIn

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {noRadio ? <BluetoothOff size={18} strokeWidth={1.5} className="text-ash" /> : <Bluetooth size={18} strokeWidth={1.5} />}
          <div>
            <div className="text-[14px] font-medium">{TRANSPORT_LABEL[status.transport]}</div>
            <StatusLed on={connected && !standIn} tone={standIn ? 'warn' : 'ok'}>
              {connection.state === 'unavailable' ? 'No Bluetooth adapter' : connected ? (standIn ? 'Simulated connection' : `Connected · ${connection.deviceName ?? connection.deviceId}`) : connection.state === 'connecting' ? 'Connecting…' : 'Not connected'}
            </StatusLed>
          </div>
        </div>
        <button type="button" className="icon-button" aria-label="Refresh bike link" onClick={() => act('refresh', refresh)}><RefreshCw size={16} className={busy === 'refresh' ? 'loading-pulse' : ''} /></button>
      </div>

      {standIn ? <Feedback tone="info"><div className="font-medium">Stand-in — no physical bike</div><p className="caption mt-1">{adapter.note || connection.note}</p></Feedback> : null}
      {noRadio && !standIn ? <Unavailable note={adapter.note || 'No Bluetooth adapter on this device.'} /> : null}
      {adapter.present && adapter.enabled === false ? <Unavailable note="Bluetooth is turned off on this phone." /> : null}

      {!compact && caps ? (
        <div className="data-list">
          {[
            ['TFT / display', caps.hasTft == null ? 'unverified' : caps.hasTft ? 'yes' : 'no'],
            ['ConnectedRide Navigator', caps.hasConnectedRideNavigator == null ? 'unverified' : caps.hasConnectedRideNavigator ? 'yes' : 'no'],
            ['Sensor box', caps.hasSensorBox == null ? 'unverified' : caps.hasSensorBox ? 'yes' : 'no'],
            ['Source', caps.verified ? 'Read from the bike' : 'Garage record · not verified on the bike'],
          ].map(([k, v]) => <div key={k} className="grid grid-cols-[1fr_1.15fr] items-baseline gap-4 py-3"><span className="text-[13px] font-medium">{k}</span><span className="caption text-right">{v}</span></div>)}
        </div>
      ) : null}

      {status.transport !== 'offline' && (standIn || !noRadio) ? (
        <div className="flex flex-wrap items-center gap-2">
          <GhostButton compact busy={busy === 'scan'} onClick={() => act('scan', async () => {
            if (!(await link.requestPermissions())) throw new Error('Bluetooth permission not granted.')
            await link.scan(!connection.scanning)
          })}>{connection.scanning ? 'Stop scan' : 'Scan for bike'}</GhostButton>
          {connected ? <GhostButton compact busy={busy === 'disconnect'} onClick={() => act('disconnect', () => link.disconnect())}>Disconnect</GhostButton> : null}
        </div>
      ) : null}

      {devices.length ? (
        <div className="data-list">
          {devices.map((d) => (
            <div key={d.id} className="data-list-row">
              <div className="min-w-0"><div className="text-[14px] font-medium">{d.name}</div><p className="caption mt-0.5">{d.rssi != null ? `${d.rssi} dBm · ` : ''}{d.paired ? 'Paired' : 'Not paired'}{d.standIn ? ' · stand-in' : ''}</p></div>
              <div className="flex shrink-0 gap-2">
                {status.transport === 'stand_in' && !d.paired ? <GhostButton compact busy={busy === `pair-${d.id}`} onClick={() => act(`pair-${d.id}`, () => link.pair(d.id))}>Pair</GhostButton> : null}
                {connection.deviceId === d.id && connected ? null : <GhostButton compact busy={busy === `connect-${d.id}`} disabled={status.transport === 'stand_in' && !d.paired} onClick={() => act(`connect-${d.id}`, () => link.connect(d.id))}>Connect</GhostButton>}
              </div>
            </div>
          ))}
        </div>
      ) : connection.scanning ? <p className="caption">Scanning… no devices found yet.</p> : null}

      {note ? <Feedback tone="error">{note}</Feedback> : null}
    </div>
  )
}
