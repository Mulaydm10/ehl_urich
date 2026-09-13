import { Link } from 'react-router-dom'
import { useState } from 'react'
import { ArrowRight, Bluetooth, ChevronDown, CornerUpRight, Monitor, Send, Smartphone } from 'lucide-react'
import { useAppState } from '../state/AppState'
import { RouteMap } from '../components/RouteMap'
import { BikeImage } from '../components/BikeImage'
import { StatusLed } from '../components/Cluster'
import { BackHeader, EmptyState, Feedback, PrimaryButton, Unavailable } from '../components/primitives'
import { BikeLinkPanel, useBikeLink } from '../components/BikeLinkPanel'
import type { LinkTransfer } from '../services/bikeLink'

export function HandoffScreen() {
  const { routes, activeRouteId, bike } = useAppState()
  const { link, status: linkStatus } = useBikeLink()
  const [result, setResult] = useState<LinkTransfer | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const route = routes.find((r) => r.id === activeRouteId) ?? routes[0]
  if (!route || !bike) return <div><BackHeader to="/more" title="Send to bike" /><div className="p-5"><EmptyState title="No route ready" action={<Link to="/discover" className="button button-secondary">Browse routes</Link>}>Choose a route before sending it to your motorcycle.</EmptyState></div></div>
  const phoneOnly = bike.connection === 'phone_only'
  const linkConnected = linkStatus?.connection.state === 'connected' && !linkStatus.standIn
  const linkLabel = !linkStatus ? 'Checking link' : linkStatus.standIn ? 'Stand-in link' : linkConnected ? 'Connected' : linkStatus.transport === 'offline' ? 'No link' : 'Not connected'

  return (
    <div className="pb-8">
      <BackHeader to="/plan" title="Send to bike" detail={bike.model} />
      <div className="vehicle-hero !h-[190px]"><BikeImage bike={bike} priority /></div>
      <div className="mb-7 mt-5 flex items-center justify-center gap-4 text-ash"><Smartphone size={17} strokeWidth={1.5} /><ArrowRight size={13} /><StatusLed on={linkConnected} tone={linkStatus?.standIn ? 'warn' : 'ok'}>{phoneOnly ? 'Phone only' : linkLabel}</StatusLed><Monitor size={17} strokeWidth={1.5} /></div>
      <section className="panel mx-6 p-5">
        <p className="label">{phoneOnly ? 'Ready on your phone' : 'Ready to transfer'}</p>
        <h2 className="mt-2 text-title">{route.name}</h2>
        <div className="mt-5 flex items-end justify-between"><div><span className="readout text-[40px]">{route.distanceKm}</span><span className="unit ml-2">km</span></div><p className="caption">{route.pois.length} {route.pois.length === 1 ? 'waypoint' : 'waypoints'}</p></div>
        <p className="caption mt-4 border-t border-white/[0.065] pt-4">{phoneOnly ? 'Navigation stays on your phone.' : bike.hasConnectedRideNavigator ? 'To your ConnectedRide Navigator' : 'To your 6.5″ TFT'}<br />Your shaping points stay with the route.</p>
      </section>
      <div className="space-y-4 px-6 pt-6">
        <PrimaryButton busy={busy} onClick={async () => {
          setBusy(true)
          setError(null)
          setResult(null)
          try { setResult(await link.sendRoute(route.id, bike.id)) }
          catch { setError('Transfer interrupted. Your route is saved. Try again.') }
          finally { setBusy(false) }
        }}>
          {phoneOnly ? <Smartphone size={17} /> : <Send size={17} />}{busy ? 'Transferring…' : phoneOnly ? 'Use phone navigation' : 'Send route to bike'}
        </PrimaryButton>
        {result ? <Feedback tone={result.ok ? 'success' : result.status === 'failed' ? 'error' : 'info'}>
          <div className="font-medium">{result.standIn ? 'Stand-in — nothing sent to the bike' : result.status === 'pending_phone' ? 'Waiting for the phone to send' : result.ok ? `Sent to ${result.target}` : 'Not sent'}</div>
          <p className="caption mt-1">{result.message}</p>
        </Feedback> : null}
        {error ? <Feedback tone="error">{error}</Feedback> : null}
      </div>
      <details className="settings-disclosure mt-5" open={!linkConnected}>
        <summary><span className="flex items-center gap-3"><Bluetooth size={19} strokeWidth={1.5} /><span className="text-[14px] font-medium">Bike link</span></span><ChevronDown size={16} /></summary>
        <div><BikeLinkPanel /></div>
      </details>
      <details className="settings-disclosure mt-5">
        <summary><span className="flex items-center gap-3"><Monitor size={19} strokeWidth={1.5} /><span className="text-[14px] font-medium">{phoneOnly ? 'Phone navigation' : 'TFT preview'}</span></span><ChevronDown size={16} /></summary>
        <div>
          {phoneOnly ? <Unavailable note="TFT unavailable for this BMW." /> : <div className="relative overflow-hidden rounded-control">
            <RouteMap path={route.path} height={200} showStartEnd={false} attribution={false} active />
            <div className="absolute left-3 top-3 flex items-center gap-3 rounded-control bg-void/95 p-3"><CornerUpRight size={26} /><div><div className="readout text-[30px]">1.2<span className="unit ml-1">km</span></div><div className="caption mt-1">Kesselbergstr.</div></div></div>
            <div className="absolute bottom-3 right-3 rounded-control bg-void/95 px-3 py-2 text-right"><div className="readout text-[42px]">78</div><div className="unit">km/h</div></div>
          </div>}
        </div>
      </details>
    </div>
  )
}
