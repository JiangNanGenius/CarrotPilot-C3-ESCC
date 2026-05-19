#!/usr/bin/env python3
import argparse

from openpilot.tools.lib.logreader import LogReader


def main():
  parser = argparse.ArgumentParser(description="Train/export a CAS JSON model from rlogs.")
  parser.add_argument("--rlogs", nargs="+", required=True, help="rlog files, route URLs, or directories")
  parser.add_argument("--car", required=True, help="car fingerprint/name for the exported model")
  parser.add_argument("--output", required=True, help="output JSON path")
  parser.add_argument("--kind", choices=("torque", "angle"), default="torque")
  args = parser.parse_args()

  counts = {}
  for source in args.rlogs:
    for msg in LogReader(source):
      which = msg.which()
      counts[which] = counts.get(which, 0) + 1

  print(f"CAS training skeleton loaded logs for {args.car} ({args.kind})")
  for key in ("carState", "modelV2", "controlsState", "lateralPlan", "liveTorqueParameters", "carParams"):
    print(f"{key}: {counts.get(key, 0)}")
  print("Training/export is not implemented yet; Phase 0 skeleton only.")


if __name__ == "__main__":
  main()

