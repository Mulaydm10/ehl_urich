import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bluetooth, BluetoothOff, RefreshCw } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { StatusLed } from './Cluster'
import { Feedback, GhostButton, Unavailable } from './primitives'
import { BikeLinkLog } from './BikeLinkLog'
import { MySpinPanel } from './MySpinPanel'
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
  const [note, setNote] = useState<{ tone: 'info' | 'error'; text: string } | null>(null)
  const [showLog, setShowLog] = useState(false)

  const say = (text: string) => setNote({ tone: 'info', text })

  const act = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key)
    setNote(null)
    try { await fn(); await refresh() }
    catch (e) { setNote({ tone: 'error', text: e instanceof Error ? e.message : 'Bike link action failed.' }) }
    finally { setBusy(null) }
  }

  if (!status) return <div className="notice caption">{error ?? 'Checking bike link…'}</div>

  const { adapter, connection, devices } = status
  // A busy room holds hundreds of anonymous BLE advertisers (phones, earbuds,
  // speakers). Show only what can matter for the bike: BMW head-unit candidates,
  // paired devices and named devices, strongest signal first.
  const shown = devices
    .filter((d) => d.icc || d.paired || d.standIn || (d.name && !d.name.startsWith('Unnamed')))
    .sort((a, b) => Number(Boolean(b.icc)) - Number(Boolean(a.icc))
      || Number(Boolean(b.paired)) - Number(Boolean(a.paired))
      || (b.rssi ?? -999) - (a.rssi ?? -999))
  const hidden = devices.length - shown.length
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
          {status.transport === 'native_ble' ? (
            <GhostButton compact busy={busy === 'bonded'} onClick={() => act('bonded', async () => {
              if (!(await link.requestPermissions())) throw new Error('Bluetooth permission not granted.')
              const bonded = await link.listBonded()
              say(`${bonded.length} bonded device(s); ${bonded.filter((d) => d.icc).length} look like a BMW head unit.`)
            })}>List paired devices</GhostButton>
          ) : null}
        </div>
      ) : null}

      {shown.length ? (
        <div className="data-list">
          {shown.map((d) => (
            <div key={d.id} className="data-list-row">
              <div className="min-w-0"><div className="text-[14px] font-medium">{d.name}{d.icc ? <span className="caption ml-2">BMW head unit?</span> : null}</div><p className="caption mt-0.5">{d.rssi != null ? `${d.rssi} dBm · ` : ''}{d.kind === 'classic' ? 'Bluetooth Classic · ' : ''}{d.paired ? 'Paired' : 'Not paired'}{d.standIn ? ' · stand-in' : ''}{d.iccReason ? ` · matched by ${d.iccReason === 'sdp_uuid' ? 'SDP UUID' : 'name'}` : ''}</p></div>
              <div className="flex shrink-0 gap-2">
                {status.transport === 'native_ble' && d.paired ? (
                  <GhostButton compact busy={busy === `probe-${d.id}`} onClick={() => act(`probe-${d.id}`, async () => {
                    say((await link.probeIcc(d.id)).message)
                  })}>Probe RFCOMM</GhostButton>
                ) : null}
                {status.transport === 'stand_in' && !d.paired ? <GhostButton compact busy={busy === `pair-${d.id}`} onClick={() => act(`pair-${d.id}`, () => link.pair(d.id))}>Pair</GhostButton> : null}
                {connection.deviceId === d.id && connected ? null : <GhostButton compact busy={busy === `connect-${d.id}`} disabled={status.transport === 'stand_in' && !d.paired} onClick={() => act(`connect-${d.id}`, () => link.connect(d.id))}>Connect</GhostButton>}
              </div>
            </div>
          ))}
        </div>
      ) : connection.scanning ? <p className="caption">Scanning… no named devices found yet.</p> : null}
      {hidden > 0 ? (
        <p className="caption">
          {hidden} unnamed nearby device{hidden === 1 ? '' : 's'} hidden. The bike&apos;s TFT does not show up in this
          scan — it pairs over Bluetooth Classic: pair it in Android Bluetooth settings, then tap List paired devices.
        </p>
      ) : null}

      {note ? <Feedback tone={note.tone}>{note.text}</Feedback> : null}

      {!compact ? <div className="border-t border-white/[0.065] pt-4"><MySpinPanel /></div> : null}

      {!compact ? (
        <div className="space-y-3">
          <GhostButton compact onClick={() => setShowLog((v) => !v)}>{showLog ? 'Hide radio log' : 'Radio log'}</GhostButton>
          {showLog ? <BikeLinkLog link={link} /> : null}
        </div>
      ) : null}
    </div>
  )
}
