# UI audit and design pass

Code-based review of all nine screens, shared components, bike profiles, and existing motorcycle images. No dependencies, backend, Bluetooth implementation, or service contract changes.

## Screen audit

| Screen | What weakened the original design | Changes |
| --- | --- | --- |
| Ride | The long model name and connection badge shared a narrow photo overlay. Text scrims obscured the motorcycle. Gauge scanlines and glowing details added texture without information. Small readouts competed with filled ride-mode pills. The last telemetry row reserved an empty third column. | Separate bike identity, photograph, and connection strip. Retain all four existing BMW images. Thinner gauge arcs, larger numbers, understated mode labels, proportional telemetry columns, a clear planning action, and larger season statistics. |
| Plan | No screen heading; route summary, fields, curvature, avoidance, and layers had weak hierarchy. Every option used the same filled pill. Inputs lacked a shrinking width and could crowd narrow screens. The long transfer label dominated the button. | Shared page header, grouped fields, a four-step curvature slider, quiet selectable chips, stacked value/unit columns, and shorter transfer copy with the target identified above it. Consistent loading and disabled controls. |
| Discover | Every route had an identical compact card, small map, dense uppercase metadata, and tiny figures. Filter chips could shrink or wrap awkwardly. | One featured route, then divided route rows. Larger key figures, sentence-case metadata, nonshrinking filters, and correctly proportioned map thumbnails. |
| Garage | Image, long model name, connection state, and a separate energy column competed in one row. Selection relied on a bright perimeter. Long status values could collide with labels. | Two-column bike selectors with room for names; energy moves below connection status. A check and `aria-pressed` reinforce selection. Vehicle status uses wrapping label/value columns and simple separators. |
| Maps | Repeated elevated cards made a utility list feel heavy. Tiny pill buttons used the same icon for retry and download; progress and failures had little visual hierarchy. | A storage summary, divided region rows, 44px shared compact controls, distinct action icons, pending states, labeled progress, and restrained failure notices. Existing mock download/failure behavior is preserved. |
| Group | Four columns compressed names, bike models, status, distance, and battery into narrow rows. A lost-signal rider's LED was switched off, muting the alert. | Two-level rider rows: identity/distance above status/phone battery. Stronger regroup hierarchy and a visible red lost-signal indicator. |
| Handoff | An undersized back control, decorative glass texture, and loosely grouped transfer content weakened the TFT presentation. Phone-only bikes still saw a mock speed and TFT view. | Shared back header, a matte instrument frame, clear navigation readouts and transfer grouping. The phone-only TFT is explicitly unavailable; the existing phone fallback remains accessible. |
| Ride detail | Back navigation was small. Each trace had its own floating card, without distance labels. Photo placeholders were decorative gradients. | Shared back header, larger telemetry and lean figures, divided trace sections with distance endpoints and accessible descriptions. Missing photos are labeled instead of represented by gradients. |
| More | Uppercase descriptions and similarly weighted cards made navigation, history, and settings hard to distinguish. Long settings values could collide. | Familiar navigation rows, restrained line icons, larger ride distances, section hierarchy, and wrapping preference values. |

## System decisions

- **Type:** Inter for interface text, Barlow Condensed for instrument values, JetBrains Mono for compact precision metadata. Shared 34px page titles, 21px section titles, 14px body copy, and 12px captions. Uppercase is reserved for short instrument labels. Values and units have distinct treatment.
- **Spacing:** Consistent 20px page gutters, 32px section starts, 16px row spacing, and deliberate grouping. Repeated information uses separators; maps and bike selectors retain containers where they help.
- **Buttons:** One shared implementation for primary, secondary, and compact actions. Main controls are at least 52px high; chips, compact controls, and back buttons are at least 44px. A 10px control radius replaces large rounded pills. Primary actions use solid bike accents with light or dark foregrounds appropriate to the bike. Secondary actions use graphite and a restrained border. Explicit hover, press, focus, disabled, and loading states; selected chips expose `aria-pressed`.
- **Surfaces:** Neutral space black and graphite replace blue-tinted layers. Flat panels use a fine border and minimal inset edge. Removed decorative glow, glass scanlines, background gradients, and photo-placeholder gradients.
- **Colour:** BMW blue `#1C69D4` for the adventure profile; red, heritage, and electric accents still follow the selected bike. Lighter accent text maintains separation from dark surfaces. Semantic green, warning, and alert colours stay localized to status.
- **Instruments:** The range arc opens at the bottom. Removed the inappropriate high-range redline. Larger tabular values and finer strokes give information priority. Unavailable values keep `--`, without a filled gauge or needle.
- **Motion:** Short colour/border transitions and a one-pixel press response replace scaling whole cards. Loading controls communicate pending work and prevent duplicate activation. Reduced-motion preferences suppress animations and movement.
- **Shell:** Removed the decorative desktop glow, fake phone time/battery, and repeated model name. A restrained BMW Motorrad brand strip sits above the content. The mobile frame fits the viewport; navigation has a small active accent marker and safe-area spacing. New screens reset their scroll position.

## Data and interaction details

The R 12 nineT no longer borrows another bike's last ride when it has no recorded rides. Its live instruments, service readings, and TFT preview remain unavailable. All four bike images, accent themes, telemetry sets, and ride-mode sets remain tied to the existing profiles.

The curvature slider maps to the existing four routing modes. Recalculation and import clear an old route query parameter so the newly created route can appear. Transfer, planning, GPX, and region actions continue to use the existing typed mock services in `src/services/api.ts`.

## Validation and limits

- `npm run lint`: passes; the existing Fast Refresh warning in `src/state/AppState.tsx` remains.
- `npm run build`: passes, including TypeScript compilation.
- A temporary server-rendering harness exercised all **36 screen/bike combinations** using the existing mock records. It checked screen titles, accent selection, hero images, ride modes, telemetry labels, missing-data renders, phone-only TFT behavior, and shared disabled/loading/pressed states. No test dependencies were installed.
- The sandbox denied the Vite listening socket (`EPERM`) and Chrome startup. This pass therefore has **not been visually verified in a browser**. The static checks do not establish pixel layout or interactive behavior. Browser review at 320px, 390px, and desktop frame sizes remains the visual validation step.
