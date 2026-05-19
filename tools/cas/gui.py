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
from datetime import datetime
from tkinter import filedialog, messagebox, ttk


REPO_ROOT = Path(__file__).resolve().parents[2]


def windows_to_wsl(path: str) -> str:
  path = str(Path(path))
  if len(path) >= 2 and path[1] == ":":
    drive = path[0].lower()
    rest = path[2:].replace("\\", "/").lstrip("/")
    return f"/mnt/{drive}/{rest}"
  return path.replace("\\", "/")


def quote(value: str) -> str:
  return shlex.quote(value)


class CASGui(tk.Tk):
  def __init__(self):
    super().__init__()
    self.title("CAS Training")
    self.geometry("980x700")
    self.proc: subprocess.Popen | None = None
    self.queue: queue.Queue[str] = queue.Queue()
    self.current_run_dir: Path | None = None

    default_rlogs = "E:\\rlogs" if os.name == "nt" and Path("E:\\rlogs").exists() else str(REPO_ROOT)
    self.rlogs_var = tk.StringVar(value=default_rlogs)
    self.car_var = tk.StringVar(value="HYUNDAI_CASPER_EV")
    self.kind_var = tk.StringVar(value="torque")
    self.epochs_var = tk.StringVar(value="20")
    self.stride_var = tk.StringVar(value="10")
    self.age_var = tk.StringVar(value="120")
    self.max_sources_var = tk.StringVar(value="")
    self.workers_var = tk.StringVar(value=str(min(4, max(1, os.cpu_count() or 1))))
    self.alpha_var = tk.StringVar(value="0.1")
    self.backend_var = tk.StringVar(value="auto")
    self.device_var = tk.StringVar(value="auto")
    self.use_wsl_var = tk.BooleanVar(value=os.name == "nt")
    self.advanced_visible_var = tk.BooleanVar(value=False)
    self.candidate_var = tk.StringVar(value=str(Path(default_rlogs) / "HYUNDAI_CASPER_EV_candidate.json"))
    self.validate_var = tk.StringVar(value=str(Path(default_rlogs) / "HYUNDAI_CASPER_EV_validate.json"))
    self.gpu_status_var = tk.StringVar(value="PyTorch/CUDA: checking...")
    self.raw_log_var = tk.StringVar(value="Raw log: not started")

    self._build()
    self.after(100, self._poll)
    self.after(300, self.detect_backend)

  def _build(self):
    root = ttk.Frame(self, padding=10)
    root.pack(fill=tk.BOTH, expand=True)

    form = ttk.Frame(root)
    form.pack(fill=tk.X)
    form.columnconfigure(1, weight=1)

    self._row(form, 0, "RLOG dir", self.rlogs_var, browse=True)
    self._row(form, 1, "Car", self.car_var)

    buttons = ttk.Frame(root)
    buttons.pack(fill=tk.X, pady=(10, 8))
    ttk.Button(buttons, text="One Click: Train + Validate", command=self.one_click).pack(side=tk.LEFT, padx=3)
    ttk.Button(buttons, text="Detect GPU", command=self.detect_backend).pack(side=tk.LEFT, padx=3)
    ttk.Checkbutton(buttons, text="Advanced", variable=self.advanced_visible_var,
                    command=self._toggle_advanced).pack(side=tk.LEFT, padx=8)
    ttk.Button(buttons, text="Stop", command=self.stop).pack(side=tk.RIGHT, padx=3)

    self.progress = ttk.Progressbar(root, mode="indeterminate")
    self.progress.pack(fill=tk.X)
    self.status_var = tk.StringVar(value="Idle")
    ttk.Label(root, textvariable=self.status_var).pack(anchor="w", pady=(4, 2))
    ttk.Label(root, textvariable=self.gpu_status_var).pack(anchor="w", pady=(0, 4))
    ttk.Label(root, textvariable=self.raw_log_var).pack(anchor="w", pady=(0, 4))

    self.advanced = ttk.LabelFrame(root, text="Advanced", padding=8)
    self.advanced.columnconfigure(1, weight=1)
    self._combo(self.advanced, 0, "Kind", self.kind_var, ("torque", "angle"))
    self._row(self.advanced, 1, "Candidate", self.candidate_var, save=True)
    self._row(self.advanced, 2, "Validate JSON", self.validate_var, save=True)

    opts = ttk.Frame(self.advanced)
    opts.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 6))
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

    manual = ttk.Frame(self.advanced)
    manual.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 0))
    ttk.Button(manual, text="Train Candidate", command=self.train).pack(side=tk.LEFT, padx=3)
    ttk.Button(manual, text="Validate", command=self.validate).pack(side=tk.LEFT, padx=3)
    ttk.Button(manual, text="Promote Dry Run", command=lambda: self.promote(True)).pack(side=tk.LEFT, padx=3)
    ttk.Button(manual, text="Promote", command=lambda: self.promote(False)).pack(side=tk.LEFT, padx=3)

    self.log = tk.Text(root, wrap=tk.WORD, height=28)
    self.log.pack(fill=tk.BOTH, expand=True)

  def _toggle_advanced(self):
    if self.advanced_visible_var.get():
      self.advanced.pack(fill=tk.X, pady=(0, 8), before=self.log)
    else:
      self.advanced.pack_forget()

  def _row(self, parent, row, label, var, browse=False, save=False):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
    ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=5)
    if browse:
      ttk.Button(parent, text="Browse", command=lambda: self._browse_dir(var)).grid(row=row, column=2)
    elif save:
      ttk.Button(parent, text="File", command=lambda: self._browse_save(var)).grid(row=row, column=2)

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
    path = filedialog.askdirectory(initialdir=var.get() or str(REPO_ROOT))
    if path:
      var.set(path)

  def _browse_save(self, var):
    path = filedialog.asksaveasfilename(initialfile=Path(var.get()).name)
    if path:
      var.set(path)

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
      messagebox.showwarning("CAS", "A command is already running.")
      return
    self.log.delete("1.0", tk.END)
    self.current_run_dir = self._make_run_dir()
    self.raw_log_var.set(f"Raw log: {self.current_run_dir}")
    commands = self._inject_audit_args(commands)
    self._write_run_metadata(self.current_run_dir, commands)
    self.status_var.set("Running")
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
    self.after(0, self.status_var.set, "Done" if ok else "Failed")
    self.after(0, self.progress.stop)

  def _run_one(self, cmd: list[str], use_wsl_capnp: bool, label: str) -> int:
    backup = REPO_ROOT / "cereal" / "car.capnp.casbak"
    car_capnp = REPO_ROOT / "cereal" / "car.capnp"
    real_car_capnp = REPO_ROOT / "opendbc_repo" / "opendbc" / "car" / "car.capnp"
    log_path = self._stage_log_path(label)
    try:
      if use_wsl_capnp:
        shutil.copyfile(car_capnp, backup)
        shutil.copyfile(real_car_capnp, car_capnp)
      header = f"\n[{label}]\n> " + " ".join(cmd) + "\n"
      self.queue.put(header)
      self._append_raw(log_path, header)
      self.proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
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
    return ["wsl", "bash", "-lc", f"cd {quote(windows_to_wsl(str(REPO_ROOT)))} && {inner}"]

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
    car = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in self.car_var.get().strip())
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(self.rlogs_var.get()) / "cas_runs" / f"{stamp}_{car}"
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
      "repo": str(REPO_ROOT),
      "rlogs": self.rlogs_var.get(),
      "car": self.car_var.get().strip(),
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

  def _train_cmd(self):
    return [
      "python3", "tools/cas/train.py",
      "--rlogs", windows_to_wsl(self.rlogs_var.get()) if self.use_wsl_var.get() else self.rlogs_var.get(),
      "--car", self.car_var.get().strip(),
      "--kind", self.kind_var.get(),
      "--output", windows_to_wsl(self.candidate_var.get()) if self.use_wsl_var.get() else self.candidate_var.get(),
      "--epochs", self.epochs_var.get(),
      "--sample-stride", self.stride_var.get(),
      "--min-file-age-sec", self.age_var.get(),
      "--alpha-max", self.alpha_var.get(),
      "--backend", self.backend_var.get(),
      "--device", self.device_var.get(),
      "--workers", self.workers_var.get(),
      *self._limit_args(),
    ]

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
      sys.executable, str(REPO_ROOT / "tools" / "cas" / "promote.py"),
      "--candidate", self.candidate_var.get(),
      "--car", self.car_var.get().strip(),
      "--kind", self.kind_var.get(),
      "--max-alpha", self.alpha_var.get(),
    ]
    cmd.append("--dry-run" if dry_run else "--force")
    return cmd

  def train(self):
    cmd = self._train_cmd()
    if self.use_wsl_var.get():
      self._run(self._wsl_cmd(" ".join(quote(x) for x in cmd)), use_wsl_capnp=True)
    else:
      self._run([sys.executable, *cmd[1:]], use_wsl_capnp=False)

  def validate(self):
    cmd = self._validate_cmd()
    if self.use_wsl_var.get():
      self._run(self._wsl_cmd(" ".join(quote(x) for x in cmd)), use_wsl_capnp=True, summary_path=self.validate_var.get())
    else:
      self._run([sys.executable, *cmd[1:]], use_wsl_capnp=False, summary_path=self.validate_var.get())

  def promote(self, dry_run: bool):
    cmd = self._promote_cmd(dry_run)
    self._run(cmd)

  def one_click(self):
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
        out = subprocess.check_output(cmd, cwd=REPO_ROOT, text=True, stderr=subprocess.STDOUT, timeout=20)
      except Exception as e:
        self.after(0, self.gpu_status_var.set, f"PyTorch/CUDA: detect failed ({e})")
        return
      lines = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
      torch_ver = lines.get("torch", "missing")
      cuda = lines.get("cuda", "False")
      device = lines.get("device", "cpu")
      if cuda == "True":
        self.after(0, self.backend_var.set, "torch")
        self.after(0, self.device_var.set, "cuda")
      else:
        self.after(0, self.backend_var.set, "auto")
        self.after(0, self.device_var.set, "auto")
      self.after(0, self.gpu_status_var.set, f"PyTorch/CUDA: torch {torch_ver}, cuda {cuda}, {device}")
    threading.Thread(target=worker, daemon=True).start()

  def _print_summary(self, summary_path: str):
    path = Path(summary_path)
    if not path.exists():
      self.queue.put("\n[Summary]\nvalidation JSON not found\n")
      return
    try:
      with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
      out = data["output_metrics"]
      applied = out["applied_delta"]
      self.queue.put("\n[Summary]\n")
      self.queue.put(f"hours: {data.get('duration_hours', 0.0):.2f}\n")
      self.queue.put(f"usable samples: {data.get('usable_samples', 0)}\n")
      self.queue.put(f"triage: {data.get('target_triage_counts', {})}\n")
      self.queue.put(f"target RMSE: {data.get('target_metrics', {}).get('rmse', 0.0):.4f}\n")
      self.queue.put(f"applied_delta p95_abs: {applied.get('p95_abs', 0.0):.4f}\n")
      self.queue.put(f"gate pass rate: {out.get('gate_pass_rate', 0.0):.3f}\n")
      self.queue.put("Promote was dry-run only. Real Promote is separate.\n")
    except Exception as e:
      self.queue.put(f"\n[Summary]\nfailed to read summary: {e}\n")

  def stop(self):
    if self.proc is not None:
      self.proc.terminate()
      self.status_var.set("Stopping")


if __name__ == "__main__":
  CASGui().mainloop()
