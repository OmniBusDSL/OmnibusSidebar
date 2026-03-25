"""
OmnibusWallet Manager  --  Standalone GUI
Generates BTC/ETH/EGLD/... wallets, stores in OmnibusVault (encrypted DPAPI).

Vault storage:
  - Uses VAULT_OP_ADD with a special exchange index VAULT_EXCHANGE_WALLET=3
  - name  = wallet label (e.g. "MY_BTC_WALLET")
  - key   = JSON with public data (addresses, pubkeys, paths)
  - secret= JSON with mnemonic + private keys (encrypted by DPAPI in Vault)

Run standalone:
  python wallet_manager.py

Or import and use wallet_manager_frame(parent) in another tkinter app.
"""

import sys
import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import ctypes
from ctypes import wintypes
import struct

# Add parent dir to path so we can import OmnibusWallet
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from OmnibusWallet.wallet_core import (
    generate_mnemonic, validate_mnemonic,
    create_wallet_entry, wallet_entry_to_json, wallet_entry_from_json,
    get_address, add_chain_to_entry,
)
from OmnibusWallet.chains import CHAINS, CHAIN_NAMES, CHAIN_COLORS

# ── Vault protocol ────────────────────────────────────────────
VAULT_OP_ADD    = 0x41
VAULT_OP_DELETE = 0x43
VAULT_OP_LIST   = 0x45
VAULT_OP_COUNT  = 0x49

# We use exchange index 3 = WALLET (extending beyond LCX/Kraken/Coinbase)
# The vault_service handles up to VAULT_EXCHANGE_COUNT=3, so we store
# wallets as a special entry in exchange 0 with a "WALLET:" name prefix.
# This avoids changing vault_core for now. Future: add VAULT_EXCHANGE_WALLET.
WALLET_NAME_PREFIX = "WALLET:"

VAULT_OK             = 0
VAULT_ERR_NO_SERVICE = 6
ERROR_NAMES = {
    0:"OK", 1:"Not found", 2:"Decrypt failed", 3:"IO error",
    4:"Vault locked", 5:"Invalid", 6:"Service not running",
    7:"Max keys reached", 8:"Name exists"
}

PIPE_NAME = r"\\.\pipe\OmnibusVault"
kernel32  = ctypes.windll.kernel32
GENERIC_READ  = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

def _pipe_call(request: bytes) -> bytes | None:
    kernel32.WaitNamedPipeA(PIPE_NAME.encode(), wintypes.DWORD(2000))
    h = kernel32.CreateFileA(PIPE_NAME.encode(),
        GENERIC_READ|GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE:
        return None
    try:
        req_buf = ctypes.create_string_buffer(request, len(request))
        written = wintypes.DWORD(0)
        ok = kernel32.WriteFile(h, req_buf, wintypes.DWORD(len(request)),
                                ctypes.byref(written), None)
        if not ok: return None
        kernel32.FlushFileBuffers(h)
        out_buf = ctypes.create_string_buffer(8192)
        read = wintypes.DWORD(0)
        ok = kernel32.ReadFile(h, out_buf, wintypes.DWORD(8192),
                               ctypes.byref(read), None)
        if not ok or read.value == 0: return None
        return bytes(out_buf.raw[:read.value])
    finally:
        kernel32.CloseHandle(h)

def _pack_str(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<H", len(b)) + b

def _unpack_str(data: bytes, pos: int):
    if pos + 2 > len(data): return "", pos
    slen = struct.unpack_from("<H", data, pos)[0]; pos += 2
    s = data[pos:pos+slen].decode("utf-8", errors="replace")
    return s, pos + slen

def _unpack_u32(data: bytes, pos: int):
    v = struct.unpack_from("<I", data, pos)[0]
    return v, pos + 4

def service_ok() -> bool:
    h = kernel32.CreateFileA(PIPE_NAME.encode(),
        GENERIC_READ|GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE: return False
    kernel32.CloseHandle(h); return True

def vault_list_wallets() -> list:
    """List all wallet entries from exchange 0 with WALLET: prefix."""
    req = struct.pack("<BBHH", VAULT_OP_LIST, 0, 0, 0)
    resp = _pipe_call(req)
    if not resp or len(resp) < 3: return []
    pos = 3  # skip err(1) + plen(2)
    if len(resp) - pos < 4: return []
    cnt, pos = _unpack_u32(resp, pos)
    wallets = []
    for _ in range(cnt):
        name,    pos = _unpack_str(resp, pos)
        api_key, pos = _unpack_str(resp, pos)
        slot,    pos = _unpack_u32(resp, pos)
        status = resp[pos] if pos < len(resp) else 0; pos += 1
        if name.startswith(WALLET_NAME_PREFIX):
            label = name[len(WALLET_NAME_PREFIX):]
            try:
                pub_data = json.loads(api_key) if api_key.startswith("{") else {}
            except Exception:
                pub_data = {}
            wallets.append({"label": label, "slot": slot,
                             "status": status, "pub": pub_data})
    return wallets

def vault_save_wallet(label: str, pub_json: str, secret_json: str) -> int:
    """Save wallet to vault. Returns error code."""
    name = WALLET_NAME_PREFIX + label
    payload = _pack_str(name) + _pack_str(pub_json) + _pack_str(secret_json)
    req = struct.pack("<BBHH", VAULT_OP_ADD, 0, 0, len(payload)) + payload
    resp = _pipe_call(req)
    if resp is None: return VAULT_ERR_NO_SERVICE
    return resp[0]

def vault_delete_wallet(slot: int) -> int:
    req = struct.pack("<BBHH", VAULT_OP_DELETE, 0, slot, 0)
    resp = _pipe_call(req)
    if resp is None: return VAULT_ERR_NO_SERVICE
    return resp[0]

# ── Colors / Fonts ────────────────────────────────────────────
BG   = "#0d0f18"
BG2  = "#10121e"
BG3  = "#141820"
FG   = "#d0d0e0"
FG2  = "#606080"
GRN  = "#25c45a"
RED  = "#c03030"
YEL  = "#f5d020"
ORG  = "#f7931a"
BLU  = "#627eea"
CYN  = "#23f7dd"
FONT  = ("Consolas", 10)
FONTB = ("Consolas", 10, "bold")
FONTS = ("Consolas", 9)
FONTM = ("Consolas", 11, "bold")

ALL_CHAINS = list(CHAINS.keys())

# ── Main App ──────────────────────────────────────────────────
class WalletManagerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("OmniBus Wallet Manager")
        root.geometry("700x720")
        root.configure(bg=BG)
        root.minsize(600, 560)

        self.wallets    = []
        self.show_gen   = False
        self.gen_mnemonic = ""
        self.gen_entry    = {}

        self._build_ui()
        self._refresh()

    # ── Build ─────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg="#0a0c14", pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="OMNIBUS WALLET", bg="#0a0c14",
                 fg=YEL, font=("Consolas", 14, "bold")).pack(side=tk.LEFT, padx=14)
        tk.Label(hdr, text="BTC · ETH · EGLD · ...", bg="#0a0c14",
                 fg=FG2, font=FONTS).pack(side=tk.LEFT)
        self.svc_lbl = tk.Label(hdr, text="...", bg="#0a0c14", fg=FG2, font=FONTS)
        self.svc_lbl.pack(side=tk.RIGHT, padx=14)

        # Wallet list
        list_frame = tk.Frame(self.root, bg=BG2)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8,4))

        self.count_lbl = tk.Label(list_frame, text="STORED WALLETS  0",
                                   bg=BG2, fg=FG2, font=FONTS, anchor="w")
        self.count_lbl.pack(fill=tk.X, padx=8, pady=(6,2))

        canvas_wrap = tk.Frame(list_frame, bg=BG2)
        canvas_wrap.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_wrap, bg=BG2, highlightthickness=0)
        sb = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.list_inner = tk.Frame(self.canvas, bg=BG2)
        self._cw = self.canvas.create_window((0,0), window=self.list_inner, anchor="nw")
        self.list_inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(
            self._cw, width=e.width))

        # Generate button
        gen_frame = tk.Frame(self.root, bg=BG3, pady=6)
        gen_frame.pack(fill=tk.X, padx=10, pady=2)

        self.gen_btn = tk.Button(gen_frame, text="  + GENERATE NEW WALLET  ",
                                  font=FONTB, bg="#0e2e14", fg=GRN, relief=tk.FLAT,
                                  activebackground="#1a4020",
                                  command=self._toggle_gen)
        self.gen_btn.pack(fill=tk.X, padx=8, pady=(0,4))

        self.gen_inner = tk.Frame(gen_frame, bg=BG3)
        # populated on demand

        # Footer
        bot = tk.Frame(self.root, bg="#0a0c14", pady=5)
        bot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(bot, text="Refresh", bg=BG3, fg=FG2, relief=tk.FLAT,
                  font=FONTS, command=self._refresh).pack(side=tk.LEFT, padx=8)
        tk.Label(bot, text="Secured by OmniBus Vault  ·  DPAPI encrypted",
                 bg="#0a0c14", fg="#282838", font=("Consolas",8)).pack(side=tk.RIGHT, padx=10)

    # ── Render wallet list ────────────────────────────────────
    def _render_wallets(self):
        for w in self.list_inner.winfo_children():
            w.destroy()
        self.count_lbl.config(text=f"STORED WALLETS  {len(self.wallets)}")

        if not self.wallets:
            tk.Label(self.list_inner, text="No wallets stored yet.",
                     bg=BG2, fg=FG2, font=FONTS).pack(pady=20)
            return

        for wallet in self.wallets:
            card = tk.Frame(self.list_inner, bg=BG3, pady=6)
            card.pack(fill=tk.X, padx=6, pady=3)

            # Title row
            title_row = tk.Frame(card, bg=BG3)
            title_row.pack(fill=tk.X, padx=8)
            tk.Label(title_row, text="◆", bg=BG3, fg=YEL, font=FONTB).pack(side=tk.LEFT)
            tk.Label(title_row, text=wallet["label"], bg=BG3, fg=FG, font=FONTB).pack(side=tk.LEFT, padx=6)

            tk.Button(title_row, text="Delete", font=FONTS,
                      bg="#2e0e0e", fg=RED, relief=tk.FLAT,
                      command=lambda s=wallet["slot"], l=wallet["label"]: self._do_delete(s, l)
                      ).pack(side=tk.RIGHT, padx=2)

            # Addresses
            pub = wallet.get("pub", {})
            addrs = pub.get("addresses", {})
            for chain, info in addrs.items():
                chain_col = CHAIN_COLORS.get(chain, FG2)
                addr_row = tk.Frame(card, bg=BG3)
                addr_row.pack(fill=tk.X, padx=12, pady=1)
                tk.Label(addr_row, text=f"{chain:5}", bg=BG3, fg=chain_col,
                         font=FONTB, width=5).pack(side=tk.LEFT)
                addr = info.get("address", "?")
                # show shortened address
                short = addr[:12] + "..." + addr[-8:] if len(addr) > 24 else addr
                tk.Label(addr_row, text=short, bg=BG3, fg=FG, font=FONTS).pack(side=tk.LEFT, padx=6)
                tk.Label(addr_row, text=info.get("derivation_path",""),
                         bg=BG3, fg="#303050", font=FONTS).pack(side=tk.RIGHT, padx=4)

            tk.Frame(self.list_inner, bg="#1a1c2e", height=1).pack(fill=tk.X, padx=6)

    # ── Generate wallet UI ────────────────────────────────────
    def _toggle_gen(self):
        self.show_gen = not self.show_gen
        if self.show_gen:
            self.gen_btn.config(text="  - CANCEL  ", bg="#2e0e0e", fg=RED)
            self._build_gen_form()
            self.gen_inner.pack(fill=tk.X)
        else:
            self.gen_btn.config(text="  + GENERATE NEW WALLET  ", bg="#0e2e14", fg=GRN)
            self.gen_inner.pack_forget()
            for w in self.gen_inner.winfo_children():
                w.destroy()
            self.gen_mnemonic = ""
            self.gen_entry = {}

    def _build_gen_form(self):
        for w in self.gen_inner.winfo_children():
            w.destroy()

        f = self.gen_inner

        # Label
        tk.Label(f, text="WALLET LABEL", bg=BG3, fg=FG2, font=FONTS, anchor="w").pack(
            fill=tk.X, padx=8)
        self.gen_label_var = tk.StringVar()
        tk.Entry(f, textvariable=self.gen_label_var, bg="#0d0f18", fg=FG,
                 insertbackground=FG, relief=tk.FLAT, font=FONT).pack(
            fill=tk.X, padx=8, ipady=4, pady=(1,6))

        # Chain selection
        tk.Label(f, text="CHAINS  (select all you need)", bg=BG3, fg=FG2,
                 font=FONTS, anchor="w").pack(fill=tk.X, padx=8)
        chain_row = tk.Frame(f, bg=BG3)
        chain_row.pack(fill=tk.X, padx=8, pady=(2,6))
        self.chain_vars = {}
        for chain in ALL_CHAINS:
            var = tk.BooleanVar(value=True)
            self.chain_vars[chain] = var
            col = CHAIN_COLORS.get(chain, FG2)
            tk.Checkbutton(chain_row, text=chain, variable=var,
                           bg=BG3, fg=col, selectcolor="#0d0f18",
                           activebackground=BG3, activeforeground=col,
                           font=FONTB).pack(side=tk.LEFT, padx=8)

        # Mnemonic words
        tk.Label(f, text="MNEMONIC WORDS", bg=BG3, fg=FG2, font=FONTS, anchor="w").pack(
            fill=tk.X, padx=8)
        words_row = tk.Frame(f, bg=BG3)
        words_row.pack(fill=tk.X, padx=8, pady=(2,6))
        self.words_var = tk.IntVar(value=24)
        for w in [12, 24]:
            tk.Radiobutton(words_row, text=f"{w} words", variable=self.words_var, value=w,
                           bg=BG3, fg=FG, selectcolor="#0d0f18",
                           activebackground=BG3, font=FONTS).pack(side=tk.LEFT, padx=8)

        # Optional passphrase
        tk.Label(f, text="BIP39 PASSPHRASE  (optional, extra security)",
                 bg=BG3, fg=FG2, font=FONTS, anchor="w").pack(fill=tk.X, padx=8)
        self.gen_pass_var = tk.StringVar()
        tk.Entry(f, textvariable=self.gen_pass_var, show="•",
                 bg="#0d0f18", fg=FG, insertbackground=FG,
                 relief=tk.FLAT, font=FONT).pack(fill=tk.X, padx=8, ipady=4, pady=(1,6))

        # Generate button
        tk.Button(f, text="  ⚡ GENERATE  ", font=FONTB,
                  bg="#1a1a2e", fg="#8080ff", relief=tk.FLAT,
                  activebackground="#252540",
                  command=self._do_generate).pack(fill=tk.X, padx=8, ipady=5, pady=2)

        # Result area (hidden until generated)
        self.result_frame = tk.Frame(f, bg=BG3)
        self.mnemonic_lbl = None

    def _do_generate(self):
        label = self.gen_label_var.get().strip()
        if not label:
            messagebox.showwarning("Missing", "Enter a wallet label."); return

        chains = [c for c, v in self.chain_vars.items() if v.get()]
        if not chains:
            messagebox.showwarning("Missing", "Select at least one chain."); return

        passphrase = self.gen_pass_var.get()
        words = self.words_var.get()

        # Generate
        try:
            mnemonic = generate_mnemonic(words)
            entry = create_wallet_entry(label, mnemonic, chains, passphrase)
        except Exception as e:
            messagebox.showerror("Error", f"Generation failed: {e}"); return

        self.gen_mnemonic = mnemonic
        self.gen_entry    = entry

        # Show result
        for w in self.result_frame.winfo_children():
            w.destroy()
        self.result_frame.pack(fill=tk.X, padx=8, pady=4)

        tk.Label(self.result_frame, text="⚠  WRITE DOWN YOUR MNEMONIC — SHOWN ONCE ONLY  ⚠",
                 bg="#1a0a00", fg=ORG, font=FONTB).pack(fill=tk.X, pady=(4,2))

        # Mnemonic display
        mn_frame = tk.Frame(self.result_frame, bg="#0a0800", pady=6)
        mn_frame.pack(fill=tk.X, pady=2)
        words_list = mnemonic.split()
        for i, word in enumerate(words_list):
            col = i // 4
            row = i % 4
            tk.Label(mn_frame, text=f"{i+1:2}. {word}", bg="#0a0800", fg=YEL,
                     font=FONT, width=16, anchor="w").grid(
                row=row, column=col, padx=4, pady=1, sticky="w")

        # Addresses preview
        addrs = entry.get("addresses", {})
        addr_frame = tk.Frame(self.result_frame, bg=BG3)
        addr_frame.pack(fill=tk.X, pady=4)
        for chain, info in addrs.items():
            col = CHAIN_COLORS.get(chain, FG2)
            row_f = tk.Frame(addr_frame, bg=BG3)
            row_f.pack(fill=tk.X, padx=4, pady=1)
            tk.Label(row_f, text=f"{chain}:", bg=BG3, fg=col,
                     font=FONTB, width=5).pack(side=tk.LEFT)
            tk.Label(row_f, text=info.get("address",""), bg=BG3, fg=FG,
                     font=FONTS).pack(side=tk.LEFT, padx=4)

        # Save button
        tk.Button(self.result_frame, text="  💾 SAVE TO VAULT  ", font=FONTB,
                  bg="#0e3518", fg=GRN, relief=tk.FLAT,
                  activebackground="#1a5020",
                  command=lambda: self._do_save(label, entry)
                  ).pack(fill=tk.X, ipady=5, pady=4)

        self.gen_inner.update_idletasks()

    def _do_save(self, label: str, entry: dict):
        if not service_ok():
            messagebox.showerror("Error", "vault_service.exe is not running!"); return

        # Public data (safe to store as api_key field)
        pub = {
            "label":     entry["label"],
            "addresses": entry["addresses"],
            "created_at": entry.get("created_at",""),
        }
        # Secret data (mnemonic + private keys, stored as api_secret — encrypted)
        sec = {
            "mnemonic":   entry["mnemonic"],
            "passphrase": entry.get("passphrase",""),
            "addresses":  entry["addresses"],  # includes private keys
        }
        pub_json = json.dumps(pub)
        sec_json = json.dumps(sec)

        err = vault_save_wallet(label, pub_json, sec_json)
        if err == VAULT_OK:
            messagebox.showinfo("Saved",
                f"Wallet '{label}' saved securely in Vault.\n\n"
                "Your mnemonic is now encrypted with DPAPI.\n"
                "Make sure you also have it written down offline!")
            self._toggle_gen()
            self._refresh()
        else:
            messagebox.showerror("Error",
                f"Save failed: {ERROR_NAMES.get(err, err)}\n"
                "Make sure vault_service.exe is running.")

    # ── Delete ────────────────────────────────────────────────
    def _do_delete(self, slot: int, label: str):
        if not messagebox.askyesno("Confirm Delete",
                f"Delete wallet '{label}'?\n\nThis CANNOT be undone.\n"
                "Make sure you have your mnemonic saved offline!"):
            return
        err = vault_delete_wallet(slot)
        if err == VAULT_OK:
            self._refresh()
        else:
            messagebox.showerror("Error", f"Delete failed: {ERROR_NAMES.get(err, err)}")

    # ── Refresh ───────────────────────────────────────────────
    def _refresh(self):
        ok = service_ok()
        self.svc_lbl.config(
            text="Vault: connected" if ok else "Vault: NOT running",
            fg=GRN if ok else RED)
        if ok:
            self.wallets = vault_list_wallets()
        else:
            self.wallets = []
        self._render_wallets()


# ── Entry point ───────────────────────────────────────────────
def run_standalone():
    k32 = ctypes.windll.kernel32
    hMutex = k32.CreateMutexA(None, True, b"Global\\OmnibusWalletManager")
    if k32.GetLastError() == 183:
        messagebox.showwarning("Already running", "OmnibusWallet is already open.")
        sys.exit(1)

    root = tk.Tk()
    app = WalletManagerApp(root)
    root.mainloop()

    k32.ReleaseMutex(hMutex)
    k32.CloseHandle(hMutex)


if __name__ == "__main__":
    run_standalone()
