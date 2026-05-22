#!/usr/bin/env python3
"""
CAS Learner — Flet (Material 3) GUI.

Simple-mode alternative to tools/cas/gui.py. Same end-to-end flow:
  서버 데이터 확인 → 학습(Train) → 검증(Validate) → 차량 적용(Apply/Promote).

Configuration persists to ~/.cas_train/gui_flet_config.json (separate from
gui.py's gui_config.json so the two GUIs don't fight each other).

Removable as a unit: this file + ~/.cas_train/gui_flet_config.json are the
only artifacts. tools/cas/gui.py (Tkinter) and the training pipeline are
unaffected by anything here.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

try:
  import flet as ft
except ModuleNotFoundError:
  print("Flet is not installed. Run: python -m pip install flet", file=sys.stderr)
  raise

from tools.cas import cloud_sync


CONFIG_PATH    = Path.home() / ".cas_train" / "gui_flet_config.json"
LOG_MAX_LINES  = 800
MIN_APPLY_HOURS = 10.0

DEFAULT_CONFIG: dict[str, Any] = {
  "rlogs":              "",                                  # auto-detect on first run
  "endpoint":           cloud_sync.DEFAULT_SERVER_ENDPOINT,
  "token":              "",
  "alpha_max":          0.5,
  "backend":            "auto",
  "device":             "auto",
  "workers":            4,
  "epochs":             20,
  "sample_stride":      10,
  "use_wsl":            False,                               # True on Windows if WSL available
  "auto_download":      True,                                # download missing rlogs before training
  "cleanup_after_train": False,                              # delete consumed rlogs after success
}


# ── Environment helpers ────────────────────────────────────────────────────

def windows_to_wsl(path: str) -> str:
  """Convert C:\\foo\\bar → /mnt/c/foo/bar for WSL invocation."""
  path = str(Path(path))
  if len(path) >= 2 and path[1] == ":":
    drive = path[0].lower()
    rest = path[2:].replace("\\", "/").lstrip("/")
    return f"/mnt/{drive}/{rest}"
  return path.replace("\\", "/")


def detect_wsl() -> bool:
  if os.name != "nt":
    return False
  try:
    r = subprocess.run(["wsl", "--status"], capture_output=True, timeout=5)
    return r.returncode == 0 and len(r.stdout) > 0
  except Exception:
    return False


def detect_rlog_dir() -> str:
  candidates: list[str] = []
  if os.name == "nt":
    candidates += ["E:\\rlogs", "E:\\rlog", "D:\\rlogs", "D:\\rlog",
                   "C:\\rlogs", "C:\\rlog"]
  candidates += [str(Path.home() / "rlogs"), str(Path.home() / "rlog")]
  for c in candidates:
    if Path(c).is_dir():
      return c
  return candidates[-1]


def load_config() -> dict[str, Any]:
  try:
    if CONFIG_PATH.exists():
      return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
  except Exception:
    pass
  return {}


def save_config(cfg: dict[str, Any]) -> None:
  try:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
      json.dumps(cfg, ensure_ascii=False, indent=2, sort_keys=True),
      encoding="utf-8",
    )
  except Exception:
    pass


def merged_config() -> dict[str, Any]:
  cfg = dict(DEFAULT_CONFIG)
  cfg.update(load_config())
  if not cfg.get("rlogs"):
    cfg["rlogs"] = detect_rlog_dir()
  if "use_wsl" not in load_config() and os.name == "nt":
    cfg["use_wsl"] = detect_wsl()
  return cfg


# ── Dataset display helpers ────────────────────────────────────────────────

def _summary(dataset: dict[str, Any]) -> dict[str, Any]:
  return dataset.get("summary", {}) or {}


def _hours(value: Any) -> float:
  try:
    return float(value or 0.0)
  except (TypeError, ValueError):
    return 0.0


def display_car(car_key: str) -> str:
  car_key = str(car_key or "").strip()
  if not car_key or car_key == "UNKNOWN_CAR":
    return "차량 확인 전 데이터"
  return car_key


def display_kind(kind: str) -> str:
  return "앵글 조향" if str(kind or "").strip() == "angle" else "조향 보정"


def dataset_hours(dataset: dict[str, Any]) -> tuple[float, float, float]:
  summary = _summary(dataset)
  total = _hours(summary.get("total_hours"))
  trained = _hours(summary.get("trained_hours"))
  return total, trained, max(0.0, total - trained)


def dataset_label(dataset: dict[str, Any]) -> str:
  total, trained, new_hours = dataset_hours(dataset)
  car = display_car(str(dataset.get("car_key", "")))
  kind = display_kind(str(dataset.get("kind", "")))
  if trained > 0:
    return f"{car} · {kind} · 새 데이터 {new_hours:.1f}h"
  return f"{car} · {kind} · {total:.1f}h"


def dataset_score(dataset: dict[str, Any]) -> tuple[int, int, float, str]:
  _total, _trained, new_hours = dataset_hours(dataset)
  known_car = 0 if str(dataset.get("car_key", "")) == "UNKNOWN_CAR" else 1
  needs_training = 1 if new_hours > 0.05 else 0
  return (-needs_training, -known_car, -new_hours, dataset_label(dataset))


def safe_name(value: str, fallback: str) -> str:
  cleaned = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in (value or "").strip())
  return cleaned or fallback


# ── Main app ───────────────────────────────────────────────────────────────

def main(page: ft.Page):
  cfg: dict[str, Any] = merged_config()

  # ── Page setup ──
  page.title = "CAS Learner"
  page.theme_mode = ft.ThemeMode.LIGHT
  page.theme = ft.Theme(use_material3=True, color_scheme_seed=ft.Colors.TEAL)
  page.window.width = 580
  page.window.height = 860
  page.window.min_width = 480
  page.window.min_height = 640
  page.padding = 0
  page.spacing = 0
  page.bgcolor = ft.Colors.SURFACE
  # Page-level scroll so the 자세히(ExpansionTile) can extend beyond the
  # window height and the user can still see all entries by scrolling.
  page.scroll = ft.ScrollMode.AUTO

  # ── Mutable session state ──
  state: dict[str, Any] = {
    "datasets":         [],                # server datasets list
    "selected_index":   0,
    "proc":             None,              # current subprocess.Popen
    "proc_lock":        threading.Lock(),
    "log":              [],
    "current_run_dir":  None,              # Path of timestamped run folder
    "current_run_log":  None,              # Path of run.log file inside it
  }

  # ── Path resolution (depends on cfg) ──
  def rlog_dir() -> Path:
    return Path(cfg.get("rlogs", "") or detect_rlog_dir())

  def cas_dir() -> Path:
    return rlog_dir() / ".cas"

  def ds_train_car(ds: dict[str, Any]) -> str:
    """Effective car name for training/file naming. If the dataset is
    server-classified as UNKNOWN_CAR the user can override via the
    'train_car_override' field (set by the car-picker dialog)."""
    override = str(ds.get("train_car_override", "")).strip()
    return override or str(ds.get("car_key", "")).strip()

  def ds_cloud_car(ds: dict[str, Any]) -> str:
    """The raw car_key the cloud uses for routes/manifest lookup."""
    return str(ds.get("car_key", "")).strip()

  def candidate_path(ds: dict[str, Any]) -> Path:
    car  = safe_name(ds_train_car(ds),        "UNKNOWN_CAR")
    kind = safe_name(str(ds.get("kind", "")), "torque")
    return cas_dir() / "candidates" / f"{car}_{kind}_candidate.json"

  def validate_path(ds: dict[str, Any]) -> Path:
    car  = safe_name(ds_train_car(ds),        "UNKNOWN_CAR")
    kind = safe_name(str(ds.get("kind", "")), "torque")
    return cas_dir() / "validations" / f"{car}_{kind}_validate.json"

  def make_run_dir(ds: dict[str, Any]) -> Path:
    car  = safe_name(ds_train_car(ds),        "setup")
    kind = safe_name(str(ds.get("kind", "")), "torque")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = cas_dir() / "runs" / f"{stamp}_{car}_{kind}"
    d.mkdir(parents=True, exist_ok=True)
    return d

  # ── Core UI controls ──
  headline = ft.Text("데이터 확인 중", size=28, weight=ft.FontWeight.W_700)
  assist   = ft.Text("서버 연결 중", size=14, color=ft.Colors.ON_SURFACE_VARIANT)
  status   = ft.Text("잠시만 기다려 주세요.", size=15, weight=ft.FontWeight.W_500)
  progress = ft.ProgressBar(visible=False, value=None, bar_height=4)
  primary_button  = ft.FilledButton("학습 시작", icon=ft.Icons.PLAY_ARROW_ROUNDED, height=52, disabled=True)
  apply_button    = ft.TextButton("차량에 적용", icon=ft.Icons.DIRECTIONS_CAR, disabled=True)
  stop_button     = ft.OutlinedButton("중지", icon=ft.Icons.STOP_CIRCLE_ROUNDED, visible=False)
  refresh_button  = ft.IconButton(ft.Icons.REFRESH_ROUNDED, tooltip="새로고침")
  settings_button = ft.IconButton(ft.Icons.SETTINGS_ROUNDED, tooltip="전문가 설정")

  vehicle_menu = ft.Dropdown(
    label="다른 차량",
    border=ft.InputBorder.OUTLINE,
    visible=False,
    options=[],
  )
  detail_tile = ft.ExpansionTile(
    title=ft.Text("자세히"),
    expanded=False,
    controls=[],
    visible=False,
  )

  log_text = ft.Text("", selectable=True, size=11, font_family="Consolas")
  log_container = ft.Container(
    content=ft.ListView([log_text], spacing=2, auto_scroll=True, expand=True),
    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    border_radius=8,
    padding=12,
    height=220,
    visible=False,
  )

  # ── Settings dialog (full edit + persist) ──
  rlogs_field    = ft.TextField(label="RLOG 폴더", dense=True, hint_text=detect_rlog_dir(), expand=True)
  endpoint_field = ft.TextField(label="서버 엔드포인트", dense=True)
  token_field    = ft.TextField(label="서버 토큰 (선택)", dense=True, password=True, can_reveal_password=True)
  alpha_label    = ft.Text("Alpha max  0.50", size=12)
  alpha_slider   = ft.Slider(min=0.0, max=1.0, divisions=20, value=0.5, label="{value}")
  backend_dd     = ft.Dropdown(
    label="Backend", dense=True,
    options=[ft.dropdown.Option("auto"), ft.dropdown.Option("numpy"), ft.dropdown.Option("torch")],
  )
  device_field   = ft.TextField(label="Device (auto/cpu/cuda)", dense=True)
  workers_label  = ft.Text("Workers  4개", size=12)
  workers_slider = ft.Slider(min=1, max=16, divisions=15, value=4, label="{value}")
  epochs_field   = ft.TextField(label="Epochs", dense=True, keyboard_type=ft.KeyboardType.NUMBER)
  stride_field   = ft.TextField(label="Sample stride", dense=True, keyboard_type=ft.KeyboardType.NUMBER)
  wsl_switch       = ft.Switch(label="WSL 사용 (Windows에서만)", value=False)
  auto_dl_switch   = ft.Switch(label="학습 시작 시 자동으로 다운로드", value=True)
  cleanup_switch   = ft.Switch(label="학습 성공 후 RLOG 자동 정리", value=False)

  def _alpha_changed(_e=None):
    alpha_label.value = f"Alpha max  {alpha_slider.value:.2f}"
    page.update()

  def _workers_changed(_e=None):
    workers_label.value = f"Workers  {int(workers_slider.value)}개"
    page.update()

  alpha_slider.on_change   = _alpha_changed
  workers_slider.on_change = _workers_changed

  def settings_apply():
    """Pull dialog field values into cfg + persist."""
    try:
      cfg["rlogs"]         = (rlogs_field.value or "").strip() or detect_rlog_dir()
      cfg["endpoint"]      = (endpoint_field.value or "").strip() or cloud_sync.DEFAULT_SERVER_ENDPOINT
      cfg["token"]         = (token_field.value or "").strip()
      cfg["alpha_max"]     = float(alpha_slider.value)
      cfg["backend"]       = backend_dd.value or "auto"
      cfg["device"]        = (device_field.value or "").strip() or "auto"
      cfg["workers"]       = int(workers_slider.value)
      cfg["epochs"]        = int(epochs_field.value or "20")
      cfg["sample_stride"] = int(stride_field.value or "10")
      cfg["use_wsl"]              = bool(wsl_switch.value)
      cfg["auto_download"]        = bool(auto_dl_switch.value)
      cfg["cleanup_after_train"]  = bool(cleanup_switch.value)
      save_config(cfg)
    except Exception as e:
      open_message("설정 오류", f"값을 확인해 주세요: {e}")
      return False
    return True

  def settings_save_clicked(_e=None):
    if settings_apply():
      page.pop_dialog()
      render_dataset()
      # WSL toggle changes the python env that runs training → re-probe.
      gpu_status_text.value = "학습 환경 확인 중"
      threading.Thread(target=detect_gpu_async, daemon=True).start()

  def settings_clicked(_event=None):
    # Sync dialog widgets from current cfg before opening.
    rlogs_field.value    = str(cfg.get("rlogs", ""))
    endpoint_field.value = str(cfg.get("endpoint", ""))
    token_field.value    = str(cfg.get("token", ""))
    alpha_slider.value   = float(cfg.get("alpha_max", 0.5))
    backend_dd.value     = str(cfg.get("backend", "auto"))
    device_field.value   = str(cfg.get("device", "auto"))
    workers_slider.value = int(cfg.get("workers", 4))
    epochs_field.value   = str(cfg.get("epochs", 20))
    stride_field.value   = str(cfg.get("sample_stride", 10))
    wsl_switch.value      = bool(cfg.get("use_wsl", False))
    auto_dl_switch.value  = bool(cfg.get("auto_download", True))
    cleanup_switch.value  = bool(cfg.get("cleanup_after_train", False))
    _alpha_changed(); _workers_changed()
    page.show_dialog(settings_dialog)

  # Single column layout — two-column Row's were getting clipped at narrow
  # widths (Flet TextField doesn't auto-expand inside Row, so the right column
  # could overflow the dialog content area).
  settings_dialog = ft.AlertDialog(
    modal=True,
    title=ft.Text("전문가 설정", size=18, weight=ft.FontWeight.W_600),
    content=ft.Container(
      width=440, height=560,
      content=ft.Column([
        ft.Text("연결", size=11, color=ft.Colors.ON_SURFACE_VARIANT, weight=ft.FontWeight.W_600),
        ft.Row(
          [rlogs_field, ft.IconButton(
            ft.Icons.FOLDER_OPEN_ROUNDED,
            tooltip="폴더 선택",
            # Lambda defers resolution so pick_rlogs (defined later) is
            # looked up at click time, not at dialog-construction time.
            on_click=lambda _e: pick_rlogs(),
          )],
          spacing=4,
        ),
        endpoint_field,
        token_field,
        ft.Container(height=4),
        ft.Text("학습 옵션", size=11, color=ft.Colors.ON_SURFACE_VARIANT, weight=ft.FontWeight.W_600),
        alpha_label, alpha_slider,
        backend_dd,
        device_field,
        workers_label, workers_slider,
        epochs_field,
        stride_field,
        ft.Container(height=4),
        ft.Text("환경", size=11, color=ft.Colors.ON_SURFACE_VARIANT, weight=ft.FontWeight.W_600),
        wsl_switch,
        ft.Container(height=4),
        ft.Text("자동화", size=11, color=ft.Colors.ON_SURFACE_VARIANT, weight=ft.FontWeight.W_600),
        auto_dl_switch,
        cleanup_switch,
        ft.Container(height=4),
        ft.Text(f"설정 저장 위치: {CONFIG_PATH}", size=10, color=ft.Colors.ON_SURFACE_VARIANT),
      ], spacing=6, scroll=ft.ScrollMode.AUTO),
    ),
    actions=[],
  )
  settings_dialog.actions = [
    ft.TextButton("취소",   on_click=lambda _e: page.pop_dialog()),
    ft.FilledButton("저장", on_click=settings_save_clicked),
  ]

  # ── Action controls ──
  # Visible under primary 학습 시작: "모든 새 데이터 학습" appears only when
  # 2+ datasets have new_hours > 0.05.
  train_all_button = ft.OutlinedButton(
    "모든 새 데이터 학습", icon=ft.Icons.PLAYLIST_PLAY_ROUNDED, visible=False, height=44,
  )
  # Manual overrides — live inside 자세히, not on the main surface.
  download_button = ft.OutlinedButton("서버에서 수동 다운로드", icon=ft.Icons.CLOUD_DOWNLOAD_ROUNDED)
  cleanup_button  = ft.OutlinedButton("RLOG 캐시 전체 정리",    icon=ft.Icons.DELETE_SWEEP_ROUNDED)
  history_button  = ft.OutlinedButton("학습 이력",             icon=ft.Icons.HISTORY_ROUNDED)
  open_rlog_button = ft.IconButton(
    ft.Icons.FOLDER_OPEN_ROUNDED, tooltip="탐색기에서 열기", icon_size=18,
  )
  gpu_status_text  = ft.Text("학습 환경 확인 중", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

  # ── Generic helpers ──
  def selected_dataset() -> dict[str, Any] | None:
    if not state["datasets"]:
      return None
    i = max(0, min(state["selected_index"], len(state["datasets"]) - 1))
    return state["datasets"][i]

  def set_busy(text: str):
    status.value = text
    progress.visible = True
    primary_button.disabled = True
    refresh_button.disabled = True
    page.update()

  def set_ready():
    progress.visible = False
    refresh_button.disabled = False
    render_dataset()

  def open_message(title: str, body: str):
    dlg = ft.AlertDialog(modal=True, title=ft.Text(title), content=ft.Text(body), actions=[])
    dlg.actions = [ft.TextButton("확인", on_click=lambda _e: page.pop_dialog())]
    page.show_dialog(dlg)

  def append_log(line: str):
    log = state["log"]
    log.append(line.rstrip("\n"))
    if len(log) > LOG_MAX_LINES:
      del log[: len(log) - LOG_MAX_LINES]
    log_text.value = "\n".join(log)
    log_container.visible = True
    # Tee to run.log so the run dir captures everything even if the GUI
    # closes mid-run.
    rd = state.get("current_run_log")
    if rd is not None:
      try:
        with open(rd, "a", encoding="utf-8") as f:
          f.write(line if line.endswith("\n") else line + "\n")
      except OSError:
        pass
    try:
      page.update()
    except Exception:
      pass

  # ── Render the main card from current dataset ──
  def render_dataset():
    ds = selected_dataset()
    if ds is None:
      headline.value = "데이터 없음"
      assist.value = "서버 데이터가 없습니다"
      status.value = "새로고침 후 다시 확인하세요."
      primary_button.disabled = True
      apply_button.disabled = True
      vehicle_menu.visible = False
      detail_tile.visible = False
      page.update()
      return

    total, trained, new_hours = dataset_hours(ds)
    summary = _summary(ds)
    car = display_car(str(ds.get("car_key", "")))
    kind = display_kind(str(ds.get("kind", "")))
    source_count = int(summary.get("source_count", 0) or summary.get("segment_count", 0) or 0)
    train_runs = int(summary.get("train_run_count", 0) or 0)
    can_train = total > 0.0 and new_hours > 0.05
    enough_to_apply = trained >= MIN_APPLY_HOURS or candidate_path(ds).exists()

    is_unknown = str(ds.get("car_key", "")) == "UNKNOWN_CAR"
    headline.value = car
    assist.value = f"{kind} · {total:.1f}h 준비됨"
    if is_unknown and can_train:
      status.value = f"차량 식별 안 됨 · 새 데이터 {new_hours:.1f}h (학습 시작 시 차량 선택)"
    elif can_train:
      status.value = f"새 데이터 {new_hours:.1f}h가 있습니다."
    elif trained > 0.0:
      status.value = "최신 데이터까지 학습했습니다."
    else:
      status.value = "학습할 데이터가 없습니다."

    # UNKNOWN_CAR with data is still trainable — we'll prompt for the actual
    # car name on click. Only disable when there's truly no new data.
    primary_button.disabled = not can_train
    apply_button.disabled = not enough_to_apply
    # Count untrained datasets across all cars for the "all" button.
    untrained = [
      d for d in state["datasets"]
      if dataset_hours(d)[2] > 0.05
         and str(d.get("car_key", "")).strip()
         and str(d.get("car_key", "")) != "UNKNOWN_CAR"
    ]
    if len(untrained) >= 2:
      train_all_button.visible = True
      train_all_button.text = f"모든 새 데이터 학습 ({len(untrained)}대)"
      train_all_button.disabled = False
    else:
      train_all_button.visible = False
    vehicle_menu.visible = len(state["datasets"]) > 1
    vehicle_menu.options = [
      ft.dropdown.Option(str(i), dataset_label(item))
      for i, item in enumerate(state["datasets"])
    ]
    vehicle_menu.value = str(max(0, min(state["selected_index"], len(state["datasets"]) - 1)))
    detail_tile.visible = True
    cache_segs, cache_bytes, cache_routes = get_local_cache_stats()
    cache_summary = (
      f"{cache_segs:,}개 세그먼트 · {format_bytes(cache_bytes)}"
      if cache_segs > 0 else "비어있음"
    )
    detail_tile.controls = [
      # 학습 환경: GPU/CPU 모드 + Python/WSL
      ft.ListTile(
        leading=ft.Icon(ft.Icons.MEMORY_ROUNDED, color=ft.Colors.PRIMARY),
        title=ft.Text("학습 환경"),
        subtitle=gpu_status_text,
        dense=True,
      ),
      # RLOG 폴더 + 캐시 + 열기 버튼
      ft.ListTile(
        leading=ft.Icon(ft.Icons.FOLDER_ROUNDED),
        title=ft.Text("RLOG 폴더"),
        subtitle=ft.Text(f"{rlog_dir()}\n캐시 {cache_summary}"),
        trailing=open_rlog_button,
        dense=True,
      ),
      # 학습 옵션 요약
      ft.ListTile(
        leading=ft.Icon(ft.Icons.SCIENCE_ROUNDED),
        title=ft.Text("학습 옵션"),
        subtitle=ft.Text(
          f"α≤{cfg['alpha_max']:.2f} · backend={cfg['backend']} · device={cfg['device']}\n"
          f"workers={cfg['workers']} · epochs={cfg['epochs']} · stride={cfg['sample_stride']}"
          + (" · WSL" if cfg.get("use_wsl") else "")
        ),
        dense=True,
      ),
      # 학습 이력 요약 + 클릭하면 다이얼로그
      ft.ListTile(
        leading=ft.Icon(ft.Icons.TIMELINE_ROUNDED),
        title=ft.Text("학습 이력"),
        subtitle=ft.Text(f"학습 {trained:.1f}h · 실행 {train_runs}회"),
        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED),
        dense=True,
        on_click=lambda _e: history_clicked(),
      ),
      # 서버 endpoint (작게)
      ft.ListTile(
        leading=ft.Icon(ft.Icons.CLOUD_DONE_ROUNDED),
        title=ft.Text("서버"),
        subtitle=ft.Text(f"{cfg.get('endpoint','')} · 세그먼트 {source_count:,}개"),
        dense=True,
      ),
      ft.Divider(height=1),
      # 데이터 액션 (다운로드/정리)
      ft.Container(
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        content=ft.Row(
          [download_button, cleanup_button],
          spacing=8, wrap=True, run_spacing=8,
        ),
      ),
    ]
    page.update()

  # ── Server data fetch ──
  def load_server_data():
    set_busy("서버 데이터를 확인하고 있습니다.")
    try:
      manifest = cloud_sync.fetch_server_manifest(
        endpoint=cfg.get("endpoint") or cloud_sync.DEFAULT_SERVER_ENDPOINT,
        token=cfg.get("token", ""),
        include_routes=True,
        timeout=30.0,
      )
      loaded = list(manifest.get("datasets", []) or [])
      loaded.sort(key=dataset_score)
      state["datasets"][:] = loaded
    except Exception as e:
      progress.visible = False
      refresh_button.disabled = False
      headline.value = "연결 실패"
      assist.value = "서버를 확인할 수 없습니다"
      status.value = str(e)
      primary_button.disabled = True
      apply_button.disabled = True
      page.update()
      return
    set_ready()

  def refresh_clicked(_event=None):
    threading.Thread(target=load_server_data, daemon=True).start()

  def vehicle_changed(event: ft.ControlEvent):
    try:
      state["selected_index"] = int(event.control.value)
    except (TypeError, ValueError):
      state["selected_index"] = 0
    render_dataset()

  # ── Command construction ──
  def py_bin() -> str:
    return "python3" if cfg.get("use_wsl") and os.name == "nt" else sys.executable

  def maybe_wsl_path(p: str) -> str:
    if cfg.get("use_wsl") and os.name == "nt":
      return windows_to_wsl(p)
    return p

  def build_train_cmd(ds: dict[str, Any], candidate: Path, audit_dir: Path) -> list[str]:
    cmd = [
      py_bin(), "tools/cas/train.py",
      "--rlogs",         maybe_wsl_path(str(rlog_dir())),
      "--car",           ds_train_car(ds),
      "--kind",          str(ds.get("kind", "torque")).strip() or "torque",
      "--output",        maybe_wsl_path(str(candidate)),
      "--alpha-max",     str(cfg["alpha_max"]),
      "--epochs",        str(cfg["epochs"]),
      "--sample-stride", str(cfg["sample_stride"]),
      "--workers",       str(cfg["workers"]),
      "--backend",       str(cfg["backend"]),
      "--device",        str(cfg["device"]),
      "--audit-dir",     maybe_wsl_path(str(audit_dir)),
      "--audit-samples",
    ]
    return cmd

  def build_validate_cmd(ds: dict[str, Any], candidate: Path, validate_out: Path,
                         audit_dir: Path) -> list[str]:
    cmd = [
      py_bin(), "tools/cas/validate.py",
      "--model",         maybe_wsl_path(str(candidate)),
      "--rlogs",         maybe_wsl_path(str(rlog_dir())),
      "--workers",       str(cfg["workers"]),
      "--sample-stride", str(cfg["sample_stride"]),
      "--output",        maybe_wsl_path(str(validate_out)),
      "--audit-dir",     maybe_wsl_path(str(audit_dir)),
      "--audit-samples",
    ]
    return cmd

  def build_promote_cmd(ds: dict[str, Any], candidate: Path) -> list[str]:
    # Promote runs on the Windows side too (writes into the repo's
    # selfdrive/carrot/cas/weights/) so no WSL wrapping needed.
    return [
      sys.executable, str(REPO_ROOT / "tools" / "cas" / "promote.py"),
      "--candidate",  str(candidate),
      "--car",        ds_train_car(ds),
      "--kind",       str(ds.get("kind", "torque")).strip() or "torque",
      "--max-alpha",  str(cfg["alpha_max"]),
      "--force",
    ]

  def wrap_for_wsl(args: list[str]) -> list[str]:
    inner = " ".join(shlex.quote(a) for a in args)
    return ["wsl", "bash", "-lc",
            f"cd {shlex.quote(windows_to_wsl(str(REPO_ROOT)))} && {inner}"]

  # ── Run metadata + history ──
  def write_run_metadata(run_dir: Path, ds: dict[str, Any], commands: list[list[str]]):
    md = {
      "started_at":    datetime.now().isoformat(timespec="seconds"),
      "repo":          str(REPO_ROOT),
      "rlogs":         str(rlog_dir()),
      "car_key":       ds_train_car(ds),
      "cloud_car_key": ds_cloud_car(ds),
      "kind":          str(ds.get("kind", "")),
      "alpha_max":     cfg["alpha_max"],
      "backend":       cfg["backend"],
      "device":        cfg["device"],
      "workers":       cfg["workers"],
      "epochs":        cfg["epochs"],
      "sample_stride": cfg["sample_stride"],
      "use_wsl":       cfg["use_wsl"],
      "commands":      commands,
    }
    try:
      (run_dir / "run_metadata.json").write_text(
        json.dumps(md, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
      append_log(f"[meta] write error: {e}")

  def record_train_run(ds: dict[str, Any], candidate: Path, validate_out: Path, run_dir: Path):
    if not candidate.exists() or not validate_out.exists():
      append_log("[history] candidate or validate missing, skipping record")
      return
    try:
      summary  = json.loads(validate_out.read_text(encoding="utf-8"))
      cand_md  = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception as e:
      append_log(f"[history] parse error: {e}")
      return
    car   = str(ds.get("car_key", "") or cand_md.get("car") or "")
    kind  = str(ds.get("kind", "torque") or cand_md.get("kind") or "torque")
    hours = float(cand_md.get("trained_on_hours", summary.get("duration_hours", 0.0)) or 0.0)
    run = {
      "train_run_id":      run_dir.name,
      "created_at":        datetime.now().isoformat(timespec="seconds"),
      "run_dir":           str(run_dir),
      "car_key":           car,
      "kind":              kind,
      "trained_on_hours":  hours,
      "candidate":         str(candidate),
      "validate_json":     str(validate_out),
      "grade_source":      "validate_summary",
    }
    # Local persistence
    try:
      runs_path = cas_dir() / "train_runs.json"
      runs_path.parent.mkdir(parents=True, exist_ok=True)
      data = {}
      if runs_path.exists():
        try:
          data = json.loads(runs_path.read_text(encoding="utf-8"))
        except Exception:
          data = {}
      data.setdefault("runs", []).append(run)
      runs_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
      append_log(f"[history] local: {runs_path} (+1 run, {hours:.2f}h)")
    except OSError as e:
      append_log(f"[history] local error: {e}")
    # Server upload (best-effort)
    endpoint = cfg.get("endpoint", "").strip()
    if endpoint:
      try:
        result = cloud_sync.post_train_run(endpoint, run, token=cfg.get("token", ""), timeout=20.0)
        append_log(f"[history] server: count={result.get('count')}")
      except Exception as e:
        append_log(f"[history] server error: {e}")

  # ── Subprocess runner ──
  def _set_busy_ui():
    stop_button.visible      = True
    progress.visible         = True
    progress.value           = None
    primary_button.disabled  = True
    train_all_button.disabled = True
    apply_button.disabled    = True
    refresh_button.disabled  = True
    download_button.disabled = True
    cleanup_button.disabled  = True
    try: page.update()
    except Exception: pass

  def _set_idle_ui():
    stop_button.visible      = False
    progress.visible         = False
    refresh_button.disabled  = False
    primary_button.disabled  = False
    train_all_button.disabled = False
    apply_button.disabled    = False
    download_button.disabled = False
    cleanup_button.disabled  = False
    try: page.update()
    except Exception: pass

  def _execute_commands_inline(commands: list[tuple[list[str], str]]) -> bool:
    """Sync: run commands sequentially, return overall_ok.
    Updates per-command status/log but does NOT toggle pipeline-level UI.
    Cancellable via state['cancel'] flag (and stop_button → terminate)."""
    state["cancel"] = False
    overall_ok = True
    for raw_cmd, label in commands:
      if state.get("cancel"):
        overall_ok = False
        status.value = "중단됨"
        break
      effective = list(raw_cmd)
      if cfg.get("use_wsl") and os.name == "nt" and label != "Apply":
        # Promote stays native; Train/Validate go through WSL.
        effective = wrap_for_wsl(effective)
      append_log(f"\n[{label}] > " + " ".join(effective))
      status.value = f"{label} 실행 중"
      progress.visible = True
      page.update()

      code = -1
      try:
        with state["proc_lock"]:
          state["proc"] = subprocess.Popen(
            effective,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
          )
        proc = state["proc"]
        assert proc.stdout is not None
        for line in proc.stdout:
          append_log(line)
        code = proc.wait()
        append_log(f"[{label}] exit={code}")
      except Exception as e:
        append_log(f"[{label}] ERROR: {e}")
      finally:
        with state["proc_lock"]:
          state["proc"] = None

      if code != 0:
        overall_ok = False
        status.value = f"{label} 실패 (exit={code})"
        break
    return overall_ok

  def run_subprocess(commands: list[tuple[list[str], str]], on_done=None):
    """Apply / one-shot: wrap _execute_commands with UI fanfare."""
    _set_busy_ui()
    ok = _execute_commands_inline(commands)
    if ok:
      status.value = "완료"
      show_toast(f"{commands[-1][1]} 완료" if commands else "완료")
    else:
      show_toast(f"실행 실패: {commands[-1][1] if commands else 'unknown'}", error=True)
    _set_idle_ui()

    if on_done is not None:
      try:
        on_done(ok)
      except Exception as e:
        append_log(f"[on_done] {e}")

    threading.Thread(target=load_server_data, daemon=True).start()

  # ── Cloud helpers shared by manual download and auto-pipeline ──
  def download_for_car_kind(car_key: str, kind: str) -> tuple[int, int, int]:
    """Download all missing rlog.zst/qlog.zst for (car, kind). Skips files that
    already exist locally. Returns (downloaded, skipped, failed)."""
    endpoint = cfg.get("endpoint") or cloud_sync.DEFAULT_SERVER_ENDPOINT
    token = cfg.get("token", "")
    routes_data = cloud_sync.fetch_server_routes(
      endpoint=endpoint, car_key=car_key, kind=kind,
      token=token, limit=500, timeout=30.0,
    )
    routes = list(routes_data.get("routes", []) or [])
    downloaded = skipped = failed = 0
    total = len(routes)
    for r_idx, route in enumerate(routes, 1):
      if state.get("cancel"):
        append_log("[download] 중단됨")
        break
      device_id = str(route.get("device_id", ""))
      route_id  = str(route.get("route_id", ""))
      segments  = route.get("segments", []) or []
      for seg in segments:
        segment = str(seg.get("segment", "") if isinstance(seg, dict) else seg)
        files = cloud_sync.cloud_route_files(str(rlog_dir()), device_id, route_id, segment)
        rlog_dest = Path(files.get("rlog", ""))
        if rlog_dest.exists() and rlog_dest.stat().st_size > 0:
          skipped += 1
          continue
        status.value = f"다운로드 {r_idx}/{total}: {route_id[:24]}…/{segment}"
        try: page.update()
        except Exception: pass
        try:
          cloud_sync.download_segment(
            endpoint=endpoint, rlogs=str(rlog_dir()),
            device_id=device_id, route_id=route_id, segment=segment,
            token=token,
          )
          downloaded += 1
          if downloaded % 5 == 0:
            append_log(f"[download] 진행 {downloaded}개 받음 · {skipped}개 건너뜀 · {failed}개 실패")
        except Exception as e:
          failed += 1
          append_log(f"[download] FAIL {route_id}/{segment}: {e}")
    return downloaded, skipped, failed

  def cleanup_for_car_kind(car_key: str, kind: str) -> tuple[int, int]:
    """Delete local cache for routes belonging to (car, kind) on server.
    Returns (segments_removed, bytes_removed)."""
    endpoint = cfg.get("endpoint") or cloud_sync.DEFAULT_SERVER_ENDPOINT
    token = cfg.get("token", "")
    routes_data = cloud_sync.fetch_server_routes(
      endpoint=endpoint, car_key=car_key, kind=kind,
      token=token, limit=500, timeout=30.0,
    )
    import shutil
    segs = 0
    total_bytes = 0
    for route in routes_data.get("routes", []) or []:
      device_id = str(route.get("device_id", ""))
      route_id  = str(route.get("route_id", ""))
      segments  = route.get("segments", []) or []
      for seg in segments:
        segment = str(seg.get("segment", "") if isinstance(seg, dict) else seg)
        route_dir = cloud_sync.cloud_route_dir(str(rlog_dir()), device_id, route_id, segment)
        if route_dir.exists():
          try:
            for f in route_dir.rglob("*"):
              try: total_bytes += f.stat().st_size
              except OSError: pass
            shutil.rmtree(route_dir, ignore_errors=True)
            segs += 1
          except OSError as e:
            append_log(f"[cleanup] {route_dir.name}: {e}")
    return segs, total_bytes

  # ── Full train pipeline (download → train → validate → record → cleanup) ──
  def train_pipeline_worker(ds: dict[str, Any]) -> bool:
    """Single-dataset pipeline. Returns True if train+validate succeeded."""
    cloud_car = ds_cloud_car(ds)                    # for routes/manifest lookup
    train_car = ds_train_car(ds)                    # for --car flag + file names
    kind = str(ds.get("kind", "torque")).strip() or "torque"
    if not train_car or train_car == "UNKNOWN_CAR":
      append_log(f"[pipeline] 차량 미식별 건너뜀: {train_car or '?'}")
      return False

    # Phase 1: auto-download (best-effort — failure doesn't abort)
    # Use cloud_car for the routes API: when the user re-tagged UNKNOWN data
    # as e.g. CASPER_EV, we still fetch the original UNKNOWN_CAR bucket from
    # the server (that's where the rlogs actually live).
    if cfg.get("auto_download", True):
      try:
        n_dl, n_skip, n_fail = download_for_car_kind(cloud_car, kind)
        bin_note = f" (서버 bin: {cloud_car})" if cloud_car != train_car else ""
        append_log(f"[{train_car}/{kind}] 다운로드{bin_note}: 새 {n_dl} · 기존 {n_skip} · 실패 {n_fail}")
        refresh_data_status()
      except Exception as e:
        append_log(f"[{train_car}/{kind}] 다운로드 실패 ({e}) — 로컬 데이터로 학습 시도")

    if state.get("cancel"):
      return False

    # Phase 2: train + validate
    run_dir = make_run_dir(ds)
    state["current_run_dir"] = run_dir
    state["current_run_log"] = run_dir / "run.log"
    cand = candidate_path(ds)
    val  = validate_path(ds)
    cand.parent.mkdir(parents=True, exist_ok=True)
    val.parent.mkdir(parents=True, exist_ok=True)
    train_cmd = build_train_cmd(ds, cand, run_dir / "train_audit")
    val_cmd   = build_validate_cmd(ds, cand, val, run_dir / "validate_audit")
    write_run_metadata(run_dir, ds, [train_cmd, val_cmd])
    append_log(f"\n[run] {run_dir}")

    ok = _execute_commands_inline([(train_cmd, "Train"), (val_cmd, "Validate")])

    # Phase 3: record train run
    if ok:
      try:
        record_train_run(ds, cand, val, run_dir)
      except Exception as e:
        append_log(f"[record] {e}")

      # Phase 4: auto-promote — copy candidate JSON to repo's weights/ so PC-side
      # runtime (if anyone runs it) can match. Devices get it via Phase 5 (OTA pull
      # from server). We promote first so the same file is ready for both paths.
      promote_cmd = build_promote_cmd(ds, cand)
      ok_promote = _execute_commands_inline([(promote_cmd, "Promote")])
      append_log(f"[promote] {'OK' if ok_promote else 'FAIL'}")

      # Phase 5: auto-publish to server. Device puller will pick this up at next
      # boot. rlog files are unrelated; we send only the small model JSON.
      if ok_promote:
        try:
          endpoint = cfg.get("endpoint") or cloud_sync.DEFAULT_SERVER_ENDPOINT
          secret = cloud_sync.resolve_upload_secret()
          result = cloud_sync.post_model(
            endpoint, train_car, kind, str(cand), secret, timeout=60.0,
          )
          append_log(f"[publish] 서버 발행 완료: car={train_car}/{kind} "
                     f"version={result.get('version','?')} "
                     f"sha={str(result.get('sha256',''))[:12]}…")
        except Exception as e:
          append_log(f"[publish] FAIL: {e}")

      # Phase 6: optional cleanup
      if cfg.get("cleanup_after_train", False):
        try:
          n_segs, n_bytes = cleanup_for_car_kind(cloud_car, kind)
          if n_segs > 0:
            append_log(f"[{train_car}/{kind}] 자동 정리: {n_segs}개 세그먼트 · {format_bytes(n_bytes)} 삭제")
        except Exception as e:
          append_log(f"[cleanup] {e}")

    state["current_run_dir"] = None
    state["current_run_log"] = None
    return ok

  def train_pipeline_wrapper(ds_list: list[dict[str, Any]], label_prefix: str = ""):
    """Run train_pipeline_worker for each ds, sequentially. UI fanfare handled here."""
    _set_busy_ui()
    state["cancel"] = False
    results: list[tuple[str, bool]] = []
    try:
      for idx, ds in enumerate(ds_list, 1):
        if state.get("cancel"):
          append_log("[pipeline] 사용자 중단")
          break
        car = str(ds.get("car_key", "?"))
        if len(ds_list) > 1:
          append_log(f"\n═══ {label_prefix} {idx}/{len(ds_list)} · {car} ═══")
        ok = train_pipeline_worker(ds)
        results.append((car, ok))
    finally:
      _set_idle_ui()

    ok_n = sum(1 for _, ok in results if ok)
    fail_n = len(results) - ok_n
    if len(ds_list) == 1:
      msg = "학습 완료" if results and results[0][1] else "학습 실패"
      show_toast(msg, error=not (results and results[0][1]))
    else:
      msg = f"{ok_n}/{len(ds_list)} 차량 학습 완료"
      show_toast(msg, error=fail_n > 0)
    status.value = msg

    refresh_data_status()
    threading.Thread(target=load_server_data, daemon=True).start()

  # ── Backfill server route_meta (re-bin UNKNOWN → chosen car) ──
  def backfill_server_meta(ds: dict[str, Any], chosen_car: str):
    """Overwrite route_meta.json on the server for every route in this
    dataset's cloud bin, tagging it with chosen_car. rlogs untouched."""
    endpoint = cfg.get("endpoint") or cloud_sync.DEFAULT_SERVER_ENDPOINT
    cloud_car = ds_cloud_car(ds) or "UNKNOWN_CAR"
    kind = str(ds.get("kind", "torque")).strip() or "torque"
    try:
      secret = cloud_sync.resolve_upload_secret()
    except Exception as e:
      append_log(f"[backfill] 시크릿 로드 실패: {e}")
      show_toast("서버 메타 갱신 실패 (시크릿)", error=True)
      return
    try:
      routes_data = cloud_sync.fetch_server_routes(
        endpoint=endpoint, car_key=cloud_car, kind=kind,
        token=cfg.get("token", ""), limit=500, timeout=30.0,
      )
    except Exception as e:
      append_log(f"[backfill] 라우트 조회 실패: {e}")
      show_toast("서버 메타 갱신 실패 (라우트 조회)", error=True)
      return
    routes = list(routes_data.get("routes", []) or [])
    n_ok = n_fail = 0
    append_log(f"\n[backfill] {cloud_car} → {chosen_car} · {len(routes)} 라우트 메타 갱신")
    for route in routes:
      device_id = str(route.get("device_id", "")).strip()
      route_id  = str(route.get("route_id", "")).strip()
      if not device_id or not route_id:
        continue
      meta = dict(route.get("route_meta", {}) or {})
      meta["car_name_raw"]   = chosen_car
      meta["car_key"]        = chosen_car
      meta["backfilled_at"]  = int(__import__("time").time())
      meta["backfill_source"] = "gui_manual"
      try:
        cloud_sync.post_route_meta(endpoint, device_id, route_id, meta, secret, timeout=30.0)
        n_ok += 1
      except Exception as e:
        n_fail += 1
        append_log(f"[backfill] FAIL {route_id}: {e}")
    append_log(f"[backfill] 완료: 성공 {n_ok} · 실패 {n_fail}")
    show_toast(f"서버 메타 {n_ok}개 갱신 (다음 새로고침부터 {chosen_car})",
               error=n_fail > 0 and n_ok == 0)
    threading.Thread(target=load_server_data, daemon=True).start()

  # ── Car identification prompt (for UNKNOWN_CAR datasets) ──
  def prompt_car_and_train(ds: dict[str, Any]):
    """Server bucketed this data as UNKNOWN_CAR — let user tell us which car
    these rlogs are for, then proceed with that name as --car.
    Inspects each route's route_meta (uploaded by the device) for car hints
    so the user doesn't have to type blind."""
    # 1) Hints from the device's own meta (uploaded as route_meta.json).
    #    Look at all the identity fields the device might have populated even
    #    when the server's binning failed. EPS firmware hash is collected for
    #    display only — not for matching.
    device_hints: dict[str, str] = {}
    eps_hashes: set[str] = set()
    for route in ds.get("routes", []) or []:
      meta = (route.get("route_meta") or {}) if isinstance(route, dict) else {}
      for key in ("last_known_car", "car_name_raw", "car_selected",
                  "car_make", "car"):
        val = str(meta.get(key, "")).strip()
        if val and val.upper() != "UNKNOWN_CAR":
          device_hints.setdefault(key, val)
      eps = str(meta.get("eps_firmware_hash", "")).strip()
      if eps:
        eps_hashes.add(eps)

    # 2) Cars seen in other datasets (already-identified cars on this server).
    other_cars = {
      ds_train_car(d) for d in state["datasets"]
      if ds_train_car(d) and ds_train_car(d) != "UNKNOWN_CAR"
    }
    # Suggestion set = device hints + other cars. Dropdown options.
    candidates = sorted(other_cars | set(device_hints.values()))

    # 3) Default text — best single guess.
    #    Priority: last_known_car > car_name_raw > car_selected > car_make > car
    default = ""
    for key in ("last_known_car", "car_name_raw", "car_selected", "car_make", "car"):
      if device_hints.get(key):
        default = device_hints[key]
        break

    car_dd = ft.Dropdown(
      label="알려진 차량에서 선택",
      options=[ft.dropdown.Option(c) for c in candidates],
      value=default if default in candidates else None,
      dense=True,
    )
    car_tf = ft.TextField(
      label="또는 직접 입력 (예: HYUNDAI_CASPER_EV)",
      value=default,
      dense=True,
    )
    update_server_cb = ft.Checkbox(
      label="서버 메타도 갱신 (다음부터 자동 인식)", value=True,
    )

    def confirm(_e=None):
      chosen = (car_tf.value or "").strip() or (car_dd.value or "").strip()
      if not chosen:
        show_toast("차량을 선택하거나 입력하세요", error=True)
        return
      if chosen.upper() == "UNKNOWN_CAR":
        show_toast("UNKNOWN_CAR는 학습 대상 이름이 될 수 없습니다", error=True)
        return
      do_backfill = bool(update_server_cb.value)
      page.pop_dialog()
      resolved = dict(ds)
      resolved["train_car_override"] = chosen
      append_log(f"[pipeline] UNKNOWN_CAR 데이터를 '{chosen}'로 학습 진행")
      # Optionally re-bin on the server (overwrite route_meta) so future
      # refreshes see this data under the real car, not UNKNOWN.
      if do_backfill:
        threading.Thread(
          target=lambda: backfill_server_meta(ds, chosen), daemon=True,
        ).start()
      threading.Thread(
        target=lambda: train_pipeline_wrapper([resolved], label_prefix="단일 차량"),
        daemon=True,
      ).start()

    # Device-report hint block (collapsed in plain text — only shown when there
    # are any hints to display).
    hint_lines: list[str] = []
    label_map = {
      "last_known_car": "디바이스 직전 차량",
      "car_name_raw":   "디바이스 CarName",
      "car_selected":   "Carrot CarSelected3",
      "car_make":       "carParams.make",
      "car":            "carParams.carFingerprint",
    }
    for key, label in label_map.items():
      if device_hints.get(key):
        hint_lines.append(f"  · {label}: {device_hints[key]}")
    if eps_hashes:
      hint_lines.append(f"  · EPS 해시(참고): {', '.join(sorted(eps_hashes))}")
    if hint_lines:
      hint_block = ft.Text(
        "디바이스가 보고한 단서:\n" + "\n".join(hint_lines),
        size=11, color=ft.Colors.ON_SURFACE_VARIANT,
      )
    else:
      hint_block = ft.Text(
        "디바이스가 식별 정보를 보내지 않았습니다 — 직접 입력하세요.",
        size=11, color=ft.Colors.ON_SURFACE_VARIANT,
      )

    dlg = ft.AlertDialog(
      modal=True,
      title=ft.Text("차량 식별이 필요합니다", size=18, weight=ft.FontWeight.W_600),
      content=ft.Container(width=460, content=ft.Column([
        ft.Text("이 데이터는 서버에서 차량 식별이 되지 않았습니다.\n"
                "어느 차량의 데이터인지 지정하면 학습이 진행됩니다.",
                size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Container(height=8),
        hint_block,
        ft.Container(height=8),
        car_dd if candidates else ft.Text(
          "(선택할 차량 후보가 없습니다)", size=11, color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        car_tf,
        update_server_cb,
        ft.Container(height=4),
        ft.Text("※ 입력한 이름은 학습된 모델 파일명과 차량 매칭에 사용됩니다.\n"
                "openpilot에 등록된 정확한 platform 이름을 권장합니다.\n"
                "※ '서버 메타 갱신'은 rlog는 그대로 두고 메타(작은 JSON)만\n"
                "   덮어써 서버 분류를 UNKNOWN → 해당 차량으로 바꿉니다.",
                size=10, color=ft.Colors.ON_SURFACE_VARIANT),
      ], spacing=8, tight=True)),
    )
    dlg.actions = [
      ft.TextButton("취소",       on_click=lambda _e: page.pop_dialog()),
      ft.FilledButton("학습 시작", on_click=confirm),
    ]
    page.show_dialog(dlg)

  # ── Click handlers ──
  def train_clicked(_event=None):
    ds = selected_dataset()
    if ds is None:
      show_toast("선택된 차량이 없습니다", error=True)
      return
    if not rlog_dir().exists():
      open_message("RLOG 폴더 없음",
                   f"학습에 쓸 rlog 폴더가 없습니다.\n전문가 설정에서 경로를 지정하세요.\n현재: {rlog_dir()}")
      return
    # If the server didn't identify the car, ask the user before training.
    if not ds_train_car(ds) or ds_train_car(ds) == "UNKNOWN_CAR":
      prompt_car_and_train(ds)
      return
    threading.Thread(
      target=lambda: train_pipeline_wrapper([ds], label_prefix="단일 차량"),
      daemon=True,
    ).start()

  def train_all_clicked(_event=None):
    untrained = []
    for d in state["datasets"]:
      _t, _tr, new_h = dataset_hours(d)
      car = str(d.get("car_key", "")).strip()
      if not car or car == "UNKNOWN_CAR":
        continue
      if new_h > 0.05:
        untrained.append(d)
    if not untrained:
      show_toast("학습할 새 데이터가 있는 차량이 없습니다")
      return
    threading.Thread(
      target=lambda: train_pipeline_wrapper(untrained, label_prefix=f"전체 {len(untrained)}대"),
      daemon=True,
    ).start()

  def apply_clicked(_event=None):
    ds = selected_dataset()
    if ds is None:
      return
    cand = candidate_path(ds)
    if not cand.exists():
      open_message(
        "candidate 없음",
        f"먼저 학습을 실행하세요.\n예상 경로:\n{cand}",
      )
      return
    threading.Thread(
      target=run_subprocess,
      args=([(build_promote_cmd(ds, cand), "Apply")],),
      daemon=True,
    ).start()

  def stop_clicked(_event=None):
    # Flag is checked by the multi-phase pipeline between phases (download /
    # train / validate / next car). subprocess.terminate covers the running
    # external process for immediate stop.
    state["cancel"] = True
    with state["proc_lock"]:
      proc = state["proc"]
      if proc is not None and proc.poll() is None:
        proc.terminate()
        append_log("[중지] terminate 신호 전송")
      else:
        append_log("[중지] 다음 단계 진입 시 중단됩니다")

  # ── Snackbar ──
  def show_toast(msg: str, error: bool = False):
    # In Flet 0.85 SnackBar is a DialogControl — use page.show_dialog().
    # Old pattern (page.overlay.append + open=True) doesn't render here.
    sb = ft.SnackBar(
      content=ft.Text(msg),
      bgcolor=ft.Colors.ERROR if error else ft.Colors.INVERSE_SURFACE,
      duration=4000,
    )
    try:
      page.show_dialog(sb)
    except Exception:
      pass

  # ── Open RLOG folder in OS file explorer ──
  def open_rlog_clicked(_e=None):
    target = rlog_dir()
    try:
      target.mkdir(parents=True, exist_ok=True)
    except OSError:
      pass
    try:
      if os.name == "nt":
        os.startfile(str(target))                    # type: ignore[attr-defined]
      elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
      else:
        subprocess.Popen(["xdg-open", str(target)])
    except Exception as e:
      show_toast(f"폴더 열기 실패: {e}", error=True)

  # ── GPU / backend detection (run in background) ──
  def detect_gpu_text() -> str:
    """Probe PyTorch + CUDA in the actual env that will run training."""
    probe = (
      "import sys; "
      "out = []\n"
      "try:\n"
      "  import torch; out.append(torch.__version__)\n"
      "  cuda = torch.cuda.is_available()\n"
      "  out.append('CUDA' if cuda else 'CPU')\n"
      "  out.append(torch.cuda.get_device_name(0) if cuda else '')\n"
      "except Exception as e:\n"
      "  print('NOTORCH:' + str(e)); sys.exit(0)\n"
      "print('|'.join(out))"
    )
    try:
      if cfg.get("use_wsl") and os.name == "nt":
        cmd = ["wsl", "bash", "-lc", f"python3 -c {shlex.quote(probe)}"]
      else:
        cmd = [sys.executable, "-c", probe]
      r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
      out = (r.stdout or "").strip().splitlines()
      if not out:
        return "PyTorch 응답 없음"
      last = out[-1]
      if last.startswith("NOTORCH:"):
        return f"PyTorch 미설치 — {'WSL ' if cfg.get('use_wsl') else ''}환경에 torch 설치 필요"
      parts = last.split("|")
      if len(parts) >= 2 and parts[1] == "CUDA":
        name = parts[2] if len(parts) > 2 and parts[2] else "GPU"
        return f"GPU 사용 가능: {name}  (PyTorch {parts[0]})"
      if len(parts) >= 2 and parts[1] == "CPU":
        return f"CPU 모드  (PyTorch {parts[0]}, CUDA 미감지)"
      return last
    except subprocess.TimeoutExpired:
      return "감지 시간 초과"
    except Exception as e:
      return f"감지 실패: {e}"

  def detect_gpu_async():
    txt = detect_gpu_text()
    gpu_status_text.value = txt
    try:
      page.update()
    except Exception:
      pass

  # ── File picker for RLOG folder ──
  # Flet ≥ 0.83 made FilePicker a `Service` (not a Control). It must go into
  # page.services, NOT page.overlay — adding it to overlay renders as a
  # visible "Unknown control" red banner. get_directory_path() is `async` and
  # returns the path directly (no on_result callback); drive it via
  # page.run_task() so the Future runs on Flet's own event loop.
  rlogs_picker = ft.FilePicker()
  page.services.append(rlogs_picker)

  async def _pick_rlogs_async():
    initial = (rlogs_field.value or "").strip() or str(rlog_dir())
    try:
      path = await rlogs_picker.get_directory_path(
        dialog_title="RLOG 폴더 선택",
        initial_directory=initial,
      )
      if path:
        rlogs_field.value = path
        page.update()
    except Exception as e:
      show_toast(f"폴더 선택 실패: {e}", error=True)

  def pick_rlogs(_e=None):
    page.run_task(_pick_rlogs_async)

  # ── Cache stats / formatting ──
  def format_bytes(n: int) -> str:
    if n < 1024:        return f"{n} B"
    if n < 1024 ** 2:   return f"{n/1024:.1f} KB"
    if n < 1024 ** 3:   return f"{n/(1024**2):.1f} MB"
    return f"{n/(1024**3):.2f} GB"

  def get_local_cache_stats() -> tuple[int, int, int]:
    """(segment_count, total_bytes, route_count)."""
    cache_root = cas_dir() / "cloud_cache"
    if not cache_root.exists():
      return 0, 0, 0
    segs = 0
    total = 0
    routes: set[tuple[str, str]] = set()
    try:
      for path in cache_root.rglob("rlog.zst"):
        segs += 1
        try:
          total += path.stat().st_size
        except OSError:
          pass
        parts = path.relative_to(cache_root).parts
        if len(parts) >= 2:
          routes.add((parts[0], parts[1]))
    except OSError:
      pass
    return segs, total, len(routes)

  def refresh_data_status():
    segs, _total, _routes = get_local_cache_stats()
    cleanup_button.disabled = (segs == 0)
    # Re-render detail_tile (it shows cache stats inline).
    try:
      render_dataset()
    except Exception:
      pass

  # ── Manual server download (selected car only) ──
  def download_clicked(_event=None):
    """Manual override — downloads new segments for the currently selected car.
    The train pipeline already does this automatically when auto_download is on;
    this button is for the case where the user just wants the files locally."""
    ds = selected_dataset()
    if ds is None:
      show_toast("선택된 차량이 없습니다", error=True)
      return
    car = str(ds.get("car_key", "")).strip()
    kind = str(ds.get("kind", "torque")).strip() or "torque"
    if not car or car == "UNKNOWN_CAR":
      show_toast("차량 미확인 데이터입니다 (서버 측 식별 필요)", error=True)
      return

    def worker():
      _set_busy_ui()
      state["cancel"] = False
      append_log(f"\n[download] {car}/{kind} 수동 다운로드")
      n_dl = n_skip = n_fail = 0
      try:
        n_dl, n_skip, n_fail = download_for_car_kind(car, kind)
        msg = f"새로 {n_dl}개 · 기존 {n_skip}개 유지"
        if n_fail: msg += f" · 실패 {n_fail}개"
        show_toast(msg, error=n_fail > 0 and n_dl == 0)
      except Exception as e:
        append_log(f"[download] ERROR: {e}")
        show_toast(f"다운로드 실패: {e}", error=True)
      finally:
        status.value = "완료"
        refresh_data_status()
        _set_idle_ui()
        threading.Thread(target=load_server_data, daemon=True).start()

    threading.Thread(target=worker, daemon=True).start()

  # ── Cleanup ──
  def cleanup_clicked(_event=None):
    segs, total, routes = get_local_cache_stats()
    if segs == 0:
      show_toast("정리할 캐시가 없습니다")
      return
    cleanup_dlg = ft.AlertDialog(modal=True, title=ft.Text("RLOG 캐시 정리"))
    cleanup_dlg.content = ft.Container(
      width=420,
      content=ft.Column([
        ft.Text(f"세그먼트  {segs:,}개"),
        ft.Text(f"라우트    {routes:,}개"),
        ft.Text(f"용량      {format_bytes(total)}"),
        ft.Container(height=8),
        ft.Text(f"폴더: {cas_dir() / 'cloud_cache'}",
                size=11, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Container(height=8),
        ft.Text("학습 완료된 RLOG는 서버에 남아 있으므로 안전하게 삭제할 수 있습니다.",
                size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Text("필요 시 [서버에서 다운로드]로 다시 받아올 수 있습니다.",
                size=12, color=ft.Colors.ON_SURFACE_VARIANT),
      ], spacing=4, tight=True),
    )
    def do_cleanup(_e=None):
      page.pop_dialog()
      import shutil
      try:
        shutil.rmtree(cas_dir() / "cloud_cache", ignore_errors=True)
        append_log(f"[cleanup] 캐시 삭제 완료 ({format_bytes(total)})")
        show_toast(f"{segs}개 세그먼트 · {format_bytes(total)} 삭제 완료")
      except Exception as e:
        append_log(f"[cleanup] ERROR: {e}")
        show_toast(f"삭제 실패: {e}", error=True)
      refresh_data_status()
    cleanup_dlg.actions = [
      ft.TextButton("취소", on_click=lambda _e: page.pop_dialog()),
      ft.FilledButton("삭제", on_click=do_cleanup),
    ]
    page.show_dialog(cleanup_dlg)

  # ── Train history ──
  def history_clicked(_event=None):
    runs_path = cas_dir() / "train_runs.json"
    if not runs_path.exists():
      show_toast("아직 학습 이력이 없습니다")
      return
    try:
      data = json.loads(runs_path.read_text(encoding="utf-8"))
      runs = list(data.get("runs", []) or [])
    except Exception as e:
      show_toast(f"이력 읽기 실패: {e}", error=True)
      return
    if not runs:
      show_toast("이력이 비어있습니다")
      return
    runs.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    items = []
    for r in runs[:50]:
      when = str(r.get("created_at", ""))[:16].replace("T", " ")
      hours = float(r.get("trained_on_hours", 0) or 0)
      items.append(ft.ListTile(
        leading=ft.Icon(ft.Icons.MODEL_TRAINING_ROUNDED, color=ft.Colors.PRIMARY),
        title=ft.Text(f"{r.get('car_key','?')} · {r.get('kind','?')}"),
        subtitle=ft.Text(f"{when} · {hours:.2f}h"),
        dense=True,
      ))
    hist_dlg = ft.AlertDialog(
      modal=True,
      title=ft.Text(f"학습 이력 (총 {len(runs)}회, 최근 {len(items)}개)",
                    size=16, weight=ft.FontWeight.W_600),
      content=ft.Container(
        width=460, height=460,
        content=ft.ListView(items, spacing=2),
      ),
    )
    hist_dlg.actions = [ft.TextButton("닫기", on_click=lambda _e: page.pop_dialog())]
    page.show_dialog(hist_dlg)

  # ── Wire events ──
  vehicle_menu.on_change   = vehicle_changed
  refresh_button.on_click  = refresh_clicked
  settings_button.on_click = settings_clicked
  primary_button.on_click  = train_clicked
  apply_button.on_click    = apply_clicked
  stop_button.on_click     = stop_clicked
  download_button.on_click   = download_clicked
  cleanup_button.on_click    = cleanup_clicked
  history_button.on_click    = history_clicked
  open_rlog_button.on_click  = open_rlog_clicked
  train_all_button.on_click  = train_all_clicked

  # ── App chrome ──
  page.appbar = ft.AppBar(
    title=ft.Text("CAS Learner"),
    center_title=False,
    bgcolor=ft.Colors.SURFACE,
    elevation=0,
    actions=[refresh_button, settings_button],
  )

  page.add(
    ft.SafeArea(
      ft.Container(
        padding=ft.Padding.only(left=20, right=20, bottom=20),
        content=ft.Column(
          [
            ft.Card(
              elevation=0,
              bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
              content=ft.Container(
                padding=24,
                content=ft.Column(
                  [
                    ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=32, color=ft.Colors.PRIMARY),
                    headline,
                    assist,
                    ft.Container(height=8),
                    status,
                    progress,
                    ft.Container(height=8),
                    primary_button,
                    train_all_button,
                    ft.Row(
                      [apply_button, stop_button],
                      alignment=ft.MainAxisAlignment.END,
                      spacing=8,
                    ),
                  ],
                  spacing=8,
                  tight=True,
                ),
              ),
            ),
            vehicle_menu,
            detail_tile,
            log_container,
          ],
          spacing=16,
        ),
      )
    )
  )

  refresh_data_status()
  refresh_clicked()
  # GPU/PyTorch probe runs in background — can take several seconds (esp. WSL).
  threading.Thread(target=detect_gpu_async, daemon=True).start()


if __name__ == "__main__":
  # Flet ≥ 0.80 uses run(); app(target=...) is deprecated.
  ft.run(main)
