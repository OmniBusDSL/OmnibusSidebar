# OmnibusSidebar — Wiki Index

## Proiect
C++ trading sidebar: Raylib + Dear ImGui, Windows native.
Build: MinGW-w64 (g++), Makefile, `mingw32-make`

## Fișiere wiki

| Fișier | Conținut |
|--------|----------|
| BUILD_STEPS.md | Compilare C++ ImGui + Raylib, Makefile, endpoint-uri prețuri |
| VAULT_ARCHITECTURE.md | VaaS arhitectură: Named Pipe, DPAPI, opcodes, wire protocol |
| VAULT_README.md | vault.dat format, DPAPI encryption, UI tab VAULT |
| README-WALLET-TO-BLOCKCHAIN.md | Integrare Python wallet ↔ nod Zig JSON-RPC 2.0 |

## Module principale

| Fișier | Status | Descriere |
|--------|--------|-----------|
| main.cpp | ✅ | Entry point, tabs, font loading |
| mod_wallet.cpp | ✅ | Wallet tab — WinHTTP direct la RPC 8332 |
| mod_prices.cpp | ✅ | Prețuri live LCX/Kraken/Coinbase |
| mod_trade.cpp | ⏳ | Trading — semnături HMAC-SHA256 TODO |
| mod_charts.cpp | ✅ | Grafice prețuri |
| mod_log.cpp | ✅ | Log panel |
| mod_toast.cpp | ✅ | Notificări |
| SuperVault/mod_vault.cpp | ✅ | Tab VAULT — stocare criptată chei API |
| SuperVault/VaultService/ | ✅ | Daemon Named Pipe Windows |
| SuperVault/VaultClient/ | ✅ | Client C++ pentru vault |
| SuperVault/OmnibusWallet/ | ✅ | Python: BIP39, 5 domenii PQ, JSON-RPC |

## Stack

- C++17, Dear ImGui 1.92, Raylib 5.0, rlImGui
- WinHTTP (HTTP direct, fără libcurl)
- DPAPI (criptare vault.dat)
- Python 3.12 (OmnibusWallet — separat)

## TODO prioritar

1. `mod_trade.cpp` — semnături reale HMAC-SHA256 (Kraken, LCX)
2. SuperVault Linux support (libsodium în loc de DPAPI)
3. Windows Hello / biometrie pentru vault unlock
4. POST autentificat real pentru trading

## Conexiune cu blockchain

`mod_wallet.cpp` → HTTP POST `http://127.0.0.1:8332` → `omnibus-node.exe`
- `getbalance` → address + balance OMNI + block height
- `sendtransaction` → to_address + amount_sat → txid
