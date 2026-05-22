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
#include "common/timing.h"

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
  if (params.getInt("CAS") <= 0 || cas_debug_val <= 0) return;

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
      has_log = (cas_log.size() >= 11);
      break;
    }
    case cereal::ControlsState::LateralControlState::ANGLE_STATE: {
      auto a = lat.getAngleState();
      cas_log = a.getCasLog();
      kind_str = "angle";
      has_log = (cas_log.size() >= 11);
      break;
    }
    default:
      break;
  }
  (void)kind_str;  // suppressed in compact mode header

  const int x0 = w - WBOX_W - MARGIN;
  char buf[160];

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
  static float last_sec_strong      = -1.0f;
  static float last_sec_weak        = -1.0f;
  static float last_accuracy        = 0.0f;
  static float last_session_s       = 0.0f;
  static float last_dist_in         = 0.0f;
  static int   last_pattern         = 0;
  static float trail[30]            = {0};
  static int   trail_head           = 0;
  static double trail_last_t        = 0.0;

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
    last_sec_strong      = cas_log[n - 6];
    last_sec_weak        = cas_log[n - 5];
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
  const float sec_since_strong = last_sec_strong;
  const float sec_since_weak  = last_sec_weak;
  const float accuracy_pct    = last_accuracy;
  const float session_seconds = last_session_s;
  const float dist_in_pct     = last_dist_in;
  const int   lane_pattern    = last_pattern;
  (void)raw_delta; (void)interventions;  // used only in dev mode

  // 1-Hz downsampled trail of offset_now (last 30 s).
  double now_t = nanos_since_boot() / 1e9;
  if (now_t - trail_last_t >= 1.0) {
    trail_head = (trail_head + 1) % 30;
    trail[trail_head] = offset_now;
    trail_last_t = now_t;
  }

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

  int y0 = (h - WBOX_H_FULL) / 2;
  ui_fill_rect(vg, { x0, y0, WBOX_W, WBOX_H_FULL }, C_BG, PANEL_RADIUS, PANEL_STROKE, &stroke);

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
    // Mode 1: 운전자 친화 컴팩트 패널
    // ============================================================
    auto draw_section = [&](const char* label) {
      nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
      ui_draw_text_vg(vg, label_x, y, label, FONT_SIZE - 8, C_GREEN, BOLD);
      y += LINE_H - 8;
    };
    auto draw_progress_bar = [&](float val_norm, NVGcolor color, int h_) {
      int gy = y;
      ui_fill_rect(vg, {gauge_left, gy, gauge_w, h_}, nvgRGBA(60, 60, 60, 255), 6);
      float n = std::max(0.0f, std::min(1.0f, val_norm));
      int fw = (int)(n * gauge_w);
      if (fw > 0) ui_fill_rect(vg, {gauge_left, gy, fw, h_}, color, 6);
      y += h_ + 6;
    };

    // ─── 상태 한 줄 평가 ────────────────────────────────────────
    const char* eval_text = "● CAS 대기 중";
    NVGcolor eval_color   = C_GRAY;
    if (alpha < 0.05f) {
      eval_text = "● CAS 대기 중";                 eval_color = C_GRAY;
    } else if (z >= 3.0f) {
      eval_text = "● 익숙하지 않은 상황";          eval_color = C_RED;
    } else if (accuracy_pct > 0.0f && accuracy_pct < 50.0f) {
      eval_text = "● 주의 — 보정 방향 불일치";    eval_color = C_ORANGE;
    } else if (centering_score >= 80.0f && intervention_rate <= 0.2f && accuracy_pct >= 70.0f) {
      eval_text = "●● CAS 매우 잘 작동";          eval_color = C_GREEN;
    } else if (centering_score >= 60.0f) {
      eval_text = "● CAS 작동 중";                 eval_color = C_WHITE;
    } else if (centering_score < 40.0f || intervention_rate > 1.0f) {
      eval_text = "● 주의 — 학습이 더 필요함";    eval_color = C_ORANGE;
    } else {
      eval_text = "● CAS 작동 중";                 eval_color = C_WHITE;
    }
    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, label_x, y, eval_text, FONT_SIZE - 2, eval_color, BOLD);
    y += LINE_H - 4;
    snprintf(buf, sizeof(buf),
             "점수 %.0f · 정확도 %.0f%% · %s",
             centering_score,
             std::max(0.0f, accuracy_pct),
             (dist_in_pct >= 80.0f ? "익숙" : "낯섦"));
    ui_draw_text_vg(vg, label_x, y, buf, FONT_SIZE - 14, C_GRAY, BOLD);
    y += LINE_H - 16 + SEC_SPACING;

    // ─── CAS 개입 정도 (보정량 + 정확도 통합) ────────────────────
    draw_section("CAS 개입 정도");
    NVGcolor inv_c = alpha < 0.05f ? C_GRAY
                    : (alpha < 0.4f ? C_WHITE
                    : (alpha < 0.8f ? C_GREEN : nvgRGBA(255, 230, 60, 255)));
    nvgTextAlign(vg, NVG_ALIGN_RIGHT | NVG_ALIGN_TOP);
    snprintf(buf, sizeof(buf), "%.0f %%", alpha * 100.0f);
    ui_draw_text_vg(vg, val_x, y - (LINE_H - 8), buf, FONT_SIZE - 6, inv_c, BOLD);
    draw_progress_bar(alpha, inv_c, GAUGE_H);
    NVGcolor acc_c = accuracy_pct >= 70.0f ? C_GREEN
                    : (accuracy_pct >= 50.0f ? C_WHITE : C_ORANGE);
    snprintf(buf, sizeof(buf), "보정 %+.3f Nm  →  정확도 %.0f%%",
             applied_delta, accuracy_pct);
    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, label_x, y, buf, FONT_SIZE - 12, acc_c, BOLD);
    y += LINE_H - 14 + SEC_SPACING;

    // ─── 속도 + 학습 범위 (텍스트만) ─────────────────────────────
    NVGcolor speed_c = dist_in_pct >= 80.0f ? C_GREEN : C_ORANGE;
    snprintf(buf, sizeof(buf), "%.0f km/h · 학습 범위 %s (%.0f~%.0f)",
             v_ego_kmh,
             (v_ego_kmh >= vego_min_kmh && v_ego_kmh <= vego_max_kmh) ? "안" : "밖",
             vego_min_kmh, vego_max_kmh);
    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, label_x, y, buf, FONT_SIZE - 10, speed_c, BOLD);
    y += LINE_H - 12 + SEC_SPACING;

    // ─── 중앙 유지 점수 ─────────────────────────────────────────
    draw_section("중앙 유지 점수");
    NVGcolor score_c = centering_score >= 80.0f ? C_GREEN
                      : (centering_score >= 50.0f ? C_WHITE : C_ORANGE);
    nvgTextAlign(vg, NVG_ALIGN_RIGHT | NVG_ALIGN_TOP);
    const char* score_tag =
        centering_score >= 90.0f ? "매우 좋음" :
        centering_score >= 75.0f ? "좋음" :
        centering_score >= 50.0f ? "보통" :
        centering_score >= 25.0f ? "주의" : "나쁨";
    snprintf(buf, sizeof(buf), "%.0f  %s", centering_score, score_tag);
    ui_draw_text_vg(vg, val_x, y, buf, FONT_SIZE - 6, score_c, BOLD);
    draw_progress_bar(centering_score / 100.0f, score_c, GAUGE_H);
    y += SEC_SPACING;

    // ─── 차선 안 위치 (가로 막대 + 도트) ──────────────────────────
    draw_section("차선 안 위치");
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
    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, gauge_left, y, "-10cm", FONT_SIZE - 18, C_GRAY, BOLD);
    nvgTextAlign(vg, NVG_ALIGN_CENTER | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, gauge_cx, y, "0", FONT_SIZE - 18, C_GRAY, BOLD);
    nvgTextAlign(vg, NVG_ALIGN_RIGHT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, gauge_left + gauge_w, y, "+10cm", FONT_SIZE - 18, C_GRAY, BOLD);
    y += LINE_H - 18 + 6;

    // ─── 추세 (30초) ────────────────────────────────────────────
    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, label_x, y, "추세 (30초)", FONT_SIZE - 12, C_WHITE, BOLD);
    y += LINE_H - 16;
    {
      int gy = y;
      int track_h = 20;
      ui_fill_rect(vg, {gauge_left, gy, gauge_w, track_h}, nvgRGBA(30, 30, 35, 255), 6);
      ui_fill_rect(vg, {gauge_cx - 1, gy, 2, track_h}, nvgRGBA(80, 80, 90, 200), 0);
      for (int i = 0; i < 30; i++) {
        int slot = (trail_head + 30 - i) % 30;
        float v = trail[slot];
        float frac = std::max(-1.0f, std::min(1.0f, v / 0.10f));
        int dxv = gauge_cx + (int)(frac * (gauge_w / 2 - 12));
        int dy  = gy + track_h / 2;
        int alpha_dot = std::max(60, 255 - i * 6);
        NVGcolor dotc = nvgRGBA(180, 220, 255, alpha_dot);
        ui_fill_rect(vg, {dxv - 3, dy - 3, 6, 6}, dotc, 3);
      }
      y += track_h + 4;
    }
    snprintf(buf, sizeof(buf), "지금 %+.0fcm · 5초 %+.0fcm · 1분 %+.0fcm",
             offset_now * 100.0f, offset_5s * 100.0f, offset_60s * 100.0f);
    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, label_x, y, buf, FONT_SIZE - 14, C_WHITE, BOLD);
    y += LINE_H - 16;

    const char* pattern_txt = "안정";
    NVGcolor pattern_c = C_GREEN;
    switch (lane_pattern) {
      case 1: pattern_txt = "계속 왼쪽으로 치우침";   pattern_c = C_ORANGE; break;
      case 2: pattern_txt = "계속 오른쪽으로 치우침"; pattern_c = C_ORANGE; break;
      case 3: pattern_txt = "좌우로 흔들림";          pattern_c = C_ORANGE; break;
      default: pattern_txt = "안정";                  pattern_c = C_GREEN;  break;
    }
    snprintf(buf, sizeof(buf), "판정: %s ●", pattern_txt);
    ui_draw_text_vg(vg, label_x, y, buf, FONT_SIZE - 10, pattern_c, BOLD);
    y += LINE_H - 12 + SEC_SPACING;

    // ─── 오늘 개입 (강/약 한 줄 통합) ────────────────────────────
    draw_section("오늘 개입");
    auto fmt_sec_since = [&](float ss, char* dest, size_t dest_n) {
      if (ss < 0.0f) snprintf(dest, dest_n, "—");
      else if (ss < 60.0f) snprintf(dest, dest_n, "%.0f초 전", ss);
      else snprintf(dest, dest_n, "%.0f분 전", ss / 60.0f);
    };
    char last_t[32];
    float last_any = std::max(sec_since_strong, sec_since_weak);
    if (last_any < 0.0f) snprintf(last_t, sizeof(last_t), "—");
    else fmt_sec_since(last_any, last_t, sizeof(last_t));

    snprintf(buf, sizeof(buf), "강한 %d회 · 약한 %d회  (%s)",
             strong_cnt, weak_cnt, last_t);
    NVGcolor any_c = strong_cnt > 0 ? C_ORANGE : C_WHITE;
    nvgTextAlign(vg, NVG_ALIGN_LEFT | NVG_ALIGN_TOP);
    ui_draw_text_vg(vg, label_x, y, buf, FONT_SIZE - 10, any_c, BOLD);
    y += LINE_H - 12;

    // ─── 운행 시간 + 익숙한 구간 (한 줄 통합) ────────────────────
    int run_min = (int)(session_seconds / 60.0f);
    NVGcolor dist_c = dist_in_pct >= 80.0f ? C_GREEN : C_ORANGE;
    snprintf(buf, sizeof(buf), "운행 %d분 · 익숙한 구간 %.0f%%",
             run_min, dist_in_pct);
    ui_draw_text_vg(vg, label_x, y, buf, FONT_SIZE - 12, dist_c, BOLD);

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
