import type { Bike, ThrillPreset } from './types'
import { bikeCharacter, type BikeCharacter } from './bikeProfiles'

/**
 * What kind of road a bike is built for.
 *
 * The routing engine scores roads against the *rider's* measured lean demand;
 * it has never been told what is parked in the garage. This is the missing
 * half, and it is a preset rather than a measurement: an S 1000 RR asks to be
 * pointed at corners, a GS at passes and altitude, an R 12 at an unhurried
 * scenic line, a CE 04 at the shortest way home inside its charge. Applying a
 * fit only moves the thrill dial and the mode — it cannot move the safety
 * gate, which stays the rider's own.
 */
export interface BikeFit {
  dial: ThrillPreset
  /** A FLOWSTATE mode key; falls back to flow when the backend does not offer it. */
  mode: string
  headline: string
  why: string
}

export const BIKE_FITS: Record<BikeCharacter, BikeFit> = {
  sport: {
    dial: 'Send it',
    mode: 'flow',
    headline: 'Corners, not kilometres',
    why: 'Sport geometry and the lean it invites: the dial goes up and the line follows the best-fitting corners rather than the prettiest view.',
  },
  adventure: {
    dial: 'Flow',
    mode: 'mountain',
    headline: 'Passes and altitude',
    why: 'Long-travel suspension and range: mountain mode weights altitude and switchbacks, so the plan climbs instead of skirting.',
  },
  heritage: {
    dial: 'Cruise',
    mode: 'scenic',
    headline: 'The unhurried scenic line',
    why: 'Relaxed geometry and no hurry: scenic mode weights elevation prominence, and the dial stays low so nothing on the route demands commitment.',
  },
  urban_electric: {
    dial: 'Cruise',
    mode: 'flow',
    headline: 'Inside the charge',
    why: 'Charge range decides the ride: a calm, direct line, because a scenic detour on this bike is range you may not get back.',
  },
}

/** The dial's z* values, as the backend's presets define them. */
export const DIAL_Z: Record<ThrillPreset, number> = {
  Cruise: 0.15,
  Flow: 0.5,
  'Send it': 0.9,
}

export const fitFor = (bike: Bike | null): BikeFit | null =>
  bike ? BIKE_FITS[bikeCharacter(bike)] : null
