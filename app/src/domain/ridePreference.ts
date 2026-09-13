import type { Bike, ThrillPreset } from './types'
import { bikeCharacter } from './bikeProfiles'

/**
 * What the rider says they want, turned into something the engine measures.
 *
 * Every answer here maps onto a column of the crowd cell table that the mode
 * scan passed, so the plan changes for a reason that can be pointed at. An
 * answer with no column behind it is not offered — see UNANSWERABLE.
 */

export type CurveWant = 'few' | 'some' | 'relentless'
export type ClimbWant = 'flat' | 'rolling' | 'high'
export type TrafficWant = 'either' | 'quiet'
export type IntentWant = 'scenic' | 'challenge' | 'either'

export interface RidePreference {
  /** 1 = only what I ride every day, 5 = past my habit. Sets the thrill dial. */
  comfort: number
  curves: CurveWant
  climb: ClimbWant
  traffic: TrafficWant
  intent: IntentWant
}

export const DEFAULT_PREFERENCE: RidePreference = {
  comfort: 3,
  curves: 'some',
  climb: 'rolling',
  traffic: 'either',
  intent: 'either',
}

export const DIAL_FOR_COMFORT: Record<number, ThrillPreset> = {
  1: 'Cruise',
  2: 'Cruise',
  3: 'Flow',
  4: 'Send it',
  5: 'Send it',
}

export const dialFor = (pref: RidePreference): ThrillPreset =>
  DIAL_FOR_COMFORT[pref.comfort] ?? 'Flow'

interface Term {
  column: string
  weight: number
  why: string
}

/** The weighted columns this preference asks for, strongest first. */
export const termsFor = (pref: RidePreference): Term[] => {
  const terms: Term[] = []
  if (pref.curves === 'relentless')
    terms.push({ column: 'reversals_km', weight: 2, why: 'switchbacks per kilometre, as the crowd rode them' })
  if (pref.curves === 'few')
    terms.push({ column: 'reversals_km', weight: -1, why: 'fewer direction changes per kilometre' })
  if (pref.climb === 'high')
    terms.push({ column: 'elev_mean', weight: 2, why: 'altitude itself — the route climbs rather than skirts' })
  if (pref.climb === 'flat')
    terms.push({ column: 'elev_mean', weight: -1, why: 'stays low where the network offers a choice' })
  if (pref.intent === 'scenic')
    terms.push({ column: 'elev_prominence_m', weight: 1, why: 'how far the road stands above its surroundings' })
  if (pref.intent === 'challenge')
    terms.push({ column: 'rhythm_purity', weight: -1, why: 'broadband corners rather than one repeating bend' })
  if (pref.traffic === 'quiet')
    terms.push({ column: 'n_rides', weight: -1, why: 'roads the crowd rarely rides' })
  return terms.slice(0, 4)
}

/**
 * The engine's mode key for this preference: one of the tested presets when the
 * answers happen to be one, otherwise a `custom:` weight vector the router
 * builds from the same columns. Null means "nothing asked for" — plain flow.
 */
export const modeKeyFor = (pref: RidePreference): string | null => {
  const terms = termsFor(pref)
  if (!terms.length) return null
  return `custom:${terms.map((t) => `${t.column}=${t.weight > 0 ? '+' : ''}${t.weight}`).join(',')}`
}

/** One line per answer, for the rider to read back before planning. */
export const explain = (pref: RidePreference): string[] => {
  const lines = termsFor(pref).map((t) => `${t.column}: ${t.why}`)
  lines.push(
    `Thrill dial ${dialFor(pref)} — how far past your own measured lean the route may ask. ` +
      'Your safety gate is not part of this: roads past it stay deleted.',
  )
  return lines
}

/** Answers the data cannot support, said plainly rather than faked. */
export const UNANSWERABLE: { want: string; why: string }[] = [
  {
    want: 'Left-hand or right-hand corners',
    why: 'the cell table counts direction changes per kilometre, it does not keep the side of each one.',
  },
  {
    want: 'Climbing gradient separately from descending',
    why: 'elevation is stored per cell as mean height and prominence, not as a signed grade for the direction you travel.',
  },
  {
    want: 'Gravel and off-road sections on purpose',
    why: 'unpaved surface is a penalty in the fit score (×0.55) and cannot be inverted into a preference without new data.',
  },
]

/** Where a bike puts the dials before the rider touches them. */
export const preferenceForBike = (bike: Bike | null): RidePreference => {
  if (!bike) return DEFAULT_PREFERENCE
  switch (bikeCharacter(bike)) {
    case 'sport':
      return { comfort: 4, curves: 'relentless', climb: 'rolling', traffic: 'either', intent: 'challenge' }
    case 'adventure':
      return { comfort: 3, curves: 'some', climb: 'high', traffic: 'quiet', intent: 'scenic' }
    case 'heritage':
      return { comfort: 2, curves: 'some', climb: 'rolling', traffic: 'quiet', intent: 'scenic' }
    case 'urban_electric':
      return { comfort: 1, curves: 'few', climb: 'flat', traffic: 'either', intent: 'either' }
  }
}
