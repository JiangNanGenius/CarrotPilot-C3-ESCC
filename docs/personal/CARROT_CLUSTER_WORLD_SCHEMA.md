# Carrot Cluster World Schema

This document maps the larger ajouatom Carrot cluster/world view into a Genius
Pilot display-only schema. It is the contract used by the local
`/cluster_world` debug surface and any future full cluster renderer.

The source surface is the ajouatom Carrot cluster bundle under
`selfdrive/carrot/cluster/`, especially:

- `cluster_models.py`: `ClusterUiState`, `DetectedVehicle`, `RadarPoint`,
  `LaneMarking`, and `ModelPathPoint`.
- `cluster_live.py`: live subscriptions and service update flow.
- `cluster_route_replay.py`: route/live normalization from `carState`,
  `modelV2`, `radarState`, `liveTracks`, CAN corner radar, navigation, and
  lateral/longitudinal plans.
- `cluster_scene.py`: display merging and filtering for detected vehicles,
  radar points, lanes, road edges, planned path, and source-colored objects.

## Policy

The full cluster/world view is an optional visualization surface, not a driving
control owner.

- It may read model, radar, car state, onroad event, plan, navigation, and local
  Fishop evidence.
- It may render detected vehicles, source-colored objects, raw or merged radar
  points, side lanes, road edges, lane-change availability, and labels.
- It must not publish `CarControl`, `sendcan`, planner messages, lane-change
  decisions, or CAN messages.
- Missing ajouatom-only fields must degrade to supported Genius fields or be
  marked unavailable. They must not be fabricated.
- Current C3 HUD remains protected: the full cluster/world view stays outside
  the default main HUD until layout, performance, and control-boundary evidence
  exist.

## Normalized Schema

The first Genius schema is `GeniusClusterWorldSnapshot`. It is a bounded,
display-only snapshot:

```json
{
  "displayOnly": true,
  "controlOutput": false,
  "base": {},
  "lanes": {},
  "objects": [],
  "radarPoints": [],
  "plans": {},
  "fishop": {},
  "sourceAvailability": {},
  "fallbacks": []
}
```

## Field Map

| Schema field | Source priority | Fallback when missing | Notes |
| --- | --- | --- | --- |
| `base.speedKph` | `carState.vEgo` | `0` | Display only. |
| `base.cruiseKph` | `carState.cruiseState.speed` | `null` | May be cluster speed when available later. |
| `base.leftBlinker` / `rightBlinker` | `carState.leftBlinker/rightBlinker` | `false` | Used for display labels only. |
| `base.leftBlindspot` / `rightBlindspot` | `carState.leftBlindspot/rightBlindspot` | `false` | May be complemented by Fishop evidence. |
| `base.laneChangeIntent` | `onroadEvents.preLaneChangeLeft/Right`, `laneChange` | `none` | Must not alter desire helper output. |
| `lanes.laneWidthM` | `modelV2.meta.laneWidthLeft/Right` average | `3.6` | Clamp in renderer later. |
| `lanes.modelPath` | `modelV2.position.x/y/z`, velocity, acceleration | empty | `ModelPathPoint` compatible. |
| `lanes.laneLines` | `modelV2.laneLines`, `laneLineProbs` | empty | Replaces ajouatom `LaneMarking.model_points`. |
| `lanes.roadEdges` | `modelV2.roadEdges`, `roadEdgeStds` | empty | Used for display confidence only. |
| `lanes.leftLaneLine` / `rightLaneLine` | `carState.leftLaneLine/rightLaneLine` | `unknown` | Ajouatom-only style codes; do not fake. |
| `lanes.activeLaneLine` | ajouatom-only `activeLaneLine` if present | `null` | Future imported field. |
| `lanes.leftLaneWidthM` / `rightLaneWidthM` | `modelV2.meta.laneWidthLeft/Right` | `null` | Optional display. |
| `lanes.leftRoadEdgeDistanceM` / `rightRoadEdgeDistanceM` | `modelV2.meta.distanceToRoadEdgeLeft/Right` | `null` | Optional display. |
| `lanes.laneChangeAvailableLeft/Right` | `modelV2.meta.laneChangeAvailableLeft/Right` | `null` | Display-only availability evidence. |
| `objects[] from radarState` | `radarState.leadOne/leadTwo` | none | Labels `TARGET`, `TARGET2`; source `radarState`. |
| `objects[] from model` | `modelV2.leadsV3` | none | Labels `M1`, `M2`; source `modelV2.leadsV3`. |
| `objects[] from carState corners` | `carState.leftLongDist/rightLongDist/leftRearLongDist/rightRearLongDist` | none | Labels `LF/RF/LR/RR`; source `carState`. |
| `objects[] from Fishop` | `Fishop` blindspot/target evidence | none | Local evidence only; source `Fishop`. |
| `objects[].sourceColor` | deterministic source palette | neutral gray | Used by the local debug page only. |
| `radarPoints[]` | `liveTracks.points` | empty | Raw display evidence in the current debug surface. |
| `radarPoints[].sourceColor` | `source` | deterministic default | Source-color objects stay display-only. |
| `radarPoints[].raw` / `merged` | `liveTracks.points` | `raw=true`, `merged=false` | Raw radar points stay evidence until a future merge policy is reviewed. |
| `plans.longitudinal` | `longitudinalPlan` | empty | Speeds, accels, jerk, FCW, should-stop evidence. |
| `plans.lateral` | `lateralPlan` | empty | Curvature and lane-line-use evidence. |
| `fishop` | local Fishop normalized sample | empty | Lane curve, lidar lane data, blindspot, navigation gate, overtake preview. |
| `sourceAvailability` | per-source freshness | `false` per source | Used to show why a layer is absent. |
| `fallbacks[]` | generated by normalizer | empty | Must name every missing ajouatom-only or optional field used by the view. |

## Surface Decision

The current decision is:

- Keep the main C3 driving HUD on `GeniusVisualMode` plus optional
  `GeniusCarrotWorldOverlay` and `GeniusFishopVisualOverlay`.
- Treat the full Carrot cluster/world renderer as a local debug surface, not a
  default HUD mode.
- The first surface is `/cluster_world` in Carrot Web. It renders
  `GeniusClusterWorldSnapshot` with source-colored objects, raw radar points,
  lane/path drawing, distance labels, speed labels, source availability, and
  fallback evidence.
- Promote it beyond debug-only only after C3 layout, performance, and
  control-boundary evidence pass locally and on the device.

## Replay Requirements

Before enabling the larger renderer on the C3, a replay fixture must prove:

- A sample with `modelV2`, `radarState`, `liveTracks`, `carState`, onroad
  events, and Fishop evidence normalizes into lanes, objects, radar points,
  plans, source availability, and fallbacks.
- Missing ajouatom-only fields such as `activeLaneLine` stay unavailable and
  are named in `fallbacks` as `activeLaneLine unavailable`.
- `radarState.leadOne/leadTwo`, `modelV2.leadsV3`,
  `liveTracks.points`, and
  `carState.leftLongDist/rightLongDist/leftRearLongDist/rightRearLongDist`
  must all be represented when they are present in a replay sample.
- `controlOutput` remains `false` and no output channel is published.
- The fixture contains at least one radarState object, one model object, one
  liveTracks radar point, one Fishop object, lane-change availability evidence,
  and road-edge evidence.
