"""
OmnibusWallet -- Bitcoin chain (BIP39/BIP44/BIP84)
Supports: mainnet, testnet
Derivation: m/44'/0'/0'/0/0  (legacy P2PKH)
             m/84'/0'/0'/0/0  (native segwit P2WPKH)
"""
from bip_utils import (
    Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes,
    Bip84, Bip84Coins,
)

CHAIN_ID   = "BTC"
CHAIN_NAME = "Bitcoin"
COIN_SYMBOL = "BTC"

def derive(mnemonic: str, passphrase: str = "", index: int = 0, segwit: bool = True) -> dict:
    seed = Bip39SeedGenerator(mnemonic).Generate(passphrase)

    if segwit:
        bip = Bip84.FromSeed(seed, Bip84Coins.BITCOIN)
        acc = bip.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)
        path = f"m/84'/0'/0'/0/{index}"
    else:
        bip = Bip44.FromSeed(seed, Bip44Coins.BITCOIN)
        acc = bip.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)
        path = f"m/44'/0'/0'/0/{index}"

    return {
        "chain":           CHAIN_ID,
        "address":         acc.PublicKey().ToAddress(),
        "public_key_hex":  acc.PublicKey().RawCompressed().ToHex(),
        "private_key_wif": acc.PrivateKey().ToWif(),
        "derivation_path": path,
        "segwit":          segwit,
    }


def derive_multiple(mnemonic: str, passphrase: str = "", count: int = 5, segwit: bool = True) -> list:
    return [derive(mnemonic, passphrase, i, segwit) for i in range(count)]
