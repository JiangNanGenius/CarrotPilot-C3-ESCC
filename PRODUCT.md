# GeniusPilot Product Context

## Platform
adaptive

## Operating surface
GeniusPilot runs on the comma three as a native embedded driver-assistance interface and is also exercised through desktop replay. The onroad HUD must be readable in a sub-second glance while the vehicle is moving.

## Primary user
The vehicle owner and driver, who needs unambiguous control state, speed targets, speed limits, traffic-light stopping state, and hardware health without interpreting internal names.

## Purpose
Provide safe, visible lateral and longitudinal assistance for the owner's vehicle integration, with fail-visible diagnostics and device-owned updates.

## Product principles
- Safety and control authority are shown before decoration.
- The vehicle instrument speed is the driver's reference; GPS speed is not used for longitudinal control.
- Critical states use large Chinese labels and values that survive a quick glance.
- Missing or stale planner, Panda, model, and update state must be visible rather than silently replaced by a plausible value.
- SunnyPilot is a read-only upstream. Device updates come only from JiangNanGenius/CarrotPilot-C3-ESCC branch genius/c3.
- Settings explain their effect, risk, unit, and default where that prevents ambiguity.

## Onroad information hierarchy
1. Current speed and engagement/alert state.
2. Instrument set speed and planner target.
3. Speed limit and overspeed state.
4. Traffic-light stop/go decision and stop distance.
5. Curve-control targets and hardware diagnostics.
