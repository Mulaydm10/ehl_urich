/**
 * Live speech-to-speech with OpenAI Realtime.
 *
 * The audio leg is peer-to-peer between this device and OpenAI over WebRTC, so
 * nothing but the signalling passes through our backend. The permanent key
 * stays on the Mac: the backend mints a client secret that lives for a minute,
 * and pins the instructions and the tool list, so the phone cannot widen what
 * the model is allowed to do.
 *
 * The model's function calls arrive here on the data channel. We do not run
 * them locally - they go back to `/api/assistant/tool`, the same execution path
 * the typed assistant uses, so voice and text read exactly the same data and
 * drive the UI through the same actions.
 */

import type { AssistantAction } from './assistant'
import { http } from './http'

export interface RealtimeHandle {
  stop: () => void
}

export type RealtimeState = 'connecting' | 'live' | 'error' | 'closed'

export interface RealtimeCallbacks {
  onState: (state: RealtimeState, detail?: string) => void
  /** What the rider said, once OpenAI has transcribed the turn. */
  onHeard: (text: string) => void
  /** What the assistant said, as text alongside the spoken audio. */
  onReply: (text: string) => void
  onActions: (actions: AssistantAction[]) => void
}

interface SessionGrant {
  ok: boolean
  client_secret?: string
  model?: string
  calls_url?: string
  say?: string
}

interface ToolRun {
  ok: boolean
  /** The whole thing, for the app to draw. */
  result: unknown
  /** The same thing shrunk to what is worth speaking, when it differs. */
  for_model?: unknown
  actions?: AssistantAction[]
}

/** WebRTC plus a microphone. Missing in older WebViews and on insecure origins. */
export const realtimeSupported = (): boolean =>
  typeof RTCPeerConnection !== 'undefined' &&
  typeof navigator !== 'undefined' &&
  !!navigator.mediaDevices?.getUserMedia

export async function startRealtime(
  context: Record<string, unknown>,
  cb: RealtimeCallbacks,
): Promise<RealtimeHandle | null> {
  cb.onState('connecting')

  let grant: SessionGrant
  try {
    grant = await http.post<SessionGrant>('/api/assistant/realtime', { context }, 20000)
  } catch {
    cb.onState('error', 'The server could not start a live voice session.')
    return null
  }
  if (!grant.ok || !grant.client_secret) {
    cb.onState('error', grant.say ?? 'Live voice is not available on the server.')
    return null
  }

  let mic: MediaStream
  try {
    mic = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    cb.onState('error', 'Microphone access was refused.')
    return null
  }

  const pc = new RTCPeerConnection()
  const audio = new Audio()
  audio.autoplay = true
  let stopped = false

  const stop = () => {
    if (stopped) return
    stopped = true
    mic.getTracks().forEach((t) => t.stop())
    audio.srcObject = null
    pc.close()
    cb.onState('closed')
  }

  pc.ontrack = (event) => {
    audio.srcObject = event.streams[0]
    void audio.play().catch(() => undefined)
  }
  for (const track of mic.getTracks()) pc.addTrack(track, mic)

  const channel = pc.createDataChannel('oai-events')
  channel.onopen = () => cb.onState('live')
  channel.onmessage = (event) => {
    void handleEvent(event.data, channel, cb)
  }
  pc.onconnectionstatechange = () => {
    if (pc.connectionState === 'failed') cb.onState('error', 'The live voice link dropped.')
  }

  try {
    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    const res = await fetch(`${grant.calls_url}?model=${encodeURIComponent(grant.model ?? '')}`, {
      method: 'POST',
      body: offer.sdp,
      headers: {
        Authorization: `Bearer ${grant.client_secret}`,
        'Content-Type': 'application/sdp',
      },
    })
    if (!res.ok) throw new Error(`realtime sdp -> ${res.status}`)
    await pc.setRemoteDescription({ type: 'answer', sdp: await res.text() })
  } catch {
    stop()
    cb.onState('error', 'Could not reach the live voice service.')
    return null
  }

  return { stop }
}

async function handleEvent(
  raw: unknown,
  channel: RTCDataChannel,
  cb: RealtimeCallbacks,
): Promise<void> {
  if (typeof raw !== 'string') return
  let event: Record<string, unknown>
  try {
    event = JSON.parse(raw) as Record<string, unknown>
  } catch {
    return
  }
  const type = String(event.type ?? '')

  if (type === 'conversation.item.input_audio_transcription.completed') {
    const text = String(event.transcript ?? '').trim()
    if (text) cb.onHeard(text)
    return
  }
  // The spoken reply, as text. Named differently across API revisions.
  if (type === 'response.output_audio_transcript.done' || type === 'response.audio_transcript.done') {
    const text = String(event.transcript ?? '').trim()
    if (text) cb.onReply(text)
    return
  }
  if (type === 'response.function_call_arguments.done') {
    await runTool(event, channel, cb)
  }
}

async function runTool(
  event: Record<string, unknown>,
  channel: RTCDataChannel,
  cb: RealtimeCallbacks,
): Promise<void> {
  const callId = String(event.call_id ?? '')
  const name = String(event.name ?? '')
  if (!callId || !name) return

  let args: Record<string, unknown> = {}
  try {
    args = JSON.parse(String(event.arguments ?? '{}')) as Record<string, unknown>
  } catch {
    args = {}
  }

  let run: ToolRun
  try {
    run = await http.post<ToolRun>('/api/assistant/tool', { name, args }, 45000)
  } catch {
    const error = { error: 'the app could not reach its backend' }
    run = { ok: false, result: error, for_model: error, actions: [] }
  }
  if (run.actions?.length) cb.onActions(run.actions)

  // Hand the result back and ask for the spoken follow-up. The backend sends
  // a speakable version alongside the full one: route geometry is thousands
  // of points the model has no use for, and truncating it mid-JSON is how a
  // model ends up narrating half a distance.
  channel.send(
    JSON.stringify({
      type: 'conversation.item.create',
      item: {
        type: 'function_call_output',
        call_id: callId,
        output: JSON.stringify(run.for_model ?? run.result).slice(0, 6000),
      },
    }),
  )
  channel.send(JSON.stringify({ type: 'response.create' }))
}
