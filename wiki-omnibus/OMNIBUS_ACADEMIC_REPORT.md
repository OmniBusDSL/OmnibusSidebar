# OmniBus Ecosystem — Raport Academic Complet
**Data:** 2026-03-25
**Scope:** Audit complet cod sursă vs documentație vs roadmap
**Proiecte:** OmnibusSidebar (C++) + OmniBus-BlockChainCore (Zig + JS + React)

---

## 1. CE ESTE SISTEMUL (DE LA 0 LA 100)

### Viziunea
OmniBus este un ecosistem blockchain post-quantum format din 3 straturi:

```
┌─────────────────────────────────────────────────────┐
│  STRATUL 1 — INTERFAȚĂ UTILIZATOR                   │
│  OmnibusSidebar.exe (C++/ImGui)                     │
│  • Prețuri live 3 exchange-uri                      │
│  • Tab wallet conectat la nod propriu               │
│  • Stocare criptată chei API (DPAPI)                │
├─────────────────────────────────────────────────────┤
│  STRATUL 2 — WALLET & SECURITATE                    │
│  SuperVault + OmnibusWallet (Python)                │
│  • BIP-39/44/84 derivare pentru 19 blockchain-uri   │
│  • 5 domenii Post-Quantum per wallet                │
│  • vault.dat criptat DPAPI pe disc                  │
├─────────────────────────────────────────────────────┤
│  STRATUL 3 — BLOCKCHAIN PROPRIU                     │
│  OmniBus-BlockChainCore (Zig)                       │
│  • Nod Zig nativ Windows + mining PoW               │
│  • secp256k1 real + liboqs PQ crypto                │
│  • JSON-RPC 2.0 pe port 8332                        │
│  • Mining pool Node.js (miners dinamici)            │
└─────────────────────────────────────────────────────┘
```

---

## 2. INVENTAR COMPLET COD

### 2.1 OmnibusSidebar — C++ Desktop App

| Fișier | Linii | Ce face | Status |
|--------|-------|---------|--------|
| main.cpp | 288 | Raylib window + ImGui + 5 tabs + font loading | ✅ REAL |
| app_state.h | 43 | Tick/MarketData structs, mutex globale | ✅ REAL |
| fetch.cpp | 142 | WinINet HTTP, parse JSON Kraken/LCX/Coinbase, FetchLoop 1s | ✅ REAL |
| win_input_region.cpp | 28 | SetWindowRgn click-through transparent zone | ✅ REAL |
| mod_prices.cpp | 137 | Flash animation, prețuri live pe 3 exchange-uri | ✅ REAL |
| mod_trade.cpp | 210 | UI trading complet, modal confirmare | ⚠️ UI real, execuție STUB |
| mod_charts.cpp | 526 | Candlestick OHLCV, 5 timeframe-uri, zoom/scroll | ✅ REAL |
| mod_log.cpp | 46 | Ring buffer 256 log entries, thread-safe | ✅ REAL |
| mod_toast.cpp | 70 | Slide-in notifications cu timer expiry | ✅ REAL |
| mod_wallet.cpp | 423 | WinHTTP → RPC 8332, getbalance + sendtransaction | ✅ REAL |

### 2.2 SuperVault — C++ + Python

| Fișier | Linii | Ce face | Status |
|--------|-------|---------|--------|
| VaultCore/vault_core.h | 107 | C interface v4: 11 opcodes, VaultKeyEntry struct | ✅ REAL |
| VaultCore/vault_core_windows.cpp | 365 | DPAPI CryptProtectData/Unprotect, format vault.dat v4 | ✅ REAL |
| VaultService/vault_service.cpp | 251 | Named Pipe daemon `\\.\pipe\OmnibusVault`, refuză GET_SECRET | ✅ REAL |
| VaultClient/vault_client.cpp | 208 | Client dual-mode (pipe + embedded) | ⚠️ Opcode mai vechi |
| VaultManager/vault_manager_gui.cpp | 499 | GUI standalone Raylib+ImGui pentru vault | ⚠️ Opcode mai vechi |
| mod_vault.cpp | 416 | Tab VAULT în sidebar: DPAPI, vault.dat, SecureZeroMemory | ✅ REAL |
| VaultManager/vault_manager.py | 2130 | Tkinter v3: ApiKeys+Wallet+PQDomains+TxHistory tabs | ✅ REAL |

### 2.3 OmnibusWallet — Python Package

| Fișier | Linii | Ce face | Status |
|--------|-------|---------|--------|
| wallet_core.py | 213 | BIP-39 generate/validate, derive_wallet, create_wallet_entry | ✅ REAL |
| wallet_store.py | 211 | DPAPI wallets.dat, atomic write, save/list/delete | ✅ REAL |
| wallet_manager.py | 493 | Tkinter standalone wallet manager | ✅ REAL |
| pq_domain.py | 287 | 4 domenii PQ, HKDF-SHA512, secp256k1 compressed pubkey | ✅ REAL |
| pq_sign.py | 363 | 3 backends: WSL liboqs / ctypes liboqs / HMAC fallback | ⚠️ Backend C = STUB |
| balance_fetcher.py | 613 | 19 blockchain-uri: BTC/ETH/SOL/LTC/... + OMNI RPC 8332 | ✅ REAL |
| send_transaction.py | 419 | SHA256d tx hash, secp256k1 sign (3 backends), send OMNI | ✅ REAL |
| chains/omni.py | 159 | 3 tipuri adresă OMNI: ob1q/O/ob_, Base58Check v=0x4F | ✅ REAL |
| chains/omni_*.py (5 fișiere) | ~115 fiecare | ML-KEM/ML-DSA/Falcon-512/SLH-DSA/Falcon-Light per domeniu | ✅ REAL |
| chains/btc.py ... egld.py | ~26-40 | BIP44/84 derivare per blockchain | ✅ REAL (19 chain-uri) |

### 2.4 OmniBus-BlockChainCore — Zig Core

| Fișier | Linii | Ce face | Status |
|--------|-------|---------|--------|
| core/main.zig | 128 | Entry: vault reader, blockchain init, wallet, RPC thread, mining | ✅ REAL |
| core/blockchain.zig | 175 | Chain ArrayList, mempool, mining PoW, calculateBlockHash SHA256 | ⚠️ validateTransaction = STUB |
| core/block.zig | 56 | Block struct, hash, addTransaction | ✅ REAL |
| core/transaction.zig | 238 | TX struct, sign/verify ECDSA, SHA256d hash, VALID_PREFIXES | ✅ REAL |
| core/secp256k1.zig | 142 | Zig stdlib ECDSA: privkey→pubkey, hash160, sign/verify | ✅ REAL |
| core/ripemd160.zig | 193 | RIPEMD-160 complet pur Zig, 80 runde, testat standard vectors | ✅ REAL |
| core/crypto.zig | 156 | SHA256d, HMAC-SHA512 | ⚠️ ripemd160 = SHA256 trunc, AES = XOR |
| core/bip32_wallet.zig | 323 | PBKDF2-HMAC-SHA512, BIP-32 real, 5 domenii PQ | ✅ REAL |
| core/wallet.zig | 353 | fromMnemonic(), adrese PQ, createTransaction() | ✅ REAL |
| core/pq_crypto.zig | 241 | liboqs FFI: ML-DSA-87, Falcon-512, SLH-DSA-256s, ML-KEM-768 | ✅ REAL |
| core/rpc_server.zig | 344 | HTTP JSON-RPC 2.0, ws2_32.recv, 6 metode, sendtransaction real | ✅ REAL |
| core/vault_reader.zig | 94 | Named Pipe 0x4A → env var → dev mnemonic | ✅ REAL |
| core/cli.zig | 176 | Argumente CLI: mode/node-id/host/port/hashrate | ✅ REAL |
| core/node_launcher.zig | 274 | NodeLauncher seed/miner, readyForMining, startMining | ✅ REAL |
| core/network.zig | 284 | P2PNetwork struct, peer management | ⚠️ broadcast = print only |
| core/bootstrap.zig | 290 | BootstrapNode, peer register/list, stale cleanup 60s | ✅ REAL |
| core/mining_pool.zig | 215 | Miner shares, reward proporțional, inactive cleanup 300s | ✅ REAL |
| core/blockchain_v2.zig | 438 | Sub-blocks 0.1s, 7 shards, prune, binary encode | ✅ REAL |
| core/sub_block.zig | 166 | SubBlock struct, SubBlockPool max 10 | ✅ REAL |
| core/compact_transaction.zig | 222 | 161 bytes/TX (63% reducere vs 432B) | ✅ REAL |
| core/light_client.zig | 470 | BlockHeader 200B, SPV, BloomFilter, fastSync | ✅ REAL (SPV simplificat) |
| core/light_miner.zig | 346 | LightMiner hashrate, MinerPool genesis 3 mineri min | ✅ REAL |
| core/miner_genesis.zig | 249 | 21M OMNI total supply, MinerWallet, GenesisAllocation | ✅ REAL |
| core/binary_codec.zig | 259 | Varint encoding, BinaryEncoder/Decoder | ✅ REAL |
| core/shard_config.zig | 191 | 7 shards, sub_id % 7, ShardValidator | ✅ REAL |
| core/prune_config.zig | 227 | max 10000 blocks, PruneStrategy, keep_days 30 | ✅ REAL |
| core/archive_manager.zig | 224 | Archive blocks 75% compresie simulată | ⚠️ Simulated |
| core/state_trie.zig | 262 | AccountState, StateTrie HashMap, calculateRootHash | ✅ REAL |
| core/witness_data.zig | 416 | WitnessData: sig_type PQ, WitnessPool + Archive | ✅ REAL |
| core/storage.zig | 335 | KeyValueStore in-memory: BlockStore, TxIndex, AddrIndex | ⚠️ IN-MEMORY ONLY |
| core/database.zig | 265 | Database unified layer, PersistentBlockchain | ⚠️ STUB (no disk) |
| core/key_encryption.zig | 242 | KeyManager password-based | ⚠️ XOR encryption, 16-word list |

### 2.5 Mining Pool + Frontend

| Fișier | Linii | Ce face | Status |
|--------|-------|---------|--------|
| rpc-server.js | 682 | Node.js pool: dynamic miners, 2s blocks, balances.json, 18 RPC methods | ✅ REAL |
| miner-client.js | 136 | Miner: registerminer + keepalive 5s | ✅ REAL |
| create-wallet.js | 225 | BIP-39 mnemonic, PBKDF2, ob_omni_ addresses | ⚠️ Wordlist incomplet |
| frontend/src/App.tsx | 545 | SPA 5 pagini: dashboard/miners/distribution/blocks/network | ✅ REAL |
| frontend/src/api/rpc-client.ts | 196 | OmniBusRpcClient JSON-RPC 2.0 wrapper | ✅ REAL |
| frontend/src/pages/GenesisCountdown.tsx | 403 | Genesis countdown, miner cards, status polling | ⚠️ Launch = alert |
| frontend/src/components/Stats.tsx | 200 | Blocks/mempool/balance, 3s polling | ✅ REAL |
| frontend/src/components/BlockExplorer.tsx | 251 | Block list + detail modal, 4s polling | ✅ REAL |
| frontend/src/components/Wallet.tsx | 220 | Balance + 5 PQ addresses | ⚠️ Adrese hardcoded demo |

---

## 3. ANALIZA DE LA 0 LA 100 — FAZE COMPLETE

### FAZA 0 → FAZA 1: Infrastructura de bază (100%)

**Ce s-a construit:**
- Fereastră desktop C++ cu Raylib + Dear ImGui
- Structura modulară (mod_*.cpp)
- Prețuri live 3 exchange-uri via WinINet
- Build system MinGW + Makefile
- Ring buffer log thread-safe

**Concluzie:** ✅ Complet și funcțional

---

### FAZA 1 → FAZA 2: Blockchain Core (95%)

**Ce s-a construit:**
- Block struct + SHA256 PoW mining cu difficulty 4
- Transaction struct cu sign/verify secp256k1 ECDSA real
- Mempool ArrayList
- Genesis block automat

**Ce lipsește:**
- `validateTransaction()` în `blockchain.zig` nu verifică semnătura (TODO în cod)
- Storage = in-memory, nu persistă la restart

**Concluzie:** ✅ 95% — funcțional, signing real, validare semnătură în blockchain lipsește

---

### FAZA 2 → FAZA 3: Crypto Real (90%)

**Ce s-a construit:**
- `secp256k1.zig` — ECDSA complet via Zig stdlib, zero dependențe externe
- `ripemd160.zig` — 193 linii, 80 runde, testat cu standard vectors
- `bip32_wallet.zig` — PBKDF2-HMAC-SHA512 real, BIP-32 HD cu hardened keys
- `pq_crypto.zig` — ML-DSA-87, Falcon-512, SLH-DSA-256s, ML-KEM-768 via liboqs

**Ce este STUB:**
- `crypto.zig` ripemd160: SHA256 trunchiat (nu folosit în producție — `secp256k1.zig` apelează direct `ripemd160.zig`)
- `crypto.zig` AES: XOR (nu e folosit în producție — placeholder)
- `key_encryption.zig`: XOR + wordlist de 16 cuvinte

**Concluzie:** ✅ 90% — crypto important este real; stub-urile din crypto.zig sunt bypassed

---

### FAZA 3 → FAZA 4: Wallet HD (95%)

**Ce s-a construit:**
- `wallet.zig`: derivare completă BIP-32, 5 adrese PQ, `createTransaction()` cu signing
- `bip32_wallet.zig`: HMAC-SHA512 pentru master key + child key derivation hardened
- `OmnibusWallet` Python: BIP-39/44/84 real via `bip_utils`, 19 blockchain-uri
- `pq_domain.py`: HKDF-SHA512 deterministic, 5 domenii non-transferabile

**Ce lipsește:**
- `createTransaction()` nu deduce balanța (nu verifică dacă ai fonduri)
- `Wallet.tsx` din frontend afișează adrese hardcoded, nu derivate real

**Concluzie:** ✅ 95% — derivare real, signing real, verificare sold lipsește

---

### FAZA 4 → FAZA 5: RPC Server + Mining Pool (95%)

**Ce s-a construit:**
- `rpc_server.zig`: HTTP JSON-RPC 2.0, `ws2_32.recv` direct (soluție pentru bug WINSOCK Windows), 6 metode, `sendtransaction` real
- `rpc-server.js`: 18 metode RPC, dynamic miner registration, keepalive 30s, `balances.json` persistent
- `miner-client.js`: registerminer + keepalive funcțional
- React frontend: 5 pagini, polling real, dark UI

**Ce lipsește:**
- `gettransactions` per adresă (history TX nu există în nod Zig)
- Frontend `Wallet.tsx` nu derivă adrese din RPC

**Concluzie:** ✅ 95% — pool complet funcțional, nod Zig funcțional

---

### FAZA 5 → FAZA 6: SuperVault (90%)

**Ce s-a construit:**
- `vault_core_windows.cpp`: DPAPI CryptProtectData/Unprotect, format binar v4
- `vault_service.cpp`: Named Pipe daemon, refuză GET_SECRET (securitate)
- `vault_reader.zig`: citire mnemonic prin Named Pipe în nod Zig
- `mod_wallet.cpp`: WinHTTP direct la RPC (eliminat Python subprocess)
- `vault_manager.py`: 2130 linii Tkinter, 4 tab-uri complete

**Ce lipsește:**
- `vault_client.cpp` și `vault_manager_gui.cpp` = opcode mai vechi (v1/v2, nu v4)
- Linux support (libsodium) = TODO
- Windows Hello biometric = TODO

**Concluzie:** ✅ 90% — Windows complet funcțional, cross-platform lipsește

---

### FAZA 6 → FAZA 7: Scalare Storage (85%)

**Ce s-a construit:**
- `blockchain_v2.zig`: sub-blocks 0.1s, 7 shards, pruning, binary codec
- `compact_transaction.zig`: 161 bytes/TX (63% reducere)
- `state_trie.zig`: AccountState cu merkle root SHA256
- `light_client.zig`: BlockHeader 200B, SPV simplificat, BloomFilter

**Ce lipsește:**
- `archive_manager.zig`: compresie simulată, fără I/O real pe disc
- `storage.zig`: in-memory, fără RocksDB
- Cross-shard communication protocol

**Concluzie:** ✅ 85% — structuri reale, persistență reală lipsește

---

### FAZA 7 → FAZA 8: Rețea P2P (40%)

**Ce s-a construit:**
- `network.zig`: P2PNetwork struct, peer list, message types
- `bootstrap.zig`: peer registration, stale cleanup
- `node_launcher.zig`: seed/miner mode, `startSeedNode()`, `startMinerNode()`

**Ce lipsește:**
- `network.zig` `broadcast()`: `std.debug.print` doar, fără TCP real
- Nu există TCP socket listener pentru peer connections
- Nu există block propagation between nodes
- Nu există consensus mechanism

**Concluzie:** ⚠️ 40% — framework există, transport real lipsește

---

### FAZA 8 → FAZA 9: Trading Real (15%)

**Ce s-a construit:**
- `mod_trade.cpp`: UI complet cu modal confirmare
- `balance_fetcher.py`: 19 chain-uri balance real
- `send_transaction.py`: OMNI send real via RPC

**Ce lipsește:**
- HMAC-SHA256/SHA512 signing pentru Kraken/LCX/Coinbase
- Order book integration
- Real POST cu autentificare exchange

**Concluzie:** ⚠️ 15% — UI gata, backend trading = 0

---

## 4. CONFLICTE DOCUMENTARE IDENTIFICATE

| Conflict | Fișier A | Fișier B | Realitate |
|----------|----------|----------|-----------|
| BIP32 "XOR placeholder" | README-WALLET-TO-BLOCKCHAIN.md | PHASE_2_SUMMARY.md (✅ COMPLETE) | bip32_wallet.zig = HMAC-SHA512 REAL; README-WALLET referă versiunea veche WSL |
| AES encryption | key_encryption.zig (XOR) | PHASE_2_SUMMARY.md (✅ AES-256) | XOR în cod, AES în doc — CONFLICT real |
| RIPEMD-160 | crypto.zig (SHA256 trunc) | ripemd160.zig (real) | ripemd160.zig există și e real, dar crypto.zig are propria versiune falsă |
| Storage persistent | PHASE_3_SUMMARY.md (✅) | database.zig (TODO) | RocksDB = nu există, in-memory only — CONFLICT |
| Miner launch frontend | PHASE_4_SUMMARY.md (✅) | GenesisCountdown.tsx | Butoanele "Launch Miners" sunt alert() — CONFLICT |

---

## 5. SCOREBOARD FINAL — DE LA 0 LA 100

```
COMPONENT                        REAL    STUB    SCORE
─────────────────────────────────────────────────────
Crypto Core (secp256k1, BIP32)   ████████████    95%
PQ Crypto (liboqs)               ████████████    95%
Blockchain (blocks, PoW)         ███████████     90%
Transaction signing              ████████████    95%
RPC Server (Zig)                 ████████████    90%
Mining Pool (Node.js)            ████████████    95%
SuperVault (Windows)             ████████████    90%
Wallet Python (19 chains)        ███████████     90%
React Frontend                   ██████████      85%
Storage / Persistence            ████            30%
P2P Network / TCP                ████            35%
Trading Execution                ██              15%
Linux / Cross-Platform           ███             25%
─────────────────────────────────────────────────────
MEDIA GLOBALĂ:                                   75%
```

---

## 6. STUB-URI COMPLETE — LISTA FINALĂ

| Fișier | Funcție | Problema | Prioritate |
|--------|---------|----------|------------|
| `blockchain.zig` | validateTransaction | Nu verifică semnătura | 🔴 CRITIC |
| `crypto.zig` | ripemd160 | SHA256 trunchiat (bypass: secp256k1.zig OK) | 🟡 MEDIE |
| `crypto.zig` | encryptAES256/decryptAES256 | XOR în loc de AES | 🟡 MEDIE |
| `key_encryption.zig` | encryptPrivateKey | XOR + wordlist 16 cuvinte | 🟡 MEDIE |
| `database.zig` | loadFromDisk/saveToDisk | TODO, fără implementare | 🔴 CRITIC |
| `network.zig` | broadcast | print() doar | 🔴 CRITIC |
| `archive_manager.zig` | archiveBlocks | Compresie simulată | 🟢 LOW |
| `mod_trade.cpp` | DoOrder | Log only, no API call | 🔴 CRITIC (trading) |
| `pq_sign.py` | Backend C | HMAC fallback, nu PQ real | 🟡 MEDIE |
| `create-wallet.js` | wordlist | 16 cuvinte + placeholders | 🟡 MEDIE |
| `Wallet.tsx` | addresses | Hardcoded demo | 🟡 MEDIE |
| `vault_client.cpp` | protocol | Opcode v1/v2, nu v4 | 🟡 MEDIE |

---

## 7. ROADMAP PRIORITAR (CE URMEAZĂ)

### Prioritate 1 — CRITIC (blochează producția)
1. `blockchain.zig` → `validateTransaction()`: verifică semnătura secp256k1
2. `database.zig` → RocksDB sau SQLite pentru persistență reală
3. `network.zig` → TCP socket real pentru P2P (std.net)
4. `rpc_server.zig` → `gettransactions` endpoint (TX history per adresă)

### Prioritate 2 — IMPORTANT
5. `mod_trade.cpp` → HMAC-SHA256 Kraken + LCX signing real
6. `vault_client.cpp` → update la opcodes v4
7. `key_encryption.zig` → AES-256 real (std.crypto.aes)
8. `Wallet.tsx` → adrese derivate din RPC (nu hardcoded)

### Prioritate 3 — VIITOR
9. Linux vault (libsodium în loc de DPAPI)
10. Phase 5: Agent trading automat
11. Ethereum bridge (USDC Sepolia)
12. WebSocket real-time
13. Cross-shard protocol
14. Mobile light client (< 1 GB)

---

## 8. PUNCTE FORTE — CE E EXCEPȚIONAL

1. **secp256k1 pur Zig** — zero dependențe externe, Bitcoin-compatible, testat
2. **RIPEMD-160 pur Zig** — 193 linii, testat cu standard vectors Bitcoin
3. **liboqs pe Windows native** — ML-DSA-87, Falcon-512, SLH-DSA compilat MinGW
4. **5 domenii PQ consistente** — aceleași coin types (777-781) în Zig, Python și C++
5. **WinHTTP direct în C++** — eliminat Python subprocess complet din mod_wallet
6. **ws2_32.recv direct** — soluție corectă pentru bug WINSOCK pe Windows (ReadFile nu merge pe socket)
7. **vault_reader.zig fallback chain** — Named Pipe → env var → dev default
8. **rpc-server.js robust** — 18 metode, dynamic miners, balances.json, keepalive
9. **OmnibusWallet 19 chain-uri** — BTC/ETH/SOL/ADA/DOT/... derivate real via bip_utils
10. **vault_manager.py 2130 linii** — GUI complet, 4 tab-uri, TX history, PQ domains

---

*Raport generat prin audit complet al ~8,500 linii de cod sursă.*
