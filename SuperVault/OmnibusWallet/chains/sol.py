"""
OmnibusWallet -- Solana (SOL) chain (BIP44, ED25519)
Derivation: m/44'/501'/0'/0'
"""
from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes

CHAIN_ID    = "SOL"
CHAIN_NAME  = "Solana"
COIN_SYMBOL = "SOL"

def derive(mnemonic: str, passphrase: str = "", index: int = 0) -> dict:
    seed = Bip39SeedGenerator(mnemonic).Generate(passphrase)
    bip  = Bip44.FromSeed(seed, Bip44Coins.SOLANA)
    acc  = bip.Purpose().Coin().Account(index)

    return {
        "chain":           CHAIN_ID,
        "address":         acc.PublicKey().ToAddress(),
        "public_key_hex":  acc.PublicKey().RawCompressed().ToHex(),
        "private_key_hex": acc.PrivateKey().Raw().ToHex(),
        "derivation_path": f"m/44'/501'/{index}'",
    }

def derive_multiple(mnemonic: str, passphrase: str = "", count: int = 5) -> list:
    return [derive(mnemonic, passphrase, i) for i in range(count)]
