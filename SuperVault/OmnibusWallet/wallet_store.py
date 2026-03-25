"""
OmnibusWallet -- wallet_store.py
Secure wallet storage using Windows DPAPI directly.
Completely independent from vault_service.exe / API key storage.

Storage: %APPDATA%/OmnibusSidebar/wallets.dat
Format:  DPAPI-encrypted JSON blob
         {
           "version": 1,
           "wallets": [
             {
               "id":         "uuid",
               "label":      "My Wallet",
               "mnemonic":   "word1 word2 ...",
               "passphrase": "",
               "addresses":  { "BTC": {...}, "ETH": {...}, ... },
               "chains":     ["BTC", "ETH", ...],
               "created_at": "2026-03-25T...",
               "source":     "omnibus_generated" | "imported"
             },
             ...
           ]
         }

The entire JSON is encrypted with DPAPI (CryptProtectData) with
descriptor "OmnibusWallets" — only the current Windows user can decrypt.
No vault_service.exe required.
"""

import os
import json
import uuid
import datetime
import ctypes
from ctypes import wintypes

# ── DPAPI via ctypes ──────────────────────────────────────────
crypt32  = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

_DPAPI_DESC = "OmnibusWallets"

def _dpapi_encrypt(plaintext: bytes) -> bytes:
    desc = ctypes.c_wchar_p(_DPAPI_DESC)
    inp  = DATA_BLOB(len(plaintext),
                     (ctypes.c_ubyte * len(plaintext))(*plaintext))
    out  = DATA_BLOB()
    ok   = crypt32.CryptProtectData(
        ctypes.byref(inp), desc, None, None, None,
        0,  # CRYPTPROTECT_UI_FORBIDDEN not set — allow silent
        ctypes.byref(out))
    if not ok:
        raise OSError(f"CryptProtectData failed: {kernel32.GetLastError()}")
    result = bytes(out.pbData[:out.cbData])
    kernel32.LocalFree(out.pbData)
    return result

def _dpapi_decrypt(ciphertext: bytes) -> bytes:
    inp = DATA_BLOB(len(ciphertext),
                    (ctypes.c_ubyte * len(ciphertext))(*ciphertext))
    out = DATA_BLOB()
    ok  = crypt32.CryptUnprotectData(
        ctypes.byref(inp), None, None, None, None, 0,
        ctypes.byref(out))
    if not ok:
        raise OSError(f"CryptUnprotectData failed: {kernel32.GetLastError()}")
    result = bytes(out.pbData[:out.cbData])
    kernel32.LocalFree(out.pbData)
    return result

# ── Storage path ──────────────────────────────────────────────
def _wallets_path() -> str:
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    folder  = os.path.join(appdata, "OmnibusSidebar")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "wallets.dat")

# ── Load / Save ───────────────────────────────────────────────
def _load_store() -> dict:
    path = _wallets_path()
    if not os.path.exists(path):
        return {"version": 1, "wallets": []}
    try:
        with open(path, "rb") as f:
            cipher = f.read()
        plain = _dpapi_decrypt(cipher)
        return json.loads(plain.decode("utf-8"))
    except Exception as e:
        print(f"[WalletStore] load failed: {e}")
        return {"version": 1, "wallets": []}

def _save_store(store: dict):
    path   = _wallets_path()
    plain  = json.dumps(store, ensure_ascii=False, indent=2).encode("utf-8")
    cipher = _dpapi_encrypt(plain)
    # Write atomically via temp file
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(cipher)
    if os.path.exists(path):
        os.replace(tmp, path)
    else:
        os.rename(tmp, path)
    print(f"[WalletStore] saved {len(store['wallets'])} wallet(s) to {path}")

# ── Public API ────────────────────────────────────────────────
def wallet_list() -> list:
    """Return list of wallet dicts (includes mnemonic — handle with care)."""
    return _load_store().get("wallets", [])

def wallet_save(label: str, mnemonic: str, passphrase: str,
                addresses: dict, chains: list,
                source: str = "omnibus_generated",
                pq_domains: dict = None) -> str:
    """
    Save a new wallet. Returns the wallet id.
    Raises on duplicate label.
    pq_domains: optional dict from pq_domain.generate_pq_domains()
    """
    store = _load_store()
    # Duplicate label check
    for w in store["wallets"]:
        if w["label"].lower() == label.lower():
            raise ValueError(f"Wallet '{label}' already exists.")

    entry = {
        "id":         str(uuid.uuid4()),
        "label":      label,
        "mnemonic":   mnemonic,
        "passphrase": passphrase,
        "addresses":  addresses,
        "chains":     chains,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source":     source,
    }
    if pq_domains:
        entry["pq_domains"] = pq_domains
    store["wallets"].append(entry)
    _save_store(store)
    return entry["id"]

def wallet_delete(wallet_id: str) -> bool:
    """Delete wallet by id. Returns True if found and deleted."""
    store = _load_store()
    before = len(store["wallets"])
    store["wallets"] = [w for w in store["wallets"] if w["id"] != wallet_id]
    if len(store["wallets"]) == before:
        return False
    _save_store(store)
    return True

def wallet_get(wallet_id: str) -> dict | None:
    """Get a single wallet by id."""
    for w in _load_store().get("wallets", []):
        if w["id"] == wallet_id:
            return w
    return None

def wallet_count() -> int:
    return len(_load_store().get("wallets", []))


def wallet_update_address_meta(wallet_id: str, chain: str, fields: dict) -> bool:
    """
    Update live fields for a specific chain address inside a wallet.
    Typical use: update bal, utxos, tx_count, last_tx, last_used after
    fetching from blockchain API.

    fields example:
      {
        "bal": 0.05,
        "utxos": [{"txid":"abc","vout":0,"amount":0.01,"confirmations":12}],
        "tx_count": 2,
        "last_tx": "def456",
        "last_used": "2026-03-25T12:00:00+00:00"
      }

    Returns True if wallet found and saved.
    """
    store = _load_store()
    for w in store["wallets"]:
        if w["id"] == wallet_id:
            chain = chain.upper()
            if chain not in w.get("addresses", {}):
                return False
            w["addresses"][chain].update(fields)
            _save_store(store)
            return True
    return False


def wallet_update(wallet_id: str, fields: dict) -> bool:
    """
    Update top-level wallet fields (e.g. label).
    Cannot be used to change mnemonic or id.
    """
    protected = {"id", "mnemonic", "passphrase"}
    store = _load_store()
    for w in store["wallets"]:
        if w["id"] == wallet_id:
            for k, v in fields.items():
                if k not in protected:
                    w[k] = v
            _save_store(store)
            return True
    return False
