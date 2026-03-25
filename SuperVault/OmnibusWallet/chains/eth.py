"""
OmnibusWallet -- Ethereum chain (BIP39/BIP44)
Supports: mainnet (chain_id=1), any EVM chain
Derivation: m/44'/60'/0'/0/index
"""
from bip_utils import (
    Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes,
)

CHAIN_ID    = "ETH"
CHAIN_NAME  = "Ethereum"
COIN_SYMBOL = "ETH"

def derive(mnemonic: str, passphrase: str = "", index: int = 0) -> dict:
    seed = Bip39SeedGenerator(mnemonic).Generate(passphrase)
    bip  = Bip44.FromSeed(seed, Bip44Coins.ETHEREUM)
    acc  = bip.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)

    return {
        "chain":           CHAIN_ID,
        "address":         acc.PublicKey().ToAddress(),
        "public_key_hex":  acc.PublicKey().RawUncompressed().ToHex(),
        "private_key_hex": acc.PrivateKey().Raw().ToHex(),
        "derivation_path": f"m/44'/60'/0'/0/{index}",
    }


def derive_multiple(mnemonic: str, passphrase: str = "", count: int = 5) -> list:
    return [derive(mnemonic, passphrase, i) for i in range(count)]
