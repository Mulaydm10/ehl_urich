/**
 * mySPIN — the phone side of the BMW / Bosch mySPIN vehicle-data link.
 *
 * Wraps the MySpin Capacitor plugin (app/android/.../MySpinPlugin.java). Live
 * bike signals (speed, RPM, gear, fuel, lean) travel over mySPIN, and the head
 * unit only hands them to an *authorised* app: mySPIN checks, per data key,
 * whether this app's identity (package + signing cert) may read it. So this
 * client can report connection + per-key grant/deny, but on an unregistered
 * app most keys come back denied — that is the truthful state, shown as-is.
 *
 * The proprietary Bosch SDK is not bundled, so on a normal build the plugin
 * reports sdkPresent=false and every reading is absent. Never fabricated.
 *
 * Trace events share BikeLink's shape and are forwarded to the same backend
 * debug trail (POST /api/bmw/link/debug), so mySPIN steps show up live in the
 * in-app radio log, logcat and on the Mac alongside the radio events.
 */
import { Capacitor, registerPlugin } from '@capacitor/core'
import type { PluginListenerHandle } from '@capacitor/core'
import { http } from './http'
import type { LinkTraceEvent } from './bikeLink'

export interface MySpinState {
  sdkPresent: boolean
  registered: boolean
  connected: boolean
  isTwoWheeler: boolean
}

/** One authorised/denied vehicle-data key, as reported by the head unit. */
export interface MySpinAccess {
  key: string
  keyId: number
  granted: boolean
}

/** A vehicle-data callback: the raw values the head unit delivered for a key. */
export interface VehicleDataEvent {
  key: string
  keyId: number
  values?: Record<string, string | null>
  detail?: string
}

interface MySpinPlugin {
  getState(): Promise<MySpinState>
  register(): Promise<MySpinState>
  subscribe(): Promise<MySpinState>
  disconnect(): Promise<MySpinState>
  getTrace(opts: { since: number }): Promise<{ events: LinkTraceEvent[]; nextSeq: number; dropped: number; session: string }>
  clearTrace(): Promise<{ nextSeq: number }>
  addListener(event: 'trace' | 'vehicleData' | 'myspinState', cb: (data: unknown) => void): Promise<PluginListenerHandle>
}

const Native = registerPlugin<MySpinPlugin>('MySpin')

export const mySpinAvailable = (): boolean =>
  Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('MySpin')

const ABSENT: MySpinState = { sdkPresent: false, registered: false, connected: false, isTwoWheeler: false }

/**
 * Parse the numeric value out of a mySPIN vehicle-data bundle. Bosch bundles
 * carry one primitive under a field name that varies by key; we take the first
 * finite number we find. Returns null when the bundle has no numeric value.
 */
export function numericValue(e: VehicleDataEvent): number | null {
  if (!e.values) return null
  for (const v of Object.values(e.values)) {
    const n = Number(v)
    if (Number.isFinite(n)) return n
  }
  return null
}

export interface MySpinClient {
  available: boolean
  getState(): Promise<MySpinState>
  register(): Promise<MySpinState>
  subscribe(): Promise<MySpinState>
  disconnect(): Promise<MySpinState>
  /** Bike vehicle-data callbacks (bike-sourced telemetry). */
  onVehicleData(cb: (e: VehicleDataEvent) => void): () => void
  onState(cb: (s: MySpinState) => void): () => void
  onTrace(cb: (e: LinkTraceEvent) => void): () => void
  access: MySpinAccess[]
}

const post = (path: string, body: unknown) => http.post(`/api/bmw/link${path}`, body)

function makeNativeMySpin(online: () => boolean): MySpinClient {
  const dataSubs = new Set<(e: VehicleDataEvent) => void>()
  const stateSubs = new Set<(s: MySpinState) => void>()
  const traceSubs = new Set<(e: LinkTraceEvent) => void>()
  const access = new Map<string, MySpinAccess>()
  let listening = false
  let queue: LinkTraceEvent[] = []
  let flushTimer: ReturnType<typeof setTimeout> | null = null

  const flush = async () => {
    flushTimer = null
    const batch = queue
    queue = []
    if (!batch.length || !online()) return
    try { await post('/debug', { session: batch[0].session, events: batch }) } catch { /* diagnostics only */ }
  }

  const listen = async () => {
    if (listening) return
    listening = true
    await Native.addListener('trace', (e) => {
      const ev = e as LinkTraceEvent
      if (ev.op === 'myspin.access' && typeof ev.key === 'string') {
        access.set(ev.key, { key: ev.key, keyId: Number(ev.keyId), granted: ev.granted === true })
      }
      for (const cb of traceSubs) cb(ev)
      queue.push(ev)
      if (!flushTimer) flushTimer = setTimeout(() => void flush(), 800)
    })
    await Native.addListener('vehicleData', (d) => { for (const cb of dataSubs) cb(d as VehicleDataEvent) })
    await Native.addListener('myspinState', (s) => { for (const cb of stateSubs) cb(s as MySpinState) })
  }

  return {
    available: true,
    getState: async () => { await listen(); return Native.getState() },
    register: async () => { await listen(); return Native.register() },
    subscribe: async () => { await listen(); return Native.subscribe() },
    disconnect: () => Native.disconnect(),
    onVehicleData: (cb) => { dataSubs.add(cb); return () => { dataSubs.delete(cb) } },
    onState: (cb) => { stateSubs.add(cb); return () => { stateSubs.delete(cb) } },
    onTrace: (cb) => { traceSubs.add(cb); return () => { traceSubs.delete(cb) } },
    get access() { return [...access.values()] },
  }
}

/** No radio and no SDK (browser / emulator without the bike). Honest no-op. */
function makeUnavailableMySpin(): MySpinClient {
  return {
    available: false,
    getState: async () => ABSENT,
    register: async () => ABSENT,
    subscribe: async () => ABSENT,
    disconnect: async () => ABSENT,
    onVehicleData: () => () => {},
    onState: () => () => {},
    onTrace: () => () => {},
    access: [],
  }
}

export function resolveMySpin(online: () => boolean): MySpinClient {
  return mySpinAvailable() ? makeNativeMySpin(online) : makeUnavailableMySpin()
}
