"""
OmnibusWallet -- send_transaction.py
Construieste, semneaza si trimite tranzactii OMNI catre nodul OmniBus local.

Flux:
  1. Construieste TX (from, to, amount, timestamp)
  2. Calculeaza hash SHA256d(TX fields)
  3. Semneaza cu private key secp256k1 (ECDSA)
  4. POST JSON-RPC 2.0 la nodul local (port 8332)
  5. Returneaza txid sau eroare

Utilizare:
  from OmnibusWallet.send_transaction import send_omni

  result = send_omni(
      wallet_entry  = entry,          # din create_wallet_entry()
      to_address    = "ob_omni_...",
      amount_omni   = 10.0,           # in OMNI (nu SAT)
  )
  # result = { "success": True, "txid": "tx_...", "amountOMNI": 10.0, ... }
  # result = { "success": False, "error": "..." }
"""

import hashlib
import json
import time
import requests

# ── Constante ────────────────────────────────────────────────────────────────

OMNI_RPC_URL     = "http://127.0.0.1:8332"
SATOSHI_PER_OMNI = 1_000_000_000       # 1 OMNI = 1,000,000,000 SAT
_TX_COUNTER      = [0]                  # ID unic per sesiune

# Prefixe valide adrese OmniBus
VALID_PREFIXES = ("ob_omni_", "ob_k1_", "ob_f5_", "ob_d5_", "ob_s3_", "ob1q", "ob_", "0x")


# ── Helper HTTP ───────────────────────────────────────────────────────────────

def _rpc_call(method: str, params: list, url: str = OMNI_RPC_URL, timeout: int = 10) -> dict:
    _TX_COUNTER[0] += 1
    payload = {
        "jsonrpc": "2.0",
        "id":      _TX_COUNTER[0],
        "method":  method,
        "params":  params,
    }
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if "error" in data and data["error"]:
            return {"success": False, "error": str(data["error"])}
        return {"success": True, "result": data.get("result")}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"OmniBus node not running at {url}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Hash TX ───────────────────────────────────────────────────────────────────

def _tx_hash(tx_id: int, from_addr: str, to_addr: str,
             amount_sat: int, timestamp: int) -> bytes:
    """
    SHA256d(id:from:to:amount:timestamp) — identic cu Zig transaction.zig.calculateHash()
    """
    raw = f"{tx_id}:{from_addr}:{to_addr}:{amount_sat}:{timestamp}".encode()
    h1  = hashlib.sha256(raw).digest()
    return hashlib.sha256(h1).digest()          # SHA256d


# ── Semnare secp256k1 ─────────────────────────────────────────────────────────

def _sign_secp256k1(private_key_hex: str, message_hash: bytes) -> tuple[str, str]:
    """
    Semneaza message_hash cu secp256k1 ECDSA.
    Returneaza (signature_hex, public_key_hex).

    Foloseste bip_utils (deja instalat in wallet) pentru key objects,
    si coincurve / ecdsa pentru semnatura actuala.
    Incearca mai intai coincurve (mai rapida), fallback pe ecdsa.
    """
    priv_bytes = bytes.fromhex(private_key_hex)

    # ── Metoda 1: coincurve (libsecp256k1 binding) ────────────────────────
    try:
        import coincurve
        priv_key = coincurve.PrivateKey(priv_bytes)
        # sign_recoverable returneaza 65 bytes; folosim sign pentru 64 bytes DER/compact
        sig_obj  = priv_key.sign(message_hash, hasher=None)  # semneaza hash direct
        sig_hex  = sig_obj.hex()
        pub_hex  = priv_key.public_key.format(compressed=True).hex()
        return sig_hex, pub_hex
    except ImportError:
        pass

    # ── Metoda 2: ecdsa (pure Python) ────────────────────────────────────
    try:
        import ecdsa
        sk = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        # Semneaza hash direct (fara re-hash)
        sig_bytes = sk.sign_digest(message_hash, sigencode=ecdsa.util.sigencode_string)
        sig_hex   = sig_bytes.hex()
        pub_hex   = (b'\x02' if vk.to_string()[-1] % 2 == 0 else b'\x03') + \
                    vk.to_string()[:32]
        pub_hex   = pub_hex.hex()
        return sig_hex, pub_hex
    except ImportError:
        pass

    # ── Metoda 3: bip_utils (disponibil sigur) ────────────────────────────
    from bip_utils import Bip32Slip10Secp256k1
    # bip_utils nu expune sign direct, dar putem folosi cryptography
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        from cryptography.hazmat.backends import default_backend

        priv_key = ec.derive_private_key(
            int.from_bytes(priv_bytes, "big"),
            ec.SECP256K1(),
            default_backend()
        )
        pub_key  = priv_key.public_key()

        # Semneaza cu Prehashed (hash-ul e deja calculat)
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        sig_der = priv_key.sign(message_hash, ec.ECDSA(hashes.Prehashed()))
        r, s    = decode_dss_signature(sig_der)
        # Compact format R||S (64 bytes)
        sig_hex = r.to_bytes(32, "big").hex() + s.to_bytes(32, "big").hex()

        # Compressed public key
        pub_nums = pub_key.public_key().public_numbers() if hasattr(pub_key, 'public_key') else pub_key.public_numbers()
        prefix   = b'\x02' if pub_nums.y % 2 == 0 else b'\x03'
        pub_hex  = (prefix + pub_nums.x.to_bytes(32, "big")).hex()
        return sig_hex, pub_hex
    except Exception:
        pass

    raise RuntimeError(
        "Nu s-a gasit nicio librarie pentru secp256k1 signing. "
        "Instaleaza: pip install coincurve  SAU  pip install ecdsa"
    )


# ── Validari ──────────────────────────────────────────────────────────────────

def _validate_address(addr: str, label: str = "address") -> None:
    if not addr:
        raise ValueError(f"{label} is empty")
    if not any(addr.startswith(p) for p in VALID_PREFIXES):
        raise ValueError(
            f"{label} '{addr[:20]}...' has invalid prefix. "
            f"Valid: {VALID_PREFIXES}"
        )


def _get_private_key(wallet_entry: dict, chain: str = "OMNI") -> tuple[str, str, str]:
    """
    Extrage private_key_hex, public_key_hex si from_address din wallet entry.
    Pentru OMNI foloseste adresa native (ob_omni_...) si cheia native (coin 777).
    """
    addr_info = wallet_entry.get("addresses", {}).get(chain, {})
    if not addr_info:
        raise ValueError(f"Chain {chain} not in wallet entry")

    # Adresa de trimitere: native pentru OMNI
    from_addr = (addr_info.get("address_native") or
                 addr_info.get("address") or
                 addr_info.get("addr", ""))
    if not from_addr:
        raise ValueError("No from_address in wallet entry")

    # Private key: native (coin 777) sau segwit
    priv_hex = (addr_info.get("private_key_hex_native") or
                addr_info.get("private_key_hex") or
                addr_info.get("private_key", ""))
    if not priv_hex or len(priv_hex) < 64:
        raise ValueError(
            "Private key not found in wallet entry. "
            "Make sure create_wallet_entry() was called with OMNI chain."
        )

    # Public key
    pub_hex = (addr_info.get("public_key_hex_native") or
               addr_info.get("public_key_hex") or
               addr_info.get("pubkey", ""))

    return from_addr, priv_hex, pub_hex


# ── API principal ─────────────────────────────────────────────────────────────

def send_omni(
    wallet_entry: dict,
    to_address:   str,
    amount_omni:  float,
    rpc_url:      str = OMNI_RPC_URL,
) -> dict:
    """
    Trimite OMNI de la wallet catre o adresa destinatie.

    Args:
        wallet_entry: dict din create_wallet_entry() (trebuie sa contina OMNI chain)
        to_address:   adresa destinatie (ob_omni_..., ob_k1_..., etc.)
        amount_omni:  suma in OMNI (ex: 10.5)
        rpc_url:      URL nod OmniBus (default: http://127.0.0.1:8332)

    Returns:
        dict cu: success, txid, status, amountOMNI, amountSat, from, to, message
                 SAU success=False, error=<mesaj eroare>
    """
    try:
        # 1. Valideaza adresa destinatie
        _validate_address(to_address, "to_address")

        # 2. Extrage cheile din wallet
        from_addr, priv_hex, pub_hex = _get_private_key(wallet_entry)
        _validate_address(from_addr, "from_address")

        # 3. Calculeaza amount in SAT
        amount_sat = int(amount_omni * SATOSHI_PER_OMNI)
        if amount_sat <= 0:
            return {"success": False, "error": f"Invalid amount: {amount_omni} OMNI"}

        # 4. TX ID si timestamp
        _TX_COUNTER[0] += 1
        tx_id     = _TX_COUNTER[0]
        timestamp = int(time.time() * 1000)  # milliseconds

        # 5. Calculeaza hash TX (SHA256d) — identic cu Zig
        tx_hash = _tx_hash(tx_id, from_addr, to_address, amount_sat, timestamp)

        # 6. Semneaza cu secp256k1
        sig_hex, pub_hex_derived = _sign_secp256k1(priv_hex, tx_hash)
        if not pub_hex:
            pub_hex = pub_hex_derived

        # 7. Construieste payload TX
        tx_payload = {
            "id":         tx_id,
            "from":       from_addr,
            "to":         to_address,
            "amount":     amount_omni,
            "amountSat":  amount_sat,
            "timestamp":  timestamp,
            "signature":  sig_hex,
            "hash":       tx_hash.hex(),
            "pubkey":     pub_hex,
        }

        # 8. Trimite catre nodul OmniBus via JSON-RPC
        response = _rpc_call("sendtransaction", [tx_payload], url=rpc_url)

        if not response["success"]:
            return response

        result = response.get("result", {})
        if isinstance(result, dict) and not result.get("success", True):
            return {"success": False, "error": result.get("error", "Node rejected TX")}

        return {
            "success":    True,
            "txid":       result.get("txid", ""),
            "status":     result.get("status", "pending"),
            "from":       from_addr,
            "to":         to_address,
            "amountOMNI": amount_omni,
            "amountSat":  amount_sat,
            "hash":       tx_hash.hex(),
            "message":    result.get("message", "Transaction sent"),
        }

    except ValueError as e:
        return {"success": False, "error": str(e)}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {e}"}


def send_omni_raw(
    from_address:   str,
    private_key_hex: str,
    to_address:     str,
    amount_omni:    float,
    rpc_url:        str = OMNI_RPC_URL,
) -> dict:
    """
    Versiune low-level: trimite direct cu private key hex, fara wallet_entry.
    Utila pentru integrare rapida sau testare.
    """
    _validate_address(from_address, "from_address")
    _validate_address(to_address,   "to_address")

    amount_sat = int(amount_omni * SATOSHI_PER_OMNI)
    if amount_sat <= 0:
        return {"success": False, "error": f"Invalid amount: {amount_omni}"}

    _TX_COUNTER[0] += 1
    tx_id     = _TX_COUNTER[0]
    timestamp = int(time.time() * 1000)

    tx_hash = _tx_hash(tx_id, from_address, to_address, amount_sat, timestamp)
    sig_hex, pub_hex = _sign_secp256k1(private_key_hex, tx_hash)

    tx_payload = {
        "id":        tx_id,
        "from":      from_address,
        "to":        to_address,
        "amount":    amount_omni,
        "amountSat": amount_sat,
        "timestamp": timestamp,
        "signature": sig_hex,
        "hash":      tx_hash.hex(),
        "pubkey":    pub_hex,
    }

    response = _rpc_call("sendtransaction", [tx_payload], url=rpc_url)
    if not response["success"]:
        return response

    result = response.get("result", {})
    return {
        "success":    True,
        "txid":       result.get("txid", ""),
        "status":     result.get("status", "pending"),
        "from":       from_address,
        "to":         to_address,
        "amountOMNI": amount_omni,
        "amountSat":  amount_sat,
        "hash":       tx_hash.hex(),
    }


def get_transaction_status(txid: str, rpc_url: str = OMNI_RPC_URL) -> dict:
    """Verifica statusul unui TX dupa txid."""
    response = _rpc_call("gettransactionhistory", [50], url=rpc_url)
    if not response["success"]:
        return response
    txs = response.get("result", [])
    if isinstance(txs, list):
        for tx in txs:
            if tx.get("txid") == txid:
                return {"success": True, "found": True, "tx": tx}
    return {"success": True, "found": False, "txid": txid}


def send_batch(
    wallet_entry: dict,
    recipients: list[dict],
    rpc_url: str = OMNI_RPC_URL,
) -> dict:
    """
    Trimite mai multe TX-uri dintr-o singura comanda (batch).

    Args:
        wallet_entry: dict din create_wallet_entry() cu chain OMNI
        recipients:   lista de { "to": "ob_...", "amount": 1.5 }
        rpc_url:      URL nod OmniBus

    Returns:
        {
          "success": True/False,
          "sent": [ { txid, to, amount, success }, ... ],
          "failed": [ { to, amount, error }, ... ],
          "total_sent": float,   # OMNI total trimis cu succes
          "count": int,
        }
    """
    if not recipients:
        return {"success": False, "error": "Empty recipients list"}

    sent   = []
    failed = []

    for item in recipients:
        to     = item.get("to", "")
        amount = float(item.get("amount", 0))

        if not to or amount <= 0:
            failed.append({"to": to, "amount": amount, "error": "Invalid to/amount"})
            continue

        result = send_omni(
            wallet_entry=wallet_entry,
            to_address=to,
            amount_omni=amount,
            rpc_url=rpc_url,
        )

        if result.get("success"):
            sent.append({
                "txid":   result["txid"],
                "to":     to,
                "amount": amount,
                "success": True,
            })
        else:
            failed.append({
                "to":     to,
                "amount": amount,
                "error":  result.get("error", "Unknown error"),
            })

    total_sent = sum(s["amount"] for s in sent)
    return {
        "success":    len(sent) > 0,
        "sent":       sent,
        "failed":     failed,
        "total_sent": total_sent,
        "count":      len(sent),
    }
