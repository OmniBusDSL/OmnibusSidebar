"""
OmnibusWallet -- balance_fetcher.py
Fetch live balance + UTXOs + tx_count + last_tx for all supported chains.

Usage:
  from OmnibusWallet.balance_fetcher import fetch_wallet_balances
  updated = fetch_wallet_balances(wallet_entry)
  # updated["addresses"]["BTC"]["bal"]      → 0.00123456
  # updated["addresses"]["BTC"]["utxos"]    → [{txid, vout, amount, confirmations}]
  # updated["addresses"]["BTC"]["tx_count"] → 5
  # updated["addresses"]["ETH"]["bal"]      → 0.5 (in ETH)

All fetchers use public APIs — no API key required for basic usage.
API keys can be optionally passed for higher rate limits.
"""

import requests
import datetime
import time

# ── HTTP helper ───────────────────────────────────────────────
_SESSION = None

def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({"User-Agent": "OmnibusWallet/1.0"})
    return _SESSION

def _get(url: str, timeout: int = 10, params: dict = None) -> dict | list | None:
    try:
        r = _get_session().get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[BalanceFetcher] GET {url} → {e}")
        return None

def _post(url: str, payload: dict, timeout: int = 10) -> dict | None:
    try:
        r = _get_session().post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[BalanceFetcher] POST {url} → {e}")
        return None

# ── Result template ───────────────────────────────────────────
def _empty() -> dict:
    return {"bal": 0.0, "utxos": [], "tx_count": 0, "last_tx": None,
            "last_used": None, "fetch_error": None}

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

# ══════════════════════════════════════════════════════════════
# BTC — Blockstream API (public, no key)
# ══════════════════════════════════════════════════════════════
def fetch_btc(address: str) -> dict:
    """Fetch BTC balance + UTXOs from Blockstream."""
    result = _empty()
    base = "https://blockstream.info/api"

    # Address stats
    data = _get(f"{base}/address/{address}")
    if not data:
        result["fetch_error"] = "Blockstream unreachable"
        return result

    chain_stats = data.get("chain_stats", {})
    mempool_stats = data.get("mempool_stats", {})

    funded   = chain_stats.get("funded_txo_sum", 0) + mempool_stats.get("funded_txo_sum", 0)
    spent    = chain_stats.get("spent_txo_sum", 0)  + mempool_stats.get("spent_txo_sum", 0)
    result["bal"]      = (funded - spent) / 1e8
    result["tx_count"] = (chain_stats.get("tx_count", 0) +
                          mempool_stats.get("tx_count", 0))

    # UTXOs
    utxos_raw = _get(f"{base}/address/{address}/utxo") or []
    result["utxos"] = [
        {
            "txid":          u["txid"],
            "vout":          u["vout"],
            "amount":        u["value"] / 1e8,
            "confirmations": u.get("status", {}).get("block_height", 0),
        }
        for u in utxos_raw
    ]

    # Last tx
    txs = _get(f"{base}/address/{address}/txs") or []
    if txs:
        result["last_tx"]   = txs[0].get("txid")
        result["last_used"] = _now()

    return result

# ══════════════════════════════════════════════════════════════
# LTC — SoChain API
# ══════════════════════════════════════════════════════════════
def fetch_ltc(address: str) -> dict:
    result = _empty()
    data = _get(f"https://sochain.com/api/v2/get_address_balance/LTC/{address}")
    if not data or data.get("status") != "success":
        # Fallback: Blockchair
        return _fetch_blockchair("litecoin", address)
    d = data.get("data", {})
    result["bal"]      = float(d.get("confirmed_balance", 0))
    result["tx_count"] = int(d.get("total_txs", 0))
    return result

# ══════════════════════════════════════════════════════════════
# DOGE — SoChain API
# ══════════════════════════════════════════════════════════════
def fetch_doge(address: str) -> dict:
    result = _empty()
    data = _get(f"https://sochain.com/api/v2/get_address_balance/DOGE/{address}")
    if not data or data.get("status") != "success":
        return _fetch_blockchair("dogecoin", address)
    d = data.get("data", {})
    result["bal"]      = float(d.get("confirmed_balance", 0))
    result["tx_count"] = int(d.get("total_txs", 0))
    return result

# ══════════════════════════════════════════════════════════════
# BCH — SoChain API
# ══════════════════════════════════════════════════════════════
def fetch_bch(address: str) -> dict:
    result = _empty()
    data = _get(f"https://sochain.com/api/v2/get_address_balance/BCH/{address}")
    if not data or data.get("status") != "success":
        return _fetch_blockchair("bitcoin-cash", address)
    d = data.get("data", {})
    result["bal"]      = float(d.get("confirmed_balance", 0))
    result["tx_count"] = int(d.get("total_txs", 0))
    return result

# ── Blockchair fallback (BTC-family) ─────────────────────────
def _fetch_blockchair(coin: str, address: str) -> dict:
    result = _empty()
    data = _get(f"https://api.blockchair.com/{coin}/dashboards/address/{address}")
    if not data:
        result["fetch_error"] = "Blockchair unreachable"
        return result
    addr_data = data.get("data", {}).get(address, {}).get("address", {})
    result["bal"]      = addr_data.get("balance", 0) / 1e8
    result["tx_count"] = addr_data.get("transaction_count", 0)
    return result

# ══════════════════════════════════════════════════════════════
# ETH / BNB / OP — Etherscan-compatible APIs (public)
# ══════════════════════════════════════════════════════════════
_ETHERSCAN_ENDPOINTS = {
    "ETH": "https://api.etherscan.io/api",
    "BNB": "https://api.bscscan.com/api",
    "OP":  "https://api-optimistic.etherscan.io/api",
}
_ETHERSCAN_APIKEY = {
    "ETH": "",   # set your key here or pass via api_keys dict
    "BNB": "",
    "OP":  "",
}

def fetch_eth_family(address: str, chain: str = "ETH",
                     api_key: str = "") -> dict:
    """ETH / BNB / OP via Etherscan-compatible API."""
    result = _empty()
    base   = _ETHERSCAN_ENDPOINTS.get(chain, _ETHERSCAN_ENDPOINTS["ETH"])
    key    = api_key or _ETHERSCAN_APIKEY.get(chain, "")

    params = {"module": "account", "action": "balance",
              "address": address, "tag": "latest"}
    if key:
        params["apikey"] = key

    data = _get(base, params=params)
    if not data or data.get("status") != "1":
        # Fallback: Ankr public RPC
        return _fetch_eth_rpc(address, chain)

    wei = int(data.get("result", 0))
    result["bal"] = wei / 1e18

    # TX count
    params2 = {"module": "proxy", "action": "eth_getTransactionCount",
               "address": address, "tag": "latest"}
    if key:
        params2["apikey"] = key
    data2 = _get(base, params=params2)
    if data2:
        try:
            result["tx_count"] = int(data2.get("result", "0x0"), 16)
        except Exception:
            pass

    # Last tx
    params3 = {"module": "account", "action": "txlist",
               "address": address, "startblock": 0, "endblock": 99999999,
               "sort": "desc", "page": 1, "offset": 1}
    if key:
        params3["apikey"] = key
    data3 = _get(base, params=params3)
    if data3 and data3.get("result"):
        txs = data3["result"]
        if isinstance(txs, list) and txs:
            result["last_tx"]   = txs[0].get("hash")
            result["last_used"] = _now()

    return result

def _fetch_eth_rpc(address: str, chain: str) -> dict:
    """Fallback: public Ankr RPC."""
    result = _empty()
    rpc_urls = {
        "ETH": "https://rpc.ankr.com/eth",
        "BNB": "https://rpc.ankr.com/bsc",
        "OP":  "https://rpc.ankr.com/optimism",
    }
    url = rpc_urls.get(chain, rpc_urls["ETH"])
    payload = {"jsonrpc": "2.0", "method": "eth_getBalance",
               "params": [address, "latest"], "id": 1}
    data = _post(url, payload)
    if data and "result" in data:
        try:
            result["bal"] = int(data["result"], 16) / 1e18
        except Exception:
            pass
    return result

# ══════════════════════════════════════════════════════════════
# SOL — Solana public RPC
# ══════════════════════════════════════════════════════════════
def fetch_sol(address: str) -> dict:
    result = _empty()
    url = "https://api.mainnet-beta.solana.com"

    # Balance
    data = _post(url, {"jsonrpc": "2.0", "id": 1,
                        "method": "getBalance", "params": [address]})
    if data and "result" in data:
        lamports = data["result"].get("value", 0)
        result["bal"] = lamports / 1e9

    # TX count (signature count)
    data2 = _post(url, {"jsonrpc": "2.0", "id": 1,
                         "method": "getSignaturesForAddress",
                         "params": [address, {"limit": 1}]})
    if data2 and "result" in data2:
        sigs = data2["result"]
        if sigs:
            result["last_tx"]   = sigs[0].get("signature")
            result["last_used"] = _now()

    return result

# ══════════════════════════════════════════════════════════════
# XRP — XRPL public API
# ══════════════════════════════════════════════════════════════
def fetch_xrp(address: str) -> dict:
    result = _empty()
    data = _get(f"https://data.ripple.com/v2/accounts/{address}/balances")
    if not data:
        result["fetch_error"] = "XRPL unreachable"
        return result
    balances = data.get("balances", [])
    for b in balances:
        if b.get("currency") == "XRP":
            result["bal"] = float(b.get("value", 0))
            break
    # TX count
    data2 = _get(f"https://data.ripple.com/v2/accounts/{address}")
    if data2:
        result["tx_count"] = data2.get("account", {}).get("transaction_count", 0)
    return result

# ══════════════════════════════════════════════════════════════
# XLM — Stellar Horizon public API
# ══════════════════════════════════════════════════════════════
def fetch_xlm(address: str) -> dict:
    result = _empty()
    data = _get(f"https://horizon.stellar.org/accounts/{address}")
    if not data:
        result["fetch_error"] = "Horizon unreachable"
        return result
    balances = data.get("balances", [])
    for b in balances:
        if b.get("asset_type") == "native":
            result["bal"] = float(b.get("balance", 0))
            break
    # TX count via operations
    data2 = _get(f"https://horizon.stellar.org/accounts/{address}/operations",
                 params={"limit": 1, "order": "desc"})
    if data2:
        records = data2.get("_embedded", {}).get("records", [])
        if records:
            result["last_tx"]   = records[0].get("transaction_hash")
            result["last_used"] = _now()
    return result

# ══════════════════════════════════════════════════════════════
# ATOM — Cosmos REST API
# ══════════════════════════════════════════════════════════════
def fetch_atom(address: str) -> dict:
    result = _empty()
    data = _get(f"https://lcd-cosmoshub.blockapsis.com/cosmos/bank/v1beta1/balances/{address}")
    if not data:
        data = _get(f"https://api.cosmos.network/cosmos/bank/v1beta1/balances/{address}")
    if not data:
        result["fetch_error"] = "Cosmos LCD unreachable"
        return result
    balances = data.get("balances", [])
    for b in balances:
        if b.get("denom") == "uatom":
            result["bal"] = int(b.get("amount", 0)) / 1e6
            break
    return result

# ══════════════════════════════════════════════════════════════
# DOT — Polkadot public API (Subscan)
# ══════════════════════════════════════════════════════════════
def fetch_dot(address: str) -> dict:
    result = _empty()
    # Subscan public API (limited rate)
    data = _post("https://polkadot.api.subscan.io/api/v2/scan/search",
                 {"key": address})
    if not data or data.get("code") != 0:
        result["fetch_error"] = "Subscan unreachable"
        return result
    account = data.get("data", {}).get("account", {})
    # balance in planck (1 DOT = 10^10 planck)
    bal_raw = account.get("balance", "0")
    try:
        result["bal"] = float(bal_raw) / 1e10
    except Exception:
        pass
    result["tx_count"] = account.get("count_extrinsic", 0)
    return result

# ══════════════════════════════════════════════════════════════
# EGLD — MultiversX public API
# ══════════════════════════════════════════════════════════════
def fetch_egld(address: str) -> dict:
    result = _empty()
    data = _get(f"https://api.multiversx.com/accounts/{address}")
    if not data:
        result["fetch_error"] = "MultiversX API unreachable"
        return result
    # balance in denomination (1 EGLD = 10^18)
    bal_raw = data.get("balance", "0")
    try:
        result["bal"] = int(bal_raw) / 1e18
    except Exception:
        pass
    result["tx_count"] = data.get("txCount", 0)
    last = data.get("scrResultsCount")
    return result

# ══════════════════════════════════════════════════════════════
# ADA — Blockfrost (requires API key) / Koios (public)
# ══════════════════════════════════════════════════════════════
def fetch_ada(address: str, api_key: str = "") -> dict:
    result = _empty()

    if api_key:
        # Blockfrost
        headers = {"project_id": api_key}
        try:
            r = _get_session().get(
                f"https://cardano-mainnet.blockfrost.io/api/v0/addresses/{address}",
                headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            for amt in data.get("amount", []):
                if amt.get("unit") == "lovelace":
                    result["bal"] = int(amt["quantity"]) / 1e6
            result["tx_count"] = data.get("tx_count", 0)
            return result
        except Exception:
            pass

    # Koios public API (no key needed)
    data = _post("https://api.koios.rest/api/v1/address_info",
                 {"_addresses": [address]})
    if data and isinstance(data, list) and data:
        d = data[0]
        bal_lovelace = int(d.get("balance", 0))
        result["bal"] = bal_lovelace / 1e6
        result["tx_count"] = d.get("tx_count", 0)
    else:
        result["fetch_error"] = "Koios unreachable"
    return result

# ══════════════════════════════════════════════════════════════
# OMNI — OmniBus local node RPC (JSON-RPC 2.0, port 8332)
# ══════════════════════════════════════════════════════════════
_OMNI_RPC_DEFAULT = "http://127.0.0.1:8332"
_SATOSHI_PER_OMNI = 1_000_000_000  # 1 OMNI = 1,000,000,000 SAT


def _omni_rpc(method: str, params: list, rpc_url: str, _id: int = 1) -> dict | None:
    """JSON-RPC 2.0 call la nodul OmniBus. Returneaza result sau None."""
    data = _post(rpc_url, {"jsonrpc": "2.0", "id": _id, "method": method, "params": params}, timeout=5)
    if not data:
        return None
    if data.get("error"):
        return None
    return data.get("result")


def fetch_omni(address: str, rpc_url: str = _OMNI_RPC_DEFAULT) -> dict:
    """
    Fetch OMNI balance + UTXOs + history din nodul OmniBus local.
    1 OMNI = 1_000_000_000 SAT.
    """
    result = _empty()
    if not address:
        return result

    rpc_result = _omni_rpc("getbalance", [address], rpc_url)
    if rpc_result is None:
        result["fetch_error"] = "OmniBus node not running (port 8332)"
        return result

    try:
        bal_sat = rpc_result.get("balance", 0) if isinstance(rpc_result, dict) else int(rpc_result)
        result["bal"] = bal_sat / _SATOSHI_PER_OMNI

        if isinstance(rpc_result, dict):
            # UTXOs reale din node
            utxos_raw = rpc_result.get("utxos", [])
            result["utxos"] = [
                {
                    "txid":        u.get("txid", ""),
                    "vout":        u.get("vout", 0),
                    "amount":      u.get("value", 0) / _SATOSHI_PER_OMNI,
                    "blockHeight": u.get("blockHeight", 0),
                    "status":      u.get("status", "confirmed"),
                }
                for u in utxos_raw
            ]
            txs = rpc_result.get("transactions", [])
            result["tx_count"] = rpc_result.get("txCount", len(txs))
            if txs:
                result["last_tx"]   = txs[-1].get("txid")
                result["last_used"] = _now()
            result["node_height"] = rpc_result.get("nodeHeight", 0)

    except Exception as e:
        result["fetch_error"] = f"Parse error: {e}"

    return result


def get_address_history(address: str, limit: int = 50,
                        rpc_url: str = _OMNI_RPC_DEFAULT) -> list[dict]:
    """
    Returneaza istoricul complet al tranzactiilor pentru o adresa.
    Include: coinbase (mining rewards), transfer sent, transfer received.
    Ordine: cele mai recente primele.

    Returns:
        list de dict cu: txid, type, direction, amount, counterparty,
                         blockHeight, status, timestamp
    """
    all_txs = _omni_rpc("gettransactionhistory", [limit * 3], rpc_url)
    if not isinstance(all_txs, list):
        return []

    result = []
    for tx in all_txs:
        frm  = tx.get("from", "")
        to   = tx.get("to", "")
        typ  = tx.get("type", "transfer")

        if frm != address and to != address:
            continue

        if frm == address:
            direction    = "sent"
            counterparty = to
        else:
            direction    = "received"
            counterparty = frm

        result.append({
            "txid":        tx.get("txid", ""),
            "type":        typ,
            "direction":   direction,
            "amount":      tx.get("amount", tx.get("amountSat", 0) / _SATOSHI_PER_OMNI),
            "amountSat":   tx.get("amountSat", 0),
            "counterparty": counterparty,
            "blockHeight": tx.get("blockHeight"),
            "status":      tx.get("status", "pending"),
            "timestamp":   tx.get("timestamp", 0),
        })

    return result[:limit]


def fetch_omni_domain(address: str, chain: str) -> dict:
    """
    Domain chains (OMNI_LOVE/FOOD/RENT/VACATION) sunt non-transferabile.
    Ownership e dovedit prin derivare BIP-32, nu prin balance on-chain.
    """
    result = _empty()
    result["fetch_error"] = f"{chain}: non-transferable domain — no on-chain balance"
    return result


# ══════════════════════════════════════════════════════════════
# Dispatcher
# ══════════════════════════════════════════════════════════════
_FETCHERS = {
    "BTC":  lambda addr, **kw: fetch_btc(addr),
    "LTC":  lambda addr, **kw: fetch_ltc(addr),
    "DOGE": lambda addr, **kw: fetch_doge(addr),
    "BCH":  lambda addr, **kw: fetch_bch(addr),
    "ETH":  lambda addr, **kw: fetch_eth_family(addr, "ETH", kw.get("ETH_KEY","")),
    "BNB":  lambda addr, **kw: fetch_eth_family(addr, "BNB", kw.get("BNB_KEY","")),
    "OP":   lambda addr, **kw: fetch_eth_family(addr, "OP",  kw.get("OP_KEY", "")),
    "SOL":  lambda addr, **kw: fetch_sol(addr),
    "XRP":  lambda addr, **kw: fetch_xrp(addr),
    "XLM":  lambda addr, **kw: fetch_xlm(addr),
    "ATOM": lambda addr, **kw: fetch_atom(addr),
    "DOT":  lambda addr, **kw: fetch_dot(addr),
    "EGLD": lambda addr, **kw: fetch_egld(addr),
    "ADA":  lambda addr, **kw: fetch_ada(addr, kw.get("ADA_KEY","")),
    # OmniBus chains — local node RPC (port 8332) or empty if node not running
    "OMNI":          lambda addr, **kw: fetch_omni(addr, kw.get("OMNI_RPC", "http://127.0.0.1:8332")),
    "OMNI_LOVE":     lambda addr, **kw: fetch_omni_domain(addr, "OMNI_LOVE"),
    "OMNI_FOOD":     lambda addr, **kw: fetch_omni_domain(addr, "OMNI_FOOD"),
    "OMNI_RENT":     lambda addr, **kw: fetch_omni_domain(addr, "OMNI_RENT"),
    "OMNI_VACATION": lambda addr, **kw: fetch_omni_domain(addr, "OMNI_VACATION"),
}


def fetch_balance(chain: str, address: str, **api_keys) -> dict:
    """
    Fetch balance for a single chain address.
    Returns dict with: bal, utxos, tx_count, last_tx, last_used, fetch_error
    api_keys: ETH_KEY, BNB_KEY, ADA_KEY etc. (optional)
    """
    if not address:
        return _empty()
    chain = chain.upper()
    fetcher = _FETCHERS.get(chain)
    if not fetcher:
        r = _empty()
        r["fetch_error"] = f"No fetcher for chain {chain}"
        return r
    return fetcher(address, **api_keys)


def fetch_wallet_balances(wallet_entry: dict,
                          chains: list = None,
                          delay: float = 0.3,
                          **api_keys) -> dict:
    """
    Fetch balances for all chains in a wallet entry.
    Updates wallet_entry["addresses"][chain] in-place with live data.

    chains: optional list to fetch only specific chains (default: all)
    delay:  seconds between requests (avoid rate limiting)
    api_keys: ETH_KEY="...", ADA_KEY="..." etc.

    Returns the updated wallet_entry.
    """
    addresses = wallet_entry.get("addresses", {})
    to_fetch  = chains or list(addresses.keys())

    for chain in to_fetch:
        if chain not in addresses:
            continue

        info    = addresses[chain]
        chain_upper = chain.upper()

        # OMNI native chain uses ob_ address (address_native)
        # Domain chains: any address is fine (non-transferable, no real balance)
        if chain_upper == "OMNI":
            address = (info.get("address_native") or
                       info.get("address") or info.get("addr", ""))
        else:
            address = info.get("address") or info.get("addr", "")

        if not address:
            continue

        print(f"[BalanceFetcher] {chain_upper} {address[:24]}...")

        result = fetch_balance(chain_upper, address, **api_keys)

        # Update the address entry
        info["bal"]       = result["bal"]
        info["utxos"]     = result["utxos"]
        info["tx_count"]  = result["tx_count"]
        info["last_tx"]   = result["last_tx"]
        if result["last_used"]:
            info["last_used"] = result["last_used"]
        if result.get("fetch_error"):
            info["fetch_error"] = result["fetch_error"]
            print(f"[BalanceFetcher]   ERROR: {result['fetch_error']}")
        else:
            info.pop("fetch_error", None)
            print(f"[BalanceFetcher]   bal={result['bal']}  txs={result['tx_count']}")

        if delay > 0:
            time.sleep(delay)

    return wallet_entry
