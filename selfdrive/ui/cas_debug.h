#pragma once

// CAS (Carrot Adaptive Steering) debug HUD overlay.
//
// This header and its .cc file are the entire UI surface of CAS in the
// onroad camera view. When CAS is retired:
//   1. Delete selfdrive/ui/cas_debug.{h,cc}
//   2. Remove "cas_debug.cc" from selfdrive/ui/SConscript
//   3. Remove #include + ui_draw_cas_overlay() call in carrot.cc
//   4. Drop the 3-line CASModelName ",CAS" suffix in carrot.cc

struct UIState;

void ui_draw_cas_overlay(UIState* s);
