"""
OmnibusWallet -- wallet_core.py
Core: mnemonic generation, derivation, vault storage.
"""
import json
import datetime
from bip_utils import Bip39MnemonicGenerator, Bip39WordsNum, Bip39MnemonicValidator

from .chains import CHAINS


def generate_mnemonic(words: int = 24) -> str:
    """Generate a new BIP39 mnemonic. 12 or 24 words."""
    count = Bip39WordsNum.WORDS_NUM_24 if words == 24 else Bip39WordsNum.WORDS_NUM_12
    return str(Bip39MnemonicGenerator().FromWordsNumber(count))


def validate_mnemonic(mnemonic: str) -> bool:
    try:
        return Bip39MnemonicValidator(mnemonic).IsValid()
    except Exception:
        return False


def _script_pubkey(address: str, chain: str) -> str:
    """
    Generate P2WPKH script_pubkey for segwit addresses (0014<20-byte-hash>).
    For non-segwit / non-BTC returns empty string — filled later by blockchain API.
    """
    try:
        if chain == "BTC" and address.startswith(("bc1q", "bc1p")):
            import base64, hashlib
            # bech32 decode → witness program
            from bip_utils import SegwitBech32Decoder
            wit_ver, wit_prog = SegwitBech32Decoder.Decode("bc", address)
            prog_hex = bytes(wit_prog).hex()
            return f"{wit_ver:02x}14{prog_hex}" if wit_ver == 0 else ""
    except Exception:
        pass
    return ""


def _derive_full(mnemonic: str, chain: str, passphrase: str, index: int = 0) -> dict:
    """
    Derive full address metadata for a chain at given index.
    Follows the schema:
      index, addr, full_path, chain (int coin_type), pubkey, script_pubkey,
      bal, utxos, tx_count, last_tx, label, created_at, last_used
    BTC additionally includes legacy address fields.
    """
    chain = chain.upper()
    mod   = CHAINS[chain]
    raw   = mod.derive(mnemonic, passphrase, index)
    now   = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # coin_type per BIP44 (for reference)
    _COIN_TYPE = {
        "BTC": 0, "LTC": 2, "DOGE": 3, "ETH": 60, "ATOM": 118,
        "XRP": 144, "BCH": 145, "XLM": 148, "ADA": 1815, "DOT": 354,
        "SOL": 501, "EGLD": 508, "BNB": 60, "OP": 60,
        "OMNI": 777,
    }

    data = {
        # ── Identity ────────────────────────────────────────────
        "index":        index,
        "chain":        _COIN_TYPE.get(chain, 0),
        "chain_id":     chain,
        "addr":         raw.get("address", ""),
        "full_path":    raw.get("derivation_path", ""),
        "pubkey":       raw.get("public_key_hex", ""),
        "script_pubkey": raw.get("script_pubkey") or _script_pubkey(raw.get("address",""), chain),
        # ── Private key (kept for completeness, stored encrypted) ─
        "private_key":  raw.get("private_key_hex") or raw.get("private_key_wif") or "",
        # ── Live data (updated from blockchain API) ──────────────
        "bal":          0.0,
        "utxos":        [],
        "tx_count":     0,
        "last_tx":      None,
        # ── Metadata ────────────────────────────────────────────
        "label":        "",
        "created_at":   now,
        "last_used":    None,
        # ── Keep raw fields for UI display ───────────────────────
        "address":          raw.get("address", ""),
        "public_key_hex":   raw.get("public_key_hex", ""),
        "derivation_path":  raw.get("derivation_path", ""),
    }

    # Private key variants
    if raw.get("private_key_hex"):
        data["private_key_hex"] = raw["private_key_hex"]
    if raw.get("private_key_wif"):
        data["private_key_wif"] = raw["private_key_wif"]

    # BTC: derive legacy address separately
    if chain == "BTC":
        legacy = mod.derive(mnemonic, passphrase, index, segwit=False)
        data["address_legacy"]         = legacy["address"]
        data["private_key_wif_legacy"] = legacy["private_key_wif"]
        data["derivation_path_legacy"] = legacy["derivation_path"]
        data["addr_legacy"]            = legacy["address"]
        data["full_path_legacy"]       = legacy["derivation_path"]

    # OMNI: all 3 addresses already in raw — just map them
    if chain == "OMNI":
        data["address_legacy"]           = raw.get("address_legacy", "")
        data["addr_legacy"]              = raw.get("address_legacy", "")
        data["full_path_legacy"]         = raw.get("derivation_path_legacy", "")
        data["derivation_path_legacy"]   = raw.get("derivation_path_legacy", "")
        data["private_key_wif_legacy"]   = raw.get("private_key_wif_legacy", "")
        data["private_key_hex_legacy"]   = raw.get("private_key_hex_legacy", "")
        data["address_native"]           = raw.get("address_native", "")
        data["full_path_native"]         = raw.get("derivation_path_native", "")
        data["derivation_path_native"]   = raw.get("derivation_path_native", "")
        data["private_key_wif_native"]   = raw.get("private_key_wif_native", "")
        data["private_key_hex_native"]   = raw.get("private_key_hex_native", "")
        data["pubkey_native"]            = raw.get("public_key_hex_native", "")
        data["address_btc_legacy"]       = raw.get("address_btc_legacy", "")

    # Extra raw fields (segwit flag etc.)
    if "segwit" in raw:
        data["segwit"] = raw["segwit"]
    if raw.get("note"):
        data["note"] = raw["note"]

    # BTC anchor address (OMNI chain + domain chains)
    if raw.get("address_btc"):
        data["address_btc"] = raw["address_btc"]

    # OmniBus domain chains — extra metadata
    if raw.get("domain"):
        data["domain"]           = raw["domain"]
        data["prefix"]           = raw.get("prefix", "")
        data["pq_algorithm"]     = raw.get("pq_algorithm", "")
        data["pq_variant"]       = raw.get("pq_variant", "")
        data["security_bits"]    = raw.get("security_bits", 0)
        data["nist_level"]       = raw.get("nist_level")
        data["purpose"]          = raw.get("purpose", "")
        data["non_transferable"] = True   # collection/identity, not a coin
        if raw.get("address_btc"):
            data["address_btc"]  = raw["address_btc"]

    return data


def derive_wallet(mnemonic: str, chain: str, passphrase: str = "", index: int = 0) -> dict:
    """Derive a single address for the given chain."""
    chain = chain.upper()
    if chain not in CHAINS:
        raise ValueError(f"Unsupported chain: {chain}. Available: {list(CHAINS.keys())}")
    return CHAINS[chain].derive(mnemonic, passphrase, index)


def create_wallet_entry(label: str, mnemonic: str, chains: list,
                        passphrase: str = "",
                        include_pq_domains: bool = False) -> dict:
    """
    Create a full wallet entry — full metadata for every chain.
    BTC includes both segwit and legacy addresses.
    Mnemonic + passphrase are secrets, stored encrypted.

    include_pq_domains: if True, derive all 5 OmniBus PQ domains and
                        include them as entry["pq_domains"].
    """
    addresses = {}
    for chain in chains:
        chain = chain.upper()
        if chain in CHAINS:
            addresses[chain] = _derive_full(mnemonic, chain, passphrase)

    entry = {
        "label":      label,
        "mnemonic":   mnemonic,
        "passphrase": passphrase,
        "addresses":  addresses,
        "chains":     [c.upper() for c in chains if c.upper() in CHAINS],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "version":    2,
    }

    if include_pq_domains:
        from .pq_domain import generate_pq_domains
        entry["pq_domains"] = generate_pq_domains(mnemonic, passphrase)

    return entry


def wallet_entry_to_json(entry: dict) -> str:
    return json.dumps(entry, indent=2)


def wallet_entry_from_json(s: str) -> dict:
    return json.loads(s)


def get_address(entry: dict, chain: str) -> str:
    chain = chain.upper()
    return entry.get("addresses", {}).get(chain, {}).get("address", "")


def add_chain_to_entry(entry: dict, chain: str) -> dict:
    """Add a new chain's full metadata to an existing wallet entry."""
    chain = chain.upper()
    if chain not in CHAINS:
        raise ValueError(f"Unsupported chain: {chain}")
    mnemonic   = entry["mnemonic"]
    passphrase = entry.get("passphrase", "")
    entry["addresses"][chain] = _derive_full(mnemonic, chain, passphrase)
    if chain not in entry.get("chains", []):
        entry.setdefault("chains", []).append(chain)
    return entry
