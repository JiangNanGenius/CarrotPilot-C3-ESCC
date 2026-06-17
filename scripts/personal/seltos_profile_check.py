#!/usr/bin/env python3
import ast
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
HYUNDAI_DIR = ROOT / "opendbc_repo/opendbc/car/hyundai"
VALUES = HYUNDAI_DIR / "values.py"
FINGERPRINTS = HYUNDAI_DIR / "fingerprints.py"
ALLOWED_EXPLICIT_REFS = {
  "opendbc_repo/opendbc/car/hyundai/values.py",
  "opendbc_repo/opendbc/car/hyundai/fingerprints.py",
}
FORBIDDEN_2023_FLAGS = [
  "HyundaiFlags.CANFD",
  "HyundaiFlags.CANFD_HDA2",
  "HyundaiFlags.CANFD_CAMERA_SCC",
  "HyundaiFlags.CANFD_HDA2_ALT_STEERING",
  "HyundaiFlags.RADAR_SCC",
  "HyundaiFlags.CAMERA_SCC",
]


class SeltosProfileError(Exception):
  pass


def rel(path: Path) -> str:
  return str(path.relative_to(ROOT))


def expr(node: ast.AST) -> str:
  try:
    return ast.unparse(node)
  except AttributeError:
    return ast.dump(node)


def func_name(node: ast.AST) -> str:
  if isinstance(node, ast.Name):
    return node.id
  if isinstance(node, ast.Attribute):
    base = func_name(node.value)
    return f"{base}.{node.attr}" if base else node.attr
  return expr(node)


def assignment_value(tree: ast.Module, name: str) -> ast.AST:
  for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "CAR":
      for stmt in node.body:
        if isinstance(stmt, ast.Assign):
          for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id == name:
              return stmt.value
  raise SeltosProfileError(f"missing CAR.{name} in {rel(VALUES)}")


def require_call(node: ast.AST, name: str) -> ast.Call:
  if not isinstance(node, ast.Call):
    raise SeltosProfileError(f"{name} is not a constructor call")
  return node


def keyword(call: ast.Call, name: str) -> Optional[ast.AST]:
  for kw in call.keywords:
    if kw.arg == name:
      return kw.value
  return None


def constants(node: ast.AST) -> Iterable[object]:
  for child in ast.walk(node):
    if isinstance(child, ast.Constant):
      yield child.value


def attributes(node: ast.AST) -> Iterable[str]:
  for child in ast.walk(node):
    if isinstance(child, ast.Attribute):
      yield func_name(child)


def require(condition: bool, message: str) -> None:
  if not condition:
    raise SeltosProfileError(message)


def require_same_expr(left: ast.AST, right: ast.AST, label: str) -> None:
  left_expr = expr(left)
  right_expr = expr(right)
  require(left_expr == right_expr, f"{label} changed: 2021={left_expr!r}, 2023={right_expr!r}")


def check_platform_configs(tree: ast.Module) -> None:
  seltos_2021 = require_call(assignment_value(tree, "KIA_SELTOS"), "KIA_SELTOS")
  seltos_2023 = require_call(assignment_value(tree, "KIA_SELTOS_2023"), "KIA_SELTOS_2023")

  require(func_name(seltos_2021.func) == "HyundaiPlatformConfig", "KIA_SELTOS must stay a classic CAN HyundaiPlatformConfig")
  require(func_name(seltos_2023.func) == "HyundaiPlatformConfig", "KIA_SELTOS_2023 must stay a classic CAN HyundaiPlatformConfig")
  require(func_name(seltos_2023.func) != "HyundaiCanFDPlatformConfig", "KIA_SELTOS_2023 must not become a CANFD config")

  require(len(seltos_2021.args) >= 2, "KIA_SELTOS constructor missing docs/specs")
  require(len(seltos_2023.args) >= 2, "KIA_SELTOS_2023 constructor missing docs/specs")

  names_2021 = [v for v in constants(seltos_2021.args[0]) if isinstance(v, str) and "Seltos" in v]
  names_2023 = [v for v in constants(seltos_2023.args[0]) if isinstance(v, str) and "Seltos" in v]
  require("Kia Seltos 2021" in names_2021, "KIA_SELTOS display name changed")
  require("Kia Seltos 2023" in names_2023, "KIA_SELTOS_2023 display name changed")

  harness_2021 = [attr for attr in attributes(seltos_2021.args[0]) if attr.startswith("CarHarness.")]
  harness_2023 = [attr for attr in attributes(seltos_2023.args[0]) if attr.startswith("CarHarness.")]
  require(harness_2021 == ["CarHarness.hyundai_a"], f"KIA_SELTOS harness changed: {harness_2021}")
  require(harness_2023 == ["CarHarness.hyundai_a"], f"KIA_SELTOS_2023 harness changed: {harness_2023}")

  require_same_expr(seltos_2021.args[1], seltos_2023.args[1], "Seltos 2023 physical specs must match Seltos 2021")

  flags_2021 = keyword(seltos_2021, "flags")
  flags_2023 = keyword(seltos_2023, "flags")
  require(flags_2021 is not None, "KIA_SELTOS flags missing")
  require(flags_2023 is not None, "KIA_SELTOS_2023 flags missing")
  require_same_expr(flags_2021, flags_2023, "Seltos 2023 flags must match Seltos 2021")

  flags_text = expr(flags_2023)
  for forbidden in FORBIDDEN_2023_FLAGS:
    require(forbidden not in flags_text, f"KIA_SELTOS_2023 must not set {forbidden}")

  config_text = expr(seltos_2023)
  require("hyundai_canfd" not in config_text.lower(), "KIA_SELTOS_2023 must not reference CANFD DBCs")
  require("CarSpecs(mass=1337, wheelbase=2.63, steerRatio=14.56)" in config_text,
          "KIA_SELTOS_2023 should still reuse the known Seltos 2021 physical profile")


def check_non_essential_ecu_parity(text: str) -> None:
  pattern = re.compile(r"Ecu\.abs:\s*\[(.*?)\]", re.S)
  match = pattern.search(text)
  require(match is not None, "cannot find Ecu.abs non-essential ECU list")
  abs_list = match.group(1)
  require("CAR.KIA_SELTOS" in abs_list, "KIA_SELTOS missing from ABS non-essential ECU list")
  require("CAR.KIA_SELTOS_2023" in abs_list, "KIA_SELTOS_2023 missing from ABS non-essential ECU list")


def check_explicit_refs() -> List[str]:
  unexpected: List[str] = []
  actual: List[str] = []
  for path in sorted(HYUNDAI_DIR.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    if "KIA_SELTOS_2023" not in text:
      continue
    path_rel = rel(path)
    actual.append(path_rel)
    if path_rel not in ALLOWED_EXPLICIT_REFS:
      unexpected.append(path_rel)
  if unexpected:
    raise SeltosProfileError(
      "KIA_SELTOS_2023 has new explicit Hyundai file references; review pure-CAN parity first:\n"
      + "\n".join(unexpected)
    )
  return actual


def check_fingerprint_policy() -> str:
  text = FINGERPRINTS.read_text(encoding="utf-8")
  if "CAR.KIA_SELTOS_2023" not in text:
    return "manual selection only; no copied Seltos 2023 FW fingerprint yet"
  require("SP2" in text, "Seltos 2023 fingerprint exists but does not look like SP2 platform data")
  return "Seltos 2023 fingerprint present; keep this tied to real device FW evidence"


def main() -> int:
  try:
    values_text = VALUES.read_text(encoding="utf-8")
    tree = ast.parse(values_text, filename=str(VALUES))

    check_platform_configs(tree)
    check_non_essential_ecu_parity(values_text)
    explicit_refs = check_explicit_refs()
    fingerprint_note = check_fingerprint_policy()

    print("Seltos 2023 profile check")
    print(f"repo: {ROOT}")
    print("KIA_SELTOS_2023: classic CAN HyundaiPlatformConfig")
    print("profile parity: harness, specs, flags match KIA_SELTOS")
    print("explicit refs:")
    for path in explicit_refs:
      print(f"- {path}")
    print(f"fingerprint policy: {fingerprint_note}")
    print("OK: Seltos 2023 profile is still a conservative Seltos 2021 reuse")
    return 0
  except SeltosProfileError as exc:
    print("Seltos profile check failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
