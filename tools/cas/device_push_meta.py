#!/usr/bin/env python3
"""
Device-side one-shot: rebuild route_meta.json for routes still in realdata and
push them to the CAS server. rlog/qlog are NOT re-uploaded — only the small
JSON. The server overwrites the existing meta and recomputes car_key, re-binning
UNKNOWN routes to the real car (now that CarName/CarParams are available).

Run on the comma device (SSH terminal):
  cd /data/openpilot
  python tools/cas/device_push_meta.py --dry-run     # show what would be sent
  python tools/cas/device_push_meta.py               # push meta for all local routes
  python tools/cas/device_push_meta.py --route 2026-05-22--14-30-00
  python tools/cas/device_push_meta.py --car HYUNDAI_CASPER_EV   # force a car name

Notes:
- Only routes still present in /data/media/0/realdata are affected. Old routes
  rotated out by the logger are not here — use the PC GUI backfill for those.
- Ignores uploader_state, so it always (re)sends the meta. Safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

# Make openpilot importable when run from /data/openpilot (or anywhere).
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
  ap = argparse.ArgumentParser(description="Re-push route_meta.json from the device.")
  ap.add_argument("--route", default="", help="only this route_id (prefix match)")
  ap.add_argument("--car", default="", help="force this car name into the meta")
  ap.add_argument("--endpoint", default="", help="override upload endpoint")
  ap.add_argument("--dry-run", action="store_true", help="print meta, don't send")
  args = ap.parse_args()

  # Heavy openpilot imports happen after argparse so --help works on a PC that
  # lacks the compiled params extension. This script is meant to run ON THE
  # DEVICE (comma), where these import fine.
  try:
    from openpilot.common.params import Params
    from openpilot.selfdrive.carrot.cas import data_uploader as du
    from openpilot.selfdrive.carrot.cas import upload_config
  except ModuleNotFoundError:
    from common.params import Params
    from selfdrive.carrot.cas import data_uploader as du
    from selfdrive.carrot.cas import upload_config

  params = Params()
  device_id = du.get_device_id(params)
  endpoint = args.endpoint or upload_config.resolve_endpoint(params)
  secret = upload_config.resolve_secret()

  # Group local segments by route.
  routes: dict[str, list[Path]] = {}
  for route_id, _seg, path in du.list_segments():
    if args.route and not route_id.startswith(args.route):
      continue
    routes.setdefault(route_id, []).append(path)

  if not routes:
    print(f"no local routes in {du.REALDATA}"
          + (f" matching '{args.route}'" if args.route else ""))
    return 1

  print(f"device_id = {device_id}")
  print(f"endpoint  = {endpoint}")
  print(f"routes    = {len(routes)}")
  if args.car:
    print(f"force car = {args.car}")

  ok_n = fail_n = 0
  for route_id, seg_paths in sorted(routes.items()):
    meta = du.build_route_meta(params, route_id, seg_paths, device_id)
    if args.car:
      meta["car_name_raw"] = args.car
      meta["car_key"] = args.car
      meta["backfill_source"] = "device_push_meta --car"

    print(f"\n[{route_id}]")
    print(f"  segments={meta.get('segments')} "
          f"car_key={meta.get('car_key') or '<none>'} "
          f"car_name_raw={meta.get('car_name_raw') or '<none>'} "
          f"last_known={meta.get('last_known_car') or '<none>'} "
          f"eps={meta.get('eps_firmware_hash') or '<none>'}")

    if args.dry_run:
      print(json.dumps(meta, ensure_ascii=False, indent=2))
      continue

    fd, tmp_name = tempfile.mkstemp(prefix=f".push_meta_{route_id}_", suffix=".json")
    tmp = Path(tmp_name)
    try:
      with open(fd, "w", encoding="utf-8") as f:
        json.dump(meta, f, sort_keys=True)
      sent_ok, msg, size = du.upload_file(
        endpoint, secret, device_id, route_id, "meta", du.META_FILENAME, tmp,
        str(meta.get("car_key", "")),
        str(meta.get("eps_firmware_hash", "")),
        str(meta.get("cas_model_used", "")),
        str(meta.get("carrot_version", "")),
      )
      print(f"  upload: {'OK' if sent_ok else 'FAIL'} ({size}B) {msg}")
      ok_n += int(sent_ok)
      fail_n += int(not sent_ok)
    finally:
      try:
        tmp.unlink()
      except OSError:
        pass

  if not args.dry_run:
    print(f"\ndone: {ok_n} ok, {fail_n} fail")
  return 0 if fail_n == 0 else 2


if __name__ == "__main__":
  raise SystemExit(main())
