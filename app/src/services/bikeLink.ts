/**
 * Bike link — the local phone <-> motorcycle channel (Bluetooth / TFT).
 *
 * Three implementations of one `BikeLinkClient`, picked by `resolveBikeLink`:
 *   nativeLink   — on Android, drives the BikeLink Capacitor plugin (real radio)
 *                  and mirrors what happened to the backend (/api/bmw/link/native/report).
 *   backendLink  — in a browser with the backend up: whatever transport the
 *                  backend runs (stand-in by default). Every answer carries `standIn`.
 *   offlineLink  — no radio, no backend. Says so; never simulates a transfer.
 *
 * Honesty rule: a result with `ok: true` means a device really acknowledged the
 * bytes. Stand-ins always return `ok: false, standIn: true`.
 *
 * UNVERIFIED: the bike's GATT service / characteristic for route transfer is
 * not known (never captured). `ROUTE_GATT` is therefore null and the native
 * plugin refuses to send until it is sourced on a real bike. Fill it in there.
 */
import { Capacitor, registerPlugin } from '@capacitor/core'
import type { PluginListenerHandle } from '@capacitor/core'
import { http } from './http'

export type LinkTransport = 'stand_in' | 'native_ble' | 'offline'
export type LinkConnectionState = 'unavailable' | 'disconnected' | 'connecting' | 'connected'
export type LinkTransferStatus = 'stand_in' | 'pending_phone' | 'sent' | 'failed' | 'unknown_transfer'

export interface LinkAdapter {
  present: boolean | null
  enabled: boolean | null
  standIn: boolean
  note: string
}

export interface LinkDevice {
  id: string
  name: string
  bikeId?: string
  rssi: number | null
  paired: boolean
  standIn: boolean
}

export interface LinkConnection {
  state: LinkConnectionState
  deviceId: string | null
  deviceName: string | null
  scanning: boolean
  standIn: boolean
  note: string
}

export interface LinkStatus {
  transport: LinkTransport
  standIn: boolean
  adapter: LinkAdapter
  connection: LinkConnection
  devices: LinkDevice[]
}

export interface LinkCapabilities {
  ok: boolean
  bikeId?: string
  verified: boolean
  source?: string
  hasTft?: boolean
  hasConnectedRideNavigator?: boolean
  /** null = unverified until the phone has actually connected to the bike. */
  hasSensorBox?: boolean | null
  hasV2bCapability?: boolean | null
  navigationHandoff?: boolean
  note: string
  linkState?: LinkConnectionState
  standIn?: boolean
}

export interface LinkTransfer {
  ok: boolean
  status: LinkTransferStatus
  standIn: boolean
  transport: LinkTransport
  transferId?: string
  target: 'ConnectedRide Navigator' | 'TFT' | 'phone'
  message: string
  gpx?: string
}

export interface BikeLinkClient {
  transport: LinkTransport
  status(): Promise<LinkStatus>
  capabilities(bikeId: string): Promise<LinkCapabilities>
  requestPermissions(): Promise<boolean>
  scan(active: boolean): Promise<LinkStatus>
  pair(deviceId: string): Promise<LinkStatus>
  unpair(deviceId: string): Promise<LinkStatus>
  connect(deviceId: string): Promise<LinkStatus>
  disconnect(): Promise<LinkStatus>
  sendRoute(routeId: string, bikeId: string): Promise<LinkTransfer>
  onChange(cb: () => void): () => void
}

/** GATT identifiers of the bike's route-transfer service. Unknown => refuse to send. */
export const ROUTE_GATT: { serviceUuid: string; characteristicUuid: string } | null = null

// --------------------------------------------------------------------------
// native plugin surface (app/android/.../BikeLinkPlugin.java)
// --------------------------------------------------------------------------

interface BikeLinkPlugin {
  getAdapterState(): Promise<LinkAdapter>
  requestBluetoothPermissions(): Promise<{ granted: boolean }>
  startScan(): Promise<{ scanning: boolean }>
  stopScan(): Promise<{ scanning: boolean; devices: LinkDevice[] }>
  getDevices(): Promise<{ scanning: boolean; devices: LinkDevice[] }>
  connect(opts: { deviceId: string }): Promise<LinkConnection>
  disconnect(): Promise<LinkConnection>
  getConnectionState(): Promise<LinkConnection>
  sendRoute(opts: { gpx: string; serviceUuid?: string; characteristicUuid?: string }): Promise<{ ok: boolean; bytes: number; message: string }>
  addListener(event: 'device' | 'connectionState' | 'services' | 'scanFailed', cb: (data: unknown) => void): Promise<PluginListenerHandle>
}

const Native = registerPlugin<BikeLinkPlugin>('BikeLink')

export const nativeLinkAvailable = (): boolean =>
  Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('BikeLink')

const targetFor = (caps: LinkCapabilities): LinkTransfer['target'] =>
  caps.hasConnectedRideNavigator ? 'ConnectedRide Navigator' : caps.hasTft ? 'TFT' : 'phone'

class Emitter {
  private subs = new Set<() => void>()
  on(cb: () => void) { this.subs.add(cb); return () => { this.subs.delete(cb) } }
  emit() { for (const cb of this.subs) cb() }
}

// --------------------------------------------------------------------------
// backend-driven (browser / stand-in)
// --------------------------------------------------------------------------

const post = <T,>(path: string, body: unknown) => http.post<T>(`/api/bmw/link${path}`, body)
const get = <T,>(path: string) => http.get<T>(`/api/bmw/link${path}`)

export const backendLink: BikeLinkClient = (() => {
  const ev = new Emitter()
  const after = async (p: Promise<unknown>) => { await p; ev.emit(); return get<LinkStatus>('/status') }
  return {
    transport: 'stand_in' as LinkTransport,
    status: () => get<LinkStatus>('/status'),
    capabilities: (bikeId) => get<LinkCapabilities>(`/capabilities/${bikeId}`),
    requestPermissions: async () => true,
    scan: (active) => after(post('/scan', { active })),
    pair: (deviceId) => after(post('/pair', { deviceId })),
    unpair: (deviceId) => after(post('/unpair', { deviceId })),
    connect: (deviceId) => after(post('/connect', { deviceId })),
    disconnect: () => after(post('/disconnect', {})),
    sendRoute: (routeId, bikeId) => post<LinkTransfer>('/send', { routeId, bikeId }),
    onChange: (cb) => ev.on(cb),
  }
})()

// --------------------------------------------------------------------------
// native (Android radio); mirrors to the backend when it is reachable
// --------------------------------------------------------------------------

export function makeNativeLink(online: () => boolean): BikeLinkClient {
  const ev = new Emitter()
  const devices = new Map<string, LinkDevice>()
  let listening = false

  const report = async (body: Record<string, unknown>) => {
    if (!online()) return
    try { await post('/native/report', body) } catch { /* backend mirror is best-effort */ }
  }

  const listen = async () => {
    if (listening) return
    listening = true
    await Native.addListener('device', (d) => { const dev = d as LinkDevice; devices.set(dev.id, dev); ev.emit() })
    await Native.addListener('connectionState', (c) => { void report({ connection: c }); ev.emit() })
    await Native.addListener('scanFailed', () => ev.emit())
  }

  const status = async (): Promise<LinkStatus> => {
    await listen()
    const [adapter, connection] = await Promise.all([Native.getAdapterState(), Native.getConnectionState()])
    const list = [...devices.values()]
    void report({ adapter, connection, devices: list })
    return { transport: 'native_ble', standIn: false, adapter, connection, devices: list }
  }

  const unsupported = (what: string) => {
    throw new Error(`${what} is not part of the verified bike protocol yet. Pair from Android Bluetooth settings.`)
  }

  return {
    transport: 'native_ble',
    status,
    capabilities: async (bikeId) => {
      const conn = await Native.getConnectionState()
      if (online()) return { ...(await get<LinkCapabilities>(`/capabilities/${bikeId}`)), linkState: conn.state, standIn: false }
      return { ok: true, bikeId, verified: false, hasSensorBox: null, hasV2bCapability: null, linkState: conn.state,
        standIn: false, note: 'Backend unreachable; capabilities can only be confirmed by connecting to the bike.' }
    },
    requestPermissions: async () => (await Native.requestBluetoothPermissions()).granted,
    scan: async (active) => {
      await listen()
      if (active) { devices.clear(); await Native.startScan() } else await Native.stopScan()
      ev.emit()
      return status()
    },
    pair: async () => unsupported('In-app pairing'),
    unpair: async () => unsupported('In-app unpairing'),
    connect: async (deviceId) => { await Native.connect({ deviceId }); ev.emit(); return status() },
    disconnect: async () => { await Native.disconnect(); ev.emit(); return status() },
    sendRoute: async (routeId, bikeId) => {
      const caps = online()
        ? await get<LinkCapabilities>(`/capabilities/${bikeId}`)
        : { ok: true, verified: false, note: '', hasTft: true } as LinkCapabilities
      const target = targetFor(caps)
      const base = { standIn: false as const, transport: 'native_ble' as const, target }
      const conn = await Native.getConnectionState()
      if (conn.state !== 'connected') {
        return { ...base, ok: false, status: 'failed', message: 'No bike connected over Bluetooth; nothing was sent.' }
      }
      let transferId: string | undefined
      let gpx: string
      if (online()) {
        const t = await post<LinkTransfer>('/send', { routeId, bikeId, deviceId: conn.deviceId })
        if (!t.gpx) return t
        transferId = t.transferId
        gpx = t.gpx
      } else {
        return { ...base, ok: false, status: 'failed', message: 'Backend unreachable: the GPX payload comes from the backend, so nothing was sent.' }
      }
      try {
        const res = await Native.sendRoute({ gpx, ...(ROUTE_GATT ?? {}) })
        void report({ transfer: { transferId, ok: res.ok, message: res.message } })
        return { ...base, ok: res.ok, status: res.ok ? 'sent' : 'failed', transferId, message: res.message }
      } catch (e) {
        const message = e instanceof Error ? e.message : String(e)
        void report({ transfer: { transferId, ok: false, message } })
        return { ...base, ok: false, status: 'failed', transferId, message }
      }
    },
    onChange: (cb) => ev.on(cb),
  }
}

// --------------------------------------------------------------------------
// nothing available
// --------------------------------------------------------------------------

const OFFLINE_NOTE = 'No Bluetooth adapter in this browser and no backend reachable. Nothing can be sent to a bike from here.'

export const offlineLink: BikeLinkClient = (() => {
  const st: LinkStatus = {
    transport: 'offline', standIn: true,
    adapter: { present: false, enabled: false, standIn: true, note: OFFLINE_NOTE },
    connection: { state: 'unavailable', deviceId: null, deviceName: null, scanning: false, standIn: true, note: OFFLINE_NOTE },
    devices: [],
  }
  const same = async () => st
  return {
    transport: 'offline',
    status: same,
    capabilities: async (bikeId) => ({ ok: false, bikeId, verified: false, hasSensorBox: null, hasV2bCapability: null, note: OFFLINE_NOTE, linkState: 'unavailable', standIn: true }),
    requestPermissions: async () => false,
    scan: same, pair: same, unpair: same, connect: same, disconnect: same,
    sendRoute: async () => ({ ok: false, status: 'failed', standIn: true, transport: 'offline', target: 'phone', message: OFFLINE_NOTE }),
    onChange: () => () => {},
  }
})()

export function resolveBikeLink(online: () => boolean): BikeLinkClient {
  if (nativeLinkAvailable()) return makeNativeLink(online)
  return online() ? backendLink : offlineLink
}
