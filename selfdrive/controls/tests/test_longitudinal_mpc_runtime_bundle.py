import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MPC_DIR = ROOT / "selfdrive/controls/lib/longitudinal_mpc_lib/c_generated_code"
RUNTIME_LIBS = (
  "libacados.so",
  "libblasfeo.so",
  "libhpipm.so",
  "libqpOASES_e.so.3.1",
)


def test_acados_runtime_libraries_are_shipped():
  for name in RUNTIME_LIBS:
    path = MPC_DIR / name
    assert path.is_file(), f"longitudinal MPC runtime library is missing: {path}"

    # A local build can leave ignored libraries behind and hide a broken clean
    # release. When Git metadata is available, require the files to be shipped.
    if (ROOT / ".git").exists():
      relative_path = path.relative_to(ROOT)
      result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(relative_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
      )
      assert result.returncode == 0, f"runtime library is present but not tracked: {relative_path}"


@pytest.mark.skipif(
  platform.system() != "Linux" or platform.machine() != "aarch64",
  reason="the shipped longitudinal MPC extension targets the C3 ARM64 runtime",
)
def test_longitudinal_mpc_imports_on_c3():
  env = os.environ.copy()
  env["PYTHONPATH"] = os.pathsep.join((str(ROOT), env.get("PYTHONPATH", "")))
  subprocess.run(
    [
      sys.executable,
      "-c",
      "from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc",
    ],
    cwd=ROOT,
    env=env,
    check=True,
  )
