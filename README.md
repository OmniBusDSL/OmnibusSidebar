# OmnibusSidebar

**Desktop trading sidebar + OmniBus wallet**
**Stack:** C++17, Raylib 5.0, Dear ImGui 1.92, WinHTTP, DPAPI
**GitHub:** https://github.com/OmniBusDSL/OmnibusSidebar

---

## Ce este

Aplicație desktop Windows (sidebar lateral) cu:
- **Prețuri live** — LCX, Kraken, Coinbase (polling 1s, WinINet)
- **Wallet OmniBus** — balance + send direct la nod Zig via WinHTTP (fără Python)
- **Trading UI** — ordine BUY/SELL cu modal confirmare (semnătură HMAC TODO)
- **Grafice** — candlestick OHLCV, 5 timeframe-uri, zoom/scroll
- **SuperVault** — stocare criptată chei API via Windows DPAPI
- **Log** — ring buffer 256 entries, thread-safe

Fereastra este `UNDECORATED + TOPMOST + TRANSPARENT` — se lipește pe partea dreaptă a ecranului.

---

## Build

```bash
# Prerequisite: MinGW-w64 (Strawberry Perl include MinGW sau MSYS2)
# Raylib 5.0 în ./raylib_pkg/raylib-5.0_win64_mingw-w64/

cd "C:\Kits work\limaje de programare\OmnibusSidebar"
mingw32-make

# Output: OmnibusSidebar.exe (~2.3 MB, zero runtime deps)
```

---

## Structura proiectului

```
OmnibusSidebar/
├── main.cpp                  Entry: Raylib window, ImGui setup, 5 tabs, font loading
├── app_state.h               Tick/MarketData structs, mutex globale, font handles
├── fetch.cpp                 WinINet HTTP, parse JSON 3 exchange-uri, FetchLoop 1s
├── win_input_region.cpp      SetWindowRgn — click-through transparent zone
│
├── mod_prices.cpp            Tab PRICES: prețuri live cu flash animation
├── mod_trade.cpp             Tab TRADE: UI ordine BUY/SELL + modal confirmare
├── mod_charts.cpp            Candlestick OHLCV, 5 timeframe-uri, zoom/scroll
├── mod_wallet.cpp            Tab WALLET: WinHTTP → RPC 8332 (getbalance + sendtx)
├── mod_log.cpp               Tab LOG: ring buffer 256 entries
├── mod_toast.cpp             Toast notifications cu slide-in + timer
│
├── SuperVault/
│   ├── VaultCore/
│   │   ├── vault_core.h           C interface v4: 11 opcodes, VaultKeyEntry
│   │   └── vault_core_windows.cpp DPAPI CryptProtectData/Unprotect, vault.dat v4
│   ├── VaultService/
│   │   └── vault_service.cpp      Named Pipe daemon: \\.\pipe\OmnibusVault
│   ├── VaultClient/
│   │   ├── vault_client.h
│   │   └── vault_client.cpp       Client dual-mode (pipe + embedded)
│   ├── VaultManager/
│   │   ├── vault_manager.py       Tkinter GUI v3: 4 tab-uri complete (2130 linii)
│   │   └── vault_manager_gui.cpp  GUI Raylib+ImGui standalone
│   ├── OmnibusWallet/
│   │   ├── wallet_core.py         BIP-39/44 derivare via bip_utils
│   │   ├── wallet_store.py        DPAPI wallets.dat, atomic write
│   │   ├── pq_domain.py           4 domenii PQ non-transferabile, HKDF-SHA512
│   │   ├── pq_sign.py             PQ signing: liboqs (WSL/ctypes) + HMAC fallback
│   │   ├── balance_fetcher.py     19 blockchain-uri + OMNI RPC 8332
│   │   ├── send_transaction.py    SHA256d tx hash, secp256k1 sign, send OMNI
│   │   └── chains/                BIP44/84 derivare: btc/eth/sol/bnb/... + omni*.py
│   ├── mod_vault.cpp              Tab VAULT: DPAPI, vault.dat, SecureZeroMemory
│   └── mod_vault.h
│
├── imgui/                    Dear ImGui 1.92 surse
├── assets/                   Fonturi Inter (Bold, Medium, Regular)
├── imgui_impl_raylib.h       Backend Raylib pentru ImGui
├── rlImGui.cpp               rlImGui integration
├── Makefile                  Build: g++ -std=c++17, -lwinhttp, -lwininet, -lraylib
├── resource.rc               Version info
└── wiki-omnibus/             Documentație completă
    ├── INDEX.md              Inventar complet module + TODO
    └── OMNIBUS_ACADEMIC_REPORT.md  Audit cod, scoruri, roadmap
```

---

## Tab WALLET — Conexiune la nod Zig

`mod_wallet.cpp` se conectează direct la `omnibus-node.exe` via WinHTTP (fără Python subprocess):

```
OmnibusSidebar.exe
    → WinHTTP POST http://127.0.0.1:8332
        → getbalance   → address + balance OMNI + block height
        → sendtransaction(to, amount_sat) → txid
```

Nodul trebuie să ruleze înainte de a deschide tab-ul Wallet:
```bash
.\zig-out\bin\omnibus-node.exe --mode seed --node-id main
```

---

## SuperVault — Stocare criptată

Cheile API și seed-urile wallet sunt stocate în `%APPDATA%\OmnibusSidebar\vault.dat` (DPAPI encrypted).

```bash
# Build vault_service
g++ SuperVault/VaultService/vault_service.cpp SuperVault/VaultCore/vault_core_windows.cpp \
    -lcrypt32 -lshell32 -ladvapi32 -o vault_service.exe

# Pornire daemon
vault_service.exe

# GUI manager (Python)
cd SuperVault/VaultManager
python vault_manager.py
```

Named Pipe protocol: `\\.\pipe\OmnibusVault`
Request: `[opcode:1][exchange:1][slot:2][payload_len:2][payload]`
Response: `[error:1][payload_len:2][payload]`

---

## OmnibusWallet — 19 Blockchain-uri + 5 Domenii PQ

```python
from SuperVault.OmnibusWallet.wallet_core import create_wallet_entry
from SuperVault.OmnibusWallet.balance_fetcher import fetch_omni

# Creare wallet
entry = create_wallet_entry("MyWallet", mnemonic, ["BTC", "ETH", "OMNI"])

# Balance OMNI de la nod local
bal = fetch_omni(address, rpc_url="http://127.0.0.1:8332")
```

Blockchain-uri suportate: BTC, ETH, SOL, BNB, LTC, DOGE, BCH, XLM, XRP, OP, ADA, ATOM, DOT, EGLD, OMNI (+ 5 domenii PQ)

**5 Domenii Post-Quantum OMNI:**

| Prefix | CoinType | Algoritm |
|--------|----------|----------|
| `ob_omni_` | 777 | ML-KEM-768 (Kyber) |
| `ob_k1_` | 778 | ML-DSA (Dilithium-5) |
| `ob_f5_` | 779 | Falcon-512 |
| `ob_d5_` | 780 | SLH-DSA (SPHINCS+) |
| `ob_s3_` | 781 | Falcon-Light AES |

---

## Status implementare

| Componentă | Status | Scor |
|------------|--------|------|
| Prețuri live (3 exchange-uri) | Funcțional | 100% |
| Grafice candlestick | Funcțional | 100% |
| Tab WALLET (WinHTTP → RPC) | Funcțional | 90% |
| Tab LOG + Toasts | Funcțional | 100% |
| SuperVault DPAPI (Windows) | Funcțional | 90% |
| OmnibusWallet (19 chain-uri) | Funcțional | 90% |
| Domenii PQ (liboqs) | Parțial | 75% |
| Trading execution (HMAC sign) | TODO | 15% |
| SuperVault Linux (libsodium) | Planificat | 0% |

**Audit complet:** `wiki-omnibus/OMNIBUS_ACADEMIC_REPORT.md`

---

## Legătură cu OmniBus-BlockChainCore

- Nod Zig: https://github.com/SAVACAZAN/OmniBus-BlockChainCore
- `mod_wallet.cpp` → `getbalance` / `sendtransaction` pe port 8332
- Aceleași prefixe adrese (ob_omni_, ob_k1_, ob_f5_, ob_d5_, ob_s3_)
- Aceleași coin types 777-781 în Zig + Python + C++
