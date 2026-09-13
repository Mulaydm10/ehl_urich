import type { Bike, CurvatureMode, PoiLayerId } from './types'

export type BikeCharacter = 'adventure' | 'sport' | 'heritage' | 'urban_electric'

export interface InstrumentTile {
  id: string
  label: string
  /** Rendered as-is; `null` bike data resolves to an explicit unavailable state. */
  read: (bike: Bike) => { value: string; unit?: string; hint?: string; ratio?: number | null }
}

export interface BikeProfile {
  character: BikeCharacter
  tagline: string
  /** Two-stop gradient used for the bike's hero treatment. */
  hero: [string, string]
  accent: string
  rideModes: string[]
  tiles: InstrumentTile[]
  suggestedMode: CurvatureMode
  suggestedLayers: PoiLayerId[]
  suggestionHeadline: string
  energyLabel: string
}

const unavailable = { value: '--', hint: 'No live data' }

const fuelTile: InstrumentTile = {
  id: 'fuel',
  label: 'Tank',
  read: (b) =>
    b.fuelPercent === null
      ? { ...unavailable, ratio: null }
      : {
          value: String(b.fuelPercent),
          unit: '%',
          hint: `${((b.fuelPercent / 100) * b.tankLitres).toFixed(1)} l left`,
          ratio: b.fuelPercent / 100,
        },
}

const rangeTile: InstrumentTile = {
  id: 'range',
  label: 'Range',
  read: (b) =>
    b.rangeKm === null
      ? { ...unavailable, ratio: null }
      : { value: String(b.rangeKm), unit: 'km', hint: `${b.consumptionLper100} l/100 km`, ratio: null },
}

const odoTile: InstrumentTile = {
  id: 'odo',
  label: 'Odometer',
  read: (b) =>
    b.odometerKm === null
      ? { ...unavailable, ratio: null }
      : { value: b.odometerKm.toLocaleString('de-DE'), unit: 'km', ratio: null },
}

const tyreTile: InstrumentTile = {
  id: 'tyres',
  label: 'Tyres',
  read: (b) =>
    b.tyrePressureBar === null
      ? { ...unavailable, ratio: null }
      : {
          value: `${b.tyrePressureBar.front.toFixed(1)} / ${b.tyrePressureBar.rear.toFixed(1)}`,
          unit: 'bar',
          hint: 'front / rear',
          ratio: null,
        },
}

const serviceTile: InstrumentTile = {
  id: 'service',
  label: 'Service',
  read: (b) =>
    b.serviceDueKm === null
      ? { ...unavailable, ratio: null }
      : { value: b.serviceDueKm.toLocaleString('de-DE'), unit: 'km', hint: b.serviceDueDate ?? '', ratio: null },
}

const batteryTile: InstrumentTile = {
  id: 'battery',
  label: 'Battery',
  read: (b) =>
    b.fuelPercent === null
      ? { ...unavailable, ratio: null }
      : { value: String(b.fuelPercent), unit: '%', hint: 'to 80% in 45 min', ratio: b.fuelPercent / 100 },
}

const voltTile: InstrumentTile = {
  id: 'volt',
  label: '12V battery',
  read: (b) =>
    b.batteryVolt === null ? { ...unavailable, ratio: null } : { value: b.batteryVolt.toFixed(1), unit: 'V', ratio: null },
}

export const BIKE_PROFILES: Record<BikeCharacter, BikeProfile> = {
  adventure: {
    character: 'adventure',
    tagline: 'Gravel, passes and long days',
    hero: ['#2E9CE8', '#0653B6'],
    accent: '#1C69D4',
    rideModes: ['Rain', 'Road', 'Eco', 'Enduro', 'Enduro Pro'],
    tiles: [rangeTile, fuelTile, tyreTile, odoTile, serviceTile],
    suggestedMode: 'curvy',
    suggestedLayers: ['fuel', 'passes', 'hotels'],
    suggestionHeadline: 'Pass roads and gravel links near you',
    energyLabel: 'Fuel',
  },
  sport: {
    character: 'sport',
    tagline: 'Lean angle and late braking',
    hero: ['#E7222E', '#1C69D4'],
    accent: '#E7222E',
    rideModes: ['Rain', 'Road', 'Dynamic', 'Race', 'Race Pro'],
    tiles: [
      {
        id: 'lean',
        label: 'Max lean',
        read: () => ({ value: '47 / 44', unit: '°', hint: 'left / right, season', ratio: null }),
      },
      fuelTile,
      rangeTile,
      odoTile,
      serviceTile,
    ],
    suggestedMode: 'extra_curvy',
    suggestedLayers: ['twisty', 'fuel', 'food'],
    suggestionHeadline: 'Tightest twisties within an hour',
    energyLabel: 'Fuel',
  },
  heritage: {
    character: 'heritage',
    tagline: 'Sunday roads, no hurry',
    hero: ['#D8C9A8', '#8A6E4B'],
    accent: '#D8C9A8',
    rideModes: ['Rain', 'Road', 'Dynamic'],
    tiles: [fuelTile, rangeTile, odoTile, voltTile, serviceTile],
    suggestedMode: 'fast_curvy',
    suggestedLayers: ['food', 'twisty', 'dealers'],
    suggestionHeadline: 'Scenic loops with a coffee stop',
    energyLabel: 'Fuel',
  },
  urban_electric: {
    character: 'urban_electric',
    tagline: 'Silent city, instant torque',
    hero: ['#00D4C8', '#0653B6'],
    accent: '#00D4C8',
    rideModes: ['Eco', 'Rain', 'Road', 'Dynamic'],
    tiles: [
      batteryTile,
      rangeTile,
      {
        id: 'charge',
        label: 'Charging',
        read: () => ({ value: '2h 10', hint: 'full charge, 2.3 kW', ratio: null }),
      },
      odoTile,
      serviceTile,
    ],
    suggestedMode: 'fastest',
    suggestedLayers: ['parking', 'food', 'events'],
    suggestionHeadline: 'Loops inside your charge range',
    energyLabel: 'Charge',
  },
}

const RENDERS: Record<BikeCharacter, string> = {
  adventure: '/bikes/gs-cutout.webp',
  sport: '/bikes/xr-cutout.webp',
  heritage: '/bikes/nine-cutout.webp',
  urban_electric: '/bikes/ce04-cutout.webp',
}

export const bikeRender = (bike: Bike): string => RENDERS[bikeCharacter(bike)]

export const bikeCharacter = (bike: Bike): BikeCharacter => {
  if (bike.model.startsWith('CE')) return 'urban_electric'
  if (bike.model.startsWith('S 1000')) return 'sport'
  if (bike.model.startsWith('R 12')) return 'heritage'
  return 'adventure'
}

export const profileFor = (bike: Bike): BikeProfile => BIKE_PROFILES[bikeCharacter(bike)]
