# Genius Pilot Visualization Policy

Genius Pilot keeps the driving screen split into two layers: one base visual preset and optional evidence overlays.

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

`GeniusFishopVisualOverlay` is not a base preset. It is an optional top-layer evidence overlay drawn on top of Sunny, Carrot, or Fusion only while local Fishop/lidar data is fresh.

The Fishop overlay may show lane curve evidence, lidar lane status, lidar/camera blindspot state, dynamic blindspot risk, navigation gate status, and overtake suggestion evidence. It must remain display-only unless a separate safety-reviewed control path is intentionally added later.

## Carrot Cluster / World View

The ajouatom Carrot branches include a larger cluster/world visualization with detected vehicles, radar points, source-colored objects, lane highlighting, and radar labels. That is useful, but it is not the same surface as the C3 driving HUD.

Genius Pilot should import that view as a separate optional page or explicit overlay path, not by mixing its renderer directly into the main HUD. Main HUD work stays lightweight and C3-safe; the cluster/world view can be added after its input schema, layout bounds, and performance cost are mapped.

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

## Current Default

The C3 alpha default is `GeniusVisualMode=2` (`Fusion`), `GeniusLaneLineStyle=1` (`Colored`), `GeniusLeadRadarVisualMode=1` (`Box`), `GeniusLaneChangeVisuals=1`, and `GeniusFishopVisualOverlay=0`.
