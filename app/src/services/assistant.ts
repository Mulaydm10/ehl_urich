/**
 * Client for the server-side ride assistant (flowstate/app/assistant.py).
 *
 * The OpenAI key lives on the Mac, never in the APK, so every model call goes
 * through the backend. The backend runs the tool calls against the real
 * FLOWSTATE engine and BMW services and hands back what to say plus what the
 * app should do. When the backend has no key, or is unreachable, the caller
 * falls back to the on-device resolver in `voiceIntents.ts`.
 */
import { http } from './http'

export type AssistantAction =
  | { type: 'navigate'; screen: string }
  | { type: 'select_bike'; bikeId: string }

export interface AssistantStatus {
  enabled: boolean
  model: string | null
  engine: string
  tools: string[]
  reason?: string
}

export interface AssistantReply {
  ok: boolean
  say: string
  actions: AssistantAction[]
  toolsUsed: string[]
}

/** Screens the backend may ask for, mapped to this app's routes. */
const ROUTE_BY_SCREEN: Record<string, string> = {
  ride: '/',
  plan: '/plan',
  thrill: '/thrill',
  discover: '/discover',
  garage: '/garage',
  group: '/group',
  maps: '/maps',
  handoff: '/handoff',
  more: '/more',
}

export const routeForScreen = (screen: string): string | null =>
  ROUTE_BY_SCREEN[screen.toLowerCase()] ?? null

export async function getAssistantStatus(): Promise<AssistantStatus | null> {
  try {
    return await http.get<AssistantStatus>('/api/assistant/status')
  } catch {
    return null
  }
}

interface RawReply {
  ok?: boolean
  say?: string
  actions?: AssistantAction[]
  tools_used?: string[]
}

/**
 * Ask the cloud assistant. Returns null when it is unavailable — a disabled
 * backend must not silently turn into an invented answer.
 */
export async function askAssistant(
  text: string,
  context: Record<string, unknown>,
): Promise<AssistantReply | null> {
  try {
    const raw = await http.post<RawReply>('/api/assistant', { text, context }, 45000)
    if (!raw.ok || !raw.say) return null
    return {
      ok: true,
      say: raw.say,
      actions: raw.actions ?? [],
      toolsUsed: raw.tools_used ?? [],
    }
  } catch {
    return null
  }
}
