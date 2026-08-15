#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SHADOW = Path(os.environ.get("GENIUS_REPLAY_SHADOW", "/tmp/gp-replay-shadow"))
DEFAULT_EIGEN_INCLUDE = Path("/opt/homebrew/opt/eigen/include")
LOCATIOND_GENERATED = ROOT / "openpilot/selfdrive/locationd/models/generated"
LONG_MPC_GENERATED = ROOT / "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/c_generated_code"
LONG_MPC_SOURCES = (
  "acados_ocp_solver_pyx.c",
  "acados_solver_long.c",
  "long_model/long_expl_ode_fun.c",
  "long_model/long_expl_vde_forw.c",
  "long_model/long_expl_vde_adj.c",
  "long_constraints/long_constr_h_fun_jac_uxt_zt.c",
  "long_constraints/long_constr_h_fun.c",
  "long_cost/long_cost_y_0_fun.c",
  "long_cost/long_cost_y_0_fun_jac_ut_xt.c",
  "long_cost/long_cost_y_0_hess.c",
  "long_cost/long_cost_y_fun.c",
  "long_cost/long_cost_y_fun_jac_ut_xt.c",
  "long_cost/long_cost_y_hess.c",
  "long_cost/long_cost_y_e_fun.c",
  "long_cost/long_cost_y_e_fun_jac_ut_xt.c",
  "long_cost/long_cost_y_e_hess.c",
)


def output_text(*parts: object) -> str:
  chunks: list[str] = []
  for part in parts:
    if part is None:
      continue
    if isinstance(part, bytes):
      chunks.append(part.decode("utf-8", errors="replace"))
    else:
      chunks.append(str(part))
  return "".join(chunks)


def run(cmd: Sequence[str], timeout_s: int = 120) -> dict[str, Any]:
  try:
    proc = subprocess.run(
      list(cmd),
      cwd=ROOT,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      check=False,
      timeout=timeout_s,
    )
    return {
      "command": list(cmd),
      "ok": proc.returncode == 0,
      "returnCode": proc.returncode,
      "output": proc.stdout.strip()[-4000:],
      "timeoutS": timeout_s,
    }
  except subprocess.TimeoutExpired as exc:
    output = output_text(exc.stdout, exc.stderr)
    return {
      "command": list(cmd),
      "ok": False,
      "returnCode": 124,
      "output": f"timed out after {timeout_s}s\n{str(output).strip()}"[-4000:],
      "timeoutS": timeout_s,
    }
  except OSError as exc:
    return {"command": list(cmd), "ok": False, "returnCode": 127, "output": str(exc), "timeoutS": timeout_s}


def py_value(code: str) -> str:
  proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, check=True)
  return proc.stdout.strip()


def acados_root() -> Path:
  return Path(py_value("import acados, os; print(os.path.dirname(acados.__file__))"))


def compile_rednose_extension(shadow: Path, eigen_include: Path, dry_run: bool) -> dict[str, Any]:
  py_include = Path(sysconfig.get_paths()["include"])
  numpy_include = Path(py_value("import numpy; print(numpy.get_include())"))
  ext_suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
  output = shadow / f"rednose/helpers/ekf_sym_pyx{ext_suffix}"
  cmd = [
    "clang++",
    "-std=c++17",
    "-O2",
    "-fPIC",
    "-bundle",
    "-undefined",
    "dynamic_lookup",
    f"-I{py_include}",
    f"-I{numpy_include}",
    "-I.",
    "-Irednose_repo",
    "-Irednose_repo/rednose",
    f"-I{eigen_include}",
    "rednose_repo/rednose/helpers/ekf_sym_pyx.cpp",
    "rednose_repo/rednose/helpers/ekf_sym.cc",
    "rednose_repo/rednose/helpers/ekf_load.cc",
    "-o",
    str(output),
  ]
  return {"command": cmd, "ok": True, "output": "dry run"} if dry_run else run(cmd, 180)


def compile_locationd_dylib(name: str, shadow: Path, eigen_include: Path, dry_run: bool) -> dict[str, Any]:
  src = f"openpilot/selfdrive/locationd/models/generated/{name}.cpp"
  output = shadow / f"openpilot/selfdrive/locationd/models/generated/lib{name}.dylib"
  cmd = [
    "clang++",
    "-std=c++17",
    "-O2",
    "-fPIC",
    "-dynamiclib",
    "-undefined",
    "dynamic_lookup",
    "-I.",
    "-Irednose_repo",
    "-Irednose_repo/rednose",
    f"-I{eigen_include}",
    src,
    "-o",
    str(output),
  ]
  return {"command": cmd, "ok": True, "output": "dry run"} if dry_run else run(cmd, 120)


def install_locationd_dylibs(shadow: Path) -> list[Path]:
  installed: list[Path] = []
  for name in ("car", "pose"):
    src = shadow / f"openpilot/selfdrive/locationd/models/generated/lib{name}.dylib"
    dst = LOCATIOND_GENERATED / f"lib{name}.dylib"
    if src.exists():
      shutil.copy2(src, dst)
      installed.append(dst)
  return installed


def compile_acados_extension(dry_run: bool) -> dict[str, Any]:
  py_include = Path(sysconfig.get_paths()["include"])
  numpy_include = Path(py_value("import numpy; print(numpy.get_include())"))
  ext_suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
  acados = acados_root()
  include = acados / "install/include"
  lib = acados / "install/lib"
  output = LONG_MPC_GENERATED / f"acados_ocp_solver_pyx{ext_suffix}"
  cmd = [
    "clang",
    "-std=c99",
    "-O2",
    "-fPIC",
    "-bundle",
    "-undefined",
    "dynamic_lookup",
    f"-I{py_include}",
    f"-I{numpy_include}",
    f"-I{include}",
    f"-I{include / 'acados'}",
    f"-I{include / 'blasfeo/include'}",
    f"-I{include / 'hpipm/include'}",
    f"-I{LONG_MPC_GENERATED}",
    f"-Wl,-rpath,{lib}",
    *(str(LONG_MPC_GENERATED / src) for src in LONG_MPC_SOURCES),
    f"-L{lib}",
    "-lacados",
    "-lhpipm",
    "-lblasfeo",
    "-lm",
    "-o",
    str(output),
  ]
  if dry_run:
    return {"command": cmd, "ok": True, "output": "dry run"}
  return run(cmd, 240)


def verify_shadow(shadow: Path) -> dict[str, Any]:
  env = os.environ.copy()
  env["PYTHONPATH"] = f"{shadow}{os.pathsep}{ROOT}"
  cmd = [
    sys.executable,
    "-P",
    "-c",
    (
      "from openpilot.selfdrive.locationd.models.car_kf import CarKalman; "
      "from openpilot.selfdrive.locationd.models.pose_kf import PoseKalman; "
      f"ck=CarKalman({str(LOCATIOND_GENERATED)!r}); "
      f"pk=PoseKalman({str(LOCATIOND_GENERATED)!r}, 1.0); "
      "print('rednose_shadow_ok', ck.filter.state().shape, pk.filter.state().shape)"
    ),
  ]
  try:
    proc = subprocess.run(cmd, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False, timeout=45)
    return {
      "command": cmd,
      "ok": proc.returncode == 0,
      "returnCode": proc.returncode,
      "output": proc.stdout.strip()[-4000:],
    }
  except subprocess.TimeoutExpired as exc:
    output = output_text(exc.stdout, exc.stderr)
    return {"command": cmd, "ok": False, "returnCode": 124, "output": str(output).strip()[-4000:]}


def verify_acados(shadow: Path) -> dict[str, Any]:
  env = os.environ.copy()
  env["PYTHONPATH"] = f"{shadow}{os.pathsep}{ROOT}"
  cmd = [
    sys.executable,
    "-P",
    "-c",
    (
      "from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc; "
      "mpc=LongitudinalMpc(); "
      "print('acados_shadow_ok', type(mpc).__name__)"
    ),
  ]
  try:
    proc = subprocess.run(cmd, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False, timeout=60)
    return {
      "command": cmd,
      "ok": proc.returncode == 0,
      "returnCode": proc.returncode,
      "output": proc.stdout.strip()[-4000:],
    }
  except subprocess.TimeoutExpired as exc:
    output = output_text(exc.stdout, exc.stderr)
    return {"command": cmd, "ok": False, "returnCode": 124, "output": str(output).strip()[-4000:]}


def self_test() -> int:
  text = Path(__file__).read_text(encoding="utf-8")
  required = (
    "Genius Pilot Mac Replay Shadow Builder",
    "ekf_sym_pyx",
    "libcar.dylib",
    "libpose.dylib",
    "GENIUS_REPLAY_SHADOW",
    "acados_ocp_solver_pyx",
    "LONG_MPC_GENERATED",
    "LongitudinalMpc",
    "CarKalman",
    "PoseKalman",
    "clang++",
    "clang",
    "-undefined",
    "dynamic_lookup",
    "--install-locationd-dylibs",
    "--build-acados",
  )
  if not all(token in text for token in required):
    print("FAIL Mac replay shadow builder self-test: missing token")
    return 1
  print("PASS Mac replay shadow builder self-test")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Genius Pilot Mac Replay Shadow Builder")
  parser.add_argument("--shadow", type=Path, default=DEFAULT_SHADOW, help="native-extension shadow path")
  parser.add_argument("--eigen-include", type=Path, default=DEFAULT_EIGEN_INCLUDE, help="Eigen include prefix")
  parser.add_argument("--install-locationd-dylibs", action=argparse.BooleanOptionalAction, default=True,
                      help="copy generated libcar/libpose.dylib into the ignored repo generated dir for process replay")
  parser.add_argument("--build-acados", action=argparse.BooleanOptionalAction, default=True,
                      help="build an ignored macOS acados_ocp_solver_pyx extension for plannerd replay")
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--json", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  report: dict[str, Any] = {
    "title": "Genius Pilot Mac Replay Shadow Builder",
    "shadow": str(args.shadow),
    "python": sys.executable,
    "eigenInclude": str(args.eigen_include),
    "ok": False,
    "steps": [],
    "installedLocationdDylibs": [],
    "installedAcadosExtension": None,
  }

  if not (args.eigen_include / "eigen3/Eigen/Core").exists():
    report["steps"].append({"name": "eigen include", "ok": False, "output": f"missing {args.eigen_include}/eigen3/Eigen/Core"})
  else:
    if not args.dry_run:
      shutil.rmtree(args.shadow / "rednose", ignore_errors=True)
      shutil.copytree(ROOT / "rednose_repo/rednose", args.shadow / "rednose")
      for linux_so in (args.shadow / "rednose/helpers").glob("ekf_sym_pyx*.so"):
        linux_so.unlink()
      (args.shadow / "openpilot/selfdrive/locationd/models/generated").mkdir(parents=True, exist_ok=True)

    steps = [
      ("rednose ekf_sym_pyx", compile_rednose_extension(args.shadow, args.eigen_include, args.dry_run)),
      ("locationd libcar.dylib", compile_locationd_dylib("car", args.shadow, args.eigen_include, args.dry_run)),
      ("locationd libpose.dylib", compile_locationd_dylib("pose", args.shadow, args.eigen_include, args.dry_run)),
    ]
    for name, step in steps:
      step["name"] = name
      report["steps"].append(step)

    if all(step["ok"] for _, step in steps) and args.install_locationd_dylibs and not args.dry_run:
      report["installedLocationdDylibs"] = [str(path) for path in install_locationd_dylibs(args.shadow)]
      verify = verify_shadow(args.shadow)
      verify["name"] = "rednose shadow import"
      report["steps"].append(verify)

  if args.build_acados:
    acados_step = compile_acados_extension(args.dry_run)
    acados_step["name"] = "plannerd acados mac extension"
    report["steps"].append(acados_step)
    if acados_step["ok"] and not args.dry_run:
      ext_suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
      report["installedAcadosExtension"] = str(LONG_MPC_GENERATED / f"acados_ocp_solver_pyx{ext_suffix}")
      verify = verify_acados(args.shadow)
      verify["name"] = "acados long_mpc import"
      report["steps"].append(verify)

  report["ok"] = all(step["ok"] for step in report["steps"]) and bool(report["steps"])
  if args.json:
    print(json.dumps(report, indent=2, sort_keys=True))
  else:
    print(f"{'PASS' if report['ok'] else 'FAIL'} {report['title']}")
    for step in report["steps"]:
      print(f"{'PASS' if step['ok'] else 'FAIL'} {step['name']}")
      if not step["ok"] and step.get("output"):
        print(step["output"])
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
