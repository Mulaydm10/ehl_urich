/**
 * One place that knows where the backend is and how to talk to it.
 *
 * Dev / preview: VITE_BACKEND_URL is empty, calls go to /api and Vite proxies
 * them to the local FLOWSTATE + BMW server on :8090.
 * APK / Mac: VITE_BACKEND_URL is the tailnet address (e.g. http://100.x.y.z:8090),
 * baked in at build time, so the phone reaches the Mac over Tailscale.
 *
 * Every call has a short timeout and throws on failure so the service layer can
 * fall back to the offline mock and the app never hangs on a dead backend.
 */

const BACKEND_KEY = 'bmw.backendUrl'
const BUILD_DEFAULT: string = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/$/, '')

/**
 * Where the backend lives, resolved at call time so a packaged APK can be
 * pointed at the Mac/Tailscale address from Settings without a rebuild.
 * A localStorage override wins; otherwise the build-time default is used.
 */
function base(): string {
  try {
    const saved = localStorage.getItem(BACKEND_KEY)
    if (saved) return saved.replace(/\/$/, '')
  } catch {
    // localStorage unavailable (SSR / privacy mode) — fall through to default.
  }
  return BUILD_DEFAULT
}

export function getBackendUrl(): string {
  try {
    return localStorage.getItem(BACKEND_KEY) ?? BUILD_DEFAULT
  } catch {
    return BUILD_DEFAULT
  }
}

export function setBackendUrl(url: string): void {
  try {
    const trimmed = url.trim().replace(/\/$/, '')
    if (trimmed) localStorage.setItem(BACKEND_KEY, trimmed)
    else localStorage.removeItem(BACKEND_KEY)
  } catch {
    // Ignore write failures; the app keeps using the build-time default.
  }
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 6000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${base()}${path}`, {
      ...init,
      headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
      signal: controller.signal,
    })
    if (!res.ok) throw new Error(`${path} -> ${res.status}`)
    return (await res.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

export const http = {
  get: <T,>(path: string, timeoutMs?: number) => request<T>(path, undefined, timeoutMs),
  post: <T,>(path: string, body: unknown, timeoutMs?: number) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }, timeoutMs),
}

/** True once we have seen at least one successful backend call this session. */
let live = false
export const backendLive = () => live
export const markLive = (value: boolean) => {
  live = value
}
