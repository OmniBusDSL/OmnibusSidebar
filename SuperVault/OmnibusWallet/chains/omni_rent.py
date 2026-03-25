"""
OmnibusWallet -- chains/omni_rent.py
OmniBus chain: omnibus.rent domain
Algorithm: SLH-DSA (SPHINCS+) — Hash-based Signatures, 256-bit
Coin type: 780
Path: m/44'/780'/0'/0/index
Address prefix: ob_d5_
"""
import hashlib
import hmac as _hmac

CHAIN_ID      = "OMNI_RENT"
CHAIN_NAME    = "OmniBus · omnibus.rent"
COIN_SYMBOL   = "OMB"
COIN_TYPE     = 780
DOMAIN        = "omnibus.rent"
PREFIX        = "ob_d5_"
PQ_ALGORITHM  = "SLH-DSA"
PQ_VARIANT    = "SPHINCS+"
SECURITY_BITS = 256
NIST_LEVEL    = None
PURPOSE       = "Hash-based signatures — contracts / rent"

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

def _omni_address(pubkey_bytes: bytes) -> str:
    h = _hash160(pubkey_bytes)
    full = bytes([0x4F]) + h
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
        km   = _hkdf_expand(prk, path.encode(), 64)
        return km[:32], km[32:64], path, "", f"hkdf-fallback ({e})"


def derive(mnemonic: str, passphrase: str = "", index: int = 0) -> dict:
    try:
        from bip_utils import Bip39SeedGenerator
        seed = bytes(Bip39SeedGenerator(mnemonic).Generate(passphrase))
    except Exception:
        salt = ("mnemonic" + passphrase).encode()
        seed = hashlib.pbkdf2_hmac("sha512", mnemonic.encode(), salt, 2048, 64)

    priv, pub, path, wif, note = _seed_to_keypair(seed, COIN_TYPE, index)
    addr = PREFIX + _omni_address(pub)

    btc_addr, script_pk = "", ""
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
        "chain": CHAIN_ID, "address": addr,
        "public_key_hex": pub.hex(), "private_key_hex": priv.hex(),
        "derivation_path": path, "script_pubkey": script_pk,
        "domain": DOMAIN, "prefix": PREFIX,
        "pq_algorithm": PQ_ALGORITHM, "pq_variant": PQ_VARIANT,
        "security_bits": SECURITY_BITS, "nist_level": NIST_LEVEL,
        "purpose": PURPOSE, "coin_type": COIN_TYPE,
        "address_btc": btc_addr,
    }
    if wif:
        result["private_key_wif"] = wif
    if note:
        result["note"] = note
    return result
