// ============================================================
//  OmnibusSidebar v4.0  —  modular architecture
//
//  main.cpp este MINIMAL — doar init, loop, module dispatch
//
//  Ca sa adaugi un modul nou:
//    1. Creezi mod_xyz.h + mod_xyz.cpp
//    2. #include "mod_xyz.h" aici
//    3. Apelezi DrawXyzTab() sau DrawXyzWindow() in loop
//
//  Module active:
//    mod_prices   — PRICES tab (3 exchanges)
//    mod_trade    — TRADE tab
//    mod_log      — LOG tab
//    mod_toast    — toast overlay
//    fetch        — background HTTP thread
// ============================================================

#include "app_state.h"
#include "win_input_region.h"
#include "fetch.h"
#include "mod_toast.h"
#include "mod_log.h"
#include "mod_prices.h"
#include "mod_trade.h"
#include "mod_charts.h"
#include "mod_wallet.h"

#include "raylib.h"
#include "rlImGui.h"

#include <thread>
#include <chrono>
#include <math.h>

// ─── Global state definitions (declared extern in app_state.h) ──
ImFont* fntRegular = nullptr;
ImFont* fntMedium  = nullptr;
ImFont* fntBold    = nullptr;
ImFont* fntLarge   = nullptr;
ImFont* fntSmall   = nullptr;

MarketData         g_md;
std::mutex         g_md_mtx;
std::atomic<bool>  g_run(true);
std::atomic<int>   g_fetch_count(0);

int g_sidebarW = 430;
int g_monH     = 0;
int g_monW     = 0;


// ─── Main ────────────────────────────────────────────────────────
int main(void)
{
    SetConfigFlags(FLAG_WINDOW_UNDECORATED | FLAG_WINDOW_TOPMOST |
                   FLAG_WINDOW_TRANSPARENT | FLAG_MSAA_4X_HINT);
    InitWindow(1,1,"OmnibusSidebar");

    int monitor = GetCurrentMonitor();
    g_monW      = GetMonitorWidth(monitor);
    g_monH      = GetMonitorHeight(monitor);

    // Fereastra = TOT ecranul — sidebar dreapta, chart stanga
    SetWindowSize(g_monW, g_monH);
    SetWindowPosition(0, 0);
    SetTargetFPS(60);

    // ── ImGui setup ─────────────────────────────────────────────
    rlImGuiSetup(true);
    ImGuiIO& io = ImGui::GetIO();
    io.IniFilename = nullptr;

    fntRegular = io.Fonts->AddFontFromFileTTF("assets/Inter-Regular.ttf", 14.f);
    fntMedium  = io.Fonts->AddFontFromFileTTF("assets/Inter-Medium.ttf",  14.f);
    fntBold    = io.Fonts->AddFontFromFileTTF("assets/Inter-Bold.ttf",    15.f);
    fntLarge   = io.Fonts->AddFontFromFileTTF("assets/Inter-Bold.ttf",    22.f);
    fntSmall   = io.Fonts->AddFontFromFileTTF("assets/Inter-Regular.ttf", 11.f);
    io.FontDefault = fntMedium;

    // ── Style: Win11 / rounded ───────────────────────────────────
    ImGui::StyleColorsDark();
    ImGuiStyle& S = ImGui::GetStyle();
    S.WindowRounding    = 12.f; S.FrameRounding     = 8.f;
    S.PopupRounding     = 10.f; S.ScrollbarRounding = 10.f;
    S.GrabRounding      = 8.f;  S.TabRounding       = 8.f;
    S.ChildRounding     = 8.f;  S.ItemSpacing       = {7,6};
    S.FramePadding      = {8,5}; S.CellPadding      = {6,4};
    S.WindowPadding     = {12,10}; S.ScrollbarSize   = 10.f;

    auto C=[](float r,float g,float b,float a=1.f)->ImVec4{return{r,g,b,a};};
    S.Colors[ImGuiCol_WindowBg]          = C(0.05f,0.06f,0.09f,0.97f);
    S.Colors[ImGuiCol_ChildBg]           = C(0.04f,0.04f,0.07f,1.f);
    S.Colors[ImGuiCol_PopupBg]           = C(0.07f,0.08f,0.11f,0.98f);
    S.Colors[ImGuiCol_Border]            = C(0.14f,0.16f,0.24f,1.f);
    S.Colors[ImGuiCol_BorderShadow]      = C(0,0,0,0);
    S.Colors[ImGuiCol_FrameBg]           = C(0.09f,0.11f,0.16f,1.f);
    S.Colors[ImGuiCol_FrameBgHovered]    = C(0.14f,0.17f,0.25f,1.f);
    S.Colors[ImGuiCol_FrameBgActive]     = C(0.17f,0.21f,0.30f,1.f);
    S.Colors[ImGuiCol_TitleBg]           = C(0.05f,0.05f,0.08f,1.f);
    S.Colors[ImGuiCol_TitleBgActive]     = C(0.07f,0.08f,0.12f,1.f);
    S.Colors[ImGuiCol_Header]            = C(0.11f,0.14f,0.20f,1.f);
    S.Colors[ImGuiCol_HeaderHovered]     = C(0.16f,0.20f,0.30f,1.f);
    S.Colors[ImGuiCol_HeaderActive]      = C(0.20f,0.25f,0.37f,1.f);
    S.Colors[ImGuiCol_Button]            = C(0.11f,0.13f,0.19f,1.f);
    S.Colors[ImGuiCol_ButtonHovered]     = C(0.17f,0.20f,0.30f,1.f);
    S.Colors[ImGuiCol_ButtonActive]      = C(0.22f,0.26f,0.40f,1.f);
    S.Colors[ImGuiCol_Tab]               = C(0.09f,0.11f,0.16f,1.f);
    S.Colors[ImGuiCol_TabHovered]        = C(0.18f,0.22f,0.35f,1.f);
    S.Colors[ImGuiCol_TabActive]         = C(0.14f,0.18f,0.28f,1.f);
    S.Colors[ImGuiCol_TabUnfocused]      = C(0.07f,0.08f,0.12f,1.f);
    S.Colors[ImGuiCol_TabUnfocusedActive]= C(0.11f,0.14f,0.20f,1.f);
    S.Colors[ImGuiCol_TableHeaderBg]     = C(0.07f,0.09f,0.13f,1.f);
    S.Colors[ImGuiCol_TableRowBg]        = C(0.f,0.f,0.f,0.f);
    S.Colors[ImGuiCol_TableRowBgAlt]     = C(1.f,1.f,1.f,0.025f);
    S.Colors[ImGuiCol_ScrollbarBg]       = C(0.02f,0.02f,0.04f,1.f);
    S.Colors[ImGuiCol_ScrollbarGrab]     = C(0.16f,0.18f,0.28f,1.f);
    S.Colors[ImGuiCol_Separator]         = C(0.12f,0.14f,0.22f,1.f);
    S.Colors[ImGuiCol_CheckMark]         = C(0.3f,1.f,0.5f,1.f);
    S.Colors[ImGuiCol_SliderGrab]        = C(0.30f,0.45f,0.80f,1.f);
    S.Colors[ImGuiCol_TextSelectedBg]    = C(0.20f,0.40f,0.80f,0.40f);

    // ── Start fetch thread ───────────────────────────────────────
    std::thread ft(FetchLoop);
    ft.detach();

    // Input region initiala — doar sidebar
    bool prevChartOpen = false;
    UpdateInputRegion(false, g_monW, g_monH, g_sidebarW);

    Log("OmnibusSidebar v4.0 started", {0.55f,0.55f,0.75f,1.f});
    Log("Fetching: LCX Exchange | Kraken | Coinbase @ 1s", {0.40f,0.70f,1.f,1.f});
    PushToast("OmnibusSidebar v4.0", {0.4f,0.7f,1.f,1.f});

    float pulse = 0.f;
    auto  tLast = std::chrono::steady_clock::now();

    auto tickFlash=[](Tick& t, float dt){
        if(t.flash_t>0) t.flash_t=fmaxf(0.f,t.flash_t-dt);
    };

    // ── Main loop ────────────────────────────────────────────────
    while(!WindowShouldClose())
    {
        auto tNow = std::chrono::steady_clock::now();
        float dt  = std::chrono::duration<float>(tNow-tLast).count();
        tLast = tNow;
        pulse = fmodf(pulse+dt*2.5f, 6.2832f);

        // Snapshot market data + tick flash timers
        MarketData md;
        {
            std::lock_guard<std::mutex> lk(g_md_mtx);
            md = g_md;
            tickFlash(g_md.lcx_lcx,dt); tickFlash(g_md.lcx_btc,dt); tickFlash(g_md.lcx_eth,dt);
            tickFlash(g_md.kraken_btc,dt); tickFlash(g_md.kraken_eth,dt); tickFlash(g_md.kraken_lcx,dt);
            tickFlash(g_md.cb_btc,dt); tickFlash(g_md.cb_eth,dt); tickFlash(g_md.cb_lcx,dt);
        }

        // Actualizeaza input region daca s-a schimbat starea chart
        bool curChartOpen = IsChartOpen();
        if(curChartOpen != prevChartOpen){
            prevChartOpen = curChartOpen;
            UpdateInputRegion(curChartOpen, g_monW, g_monH, g_sidebarW);
        }

        // ── Raylib background ────────────────────────────────────
        BeginDrawing();
        ClearBackground(BLANK);   // tot ecranul transparent

        // Sidebar background (dreapta)
        int sX = g_monW - g_sidebarW;
        DrawRectangle(sX, 0, g_sidebarW, g_monH, {7,8,12,252});
        for(int i=0;i<4;i++)
            DrawRectangle(sX,i,g_sidebarW,1,{(unsigned char)(18+i*4),(unsigned char)(20+i*4),(unsigned char)(32+i*4),255});
        // Exchange accent stripes (marginea stanga a sidebar-ului)
        DrawRectangle(sX, 0,          2, g_monH/3,    {51,140,255,180});
        DrawRectangle(sX, g_monH/3,   2, g_monH/3,    {153,90,255,180});
        DrawRectangle(sX, g_monH*2/3, 2, g_monH/3+1,  {38,204,148,180});

        // ── ImGui ────────────────────────────────────────────────
        rlImGuiBegin();

        ImGui::SetNextWindowPos({(float)(g_monW - g_sidebarW + 4), 0});
        ImGui::SetNextWindowSize({(float)(g_sidebarW-4),(float)g_monH});
        ImGui::Begin("##root",nullptr,
            ImGuiWindowFlags_NoDecoration|ImGuiWindowFlags_NoMove|
            ImGuiWindowFlags_NoBackground|ImGuiWindowFlags_NoBringToFrontOnFocus);

        // ── Header ───────────────────────────────────────────────
        ImGui::Spacing();
        {
            ImVec2 p=ImGui::GetCursorScreenPos();
            float a=0.55f+0.45f*sinf(pulse);
            ImGui::GetWindowDrawList()->AddCircleFilled(
                {p.x+10.f,p.y+10.f},5.5f,
                IM_COL32(40,(int)(200*a),90,(int)(255*a)));
            ImGui::SetCursorPosX(ImGui::GetCursorPosX()+24.f);
        }
        ImGui::PushFont(fntBold);
        ImGui::TextColored({0.95f,0.82f,0.20f,1.f},"OMNIBUS TERMINAL");
        ImGui::PopFont();
        ImGui::SameLine();
        ImGui::TextColored({0.25f,0.85f,0.45f,1.f},"v4");
        DrawChartsButton();

        ImGui::SetCursorPosX(24.f);
        ImGui::PushFont(fntSmall);
        ImGui::TextColored({0.30f,0.30f,0.45f,1.f},
            "LCX | KRAKEN | COINBASE   polls:%d   dt:%.0fms",
            g_fetch_count.load(), dt*1000.f);
        ImGui::PopFont();
        ImGui::Spacing();

        ImVec2 sep0=ImGui::GetCursorScreenPos();
        ImGui::GetWindowDrawList()->AddLine(sep0,
            {sep0.x+(float)(g_sidebarW-16),sep0.y},IM_COL32(30,34,54,255),1.f);
        ImGui::Dummy({0,3});

        // ── Tabs ─────────────────────────────────────────────────
        ImGui::PushStyleVar(ImGuiStyleVar_TabRounding,8.f);
        if(ImGui::BeginTabBar("##tabs",ImGuiTabBarFlags_NoTabListScrollingButtons))
        {
            if(ImGui::BeginTabItem(" PRICES "))
            {
                DrawPricesTab(md, dt);
                ImGui::EndTabItem();
            }
            if(ImGui::BeginTabItem(" TRADE "))
            {
                DrawTradeTab(md);
                ImGui::EndTabItem();
            }
            if(ImGui::BeginTabItem(" LOG "))
            {
                DrawLogTab();
                ImGui::EndTabItem();
            }
            if(ImGui::BeginTabItem(" WALLET "))
            {
                DrawWalletTab();
                ImGui::EndTabItem();
            }

            // ── ADD NEW TABS HERE ─────────────────────────────────
            // if(ImGui::BeginTabItem(" CHARTS "))  { DrawChartsTab(md,dt); ImGui::EndTabItem(); }
            // if(ImGui::BeginTabItem(" RSI "))      { DrawRsiTab(md); ImGui::EndTabItem(); }
            // if(ImGui::BeginTabItem(" ORDERS "))   { DrawOrdersTab(); ImGui::EndTabItem(); }

            ImGui::EndTabBar();
        }
        ImGui::PopStyleVar();

        // ── Footer ───────────────────────────────────────────────
        ImGui::SetCursorPosY((float)g_monH - 80.f);
        {
            ImVec2 fp=ImGui::GetCursorScreenPos();
            ImGui::GetWindowDrawList()->AddRectFilled(
                fp,{fp.x+(float)(g_sidebarW-8),fp.y+46.f},
                IM_COL32(7,8,12,245));
        }

        ImGui::PushFont(fntSmall);
        ImGui::TextColored({0.22f,0.22f,0.35f,1.f},
            "  OmnibusSidebar v4.0  |  @1s REST");
        ImGui::PopFont();

        ImGui::End();

        // close via Alt+F4 or OS

        // Floating windows — INSIDE rlImGui frame, AFTER sidebar End
        DrawChartsWindow();

        rlImGuiEnd();

        // Toasts drawn on top of everything
        DrawToasts(dt, g_sidebarW, g_monH);

        EndDrawing();
    }

    g_run=false;
    rlImGuiShutdown();
    CloseWindow();
    return 0;
}
