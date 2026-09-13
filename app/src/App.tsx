import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppStateProvider, useAppState } from './state/AppState'
import { Shell } from './components/Shell'
import { EmptyState, PrimaryButton } from './components/primitives'
import { RideScreen } from './screens/Ride'
import { PlanScreen } from './screens/Plan'
import { ThrillScreen } from './screens/Thrill'
import { NavigateScreen } from './screens/Navigate'
import { DiscoverScreen } from './screens/Discover'
import { GarageScreen } from './screens/Garage'
import { MoreScreen } from './screens/More'
import { RideDetailScreen } from './screens/RideDetail'
import { GroupScreen } from './screens/Group'
import { HandoffScreen } from './screens/Handoff'
import { MapsScreen } from './screens/Maps'

function Booting() {
  return (
    <div className="px-5 py-6" role="status" aria-label="Loading your garage">
      <div className="label">BMW Motorrad</div>
      <p className="mt-2 text-title">Preparing your ride</p>
      <div className="loading-pulse mt-6 aspect-[3/2] rounded-panel bg-panel" aria-hidden="true" />
      <div className="loading-pulse mt-5 grid grid-cols-3 gap-3" aria-hidden="true">
        {[0, 1, 2].map((i) => <div key={i} className="h-24 rounded-control bg-panel" />)}
      </div>
      <p className="caption mt-5">Loading your motorcycles and saved routes…</p>
    </div>
  )
}

function Content() {
  const { ready, loadError, retryLoading } = useAppState()
  return (
    <Shell>
      {ready ? (
        <Routes>
          <Route path="/" element={<RideScreen />} />
          <Route path="/plan" element={<PlanScreen />} />
          <Route path="/thrill" element={<ThrillScreen />} />
          <Route path="/navigate" element={<NavigateScreen />} />
          <Route path="/discover" element={<DiscoverScreen />} />
          <Route path="/garage" element={<GarageScreen />} />
          <Route path="/more" element={<MoreScreen />} />
          <Route path="/ride/:rideId" element={<RideDetailScreen />} />
          <Route path="/group" element={<GroupScreen />} />
          <Route path="/handoff" element={<HandoffScreen />} />
          <Route path="/maps" element={<MapsScreen />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      ) : (
        loadError ? <div className="p-5"><EmptyState title="Garage unavailable" action={<PrimaryButton onClick={retryLoading}>Try again</PrimaryButton>}>{loadError}</EmptyState></div> : <Booting />
      )}
    </Shell>
  )
}

export default function App() {
  return (
    <AppStateProvider>
      <BrowserRouter>
        <Content />
      </BrowserRouter>
    </AppStateProvider>
  )
}
