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
 *
 * Debugging a real bike: every radio event the plugin emits is kept here in a
 * ring buffer, shown by BikeLinkLog and forwarded to the backend trail
 * (POST /api/bmw/link/debug) so the ride can be watched from the Mac.
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
  /** How it was found: BLE advertising or a bonded Bluetooth Classic device. */
  kind?: 'ble' | 'classic'
  /** Looks like the bike head unit by SDP UUID or name prefix (BMW app's own test). */
  icc?: boolean
  iccReason?: 'sdp_uuid' | 'name_prefix' | null
  bondState?: 'none' | 'bonding' | 'bonded'
  sdpUuids?: string[]
  shortId?: string
}

/** One radio event. Free-form fields per `op`; the log panel renders them raw. */
export interface LinkTraceEvent {
  seq: number
  at: number
  op: string
  level: 'info' | 'warn' | 'error'
  source: string
  session?: string
  [field: string]: unknown
}

/** Result of opening (and closing) an RFCOMM channel; no protocol is spoken. */
export interface IccProbe {
  ok: boolean
  uuid: string
  elapsedMs: number
  message: string
  error?: string
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
  /** Bonded Bluetooth Classic devices — where the BMW app finds the head unit. */
  listBonded(): Promise<LinkDevice[]>
  /** Open and close an RFCOMM channel to see whether the bike accepts it. */
  probeIcc(deviceId: string, uuid?: string): Promise<IccProbe>
  trace(): LinkTraceEvent[]
  onTrace(cb: (e: LinkTraceEvent) => void): () => void
  clearTrace(): Promise<void>
}

/**
 * SDP service IDs the shipped BMW app accepts for the bike head unit
 * (com.bmw.connride.connectivity.bluetooth). They identify a *Bluetooth
 * Classic / RFCOMM* endpoint, so they are offered as probe targets only;
 * they are deliberately NOT used as GATT route-transfer UUIDs.
 */
export const ICC_SERVICE_UUIDS = [
  'c707050e-efae-1449-3913-c191e5bb32dc',
  'a96f9e76-ab2e-869c-40e3-1da0c086a07a',
  'dc32bbe5-91c1-1339-4914-aeef0e0507c7',
] as const

const TRACE_LIMIT = 500

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
  listBondedDevices(): Promise<{ devices: LinkDevice[] }>
  probeIccLink(opts: { deviceId: string; uuid?: string }): Promise<IccProbe>
  getTrace(opts: { since: number }): Promise<{ events: LinkTraceEvent[]; nextSeq: number; dropped: number; session: string }>
  clearTrace(): Promise<{ nextSeq: number }>
  addListener(event: 'device' | 'connectionState' | 'services' | 'scanFailed' | 'trace', cb: (data: unknown) => void): Promise<PluginListenerHandle>
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

/**
 * Ring buffer of radio events plus the best-effort forward to the backend
 * trail. Events are batched so a chunked transfer does not turn into one HTTP
 * request per write.
 */
class TraceLog {
  private events: LinkTraceEvent[] = []
  private subs = new Set<(e: LinkTraceEvent) => void>()
  private queue: LinkTraceEvent[] = []
  private flushTimer: ReturnType<typeof setTimeout> | null = null
  private seq = 0

  private readonly online: () => boolean
  private readonly forward: boolean

  constructor(online: () => boolean, forward: boolean) {
    this.online = online
    this.forward = forward
  }

  add(e: Partial<LinkTraceEvent> & { op: string }): LinkTraceEvent {
    const ev: LinkTraceEvent = {
      level: 'info', source: 'app', at: Date.now(), seq: ++this.seq, ...e,
    }
    this.events.push(ev)
    if (this.events.length > TRACE_LIMIT) this.events.splice(0, this.events.length - TRACE_LIMIT)
    for (const cb of this.subs) cb(ev)
    if (this.forward) this.enqueue(ev)
    return ev
  }

  private enqueue(ev: LinkTraceEvent) {
    this.queue.push(ev)
    if (this.flushTimer) return
    this.flushTimer = setTimeout(() => { this.flushTimer = null; void this.flush() }, 800)
  }

  private async flush() {
    const batch = this.queue.splice(0, this.queue.length)
    if (!batch.length || !this.online()) return
    try { await post('/debug', { session: batch[0].session, events: batch }) }
    catch { /* the trail is diagnostics; never fail an action because of it */ }
  }

  all() { return [...this.events] }
  clear() { this.events = [] }
  on(cb: (e: LinkTraceEvent) => void) { this.subs.add(cb); return () => { this.subs.delete(cb) } }
}

// --------------------------------------------------------------------------
// backend-driven (browser / stand-in)
// --------------------------------------------------------------------------

const post = <T,>(path: string, body: unknown) => http.post<T>(`/api/bmw/link${path}`, body)
const get = <T,>(path: string) => http.get<T>(`/api/bmw/link${path}`)

export const backendLink: BikeLinkClient = (() => {
  const ev = new Emitter()
  // The backend records its own side of these calls, so nothing is forwarded.
  const log = new TraceLog(() => true, false)
  const after = async (p: Promise<unknown>) => { await p; ev.emit(); return get<LinkStatus>('/status') }
  const noRadio = (what: string): never => {
    throw new Error(`${what} needs the phone's Bluetooth radio; this browser session has none.`)
  }
  return {
    transport: 'stand_in' as LinkTransport,
    status: () => get<LinkStatus>('/status'),
    capabilities: (bikeId) => get<LinkCapabilities>(`/capabilities/${bikeId}`),
    requestPermissions: async () => true,
    scan: (active) => { log.add({ op: 'scan', source: 'backend', active }); return after(post('/scan', { active })) },
    pair: (deviceId) => after(post('/pair', { deviceId })),
    unpair: (deviceId) => after(post('/unpair', { deviceId })),
    connect: (deviceId) => { log.add({ op: 'connect', source: 'backend', deviceId }); return after(post('/connect', { deviceId })) },
    disconnect: () => after(post('/disconnect', {})),
    sendRoute: (routeId, bikeId) => post<LinkTransfer>('/send', { routeId, bikeId }),
    onChange: (cb) => ev.on(cb),
    listBonded: async () => noRadio('Listing bonded devices'),
    probeIcc: async () => noRadio('Probing the bike RFCOMM channel'),
    trace: () => log.all(),
    onTrace: (cb) => log.on(cb),
    clearTrace: async () => { log.clear() },
  }
})()

// --------------------------------------------------------------------------
// native (Android radio); mirrors to the backend when it is reachable
// --------------------------------------------------------------------------

export function makeNativeLink(online: () => boolean): BikeLinkClient {
  const ev = new Emitter()
  const devices = new Map<string, LinkDevice>()
  const log = new TraceLog(online, true)
  let listening = false

  // Every BLE advertisement re-renders the panel, and each render used to post a
  // full report: ~19 POSTs a second in a busy room, which flooded the backend
  // trail. Reports now go out only when their content changes (RSSI ignored),
  // at most one per REPORT_MIN_MS; transfer outcomes always go out at once.
  const REPORT_MIN_MS = 2000
  let lastSig = ''
  let lastSentAt = 0
  let pending: Record<string, unknown> | null = null
  let reportTimer: ReturnType<typeof setTimeout> | null = null
  const sigOf = (body: Record<string, unknown>) =>
    JSON.stringify(body, (k, v) => (k === 'rssi' || k === 'reportedAt' ? undefined : v))
  const send = async (body: Record<string, unknown>) => {
    lastSentAt = Date.now()
    try { await post('/native/report', body) } catch { /* backend mirror is best-effort */ }
  }
  const report = async (body: Record<string, unknown>) => {
    if (!online()) return
    if ('transfer' in body) { await send(body); return }
    const sig = sigOf(body)
    if (sig === lastSig) return
    lastSig = sig
    const wait = REPORT_MIN_MS - (Date.now() - lastSentAt)
    if (wait <= 0) { await send(body); return }
    pending = body
    if (!reportTimer) {
      reportTimer = setTimeout(() => {
        reportTimer = null
        const b = pending
        pending = null
        if (b) void send(b)
      }, wait)
    }
  }
  // Only devices worth mirroring: a busy room has hundreds of unnamed advertisers.
  const relevant = (d: LinkDevice) => Boolean(d.icc || d.paired || (d.name && !d.name.startsWith('Unnamed')))

  const listen = async () => {
    if (listening) return
    listening = true
    await Native.addListener('device', (d) => { const dev = d as LinkDevice; devices.set(dev.id, dev); ev.emit() })
    await Native.addListener('connectionState', (c) => { void report({ connection: c }); ev.emit() })
    await Native.addListener('scanFailed', () => ev.emit())
    await Native.addListener('trace', (e) => { log.add(e as LinkTraceEvent); ev.emit() })
  }

  const status = async (): Promise<LinkStatus> => {
    await listen()
    const [adapter, connection] = await Promise.all([Native.getAdapterState(), Native.getConnectionState()])
    const list = [...devices.values()]
    void report({ adapter, connection, devices: list.filter(relevant) })
    return { transport: 'native_ble', standIn: false, adapter, connection, devices: list }
  }

  // A BLE scan is a battery-heavy radio sweep; stop it on its own after SCAN_MS.
  const SCAN_MS = 15000
  let scanTimer: ReturnType<typeof setTimeout> | null = null

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
      if (scanTimer) { clearTimeout(scanTimer); scanTimer = null }
      if (active) {
        devices.clear()
        await Native.startScan()
        scanTimer = setTimeout(() => {
          scanTimer = null
          void Native.stopScan().then(() => ev.emit()).catch(() => undefined)
        }, SCAN_MS)
      } else await Native.stopScan()
      ev.emit()
      return status()
    },
    pair: async () => unsupported('In-app pairing'),
    unpair: async () => unsupported('In-app unpairing'),
    listBonded: async () => {
      await listen()
      const { devices: bonded } = await Native.listBondedDevices()
      for (const d of bonded) devices.set(d.id, d)
      ev.emit()
      void report({ devices: [...devices.values()] })
      return bonded
    },
    probeIcc: async (deviceId, uuid) => {
      await listen()
      return Native.probeIccLink(uuid ? { deviceId, uuid } : { deviceId })
    },
    trace: () => log.all(),
    onTrace: (cb) => log.on(cb),
    clearTrace: async () => { log.clear(); await Native.clearTrace() },
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
    listBonded: async () => { throw new Error(OFFLINE_NOTE) },
    probeIcc: async () => { throw new Error(OFFLINE_NOTE) },
    trace: () => [],
    onTrace: () => () => {},
    clearTrace: async () => {},
  }
})()

export function resolveBikeLink(online: () => boolean): BikeLinkClient {
  if (nativeLinkAvailable()) return makeNativeLink(online)
  return online() ? backendLink : offlineLink
}
