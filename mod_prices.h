// ============================================================
//  mod_prices.h
// ============================================================
#pragma once
#include "app_state.h"
#include "imgui/imgui.h"

ImVec4 FlashColor(const Tick& t);
void   PriceCell(const Tick& t, int dec, bool isBid, bool isAsk, float dt);
void   ExchangeSection(
           const char* name, const char* url,
           ImVec4 accent, ImU32 accentU32,
           const Tick& ta, const char* labelA, int decA,
           const Tick& tb, const char* labelB, int decB,
           const Tick& tc, const char* labelC, int decC,
           float dt);

void DrawPricesTab(const MarketData& md, float dt);
