# OmnibusSidebar v4.0

Transparent crypto price ticker + trading terminal sidebar for Windows.
Always-on-top, click-through in background, 1s live data from 3 exchanges.

---

## Ce face

- Sidebar floating pe dreapta ecranului (430px), transparent in rest
- Preturi live: **LCX**, **Kraken**, **Coinbase** — BTC, ETH, LCX
- Flash animatie la schimbare de pret (verde = up, rosu = down)
- Tab TRADE: formular de ordine cu BUY/SELL + confirmare modal
- Tab LOG: mesaje colorate, buffer circular 256 linii
- Fereastra flotanta de **candlestick charts** cu volume bars
- Toast notifications cu animatie slide-in + fade-out
- Inchidere cu **Alt+F4**

---

## Structura fisiere

```
OmnibusSidebar/
├── main.cpp              # Entry point, init Raylib + ImGui, main loop, header, tabs, footer
├── app_state.h           # Structs globale: Tick, MarketData, fonts, g_md, g_run, g_monW/H
│
├── fetch.cpp / .h        # Thread background HTTP polling @ 1s
│                         #   HttpGet()     — WinINet HTTPS GET
│                         #   Jx()          — JSON key extractor minimal (fara librarie)
│                         #   ParseLCX()    — JSON LCX ticker
│                         #   ParseKraken() — JSON Kraken ticker
│                         #   ParseCoinbase()— JSON Coinbase ticker
│                         #   FetchLoop()   — thread principal fetch + flash trigger
│
├── mod_prices.cpp / .h   # Tab PRICES
│                         #   FlashColor()      — interpolare culoare pe timer
│                         #   PriceCell()       — celula pret cu decimale adaptive
│                         #   ExchangeSection() — tabel BID/ASK/LAST/SPREAD% per exchange
│                         #   DrawPricesTab()   — 3 sectiuni (LCX blue, Kraken purple, CB green)
│
├── mod_trade.cpp / .h    # Tab TRADE
│                         #   Selector exchange + asset
│                         #   Input amount + limit price + buton Fill
│                         #   BUY / SELL cu modal de confirmare
│                         #   DoOrder() — logheaza + toast (fara executie API inca)
│
├── mod_log.cpp / .h      # Tab LOG
│                         #   Buffer circular g_log[256] cu mutex
│                         #   Log() — adauga linie colorata, auto-scroll
│                         #   DrawLogTab() — render scrollabil
│
├── mod_toast.cpp / .h    # Notificari toast
│                         #   PushToast() — adauga notificare (max 5 simultane)
│                         #   DrawToasts() — slide-in, progress bar, fade-out, 3.5s durata
│
├── mod_charts.cpp / .h   # Fereastra flotanta candlestick
│                         #   ParseKrakenOHLC() / ParseCoinbaseCandles() / ParseLCXKline()
│                         #   FetchCandles()    — thread fetch ~200 lumanari
│                         #   DrawCandlesticks()— corp + fitil + volume + grid + last price line
│                         #   DrawChartsWindow()— fereastra ImGui flotanta stanga
│                         #   DrawChartsButton()— buton din header sidebar
│
├── win_input_region.cpp / .h  # Windows-only input region
│                              #   UpdateInputRegion() — SetWindowRgn() via WinAPI
│                              #   Sidebar closed: input doar pe dreapta 430px
│                              #   Chart open: input pe tot ecranul
│
├── assets/
│   ├── Inter-Regular.ttf  # Font UI 14px
│   ├── Inter-Medium.ttf   # Font UI default 14px
│   └── Inter-Bold.ttf     # Font titluri 15px, 22px
│
├── imgui/                 # Dear ImGui source (ocornut/imgui)
│   ├── imgui.cpp / .h
│   ├── imgui_draw.cpp
│   ├── imgui_widgets.cpp
│   └── imgui_tables.cpp
│
├── rlImGui.cpp / .h       # Bridge Raylib ↔ ImGui (raylib-extras/rlImGui)
├── imgui_impl_raylib.h    # Header compatibilitate
│
├── raylib_pkg/            # Raylib 5.0 win64 mingw-w64 (headers + lib)
│   └── raylib-5.0_win64_mingw-w64/
│       ├── include/       # raylib.h
│       └── lib/           # libraylib.a
│
├── resource.rc            # Icon aplicatie + versiune (Windows VERSIONINFO)
├── Makefile               # Build cu mingw32-make
└── OmnibusSidebar.exe     # Executabil final
```

---

## Librarii folosite

| Librarie | Versiune | Scop |
|----------|----------|------|
| **Raylib** | 5.0 | Fereastra, rendering, 60 FPS, input |
| **Dear ImGui** | latest | UI: widgets, tabs, tabele, modals, tooltips |
| **rlImGui** | latest | Bridge Raylib ↔ ImGui |
| **WinINet** | built-in Windows | HTTP/HTTPS GET (fara curl) |
| **WinAPI** | built-in Windows | Window region, input management |
| **Inter** | font TTF | Typography: Regular, Medium, Bold |

---

## API Endpoints folosite

### Ticker live (polling 1s)

| Exchange | URL | Date returnate |
|----------|-----|----------------|
| LCX | `exchange-api.lcx.com/api/ticker?pair=BTC%2FUSDC` | lastPrice, bestBid, bestAsk |
| LCX | `exchange-api.lcx.com/api/ticker?pair=ETH%2FUSDC` | same |
| LCX | `exchange-api.lcx.com/api/ticker?pair=LCX%2FUSDC` | same |
| Kraken | `api.kraken.com/0/public/Ticker?pair=XBTUSD` | c (last), a (ask), b (bid) |
| Kraken | `api.kraken.com/0/public/Ticker?pair=ETHUSD` | same |
| Kraken | `api.kraken.com/0/public/Ticker?pair=LCXUSD` | same |
| Coinbase | `api.coinbase.com/api/v3/brokerage/market/products/BTC-USD/ticker` | best_bid, best_ask, price |
| Coinbase | `api.coinbase.com/api/v3/brokerage/market/products/ETH-USD/ticker` | same |
| Coinbase | `api.coinbase.com/api/v3/brokerage/market/products/LCX-USD/ticker` | same |

### Candles (la cerere, din Charts)

| Exchange | URL | Format |
|----------|-----|--------|
| Kraken | `api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=60` | `[time, o, h, l, c, vwap, vol]` |
| Coinbase | `api.coinbase.com/.../candles?granularity=3600` | `{start, open, high, low, close, volume}` |
| LCX | `api-kline.lcx.com/v1/market/kline?pair=BTC%2FUSDC&resolution=1h` | `{data:[{time, open, high, low, close, volume}]}` |

Toate endpoint-urile sunt **publice** (fara autentificare).

---

## Build

### Cerinte

- **MinGW-w64** cu g++ (testat cu Strawberry Perl / MSYS2)
- Raylib 5.0 inclus in `raylib_pkg/`

### Compilare

```bash
# Din MSYS2 / MinGW terminal:
cd "/c/Kits work/limaje de programare/OmnibusSidebar"

# Cu Makefile (necesita icon in assets/app_icon.ico):
mingw32-make

# Sau direct cu g++ (fara icon):
RAYLIB="raylib_pkg/raylib-5.0_win64_mingw-w64"
g++ -std=c++17 -O2 -I. -Iimgui -I"$RAYLIB/include" -DWIN32_LEAN_AND_MEAN \
  main.cpp fetch.cpp mod_toast.cpp mod_log.cpp mod_prices.cpp mod_trade.cpp \
  mod_charts.cpp rlImGui.cpp win_input_region.cpp \
  imgui/imgui.cpp imgui/imgui_draw.cpp imgui/imgui_widgets.cpp imgui/imgui_tables.cpp \
  -L"$RAYLIB/lib" -lraylib -lopengl32 -lgdi32 -lwinmm -lwininet -mwindows \
  -o OmnibusSidebar.exe
```

### Output

`OmnibusSidebar.exe` — executabil standalone, fara dependente externe, fara fereastra console.

---

## Utilizare

1. Porneste `OmnibusSidebar.exe`
2. Sidebar-ul apare pe dreapta ecranului, mereu deasupra
3. Click in afara sidebar-ului trece direct la aplicatia de dedesubt (click-through)
4. Butonul `CHARTS` din header deschide fereastra flotanta de candlestick
5. **Alt+F4** pentru inchidere

---

## Arhitectura tehnica

```
main.cpp
  └── init Raylib (transparent, undecorated, topmost, fullscreen)
  └── init ImGui (rlImGui bridge, 5 fonturi Inter)
  └── thread: FetchLoop() — HTTP polling 1s
  └── main loop @ 60 FPS:
        ├── snapshot MarketData (mutex)
        ├── UpdateInputRegion() daca s-a schimbat starea chart
        ├── BeginDrawing() — background transparent
        ├── DrawRectangle() — sidebar background + accent stripes
        ├── rlImGuiBegin()
        │     ├── Header (titlu + buton charts)
        │     ├── TabBar:
        │     │     ├── DrawPricesTab(md, dt)
        │     │     ├── DrawTradeTab(md)
        │     │     └── DrawLogTab()
        │     └── DrawChartsWindow()   ← fereastra flotanta
        ├── rlImGuiEnd()
        ├── DrawToasts(dt)             ← overlay peste tot
        └── EndDrawing()
```

---

## Adaugare modul nou

1. Creeaza `mod_xyz.h` + `mod_xyz.cpp`
2. Include in `main.cpp`: `#include "mod_xyz.h"`
3. Adauga in Makefile la `SOURCES`
4. Apeleaza `DrawXyzTab()` in sectiunea TabBar din `main.cpp`

---

## Limitari cunoscute

- Trade execution: interfata UI completa, API calls de executie nu sunt inca implementate
- Windows only (WinAPI pentru input region + WinINet pentru HTTP)
- Fara WebSocket (REST polling la 1s)
- Fara autentificare / balance display / order management
