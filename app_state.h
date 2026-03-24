// ============================================================
//  app_state.h  —  shared state across all modules
//  Include once from main.cpp, extern-declare in modules
// ============================================================
#pragma once

#include "imgui/imgui.h"
#include <mutex>
#include <atomic>

// ─── Fonts (set once in main after rlImGuiSetup) ─────────────
extern ImFont* fntRegular;
extern ImFont* fntMedium;
extern ImFont* fntBold;
extern ImFont* fntLarge;   // 22px — big prices
extern ImFont* fntSmall;   // 11px — labels

// ─── Price tick ──────────────────────────────────────────────
struct Tick {
    double bid=0, ask=0, last=0, prev_last=0;
    float  flash_t  = 0;      // seconds since last change
    bool   flash_up = true;
    bool   ok       = false;
    char   ts[12]   = "--:--:--";
};

// ─── All market data ─────────────────────────────────────────
struct MarketData {
    Tick lcx_lcx,    lcx_btc,    lcx_eth;
    Tick kraken_btc, kraken_eth, kraken_lcx;
    Tick cb_btc,     cb_eth,     cb_lcx;
};

extern MarketData         g_md;
extern std::mutex         g_md_mtx;
extern std::atomic<bool>  g_run;
extern std::atomic<int>   g_fetch_count;

// ─── Screen geometry (set in main) ───────────────────────────
extern int g_sidebarW;   // sidebar pixel width
extern int g_monH;       // monitor height
extern int g_monW;       // monitor width (full)
