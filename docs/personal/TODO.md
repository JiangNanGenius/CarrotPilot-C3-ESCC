# CarrotPilot-C3-ESCC Alpha TODO

This file tracks the personal C3 alpha line. Stable daily use stays on `/i`; the SunnyPilot 0.11 alpha line is installed from `/x`.

## Installers

- [x] Keep `/i` as the stable `personal/c3-escc-atune` installer.
- [x] Publish `/x` as the alpha `alpha-sunnypilot-c3` installer.
- [x] Replace the old Qt-style `/x` binary with a SunnyPilot Raylib ARM64 installer.
- [x] Verify the published `/x` binary contains the CarrotPilot-C3-ESCC repo and `alpha-sunnypilot-c3` branch.
- [x] Add `scripts/personal/sunnypilot_c3_installer_audit.py` so future updates can reject old Qt installer binaries.
- [ ] After the user retries `/x`, collect device evidence if it still exits after the download screen.

## Base And C3

- [x] Start from SunnyPilot 0.11.2 staging.
- [x] Add C3/TICI channel gate for `alpha-sunnypilot-c3` and `experimental/sunnypilot-011-c3`.
- [x] Route clone C3 `comma tici` devices through the C3 launcher.
- [x] Keep normal shutdown policy; do not import Mr.One never-shutdown behavior.
- [x] Keep local Wi-Fi, SSH, local web, GitHub update, and model download paths.
- [ ] Run real device parking test on clone C3.

## Cloud Removal

- [x] Disable manager registration for athenad, uploader, Sunnylink daemon, Sunnylink registration, statsd_sp, and backup manager.
- [x] Keep `SunnylinkEnabled`, `EnableSunnylinkUploader`, and `OnroadUploads` ineffective as cloud-start controls.
- [x] Remove user-facing Sunnylink and Onroad Uploads entry points from the alpha UI.
- [ ] Confirm on device that no cloud/upload process exists after boot.

## Seltos 2023 And ESCC

- [x] Add `KIA_SELTOS_2023` as a pure-CAN SCC Seltos profile using the known Seltos 2021-compatible path.
- [x] Keep ESCC automatic through SunnyPilot enhanced SCC detection on `0x2AB`.
- [x] Do not add a broad manual ESCC switch.
- [x] Keep Non-SCC Seltos out of personal matching/selection.
- [ ] Validate on the user's Kia Seltos 2023 with stock model and Carrot controls off first.

## Model Manager

- [x] Use SunnyPilot native model manager and `modeld_tinygrad`.
- [x] Keep stock model as default.
- [x] Restrict model download, verify, switch, and rollback to offroad.
- [ ] Verify model list download and active bundle evidence on C3.

## Speed Limit And Maps

- [x] Add phone/APN/N/Navipilot speed source with freshness timeout.
- [x] Default speed source order: fresh phone, car/instrument, Sunny OSM/mapd.
- [x] Keep route and map display from becoming speed-limit truth by default.
- [x] Default speed offset to zero.
- [x] Add fixed and percentage speed offset modes.
- [x] Default `CarrotMapOverlayEnabled` to off so Mapbox/Kakao overlay does not cover the HUD.
- [ ] Validate speed source switching in display-only mode before enabling active speed assist.

## Carrot, Auto-Tuner, And Fishop Hardware

- [x] Bring over local Carrot Web, CarrotMan-style status, navigation event input, APN/N style phone speed input, SDI/speed-bump/model-speed evidence, and Auto-Tuner core.
- [x] Keep Auto-Tuner auto-apply off by default.
- [x] Keep high-risk controls gated off by default: traffic-light stop, auto-turn speed control, active speed control, Auto-Tuner auto-apply, and fishop auto-overtake.
- [x] Add read-only fishop lane curve, lane quality, lidar blindspot, target, dynamic risk, navigation gate, and overtake suggestion evidence.
- [ ] Only after logs and rollback evidence exist, review whether any fishop hint can move from display-only to controlled experiment.

## Localization And Docs

- [x] Remove obvious Korean-only direct text from the personal alpha surface.
- [x] Add Chinese/English descriptions for the confusing personal controls.
- [x] Document installer split, rollback path, and alpha evidence checks.
- [ ] Continue polishing Chinese descriptions after real-device feedback.

## Update Checklist

- [x] Add `AGENTS.md` with the future-agent update strategy, safety boundaries, branch rules, and C3/Seltos context.
- [x] Add `scripts/personal/sunnypilot_c3_alpha_release_gate.py` as a repeatable fast/full update gate.
- [ ] Fetch SunnyPilot staging and compare watched paths.
- [ ] Fetch CarrotPilot source and compare Carrot, speed, model, and map changes.
- [ ] Fetch mechanical/Auto-Tuner source and compare Auto-Tuner, APN/N, fishop hardware, and local web changes.
- [ ] Re-run static checks, compatibility audit, installer audit, and evidence checker self-tests.
- [ ] Publish alpha only after `/x` installer audit passes.
- [ ] Keep `/i` stable until C3 parking and road evidence are clean.
