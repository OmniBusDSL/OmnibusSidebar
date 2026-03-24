// ============================================================
//  mod_charts.cpp  —  Candlestick chart window
//
//  Data sources:
//    Kraken  : GET api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=60
//    Coinbase: GET api.coinbase.com/api/v3/brokerage/market/products/BTC-USD/candles?granularity=3600
//    LCX     : GET api-kline.lcx.com/v1/market/kline?pair=LCX/USDC&resolution=1h&from=...&to=...
//
//  Ca sa adaugi un indicator nou:
//    1. Calculeaza din g_candles dupa fetch
//    2. Deseneaza in DrawIndicator() sub chart
// ============================================================

#include "mod_charts.h"
#include "fetch.h"
#include "mod_log.h"

#define WIN32_LEAN_AND_MEAN
#define NOGDI
#define NOUSER
#include <windows.h>
#undef NOGDI
#undef NOUSER

#include "raylib.h"

#include <string>
#include <vector>
#include <algorithm>
#include <mutex>
#include <thread>
#include <atomic>
#include <math.h>
#include <stdio.h>
#include <time.h>

// ─── Candle ──────────────────────────────────────────────────
struct Candle {
    double o, h, l, c, v;
    time_t t;
};

// ─── Chart state ─────────────────────────────────────────────
static bool   g_chartOpen  = false;
static int    g_chartPair  = 0;    // index into PAIRS table
static int    g_chartExch  = 0;    // 0=Kraken 1=Coinbase 2=LCX
static int    g_chartTF    = 2;    // 0=1m 1=5m 2=1h 3=4h 4=1d

static std::vector<Candle> g_candles;
static std::mutex          g_candles_mtx;
static std::atomic<bool>   g_fetching(false);
static std::atomic<bool>   g_needFetch(true);
static char                g_chartStatus[64] = "Ready";

static const char* TF_LABELS[]   = {"1m","5m","1h","4h","1d"};
static const int   TF_KRAKEN[]   = {1,5,60,240,1440};
static const int   TF_COINBASE[] = {60,300,3600,14400,86400};
static const int   TF_SEC[]      = {60,300,3600,14400,86400};
static const char* TF_LCX[]      = {"1m","5m","1h","4h","1d"};

static const char* EXCH_LABELS[] = {"Kraken","Coinbase","LCX"};

// Perechi disponibile per exchange
// Kraken
static const char* KRAKEN_PAIRS[]  = {"XBTUSD","ETHUSD","LCXUSD","XXBTZEUR","XETHZEUR"};
static const char* KRAKEN_LABELS[] = {"BTC/USD","ETH/USD","LCX/USD","BTC/EUR","ETH/EUR"};
static const int   KRAKEN_N        = 5;

// Coinbase
static const char* CB_PAIRS[]  = {"BTC-USD","ETH-USD","LCX-USD","BTC-EUR","ETH-EUR","BTC-USDC","ETH-USDC"};
static const char* CB_LABELS[] = {"BTC/USD","ETH/USD","LCX/USD","BTC/EUR","ETH/EUR","BTC/USDC","ETH/USDC"};
static const int   CB_N        = 7;

// LCX Exchange
static const char* LCX_PAIRS[]  = {"BTC%2FUSDC","ETH%2FUSDC","LCX%2FUSDC","BTC%2FEUR","ETH%2FEUR","LCX%2FEUR"};
static const char* LCX_LABELS[] = {"BTC/USDC","ETH/USDC","LCX/USDC","BTC/EUR","ETH/EUR","LCX/EUR"};
static const int   LCX_N        = 6;

// ─── Parse Kraken OHLC ───────────────────────────────────────
// Response: {"result":{"XXBTZUSD":[[time,o,h,l,c,vwap,vol,count],...]},...}
static std::vector<Candle> ParseKrakenOHLC(const std::string& r)
{
    std::vector<Candle> out;
    // Find first '[' after 'result'
    size_t start = r.find("\"result\"");
    if(start==std::string::npos) return out;
    // Find the array of arrays — skip first '[' (object open) find second
    size_t arr = r.find("[[", start);
    if(arr==std::string::npos) return out;

    size_t p = arr;
    while(p < r.size())
    {
        size_t open = r.find('[', p);
        if(open==std::string::npos) break;
        size_t close = r.find(']', open);
        if(close==std::string::npos) break;
        // Check it's not the outer array open
        if(close > open+2)
        {
            std::string row = r.substr(open+1, close-open-1);
            // parse: time,o,h,l,c,vwap,vol,count
            double vals[7]={};
            int vi=0;
            size_t rp=0;
            while(vi<7 && rp<row.size())
            {
                size_t comma = row.find(',', rp);
                std::string tok = (comma==std::string::npos) ? row.substr(rp) : row.substr(rp,comma-rp);
                // strip quotes
                if(!tok.empty()&&tok[0]=='"') tok=tok.substr(1,tok.size()-2);
                vals[vi++] = atof(tok.c_str());
                if(comma==std::string::npos) break;
                rp = comma+1;
            }
            if(vi>=5 && vals[0]>0)
            {
                Candle c;
                c.t=(time_t)vals[0];
                c.o=vals[1]; c.h=vals[2]; c.l=vals[3]; c.c=vals[4];
                c.v=(vi>=7)?vals[6]:0;
                out.push_back(c);
            }
        }
        p = close+1;
        // Stop at last ']]'
        if(p<r.size() && r[p]==']') break;
    }
    return out;
}

// ─── Parse Coinbase candles ───────────────────────────────────
// Response: {"candles":[{"start":"ts","low":"..","high":"..","open":"..","close":"..","volume":".."},...]}
static std::vector<Candle> ParseCoinbaseCandles(const std::string& r)
{
    std::vector<Candle> out;
    size_t arr = r.find("\"candles\"");
    if(arr==std::string::npos) return out;
    arr = r.find('[', arr);
    if(arr==std::string::npos) return out;

    size_t p = arr+1;
    while(p < r.size())
    {
        size_t open = r.find('{', p);
        if(open==std::string::npos) break;
        size_t close = r.find('}', open);
        if(close==std::string::npos) break;
        std::string obj = r.substr(open, close-open+1);

        auto field=[&](const char* key)->double{
            std::string k=std::string("\"")+key+"\":\"";
            size_t fp=obj.find(k);
            if(fp==std::string::npos){
                // try without quotes around value
                k=std::string("\"")+key+"\":";
                fp=obj.find(k); if(fp==std::string::npos) return 0.0;
                fp+=k.size(); size_t e=obj.find_first_of(",}",fp);
                return atof(obj.substr(fp,e-fp).c_str());
            }
            fp+=k.size();
            size_t e=obj.find('"',fp);
            return atof(obj.substr(fp,e-fp).c_str());
        };

        Candle c;
        c.t=(time_t)field("start");
        c.o=field("open"); c.h=field("high"); c.l=field("low");
        c.c=field("close"); c.v=field("volume");
        if(c.t>0) out.push_back(c);
        p = close+1;
        if(p<r.size()&&r[p]==']') break;
    }
    // Coinbase returns newest first — reverse
    std::reverse(out.begin(), out.end());
    return out;
}

// ─── Parse LCX kline ─────────────────────────────────────────
// Response: {"data":[{"time":ts,"open":"..","high":"..","low":"..","close":"..","volume":".."},...]}
static std::vector<Candle> ParseLCXKline(const std::string& r)
{
    std::vector<Candle> out;
    size_t arr = r.find("\"data\"");
    if(arr==std::string::npos) return out;
    arr = r.find('[', arr);
    if(arr==std::string::npos) return out;

    size_t p = arr+1;
    while(p < r.size())
    {
        size_t open = r.find('{', p);
        if(open==std::string::npos) break;
        size_t close = r.find('}', open);
        if(close==std::string::npos) break;
        std::string obj = r.substr(open, close-open+1);

        auto fld=[&](const char* key)->double{
            return atof(Jx(obj,key).c_str());
        };

        Candle c;
        c.t=(time_t)fld("time");
        c.o=fld("open"); c.h=fld("high"); c.l=fld("low");
        c.c=fld("close"); c.v=fld("volume");
        if(c.t>0) out.push_back(c);
        p = close+1;
        if(p<r.size()&&r[p]==']') break;
    }
    return out;
}

// ─── Fetch candles in background ─────────────────────────────
static void FetchCandles(int pair, int exch, int tf)
{
    g_fetching = true;
    snprintf(g_chartStatus, sizeof(g_chartStatus), "Fetching...");

    std::vector<Candle> candles;
    std::string resp;

    if(exch == 0) // Kraken
    {
        int idx = (pair < KRAKEN_N) ? pair : 0;
        char path[128];
        snprintf(path,sizeof(path),"/0/public/OHLC?pair=%s&interval=%d",
            KRAKEN_PAIRS[idx], TF_KRAKEN[tf]);
        resp = HttpGet("api.kraken.com", path);
        candles = ParseKrakenOHLC(resp);
    }
    else if(exch == 1) // Coinbase
    {
        int idx = (pair < CB_N) ? pair : 0;
        char path[256];
        time_t now = time(NULL);
        time_t from = now - (time_t)TF_COINBASE[tf] * 200;
        snprintf(path,sizeof(path),
            "/api/v3/brokerage/market/products/%s/candles?granularity=%d&start=%lld&end=%lld",
            CB_PAIRS[idx], TF_COINBASE[tf], (long long)from, (long long)now);
        resp = HttpGet("api.coinbase.com", path);
        candles = ParseCoinbaseCandles(resp);
    }
    else // LCX
    {
        int idx = (pair < LCX_N) ? pair : 0;
        char path[256];
        time_t now = time(NULL);
        time_t from = now - (time_t)TF_SEC[tf] * 200;
        snprintf(path,sizeof(path),
            "/v1/market/kline?pair=%s&resolution=%s&from=%lld&to=%lld",
            LCX_PAIRS[idx], TF_LCX[tf], (long long)from, (long long)now);
        resp = HttpGet("api-kline.lcx.com", path);
        candles = ParseLCXKline(resp);
    }

    {
        std::lock_guard<std::mutex> lk(g_candles_mtx);
        g_candles = candles;
    }

    if(candles.empty())
        snprintf(g_chartStatus,sizeof(g_chartStatus),"No data");
    else
        snprintf(g_chartStatus,sizeof(g_chartStatus),"%d candles OK", (int)candles.size());

    Log(g_chartStatus, {0.4f,0.8f,1.f,1.f});
    g_fetching = false;
}

// ─── Draw candlestick chart ───────────────────────────────────
static void DrawCandlesticks(const std::vector<Candle>& candles,
                              ImVec2 pos, ImVec2 size)
{
    if(candles.empty()){
        ImGui::SetCursorScreenPos({pos.x+size.x/2-40, pos.y+size.y/2-8});
        ImGui::TextDisabled("No data");
        return;
    }

    ImDrawList* dl = ImGui::GetWindowDrawList();

    // Background
    dl->AddRectFilled(pos, {pos.x+size.x, pos.y+size.y},
        IM_COL32(8,10,16,255), 4.f);
    dl->AddRect(pos, {pos.x+size.x, pos.y+size.y},
        IM_COL32(25,30,50,255), 4.f);

    // Find min/max
    double hi = candles[0].h, lo = candles[0].l;
    for(auto& c : candles){ if(c.h>hi) hi=c.h; if(c.l<lo) lo=c.l; }
    double range = hi - lo;
    if(range < 1e-10) range = 1.0;

    const float PAD  = 8.f;
    const float VPAD = 20.f;  // bottom volume area height
    float cw    = size.x / (float)candles.size();
    float candleW = fmaxf(cw * 0.7f, 1.f);

    auto priceY=[&](double p)->float{
        return pos.y + PAD + (float)((hi-p)/range) * (size.y - PAD*2 - VPAD);
    };

    // Grid lines (4 horizontal)
    for(int i=1; i<=3; i++){
        float gy = pos.y + PAD + (size.y-PAD*2-VPAD) * i / 4.f;
        dl->AddLine({pos.x,gy},{pos.x+size.x,gy}, IM_COL32(20,24,38,255));
        double gval = hi - range * i / 4.0;
        char lbl[32];
        if(gval >= 1000.0)      snprintf(lbl,sizeof(lbl),"%.0f",gval);
        else if(gval >= 1.0)    snprintf(lbl,sizeof(lbl),"%.2f",gval);
        else                    snprintf(lbl,sizeof(lbl),"%.5f",gval);
        dl->AddText({pos.x+2, gy-11}, IM_COL32(50,55,80,255), lbl);
    }

    // Volume max
    double maxVol = 0;
    for(auto& c : candles) if(c.v > maxVol) maxVol = c.v;
    if(maxVol < 1e-10) maxVol = 1.0;

    // Draw candles
    for(int i=0; i<(int)candles.size(); i++)
    {
        const Candle& c = candles[i];
        float cx = pos.x + (i+0.5f)*cw;
        float x0 = cx - candleW/2.f;
        float x1 = cx + candleW/2.f;

        float yo = priceY(c.o);
        float yc = priceY(c.c);
        float yh = priceY(c.h);
        float yl = priceY(c.l);

        bool up = (c.c >= c.o);
        ImU32 col    = up ? IM_COL32(32,180,80,230)  : IM_COL32(200,50,50,230);
        ImU32 colDim = up ? IM_COL32(20,100,45,180)  : IM_COL32(120,30,30,180);

        // Wick
        dl->AddLine({cx,yh},{cx,yl}, colDim, 1.f);

        // Body
        float bodyTop = fminf(yo,yc);
        float bodyBot = fmaxf(yo,yc);
        if(bodyBot-bodyTop < 1.f) bodyBot = bodyTop+1.f;
        dl->AddRectFilled({x0,bodyTop},{x1,bodyBot}, col);

        // Volume bar (bottom)
        if(c.v > 0 && maxVol > 0){
            float vh = (float)(c.v/maxVol) * (VPAD-3.f);
            float vy = pos.y + size.y - 2.f - vh;
            dl->AddRectFilled({x0, vy},{x1, pos.y+size.y-2.f},
                up ? IM_COL32(20,80,40,120) : IM_COL32(80,20,20,120));
        }
    }

    // Last price line
    if(!candles.empty()){
        float ly = priceY(candles.back().c);
        dl->AddLine({pos.x,ly},{pos.x+size.x,ly},
            IM_COL32(255,220,50,80), 1.f);
        char lpx[32];
        double lp = candles.back().c;
        if(lp>=1000.0)    snprintf(lpx,sizeof(lpx),"%.0f",lp);
        else if(lp>=1.0)  snprintf(lpx,sizeof(lpx),"%.2f",lp);
        else              snprintf(lpx,sizeof(lpx),"%.5f",lp);
        dl->AddRectFilled({pos.x+size.x-52,ly-10},{pos.x+size.x,ly+3},
            IM_COL32(60,50,10,200), 2.f);
        dl->AddText({pos.x+size.x-50, ly-9}, IM_COL32(255,220,50,255), lpx);
    }
}

// ─── Public: stare chart ─────────────────────────────────────
bool IsChartOpen() { return g_chartOpen; }

// ─── Public: button in sidebar header area ───────────────────
void DrawChartsButton()
{
    ImGui::SameLine();
    bool wasOpen = g_chartOpen;
    if(wasOpen)
        ImGui::PushStyleColor(ImGuiCol_Button, {0.15f,0.35f,0.55f,1.f});
    if(ImGui::SmallButton(" CHART "))
    {
        g_chartOpen = !g_chartOpen;
        if(g_chartOpen) g_needFetch = true;
    }
    if(wasOpen) ImGui::PopStyleColor();
    if(ImGui::IsItemHovered())
        ImGui::SetTooltip("Open/Close chart window");
}

// ─── Public: floating chart window ───────────────────────────
void DrawChartsWindow()
{
    if(!g_chartOpen) return;

    // Trigger fetch when needed
    if(g_needFetch && !g_fetching){
        g_needFetch = false;
        int p=g_chartPair, e=g_chartExch, tf=g_chartTF;
        std::thread([p,e,tf]{ FetchCandles(p,e,tf); }).detach();
    }

    // Chart window: centrata in zona stanga (tot ecranul minus sidebar)
    float areaW = (float)(g_monW - g_sidebarW);  // zona disponibila
    float winW  = areaW - 20.f;
    float winH  = (float)g_monH - 40.f;
    float winX  = (areaW - winW) / 2.f;
    float winY  = 20.f;

    ImGui::SetNextWindowPos({winX, winY}, ImGuiCond_Always);
    ImGui::SetNextWindowSize({winW, winH}, ImGuiCond_Always);

    ImGuiWindowFlags flags = ImGuiWindowFlags_NoScrollbar
                           | ImGuiWindowFlags_NoScrollWithMouse;

    bool open = true;
    ImGui::Begin("##chart", &open, flags);
    if(!open){ g_chartOpen=false; ImGui::End(); return; }

    // ── Toolbar row 1: Exchange + Timeframe + Status ──────────
    ImGui::PushFont(fntBold);
    ImGui::TextColored({0.95f,0.82f,0.20f,1.f},"CHART");
    ImGui::PopFont();
    ImGui::SameLine(0,12);

    // Exchange selector
    ImVec4 exchCols[] = {{0.6f,0.35f,1.f,1.f},{0.15f,0.8f,0.58f,1.f},{0.2f,0.55f,1.f,1.f}};
    for(int i=0;i<3;i++){
        bool sel=(g_chartExch==i);
        if(sel){
            ImGui::PushStyleColor(ImGuiCol_Button,{exchCols[i].x*.3f,exchCols[i].y*.3f,exchCols[i].z*.3f,1.f});
            ImGui::PushStyleColor(ImGuiCol_Text, exchCols[i]);
        }
        if(ImGui::SmallButton(EXCH_LABELS[i])){
            if(g_chartExch!=i){
                g_chartExch=i;
                g_chartPair=0; // reset pair when exchange changes
                g_needFetch=true;
            }
        }
        if(sel) ImGui::PopStyleColor(2);
        if(i<2) ImGui::SameLine(0,3);
    }
    ImGui::SameLine(0,14);

    // Timeframe selector
    for(int i=0;i<5;i++){
        bool sel=(g_chartTF==i);
        if(sel){
            ImGui::PushStyleColor(ImGuiCol_Button,{0.15f,0.20f,0.35f,1.f});
            ImGui::PushStyleColor(ImGuiCol_Text,{0.7f,0.9f,1.f,1.f});
        }
        if(ImGui::SmallButton(TF_LABELS[i])){
            if(g_chartTF!=i){ g_chartTF=i; g_needFetch=true; }
        }
        if(sel) ImGui::PopStyleColor(2);
        if(i<4) ImGui::SameLine(0,3);
    }
    ImGui::SameLine(0,14);

    if(g_fetching){
        ImGui::PushFont(fntSmall);
        ImGui::TextColored({0.5f,0.8f,1.f,1.f},"loading...");
        ImGui::PopFont();
    } else {
        if(ImGui::SmallButton("Refresh")) g_needFetch=true;
        ImGui::SameLine(0,8);
        ImGui::PushFont(fntSmall);
        ImGui::TextColored({0.35f,0.35f,0.55f,1.f},"%s",g_chartStatus);
        ImGui::PopFont();
    }

    // ── Toolbar row 2: Pair selector (dynamic per exchange) ───
    ImGui::Spacing();
    ImGui::PushFont(fntSmall);
    ImGui::TextColored({0.35f,0.35f,0.55f,1.f},"PAIR:");
    ImGui::PopFont();
    ImGui::SameLine(0,6);

    const char** pairLabels = (g_chartExch==0)?KRAKEN_LABELS:(g_chartExch==1)?CB_LABELS:LCX_LABELS;
    int          pairN      = (g_chartExch==0)?KRAKEN_N:(g_chartExch==1)?CB_N:LCX_N;

    // Clamp pair index if switching exchange
    if(g_chartPair >= pairN) g_chartPair = 0;

    for(int i=0;i<pairN;i++){
        bool sel=(g_chartPair==i);
        if(sel){
            ImGui::PushStyleColor(ImGuiCol_Button,{0.18f,0.25f,0.40f,1.f});
            ImGui::PushStyleColor(ImGuiCol_Text,{0.85f,0.90f,1.f,1.f});
        }
        ImGui::PushFont(fntSmall);
        if(ImGui::SmallButton(pairLabels[i])){
            if(g_chartPair!=i){ g_chartPair=i; g_needFetch=true; }
        }
        ImGui::PopFont();
        if(sel) ImGui::PopStyleColor(2);
        if(i<pairN-1) ImGui::SameLine(0,3);
    }

    ImGui::Separator();

    // ── Chart area ───────────────────────────────────────────
    ImVec2 avail = ImGui::GetContentRegionAvail();
    ImVec2 chartPos = ImGui::GetCursorScreenPos();

    // Snapshot candles
    std::vector<Candle> snap;
    {
        std::lock_guard<std::mutex> lk(g_candles_mtx);
        snap = g_candles;
    }

    // Limit visible candles to avoid overcrowding
    const int MAX_VISIBLE = (int)(avail.x / 4.f);
    if((int)snap.size() > MAX_VISIBLE)
        snap = std::vector<Candle>(snap.end()-MAX_VISIBLE, snap.end());

    DrawCandlesticks(snap, chartPos, avail);

    // Invisible button to capture hover for the entire chart area
    ImGui::InvisibleButton("##chartarea", avail);

    ImGui::End();
}
