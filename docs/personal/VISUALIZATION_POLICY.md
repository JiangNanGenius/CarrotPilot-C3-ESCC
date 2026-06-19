# Genius Pilot Visualization Policy

Genius Pilot keeps the driving screen split into two layers: one base visual preset and optional evidence overlays.

This is the rule for mixing the several visual systems in this repository: the base road view is mutually exclusive, but evidence overlays are additive. Carrot's lane and lane-change presentation is preferred when it makes adjacent-lane awareness clearer than SunnyPilot's stock view.

## Base Presets

One base preset is active at a time through `GeniusVisualMode`.

- `Sunny`: minimal upstream-style HUD, original path body, simple lead chevron.
- `Carrot`: denser Carrot-style road view with stronger lane/path emphasis, Carrot lead boxes, radar speed labels, and lane-change intent cues.
- `Fusion`: default C3 preset. It keeps the Sunny HUD structure while using Carrot-style lane/path/lead cues where they are clearer for lane display and lane-change awareness.

Changing a preset may update the detail controls below, but the user can still adjust them afterward.

- `GeniusLaneLineStyle`: lane-line drawing detail.
- `GeniusLeadRadarVisualMode`: lead and radar display detail.
- `GeniusLaneChangeVisuals`: model lane-change intent cues from existing `onroadEvents`.

## Independent Overlays

`GeniusCarrotWorldOverlay` is independent of the base preset. It draws Carrot-style side-lane, blindspot, lane-change, lead, and radar evidence on top of Sunny, Carrot, or Fusion. It exists because the ajouatom Carrot visualization is clearer than Sunny for adjacent-lane awareness and lane-change context.

The current C3 alpha implementation only uses fields already present in the new base: `modelV2`, `radarState.leadOne/leadTwo`, `carState.leftBlindspot/rightBlindspot`, and `onroadEvents`. It does not fake ajouatom-only fields such as `leftLaneLine/rightLaneLine`, `leadsLeft/leadsRight/leadsCenter`, or `activeLaneLine`.

`GeniusFishopVisualOverlay` is not a base preset. It is an optional top-layer evidence overlay drawn on top of Sunny, Carrot, or Fusion only while local Fishop/lidar data is fresh.

The Fishop overlay may show lane curve evidence, lidar lane status, lidar/camera blindspot state, dynamic blindspot risk, navigation gate status, and overtake suggestion evidence. It must remain display-only unless a separate safety-reviewed control path is intentionally added later.

## Carrot Cluster / World View

The ajouatom Carrot branches include a larger cluster/world visualization with detected vehicles, radar points, source-colored objects, lane highlighting, and radar labels. That is useful, but it is not the same surface as the C3 driving HUD.

Genius Pilot imports the safe subset as `GeniusCarrotWorldOverlay`. The full cluster/world page still needs input schema mapping for ajouatom-only lane/radar fields, layout bounds, and C3 performance cost before it becomes more than an explicit overlay/debug surface.

## Safety Boundary

Visualization settings must not publish control messages, write planner/CAN state, open sockets, or change lane-change decisions.

Allowed:

- Read model, radar, car state, onroad event, and local Fishop evidence.
- Draw path, lane lines, road edges, lead markers, radar labels, lane-change cues, and Fishop evidence.
- Change display params from the offroad settings UI or local Web/API.

Not allowed:

- Publishing `CarControl`, `sendcan`, planner outputs, or CAN messages.
- Writing params from renderer code.
- Enabling Fishop auto-overtake output from a display setting.
- Making Sunny, Carrot, Fusion, and Fishop overlay fight over the same base layer.
- Using a display setting to enable Carrot cluster, Fishop, or auto-overtake control output.

## Current Default

The C3 alpha default is `GeniusVisualMode=2` (`Fusion`), `GeniusLaneLineStyle=1` (`Colored`), `GeniusLeadRadarVisualMode=1` (`Box`), `GeniusLaneChangeVisuals=1`, `GeniusCarrotWorldOverlay=0`, and `GeniusFishopVisualOverlay=0`.
