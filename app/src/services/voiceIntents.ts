import type { Bike, Ride, Route, SeasonStats } from '../domain/types'

/**
 * Local intent matching for the voice assistant. Deliberately small and
 * offline: it answers from data the app already holds and navigates the UI.
 * The same shapes (a spoken answer plus an optional navigation target) are
 * what the OpenAI Realtime tool-call layer will return once it is wired to
 * the backend, so only this resolver gets replaced.
 */

export interface VoiceContext {
  bike: Bike | null
  routes: Route[]
  rides: Ride[]
  stats: SeasonStats | null
  online: boolean
  engine: string
}

export interface VoiceAnswer {
  /** Spoken and shown to the rider. */
  say: string
  /** In-app route to open, when the command implies a screen. */
  go?: string
}

const km = (n: number) => `${Math.round(n)} kilometres`

function has(text: string, ...words: string[]) {
  return words.some((w) => text.includes(w))
}

export function resolveVoice(rawText: string, ctx: VoiceContext): VoiceAnswer {
  const text = rawText.toLowerCase().trim()
  const { bike } = ctx

  if (!text) return { say: 'I did not catch that. Try again.' }

  if (has(text, 'range', 'how far can i', 'how much left')) {
    if (!bike) return { say: 'No motorcycle is selected yet.' }
    return bike.rangeKm == null
      ? { say: `${bike.model} is phone-only right now, so it cannot report range.` }
      : { say: `${bike.model} has about ${km(bike.rangeKm)} of range left.` }
  }

  if (has(text, 'fuel', 'tank', 'petrol', 'gas')) {
    if (!bike) return { say: 'No motorcycle is selected yet.' }
    return bike.fuelPercent == null
      ? { say: `No live fuel reading from ${bike.model}.` }
      : { say: `The tank is at ${Math.round(bike.fuelPercent)} percent.` }
  }

  if (has(text, 'service', 'maintenance', 'inspection')) {
    if (!bike) return { say: 'No motorcycle is selected yet.' }
    return bike.serviceDueKm == null
      ? { say: 'No service interval is available for this motorcycle.', go: '/garage' }
      : { say: `Next service is due in ${km(bike.serviceDueKm)}.`, go: '/garage' }
  }

  if (has(text, 'tyre', 'tire', 'pressure')) {
    if (!bike?.tyrePressureBar) return { say: 'No live tyre pressure reading available.', go: '/garage' }
    const { front, rear } = bike.tyrePressureBar
    return { say: `Tyres are ${front} bar front and ${rear} bar rear.`, go: '/garage' }
  }

  if (has(text, 'loop', 'two hour', '2 hour', 'three hour', '3 hour', 'just ride', 'send it', 'flow')) {
    return {
      say: ctx.online
        ? 'Opening fun-fit planning. Pick a thrill level and I will build a loop.'
        : 'The route engine is not reachable, so I cannot build a live loop. Opening planning anyway.',
      go: '/thrill',
    }
  }

  if (has(text, 'plan', 'route to', 'navigate to', 'take me to', 'ride to')) {
    return { say: 'Opening route planning.', go: '/plan' }
  }

  if (has(text, 'where am i', 'my location', 'position', 'gps')) {
    return { say: 'Showing your live position.', go: '/' }
  }

  if (has(text, 'map', 'satellite', 'offline map', 'download')) {
    return { say: 'Opening maps.', go: '/maps' }
  }

  if (has(text, 'group', 'friends', 'others')) {
    return { say: 'Opening the group ride.', go: '/group' }
  }

  if (has(text, 'garage', 'my bike', 'which bike')) {
    return { say: bike ? `You are on the ${bike.model}.` : 'Opening your garage.', go: '/garage' }
  }

  if (has(text, 'last ride', 'previous ride', 'yesterday')) {
    const last = ctx.rides[0]
    if (!last) return { say: 'No rides are recorded yet.' }
    return {
      say: `Your last ride was ${last.title}, ${km(last.distanceKm)} in ${Math.round(last.durationMin / 60)} hours.`,
      go: `/ride/${last.id}`,
    }
  }

  if (has(text, 'season', 'this year', 'total', 'stats')) {
    const s = ctx.stats
    return s
      ? { say: `This season: ${s.rides} rides, ${km(s.distanceKm)}, and ${s.passesRidden} passes.` }
      : { say: 'Season stats are not loaded.' }
  }

  if (has(text, 'handoff', 'send to bike', 'tft', 'navigator')) {
    return { say: 'Opening handoff to your motorcycle.', go: '/handoff' }
  }

  if (has(text, 'hello', 'hey', 'hi ', 'are you there')) {
    return { say: 'I am here. Ask for range, service, or a flow loop.' }
  }

  return {
    say: 'I can answer range, fuel, service, tyres, your last ride and season stats, or open planning, maps, group and handoff. Conversational planning arrives with the cloud assistant.',
  }
}

export const VOICE_EXAMPLES = [
  'How much range is left?',
  'Plan a two hour flow loop',
  'When is my next service?',
  'Show my last ride',
]
