import type { RidePreference } from '../domain/ridePreference'

/**
 * The rider's own answers, kept on the phone. No backend call: the engine is
 * stateless about who is asking, and the answers only shape the next request.
 */

const KEY = 'ridefit.ride_preference'

type Listener = (pref: RidePreference | null) => void

let current: RidePreference | null = read()
const listeners = new Set<Listener>()

function read(): RidePreference | null {
  try {
    const raw = window.localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as RidePreference) : null
  } catch {
    return null
  }
}

export const getPreference = (): RidePreference | null => current

export const setPreference = (pref: RidePreference | null) => {
  current = pref
  try {
    if (pref) window.localStorage.setItem(KEY, JSON.stringify(pref))
    else window.localStorage.removeItem(KEY)
  } catch {
    // A phone with storage denied still gets the preference for this session.
  }
  for (const listener of listeners) listener(current)
}

export const subscribePreference = (listener: Listener): (() => void) => {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
