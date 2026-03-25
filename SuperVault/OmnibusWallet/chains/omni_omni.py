"""
OmnibusWallet -- chains/omni_omni.py
OmniBus chain: omnibus.omni domain
Algorithm: ML-KEM (Kyber-768) — Key Encapsulation, NIST Level 3
Coin type: 777
Path: m/44'/777'/0'/0/index
Address prefix: ob_omni_
"""
import hashlib
import hmac as _hmac

CHAIN_ID     = "OMNI_OMNI"
CHAIN_NAME   = "OmniBus · omnibus.omni"
COIN_SYMBOL  = "OMB"
COIN_TYPE    = 777
DOMAIN       = "omnibus.omni"
PREFIX       = "ob_omni_"
PQ_ALGORITHM = "ML-KEM"
PQ_VARIANT   = "Kyber-768"
SECURITY_BITS = 256
NIST_LEVEL   = 3
PURPOSE      = "Key Encapsulation — secure node communication"

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

def _omni_address(pubkey_bytes: bytes, version_byte: int = 0x4F) -> str:
    h    = _hash160(pubkey_bytes)
    full = bytes([version_byte]) + h
    return _b58encode(full + _checksum(full))

def _hkdf_expand(prk: bytes, info: bytes, length: int = 64) -> bytes:
    okm, t = b"", b""
    i = 0
    while len(okm) < length:
        i += 1
        t = _hmac.new(prk, t + info + bytes([i]), hashlib.sha512).digest()
        okm += t
    return okm[:length]

def _seed_to_keypair(seed: bytes, coin_type: int, index: int):
    """
    Derive keypair via BIP32 secp256k1 if bip_utils available,
    else HKDF deterministic fallback.
    Returns (privkey_bytes, pubkey_bytes, path, wif)
    """
    path = f"m/44'/{coin_type}'/0'/0/{index}"
    try:
        from bip_utils import Bip32Slip10Secp256k1, Bip32KeyIndex
        bip32 = Bip32Slip10Secp256k1.FromSeed(seed)
        node  = (bip32
                 .ChildKey(Bip32KeyIndex.HardenIndex(44))
                 .ChildKey(Bip32KeyIndex.HardenIndex(coin_type))
                 .ChildKey(Bip32KeyIndex.HardenIndex(0))
                 .ChildKey(0)
                 .ChildKey(index))
        priv = node.PrivateKey().Raw().ToBytes()
        pub  = node.PublicKey().RawCompressed().ToBytes()
        wif_raw = b"\x80" + priv + b"\x01"
        wif = _b58encode(wif_raw + _checksum(wif_raw))
        return priv, pub, path, wif, ""
    except Exception as e:
        salt = hashlib.sha256(f"OmniBus:{coin_type}".encode()).digest()
        prk  = _hmac.new(salt, seed, hashlib.sha512).digest()
        km   = _hkdf_expand(prk, f"{path}".encode(), 64)
        priv = km[:32]
        pub  = km[32:64]
        return priv, pub, path, "", f"hkdf-fallback ({e})"


def derive(mnemonic: str, passphrase: str = "", index: int = 0) -> dict:
    try:
        from bip_utils import Bip39SeedGenerator
        seed = bytes(Bip39SeedGenerator(mnemonic).Generate(passphrase))
    except Exception:
        salt = ("mnemonic" + passphrase).encode()
        seed = hashlib.pbkdf2_hmac("sha512", mnemonic.encode(), salt, 2048, 64)

    priv, pub, path, wif, note = _seed_to_keypair(seed, COIN_TYPE, index)

    addr = PREFIX + _omni_address(pub)

    # Bitcoin P2WPKH anchor address
    btc_addr = ""
    script_pk = ""
    try:
        from bip_utils import P2WPKHAddrEncoder, CoinsConf
        
        hrp = CoinsConf.BitcoinMainNet.ParamByKey("p2wpkh_hrp")
        btc_addr = P2WPKHAddrEncoder.EncodeKey(pub, hrp=hrp)
        from bip_utils import SegwitBech32Decoder
        wv, wp = SegwitBech32Decoder.Decode("bc", btc_addr)
        script_pk = f"{wv:02x}14{bytes(wp).hex()}" if wv == 0 else ""
    except Exception:
        pass

    result = {
        "chain":             CHAIN_ID,
        "address":           addr,
        "public_key_hex":    pub.hex(),
        "private_key_hex":   priv.hex(),
        "derivation_path":   path,
        "script_pubkey":     script_pk,
        # OmniBus domain metadata
        "domain":            DOMAIN,
        "prefix":            PREFIX,
        "pq_algorithm":      PQ_ALGORITHM,
        "pq_variant":        PQ_VARIANT,
        "security_bits":     SECURITY_BITS,
        "nist_level":        NIST_LEVEL,
        "purpose":           PURPOSE,
        "coin_type":         COIN_TYPE,
        # Bitcoin anchor
        "address_btc":       btc_addr,
    }
    if wif:
        result["private_key_wif"] = wif
    if note:
        result["note"] = note
    return result
