#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import time
from collections import Counter
from datetime import datetime
from tkinter import filedialog, messagebox, ttk


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path.home() / ".cas_train" / "gui_config.json"
LOG_FILENAMES = {"rlog", "rlog.bz2", "rlog.zst", "raw_log.bz2"}
LOG_SUFFIXES = ("--rlog", "--rlog.bz2", "--rlog.zst", "--raw_log.bz2")


def windows_to_wsl(path: str) -> str:
  path = str(Path(path))
  if len(path) >= 2 and path[1] == ":":
    drive = path[0].lower()
    rest = path[2:].replace("\\", "/").lstrip("/")
    return f"/mnt/{drive}/{rest}"
  return path.replace("\\", "/")


def quote(value: str) -> str:
  return shlex.quote(value)


# ── Host environment auto-detection helpers ──────────────────────────────

def detect_wsl() -> bool:
  """Return True only if WSL is actually usable (distro available)."""
  if os.name != "nt":
    return False
  try:
    r = subprocess.run(["wsl", "--status"], capture_output=True, timeout=5)
    if r.returncode != 0:
      return False
    # 'wsl --status' on a working host prints the default distro name.
    return len(r.stdout) > 0
  except Exception:
    return False


def detect_rlog_dir() -> str | None:
  """Best-effort guess for an existing rlog directory."""
  candidates = []
  if os.name == "nt":
    # Drive-letter heuristics common on the dev PCs.
    candidates += [
      "E:\\rlogs", "E:\\rlog",
      "D:\\rlogs", "D:\\rlog",
      "C:\\rlogs", "C:\\rlog",
    ]
  candidates += [
    str(Path.home() / "rlogs"),
    str(Path.home() / "rlog"),
  ]
  for c in candidates:
    p = Path(c)
    try:
      if p.exists() and p.is_dir() and any(p.iterdir()):
        return str(p)
    except (PermissionError, OSError):
      continue
  return None


def recommend_workers() -> int:
  """Half of logical CPUs, clamped to [2, 12]."""
  cpu = os.cpu_count() or 4
  return max(2, min(12, cpu // 2))


def _stable_file(path: Path, min_file_age_sec: float) -> bool:
  if min_file_age_sec <= 0.0:
    return True
  try:
    return time.time() - path.stat().st_mtime >= min_file_age_sec
  except OSError:
    return False


def _fast_log_sources(rlogs: str, min_file_age_sec: float, max_sources: int) -> tuple[list[str], int]:
  path = Path(rlogs).expanduser()
  if path.is_file():
    return ([str(path)] if _stable_file(path, min_file_age_sec) else []), 1
  if not path.is_dir():
    return [rlogs], 1

  sources = []
  seen = 0
  max_dirs = 800
  for dir_index, (root, dirs, files) in enumerate(os.walk(path)):
    if dir_index >= max_dirs or len(sources) >= max_sources:
      break
    dirs.sort(reverse=True)
    for name in sorted(files, reverse=True):
      if name in LOG_FILENAMES or name.endswith(LOG_SUFFIXES):
        seen += 1
        candidate = Path(root) / name
        if _stable_file(candidate, min_file_age_sec):
          sources.append(str(candidate))
          if len(sources) >= max_sources:
            break
  return sources, max(seen, len(sources))


def scan_rlog_metadata(rlogs: str, min_file_age_sec: float = 0.0,
                       max_sources: int = 4, max_messages_per_source: int = 20000) -> dict:
  from tools.cas.train import install_openpilot_aliases

  install_openpilot_aliases()
  try:
    from openpilot.tools.lib.logreader import LogReader
    from openpilot.selfdrive.carrot.cas.metadata import eps_firmware_hash
  except ModuleNotFoundError:
    from tools.lib.logreader import LogReader
    from selfdrive.carrot.cas.metadata import eps_firmware_hash

  selected, source_count = _fast_log_sources(rlogs, min_file_age_sec, max(1, max_sources))
  cars = Counter()
  eps_hashes = Counter()
  message_counts = Counter()
  errors = []
  first_t = None
  last_t = None
  scanned_count = 0

  for source in selected:
    scanned_count += 1
    try:
      for index, msg in enumerate(LogReader(source), 1):
        which = msg.which()
        message_counts[which] += 1
        t = msg.logMonoTime * 1e-9
        first_t = t if first_t is None else min(first_t, t)
        last_t = t if last_t is None else max(last_t, t)
        if which == "carParams":
          car = str(getattr(msg.carParams, "carFingerprint", "")).strip()
          if car:
            cars[car] += 1
          eps_hash = eps_firmware_hash(msg.carParams.carFw)
          if eps_hash:
            eps_hashes[eps_hash] += 1
          break
        if index >= max_messages_per_source:
          break
    except Exception as e:
      errors.append(f"{source}: {e}")
    if cars and eps_hashes:
      break

  return {
    "source_count": source_count,
    "scanned_count": scanned_count,
    "cars": cars,
    "eps_hashes": eps_hashes,
    "message_counts": message_counts,
    "duration_hours": 0.0 if first_t is None or last_t is None else max(0.0, last_t - first_t) / 3600.0,
    "errors": errors,
  }


def default_candidate_name(car: str) -> str:
  safe_car = car.strip() or "CAS_AUTO"
  return f"{safe_car}_candidate.json"


def default_validate_name(car: str) -> str:
  safe_car = car.strip() or "CAS_AUTO"
  return f"{safe_car}_validate.json"


# Mapping from python import name → pip package name (when they differ).
PIP_NAME = {
  "capnp": "pycapnp",
  "zmq": "pyzmq",
}


def _load_gui_config() -> dict:
  try:
    if CONFIG_PATH.exists():
      return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
  except Exception:
    pass
  return {}


class CASGui(tk.Tk):
  def __init__(self):
    super().__init__()
    self.title("CAS Training")
    self.geometry("900x640")
    self.minsize(760, 560)
    self.proc: subprocess.Popen | None = None
    self.queue: queue.Queue[str] = queue.Queue()
    self.current_run_dir: Path | None = None
    self.advanced_window: tk.Toplevel | None = None

    config = _load_gui_config()
    last_rlogs = config.get("rlogs", "")
    last_car = config.get("car", "")
    last_kind = config.get("kind", "torque")

    # Openpilot dir is auto-detected from this script's location. User can
    # still see it (and the config override survives moves of gui.py).
    self.repo_var = tk.StringVar(value=config.get("repo", str(REPO_ROOT)))
    self.rlogs_var = tk.StringVar(value=last_rlogs)
    self.car_var = tk.StringVar(value=last_car)
    self.car_aliases_var = tk.StringVar(value=config.get("car_aliases", ""))
    self.eps_hash_var = tk.StringVar(value=config.get("eps_firmware_hash", ""))
    self.kind_var = tk.StringVar(value=last_kind)
    self.epochs_var = tk.StringVar(value=str(config.get("epochs", 20)))
    self.stride_var = tk.StringVar(value=str(config.get("stride", 10)))
    self.age_var = tk.StringVar(value=str(config.get("min_file_age_sec", 120)))
    self.max_sources_var = tk.StringVar(value=str(config.get("max_sources", "")))
    self.workers_var = tk.StringVar(value=str(config.get("workers", min(4, max(1, os.cpu_count() or 1)))))
    self.alpha_var = tk.StringVar(value=str(config.get("alpha", 0.5)))
    self.backend_var = tk.StringVar(value=config.get("backend", "auto"))
    self.device_var = tk.StringVar(value=config.get("device", "auto"))
    self.use_wsl_var = tk.BooleanVar(value=bool(config.get("use_wsl", os.name == "nt")))
    self.candidate_var = tk.StringVar(value=config.get("candidate", self._derive_candidate_path(last_rlogs, last_car)))
    self.validate_var = tk.StringVar(value=config.get("validate_json", self._derive_validate_path(last_rlogs, last_car)))
    self.gpu_status_var = tk.StringVar(value="PyTorch/CUDA: checking...")
    self.raw_log_var = tk.StringVar(value="실행 로그: 아직 없음")
    self.log_info_var = tk.StringVar(value=self._log_info_text(last_car, "", 0, 0, 0.0))
    self.scan_running = False

    self._build()
    self.after(100, self._poll)
    self.after(300, self.detect_backend)
    # Save config on close.
    self.protocol("WM_DELETE_WINDOW", self._on_close)

  @staticmethod
  def _derive_candidate_path(rlogs: str, car: str) -> str:
    if not rlogs:
      return ""
    return str(Path(rlogs) / default_candidate_name(car))

  @staticmethod
  def _derive_validate_path(rlogs: str, car: str) -> str:
    if not rlogs:
      return ""
    return str(Path(rlogs) / default_validate_name(car))

  @staticmethod
  def _log_info_text(car: str, eps_hash: str, source_count: int, scanned_count: int, duration_hours: float) -> str:
    del duration_hours
    car_text = car.strip() if car.strip() else "감지 전"
    eps_text = eps_hash.strip() if eps_hash.strip() else "감지 전"
    if source_count > 0:
      return f"감지된 차량: {car_text} / EPS: {eps_text} / 로그: {source_count}개 중 {scanned_count}개 빠른 확인"
    return f"감지된 차량: {car_text} / EPS: {eps_text} / 학습 시작 후 자동으로 확정됩니다."

  def _save_config(self):
    try:
      CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
      data = {
        "repo": self.repo_var.get(),
        "rlogs": self.rlogs_var.get(),
        "car": self.car_var.get(),
        "candidate": self.candidate_var.get(),
        "validate_json": self.validate_var.get(),
        "car_aliases": self.car_aliases_var.get(),
        "eps_firmware_hash": self.eps_hash_var.get(),
        "kind": self.kind_var.get(),
        "epochs": self.epochs_var.get(),
        "stride": self.stride_var.get(),
        "min_file_age_sec": self.age_var.get(),
        "max_sources": self.max_sources_var.get(),
        "workers": self.workers_var.get(),
        "alpha": self.alpha_var.get(),
        "backend": self.backend_var.get(),
        "device": self.device_var.get(),
        "use_wsl": self.use_wsl_var.get(),
      }
      CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
      pass

  def _on_close(self):
    self._save_config()
    if self.advanced_window is not None and self.advanced_window.winfo_exists():
      self.advanced_window.destroy()
    self.destroy()

  def _require_paths(self) -> bool:
    """Validate that both Openpilot dir and RLOG dir are set and exist.
    Returns False (and shows a message) if not."""
    repo = self.repo_var.get().strip()
    rlogs = self.rlogs_var.get().strip()
    if not repo or not Path(repo).is_dir():
      messagebox.showerror("CAS", "Openpilot dir이 잘못되었습니다. 폴더를 선택하세요.")
      return False
    if not rlogs or not Path(rlogs).is_dir():
      messagebox.showerror("CAS", "RLOG dir이 비어있거나 존재하지 않습니다. 폴더를 선택하세요.")
      return False
    car = self.car_var.get().strip()
    self._refresh_derived_paths(rlogs, car)
    self._save_config()
    return True

  def _refresh_derived_paths(self, rlogs: str, car: str):
    expected_candidate = self._derive_candidate_path(rlogs, car)
    expected_validate = self._derive_validate_path(rlogs, car)

    candidate = self.candidate_var.get().strip()
    if not candidate:
      self.candidate_var.set(expected_candidate)
    else:
      candidate_path = Path(candidate)
      if (not candidate_path.exists()
          and str(candidate_path.parent) == str(Path(rlogs))
          and candidate_path.name.endswith("_candidate.json")):
        self.candidate_var.set(expected_candidate)

    validate = self.validate_var.get().strip()
    if not validate:
      self.validate_var.set(expected_validate)
    else:
      validate_path = Path(validate)
      if (not validate_path.exists()
          and str(validate_path.parent) == str(Path(rlogs))
          and validate_path.name.endswith("_validate.json")):
        self.validate_var.set(expected_validate)

  def _build(self):
    root = ttk.Frame(self, padding=12)
    root.pack(fill=tk.BOTH, expand=True)

    header = ttk.Frame(root)
    header.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(header, text="CAS Training", font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
    ttk.Label(header, text="RLOG 폴더만 고르면 됩니다. 차량 정보는 학습 시작 후 로그에서 자동으로 확정됩니다.").pack(anchor="w", pady=(2, 0))

    form = ttk.LabelFrame(root, text="일반 모드", padding=10)
    form.pack(fill=tk.X)
    form.columnconfigure(1, weight=1)

    self._row(form, 0, "RLOG 폴더", self.rlogs_var, browse=True)
    ttk.Label(form, text="로그 정보").grid(row=1, column=0, sticky="w", pady=3)
    ttk.Label(form, textvariable=self.log_info_var).grid(row=1, column=1, columnspan=2, sticky="w", padx=5)

    buttons = ttk.Frame(root)
    buttons.pack(fill=tk.X, pady=(12, 10))
    ttk.Button(buttons, text="학습 시작 + 검증", command=self.one_click).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(buttons, text="자동 설정", command=self.auto_tune).pack(side=tk.LEFT, padx=3)
    ttk.Button(buttons, text="로그 확인", command=self.scan_logs).pack(side=tk.LEFT, padx=3)
    ttk.Button(buttons, text="모델 적용", command=lambda: self.promote(False)).pack(side=tk.LEFT, padx=3)
    ttk.Button(buttons, text="고급 설정...", command=self._open_advanced).pack(side=tk.LEFT, padx=3)
    ttk.Button(buttons, text="중지", command=self.stop).pack(side=tk.RIGHT, padx=(6, 0))

    self.progress = ttk.Progressbar(root, mode="indeterminate")
    self.progress.pack(fill=tk.X)
    self.status_var = tk.StringVar(value="Idle")
    status = ttk.LabelFrame(root, text="상태", padding=(10, 6))
    status.pack(fill=tk.X, pady=(8, 8))
    ttk.Label(status, textvariable=self.status_var).pack(anchor="w", pady=(0, 2))
    ttk.Label(status, textvariable=self.gpu_status_var).pack(anchor="w", pady=(0, 2))
    ttk.Label(status, textvariable=self.raw_log_var).pack(anchor="w")

    ttk.Label(root, text="작업 로그").pack(anchor="w", pady=(2, 4))
    self.log = tk.Text(root, wrap=tk.WORD, height=28)
    self.log.pack(fill=tk.BOTH, expand=True)

  def _open_advanced(self):
    if self.advanced_window is not None and self.advanced_window.winfo_exists():
      self.advanced_window.lift()
      self.advanced_window.focus_force()
      return

    win = tk.Toplevel(self)
    self.advanced_window = win
    win.title("CAS 고급 설정")
    win.geometry("940x430")
    win.minsize(760, 380)
    win.transient(self)

    def close():
      self._save_config()
      self.advanced_window = None
      win.destroy()

    win.protocol("WM_DELETE_WINDOW", close)

    root = ttk.Frame(win, padding=12)
    root.pack(fill=tk.BOTH, expand=True)

    paths = ttk.LabelFrame(root, text="경로", padding=10)
    paths.pack(fill=tk.X, pady=(0, 8))
    paths.columnconfigure(1, weight=1)
    self._row(paths, 0, "Openpilot 폴더", self.repo_var, browse=True)
    self._row(paths, 1, "RLOG 폴더", self.rlogs_var, browse=True)
    self._row(paths, 2, "Candidate JSON", self.candidate_var, save=True)
    self._row(paths, 3, "Validate JSON", self.validate_var, save=True)

    model = ttk.LabelFrame(root, text="모델 식별", padding=10)
    model.pack(fill=tk.X, pady=(0, 8))
    model.columnconfigure(1, weight=1)
    self._combo(model, 0, "종류", self.kind_var, ("torque", "angle"))
    self._row(model, 1, "모델 차량 이름", self.car_var)
    self._row(model, 2, "차량 별칭", self.car_aliases_var)
    self._row(model, 3, "EPS 해시 강제 지정", self.eps_hash_var)

    opts = ttk.LabelFrame(root, text="학습 옵션", padding=10)
    opts.pack(fill=tk.X, pady=(0, 8))
    for i in range(9):
      opts.columnconfigure(i, weight=1)
    self._small(opts, 0, "Epochs", self.epochs_var)
    self._small(opts, 1, "Stride", self.stride_var)
    self._small(opts, 2, "Min age", self.age_var)
    self._small(opts, 3, "Max sources", self.max_sources_var)
    self._small(opts, 4, "Workers", self.workers_var)
    self._small(opts, 5, "Alpha", self.alpha_var)
    self._combo(opts, 6, "Backend", self.backend_var, ("auto", "numpy", "torch"), small=True)
    self._small(opts, 7, "Device", self.device_var)
    ttk.Checkbutton(opts, text="WSL", variable=self.use_wsl_var).grid(row=0, column=8, sticky="w", padx=4)

    manual = ttk.Frame(root)
    manual.pack(fill=tk.X)
    ttk.Button(manual, text="Train Candidate", command=self.train).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(manual, text="Validate", command=self.validate).pack(side=tk.LEFT, padx=3)
    ttk.Button(manual, text="Promote Dry Run", command=lambda: self.promote(True)).pack(side=tk.LEFT, padx=3)
    ttk.Button(manual, text="Promote", command=lambda: self.promote(False)).pack(side=tk.LEFT, padx=3)
    ttk.Button(manual, text="닫기", command=close).pack(side=tk.RIGHT)

  def _row(self, parent, row, label, var, browse=False, save=False):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
    ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=5)
    if browse:
      ttk.Button(parent, text="찾기", command=lambda: self._browse_dir(var)).grid(row=row, column=2)
    elif save:
      ttk.Button(parent, text="파일", command=lambda: self._browse_save(var)).grid(row=row, column=2)

  def _small(self, parent, col, label, var):
    frame = ttk.Frame(parent)
    frame.grid(row=0, column=col, sticky="ew", padx=4)
    ttk.Label(frame, text=label).pack(anchor="w")
    ttk.Entry(frame, textvariable=var, width=10).pack(fill=tk.X)

  def _combo(self, parent, row_or_col, label, var, values, small=False):
    if small:
      frame = ttk.Frame(parent)
      frame.grid(row=0, column=row_or_col, sticky="ew", padx=4)
      ttk.Label(frame, text=label).pack(anchor="w")
      ttk.Combobox(frame, textvariable=var, values=values, width=10, state="readonly").pack(fill=tk.X)
    else:
      ttk.Label(parent, text=label).grid(row=row_or_col, column=0, sticky="w", pady=3)
      ttk.Combobox(parent, textvariable=var, values=values, state="readonly").grid(row=row_or_col, column=1, sticky="w", padx=5)

  def _browse_dir(self, var):
    old = var.get().strip()
    path = filedialog.askdirectory(initialdir=var.get() or str(self._repo()))
    if path:
      var.set(path)
      if var is self.rlogs_var and path != old:
        self.car_var.set("")
        self.car_aliases_var.set("")
        self.eps_hash_var.set("")
        self._refresh_derived_paths(path, "")
        self.log_info_var.set(self._log_info_text("", "", 0, 0, 0.0))

  def _browse_save(self, var):
    path = filedialog.asksaveasfilename(initialfile=Path(var.get()).name)
    if path:
      var.set(path)

  def _scan_logs_sync(self, show_errors: bool = True) -> bool:
    rlogs = self.rlogs_var.get().strip()
    if not rlogs or not Path(rlogs).is_dir():
      if show_errors:
        messagebox.showerror("CAS 로그 확인", "먼저 RLOG 폴더를 선택하세요.")
      return False
    try:
      result = scan_rlog_metadata(rlogs, float(self.age_var.get() or 0.0))
    except Exception as e:
      if show_errors:
        messagebox.showerror("CAS 로그 확인", f"로그 정보를 읽지 못했습니다.\n\n{e}")
      self.log_info_var.set("로그 정보 확인 실패")
      return False
    self._apply_scan_result(result)
    return bool(self.car_var.get().strip())

  def scan_logs(self):
    if self.scan_running:
      return
    rlogs = self.rlogs_var.get().strip()
    if not rlogs or not Path(rlogs).is_dir():
      messagebox.showerror("CAS 로그 확인", "먼저 RLOG 폴더를 선택하세요.")
      return

    self.scan_running = True
    self.status_var.set("로그에서 차량 정보 확인 중")
    self.log_info_var.set("로그 정보 확인 중...")

    def worker():
      try:
        result = scan_rlog_metadata(rlogs, float(self.age_var.get() or 0.0))
      except Exception as e:
        self.after(0, lambda: self._scan_failed(e))
        return
      self.after(0, lambda: self._scan_done(result))

    threading.Thread(target=worker, daemon=True).start()

  def _scan_failed(self, error: Exception):
    self.scan_running = False
    self.status_var.set("로그 정보 확인 실패")
    self.log_info_var.set("로그 정보 확인 실패")
    messagebox.showerror("CAS 로그 확인", f"로그 정보를 읽지 못했습니다.\n\n{error}")

  def _scan_done(self, result: dict):
    self.scan_running = False
    self._apply_scan_result(result)
    self.status_var.set("로그 정보 확인 완료" if self.car_var.get().strip() else "차량 정보 없음")

  def _apply_scan_result(self, result: dict):
    cars: Counter = result.get("cars", Counter())
    eps_hashes: Counter = result.get("eps_hashes", Counter())
    car = cars.most_common(1)[0][0] if cars else ""
    eps_hash = eps_hashes.most_common(1)[0][0] if eps_hashes else ""

    if car:
      self.car_var.set(car)
      aliases = [alias.strip() for alias in self.car_aliases_var.get().replace(";", ",").split(",") if alias.strip()]
      if car not in aliases:
        aliases.insert(0, car)
        self.car_aliases_var.set(", ".join(aliases))
    if eps_hash:
      self.eps_hash_var.set(eps_hash)

    self.log_info_var.set(self._log_info_text(
      car,
      eps_hash,
      int(result.get("source_count", 0)),
      int(result.get("scanned_count", 0)),
      float(result.get("duration_hours", 0.0)),
    ))
    if car and self.rlogs_var.get().strip():
      self._refresh_derived_paths(self.rlogs_var.get().strip(), car)

  def _append(self, text: str):
    self.log.insert(tk.END, text)
    self.log.see(tk.END)

  def _poll(self):
    try:
      while True:
        msg = self.queue.get_nowait()
        self._append(msg)
    except queue.Empty:
      pass
    self.after(100, self._poll)

  def _run(self, cmd: list[str], use_wsl_capnp=False, summary_path: str | None = None):
    self._run_sequence([(cmd, use_wsl_capnp, "Command")], summary_path)

  def _run_sequence(self, commands: list[tuple[list[str], bool, str]], summary_path: str | None = None):
    if self.proc is not None:
      messagebox.showwarning("CAS", "이미 실행 중인 작업이 있습니다. 끝난 뒤 다시 눌러주세요.")
      return
    self.log.delete("1.0", tk.END)
    self.current_run_dir = self._make_run_dir()
    self.raw_log_var.set(f"실행 로그 폴더: {self.current_run_dir}")
    commands = self._inject_audit_args(commands)
    self._write_run_metadata(self.current_run_dir, commands)
    self.status_var.set("실행 중")
    self.progress.start(10)
    thread = threading.Thread(target=self._sequence_worker, args=(commands, summary_path), daemon=True)
    thread.start()

  def _sequence_worker(self, commands: list[tuple[list[str], bool, str]], summary_path: str | None):
    ok = True
    for cmd, use_wsl_capnp, label in commands:
      code = self._run_one(cmd, use_wsl_capnp, label)
      if code != 0:
        ok = False
        break
    if ok and summary_path:
      self._print_summary(summary_path)
      self._copy_summary(summary_path)
    self.after(0, self.status_var.set, "완료" if ok else "실패")
    self.after(0, self.progress.stop)
    # Triggered when _install_deps just ran — re-probe so GPU/CUDA status
    # refreshes without the user clicking Detect GPU again.
    self.after(0, self._maybe_redetect_after_install)

  def _repo(self) -> Path:
    return Path(self.repo_var.get().strip() or str(REPO_ROOT))

  def _run_one(self, cmd: list[str], use_wsl_capnp: bool, label: str) -> int:
    repo = self._repo()
    backup = repo / "cereal" / "car.capnp.casbak"
    car_capnp = repo / "cereal" / "car.capnp"
    real_car_capnp = repo / "opendbc_repo" / "opendbc" / "car" / "car.capnp"
    log_path = self._stage_log_path(label)
    try:
      if use_wsl_capnp:
        shutil.copyfile(car_capnp, backup)
        shutil.copyfile(real_car_capnp, car_capnp)
      header = f"\n[{label}]\n> " + " ".join(cmd) + "\n"
      self.queue.put(header)
      self._append_raw(log_path, header)
      self.proc = subprocess.Popen(cmd, cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
      assert self.proc.stdout is not None
      for line in self.proc.stdout:
        self.queue.put(line)
        self._append_raw(log_path, line)
      code = self.proc.wait()
      footer = f"exit code: {code}\n"
      self.queue.put(footer)
      self._append_raw(log_path, footer)
      return code
    except Exception as e:
      err = f"\nERROR: {e}\n"
      self.queue.put(err)
      self._append_raw(log_path, err)
      return 1
    finally:
      self.proc = None
      if backup.exists():
        shutil.move(str(backup), str(car_capnp))

  def _wsl_cmd(self, inner: str) -> list[str]:
    return ["wsl", "bash", "-lc", f"cd {quote(windows_to_wsl(str(self._repo())))} && {inner}"]

  def _inject_audit_args(self, commands: list[tuple[list[str], bool, str]]) -> list[tuple[list[str], bool, str]]:
    if self.current_run_dir is None:
      return commands
    injected = []
    for cmd, use_wsl_capnp, label in commands:
      audit_dir = None
      if "Train" in label:
        audit_dir = self.current_run_dir / "train_audit"
      elif "Validate" in label:
        audit_dir = self.current_run_dir / "validate_audit"

      if audit_dir is None:
        injected.append((cmd, use_wsl_capnp, label))
        continue

      if use_wsl_capnp:
        audit_args = f" --audit-dir {quote(windows_to_wsl(str(audit_dir)))} --audit-samples"
        cmd = [*cmd]
        cmd[3] = cmd[3] + audit_args
      else:
        cmd = [*cmd, "--audit-dir", str(audit_dir), "--audit-samples"]
      injected.append((cmd, use_wsl_capnp, label))
    return injected

  def _make_run_dir(self) -> Path:
    car = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in self.car_var.get().strip()) or "setup"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path(self.rlogs_var.get().strip()) if self.rlogs_var.get().strip() else CONFIG_PATH.parent
    run_dir = base / "cas_runs" / f"{stamp}_{car}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

  def _stage_log_path(self, label: str) -> Path | None:
    if self.current_run_dir is None:
      return None
    safe = "".join(c.lower() if c.isalnum() else "_" for c in label).strip("_")
    return self.current_run_dir / f"{safe}.log"

  def _append_raw(self, path: Path | None, text: str):
    if path is None:
      return
    with open(path, "a", encoding="utf-8") as f:
      f.write(text)

  def _write_run_metadata(self, run_dir: Path, commands: list[tuple[list[str], bool, str]]):
    data = {
      "started_at": datetime.now().isoformat(timespec="seconds"),
      "repo": str(self._repo()),
      "rlogs": self.rlogs_var.get(),
      "car": self.car_var.get().strip(),
      "car_aliases": self.car_aliases_var.get().strip(),
      "eps_firmware_hash": self.eps_hash_var.get().strip(),
      "kind": self.kind_var.get(),
      "candidate": self.candidate_var.get(),
      "validate_json": self.validate_var.get(),
      "epochs": self.epochs_var.get(),
      "sample_stride": self.stride_var.get(),
      "min_file_age_sec": self.age_var.get(),
      "max_sources": self.max_sources_var.get().strip(),
      "workers": self.workers_var.get(),
      "alpha_max": self.alpha_var.get(),
      "backend": self.backend_var.get(),
      "device": self.device_var.get(),
      "use_wsl": self.use_wsl_var.get(),
      "gpu_status": self.gpu_status_var.get(),
      "commands": [{"label": label, "use_wsl_capnp": use_wsl_capnp, "cmd": cmd}
                   for cmd, use_wsl_capnp, label in commands],
    }
    with open(run_dir / "run_metadata.json", "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=2)

  def _copy_summary(self, summary_path: str):
    if self.current_run_dir is None:
      return
    src = Path(summary_path)
    if src.exists():
      shutil.copyfile(src, self.current_run_dir / "validate_summary.json")

  def _limit_args(self):
    args = []
    if self.max_sources_var.get().strip():
      args += ["--max-sources", self.max_sources_var.get().strip()]
    return args

  def _car_metadata_args(self):
    args = []
    aliases = [alias.strip() for alias in self.car_aliases_var.get().replace(";", ",").split(",")]
    for alias in aliases:
      if alias:
        args += ["--car-name", alias]
    eps_hash = self.eps_hash_var.get().strip()
    if eps_hash:
      args += ["--eps-firmware-hash", eps_hash]
    return args

  def _train_cmd(self):
    cmd = [
      "python3", "tools/cas/train.py",
      "--rlogs", windows_to_wsl(self.rlogs_var.get()) if self.use_wsl_var.get() else self.rlogs_var.get(),
      "--kind", self.kind_var.get(),
      "--output", windows_to_wsl(self.candidate_var.get()) if self.use_wsl_var.get() else self.candidate_var.get(),
      "--epochs", self.epochs_var.get(),
      "--sample-stride", self.stride_var.get(),
      "--min-file-age-sec", self.age_var.get(),
      "--alpha-max", self.alpha_var.get(),
      "--backend", self.backend_var.get(),
      "--device", self.device_var.get(),
      "--workers", self.workers_var.get(),
      *self._car_metadata_args(),
      *self._limit_args(),
    ]
    if self.car_var.get().strip():
      cmd[4:4] = ["--car", self.car_var.get().strip()]
    return cmd

  def _validate_cmd(self):
    return [
      "python3", "tools/cas/validate.py",
      "--model", windows_to_wsl(self.candidate_var.get()) if self.use_wsl_var.get() else self.candidate_var.get(),
      "--rlogs", windows_to_wsl(self.rlogs_var.get()) if self.use_wsl_var.get() else self.rlogs_var.get(),
      "--sample-stride", self.stride_var.get(),
      "--min-file-age-sec", self.age_var.get(),
      "--workers", self.workers_var.get(),
      "--output", windows_to_wsl(self.validate_var.get()) if self.use_wsl_var.get() else self.validate_var.get(),
      *self._limit_args(),
    ]

  def _promote_cmd(self, dry_run: bool):
    cmd = [
      sys.executable, str(self._repo() / "tools" / "cas" / "promote.py"),
      "--candidate", self.candidate_var.get(),
      "--kind", self.kind_var.get(),
      "--max-alpha", self.alpha_var.get(),
    ]
    if self.car_var.get().strip():
      cmd[4:4] = ["--car", self.car_var.get().strip()]
    cmd.append("--dry-run" if dry_run else "--force")
    return cmd

  def train(self):
    if not self._require_paths():
      return
    cmd = self._train_cmd()
    if self.use_wsl_var.get():
      self._run(self._wsl_cmd(" ".join(quote(x) for x in cmd)), use_wsl_capnp=True)
    else:
      self._run([sys.executable, *cmd[1:]], use_wsl_capnp=False)

  def validate(self):
    if not self._require_paths():
      return
    cmd = self._validate_cmd()
    if self.use_wsl_var.get():
      self._run(self._wsl_cmd(" ".join(quote(x) for x in cmd)), use_wsl_capnp=True, summary_path=self.validate_var.get())
    else:
      self._run([sys.executable, *cmd[1:]], use_wsl_capnp=False, summary_path=self.validate_var.get())

  def promote(self, dry_run: bool):
    if not self._require_paths():
      return
    if not dry_run:
      candidate = Path(self.candidate_var.get())
      if not candidate.exists():
        messagebox.showerror("CAS 모델 적용", "적용할 candidate JSON이 없습니다. 먼저 학습 + 검증을 실행하세요.")
        return
      if not Path(self.validate_var.get()).exists():
        messagebox.showerror("CAS 모델 적용", "검증 결과 JSON이 없습니다. 먼저 [학습 시작 + 검증]을 실행하세요.")
        return
      ok = messagebox.askyesno(
        "CAS 모델 적용",
        "검증된 candidate 모델을 실제 weights 폴더에 적용할까요?\n\n"
        "차량에서 바로 사용될 파일이 바뀝니다. 학습 결과가 부족하다고 표시되면 적용하지 않는 것이 좋습니다.",
      )
      if not ok:
        return
    cmd = self._promote_cmd(dry_run)
    self._run(cmd)

  def one_click(self):
    if not self._require_paths():
      return
    train_cmd = self._train_cmd()
    validate_cmd = self._validate_cmd()
    commands: list[tuple[list[str], bool, str]] = []
    if self.use_wsl_var.get():
      commands.append((self._wsl_cmd(" ".join(quote(x) for x in train_cmd)), True, "1/3 Train Candidate"))
      commands.append((self._wsl_cmd(" ".join(quote(x) for x in validate_cmd)), True, "2/3 Validate"))
    else:
      commands.append(([sys.executable, *train_cmd[1:]], False, "1/3 Train Candidate"))
      commands.append(([sys.executable, *validate_cmd[1:]], False, "2/3 Validate"))
    commands.append((self._promote_cmd(True), False, "3/3 Promote Dry Run"))
    self._run_sequence(commands, self.validate_var.get())

  def auto_tune(self):
    """Detect CPU / disk / GPU / WSL and apply best-effort defaults."""
    if self.proc is not None:
      return

    summary_parts = []

    # CPU + workers
    cpu = os.cpu_count() or 4
    workers = recommend_workers()
    self.workers_var.set(str(workers))
    summary_parts.append(f"workers={workers} (CPU={cpu})")

    # WSL
    wsl_ok = detect_wsl()
    self.use_wsl_var.set(wsl_ok)
    summary_parts.append(f"WSL={'on' if wsl_ok else 'off'}")

    # rlog dir — only override if current path looks unusable.
    current = self.rlogs_var.get().strip()
    cur_ok = bool(current) and Path(current).exists() and Path(current).is_dir() \
             and any(Path(current).iterdir()) and Path(current).resolve() != REPO_ROOT
    if not cur_ok:
      guess = detect_rlog_dir()
      if guess:
        self.rlogs_var.set(guess)
        summary_parts.append(f"rlogs={guess}")
      else:
        summary_parts.append("rlogs=(not found, set manually)")
    else:
      summary_parts.append(f"rlogs={current}")

    self.gpu_status_var.set("Auto Tune: " + ", ".join(summary_parts) + " — probing GPU…")
    # Fire GPU/dependency detection (it will update gpu_status_var itself).
    self.detect_backend()

  def detect_backend(self):
    if self.proc is not None:
      return
    if self.use_wsl_var.get():
      cmd = self._wsl_cmd(
        "python3 - <<'PY'\n"
        "try:\n"
        "  import torch\n"
        "  print('torch=' + torch.__version__)\n"
        "  print('cuda=' + str(torch.cuda.is_available()))\n"
        "  print('device=' + (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'))\n"
        "except Exception as e:\n"
        "  print('torch=missing')\n"
        "  print('cuda=False')\n"
        "  print('device=cpu')\n"
        "PY"
      )
    else:
      code = (
        "import importlib\n"
        "missing = []\n"
        "for mod in ('numpy', 'capnp', 'zmq', 'tqdm', 'zstandard'):\n"
        " try: importlib.import_module(mod)\n"
        " except ImportError: missing.append(mod)\n"
        "print('missing=' + ','.join(missing))\n"
        "try:\n"
        " import torch\n"
        " print('torch=' + torch.__version__)\n"
        " print('cuda=' + str(torch.cuda.is_available()))\n"
        " print('device=' + (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'))\n"
        "except Exception:\n"
        " print('torch=missing')\n"
        " print('cuda=False')\n"
        " print('device=cpu')\n"
      )
      cmd = [sys.executable, "-c", code]

    def worker():
      try:
        out = subprocess.check_output(cmd, cwd=str(self._repo()), text=True, stderr=subprocess.STDOUT, timeout=20)
      except Exception as e:
        self.after(0, self.gpu_status_var.set, f"PyTorch/CUDA: detect failed ({e})")
        return
      lines = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
      torch_ver = lines.get("torch", "missing")
      cuda = lines.get("cuda", "False")
      device = lines.get("device", "cpu")
      missing = [m for m in lines.get("missing", "").split(",") if m]

      # Pick backend / device based on what's actually available.
      if torch_ver == "missing":
        self.after(0, self.backend_var.set, "numpy")
        self.after(0, self.device_var.set, "cpu")
      elif cuda == "True":
        self.after(0, self.backend_var.set, "torch")
        self.after(0, self.device_var.set, "cuda")
      else:
        self.after(0, self.backend_var.set, "torch")
        self.after(0, self.device_var.set, "cpu")

      status = f"PyTorch/CUDA: torch {torch_ver}, cuda {cuda}, {device}"
      torch_missing = torch_ver == "missing"
      if torch_missing or missing:
        need = list(missing)
        if torch_missing:
          need.append("torch")
        status = f"PyTorch/CUDA: missing {','.join(need)} — installing automatically…"
        self.after(0, self.gpu_status_var.set, status)
        # Schedule the actual install on the main thread; it uses _run_sequence
        # which streams output to the log area.
        self.after(0, lambda m=list(missing), t=torch_missing: self._install_deps(m, t))
        return
      self.after(0, self.gpu_status_var.set, status)
    threading.Thread(target=worker, daemon=True).start()

  def _install_deps(self, missing: list[str], torch_missing: bool):
    """Auto-install missing deps via pip. Runs through _run_sequence so output
    streams to the log area. After install completes, re-runs detect_backend.

    Skipped silently if a command is already in progress (e.g. training)."""
    if self.proc is not None:
      self.gpu_status_var.set(
        "PyTorch/CUDA: deps missing — auto-install skipped (a command is running)."
      )
      return

    cmds: list[tuple[list[str], bool, str]] = []
    base_pip = [PIP_NAME.get(m, m) for m in missing if m != "torch"]
    py = sys.executable
    if base_pip:
      cmds.append(([py, "-m", "pip", "install", *base_pip], False, "Install base deps"))
    if torch_missing:
      # CUDA wheel via official PyTorch index. Drops to CPU wheel only if
      # the user explicitly edited requirements; cu128 works on most modern GPUs.
      cmds.append((
        [py, "-m", "pip", "install", "--index-url", "https://download.pytorch.org/whl/cu128", "torch"],
        False, "Install CUDA torch",
      ))
    if not cmds:
      return

    self.gpu_status_var.set("Installing missing deps… (see log)")
    # Hook: after the sequence finishes, re-detect.
    self._post_install_redetect = True
    self._run_sequence(cmds)

  def _maybe_redetect_after_install(self):
    if getattr(self, "_post_install_redetect", False):
      self._post_install_redetect = False
      # Small delay so file locks settle.
      self.after(500, self.detect_backend)

  def _print_summary(self, summary_path: str):
    path = Path(summary_path)
    if not path.exists():
      self.queue.put("\n[요약]\nvalidation JSON을 찾을 수 없습니다.\n")
      return
    try:
      with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
      out = data["output_metrics"]
      applied = out["applied_delta"]
      detected_car = str(data.get("car", "")).strip()
      eps_counts = data.get("eps_firmware_hash_counts", {}) or {}
      detected_eps = max(eps_counts.items(), key=lambda item: int(item[1]))[0] if eps_counts else ""
      if detected_car:
        self.after(0, self.car_var.set, detected_car)
      if detected_eps:
        self.after(0, self.eps_hash_var.set, detected_eps)
      if detected_car or detected_eps:
        self.after(0, self.log_info_var.set,
                   self._log_info_text(detected_car, detected_eps, int(data.get("source_count", 0)),
                                       int(data.get("source_count", 0)), float(data.get("duration_hours", 0.0))))

      hours = float(data.get("duration_hours", 0.0))
      samples = int(data.get("usable_samples", 0))
      triage = data.get("target_triage_counts", {}) or {}
      t1 = int(triage.get("T1_GOOD", 0))
      t2 = int(triage.get("T2_OFFSET", 0))
      t3 = int(triage.get("T3_STRONG_INTERVENTION", 0))
      t4 = int(triage.get("T4_WEAK_INTERVENTION", 0))
      rmse = float(data.get("target_metrics", {}).get("rmse", 0.0))
      p95 = float(applied.get("p95_abs", 0.0))
      gate_rate = float(out.get("gate_pass_rate", 0.0))
      total_triage = max(t1 + t2 + t3 + t4, 1)
      pct = lambda n: 100.0 * n / total_triage

      issues = []
      good_points = []
      if hours < 1.0:
        issues.append(f"학습 시간이 너무 짧음 ({hours:.2f}h, 권장 ≥ 10h)")
      elif hours < 10.0:
        issues.append(f"학습 시간이 다소 짧음 ({hours:.2f}h, 권장 ≥ 10h, 그래도 첫 적용은 가능)")
      else:
        good_points.append(f"학습 시간 충분 ({hours:.2f}h)")

      if samples < 50000:
        issues.append(f"사용 가능한 샘플이 적음 ({samples:,}개)")
      else:
        good_points.append(f"샘플 수 {samples:,}개")

      if t3 + t4 < 1000:
        issues.append("운전자 개입 신호(T3/T4) 부족 — 일반화 약함")
      else:
        good_points.append(f"운전자 개입 신호 충분 (T3={t3:,}, T4={t4:,})")

      if gate_rate < 0.2:
        issues.append(f"게이트 통과율 낮음 ({gate_rate:.1%}) — 학습 분포 너무 좁음")
      else:
        good_points.append(f"게이트 통과율 {gate_rate:.1%}")

      if p95 < 0.01:
        issues.append(f"적용 보정량 매우 작음 (p95={p95:.4f}) — 체감 거의 없을 수 있음")
      elif p95 > 0.5:
        issues.append(f"적용 보정량 큼 (p95={p95:.4f}) — 진동/과보정 주의")
      else:
        good_points.append(f"적용 보정량 {p95:.4f} (정상 범위)")

      grade = "학습 양호" if not issues else ("학습 완료 (주의 필요)" if len(issues) <= 2 else "데이터/설정 부족")

      self.queue.put("\n[요약]\n")
      self.queue.put(f"평가: {grade}\n")
      self.queue.put(f"학습 시간: {hours:.2f} 시간\n")
      self.queue.put(f"사용 샘플: {samples:,}개\n")
      self.queue.put(f"트리아지 분포:\n")
      self.queue.put(f"  T1 양호 운전:        {t1:>8,} ({pct(t1):5.1f}%)\n")
      self.queue.put(f"  T2 쏠림 구간:        {t2:>8,} ({pct(t2):5.1f}%)\n")
      self.queue.put(f"  T3 운전자 강 개입:   {t3:>8,} ({pct(t3):5.1f}%)  ★ 가장 강한 학습 신호\n")
      if t4:
        self.queue.put(f"  T4 운전자 약 개입:   {t4:>8,} ({pct(t4):5.1f}%)\n")
      self.queue.put(f"학습 정확도(RMSE):    {rmse:.4f}\n")
      self.queue.put(f"실제 적용 보정량 p95: {p95:.4f}\n")
      self.queue.put(f"게이트 통과율:        {gate_rate:.1%}\n")
      if good_points:
        self.queue.put("\n잘된 점:\n")
        for g in good_points:
          self.queue.put(f"  ✓ {g}\n")
      if issues:
        self.queue.put("\n확인 필요:\n")
        for i in issues:
          self.queue.put(f"  ! {i}\n")
      self.queue.put("\n아직 실제 적용은 하지 않았습니다. 결과가 괜찮으면 [모델 적용]을 누르세요.\n")

      summary_for_popup = (
        f"평가: {grade}\n\n"
        f"학습 결과\n"
        f"- 학습 시간: {hours:.2f}시간\n"
        f"- 사용 샘플: {samples:,}개\n"
        f"- 양호 운전(T1): {pct(t1):.0f}%\n"
        f"- 쏠림 학습(T2): {pct(t2):.0f}%\n"
        f"- 운전자 개입(T3): {pct(t3):.0f}%\n"
        f"- 적용 보정량: {p95:.4f} (p95)\n"
        f"- 게이트 통과: {gate_rate:.0%}\n"
      )
      if issues:
        summary_for_popup += "\n확인 필요\n"
        for i in issues:
          summary_for_popup += f"- {i}\n"
      summary_for_popup += (
        "\n다음 단계\n"
        "1. 결과가 괜찮으면 [모델 적용]을 누르세요.\n"
        "2. 차량에서는 저속, 한산한 도로부터 테스트하세요.\n"
        "3. 진동이나 이상감이 있으면 CAS 토글을 끄세요.\n"
        "4. 결과가 부족하면 rlog를 더 모은 뒤 다시 학습하세요."
      )
      self.after(0, lambda s=summary_for_popup, g=grade: self._show_summary_popup(s, g))

    except Exception as e:
      self.queue.put(f"\n[요약]\n요약 파일 읽기 실패: {e}\n")

  def _show_summary_popup(self, message: str, grade: str):
    if "부족" in grade:
      messagebox.showerror("CAS 학습 결과", message)
    elif "주의" in grade:
      messagebox.showwarning("CAS 학습 결과", message)
    else:
      messagebox.showinfo("CAS 학습 결과", message)

  def stop(self):
    if self.proc is not None:
      self.proc.terminate()
      self.status_var.set("중지 중")


if __name__ == "__main__":
  CASGui().mainloop()
