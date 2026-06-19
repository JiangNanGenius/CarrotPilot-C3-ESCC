# Genius Pilot Visualization Policy

Genius Pilot keeps the driving screen split into two layers: one base visual preset and optional evidence overlays.

This is the rule for mixing the several visual systems in this repository: the base road view is mutually exclusive, but evidence overlays are additive. Carrot's lane and lane-change presentation is preferred when it makes adjacent-lane awareness clearer than SunnyPilot's stock view.

## Stack Order

The driving screen is drawn in this order:

- Camera/video frame.
- Base road renderer selected by `GeniusVisualMode`.
- `GeniusCarrotWorldOverlay`, if enabled.
- `GeniusFishopVisualOverlay`, if enabled and local sensor data is fresh.
- Sunny/Genius HUD, alerts, and driver-state widgets.

This means Sunny, Carrot, and Balanced do not fight over the same base path/lane renderer. Carrot World and Fishop can both be opened on top of any base preset because they are evidence overlays, not base presets.
The short form is: base road renderer, Carrot World overlay, Fishop overlay, then HUD/alerts.

## Mode Relationship

| Surface | Relationship | Default | Purpose |
| --- | --- | --- | --- |
| Sunny base | Mutually exclusive base preset | Off | Minimal upstream-style road renderer. |
| Carrot base | Mutually exclusive base preset | Off | Dense Carrot-style lane/path/lead/radar display. |
| Balanced base | Mutually exclusive base preset | On | Sunny HUD structure with Carrot-preferred lane/path/lead cues. Internally this is the old fusion mode value. |
| Carrot World overlay | Additive evidence overlay | Off | Side-lane, blindspot, lane-change, lead, and radar context. |
| Fishop overlay | Additive evidence overlay | Off | Extra hardware lane/lidar/blindspot/overtake evidence. |
| Full Carrot cluster/world surface | Debug-only local Web page | Off | Source-colored objects, raw radar points, distance/speed labels, and ajouatom-only fields when available. |

The important rule is simple: choose one base display, then optionally add evidence layers. The Carrot-derived lane and lane-change visuals are preferred in `Carrot` and `Balanced` because they make adjacent lanes, blindspot context, and lane-change state easier to read than the stock Sunny road display.

## Base Presets

One base preset is active at a time through `GeniusVisualMode`.

- `Sunny`: minimal upstream-style HUD, original path body, simple lead chevron.
- `Carrot`: denser Carrot-style road view with stronger lane/path emphasis, Carrot lead boxes, radar speed labels, and lane-change intent cues.
- `Balanced`: default C3 preset. It keeps the Sunny HUD structure while using Carrot-style lane/path/lead cues where they are clearer for lane display and lane-change awareness. This is the user-facing name for the internal fusion renderer.

Changing a preset may update the detail controls below, but the user can still adjust them afterward.

- `GeniusLaneLineStyle`: lane-line drawing detail.
- `GeniusLeadRadarVisualMode`: lead and radar display detail.
- `GeniusLaneChangeVisuals`: model lane-change intent cues from existing `onroadEvents`.

## Independent Overlays

`GeniusCarrotWorldOverlay` is independent of the base preset. It draws Carrot-style side-lane, blindspot, lane-change, lead, and radar evidence on top of Sunny, Carrot, or Balanced. It exists because the ajouatom Carrot visualization is clearer than Sunny for adjacent-lane awareness and lane-change context.

The current C3 alpha implementation only uses fields already present in the new base: `modelV2`, `radarState.leadOne/leadTwo`, `carState.leftBlindspot/rightBlindspot`, and `onroadEvents`. It does not fake ajouatom-only fields such as `leftLaneLine/rightLaneLine`, `leadsLeft/leadsRight/leadsCenter`, or `activeLaneLine`.

`GeniusFishopVisualOverlay` is not a base preset. It is an optional top-layer evidence overlay drawn on top of Sunny, Carrot, or Balanced only while local Fishop/lidar data is fresh.

The Fishop overlay may show lane curve evidence, lidar lane status, lidar/camera blindspot state, dynamic blindspot risk, navigation gate status, and overtake suggestion evidence. It must remain display-only unless a separate safety-reviewed control path is intentionally added later.

The recommended stack for your C3 is `Balanced` base plus optional Carrot World and Fishop overlays during parked/debug review. For daily driving, leave the large overlays off unless you are deliberately checking lane-change, blindspot, or extra-hardware evidence.

## Carrot Cluster / World View

The ajouatom Carrot branches include a larger cluster/world visualization with detected vehicles, radar points, source-colored objects, lane highlighting, and radar labels. That is useful, but it is not the same surface as the C3 driving HUD.

Genius Pilot imports the safe subset as `GeniusCarrotWorldOverlay`. The full cluster/world page still needs input schema mapping for ajouatom-only lane/radar fields, layout bounds, and C3 performance cost before it becomes more than an explicit overlay/debug surface.

The input map for that surface lives in `docs/personal/CARROT_CLUSTER_WORLD_SCHEMA.md`. It keeps detected vehicles, raw radar points, lane style codes, road edges, and Fishop evidence in a display-only `GeniusClusterWorldSnapshot` and records missing ajouatom-only fields as fallbacks instead of inventing values.

The first full-surface decision is `/cluster_world`, a debug-only local Web page backed by `/api/cluster_world`. It draws the model path, lane lines, road edges, source-colored detected objects, raw `liveTracks` radar points, distance/speed labels, active sources, and fallbacks. It is read-only, display-only, and uses the same `GeniusClusterWorldSnapshot` schema as the replay contract.

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
- Making Sunny, Carrot, Balanced, and Fishop overlay fight over the same base layer.
- Using a display setting to enable Carrot cluster, Fishop, or auto-overtake control output.

## Current Default

The C3 alpha default is `GeniusVisualMode=2` (`Balanced`), `GeniusLaneLineStyle=1` (`Colored`), `GeniusLeadRadarVisualMode=1` (`Box`), `GeniusLaneChangeVisuals=1`, `GeniusCarrotWorldOverlay=0`, and `GeniusFishopVisualOverlay=0`.
