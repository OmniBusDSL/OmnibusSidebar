# OmnibusSidebar — Build & Integration Guide

## Structura folderului
```
OmnibusSidebar/
├── main.cpp          ← codul principal complet
├── rlImGui.cpp       ← descarcă de pe GitHub (vezi Pasul 3)
├── rlImGui.h         ← idem
├── resource.rc       ← iconița + versiune
├── Makefile          ← compilare one-click
├── assets/
│   └── app_icon.ico  ← iconița ta
└── imgui/
    ├── imgui.h / imgui.cpp
    ├── imgui_draw.cpp / imgui_widgets.cpp
    ├── imgui_tables.cpp / imgui_internal.h
    └── imconfig.h / imgui_demo.cpp (opțional)
```

---

## Pasul 1 — Instalează MinGW-w64 via MSYS2
```bash
# Descarcă MSYS2 de pe https://www.msys2.org/
# Apoi în MSYS2 MinGW64 terminal:
pacman -S mingw-w64-x86_64-gcc
pacman -S mingw-w64-x86_64-raylib
pacman -S make
```

## Pasul 2 — Descarcă Dear ImGui
```bash
git clone https://github.com/ocornut/imgui.git imgui
```
Sau ZIP de pe GitHub → copiezi fișierele .cpp/.h în `imgui/`.

## Pasul 3 — Descarcă rlImGui (puntea Raylib+ImGui)
```bash
git clone https://github.com/raylib-extras/rlImGui.git _tmp_rl
copy _tmp_rl\rlImGui.cpp .
copy _tmp_rl\rlImGui.h .
```

## Pasul 4 — Iconița
Pune fișierul tău `.ico` în `assets/app_icon.ico`.
Conversie PNG→ICO: https://convertio.co/png-ico/

## Pasul 5 — Compilează
```bash
cd "C:\Kits work\limaje de programare\OmnibusSidebar"
make
```
Rezultat: `OmnibusSidebar.exe` — sidebar fără consolă, with iconița ta.

---

## Cum conectezi endpoint-urile Python existente → C++

### Prețuri (deja integrate în main.cpp)

| Ce face | Fișier Python sursă | Endpoint folosit în C++ |
|---------|---------------------|-------------------------|
| LCX lastPrice | `TIER_1/LCX/lcx_public_endpoints.py` | `GET exchange-api.lcx.com/api/ticker?pair=LCX%2FUSDC` |
| BTC/USD Kraken | `TIER_1/KRAKEN/kraken_public_endpoints.py` | `GET api.kraken.com/0/public/Ticker?pair=XBTUSD` |
| ETH/USD Kraken | idem | `GET api.kraken.com/0/public/Ticker?pair=ETHUSD` |
| LCX Coinbase | `TIER_1/COINBASE/coinbase_public_endpoints.py` | `GET api.coinbase.com/api/v3/brokerage/market/products/LCX-USD/ticker` |

### Trading — cum adaugi semnătura reală

Caută în `main.cpp` comentariile:
```cpp
// ── TODO: call your LCX private endpoint here ─────────────────
// ── TODO: call your Kraken private endpoint here ───────────────
```

#### LCX (din `TIER_1/LCX/lcx_private_endpoints.py`)
```cpp
// Semnătura LCX — identic cu Python:
//   request_string = METHOD + endpoint + JSON(payload)
//   signature = base64(HMAC-SHA256(api_secret, request_string))
//
// POST https://exchange-api.lcx.com/api/create
// Headers:
//   x-access-key: <api_key>
//   x-access-sign: <signature>
//   x-access-timestamp: <timestamp_ms>
//   API-VERSION: 1.1.0
//   Content-Type: application/json
// Body:
//   {"pair":"LCX/USDC","side":"BUY","type":"LIMIT","amount":"1000","price":"0.0432"}
```

#### Kraken (din `TIER_1/KRAKEN/kraken_private_endpoints.py`)
```cpp
// POST https://api.kraken.com/0/private/AddOrder
// Headers:
//   API-Key: <api_key>
//   API-Sign: <HMAC-SHA512 signature>
// Body (form-encoded):
//   nonce=<nonce>&pair=LCXUSD&type=buy&ordertype=limit&volume=1000&price=0.0432
```

### WebSocket (viitor)
WebSocket-urile din:
- `TIER_1/LCX/lcx_websockets.py`     → subscribeTicker, subscribeOrderbook
- `TIER_1/KRAKEN/kraken_websockets.py` → ticker, book, trade
- `TIER_1/COINBASE/coinbase_websockets.py`

Pentru C++, poți adăuga mai târziu cu **libwebsockets** sau **IXWebSocket** (header-only).
Sau rulezi Python-ul ca proces separat și comunici prin pipe/socket local.

---

## Arhitectura prețurilor în main.cpp

```
FetchThread() [background thread]
    │
    ├── WinHttpGet(exchange-api.lcx.com, /api/ticker?pair=LCX/USDC)
    │     └── JsonExtract(response, "lastPrice") → lcx_kraken
    │
    ├── WinHttpGet(api.kraken.com, /0/public/Ticker?pair=XBTUSD)
    │     └── parse "c":[" → btc_kraken
    │
    ├── WinHttpGet(api.kraken.com, /0/public/Ticker?pair=ETHUSD)
    │     └── parse "c":[" → eth_kraken
    │
    └── WinHttpGet(api.coinbase.com, /api/v3/.../LCX-USD/ticker)
          └── JsonExtract(best_bid) + best_ask / 2 → lcx_coinbase

Main thread citește PriceData prin mutex → afișează în ImGui table
Auto-refresh la 60 secunde + buton manual "Refresh"
```

---

## Note importante
- **WinINet** = HTTP Windows built-in → zero dependențe externe
- **-mwindows** în Makefile = fără fereastră neagră de consolă
- **FLAG_WINDOW_TOPMOST** = rămâne deasupra Chrome, Excel etc.
- **FLAG_WINDOW_UNDECORATED** = fără bară de titlu
- Butonul **Fill** copiază prețul live în câmpul Limit Price automat
- BUY/SELL au modal de confirmare înainte de execuție
