// ============================================================
//  mod_toast.h  —  toast notification system
// ============================================================
#pragma once
#include "imgui/imgui.h"

void PushToast(const char* msg,
               ImVec4 col = {0.25f,1.f,0.45f,1.f},
               float dur  = 3.5f);

void DrawToasts(float dt, int screenW, int screenH);
