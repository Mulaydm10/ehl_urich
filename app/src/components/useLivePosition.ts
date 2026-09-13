import { useEffect, useRef, useState } from 'react'

export interface LivePosition {
  lat: number
  lng: number
  /** metres, from the Geolocation API. */
  accuracy: number
  /** km/h, null when the device does not report speed. */
  speedKmh: number | null
  /** degrees, null when heading is unknown. */
  headingDeg: number | null
  at: number
}

export type LiveState = 'idle' | 'locating' | 'tracking' | 'denied' | 'unsupported'

/**
 * Live GPS from the browser/WebView Geolocation API. Keyless and works on the
 * phone in the field; on the emulator it depends on a mock location being set.
 * We never fabricate a position — if permission is denied or unavailable the
 * caller shows an honest "location off" state rather than a fake dot.
 */
export function useLivePosition(enabled: boolean): { state: LiveState; position: LivePosition | null } {
  const [state, setState] = useState<LiveState>('idle')
  const [position, setPosition] = useState<LivePosition | null>(null)
  const watchId = useRef<number | null>(null)

  useEffect(() => {
    if (!enabled) {
      setState('idle')
      return
    }
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setState('unsupported')
      return
    }
    setState('locating')
    watchId.current = navigator.geolocation.watchPosition(
      (p) => {
        setPosition({
          lat: p.coords.latitude,
          lng: p.coords.longitude,
          accuracy: p.coords.accuracy,
          speedKmh: p.coords.speed != null ? Math.max(0, p.coords.speed * 3.6) : null,
          headingDeg: p.coords.heading ?? null,
          at: p.timestamp,
        })
        setState('tracking')
      },
      (err) => setState(err.code === err.PERMISSION_DENIED ? 'denied' : 'unsupported'),
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 15000 },
    )
    return () => {
      if (watchId.current != null) navigator.geolocation.clearWatch(watchId.current)
    }
  }, [enabled])

  return { state, position }
}
