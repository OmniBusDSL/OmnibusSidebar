"""
OmnibusWallet -- OmniBus chain (OmniBus Blockchain)
Chain ID:   OMNI

3 address types:
  1. SegWit   m/84'/0'/0'/0/index  → ob1q...  (HRP 'ob', P2WPKH) — BTC-compatible
  2. Legacy   m/44'/0'/0'/0/index  → O...     (version 0x4F, P2PKH) — BTC-compatible
  3. Native   m/44'/777'/0'/0/index → ob_...  (OmniBus blockchain, coin type 777)

Bitcoin compatibility (SegWit + Legacy):
  Same seed + same path → same private key as BTC.
  ob1q... ↔ bc1q...  (same key, different HRP)
  O...    ↔ 1...     (same key, different version byte)

OmniBus Native (777):
  Independent key, OmniBus blockchain only, no BTC equivalent.

Reference: https://github.com/SAVACAZAN/OmniBus-BlockChainCore
"""
import hashlib

CHAIN_ID    = "OMNI"
CHAIN_NAME  = "OmniBus"
COIN_SYMBOL = "OMB"

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    r = ""
    while n > 0:
        n, rem = divmod(n, 58)
        r = _B58[rem] + r
    return "1" * (len(data) - len(data.lstrip(b"\x00"))) + r

def _checksum(d: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(d).digest()).digest()[:4]

def _hash160(d: bytes) -> bytes:
    return hashlib.new("ripemd160", hashlib.sha256(d).digest()).digest()

def _p2pkh(pub: bytes, version: int) -> str:
    h    = _hash160(pub)
    full = bytes([version]) + h
    return _b58encode(full + _checksum(full))

def _p2wpkh(pub: bytes, hrp: str) -> str:
    try:
        from bip_utils import P2WPKHAddrEncoder
        return P2WPKHAddrEncoder.EncodeKey(pub, hrp=hrp)
    except Exception:
        return ""

def _script_pubkey(address: str, hrp: str) -> str:
    try:
        from bip_utils import SegwitBech32Decoder
        wv, wp = SegwitBech32Decoder.Decode(hrp, address)
        return f"{wv:02x}14{bytes(wp).hex()}" if wv == 0 else ""
    except Exception:
        return ""

def _wif(priv: bytes) -> str:
    raw = b"\x80" + priv + b"\x01"
    return _b58encode(raw + _checksum(raw))

def _bip32_node(seed: bytes, purpose: int, coin: int, index: int):
    from bip_utils import Bip32Slip10Secp256k1, Bip32KeyIndex
    bip32 = Bip32Slip10Secp256k1.FromSeed(seed)
    return (bip32
            .ChildKey(Bip32KeyIndex.HardenIndex(purpose))
            .ChildKey(Bip32KeyIndex.HardenIndex(coin))
            .ChildKey(Bip32KeyIndex.HardenIndex(0))
            .ChildKey(0)
            .ChildKey(index))


def derive(mnemonic: str, passphrase: str = "", index: int = 0) -> dict:
    """
    Derive all 3 OmniBus address types from the same mnemonic.

    Returns full metadata with:
      address / addr          = ob1q...  (SegWit, primary)
      address_legacy          = O...     (Legacy P2PKH)
      derivation_path         = m/84'/0'/0'/0/index
      derivation_path_legacy  = m/44'/0'/0'/0/index
      address_native          = ob_...   (OmniBus native, coin 777)
      derivation_path_native  = m/44'/777'/0'/0/index
      address_btc             = bc1q...  (BTC SegWit anchor, same key)
      address_btc_legacy      = 1...     (BTC Legacy anchor, same key)
    """
    from bip_utils import Bip39SeedGenerator, Bip84, Bip84Coins, Bip44, Bip44Coins, Bip44Changes

    seed = Bip39SeedGenerator(mnemonic).Generate(passphrase)

    # ── 1. SegWit  m/84'/0'/0'/0/index ──────────────────────
    bip84  = Bip84.FromSeed(seed, Bip84Coins.BITCOIN)
    sw_node = bip84.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)
    sw_pub  = sw_node.PublicKey().RawCompressed().ToBytes()
    sw_priv = sw_node.PrivateKey().Raw().ToBytes()
    sw_path = f"m/84'/0'/0'/0/{index}"

    omni_segwit = _p2wpkh(sw_pub, hrp="ob")    # ob1q...
    btc_segwit  = _p2wpkh(sw_pub, hrp="bc")    # bc1q...
    script_pk   = _script_pubkey(omni_segwit, "ob")

    # ── 2. Legacy  m/44'/0'/0'/0/index ──────────────────────
    bip44  = Bip44.FromSeed(seed, Bip44Coins.BITCOIN)
    lg_node = bip44.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)
    lg_pub  = lg_node.PublicKey().RawCompressed().ToBytes()
    lg_priv = lg_node.PrivateKey().Raw().ToBytes()
    lg_path = f"m/44'/0'/0'/0/{index}"

    omni_legacy = _p2pkh(lg_pub, 0x4F)          # O... / Y...
    btc_legacy  = _p2pkh(lg_pub, 0x00)          # 1...

    # ── 3. Native  m/44'/777'/0'/0/index ────────────────────
    seed_bytes = bytes(seed)
    nat_node   = _bip32_node(seed_bytes, 44, 777, index)
    nat_pub    = nat_node.PublicKey().RawCompressed().ToBytes()
    nat_priv   = nat_node.PrivateKey().Raw().ToBytes()
    nat_path   = f"m/44'/777'/0'/0/{index}"

    # Native address: ob_ prefix + Base58Check with version 0x4F
    nat_h    = _hash160(nat_pub)
    nat_full = bytes([0x4F]) + nat_h
    omni_native = "ob_" + _b58encode(nat_full + _checksum(nat_full))

    return {
        "chain":                    CHAIN_ID,
        # ── SegWit (primary) ─────────────────────────────────
        "address":                  omni_segwit,
        "public_key_hex":           sw_pub.hex(),
        "private_key_hex":          sw_priv.hex(),
        "private_key_wif":          sw_node.PrivateKey().ToWif(),
        "derivation_path":          sw_path,
        "script_pubkey":            script_pk,
        "segwit":                   True,
        # ── Legacy ───────────────────────────────────────────
        "address_legacy":           omni_legacy,
        "public_key_hex_legacy":    lg_pub.hex(),
        "private_key_hex_legacy":   lg_priv.hex(),
        "private_key_wif_legacy":   lg_node.PrivateKey().ToWif(),
        "derivation_path_legacy":   lg_path,
        # ── OmniBus Native (777) ──────────────────────────────
        "address_native":           omni_native,
        "public_key_hex_native":    nat_pub.hex(),
        "private_key_hex_native":   nat_priv.hex(),
        "private_key_wif_native":   _wif(nat_priv),
        "derivation_path_native":   nat_path,
        # ── BTC anchors ───────────────────────────────────────
        "address_btc":              btc_segwit,
        "address_btc_legacy":       btc_legacy,
        # ── Common ────────────────────────────────────────────
        "coin_type":                0,
        "coin_type_native":         777,
        "chain_name":               CHAIN_NAME,
        "coin_symbol":              COIN_SYMBOL,
    }
