import { useState } from 'react'
import { ImageOff } from 'lucide-react'
import type { Bike } from '../domain/types'
import { bikeRender } from '../domain/bikeProfiles'

type BikeImageProps = { bike: Bike; className?: string; priority?: boolean; decorative?: boolean }

export function BikeImage(props: BikeImageProps) {
  return <BikePhoto key={props.bike.id} {...props} />
}

function BikePhoto({ bike, className = '', priority = false, decorative = false }: BikeImageProps) {
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)
  return <span className={`relative bike-image block overflow-hidden ${className}`}>
    {!loaded && !failed ? <span className="loading-pulse absolute inset-0 bg-raised" aria-hidden="true" /> : null}
    {failed ? <span className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-ash" role="img" aria-label={`${bike.model} image unavailable`}>
      <ImageOff size={22} strokeWidth={1.5} />
      {priority ? <span className="caption">Image unavailable</span> : null}
    </span> : <img src={bikeRender(bike)} alt={decorative ? '' : bike.model} className={`h-full w-full object-contain transition-opacity duration-150 ${loaded ? 'opacity-100' : 'opacity-0'}`} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} loading={priority ? 'eager' : 'lazy'} fetchPriority={priority ? 'high' : 'auto'} />}
  </span>
}
