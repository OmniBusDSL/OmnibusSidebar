// ============================================================
//  mod_trade.cpp
// ============================================================
#include "mod_trade.h"
#include "mod_log.h"
#include "mod_toast.h"
#include <stdio.h>
#include <string.h>

static char s_amt[32]  = "1000";
static char s_px[32]   = "0.00000";
static int  s_exch     = 0;
static int  s_asset    = 0;
static bool s_cbuy     = false;
static bool s_csell    = false;

static const char* exch_names[] = {"LCX Exchange","Kraken","Coinbase"};
static const char* exch_short[] = {"LCX","KRK","CB"};
static const char* asset_names[]= {"LCX","BTC","ETH"};
static const char* lcx_syms[]   = {"LCX/USDC","BTC/USDC","ETH/USDC"};
static const char* krak_syms[]  = {"LCXUSD","XBTUSD","ETHUSD"};
static const char* cb_syms[]    = {"LCX-USD","BTC-USD","ETH-USD"};

static ImVec4 aLCX    = {0.20f,0.55f,1.00f,1.f};
static ImVec4 aKraken = {0.60f,0.35f,1.00f,1.f};
static ImVec4 aCB     = {0.15f,0.80f,0.58f,1.f};

static void DoOrder(const char* side, const char* exch,
                    const char* pair, const char* amt, const char* px)
{
    char buf[160];
    snprintf(buf,sizeof(buf),"[%s] %s  %s  qty:%s  @%s",side,exch,pair,amt,px);
    bool isBuy=(strcmp(side,"BUY")==0);
    Log(buf, isBuy?ImVec4{0.2f,1.f,0.4f,1.f}:ImVec4{1.f,0.35f,0.35f,1.f});
    PushToast(buf, isBuy?ImVec4{0.2f,0.9f,0.4f,1.f}:ImVec4{1.f,0.35f,0.35f,1.f});
}

void DrawTradeTab(const MarketData& md)
{
    ImGui::Spacing();
    float bw3 = ((float)(g_sidebarW-4)-28.f)/3.f;

    // Exchange selector
    ImGui::PushFont(fntSmall);
    ImGui::TextColored({0.40f,0.40f,0.55f,1.f},"EXCHANGE");
    ImGui::PopFont();
    for(int i=0;i<3;i++){
        bool sel=(s_exch==i);
        ImVec4 ac=(i==0)?aLCX:(i==1)?aKraken:aCB;
        if(sel){
            ImGui::PushStyleColor(ImGuiCol_Button,       {ac.x*.3f,ac.y*.3f,ac.z*.3f,1.f});
            ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{ac.x*.4f,ac.y*.4f,ac.z*.4f,1.f});
            ImGui::PushStyleColor(ImGuiCol_Text, ac);
        }
        ImGui::PushFont(fntMedium);
        if(ImGui::Button(exch_short[i],{bw3,30.f})) s_exch=i;
        ImGui::PopFont();
        if(sel) ImGui::PopStyleColor(3);
        if(i<2) ImGui::SameLine(0,4);
    }

    // Asset selector
    ImGui::Spacing();
    ImGui::PushFont(fntSmall);
    ImGui::TextColored({0.40f,0.40f,0.55f,1.f},"ASSET");
    ImGui::PopFont();
    ImVec4 assetCols[]={{0.25f,0.85f,1.f,1.f},{0.97f,0.72f,0.10f,1.f},{0.55f,0.60f,1.f,1.f}};
    for(int i=0;i<3;i++){
        bool sel=(s_asset==i);
        if(sel){
            ImVec4 ac=assetCols[i];
            ImGui::PushStyleColor(ImGuiCol_Button,       {ac.x*.25f,ac.y*.25f,ac.z*.25f,1.f});
            ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{ac.x*.35f,ac.y*.35f,ac.z*.35f,1.f});
            ImGui::PushStyleColor(ImGuiCol_Text, ac);
        }
        ImGui::PushFont(fntBold);
        if(ImGui::Button(asset_names[i],{bw3,30.f})) s_asset=i;
        ImGui::PopFont();
        if(sel) ImGui::PopStyleColor(3);
        if(i<2) ImGui::SameLine(0,4);
    }

    ImGui::Spacing(); ImGui::Separator(); ImGui::Spacing();

    // Current tick
    auto getTick=[&](int ex, int as)->const Tick*{
        if(ex==0){if(as==0)return&md.lcx_lcx;if(as==1)return&md.lcx_btc;return&md.lcx_eth;}
        if(ex==1){if(as==0)return&md.kraken_lcx;if(as==1)return&md.kraken_btc;return&md.kraken_eth;}
        if(as==0)return&md.cb_lcx;if(as==1)return&md.cb_btc;return&md.cb_eth;
    };
    const Tick* ct = getTick(s_exch,s_asset);
    int dec=(s_asset==0)?5:(s_asset==1?0:2);

    // Bid / Ask boxes
    float bw2=((float)(g_sidebarW-4)-28.f)/2.f;
    ImGui::PushStyleColor(ImGuiCol_ChildBg,{0.03f,0.10f,0.05f,1.f});
    ImGui::BeginChild("##bid",{bw2,58.f},true);
    ImGui::PushFont(fntSmall); ImGui::TextColored({0.35f,0.70f,0.35f,1.f},"BID"); ImGui::PopFont();
    ImGui::PushFont(fntLarge);
    if(ct&&ct->ok&&ct->bid>0){
        if(dec<=0)      ImGui::TextColored({0.25f,1.f,0.45f,1.f},"$%.0f",ct->bid);
        else if(dec==2) ImGui::TextColored({0.25f,1.f,0.45f,1.f},"$%.2f",ct->bid);
        else            ImGui::TextColored({0.25f,1.f,0.45f,1.f},"$%.5f",ct->bid);
    } else { ImGui::TextDisabled("---"); }
    ImGui::PopFont();
    ImGui::EndChild();
    ImGui::PopStyleColor();

    ImGui::SameLine(0,6);

    ImGui::PushStyleColor(ImGuiCol_ChildBg,{0.10f,0.03f,0.03f,1.f});
    ImGui::BeginChild("##ask",{bw2,58.f},true);
    ImGui::PushFont(fntSmall); ImGui::TextColored({0.80f,0.35f,0.35f,1.f},"ASK"); ImGui::PopFont();
    ImGui::PushFont(fntLarge);
    if(ct&&ct->ok&&ct->ask>0){
        if(dec<=0)      ImGui::TextColored({1.f,0.38f,0.38f,1.f},"$%.0f",ct->ask);
        else if(dec==2) ImGui::TextColored({1.f,0.38f,0.38f,1.f},"$%.2f",ct->ask);
        else            ImGui::TextColored({1.f,0.38f,0.38f,1.f},"$%.5f",ct->ask);
    } else { ImGui::TextDisabled("---"); }
    ImGui::PopFont();
    ImGui::EndChild();
    ImGui::PopStyleColor();

    ImGui::Spacing();

    // Amount + Price inputs
    ImGui::PushFont(fntSmall); ImGui::TextColored({0.40f,0.40f,0.55f,1.f},"AMOUNT"); ImGui::PopFont();
    ImGui::SetNextItemWidth(-1);
    ImGui::InputText("##amt",s_amt,sizeof(s_amt));

    ImGui::PushFont(fntSmall); ImGui::TextColored({0.40f,0.40f,0.55f,1.f},"LIMIT PRICE"); ImGui::PopFont();
    ImGui::SetNextItemWidth(-(80.f));
    ImGui::InputText("##px",s_px,sizeof(s_px));
    ImGui::SameLine(0,4);
    if(ImGui::Button("Fill",{74,0})){
        if(ct&&ct->last>0){
            if(dec<=0)      snprintf(s_px,sizeof(s_px),"%.0f",ct->last);
            else if(dec==2) snprintf(s_px,sizeof(s_px),"%.2f",ct->last);
            else            snprintf(s_px,sizeof(s_px),"%.5f",ct->last);
        }
    }
    if(ImGui::IsItemHovered()) ImGui::SetTooltip("Fill from last traded price");

    ImGui::Spacing();

    // BUY / SELL buttons
    float bwBtn=((float)(g_sidebarW-4)-24.f)/2.f;
    ImGui::PushStyleColor(ImGuiCol_Button,        {0.06f,0.44f,0.14f,1.f});
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, {0.08f,0.60f,0.20f,1.f});
    ImGui::PushStyleColor(ImGuiCol_ButtonActive,  {0.04f,0.32f,0.10f,1.f});
    ImGui::PushFont(fntBold);
    if(ImGui::Button("  BUY  ",{bwBtn,48.f})) s_cbuy=true;
    ImGui::PopFont(); ImGui::PopStyleColor(3);
    ImGui::SameLine(0,4);
    ImGui::PushStyleColor(ImGuiCol_Button,        {0.52f,0.06f,0.06f,1.f});
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, {0.72f,0.09f,0.09f,1.f});
    ImGui::PushStyleColor(ImGuiCol_ButtonActive,  {0.38f,0.04f,0.04f,1.f});
    ImGui::PushFont(fntBold);
    if(ImGui::Button("  SELL  ",{bwBtn,48.f})) s_csell=true;
    ImGui::PopFont(); ImGui::PopStyleColor(3);

    // BUY modal
    if(s_cbuy) ImGui::OpenPopup("##mbuy");
    if(ImGui::BeginPopupModal("##mbuy",nullptr,
        ImGuiWindowFlags_AlwaysAutoResize|ImGuiWindowFlags_NoTitleBar)){
        ImGui::PushFont(fntBold);
        ImGui::TextColored({0.25f,1.f,0.45f,1.f},"CONFIRM BUY");
        ImGui::PopFont();
        ImGui::Separator();
        const char* sym=(s_exch==0)?lcx_syms[s_asset]:(s_exch==1)?krak_syms[s_asset]:cb_syms[s_asset];
        ImGui::Text("%s  |  %s",exch_names[s_exch],sym);
        ImGui::Text("Amount : %s",s_amt);
        ImGui::Text("Price  : %s",s_px);
        ImGui::Spacing();
        ImGui::PushStyleColor(ImGuiCol_Button,{0.06f,0.44f,0.14f,1.f});
        if(ImGui::Button("Confirm",{150,34})){
            DoOrder("BUY",exch_names[s_exch],sym,s_amt,s_px);
            s_cbuy=false; ImGui::CloseCurrentPopup();
        }
        ImGui::PopStyleColor();
        ImGui::SameLine();
        if(ImGui::Button("Cancel",{110,34})){s_cbuy=false;ImGui::CloseCurrentPopup();}
        ImGui::EndPopup();
    }

    // SELL modal
    if(s_csell) ImGui::OpenPopup("##msell");
    if(ImGui::BeginPopupModal("##msell",nullptr,
        ImGuiWindowFlags_AlwaysAutoResize|ImGuiWindowFlags_NoTitleBar)){
        ImGui::PushFont(fntBold);
        ImGui::TextColored({1.f,0.35f,0.35f,1.f},"CONFIRM SELL");
        ImGui::PopFont();
        ImGui::Separator();
        const char* sym=(s_exch==0)?lcx_syms[s_asset]:(s_exch==1)?krak_syms[s_asset]:cb_syms[s_asset];
        ImGui::Text("%s  |  %s",exch_names[s_exch],sym);
        ImGui::Text("Amount : %s",s_amt);
        ImGui::Text("Price  : %s",s_px);
        ImGui::Spacing();
        ImGui::PushStyleColor(ImGuiCol_Button,{0.52f,0.06f,0.06f,1.f});
        if(ImGui::Button("Confirm",{150,34})){
            DoOrder("SELL",exch_names[s_exch],sym,s_amt,s_px);
            s_csell=false; ImGui::CloseCurrentPopup();
        }
        ImGui::PopStyleColor();
        ImGui::SameLine();
        if(ImGui::Button("Cancel",{110,34})){s_csell=false;ImGui::CloseCurrentPopup();}
        ImGui::EndPopup();
    }
}
