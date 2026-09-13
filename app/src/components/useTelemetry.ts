import { useEffect, useRef, useState } from 'react'
import { useLivePosition } from './useLivePosition'
import { resolveMySpin, numericValue, type VehicleDataEvent } from '../services/mySpin'
import { useAppState } from '../state/AppState'

/**
 * Live ride telemetry, fused from what the phone can actually measure and, when
 * an authorised mySPIN link exists, from the bike itself.
 *
 *  - speed:    bike (mySPIN) when granted, else phone GPS (coords.speed).
 *  - lean:     bike ROLE_ANGLE when granted, else phone gyro (deviceorientation).
 *  - gForce:   phone accelerometer (devicemotion). The bike exposes lateral/
 *              longitudinal acceleration only to an authorised app.
 *  - rpm/gear/fuel: bike-only — shown only when mySPIN actually delivers them.
 *
 * Every field carries its `source` so the UI can label it honestly. We never
 * invent a reading: when nothing measures a field it stays null.
 */
export type TelemetrySource = 'bike' | 'phone' | 'none'

export interface Telemetry {
  speedKmh: number | null
  speedSource: TelemetrySource
  leanDeg: number | null
  leanSource: TelemetrySource
  gForce: number | null
  headingDeg: number | null
  rpm: number | null
  gear: number | null
  fuelPercent: number | null
  bikeConnected: boolean
  updatedAt: number
}

const BIKE_STALE_MS = 4000

export function useTelemetry(enabled: boolean): Telemetry {
  const { online } = useAppState()
  const { position } = useLivePosition(enabled)
  const [phoneLean, setPhoneLean] = useState<number | null>(null)
  const [gForce, setGForce] = useState<number | null>(null)
  const [bike, setBike] = useState<{ at: number; speed?: number; lean?: number; rpm?: number; gear?: number; fuel?: number; connected: boolean }>({ at: 0, connected: false })
  const [now, setNow] = useState(() => Date.now())
  const clientRef = useRef(resolveMySpin(() => online))

  // Bike readings must expire on their own, not only when a new one arrives,
  // so a link that goes quiet falls back to the phone instead of freezing.
  useEffect(() => {
    if (!bike.connected) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [bike.connected])

  // Phone motion sensors: lean from orientation, g-force from acceleration.
  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return
    const onOrient = (e: DeviceOrientationEvent) => {
      // gamma is left/right tilt in degrees; that is the lean of a phone
      // mounted upright on the bars. Clamp to a sane motorcycle range.
      if (e.gamma == null) return
      setPhoneLean(Math.max(-60, Math.min(60, e.gamma)))
    }
    const onMotion = (e: DeviceMotionEvent) => {
      const a = e.accelerationIncludingGravity
      if (!a || a.x == null || a.y == null || a.z == null) return
      const mag = Math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z)
      setGForce(mag / 9.81)
    }
    window.addEventListener('deviceorientation', onOrient)
    window.addEventListener('devicemotion', onMotion)
    return () => {
      window.removeEventListener('deviceorientation', onOrient)
      window.removeEventListener('devicemotion', onMotion)
    }
  }, [enabled])

  // mySPIN bike data (only if an authorised link delivers it).
  useEffect(() => {
    if (!enabled) return
    const client = clientRef.current
    if (!client.available) return
    void client.register().then(() => client.subscribe())
    const offState = client.onState((s) => setBike((b) => ({ ...b, connected: s.connected })))
    const offData = client.onVehicleData((e: VehicleDataEvent) => {
      const n = numericValue(e)
      if (n == null) return
      setBike((b) => {
        const next = { ...b, at: Date.now(), connected: true }
        if (e.key === 'display_vehicle_speed' || e.key === 'vehicle_speed_accurate') next.speed = n
        else if (e.key === 'lean_angle') next.lean = n
        else if (e.key === 'display_engine_speed') next.rpm = n
        else if (e.key === 'actual_gear_position') next.gear = n
        else if (e.key === 'fuel_level') next.fuel = n
        return next
      })
    })
    return () => { offState(); offData() }
  }, [enabled])

  const bikeFresh = bike.connected && now - bike.at < BIKE_STALE_MS
  const phoneSpeed = position?.speedKmh ?? null

  const speedKmh = bikeFresh && bike.speed != null ? bike.speed : phoneSpeed
  const speedSource: TelemetrySource = bikeFresh && bike.speed != null ? 'bike' : phoneSpeed != null ? 'phone' : 'none'
  const leanDeg = bikeFresh && bike.lean != null ? bike.lean : phoneLean
  const leanSource: TelemetrySource = bikeFresh && bike.lean != null ? 'bike' : phoneLean != null ? 'phone' : 'none'

  return {
    speedKmh,
    speedSource,
    leanDeg,
    leanSource,
    gForce,
    headingDeg: position?.headingDeg ?? null,
    rpm: bikeFresh ? bike.rpm ?? null : null,
    gear: bikeFresh ? bike.gear ?? null : null,
    fuelPercent: bikeFresh ? bike.fuel ?? null : null,
    bikeConnected: bikeFresh,
    updatedAt: Math.max(position?.at ?? 0, bike.at),
  }
}
