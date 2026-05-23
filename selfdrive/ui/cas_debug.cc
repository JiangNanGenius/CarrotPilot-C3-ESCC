// CAS (Carrot Adaptive Steering) debug HUD overlay — self-contained.
//
// Modes (controlled by Params "CASDebug"):
//   1  → user-friendly compact panel (default for drivers)
//   2+ → developer text dump (raw alpha/delta/raw/z values)
//
// Reads from cereal controlsState.lateralControlState (torque or angle),
// pulling the 39-float casLog appended by selfdrive/carrot/cas/runtime.py.
// All state is local to this file (function statics + anonymous namespace).

#include "selfdrive/ui/cas_debug.h"
#include "selfdrive/ui/carrot.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>

#include <QString>

#include "cereal/messaging/messaging.h"
#include "common/params.h"

// carrot.cc defines BOLD/COLOR_* as file-scope macros (not in carrot.h),
// and ui_draw_text_vg is static there too. To keep this file self-contained
// (deletable as a unit), redeclare them locally with internal linkage.
#ifndef BOLD
#define BOLD "KaiGenGothicKR-Bold"
#endif
#ifndef COLOR_WHITE
#define COLOR_WHITE nvgRGBA(255, 255, 255, 255)
#endif
#ifndef COLOR_BLACK
#define COLOR_BLACK nvgRGBA(0, 0, 0, 255)
#endif

namespace {

// File-local copy of carrot.cc::ui_draw_text_vg (which is `static` there and
// thus invisible to other TUs). Keeping a private copy lets us drop cas_debug.cc
// without modifying carrot.cc.
void ui_draw_text_vg(NVGcontext* vg, float x, float y, const char* string,
                     float size, NVGcolor color, const char* font_name,
                     float borderWidth = 3.0, float shadowOffset = 0.0,
                     NVGcolor borderColor = COLOR_BLACK,
                     NVGcolor shadowColor = COLOR_BLACK) {
  nvgFontFace(vg, font_name);
  nvgFontSize(vg, size);
  if (borderWidth > 0.0) {
    nvgFillColor(vg, borderColor);
    for (int i = 0; i < 360; i += 45) {
      float angle = i * NVG_PI / 180.0f;
      float offsetX = borderWidth * cos(angle);
      float offsetY = borderWidth * sin(angle);
      nvgText(vg, x + offsetX, y + offsetY, string, NULL);
    }
  }
  if (shadowOffset != 0.0) {
    nvgFillColor(vg, shadowColor);
    nvgText(vg, x + shadowOffset, y + shadowOffset, string, NULL);
  }
  nvgFillColor(vg, color);
  nvgText(vg, x, y, string, NULL);
}

// ───── Layout ─────────────────────────────────────────────────────
// All visual tuning lives here. Adjust these, not inline numbers.
constexpr int   WBOX_W           = 740;   // panel width (was 900)
constexpr int   WBOX_H_FULL      = 780;   // panel height when model loaded (was 1120)
constexpr int   WBOX_H_COMPACT   = 500;
constexpr int   WBOX_H_NOMODEL   = 180;
constexpr int   MARGIN           = 24;
constexpr int   INNER_PAD        = 24;
constexpr float FONT_SIZE        = 38.0f; // was 44
constexpr int   LINE_H           = 52;    // was 64
constexpr int   SEC_SPACING      = 16;    // was 28
constexpr int   PANEL_RADIUS     = 22;
constexpr int   PANEL_STROKE     = 2;
constexpr int   GAUGE_H          = 16;

// ───── Transparency ──────────────────────────────────────────────
constexpr int BG_ALPHA     = 180;  // 71% opaque (was 88%)
constexpr int STROKE_ALPHA = 160;

// ───── Colors ────────────────────────────────────────────────────
const NVGcolor C_WHITE  = COLOR_WHITE;
const NVGcolor C_GREEN  = nvgRGBA(120, 220, 120, 255);
const NVGcolor C_ORANGE = nvgRGBA(255, 170,  60, 255);
const NVGcolor C_RED    = nvgRGBA(230,  80,  80, 255);
const NVGcolor C_GRAY   = nvgRGBA(160, 160, 160, 255);
const NVGcolor C_BG     = nvgRGBA( 10,  10,  14, BG_ALPHA);

std::string format_cas_hours(const QString& cas_hours) {
  bool ok = false;
  const double hours = cas_hours.toDouble(&ok);
  if (!ok || hours <= 0.0) return "";
  return std::to_string((int)std::round(hours)) + "h";
}

// Outline color follows panel status — gives peripheral cue.
//   0=idle/gray, 1=active+good/green, 2=caution/orange, 3=out-of-dist/red.
NVGcolor stroke_for_status(int status) {
  switch (status) {
    case 1:  return nvgRGBA(120, 220, 120, STROKE_ALPHA);
    case 2:  return nvgRGBA(255, 170,  60, STROKE_ALPHA);
    case 3:  return nvgRGBA(230,  80,  80, STROKE_ALPHA);
    default: return nvgRGBA( 90,  90, 100, STROKE_ALPHA);
  }
}

int evaluate_status(float alpha, float z, float centering, float accuracy, float intervention_rate) {
  if (alpha < 0.05f) return 0;          // 대기 중
  if (z >= 3.0f)     return 3;          // 분포 밖
  if (accuracy > 0.0f && accuracy < 50.0f) return 2;
  if (centering < 40.0f || intervention_rate > 1.0f) return 2;
  return 1;                              // 작동 중/매우 좋음
}

}  // anonymous namespace


void ui_draw_cas_overlay(UIState* s) {
  Params params;
  const int cas_debug_val = params.getInt("CASDebug");
  const bool cas_enabled = params.getInt("CAS") > 0;
  if (cas_debug_val <= 0) return;

  // s->vg is the inner camera framebuffer (matches existing call site in
  // carrot.cc::ui_draw). s->vg_border is mostly occluded by AnnotatedCameraWidget.
  NVGcontext* vg = s->vg;
  SubMaster& sm  = *(s->sm);
  if (!sm.alive("controlsState")) return;

  const int w = s->fb_w;
  const int h = s->fb_h;

  QString cas_model = QString::fromStdString(params.get("CASModelName"));

  // ───── Read casLog from whichever lateral state is active ────────
  auto lat = sm["controlsState"].getControlsState().getLateralControlState();
  capnp::List<float>::Reader cas_log;
  const char* kind_str = "—";
  bool has_log = false;
  switch (lat.which()) {
    case cereal::ControlsState::LateralControlState::TORQUE_STATE: {
      auto t = lat.getTorqueState();
      cas_log = t.getCasLog();
      kind_str = "torque";
      has_log = (cas_log.size() >= 19);
      break;
    }
    case cereal::ControlsState::LateralControlState::ANGLE_STATE: {
      auto a = lat.getAngleState();
      cas_log = a.getCasLog();
      kind_str = "angle";
      has_log = (cas_log.size() >= 19);
      break;
    }
    default:
      break;
  }
  (void)kind_str;  // suppressed in compact mode header

  const int x0 = w - WBOX_W - MARGIN;
  char buf[160];

  // CAS debug is useful even when CAS itself is off: show why nothing is active.
  if (!cas_enabled) {
    int y0 = (h - WBOX_H_NOMODEL) / 2;
    NVGcolor stroke = stroke_for_status(0);
    ui_fill_rect(vg, { x0, y0, WBOX_W, WBOX_H_NOMODEL }, C_BG, PANEL_RADIUS, PANEL_STROKE, &stroke);
    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, x0 + INNER_PAD, y0 + 22, "CAS", FONT_SIZE, C_GRAY, BOLD);
    ui_draw_text_vg(vg, x0 + INNER_PAD, y0 + 22 + LINE_H, "설정에서 CAS가 꺼져 있음",
                    FONT_SIZE - 8, C_GRAY, BOLD);
    return;
  }

  // ───── No model → small placeholder panel ────────────────────────
  if (cas_model.length() == 0) {
    int y0 = (h - WBOX_H_NOMODEL) / 2;
    NVGcolor stroke = stroke_for_status(0);
    ui_fill_rect(vg, { x0, y0, WBOX_W, WBOX_H_NOMODEL }, C_BG, PANEL_RADIUS, PANEL_STROKE, &stroke);
    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, x0 + INNER_PAD, y0 + 22, "CAS", FONT_SIZE, C_GRAY, BOLD);
    ui_draw_text_vg(vg, x0 + INNER_PAD, y0 + 22 + LINE_H, "이 차량용 모델 없음",
                    FONT_SIZE - 8, C_GRAY, BOLD);
    return;
  }

  // ───── Static cache so values survive controlsState pauses ───────
  static float last_raw_delta       = 0.0f;
  static float last_applied_delta   = 0.0f;
  static float last_alpha           = 0.0f;
  static float last_z               = 0.0f;
  static float last_offset_now      = 0.0f;
  static float last_offset_5s       = 0.0f;
  static float last_offset_60s      = 0.0f;
  static float last_centering_score = 0.0f;
  static int   last_interventions   = 0;
  static float last_sec_since       = -1.0f;
  static int   last_strong          = 0;
  static int   last_weak            = 0;
  static float last_accuracy        = 0.0f;
  static float last_session_s       = 0.0f;
  static float last_dist_in         = 0.0f;
  static int   last_pattern         = 0;

  if (has_log) {
    const int n = cas_log.size();
    last_raw_delta       = cas_log[n - 19];
    last_applied_delta   = cas_log[n - 18];
    last_alpha           = cas_log[n - 17];
    last_z               = cas_log[n - 16];
    last_offset_now      = cas_log[n - 15];
    last_offset_5s       = cas_log[n - 14];
    last_offset_60s      = cas_log[n - 13];
    last_centering_score = cas_log[n - 11];
    last_interventions   = (int)cas_log[n - 10];
    last_sec_since       = cas_log[n - 9];
    last_strong          = (int)cas_log[n - 8];
    last_weak            = (int)cas_log[n - 7];
    last_accuracy        = cas_log[n - 4];
    last_session_s       = cas_log[n - 3];
    last_dist_in         = cas_log[n - 2];
    last_pattern         = (int)cas_log[n - 1];
  }
  const float raw_delta       = last_raw_delta;
  const float applied_delta   = last_applied_delta;
  const float alpha           = last_alpha;
  const float z               = last_z;
  const float offset_now      = last_offset_now;
  const float offset_5s       = last_offset_5s;
  const float offset_60s      = last_offset_60s;
  const float centering_score = last_centering_score;
  const int   interventions   = last_interventions;
  const float sec_since       = last_sec_since;
  const int   strong_cnt      = last_strong;
  const int   weak_cnt        = last_weak;
  const float accuracy_pct    = last_accuracy;
  const float session_seconds = last_session_s;
  const float dist_in_pct     = last_dist_in;
  const int   lane_pattern    = last_pattern;
  (void)raw_delta; (void)interventions;  // used only in dev mode

  float v_ego_kmh = 0.0f;
  if (sm.alive("carState")) {
    v_ego_kmh = sm["carState"].getCarState().getVEgo() * 3.6f;
  }
  // Casper EV defaults (7..30 m/s ≈ 26..108 km/h); real gate uses model meta.
  const float vego_min_kmh = 7.0f * 3.6f;
  const float vego_max_kmh = 30.0f * 3.6f;

  const float intervention_rate = (session_seconds > 30.0f)
      ? (interventions * 60.0f / session_seconds) : 0.0f;
  const int status = evaluate_status(alpha, z, centering_score, accuracy_pct, intervention_rate);
  NVGcolor stroke = stroke_for_status(status);

  const int panel_h = (cas_debug_val == 1) ? WBOX_H_COMPACT : WBOX_H_FULL;
  int y0 = (h - panel_h) / 2;
  ui_fill_rect(vg, { x0, y0, WBOX_W, panel_h }, C_BG, PANEL_RADIUS, PANEL_STROKE, &stroke);

  const int label_x  = x0 + INNER_PAD;
  const int val_x    = x0 + WBOX_W - INNER_PAD;
  const int gauge_left = x0 + INNER_PAD;
  const int gauge_w    = WBOX_W - 2 * INNER_PAD;
  const int gauge_cx   = x0 + WBOX_W / 2;
  int y = y0 + 20;

  // ───── Header (single line) ──────────────────────────────────────
  //   CAS · CASPER EV · 6h
  QString cas_hours = QString::fromStdString(params.get("CASModelHours"));
  const std::string cas_hours_label = format_cas_hours(cas_hours);
  std::string header = "CAS · " + cas_model.toStdString();
  if (!cas_hours_label.empty()) {
    header += " · " + cas_hours_label;
  }
  nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
  ui_draw_text_vg(vg, label_x, y, header.c_str(), FONT_SIZE - 2, C_WHITE, BOLD);
  y += LINE_H - 4 + SEC_SPACING;

  if (cas_debug_val == 1) {
    // ============================================================
    // Mode 1: 운전자 친화 초간단 패널
    // ============================================================
    auto draw_progress_bar = [&](float val_norm, NVGcolor color, int h_) {
      int gy = y;
      ui_fill_rect(vg, {gauge_left, gy, gauge_w, h_}, nvgRGBA(60, 60, 60, 255), 6);
      float n = std::max(0.0f, std::min(1.0f, val_norm));
      int fw = (int)(n * gauge_w);
      if (fw > 0) ui_fill_rect(vg, {gauge_left, gy, fw, h_}, color, 6);
      y += h_ + 6;
    };
    auto draw_metric = [&](const char* label, const char* value, NVGcolor color) {
      nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
      ui_draw_text_vg(vg, label_x, y, label, FONT_SIZE - 10, C_GRAY, BOLD);
      nvgTextAlign(vg, NVG_ALIGN_RIGHT | NVG_ALIGN_TOP);
      ui_draw_text_vg(vg, val_x, y, value, FONT_SIZE - 8, color, BOLD);
      y += LINE_H - 10;
    };

    // A short "why" is more useful on-road than a wall of raw numbers.
    const char* eval_text = "CAS 대기 중";
    NVGcolor eval_color   = C_GRAY;
    const char* reason_text = "보정 조건을 기다리는 중";
    if (!has_log) {
      eval_text = "CAS 로그 없음";                 eval_color = C_ORANGE;
      reason_text = "컨트롤 상태가 아직 들어오지 않음";
    } else if (alpha < 0.05f && z >= 3.0f) {
      eval_text = "CAS 보류";                      eval_color = C_RED;
      reason_text = "학습 범위 밖 입력";
    } else if (alpha < 0.05f && (v_ego_kmh < vego_min_kmh || v_ego_kmh > vego_max_kmh)) {
      eval_text = "CAS 보류";                      eval_color = C_ORANGE;
      reason_text = "속도 범위 밖";
    } else if (alpha < 0.05f) {
      eval_text = "CAS 대기 중";                   eval_color = C_GRAY;
      reason_text = "보정량이 작거나 게이트 대기";
    } else if (z >= 3.0f) {
      eval_text = "CAS 약하게 보정";               eval_color = C_ORANGE;
      reason_text = "익숙하지 않은 구간";
    } else if (accuracy_pct > 0.0f && accuracy_pct < 50.0f) {
      eval_text = "CAS 확인 필요";                 eval_color = C_ORANGE;
      reason_text = "보정 방향 정확도 낮음";
    } else if (centering_score >= 75.0f && intervention_rate <= 0.3f) {
      eval_text = "CAS 작동 좋음";                 eval_color = C_GREEN;
      reason_text = "중앙 유지가 안정적";
    } else if (centering_score >= 60.0f) {
      eval_text = "CAS 작동 중";                   eval_color = C_WHITE;
      reason_text = "보정 적용 중";
    } else {
      eval_text = "CAS 학습 더 필요";              eval_color = C_ORANGE;
      reason_text = "중앙 유지 점수 낮음";
    }

    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, label_x, y, eval_text, FONT_SIZE + 2, eval_color, BOLD);
    y += LINE_H - 2;
    ui_draw_text_vg(vg, label_x, y, reason_text, FONT_SIZE - 14, C_GRAY, BOLD);
    y += LINE_H - 14 + SEC_SPACING;

    // ─── Applied correction ─────────────────────────────────────
    NVGcolor inv_c = alpha < 0.05f ? C_GRAY
                    : (alpha < 0.4f ? C_WHITE
                    : (alpha < 0.8f ? C_GREEN : nvgRGBA(255, 230, 60, 255)));
    snprintf(buf, sizeof(buf), "%.0f%%  %+0.3f Nm", alpha * 100.0f, applied_delta);
    draw_metric("적용", buf, inv_c);
    draw_progress_bar(alpha, inv_c, GAUGE_H);

    NVGcolor acc_c = accuracy_pct >= 70.0f ? C_GREEN
                    : (accuracy_pct >= 50.0f ? C_WHITE : C_ORANGE);
    snprintf(buf, sizeof(buf), "%.0f%%", std::max(0.0f, accuracy_pct));
    draw_metric("방향 일치", buf, acc_c);

    NVGcolor score_c = centering_score >= 80.0f ? C_GREEN
                      : (centering_score >= 50.0f ? C_WHITE : C_ORANGE);
    snprintf(buf, sizeof(buf), "%.0f점", centering_score);
    draw_metric("중앙 유지", buf, score_c);
    draw_progress_bar(centering_score / 100.0f, score_c, GAUGE_H);
    y += SEC_SPACING / 2;

    // ─── Lane position ──────────────────────────────────────────
    {
      int gy = y;
      int track_h = 24;
      ui_fill_rect(vg, {gauge_left, gy, gauge_w, track_h}, nvgRGBA(40, 40, 45, 255), 8);
      ui_fill_rect(vg, {gauge_cx - 1, gy - 4, 2, track_h + 8}, C_GRAY, 0);
      float frac = std::max(-1.0f, std::min(1.0f, offset_now / 0.10f));
      int dot_x = gauge_cx + (int)(frac * (gauge_w / 2 - 14));
      int dot_y = gy + track_h / 2;
      NVGcolor dot_c = std::abs(offset_now) < 0.03f ? C_GREEN : C_ORANGE;
      ui_fill_rect(vg, {dot_x - 9, dot_y - 9, 18, 18}, dot_c, 9);
      y += track_h + 6;
    }
    snprintf(buf, sizeof(buf), "지금 %+.0fcm · 5초 %+.0fcm · 1분 %+.0fcm",
             offset_now * 100.0f, offset_5s * 100.0f, offset_60s * 100.0f);
    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, label_x, y, buf, FONT_SIZE - 14, C_WHITE, BOLD);
    y += LINE_H - 14;

    const char* pattern_txt = "안정";
    NVGcolor pattern_c = C_GREEN;
    switch (lane_pattern) {
      case 1: pattern_txt = "계속 왼쪽으로 치우침";   pattern_c = C_ORANGE; break;
      case 2: pattern_txt = "계속 오른쪽으로 치우침"; pattern_c = C_ORANGE; break;
      case 3: pattern_txt = "좌우로 흔들림";          pattern_c = C_ORANGE; break;
      default: pattern_txt = "안정";                  pattern_c = C_GREEN;  break;
    }
    snprintf(buf, sizeof(buf), "%s", pattern_txt);
    draw_metric("차선 패턴", buf, pattern_c);

    int run_min = (int)(session_seconds / 60.0f);
    NVGcolor dist_c = dist_in_pct >= 80.0f ? C_GREEN : C_ORANGE;
    snprintf(buf, sizeof(buf), "%.0f km/h · 익숙 %.0f%% · %d분",
             v_ego_kmh, dist_in_pct, run_min);
    draw_metric("주행 조건", buf, dist_c);

  } else {
    // ============================================================
    // Mode 2: 개발자 텍스트 (alpha/delta/raw/z 등 원시값)
    // ============================================================
    auto draw_line = [&](const char* label, const char* value, NVGcolor color) {
      nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
      ui_draw_text_vg(vg, label_x, y, label, FONT_SIZE - 4, color, BOLD);
      nvgTextAlign(vg, NVG_ALIGN_RIGHT | NVG_ALIGN_TOP);
      ui_draw_text_vg(vg, val_x, y, value, FONT_SIZE - 4, color, BOLD);
      y += LINE_H - 8;
    };
    auto draw_section_dev = [&](const char* label) {
      nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
      ui_draw_text_vg(vg, label_x, y, label, FONT_SIZE - 8, C_GREEN, BOLD);
      y += LINE_H - 12;
    };

    draw_section_dev("현재 상태");
    snprintf(buf, sizeof(buf), "%.3f", alpha);
    draw_line("  alpha", buf, alpha > 0.01f ? C_GREEN : C_GRAY);
    snprintf(buf, sizeof(buf), "%+.3f", applied_delta);
    draw_line("  delta", buf, applied_delta != 0.0f ? C_WHITE : C_GRAY);
    snprintf(buf, sizeof(buf), "%+.3f", raw_delta);
    draw_line("  raw", buf, C_GRAY);
    snprintf(buf, sizeof(buf), "%.2f", z);
    draw_line("  z", buf, z >= 3.0f ? C_RED : (z >= 2.0f ? C_ORANGE : C_WHITE));
    y += SEC_SPACING;

    draw_section_dev("중앙 유지");
    snprintf(buf, sizeof(buf), "%.0f", centering_score);
    NVGcolor score_c = centering_score >= 80.0f ? C_GREEN
                       : (centering_score >= 50.0f ? C_WHITE : C_ORANGE);
    draw_line("  점수", buf, score_c);
    snprintf(buf, sizeof(buf), "%+.3f m", offset_now);
    draw_line("  현재", buf, C_WHITE);
    snprintf(buf, sizeof(buf), "%+.3f m", offset_5s);
    draw_line("  5초", buf, C_WHITE);
    snprintf(buf, sizeof(buf), "%+.3f m", offset_60s);
    draw_line("  60초", buf, C_WHITE);
    y += SEC_SPACING;

    draw_section_dev("운전자 개입");
    snprintf(buf, sizeof(buf), "%d (강 %d / 약 %d)", interventions, strong_cnt, weak_cnt);
    draw_line("  횟수", buf, interventions == 0 ? C_GREEN : C_WHITE);
    if (sec_since < 0.0f) {
      draw_line("  최근", "—", C_GRAY);
    } else if (sec_since < 60.0f) {
      snprintf(buf, sizeof(buf), "%.0f초 전", sec_since);
      draw_line("  최근", buf, sec_since < 10.0f ? C_RED : C_ORANGE);
    } else {
      snprintf(buf, sizeof(buf), "%.0f분 전", sec_since / 60.0f);
      draw_line("  최근", buf, C_WHITE);
    }
  }
}
