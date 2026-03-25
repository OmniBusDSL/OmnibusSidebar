from . import btc, eth, egld, sol, atom, dot, bnb, ltc, doge, bch, xlm, xrp, op, ada, omni
from . import omni_omni, omni_love, omni_food, omni_rent, omni_vacation

# Registry — add new chains here
CHAINS = {
    # ── Original 3 ──────────────────────────────────────────
    "BTC":  btc,
    "ETH":  eth,
    "EGLD": egld,
    # ── Layer 1 ─────────────────────────────────────────────
    "SOL":  sol,
    "ADA":  ada,
    "XRP":  xrp,
    "DOT":  dot,
    "ATOM": atom,
    "XLM":  xlm,
    # ── EVM chains (same address as ETH) ────────────────────
    "BNB":  bnb,
    "OP":   op,
    # ── UTXO chains ─────────────────────────────────────────
    "LTC":  ltc,
    "DOGE": doge,
    "BCH":  bch,
    # ── OmniBus native chain (transferable — transactions) ───
    "OMNI":          omni,
    # ── OmniBus PQ Domains (non-transferable, collection/identity) ──
    # OMNI_OMNI removed — same coin_type 777 as OMNI, use OMNI for transactions
    "OMNI_LOVE":     omni_love,      # ML-DSA — identity / wallets (778)
    "OMNI_FOOD":     omni_food,      # Falcon-512 — retail / food   (779)
    "OMNI_RENT":     omni_rent,      # SLH-DSA — contracts / rent   (780)
    "OMNI_VACATION": omni_vacation,  # Falcon Light — mobile / IoT  (781)
}

CHAIN_NAMES = {
    "BTC":  "Bitcoin",
    "ETH":  "Ethereum",
    "EGLD": "MultiversX",
    "SOL":  "Solana",
    "ADA":  "Cardano",
    "XRP":  "XRP",
    "DOT":  "Polkadot",
    "ATOM": "Cosmos",
    "XLM":  "Stellar",
    "BNB":  "BNB Smart Chain",
    "OP":   "Optimism",
    "LTC":  "Litecoin",
    "DOGE": "Dogecoin",
    "BCH":  "Bitcoin Cash",
    "OMNI":          "OmniBus",
    "OMNI_LOVE":     "omnibus.love  (ML-DSA)",
    "OMNI_FOOD":    "omnibus.food  (Falcon-512)",
    "OMNI_RENT":    "omnibus.rent  (SLH-DSA)",
    "OMNI_VACATION": "omnibus.vacation  (Falcon Light)",
}

# Which chains are non-transferable (collection/identity/utility only)
CHAIN_NON_TRANSFERABLE = {
    "OMNI_LOVE", "OMNI_FOOD", "OMNI_RENT", "OMNI_VACATION",
}

CHAIN_COLORS = {
    "BTC":  "#f7931a",
    "ETH":  "#627eea",
    "EGLD": "#23f7dd",
    "SOL":  "#9945ff",
    "ADA":  "#0033ad",
    "XRP":  "#346aa9",
    "DOT":  "#e6007a",
    "ATOM": "#2e3148",
    "XLM":  "#7d00ff",
    "BNB":  "#f3ba2f",
    "OP":   "#ff0420",
    "LTC":  "#bfbbbb",
    "DOGE": "#c2a633",
    "BCH":  "#8dc351",
    "OMNI":          "#00c8ff",   # OmniBus cyan
    "OMNI_LOVE":     "#9945ff",   # ML-DSA  — purple
    "OMNI_FOOD":     "#25c45a",   # Falcon  — green
    "OMNI_RENT":     "#f5d020",   # SLH-DSA — yellow
    "OMNI_VACATION": "#f7931a",   # Falcon Light — orange
}

# Group chains for UI display
CHAIN_GROUPS = {
    "OmniBus":    ["OMNI"],
    "OmniDomains": ["OMNI_LOVE", "OMNI_FOOD", "OMNI_RENT", "OMNI_VACATION"],
    "Layer 1":    ["BTC", "ETH", "EGLD", "SOL", "ADA", "XRP", "DOT", "ATOM", "XLM"],
    "EVM":        ["BNB", "OP"],
    "UTXO":       ["LTC", "DOGE", "BCH"],
}
