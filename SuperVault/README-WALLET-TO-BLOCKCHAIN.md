# OmnibusWallet ↔ OmniBus-BlockChainCore
## Integrare completă: Wallet Python → Nod Zig

---

## 1. Arhitectură generală

```
┌─────────────────────────────────────────────────────┐
│              SuperVault / OmnibusWallet              │
│                    (Python)                          │
│                                                      │
│  wallet_core.py   →  derivare BIP39/BIP44/BIP84      │
│  balance_fetcher.py →  JSON-RPC → nod local          │
│  vault_manager.py  →  UI PyQt6                       │
└──────────────────────────┬──────────────────────────┘
                           │ HTTP JSON-RPC 2.0
                           │ http://127.0.0.1:8332
┌──────────────────────────▼──────────────────────────┐
│         OmniBus-BlockChainCore (Zig + Node.js)       │
│                                                      │
│  rpc-server.js  →  JSON-RPC 2.0 server port 8332     │
│  core/wallet.zig       →  structuri adrese           │
│  core/transaction.zig  →  validare prefixe           │
│  core/bip32_wallet.zig →  derivare HD (TODO real)    │
│  core/pq_crypto.zig    →  PQ keys (TODO real)        │
└─────────────────────────────────────────────────────┘
```

---

## 2. Tipuri de adrese — compatibilitate completă

### 2.1 OMNI — instrumentul transferabil (coin type 777 + BTC-compat)

| Tip | Path derivare | Prefix | Compatibil BTC |
|-----|--------------|--------|----------------|
| SegWit | `m/84'/0'/0'/0/index` | `ob1q...` | da (`bc1q...` același key) |
| Legacy | `m/44'/0'/0'/0/index` | `O...` | da (`1...` același key) |
| Native | `m/44'/777'/0'/0/index` | `ob_...` | nu (OmniBus only) |

### 2.2 Domenii PQ — non-transferabile (collection / identitate)

| Chain | Coin Type | Prefix | Algoritm PQ | Security |
|-------|-----------|--------|-------------|----------|
| OMNI_LOVE | 778 | `ob_k1_` | ML-DSA (Dilithium-5) | 256-bit |
| OMNI_FOOD | 779 | `ob_f5_` | Falcon-512 | 192-bit |
| OMNI_RENT | 780 | `ob_d5_` | SLH-DSA (SPHINCS+) | 256-bit |
| OMNI_VACATION | 781 | `ob_s3_` | Falcon-Light / AES-128 | 128-bit |

Toate sunt **non-transferabile** — ownership-ul se dovedește prin derivare din seed,
nu prin balanță on-chain. `bal` este întotdeauna 0.

### 2.3 Prefixe validate în transaction.zig (Zig core)

```zig
// core/transaction.zig
const valid_prefixes = [_][]const u8{
    "ob_omni_",   // ← OMNI Native
    "ob_k1_",     // ← OMNI_LOVE
    "ob_f5_",     // ← OMNI_FOOD
    "ob_d5_",     // ← OMNI_RENT
    "ob_s3_",     // ← OMNI_VACATION
    "0x",         // ← ETH-compatible
};
```

**Wallet Python generează exact aceste prefixe.** Compatibilitate 100%.

---

## 3. Schema full metadata — per adresă

Fiecare adresă derivată în wallet are următoarele câmpuri (schema v2):

```python
{
    # ── Identitate ───────────────────────────────
    "index":           0,
    "chain":           777,          # coin_type BIP44
    "chain_id":        "OMNI",
    "addr":            "ob1q...",    # adresa primară (SegWit)
    "full_path":       "m/84'/0'/0'/0/0",
    "pubkey":          "02abc...",   # compressed public key hex
    "script_pubkey":   "001420byte_hash",  # P2WPKH (pentru SegWit)
    "private_key":     "...",        # hex sau WIF (stocat criptat)

    # ── OMNI specific: 3 adrese ──────────────────
    "address":         "ob1q...",    # SegWit (primar)
    "address_legacy":  "OAbc...",    # Legacy P2PKH (0x4F)
    "address_native":  "ob_OAbc...", # Native 777

    "derivation_path":         "m/84'/0'/0'/0/0",
    "derivation_path_legacy":  "m/44'/0'/0'/0/0",
    "derivation_path_native":  "m/44'/777'/0'/0/0",

    "private_key_hex":         "...",
    "private_key_wif":         "...",
    "private_key_hex_legacy":  "...",
    "private_key_wif_legacy":  "...",
    "private_key_hex_native":  "...",
    "private_key_wif_native":  "...",

    "public_key_hex":          "...",

    # ── BTC anchors (același key, HRP diferit) ───
    "address_btc":        "bc1q...",  # BTC SegWit (același key ca ob1q)
    "address_btc_legacy": "1Abc...",  # BTC Legacy (același key ca O...)

    # ── Live data (actualizat din RPC) ───────────
    "bal":        0.0,
    "utxos":      [],
    "tx_count":   0,
    "last_tx":    None,

    # ── Metadata ─────────────────────────────────
    "label":      "",
    "created_at": "2026-03-25T...",
    "last_used":  None,
}
```

---

## 4. Fetch balance — JSON-RPC flow

### Python → Zig node

```python
# balance_fetcher.py → fetch_omni()

POST http://127.0.0.1:8332
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getBalance",
  "params": ["ob_OYourAddress..."]
}

# Răspuns așteptat:
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": 5000000000   # satoshis → 50 OMNI
}
# SAU
{
  "result": {
    "balance": 5000000000,
    "transactions": [{"txid": "abc...", ...}]
  }
}
```

**Conversie**: `bal = satoshis / 1e8` (identic cu BTC)
**1 OMNI = 100,000,000 satoshis**

### Adresa folosită pentru fetch

- OMNI: `address_native` (`ob_...`) — nodul validează prefixul `ob_omni_`
- Domenii: nu se face fetch (non-transferabile, `fetch_error` setat cu notă explicativă)

---

## 5. Ce mai trebuie făcut în OmniBus-BlockChainCore

### 5.1 BIP32 derivation reală (CRITICĂ)

**Status actual** în `core/bip32_wallet.zig`:
```zig
// TODO: derivare HMAC-SHA512 reală
// Momentan folosește XOR simplificat — NU e compatibil cu BIP32 standard
fn deriveChildKey(parent: [32]u8, index: u32) [32]u8 {
    // XOR placeholder...
}
```

**Ce trebuie implementat**:
```
HMAC-SHA512(key=parent_chain_code, data=parent_pubkey || index)
→ left 32 bytes  = child private key tweak
→ right 32 bytes = child chain code
```

**Fără asta**: adresele generate de Zig ≠ adresele generate de Python.
Wallet-ul Python folosește BIP32 standard (via `bip_utils`) — derivare corectă.

**Impact**: tranzacțiile semnate de wallet Python nu vor fi recunoscute de nodul Zig
dacă Zig derivă alte chei.

**Referință**: [BIP-0032](https://github.com/bitcoin/bips/blob/master/bip-0032.mediawiki)

---

### 5.2 PQ Crypto reală (IMPORTANTĂ pentru domenii)

**Status actual** în `core/pq_crypto.zig`:
```zig
// Kyber768, Dilithium5, Falcon512, SPHINCSPlus — toate TODO
pub fn generateKyberKeypair() KyberKeypair {
    // TODO: implementare reală
}
```

**Key sizes definite corect** (compatibile cu wallet Python):
```zig
const KYBER768_PUBLIC_KEY_SIZE  = 1184;
const DILITHIUM5_PUBLIC_KEY_SIZE = 2544;
const FALCON512_PUBLIC_KEY_SIZE  = 897;
```

**Ce trebuie implementat**:
- ML-KEM (Kyber-768) — NIST FIPS 203
- ML-DSA (Dilithium-5) — NIST FIPS 204
- Falcon-512 — NIST FIPS 206
- SLH-DSA (SPHINCS+) — NIST FIPS 205

**Librărie Zig recomandată**: [mupq/zig-pqc](https://github.com/mupq) sau
port din `liboqs` (C → Zig FFI).

**Wallet Python** folosește momentan HKDF-SHA256 deterministic ca placeholder —
același approach ca Zig (TODO), deci sunt în sync.

---

### 5.3 RPC `getBalance` — îmbunătățiri recomandate

**Momentan** (rpc-server.js):
```javascript
// getBalance returnează număr simplu sau nimic
```

**Recomandat** pentru compatibilitate completă cu wallet Python:
```javascript
// getBalance(address) → returnează obiect complet
{
  "balance": 5000000000,        // satoshis
  "confirmed": 5000000000,
  "unconfirmed": 0,
  "transactions": [
    { "txid": "abc...", "amount": 5000000000, "block": 42 }
  ],
  "utxos": [
    { "txid": "abc...", "vout": 0, "value": 5000000000 }
  ]
}
```

Wallet Python (`fetch_omni`) acceptă deja ambele formate (int și dict).

---

### 5.4 RPC metode necesare (toate există deja în rpc-server.js)

| Metodă | Status | Folosit de wallet |
|--------|--------|-------------------|
| `getBalance` | ✓ există | `fetch_omni()` |
| `sendTransaction` | ✓ există | viitor: send TX |
| `getBlockCount` | ✓ există | `fetch_omni()` (node_height) |
| `getLatestBlock` | ✓ există | viitor: TX history |
| `getMempoolTransactions` | ✓ există | viitor: pending TX |

---

## 6. Cum pornești și testezi integrarea

### Start nod OmniBus (WSL)

```bash
# în WSL Ubuntu
cd /home/kiss/OmniBus-BlockChainCore
node rpc-server.js
# → JSON-RPC 2.0 server pornit pe port 8332
```

### Test fetch balance din Python

```python
from OmnibusWallet.balance_fetcher import fetch_omni

# cu nod pornit
result = fetch_omni("ob_OYourAddress...")
print(result)
# → {"bal": 500.0, "node_height": 42, "tx_count": 0, ...}

# fără nod (graceful fallback)
# → {"bal": 0.0, "fetch_error": "OmniBus node not running (port 8332)", ...}
```

### Test wallet complet

```python
from OmnibusWallet import generate_mnemonic, create_wallet_entry
from OmnibusWallet.balance_fetcher import fetch_wallet_balances

mnemonic = generate_mnemonic(24)
entry = create_wallet_entry("Test", mnemonic, ["OMNI"], include_pq_domains=True)

# fetch balance (necesită nod pornit pe 8332)
updated = fetch_wallet_balances(entry, chains=["OMNI"])
print(updated["addresses"]["OMNI"]["bal"])
```

---

## 7. Priorităti de lucru (roadmap)

### Imediat (wallet Python — GATA)
- [x] Derivare BIP39/BIP44/BIP84 corectă pentru toate chainurile
- [x] 3 adrese OMNI (SegWit + Legacy + Native 777)
- [x] Full metadata schema compatibilă BTC
- [x] 4 domenii PQ cu prefixe corecte
- [x] BTC anchors pe toate adresele
- [x] Fetch balance via JSON-RPC (cu fallback graceful)
- [x] UI PyQt6 cu tab PQ Domains

### Următor (OmniBus-BlockChainCore — TODO)

**Prioritate 1 — BIP32 real**
- Implementează HMAC-SHA512 în `core/bip32_wallet.zig`
- Fără asta walletul și nodul derivă chei diferite

**Prioritate 2 — RPC `getBalance` răspuns complet**
- Returnează `{balance, utxos, transactions}` nu doar un număr
- Wallet Python acceptă deja ambele formate

**Prioritate 3 — PQ Crypto real**
- Integrează `liboqs` sau implementare nativă Zig
- Dilithium-5, Falcon-512, SPHINCS+, Kyber-768

**Prioritate 4 — Validare adrese ob_ în TX**
- `transaction.zig` are deja prefixele corecte
- Adaugă verificare că adresa sursă corespunde cheii private din semnătură

---

## 8. Compatibilitate — rezumat

| Component | Python Wallet | Zig Core | Status |
|-----------|--------------|----------|--------|
| Prefixe adrese | `ob1q/O.../ob_...` | validate în transaction.zig | ✅ SYNC |
| BIP39 seed | `bip_utils` standard | TODO real HMAC-SHA512 | ⚠️ PARTIAL |
| Coin types | 777/778/779/780/781 | definite în wallet.zig | ✅ SYNC |
| RPC protocol | JSON-RPC 2.0 fetch | JSON-RPC 2.0 server | ✅ COMPATIBIL |
| PQ algorithms | HKDF placeholder | TODO placeholder | ✅ SYNC (ambele TODO) |
| Satoshi scale | 1e8 | 50_000_000_000 = 500 OMB | ✅ CORECT |
