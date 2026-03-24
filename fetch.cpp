// ============================================================
//  fetch.cpp  —  HTTP + JSON + background fetch thread
// ============================================================
#define WIN32_LEAN_AND_MEAN
#define NOGDI
#define NOUSER
#include <windows.h>
#undef NOGDI
#undef NOUSER
#include <wininet.h>

#include "fetch.h"
#include "app_state.h"
#include <string>
#include <time.h>

// ─── HTTP GET via WinINet ────────────────────────────────────
std::string HttpGet(const char* host, const char* path)
{
    std::string out;
    HINTERNET hI = InternetOpenA("OmnibusSidebar/3.0",
                                  INTERNET_OPEN_TYPE_PRECONFIG, 0,0,0);
    if (!hI) return out;
    HINTERNET hC = InternetConnectA(hI, host,
                                     INTERNET_DEFAULT_HTTPS_PORT,
                                     0,0,INTERNET_SERVICE_HTTP,0,0);
    if (!hC){ InternetCloseHandle(hI); return out; }
    DWORD fl = INTERNET_FLAG_RELOAD|INTERNET_FLAG_NO_CACHE_WRITE|INTERNET_FLAG_SECURE;
    HINTERNET hR = HttpOpenRequestA(hC,"GET",path,0,0,0,fl,0);
    if (hR && HttpSendRequestA(hR,0,0,0,0)){
        char buf[8192]; DWORD rd=0;
        while(InternetReadFile(hR,buf,sizeof(buf)-1,&rd)&&rd){buf[rd]=0;out+=buf;}
        InternetCloseHandle(hR);
    }
    InternetCloseHandle(hC);
    InternetCloseHandle(hI);
    return out;
}

// ─── JSON micro-extractor ────────────────────────────────────
std::string Jx(const std::string& j, const char* key)
{
    std::string nd = std::string("\"")+key+"\":";
    size_t p = j.find(nd);
    if(p==std::string::npos) return "";
    p += nd.size();
    while(p<j.size()&&(j[p]==' '||j[p]=='\n'||j[p]=='\r')) p++;
    if(p>=j.size()) return "";
    if(j[p]=='"'){ p++; size_t e=j.find('"',p); return e==std::string::npos?"":j.substr(p,e-p); }
    size_t e=p; while(e<j.size()&&j[e]!=','&&j[e]!='}'&&j[e]!=']') e++;
    return j.substr(p,e-p);
}

// ─── Timestamp helper ────────────────────────────────────────
void NowStr(char* buf, int sz)
{
    time_t t=time(NULL); struct tm tm; localtime_s(&tm,&t);
    strftime(buf,sz,"%H:%M:%S",&tm);
}

// ─── Parse helpers ───────────────────────────────────────────
static Tick ParseKraken(const std::string& r)
{
    Tick t;
    auto arr=[&](const char* key)->double{
        std::string nd=std::string("\"")+key+"\":[\"";
        size_t p=r.find(nd); if(p==std::string::npos) return 0.0;
        p+=nd.size(); size_t e=r.find('"',p);
        return e==std::string::npos?0.0:atof(r.substr(p,e-p).c_str());
    };
    t.ask=arr("a"); t.bid=arr("b"); t.last=arr("c");
    t.ok=(t.last>0); NowStr(t.ts,sizeof(t.ts));
    return t;
}

static void ParseLCX(const std::string& r, Tick& t)
{
    t.bid  = atof(Jx(r,"bestBid").c_str());
    t.ask  = atof(Jx(r,"bestAsk").c_str());
    t.last = atof(Jx(r,"lastPrice").c_str());
    t.ok   = (t.last>0||t.bid>0);
    NowStr(t.ts,sizeof(t.ts));
}

static void ParseCoinbase(const std::string& r, Tick& t)
{
    t.bid  = atof(Jx(r,"best_bid").c_str());
    t.ask  = atof(Jx(r,"best_ask").c_str());
    t.last = atof(Jx(r,"price").c_str());
    if(t.last==0&&t.bid>0&&t.ask>0) t.last=(t.bid+t.ask)/2.0;
    t.ok   = (t.last>0||t.bid>0);
    NowStr(t.ts,sizeof(t.ts));
}

// ─── Background fetch thread — runs every 1s ─────────────────
void FetchLoop()
{
    while(g_run.load())
    {
        MarketData nd;

        ParseLCX(HttpGet("exchange-api.lcx.com","/api/ticker?pair=LCX%2FUSDC"), nd.lcx_lcx);
        ParseLCX(HttpGet("exchange-api.lcx.com","/api/ticker?pair=BTC%2FUSDC"), nd.lcx_btc);
        ParseLCX(HttpGet("exchange-api.lcx.com","/api/ticker?pair=ETH%2FUSDC"), nd.lcx_eth);

        nd.kraken_btc = ParseKraken(HttpGet("api.kraken.com","/0/public/Ticker?pair=XBTUSD"));
        nd.kraken_eth = ParseKraken(HttpGet("api.kraken.com","/0/public/Ticker?pair=ETHUSD"));
        nd.kraken_lcx = ParseKraken(HttpGet("api.kraken.com","/0/public/Ticker?pair=LCXUSD"));

        ParseCoinbase(HttpGet("api.coinbase.com","/api/v3/brokerage/market/products/BTC-USD/ticker"), nd.cb_btc);
        ParseCoinbase(HttpGet("api.coinbase.com","/api/v3/brokerage/market/products/ETH-USD/ticker"), nd.cb_eth);
        ParseCoinbase(HttpGet("api.coinbase.com","/api/v3/brokerage/market/products/LCX-USD/ticker"), nd.cb_lcx);

        // commit + detect price change for flash
        {
            std::lock_guard<std::mutex> lk(g_md_mtx);
            auto applyFlash=[](Tick& n, const Tick& o){
                n.prev_last = o.last;
                if(n.last>0 && o.last>0 && n.last!=o.last){
                    n.flash_t  = 1.2f;
                    n.flash_up = (n.last > o.last);
                } else {
                    n.flash_t  = o.flash_t;
                    n.flash_up = o.flash_up;
                }
            };
            applyFlash(nd.lcx_lcx,    g_md.lcx_lcx);
            applyFlash(nd.lcx_btc,    g_md.lcx_btc);
            applyFlash(nd.lcx_eth,    g_md.lcx_eth);
            applyFlash(nd.kraken_btc, g_md.kraken_btc);
            applyFlash(nd.kraken_eth, g_md.kraken_eth);
            applyFlash(nd.kraken_lcx, g_md.kraken_lcx);
            applyFlash(nd.cb_btc,     g_md.cb_btc);
            applyFlash(nd.cb_eth,     g_md.cb_eth);
            applyFlash(nd.cb_lcx,     g_md.cb_lcx);
            g_md = nd;
        }
        g_fetch_count++;
        Sleep(1000);
    }
}
