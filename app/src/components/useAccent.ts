import { useEffect, useState } from 'react'

/**
 * Leaflet writes colours to SVG presentation attributes, where `var(--accent)`
 * and `color-mix()` never resolve. So the per-bike accent has to be read back
 * as a concrete hex before it is handed to a Polyline.
 */
export function useAccent(): string {
  const [accent, setAccent] = useState('#1C69D4')
  useEffect(() => {
    const raw = getComputedStyle(document.body).getPropertyValue('--accent').trim()
    if (raw) setAccent(raw)
  }, [])
  return accent
}

const clamp = (n: number) => Math.min(255, Math.max(0, Math.round(n)))

function parseHex(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)]
}

/** Blend two hex colours, t=0 -> a, t=1 -> b. Used for the flow gradient. */
export function mixHex(a: string, b: string, t: number): string {
  const [ar, ag, ab] = parseHex(a)
  const [br, bg, bb] = parseHex(b)
  const u = Math.min(1, Math.max(0, t))
  const to2 = (n: number) => clamp(n).toString(16).padStart(2, '0')
  return `#${to2(ar + (br - ar) * u)}${to2(ag + (bg - ag) * u)}${to2(ab + (bb - ab) * u)}`
}
