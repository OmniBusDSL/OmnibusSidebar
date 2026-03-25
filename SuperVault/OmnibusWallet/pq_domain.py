"""
OmnibusWallet -- pq_domain.py
PQDomainDerivation: Post-Quantum domain derivation for OmniBus blockchain.

Delegates to the 5 OmniBus domain chain modules (omni_omni, omni_love, etc.)
and returns full metadata identical to wallet_core._derive_full schema.

Domain map:
  Index 0: omnibus.omni     ob_omni_   ML-KEM   (Kyber-768)        256-bit  NIST L3  Key Encapsulation
  Index 1: omnibus.love     ob_k1_     ML-DSA   (Dilithium-5)      256-bit  NIST L5  Digital Signatures
  Index 2: omnibus.food     ob_f5_     Falcon-512                  192-bit           Compact Signatures
  Index 3: omnibus.rent     ob_d5_     SLH-DSA  (SPHINCS+)         256-bit           Hash-based Sigs
  Index 4: omnibus.vacation ob_s3_     Falcon Light / AES-128      128-bit  NIST L1  Mobile/IoT

Architecture:
  - OMNI     = instrument de interacțiune cu chain-ul (transferabil)
  - celelalte 4 domenii = colecție / identitate / recompense (non-transferabile)

Full address metadata schema (matches wallet_core._derive_full):
  index, addr, address, full_path, derivation_path, chain (coin_type int),
  chain_id, pubkey, public_key_hex, script_pubkey, private_key, private_key_hex,
  bal, utxos, tx_count, last_tx, label, created_at, last_used,
  domain, prefix, pq_algorithm, pq_variant, security_bits, nist_level,
  purpose, non_transferable, address_btc

Standalone usage:
  from OmnibusWallet.pq_domain import generate_pq_domains
  domains = generate_pq_domains(mnemonic, passphrase="")
  # domains["omnibus.omni"]["addr"]  → ob_omni_1A2b...
  # domains["omnibus.love"]["addr"]  → ob_k1_1Xf4...

Integration with wallet_core:
  entry = create_wallet_entry(label, mnemonic, chains=["BTC","OMNI_OMNI","OMNI_LOVE"],
                              include_pq_domains=True)
"""

import datetime

# ── Chain module map ──────────────────────────────────────────
from .chains import omni_love, omni_food, omni_rent, omni_vacation

_DOMAIN_MODULES = {
    # omnibus.omni removed — use OMNI chain directly (same coin_type 777)
    "omnibus.love":     omni_love,
    "omnibus.food":     omni_food,
    "omnibus.rent":     omni_rent,
    "omnibus.vacation": omni_vacation,
}

# Spec list (for UI / introspection — no private data)
OMNIBUS_DOMAINS = [
    # Note: omnibus.omni (coin 777) = OMNI chain — used directly for transactions
    # PQ domains are 4 non-transferable collection/identity domains:
    {
        "domain_index": 1,
        "domain":        "omnibus.love",
        "chain_id":      "OMNI_LOVE",
        "prefix":        "ob_k1_",
        "pq_algorithm":  "ML-DSA",
        "pq_variant":    "Dilithium-5",
        "security_bits": 256,
        "nist_level":    5,
        "purpose":       "Digital signatures — wallets / identity",
        "coin_type":     778,
        "non_transferable": True,
    },
    {
        "domain_index": 2,
        "domain":        "omnibus.food",
        "chain_id":      "OMNI_FOOD",
        "prefix":        "ob_f5_",
        "pq_algorithm":  "Falcon-512",
        "pq_variant":    "Falcon-512",
        "security_bits": 192,
        "nist_level":    None,
        "purpose":       "Compact signatures — retail / food",
        "coin_type":     779,
        "non_transferable": True,
    },
    {
        "domain_index": 3,
        "domain":        "omnibus.rent",
        "chain_id":      "OMNI_RENT",
        "prefix":        "ob_d5_",
        "pq_algorithm":  "SLH-DSA",
        "pq_variant":    "SPHINCS+",
        "security_bits": 256,
        "nist_level":    None,
        "purpose":       "Hash-based signatures — contracts / rent",
        "coin_type":     780,
        "non_transferable": True,
    },
    {
        "domain_index": 4,
        "domain":        "omnibus.vacation",
        "chain_id":      "OMNI_VACATION",
        "prefix":        "ob_s3_",
        "pq_algorithm":  "Falcon-Light",
        "pq_variant":    "AES-128 / Falcon Light",
        "security_bits": 128,
        "nist_level":    1,
        "purpose":       "Mobile / IoT compatible",
        "coin_type":     781,
        "non_transferable": True,
    },
]

# Quick lookup by domain name
_DOMAIN_SPEC = {d["domain"]: d for d in OMNIBUS_DOMAINS}


# ── Full metadata builder ─────────────────────────────────────
def _derive_domain_full(mnemonic: str, domain: str,
                        passphrase: str = "", index: int = 0) -> dict:
    """
    Derive full metadata for one OmniBus PQ domain.
    Uses the domain's chain module (omni_omni.derive, etc.)
    Returns schema identical to wallet_core._derive_full.
    """
    mod  = _DOMAIN_MODULES[domain]
    spec = _DOMAIN_SPEC[domain]
    now  = datetime.datetime.now(datetime.timezone.utc).isoformat()

    raw = mod.derive(mnemonic, passphrase, index)

    data = {
        # ── Identity ─────────────────────────────────────────
        "index":            index,
        "domain_index":     spec["domain_index"],
        "domain":           domain,
        "chain_id":         spec["chain_id"],
        "chain":            spec["coin_type"],       # BIP44 coin_type
        "prefix":           spec["prefix"],
        # ── Address ──────────────────────────────────────────
        "addr":             raw.get("address", ""),
        "address":          raw.get("address", ""),
        "full_path":        raw.get("derivation_path", ""),
        "derivation_path":  raw.get("derivation_path", ""),
        # ── Keys ─────────────────────────────────────────────
        "pubkey":           raw.get("public_key_hex", ""),
        "public_key_hex":   raw.get("public_key_hex", ""),
        "script_pubkey":    raw.get("script_pubkey", ""),
        "private_key":      raw.get("private_key_hex", ""),
        "private_key_hex":  raw.get("private_key_hex", ""),
        # ── Bitcoin anchor ───────────────────────────────────
        "address_btc":      raw.get("address_btc", ""),
        # ── PQ metadata ──────────────────────────────────────
        "pq_algorithm":     spec["pq_algorithm"],
        "pq_variant":       spec["pq_variant"],
        "security_bits":    spec["security_bits"],
        "nist_level":       spec["nist_level"],
        "purpose":          spec["purpose"],
        "non_transferable": True,
        # ── Live data (updated from blockchain API) ───────────
        "bal":              0.0,
        "utxos":            [],
        "tx_count":         0,
        "last_tx":          None,
        # ── Metadata ─────────────────────────────────────────
        "label":            "",
        "created_at":       now,
        "last_used":        None,
    }

    if raw.get("private_key_wif"):
        data["private_key_wif"] = raw["private_key_wif"]
    if raw.get("note"):
        data["note"] = raw["note"]

    return data


# ── Public API ────────────────────────────────────────────────
def generate_pq_domains(mnemonic: str, passphrase: str = "",
                        index: int = 0) -> dict:
    """
    Generate all 5 OmniBus PQ domain entries from a BIP39 mnemonic.

    Returns:
      {
        "omnibus.omni":     { full metadata — addr = ob_omni_1A2b... },
        "omnibus.love":     { full metadata — addr = ob_k1_1Xf4...  },
        "omnibus.food":     { full metadata — addr = ob_f5_1Qq1...  },
        "omnibus.rent":     { full metadata — addr = ob_d5_1Ss3...  },
        "omnibus.vacation": { full metadata — addr = ob_s3_1Uu5...  },
      }

    All entries follow wallet_core._derive_full schema.
    Each includes:
      - addr / address: ob_<prefix>_<Base58Check>
      - address_btc: Bitcoin P2WPKH anchor address
      - public_key_hex, private_key_hex, private_key_wif
      - derivation_path: m/44'/<coin_type>'/0'/0/<index>
      - script_pubkey: P2WPKH (from BTC anchor)
      - bal, utxos, tx_count, last_tx (live data, starts at 0)
      - non_transferable: True
    """
    return {
        domain: _derive_domain_full(mnemonic, domain, passphrase, index)
        for domain in _DOMAIN_MODULES
    }


def generate_pq_domain(mnemonic: str, domain: str,
                       passphrase: str = "", index: int = 0) -> dict:
    """
    Generate a single OmniBus PQ domain entry.
    domain: "omnibus.omni" | "omnibus.love" | "omnibus.food" |
            "omnibus.rent" | "omnibus.vacation"
    """
    if domain not in _DOMAIN_MODULES:
        raise ValueError(
            f"Unknown domain '{domain}'. "
            f"Available: {list(_DOMAIN_MODULES.keys())}"
        )
    return _derive_domain_full(mnemonic, domain, passphrase, index)


def pq_domain_list() -> list:
    """Return domain spec list (no keys, just definitions)."""
    return list(OMNIBUS_DOMAINS)


def add_pq_domains_to_wallet(wallet_entry: dict, passphrase: str = "",
                              index: int = 0) -> dict:
    """
    Add PQ domain data to an existing wallet entry.
    Modifies wallet_entry in-place and returns it.
    """
    mnemonic = wallet_entry.get("mnemonic", "")
    if not mnemonic:
        raise ValueError("wallet_entry missing mnemonic")
    wallet_entry["pq_domains"] = generate_pq_domains(mnemonic, passphrase, index)
    return wallet_entry


def sign_pq_domains_in_wallet(wallet_entry: dict, message: bytes) -> dict:
    """
    Sign a message with all 4 PQ domains present in wallet_entry.

    Uses pq_domains[domain]["private_key_hex"] as BIP32-derived seed for each domain.
    Falls back to addresses[chain_id] if pq_domains not populated.

    Returns:
        {
          "omnibus.love":     {"backend": "liboqs-wsl", "sig_bytes": 4627, ...},
          "omnibus.food":     {...},
          "omnibus.rent":     {...},
          "omnibus.vacation": {...},
        }
    """
    from .pq_sign import sign_pq_domain

    _chain_map = {
        "omnibus.love":     "OMNI_LOVE",
        "omnibus.food":     "OMNI_FOOD",
        "omnibus.rent":     "OMNI_RENT",
        "omnibus.vacation": "OMNI_VACATION",
    }

    results = {}
    pq_domains = wallet_entry.get("pq_domains", {})
    addresses  = wallet_entry.get("addresses", {})

    for domain, chain_id in _chain_map.items():
        # Try pq_domains first, then addresses fallback
        priv_hex = ""
        if domain in pq_domains:
            info = pq_domains[domain]
            priv_hex = (info.get("private_key_hex") or
                        info.get("private_key") or "")
        if not priv_hex and chain_id in addresses:
            info = addresses[chain_id]
            priv_hex = (info.get("private_key_hex_native") or
                        info.get("private_key_hex") or
                        info.get("private_key") or "")

        if not priv_hex or len(priv_hex) < 64:
            results[domain] = {"success": False,
                               "error": f"No private key for {domain}"}
            continue

        priv_seed = bytes.fromhex(priv_hex[:64])
        results[domain] = sign_pq_domain(domain, priv_seed, message)

    return results
