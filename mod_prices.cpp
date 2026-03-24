// ============================================================
//  mod_prices.cpp
// ============================================================
#include "mod_prices.h"
#include <math.h>

ImVec4 FlashColor(const Tick& t)
{
    if(t.flash_t<=0 || !t.ok)
        return {0.88f,0.88f,0.92f,1.f};
    float p = t.flash_t / 1.2f;
    if(t.flash_up)
        return {0.88f+0.12f*p, 0.88f+0.12f*p, 0.92f-0.52f*p, 1.f};
    else
        return {0.88f+0.12f*p, 0.88f-0.48f*p, 0.92f-0.72f*p, 1.f};
}

void PriceCell(const Tick& t, int dec, bool isBid, bool isAsk, float dt)
{
    double val = isAsk ? t.ask : (isBid ? t.bid : t.last);
    if(!t.ok || val<=0){ ImGui::TextDisabled("  ---"); return; }

    ImVec4 col;
    if(isBid)      col = {0.25f,0.92f,0.45f,1.f};
    else if(isAsk) col = {1.f,0.38f,0.38f,1.f};
    else           col = FlashColor(t);

    if(dec<=0)      ImGui::TextColored(col,"$%.0f",  val);
    else if(dec==2) ImGui::TextColored(col,"$%.2f",  val);
    else            ImGui::TextColored(col,"$%.5f",  val);
}

void ExchangeSection(
    const char* name, const char* url,
    ImVec4 accent, ImU32 accentU32,
    const Tick& ta, const char* labelA, int decA,
    const Tick& tb, const char* labelB, int decB,
    const Tick& tc, const char* labelC, int decC,
    float dt)
{
    ImVec2 headerPos = ImGui::GetCursorScreenPos();
    ImGui::GetWindowDrawList()->AddRectFilled(
        headerPos, {headerPos.x+3.f, headerPos.y+20.f}, accentU32);
    ImGui::SetCursorPosX(ImGui::GetCursorPosX()+10.f);
    ImGui::PushFont(fntBold);
    ImGui::TextColored(accent, "%s", name);
    ImGui::PopFont();
    ImGui::SameLine();
    ImGui::PushFont(fntSmall);
    ImGui::TextColored({0.30f,0.30f,0.42f,1.f}," %s", url);
    ImGui::PopFont();

    ImGuiTableFlags fl = ImGuiTableFlags_BordersInnerH
                       | ImGuiTableFlags_RowBg
                       | ImGuiTableFlags_SizingStretchProp;
    if(!ImGui::BeginTable(name, 5, fl)) return;

    ImGui::TableSetupColumn("",     0, 0.85f);
    ImGui::TableSetupColumn("BID",  0, 1.30f);
    ImGui::TableSetupColumn("ASK",  0, 1.30f);
    ImGui::TableSetupColumn("LAST", 0, 1.30f);
    ImGui::TableSetupColumn("SPR%", 0, 0.75f);
    ImGui::TableHeadersRow();

    auto Row=[&](const char* label, ImVec4 lc, const Tick& tk, int dec){
        ImGui::TableNextRow();
        ImGui::TableNextColumn();
        ImGui::PushFont(fntMedium);
        ImGui::TextColored(lc, "%s", label);
        ImGui::PopFont();

        ImGui::TableNextColumn(); PriceCell(tk,dec,true,false,dt);
        ImGui::TableNextColumn(); PriceCell(tk,dec,false,true,dt);
        ImGui::TableNextColumn(); PriceCell(tk,dec,false,false,dt);

        if(ImGui::IsItemHovered()){
            ImGui::BeginTooltip();
            ImGui::Text("Exchange: %s", name);
            ImGui::Text("Pair: %s", label);
            ImGui::Text("Updated: %s", tk.ts);
            if(tk.ok && tk.bid>0 && tk.ask>0)
                ImGui::Text("Spread: $%.5f", tk.ask-tk.bid);
            ImGui::EndTooltip();
        }

        ImGui::TableNextColumn();
        if(tk.ok && tk.bid>0 && tk.ask>0){
            float sp=(float)((tk.ask-tk.bid)/tk.bid*100.0);
            ImGui::TextColored({0.40f,0.40f,0.55f,1.f},"%.3f%%",sp);
        } else ImGui::TextDisabled("-");
    };

    Row(labelA, {0.97f,0.72f,0.10f,1.f}, ta, decA);
    Row(labelB, {0.55f,0.60f,1.00f,1.f}, tb, decB);
    Row(labelC, {0.25f,0.85f,1.00f,1.f}, tc, decC);

    ImGui::EndTable();
    ImGui::Spacing();
}

void DrawPricesTab(const MarketData& md, float dt)
{
    ImVec4 aLCX    = {0.20f,0.55f,1.00f,1.f};
    ImVec4 aKraken = {0.60f,0.35f,1.00f,1.f};
    ImVec4 aCB     = {0.15f,0.80f,0.58f,1.f};
    ImU32  uLCX    = IM_COL32(51,140,255,255);
    ImU32  uKraken = IM_COL32(153,90,255,255);
    ImU32  uCB     = IM_COL32(38,204,148,255);

    ImGui::BeginChild("##pc", {0,0}, false, ImGuiWindowFlags_NoScrollbar);

    ExchangeSection("LCX Exchange","exchange-api.lcx.com", aLCX, uLCX,
        md.lcx_btc,"BTC",0, md.lcx_eth,"ETH",2, md.lcx_lcx,"LCX",5, dt);

    ImVec2 dv=ImGui::GetCursorScreenPos();
    ImGui::GetWindowDrawList()->AddLine(dv,{dv.x+(float)(g_sidebarW-20),dv.y},IM_COL32(22,26,42,255),1.f);
    ImGui::Dummy({0,4});

    ExchangeSection("Kraken","api.kraken.com", aKraken, uKraken,
        md.kraken_btc,"BTC",0, md.kraken_eth,"ETH",2, md.kraken_lcx,"LCX",5, dt);

    dv=ImGui::GetCursorScreenPos();
    ImGui::GetWindowDrawList()->AddLine(dv,{dv.x+(float)(g_sidebarW-20),dv.y},IM_COL32(22,26,42,255),1.f);
    ImGui::Dummy({0,4});

    ExchangeSection("Coinbase","api.coinbase.com", aCB, uCB,
        md.cb_btc,"BTC",0, md.cb_eth,"ETH",2, md.cb_lcx,"LCX",5, dt);

    if(!md.cb_lcx.ok){
        ImGui::PushFont(fntSmall);
        ImGui::TextColored({0.35f,0.35f,0.50f,1.f},"  * LCX-USD not listed on Coinbase");
        ImGui::PopFont();
    }

    ImGui::EndChild();
}
