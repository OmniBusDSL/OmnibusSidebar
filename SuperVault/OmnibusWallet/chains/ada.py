"""
OmnibusWallet -- Cardano (ADA) chain (BIP44, Byron Icarus)
Derivation: m/44'/1815'/0'/0/index
Address: addr1...  (Byron base58 format via bip_utils)
"""
from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes

CHAIN_ID    = "ADA"
CHAIN_NAME  = "Cardano"
COIN_SYMBOL = "ADA"

def derive(mnemonic: str, passphrase: str = "", index: int = 0) -> dict:
    seed = Bip39SeedGenerator(mnemonic).Generate(passphrase)
    bip  = Bip44.FromSeed(seed, Bip44Coins.CARDANO_BYRON_ICARUS)
    acc  = bip.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)

    return {
        "chain":           CHAIN_ID,
        "address":         acc.PublicKey().ToAddress(),
        "public_key_hex":  acc.PublicKey().RawCompressed().ToHex(),
        "private_key_hex": acc.PrivateKey().Raw().ToHex(),
        "derivation_path": f"m/44'/1815'/0'/0/{index}",
        "note":            "Byron Icarus format",
    }

def derive_multiple(mnemonic: str, passphrase: str = "", count: int = 5) -> list:
    return [derive(mnemonic, passphrase, i) for i in range(count)]
