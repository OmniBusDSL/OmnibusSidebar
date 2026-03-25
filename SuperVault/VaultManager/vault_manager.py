"""
vault_manager.py  --  OmniBus Vault Manager v3  (API KEYS + WALLET tabs)

Talks to vault_service.exe via Named Pipe \\\\.\\pipe\\OmnibusVault
Protocol v4: [opcode:1][exchange:1][slot:2][payload_len:2][payload]

Libraries: Python stdlib only (tkinter + ctypes + struct)
"""

import sys
import os
import json
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import ctypes
from ctypes import wintypes
import struct

# ── QR Code support (optional) ───────────────────────────────
try:
    import qrcode
    from PIL import Image, ImageTk
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

# ── Opcodes (must match vault_core.h v4) ─────────────────────
VAULT_OP_ADD        = 0x41
VAULT_OP_DELETE     = 0x43
VAULT_OP_LOCK       = 0x44
VAULT_OP_LIST       = 0x45
VAULT_OP_SET_STATUS = 0x46
VAULT_OP_COUNT      = 0x49

VAULT_KEY_STATUS_FREE    = 0
VAULT_KEY_STATUS_PAID    = 1
VAULT_KEY_STATUS_NOTPAID = 2

STATUS_LABEL = {0: "FREE", 1: "PAID", 2: "NOTPAID"}
STATUS_COLOR = {0: "#4488cc", 1: "#25c45a", 2: "#c03030"}

VAULT_OK             = 0
VAULT_ERR_NOT_FOUND  = 1
VAULT_ERR_DECRYPT    = 2
VAULT_ERR_IO         = 3
VAULT_ERR_LOCKED     = 4
VAULT_ERR_INVALID    = 5
VAULT_ERR_NO_SERVICE = 6
VAULT_ERR_FULL       = 7
VAULT_ERR_DUPLICATE  = 8

ERROR_NAMES = {
    0: "OK", 1: "Not found", 2: "Decrypt failed", 3: "IO error",
    4: "Vault locked", 5: "Invalid param", 6: "Service not running",
    7: "Max keys (8) reached", 8: "Name already exists"
}

EXCHANGE_NAMES = ["LCX", "Kraken", "Coinbase"]
PIPE_NAME = r"\\.\pipe\OmnibusVault"

# ── Named Pipe helpers ────────────────────────────────────────
kernel32 = ctypes.windll.kernel32
GENERIC_READ    = 0x80000000
GENERIC_WRITE   = 0x40000000
OPEN_EXISTING   = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

def pipe_call(request: bytes) -> bytes | None:
    """Open pipe, write request, read response, close."""
    kernel32.WaitNamedPipeA(PIPE_NAME.encode(), wintypes.DWORD(2000))

    h = kernel32.CreateFileA(
        PIPE_NAME.encode(),
        GENERIC_READ | GENERIC_WRITE,
        0, None, OPEN_EXISTING, 0, None
    )
    if h == INVALID_HANDLE_VALUE:
        print(f"[PIPE] CreateFileA FAILED LastError={kernel32.GetLastError()}")
        return None

    try:
        req_buf = ctypes.create_string_buffer(request, len(request))
        written = wintypes.DWORD(0)
        ok = kernel32.WriteFile(h, req_buf, wintypes.DWORD(len(request)),
                                ctypes.byref(written), None)
        if not ok:
            print(f"[PIPE] WriteFile FAILED LastError={kernel32.GetLastError()}")
            return None
        if written.value != len(request):
            print(f"[PIPE] WriteFile partial {written.value}/{len(request)}")
            return None

        kernel32.FlushFileBuffers(h)

        out_buf = ctypes.create_string_buffer(8192)
        read = wintypes.DWORD(0)
        ok = kernel32.ReadFile(h, out_buf, wintypes.DWORD(8192),
                               ctypes.byref(read), None)
        if not ok or read.value == 0:
            print(f"[PIPE] ReadFile FAILED ok={ok} read={read.value} LastError={kernel32.GetLastError()}")
            return None

        data = bytes(out_buf.raw[:read.value])
        print(f"[PIPE] OK sent={len(request)}b recv={read.value}b resp[0]=0x{data[0]:02X}")
        return data
    finally:
        kernel32.CloseHandle(h)

def service_available() -> bool:
    h = kernel32.CreateFileA(
        PIPE_NAME.encode(), GENERIC_READ | GENERIC_WRITE,
        0, None, OPEN_EXISTING, 0, None
    )
    if h == INVALID_HANDLE_VALUE:
        return False
    kernel32.CloseHandle(h)
    return True

# ── Protocol helpers ──────────────────────────────────────────
def pack_str(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<H", len(b)) + b

def unpack_str(data: bytes, pos: int):
    if pos + 2 > len(data):
        return "", pos
    slen = struct.unpack_from("<H", data, pos)[0]
    pos += 2
    s = data[pos:pos+slen].decode("utf-8", errors="replace")
    return s, pos + slen

def unpack_u32(data: bytes, pos: int):
    v = struct.unpack_from("<I", data, pos)[0]
    return v, pos + 4

# ── Service calls ─────────────────────────────────────────────
def svc_list(exch: int):
    req = struct.pack("<BBHH", VAULT_OP_LIST, exch, 0, 0)
    print(f"[LIST] exch={exch}")
    resp = pipe_call(req)
    if resp is None:
        return [], VAULT_ERR_NO_SERVICE
    print(f"[LIST] raw={resp.hex()}")
    if len(resp) < 3:
        print(f"[LIST] response too short ({len(resp)} bytes)")
        return [], VAULT_ERR_INVALID
    pos = 0
    err = resp[pos]; pos += 1
    plen = struct.unpack_from("<H", resp, pos)[0]; pos += 2
    print(f"[LIST] err={err} plen={plen} remaining={len(resp)-pos}")
    if err != VAULT_OK:
        print(f"[LIST] service error: {ERROR_NAMES.get(err)}")
        return [], err
    if len(resp) - pos < 4:
        print(f"[LIST] payload too short for count field, returning empty")
        return [], VAULT_OK
    cnt, pos = unpack_u32(resp, pos)
    print(f"[LIST] cnt={cnt}")
    keys = []
    for i in range(cnt):
        name,    pos = unpack_str(resp, pos)
        api_key, pos = unpack_str(resp, pos)
        slot,    pos = unpack_u32(resp, pos)
        status = resp[pos]; pos += 1
        print(f"[LIST]   [{i}] name='{name}' slot={slot} status={STATUS_LABEL.get(status, status)}")
        keys.append({"name": name, "api_key": api_key, "slot": slot, "status": status})
    return keys, VAULT_OK

def svc_add(exch: int, name: str, api_key: str, secret: str):
    payload = pack_str(name) + pack_str(api_key) + pack_str(secret)
    req = struct.pack("<BBHH", VAULT_OP_ADD, exch, 0, len(payload)) + payload
    print(f"[ADD] exch={exch} name='{name}' key_len={len(api_key)} sec_len={len(secret)}")
    resp = pipe_call(req)
    if resp is None:
        return VAULT_ERR_NO_SERVICE
    err = resp[0]
    print(f"[ADD] err={err} ({ERROR_NAMES.get(err)})")
    return err

def svc_delete(exch: int, slot: int):
    req = struct.pack("<BBHH", VAULT_OP_DELETE, exch, slot, 0)
    print(f"[DEL] exch={exch} slot={slot}")
    resp = pipe_call(req)
    if resp is None:
        return VAULT_ERR_NO_SERVICE
    err = resp[0]
    print(f"[DEL] err={err} ({ERROR_NAMES.get(err)})")
    return err

def svc_set_status(exch: int, slot: int, status: int):
    payload = struct.pack("B", status)
    req = struct.pack("<BBHH", VAULT_OP_SET_STATUS, exch, slot, len(payload)) + payload
    print(f"[SETSTATUS] exch={exch} slot={slot} status={STATUS_LABEL.get(status, status)}")
    resp = pipe_call(req)
    if resp is None:
        return VAULT_ERR_NO_SERVICE
    err = resp[0]
    print(f"[SETSTATUS] err={err} ({ERROR_NAMES.get(err)})")
    return err

def svc_lock():
    req = struct.pack("<BBHH", VAULT_OP_LOCK, 0, 0, 0)
    resp = pipe_call(req)
    return resp[0] if resp else VAULT_ERR_NO_SERVICE

# ── Wallet vault helpers ──────────────────────────────────────
WALLET_NAME_PREFIX = "WALLET:"

def vault_list_wallets() -> list:
    req = struct.pack("<BBHH", VAULT_OP_LIST, 0, 0, 0)
    resp = pipe_call(req)
    if not resp or len(resp) < 3:
        return []
    pos = 3  # skip err(1) + plen(2)
    if len(resp) - pos < 4:
        return []
    cnt, pos = unpack_u32(resp, pos)
    wallets = []
    for _ in range(cnt):
        name,    pos = unpack_str(resp, pos)
        api_key, pos = unpack_str(resp, pos)
        slot,    pos = unpack_u32(resp, pos)
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
    name = WALLET_NAME_PREFIX + label
    payload = pack_str(name) + pack_str(pub_json) + pack_str(secret_json)
    req = struct.pack("<BBHH", VAULT_OP_ADD, 0, 0, len(payload)) + payload
    resp = pipe_call(req)
    if resp is None:
        return VAULT_ERR_NO_SERVICE
    return resp[0]

def vault_delete_wallet(slot: int) -> int:
    req = struct.pack("<BBHH", VAULT_OP_DELETE, 0, slot, 0)
    resp = pipe_call(req)
    if resp is None:
        return VAULT_ERR_NO_SERVICE
    return resp[0]

# ── GUI colors/fonts ──────────────────────────────────────────
BG   = "#0d0f18"
BG2  = "#10121e"
BG3  = "#141820"
FG   = "#d0d0e0"
FG2  = "#808098"
ACC  = "#2e6ef5"
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

# ── QR Code popup ────────────────────────────────────────────
def show_qr_popup(parent, address: str, title: str = "Receive Address"):
    """Show a QR code popup for an address."""
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=BG)
    win.resizable(False, False)
    win.grab_set()

    tk.Label(win, text=title, bg=BG, fg=YEL, font=FONTB).pack(pady=(12, 4))

    if QR_AVAILABLE:
        qr = qrcode.QRCode(box_size=6, border=3,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(address)
        qr.make(fit=True)
        img_pil = qr.make_image(fill_color="white", back_color="#0d0f18")
        img_tk  = ImageTk.PhotoImage(img_pil)
        lbl = tk.Label(win, image=img_tk, bg=BG, padx=10, pady=6)
        lbl.image = img_tk  # keep reference
        lbl.pack()
    else:
        tk.Label(win,
                 text="qrcode / Pillow not installed.\npip install qrcode[pil]",
                 bg=BG, fg=RED, font=FONTS).pack(padx=30, pady=10)

    # Address text + copy
    addr_frame = tk.Frame(win, bg=BG2)
    addr_frame.pack(fill=tk.X, padx=14, pady=(4, 2))
    var = tk.StringVar(value=address)
    tk.Entry(addr_frame, textvariable=var, bg=BG2, fg=FG,
             relief=tk.FLAT, font=("Consolas", 9),
             readonlybackground=BG2, state="readonly").pack(
        side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(6, 0))
    tk.Button(addr_frame, text="Copy", font=FONTS, bg="#0e1e2e", fg="#4488cc",
              relief=tk.FLAT, padx=8,
              command=lambda: (win.clipboard_clear(), win.clipboard_append(address))
              ).pack(side=tk.RIGHT, padx=4)

    tk.Button(win, text="  Close  ", bg=BG3, fg=FG2, relief=tk.FLAT,
              font=FONTS, command=win.destroy).pack(pady=(6, 12))
    win.geometry("")  # auto-size


# ── API KEYS tab ─────────────────────────────────────────────
class ApiKeysTab:
    def __init__(self, parent: tk.Frame, svc_lbl: tk.Label):
        self.parent  = parent
        self.svc_lbl = svc_lbl
        self.cur_exch = 0
        self.keys = [[], [], []]

        self._build_ui()
        self._refresh()

    def _build_ui(self):
        # Exchange selector
        exch_frame = tk.Frame(self.parent, bg=BG, pady=6)
        exch_frame.pack(fill=tk.X, padx=10)
        self.exch_btns = []
        for i, name in enumerate(EXCHANGE_NAMES):
            b = tk.Button(exch_frame, text=name, font=FONTB,
                          bg=BG3, fg=FG2, relief=tk.FLAT,
                          activebackground="#1e2540", activeforeground=FG,
                          width=10, pady=4,
                          command=lambda i=i: self._select_exch(i))
            b.pack(side=tk.LEFT, padx=3)
            self.exch_btns.append(b)

        tk.Frame(self.parent, bg="#1a1c2e", height=1).pack(fill=tk.X, padx=10)

        # Key list area
        list_frame = tk.Frame(self.parent, bg=BG2)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6,0))

        self.count_lbl = tk.Label(list_frame, text="STORED KEYS  0 / 8",
                                   bg=BG2, fg=FG2, font=FONTS, anchor="w")
        self.count_lbl.pack(fill=tk.X, padx=8, pady=(6,2))

        canvas_frame = tk.Frame(list_frame, bg=BG2)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg=BG2, highlightthickness=0)
        sb = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.list_inner = tk.Frame(self.canvas, bg=BG2)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.list_inner, anchor="nw")
        self.list_inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(
            self.canvas_window, width=e.width))

        # Add key form
        add_frame = tk.Frame(self.parent, bg=BG3, pady=8)
        add_frame.pack(fill=tk.X, padx=10, pady=4)

        self.show_add = False
        self.add_toggle_btn = tk.Button(add_frame, text="  + ADD KEY  ", font=FONTB,
                                         bg="#0e2e14", fg=GRN, relief=tk.FLAT,
                                         activebackground="#1a4020",
                                         command=self._toggle_add)
        self.add_toggle_btn.pack(fill=tk.X, padx=8, pady=(0,4))

        self.add_inner = tk.Frame(add_frame, bg=BG3)

        tk.Label(self.add_inner, text="NAME", bg=BG3, fg=FG2, font=FONTS, anchor="w").pack(
            fill=tk.X, padx=8)
        self.new_name = tk.Entry(self.add_inner, bg="#0d0f18", fg=FG,
                                  insertbackground=FG, relief=tk.FLAT, font=FONT)
        self.new_name.pack(fill=tk.X, padx=8, pady=(1,6), ipady=4)

        tk.Label(self.add_inner, text="API KEY", bg=BG3, fg=FG2, font=FONTS, anchor="w").pack(
            fill=tk.X, padx=8)
        self.new_key = tk.Entry(self.add_inner, bg="#0d0f18", fg=FG,
                                 insertbackground=FG, relief=tk.FLAT, font=FONT)
        self.new_key.pack(fill=tk.X, padx=8, pady=(1,6), ipady=4)

        tk.Label(self.add_inner, text="API SECRET  (encrypted, never shown again)",
                 bg=BG3, fg=FG2, font=FONTS, anchor="w").pack(fill=tk.X, padx=8)
        self.new_sec = tk.Entry(self.add_inner, bg="#0d0f18", fg=FG,
                                 insertbackground=FG, relief=tk.FLAT, font=FONT, show="•")
        self.new_sec.pack(fill=tk.X, padx=8, pady=(1,6), ipady=4)

        self.add_status = tk.Label(self.add_inner, text="", bg=BG3, fg=RED, font=FONTS)
        self.add_status.pack(fill=tk.X, padx=8)

        tk.Button(self.add_inner, text="  SAVE KEY  ", font=FONTB,
                  bg="#0e3518", fg=GRN, relief=tk.FLAT,
                  activebackground="#1a5020",
                  command=self._do_add).pack(fill=tk.X, padx=8, pady=(4,2), ipady=5)

        # Footer bar
        bot = tk.Frame(self.parent, bg="#0a0c14", pady=5)
        bot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(bot, text="Refresh", bg=BG3, fg=FG2, relief=tk.FLAT,
                  font=FONTS, command=self._refresh).pack(side=tk.LEFT, padx=8)
        tk.Button(bot, text="Lock & Clear Memory", bg=BG3, fg="#6060a0",
                  relief=tk.FLAT, font=FONTS, command=self._lock_all).pack(side=tk.LEFT)
        tk.Label(bot, text="vault.dat @ %APPDATA%\\OmnibusSidebar  |  DPAPI",
                 bg="#0a0c14", fg="#282838", font=("Consolas", 8)).pack(side=tk.RIGHT, padx=10)

        self._select_exch(0)

    def _select_exch(self, i):
        EXCH_COLS = ["#2e6ef5", "#8844ff", "#20c090"]
        self.cur_exch = i
        for j, b in enumerate(self.exch_btns):
            if j == i:
                b.config(bg="#1a2240", fg=EXCH_COLS[j])
            else:
                b.config(bg=BG3, fg=FG2)
        self._render_keys()

    def _render_keys(self):
        for w in self.list_inner.winfo_children():
            w.destroy()

        keys = self.keys[self.cur_exch]
        self.count_lbl.config(text=f"STORED KEYS  {len(keys)} / 8  —  {EXCHANGE_NAMES[self.cur_exch]}")

        if not keys:
            tk.Label(self.list_inner, text="No keys stored for this exchange.",
                     bg=BG2, fg=FG2, font=FONTS).pack(pady=20)
            return

        for k in keys:
            row = tk.Frame(self.list_inner, bg=BG2, pady=4)
            row.pack(fill=tk.X, padx=6, pady=2)

            st = k["status"]
            dot_col = STATUS_COLOR.get(st, FG2)
            tk.Label(row, text="●", bg=BG2, fg=dot_col, font=FONTB, width=2).pack(side=tk.LEFT)
            name_col = FG if st != VAULT_KEY_STATUS_NOTPAID else "#606060"
            tk.Label(row, text=k["name"], bg=BG2, fg=name_col, font=FONTB).pack(side=tk.LEFT, padx=4)

            masked = self._mask(k["api_key"])
            tk.Label(row, text=f"API: {masked}", bg=BG2, fg="#404060", font=FONTS).pack(
                side=tk.LEFT, padx=8)

            badge_bg = {"FREE": "#0a1830", "PAID": "#0a2010", "NOTPAID": "#2e0808"}
            badge_fg = {"FREE": "#4488cc", "PAID": "#25c45a",  "NOTPAID": "#c03030"}
            slabel = STATUS_LABEL.get(st, "?")
            tk.Label(row, text=slabel, bg=badge_bg.get(slabel, BG2),
                     fg=badge_fg.get(slabel, FG2),
                     font=("Consolas", 8, "bold"), padx=6).pack(side=tk.RIGHT, padx=4)

            next_status = {VAULT_KEY_STATUS_FREE: VAULT_KEY_STATUS_PAID,
                           VAULT_KEY_STATUS_PAID: VAULT_KEY_STATUS_NOTPAID,
                           VAULT_KEY_STATUS_NOTPAID: VAULT_KEY_STATUS_FREE}
            ns = next_status.get(st, VAULT_KEY_STATUS_FREE)
            ns_label = STATUS_LABEL.get(ns, "?")
            tk.Button(row, text=f"→{ns_label}", font=FONTS,
                      bg=BG3, fg=FG2, relief=tk.FLAT,
                      activebackground="#1e2030",
                      command=lambda s=k["slot"], nst=ns: self._do_set_status(s, nst)
                      ).pack(side=tk.RIGHT, padx=2)

            tk.Button(row, text="Delete", font=FONTS,
                      bg="#2e0e0e", fg=RED, relief=tk.FLAT,
                      activebackground="#401414",
                      command=lambda s=k["slot"], n=k["name"]: self._do_delete(s, n)
                      ).pack(side=tk.RIGHT, padx=2)

            tk.Frame(self.list_inner, bg="#1a1c2e", height=1).pack(fill=tk.X, padx=6)

    def _mask(self, key: str) -> str:
        if len(key) <= 12:
            return key
        return key[:8] + "..." + key[-4:]

    def _refresh(self):
        if service_available():
            self.svc_lbl.config(text="Service: connected", fg=GRN)
        else:
            self.svc_lbl.config(text="Service: NOT running", fg=RED)
        for e in range(3):
            keys, err = svc_list(e)
            self.keys[e] = keys if keys else []
        self._render_keys()

    def _toggle_add(self):
        self.show_add = not self.show_add
        if self.show_add:
            self.add_toggle_btn.config(text="  - CANCEL  ", bg="#2e0e0e", fg=RED)
            self.add_inner.pack(fill=tk.X)
            self.new_name.focus_set()
        else:
            self.add_toggle_btn.config(text="  + ADD KEY  ", bg="#0e2e14", fg=GRN)
            self.add_inner.pack_forget()
            self.new_name.delete(0, tk.END)
            self.new_key.delete(0, tk.END)
            self.new_sec.delete(0, tk.END)
            self.add_status.config(text="")

    def _do_add(self):
        name = self.new_name.get().strip()
        key  = self.new_key.get().strip()
        sec  = self.new_sec.get().strip()
        if not name:
            self.add_status.config(text="Name is required"); return
        if not key:
            self.add_status.config(text="API Key is required"); return
        if not sec:
            self.add_status.config(text="API Secret is required"); return

        err = svc_add(self.cur_exch, name, key, sec)
        self.new_sec.delete(0, tk.END)

        if err == VAULT_OK:
            self.add_status.config(text="")
            self._toggle_add()
            self._refresh()
            messagebox.showinfo("Saved", f"Key '{name}' saved for {EXCHANGE_NAMES[self.cur_exch]}.")
        else:
            self.add_status.config(text=f"Error: {ERROR_NAMES.get(err, err)}")

    def _do_delete(self, slot: int, name: str):
        if not messagebox.askyesno("Confirm Delete",
                f"Delete key '{name}' from {EXCHANGE_NAMES[self.cur_exch]}?\n\nThis cannot be undone."):
            return
        err = svc_delete(self.cur_exch, slot)
        if err == VAULT_OK:
            self._refresh()
        else:
            messagebox.showerror("Error", f"Delete failed: {ERROR_NAMES.get(err, err)}")

    def _do_set_status(self, slot: int, status: int):
        err = svc_set_status(self.cur_exch, slot, status)
        if err == VAULT_OK:
            self._refresh()
        else:
            messagebox.showerror("Error", f"Set status failed: {ERROR_NAMES.get(err, err)}")

    def _lock_all(self):
        err = svc_lock()
        if err == VAULT_OK:
            messagebox.showinfo("Locked", "Vault locked — keys cleared from service memory.\nRestart vault_service.exe to unlock.")
        else:
            messagebox.showerror("Error", f"Lock failed: {ERROR_NAMES.get(err, err)}")


# ── WALLET tab ───────────────────────────────────────────────
# Import OmnibusWallet — look in SuperVault root
_HERE   = os.path.dirname(os.path.abspath(__file__))
_SUPER  = os.path.dirname(_HERE)   # SuperVault/
if _SUPER not in sys.path:
    sys.path.insert(0, _SUPER)

try:
    from OmnibusWallet.wallet_core import (
        generate_mnemonic, create_wallet_entry,
    )
    from OmnibusWallet.chains import CHAINS, CHAIN_NAMES, CHAIN_COLORS, CHAIN_GROUPS
    from OmnibusWallet.wallet_store import (
        wallet_list, wallet_save, wallet_delete, wallet_get,
        wallet_update_address_meta,
    )
    from OmnibusWallet.pq_domain import OMNIBUS_DOMAINS, generate_pq_domains
    from OmnibusWallet.balance_fetcher import fetch_balance
    WALLET_AVAILABLE = True
except ImportError as _we:
    WALLET_AVAILABLE = False
    _WALLET_IMPORT_ERROR = str(_we)
    OMNIBUS_DOMAINS = []

ALL_CHAINS = list(CHAINS.keys()) if WALLET_AVAILABLE else []


class WalletTab:
    def __init__(self, parent: tk.Frame, svc_lbl: tk.Label):
        self.parent  = parent
        self.svc_lbl = svc_lbl
        self.wallets    = []
        self.show_gen   = False
        self.gen_mnemonic = ""
        self.gen_entry    = {}

        self._build_ui()
        self._refresh()

    def _build_ui(self):
        if not WALLET_AVAILABLE:
            tk.Label(self.parent,
                     text=f"OmnibusWallet not available:\n{_WALLET_IMPORT_ERROR}",
                     bg=BG, fg=RED, font=FONTS, wraplength=500, justify="left"
                     ).pack(padx=20, pady=30)
            return

        # Footer first so it anchors to bottom before expand=True eats space
        bot = tk.Frame(self.parent, bg="#0a0c14", pady=5)
        bot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(bot, text="Refresh", bg=BG3, fg=FG2, relief=tk.FLAT,
                  font=FONTS, command=self._refresh).pack(side=tk.LEFT, padx=8)
        tk.Button(bot, text="Import Wallet", bg=BG3, fg="#4488cc", relief=tk.FLAT,
                  font=FONTS, command=self._do_import).pack(side=tk.LEFT, padx=2)
        tk.Label(bot, text="Secured by OmniBus Vault  ·  DPAPI encrypted",
                 bg="#0a0c14", fg="#282838", font=("Consolas",8)).pack(side=tk.RIGHT, padx=10)

        # Main area: top=list, bottom=generate panel (scrollable)
        main = tk.Frame(self.parent, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        # ── TOP: wallet list (expands) ──
        list_frame = tk.Frame(main, bg=BG2)
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

        # ── BOTTOM: generate panel with its own scrollable canvas ──
        gen_outer = tk.Frame(main, bg=BG3)
        gen_outer.pack(fill=tk.X, padx=10, pady=(0,4))

        self.gen_btn = tk.Button(gen_outer, text="  + GENERATE NEW WALLET  ",
                                  font=FONTB, bg="#0e2e14", fg=GRN, relief=tk.FLAT,
                                  activebackground="#1a4020",
                                  command=self._toggle_gen)
        self.gen_btn.pack(fill=tk.X, padx=8, pady=4)

        # Scrollable container for the form (height capped, scrollbar appears when needed)
        self.gen_scroll_frame = tk.Frame(gen_outer, bg=BG3)
        # packed on demand in _toggle_gen

        self.gen_canvas = tk.Canvas(self.gen_scroll_frame, bg=BG3,
                                     highlightthickness=0, height=260)
        gen_sb = ttk.Scrollbar(self.gen_scroll_frame, orient="vertical",
                                command=self.gen_canvas.yview)
        self.gen_canvas.configure(yscrollcommand=gen_sb.set)
        gen_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.gen_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.gen_inner = tk.Frame(self.gen_canvas, bg=BG3)
        self._gen_cw = self.gen_canvas.create_window((0,0), window=self.gen_inner, anchor="nw")
        self.gen_inner.bind("<Configure>", lambda e: self.gen_canvas.configure(
            scrollregion=self.gen_canvas.bbox("all")))
        self.gen_canvas.bind("<Configure>", lambda e: self.gen_canvas.itemconfig(
            self._gen_cw, width=e.width))

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

            title_row = tk.Frame(card, bg=BG3)
            title_row.pack(fill=tk.X, padx=8)

            src = wallet.get("source", "omnibus_generated")
            is_imported = (src == "imported")
            dot_col = "#4488cc" if is_imported else YEL
            dot_chr = "▼" if is_imported else "◆"
            src_tag = " [IMPORTED]" if is_imported else " [OMNIBUS]"
            src_col = "#4060a0" if is_imported else "#406040"

            tk.Label(title_row, text=dot_chr, bg=BG3, fg=dot_col, font=FONTB).pack(side=tk.LEFT)
            tk.Label(title_row, text=wallet["label"], bg=BG3, fg=FG, font=FONTB).pack(side=tk.LEFT, padx=6)
            tk.Label(title_row, text=src_tag, bg=BG3, fg=src_col, font=FONTS).pack(side=tk.LEFT)

            tk.Button(title_row, text="Delete", font=FONTS,
                      bg="#2e0e0e", fg=RED, relief=tk.FLAT,
                      command=lambda wid=wallet["id"], l=wallet["label"]: self._do_delete(wid, l)
                      ).pack(side=tk.RIGHT, padx=2)
            tk.Button(title_row, text="Export", font=FONTS,
                      bg="#0e1e2e", fg="#4488cc", relief=tk.FLAT,
                      activebackground="#162840",
                      command=lambda w=wallet: self._do_export(w)
                      ).pack(side=tk.RIGHT, padx=2)
            tk.Button(title_row, text="Addresses", font=FONTS,
                      bg="#0e1e0e", fg="#25c45a", relief=tk.FLAT,
                      activebackground="#162816",
                      command=lambda w=wallet: self._show_addresses(w)
                      ).pack(side=tk.RIGHT, padx=2)
            tk.Button(title_row, text="Balance", font=FONTS,
                      bg="#0e1a10", fg="#20a050", relief=tk.FLAT,
                      activebackground="#162818",
                      command=lambda w=wallet: self._fetch_balances(w)
                      ).pack(side=tk.RIGHT, padx=2)
            # Send button — only shown if wallet has OMNI
            if "OMNI" in wallet.get("addresses", {}):
                tk.Button(title_row, text="Send", font=FONTS,
                          bg="#1a0e0e", fg="#f7931a", relief=tk.FLAT,
                          activebackground="#2a1414",
                          command=lambda w=wallet: show_send_omni_popup(self.parent, w)
                          ).pack(side=tk.RIGHT, padx=2)

            # Chain badges + balance
            chains = wallet.get("chains", list(wallet.get("addresses", {}).keys()))
            badges = tk.Frame(card, bg=BG3)
            badges.pack(fill=tk.X, padx=12, pady=(2,4))
            for chain in chains:
                col  = CHAIN_COLORS.get(chain, FG2)
                info = wallet.get("addresses", {}).get(chain, {})
                bal  = info.get("bal", 0.0)
                bal_str = f" {bal:.4f}" if bal and bal > 0 else ""
                lbl_text = chain + bal_str
                tk.Label(badges, text=lbl_text, bg="#0d0f18", fg=col,
                         font=("Consolas", 8, "bold"), padx=5, pady=1).pack(side=tk.LEFT, padx=2)

            tk.Frame(self.list_inner, bg="#1a1c2e", height=1).pack(fill=tk.X, padx=6)

    def _toggle_gen(self):
        """Open wallet generator as a split Toplevel window."""
        self._open_gen_window()

    def _open_gen_window(self):
        """Wallet generator in its own resizable window, split left/right."""
        win = tk.Toplevel(self.parent)
        win.title("Generate New Wallet")
        win.geometry("1000x560")
        win.minsize(800, 480)
        win.configure(bg=BG)
        win.grab_set()  # modal

        # ── Header ───────────────────────────────────────────────
        hdr = tk.Frame(win, bg="#0a0c14", pady=7)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="GENERATE NEW WALLET", bg="#0a0c14",
                 fg=YEL, font=("Consolas", 12, "bold")).pack(side=tk.LEFT, padx=14)
        tk.Button(hdr, text="  CLOSE  ", bg="#2e0e0e", fg=RED, relief=tk.FLAT,
                  font=FONTS, command=win.destroy).pack(side=tk.RIGHT, padx=10)

        # ── Split: left = form, right = result ───────────────────
        body = tk.Frame(win, bg=BG)
        body.pack(fill=tk.BOTH, expand=True)

        left  = tk.Frame(body, bg=BG3, width=380)
        right = tk.Frame(body, bg=BG2)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(8,4), pady=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4,8), pady=8)
        left.pack_propagate(False)

        # ── LEFT: form ───────────────────────────────────────────
        tk.Label(left, text="WALLET LABEL", bg=BG3, fg=FG2, font=FONTS, anchor="w").pack(
            fill=tk.X, padx=10, pady=(10,0))
        gen_label_var = tk.StringVar()
        tk.Entry(left, textvariable=gen_label_var, bg="#0d0f18", fg=FG,
                 insertbackground=FG, relief=tk.FLAT, font=FONT).pack(
            fill=tk.X, padx=10, ipady=4, pady=(2,10))

        tk.Label(left, text="CHAINS", bg=BG3, fg=FG2, font=FONTS, anchor="w").pack(
            fill=tk.X, padx=10)

        chain_vars = {}
        # Import CHAIN_GROUPS for grouped display
        try:
            from OmnibusWallet.chains import CHAIN_GROUPS as _CG
        except Exception:
            _CG = {"All": ALL_CHAINS}

        group_label_colors = {
            "OmniBus":     "#00c8ff",
            "OmniDomains": "#9945ff",
            "Layer 1":     "#808098",
            "EVM":         "#627eea",
            "UTXO":        "#f7931a",
        }
        try:
            from OmnibusWallet.chains import CHAIN_NON_TRANSFERABLE as _CNT
        except Exception:
            _CNT = set()

        for group_name, group_chains in _CG.items():
            g_frame = tk.Frame(left, bg=BG3)
            g_frame.pack(fill=tk.X, padx=10, pady=(3,0))
            glbl = group_name if group_name != "OmniDomains" else "OmniDomains ✦"
            tk.Label(g_frame, text=glbl, bg=BG3,
                     fg=group_label_colors.get(group_name, FG2),
                     font=("Consolas", 8, "bold"), width=14, anchor="w").pack(side=tk.LEFT)
            for chain in group_chains:
                is_nt = chain in _CNT
                var = tk.BooleanVar(value=(chain in ("BTC","ETH","SOL","BNB","OMNI_OMNI","OMNI_LOVE")))
                chain_vars[chain] = var
                col = CHAIN_COLORS.get(chain, FG2)
                lbl = chain.replace("OMNI_","") if chain.startswith("OMNI_") else chain
                tk.Checkbutton(g_frame, text=lbl, variable=var,
                               bg=BG3, fg=col, selectcolor="#0d0f18",
                               activebackground=BG3, activeforeground=col,
                               font=("Consolas", 8, "bold")).pack(side=tk.LEFT, padx=3)
        # spacer
        tk.Frame(left, bg=BG3, height=6).pack()

        tk.Label(left, text="MNEMONIC WORDS", bg=BG3, fg=FG2, font=FONTS, anchor="w").pack(
            fill=tk.X, padx=10)
        words_row = tk.Frame(left, bg=BG3)
        words_row.pack(fill=tk.X, padx=10, pady=(2,10))
        words_var = tk.IntVar(value=24)
        for w in [12, 24]:
            tk.Radiobutton(words_row, text=f"{w} words", variable=words_var, value=w,
                           bg=BG3, fg=FG, selectcolor="#0d0f18",
                           activebackground=BG3, font=FONTS).pack(side=tk.LEFT, padx=8)

        tk.Label(left, text="BIP39 PASSPHRASE  (optional)",
                 bg=BG3, fg=FG2, font=FONTS, anchor="w").pack(fill=tk.X, padx=10)
        gen_pass_var = tk.StringVar()
        tk.Entry(left, textvariable=gen_pass_var, show="•",
                 bg="#0d0f18", fg=FG, insertbackground=FG,
                 relief=tk.FLAT, font=FONT).pack(fill=tk.X, padx=10, ipady=4, pady=(2,8))

        pq_var = tk.BooleanVar(value=True)
        tk.Checkbutton(left, text="Include PQ Domains  (OmniBus post-quantum keys)",
                       variable=pq_var, bg=BG3, fg="#00c8ff",
                       selectcolor="#0d0f18", activebackground=BG3,
                       activeforeground="#00c8ff",
                       font=("Consolas", 8, "bold")).pack(anchor="w", padx=10, pady=(0,10))

        gen_status = tk.Label(left, text="", bg=BG3, fg=RED, font=FONTS)
        gen_status.pack(fill=tk.X, padx=10)

        tk.Button(left, text="  ⚡ GENERATE  ", font=FONTB,
                  bg="#1a1a2e", fg="#8080ff", relief=tk.FLAT,
                  activebackground="#252540",
                  command=lambda: _do_gen()
                  ).pack(fill=tk.X, padx=10, ipady=6, pady=6)

        # ── RIGHT: result area ───────────────────────────────────
        tk.Label(right, text="RESULT", bg=BG2, fg=FG2, font=FONTS, anchor="w").pack(
            fill=tk.X, padx=10, pady=(10,2))

        result_canvas = tk.Canvas(right, bg=BG2, highlightthickness=0)
        r_sb = ttk.Scrollbar(right, orient="vertical", command=result_canvas.yview)
        result_canvas.configure(yscrollcommand=r_sb.set)
        r_sb.pack(side=tk.RIGHT, fill=tk.Y)
        result_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        result_inner = tk.Frame(result_canvas, bg=BG2)
        r_cw = result_canvas.create_window((0,0), window=result_inner, anchor="nw")
        result_inner.bind("<Configure>", lambda e: result_canvas.configure(
            scrollregion=result_canvas.bbox("all")))
        result_canvas.bind("<Configure>", lambda e: result_canvas.itemconfig(
            r_cw, width=e.width))

        pending_entry = [None]  # holds generated entry for save/export

        def _show_result(entry: dict):
            for w in result_inner.winfo_children():
                w.destroy()
            mnemonic = entry.get("mnemonic","")

            # Warning
            tk.Label(result_inner,
                     text="⚠  WRITE DOWN YOUR MNEMONIC — SHOWN ONCE ONLY  ⚠",
                     bg="#1a0a00", fg=ORG, font=FONTB,
                     wraplength=580).pack(fill=tk.X, padx=8, pady=(8,2))

            # Mnemonic grid
            mn_frame = tk.Frame(result_inner, bg="#0a0800", pady=8)
            mn_frame.pack(fill=tk.X, padx=8, pady=4)
            words_list = mnemonic.split()
            cols = 6 if len(words_list) == 24 else 4
            for i, word in enumerate(words_list):
                c = i % cols
                r = i // cols
                tk.Label(mn_frame, text=f"{i+1:2}. {word}",
                         bg="#0a0800", fg=YEL, font=FONT,
                         width=14, anchor="w").grid(
                    row=r, column=c, padx=4, pady=2, sticky="w")

            # Addresses (full, copyable)
            tk.Label(result_inner, text="ADDRESSES", bg=BG2, fg=FG2,
                     font=FONTS, anchor="w").pack(fill=tk.X, padx=8, pady=(8,2))
            addrs = entry.get("addresses", {})
            for chain, info in addrs.items():
                chain_col = CHAIN_COLORS.get(chain, FG2)
                af = tk.Frame(result_inner, bg=BG3, pady=4)
                af.pack(fill=tk.X, padx=8, pady=2)
                tk.Label(af, text=f"{chain}", bg=BG3, fg=chain_col,
                         font=FONTB, width=6).pack(side=tk.LEFT, padx=(8,4))
                addr = info.get("address","")
                addr_var = tk.StringVar(value=addr)
                addr_entry = tk.Entry(af, textvariable=addr_var, bg=BG3, fg=FG,
                                      relief=tk.FLAT, font=FONTS,
                                      readonlybackground=BG3, state="readonly")
                addr_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
                tk.Button(af, text="Copy", font=FONTS, bg="#0e1e2e", fg="#4488cc",
                          relief=tk.FLAT,
                          command=lambda a=addr: (win.clipboard_clear(), win.clipboard_append(a))
                          ).pack(side=tk.RIGHT, padx=6)

            # PQ Domains preview
            pq_domains = entry.get("pq_domains", {})
            if pq_domains:
                tk.Label(result_inner, text="PQ DOMAINS  (OmniBus post-quantum)",
                         bg=BG2, fg="#00c8ff", font=FONTS, anchor="w").pack(
                    fill=tk.X, padx=8, pady=(10,2))
                for dk, di in pq_domains.items():
                    alg = di.get("pq_algorithm","")
                    df = tk.Frame(result_inner, bg=BG3, pady=3)
                    df.pack(fill=tk.X, padx=8, pady=1)
                    tk.Label(df, text=dk, bg=BG3, fg="#00c8ff",
                             font=("Consolas",8,"bold"), width=20, anchor="w").pack(side=tk.LEFT, padx=6)
                    tk.Label(df, text=alg, bg=BG3, fg="#2a6070",
                             font=("Consolas",8), width=14).pack(side=tk.LEFT)
                    addr = di.get("addr","")
                    av = tk.StringVar(value=addr)
                    tk.Entry(df, textvariable=av, bg=BG3, fg="#00c8ff",
                             relief=tk.FLAT, font=("Consolas",8),
                             readonlybackground=BG3, state="readonly").pack(
                        side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
                    tk.Button(df, text="Copy", font=("Consolas",8),
                              bg="#0e1e2e", fg="#4488cc", relief=tk.FLAT,
                              command=lambda a=addr: (win.clipboard_clear(), win.clipboard_append(a))
                              ).pack(side=tk.RIGHT, padx=4)

            # Action buttons
            btn_row = tk.Frame(result_inner, bg=BG2)
            btn_row.pack(fill=tk.X, padx=8, pady=10)
            tk.Button(btn_row, text="  SAVE TO VAULT  ", font=FONTB,
                      bg="#0e3518", fg=GRN, relief=tk.FLAT, activebackground="#1a5020",
                      command=lambda: (_do_save_and_close(entry))
                      ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0,3))
            tk.Button(btn_row, text="  EXPORT FULL BACKUP  ", font=FONTB,
                      bg="#0e1a2e", fg="#4488cc", relief=tk.FLAT, activebackground="#162840",
                      command=lambda: self._export_full(entry)
                      ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(3,0))

            result_canvas.update_idletasks()
            result_canvas.configure(scrollregion=result_canvas.bbox("all"))

        def _do_gen():
            label = gen_label_var.get().strip()
            if not label:
                gen_status.config(text="Enter a wallet label."); return
            chains = [c for c, v in chain_vars.items() if v.get()]
            if not chains:
                gen_status.config(text="Select at least one chain."); return
            gen_status.config(text="Generating...")
            win.update_idletasks()
            try:
                mnemonic = generate_mnemonic(words_var.get())
                entry = create_wallet_entry(label, mnemonic, chains,
                                            gen_pass_var.get(),
                                            include_pq_domains=pq_var.get())
            except Exception as e:
                gen_status.config(text=f"Error: {e}"); return
            gen_status.config(text="")
            pending_entry[0] = entry
            _show_result(entry)

        def _do_save_and_close(entry: dict):
            self._do_save(entry.get("label",""), entry)
            win.destroy()

    def _do_save(self, label: str, entry: dict):
        try:
            wallet_save(
                label      = label,
                mnemonic   = entry.get("mnemonic", ""),
                passphrase = entry.get("passphrase", ""),
                addresses  = entry.get("addresses", {}),
                chains     = entry.get("chains", list(entry.get("addresses", {}).keys())),
                source     = entry.get("source", "omnibus_generated"),
                pq_domains = entry.get("pq_domains"),
            )
            messagebox.showinfo("Saved",
                f"Wallet '{label}' saved securely.\n\n"
                "Encrypted with DPAPI in wallets.dat\n"
                "Keep a written mnemonic backup offline!")
            self._refresh()
        except ValueError as e:
            messagebox.showerror("Error", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"Save failed:\n{e}")

    def _show_addresses(self, wallet: dict):
        """Show full metadata for all chains — addresses, pubkeys, privkeys, paths."""
        label = wallet["label"]
        addrs = wallet.get("addresses", {})

        win = tk.Toplevel(self.parent)
        win.title(f"Wallet Details — {label}")
        win.geometry("720x560")
        win.minsize(600, 400)
        win.configure(bg=BG)
        win.resizable(True, True)

        # Header
        hdr = tk.Frame(win, bg="#0a0c14", pady=7)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"WALLET DETAILS  —  {label}", bg="#0a0c14",
                 fg=YEL, font=FONTB).pack(side=tk.LEFT, padx=14)
        tk.Button(hdr, text="Close", bg=BG3, fg=FG2, relief=tk.FLAT,
                  font=FONTS, command=win.destroy).pack(side=tk.RIGHT, padx=10)

        # Scrollable body
        body_wrap = tk.Frame(win, bg=BG)
        body_wrap.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(body_wrap, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(body_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = tk.Frame(canvas, bg=BG)
        cw = canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))

        def _copy_row(parent, label_text, value, label_fg=FG2, show_qr=False):
            """One field row: label + readonly entry + copy button + optional QR."""
            f = tk.Frame(parent, bg=BG2)
            f.pack(fill=tk.X, padx=0, pady=1)
            tk.Label(f, text=label_text, bg=BG2, fg=label_fg,
                     font=("Consolas", 8), width=22, anchor="w").pack(side=tk.LEFT, padx=(8,2))
            var = tk.StringVar(value=value)
            tk.Entry(f, textvariable=var, bg=BG2, fg=FG, relief=tk.FLAT,
                     font=("Consolas", 9), readonlybackground=BG2,
                     state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
            if show_qr and value:
                tk.Button(f, text="QR", font=("Consolas", 8), bg="#0e1a0e", fg=GRN,
                          relief=tk.FLAT, padx=5,
                          command=lambda v=value, lt=label_text: show_qr_popup(win, v, lt)
                          ).pack(side=tk.RIGHT, padx=2)
            tk.Button(f, text="Copy", font=("Consolas", 8), bg="#0e1e2e", fg="#4488cc",
                      relief=tk.FLAT, padx=6,
                      command=lambda v=value: (win.clipboard_clear(), win.clipboard_append(v))
                      ).pack(side=tk.RIGHT, padx=4)

        try:
            from OmnibusWallet.chains import CHAIN_NON_TRANSFERABLE as _CNT2
        except Exception:
            _CNT2 = set()

        for chain, info in addrs.items():
            chain_col  = CHAIN_COLORS.get(chain, FG2)
            is_nt      = chain in _CNT2
            hdr_bg     = "#0a0c18" if is_nt else BG3

            # Chain header
            ch_hdr = tk.Frame(inner, bg=hdr_bg, pady=5)
            ch_hdr.pack(fill=tk.X, padx=8, pady=(10,2))
            tk.Label(ch_hdr, text=f"  {chain}  {CHAIN_NAMES.get(chain,'')}",
                     bg=hdr_bg, fg=chain_col, font=FONTB).pack(side=tk.LEFT, padx=6)
            if is_nt:
                tk.Label(ch_hdr, text="  ✦ collection · non-transferable",
                         bg=hdr_bg, fg="#3a2060", font=("Consolas",8)).pack(side=tk.LEFT)
            path = info.get("derivation_path","")
            tk.Label(ch_hdr, text=path, bg=hdr_bg, fg="#404060", font=FONTS).pack(side=tk.LEFT, padx=8)

            block = tk.Frame(inner, bg=BG2)
            block.pack(fill=tk.X, padx=8, pady=(0,4))

            # Address(es)
            _copy_row(block, "Address", info.get("address",""), chain_col, show_qr=True)
            if info.get("address_btc"):
                _copy_row(block, "BTC Anchor Addr", info["address_btc"], "#f7931a", show_qr=True)
            if info.get("address_legacy"):
                _copy_row(block, "Address (Legacy)", info["address_legacy"], "#a0a060", show_qr=True)
                _copy_row(block, "Path (Legacy)", info.get("derivation_path_legacy",""), "#404060")

            # Public key
            if info.get("public_key_hex"):
                _copy_row(block, "Public Key (hex)", info["public_key_hex"], "#406060")

            # Private key
            if info.get("private_key_hex"):
                _copy_row(block, "Private Key (hex)", info["private_key_hex"], "#604040")
            if info.get("private_key_wif"):
                _copy_row(block, "Private Key (WIF)", info["private_key_wif"], "#604040")
            if info.get("private_key_wif_legacy"):
                _copy_row(block, "Priv Key WIF (Legacy)", info["private_key_wif_legacy"], "#604040")

            # OmniBus domain info
            if info.get("pq_algorithm"):
                alg_line = (f"  {info['pq_algorithm']}  ·  {info.get('security_bits','')} bit"
                            + (f"  ·  NIST L{info['nist_level']}" if info.get("nist_level") else "")
                            + f"  ·  {info.get('purpose','')}")
                tk.Label(block, text=alg_line, bg=BG2,
                         fg="#2a4060", font=("Consolas",8)).pack(anchor="w", padx=8, pady=(2,0))

            # Extra notes
            if info.get("note"):
                tk.Label(block, text=f"  ℹ  {info['note']}", bg=BG2,
                         fg="#404060", font=("Consolas",8)).pack(anchor="w", padx=8, pady=2)

        # ── PQ Domains section ───────────────────────────────────
        pq_domains = wallet.get("pq_domains", {})
        if pq_domains:
            pq_hdr = tk.Frame(inner, bg="#0a0c18", pady=6)
            pq_hdr.pack(fill=tk.X, padx=8, pady=(14,2))
            tk.Label(pq_hdr, text="  PQ DOMAINS  —  OmniBus Post-Quantum Keys",
                     bg="#0a0c18", fg="#00c8ff", font=FONTB).pack(side=tk.LEFT, padx=6)
            tk.Label(pq_hdr, text="quantum-resistant", bg="#0a0c18",
                     fg="#2a6070", font=("Consolas",8)).pack(side=tk.RIGHT, padx=8)

            for domain_key, dinfo in pq_domains.items():
                alg  = dinfo.get("pq_algorithm","")
                bits = dinfo.get("security_bits","")
                lvl  = dinfo.get("nist_level")
                lvl_str = f"  NIST L{lvl}" if lvl else ""
                purpose = dinfo.get("purpose","")
                backend = dinfo.get("pq_backend","")

                dh = tk.Frame(inner, bg="#0d1020", pady=4)
                dh.pack(fill=tk.X, padx=8, pady=(8,0))
                tk.Label(dh, text=f"  {domain_key}",
                         bg="#0d1020", fg="#00c8ff", font=FONTB).pack(side=tk.LEFT, padx=6)
                tk.Label(dh, text=f"{alg}  {bits}-bit{lvl_str}",
                         bg="#0d1020", fg="#2a8090", font=FONTS).pack(side=tk.LEFT, padx=8)
                tk.Label(dh, text=purpose, bg="#0d1020", fg="#2a4050",
                         font=("Consolas",8)).pack(side=tk.RIGHT, padx=8)
                if backend == "hkdf-deterministic":
                    tk.Label(dh, text="[sim]", bg="#0d1020", fg="#604020",
                             font=("Consolas",8)).pack(side=tk.RIGHT, padx=2)

                dblock = tk.Frame(inner, bg="#080c18")
                dblock.pack(fill=tk.X, padx=8, pady=(0,4))

                _copy_row(dblock, "OmniBus Address", dinfo.get("addr",""), "#00c8ff", show_qr=True)
                if dinfo.get("addr_btc"):
                    _copy_row(dblock, "BTC Anchor Addr", dinfo["addr_btc"], "#f7931a", show_qr=True)
                if dinfo.get("full_path"):
                    _copy_row(dblock, "Derivation Path", dinfo["full_path"], "#404060")
                if dinfo.get("pubkey"):
                    _copy_row(dblock, "PQ Public Key", dinfo["pubkey"], "#406060")
                if dinfo.get("pubkey_btc") and dinfo.get("pubkey_btc") != dinfo.get("pubkey"):
                    _copy_row(dblock, "BTC Public Key", dinfo["pubkey_btc"], "#406040")
                if dinfo.get("script_pubkey"):
                    _copy_row(dblock, "script_pubkey", dinfo["script_pubkey"], "#303050")

        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _export_full(self, entry: dict):
        """Export FULL backup: mnemonic included, passphrase NOT saved if set (user keeps it in head)."""
        label      = entry.get("label", "wallet")
        mnemonic   = entry.get("mnemonic", "")
        passphrase = entry.get("passphrase", "")
        has_pass   = bool(passphrase)

        msg = (
            "This will save your MNEMONIC to a file.\n\n"
            "Keep this file OFFLINE and SECURE.\n"
            "Anyone with this file can restore your wallet!\n"
        )
        if has_pass:
            msg += (
                "\nYour BIP39 PASSPHRASE will NOT be saved in the file.\n"
                "You must remember it separately — without it the wallet cannot be restored."
            )
        if not messagebox.askyesno("Export Full Backup", msg + "\n\nContinue?"):
            return

        export_data = {
            "omnibus_wallet_export": True,
            "source":     "omnibus_generated",
            "label":      label,
            "mnemonic":   mnemonic,
            # passphrase intentionally excluded — user keeps it in memory
            "passphrase_protected": has_pass,
            "addresses":  entry.get("addresses", {}),
            "created_at": entry.get("created_at", ""),
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "warning": "Keep this file OFFLINE and SECURE. Never share it.",
        }
        if has_pass:
            export_data["note"] = "PASSPHRASE NOT INCLUDED in this file. You must enter it manually on import."

        default_name = f"wallet_{label}_BACKUP_{datetime.date.today()}.json"
        path = filedialog.asksaveasfilename(
            title="Save Wallet Backup",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            extra = "\n\nRemember: your passphrase is NOT in this file." if has_pass else ""
            messagebox.showinfo("Backup Saved",
                f"Backup saved to:\n{path}\n\n"
                f"Contains: mnemonic + all addresses{extra}\n"
                "Store it offline and keep it secret!")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _do_export(self, wallet: dict):
        """Export public wallet info (addresses + pubkeys) to JSON file. No mnemonic."""
        label = wallet["label"]
        export_data = {
            "omnibus_wallet_export": True,
            "source": wallet.get("source", "omnibus_generated"),
            "label": label,
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "note": "MNEMONIC NOT INCLUDED in this file. It remains encrypted in wallets.dat (DPAPI).",
            "addresses": wallet.get("addresses", {}),
            "created_at": wallet.get("created_at", ""),
        }
        default_name = f"wallet_{label}_{datetime.date.today()}.json"
        path = filedialog.asksaveasfilename(
            title="Export Wallet Backup",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            messagebox.showinfo("Exported",
                f"Wallet '{label}' exported to:\n{path}\n\n"
                "NOTE: This file contains only public addresses.\n"
                "Your mnemonic is NOT in this file — it remains encrypted in the Vault.")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _do_import(self):
        """Import a wallet from a JSON backup file."""
        path = filedialog.askopenfilename(
            title="Import Wallet from Backup",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Import Error", f"Cannot read file:\n{e}"); return

        label      = data.get("label", "")
        mnemonic   = data.get("mnemonic", "")
        addresses  = data.get("addresses", {})
        created_at = data.get("created_at", data.get("exported_at", ""))
        has_pass_protected = data.get("passphrase_protected", False)

        if not label:
            messagebox.showerror("Import Error", "No 'label' field found in file."); return
        if not addresses and not mnemonic:
            messagebox.showerror("Import Error", "No addresses or mnemonic found in file."); return

        is_full = bool(mnemonic)

        # If passphrase-protected, ask user to enter it
        passphrase = ""
        if has_pass_protected and mnemonic:
            pass_win = tk.Toplevel(self.parent)
            pass_win.title("Enter BIP39 Passphrase")
            pass_win.geometry("400x160")
            pass_win.configure(bg=BG)
            pass_win.grab_set()
            tk.Label(pass_win,
                     text="This wallet was created with a BIP39 passphrase.\nEnter it to restore access:",
                     bg=BG, fg=FG, font=FONTS, justify="left").pack(padx=16, pady=(14,4), anchor="w")
            pp_var = tk.StringVar()
            tk.Entry(pass_win, textvariable=pp_var, show="•", bg="#0d0f18", fg=FG,
                     insertbackground=FG, relief=tk.FLAT, font=FONT).pack(
                fill=tk.X, padx=16, ipady=4)
            tk.Label(pass_win, text="Leave empty to import without passphrase.",
                     bg=BG, fg=FG2, font=("Consolas",8)).pack(padx=16, anchor="w")
            confirmed = [False]
            def _pp_ok():
                confirmed[0] = True
                pass_win.destroy()
            tk.Button(pass_win, text="OK", bg="#0e3518", fg=GRN, relief=tk.FLAT,
                      font=FONTB, command=_pp_ok).pack(pady=10, ipadx=20)
            pass_win.wait_window()
            passphrase = pp_var.get() if confirmed[0] else ""

        try:
            wallet_save(
                label      = label,
                mnemonic   = mnemonic,
                passphrase = passphrase,
                addresses  = addresses,
                chains     = list(addresses.keys()),
                source     = "imported",
            )
            kind = "full wallet (with mnemonic)" if is_full else "addresses-only"
            messagebox.showinfo("Imported",
                f"Wallet '{label}' imported ({kind}).\n\n"
                "Stored encrypted in wallets.dat (DPAPI).")
            self._refresh()
        except ValueError as e:
            messagebox.showerror("Import Error", str(e))
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed:\n{e}")

    def _fetch_balances(self, wallet: dict):
        """Fetch live balances for all chains in wallet, save to wallets.dat."""
        import threading

        label     = wallet["label"]
        wallet_id = wallet["id"]
        addresses = wallet.get("addresses", {})

        # Progress popup
        win = tk.Toplevel(self.parent)
        win.title(f"Fetching Balance — {label}")
        win.geometry("420x300")
        win.configure(bg=BG)
        win.resizable(False, False)

        tk.Label(win, text=f"FETCHING BALANCES  —  {label}",
                 bg=BG, fg=YEL, font=FONTB).pack(pady=(14,6))
        log = tk.Text(win, bg=BG2, fg=FG, font=FONTS, relief=tk.FLAT,
                      height=10, state="disabled")
        log.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        status_lbl = tk.Label(win, text="Working...", bg=BG, fg=FG2, font=FONTS)
        status_lbl.pack(pady=4)

        def _log(msg):
            log.configure(state="normal")
            log.insert(tk.END, msg + "\n")
            log.see(tk.END)
            log.configure(state="disabled")
            win.update_idletasks()

        def _run():
            total_bal = {}
            errors    = []
            for chain, info in addresses.items():
                addr = info.get("address") or info.get("addr", "")
                if not addr or chain.startswith("OMNI_") or chain == "OMNI":
                    continue
                _log(f"  {chain:12} {addr[:22]}...")
                try:
                    result = fetch_balance(chain, addr)
                    bal    = result["bal"]
                    total_bal[chain] = bal
                    fields = {k: result[k] for k in
                              ("bal","utxos","tx_count","last_tx","last_used")
                              if result.get(k) is not None}
                    wallet_update_address_meta(wallet_id, chain, fields)
                    err = result.get("fetch_error")
                    if err:
                        _log(f"    ERROR: {err}")
                        errors.append(chain)
                    else:
                        _log(f"    bal={bal}  txs={result['tx_count']}")
                except Exception as e:
                    _log(f"    EXCEPTION: {e}")
                    errors.append(chain)
                import time; time.sleep(0.3)

            # Summary
            _log("")
            _log("Done.")
            for c, b in total_bal.items():
                if b > 0:
                    _log(f"  {c}: {b}")
            if errors:
                _log(f"Errors: {errors}")

            win.after(0, lambda: status_lbl.config(
                text="Complete!" if not errors else f"Done with {len(errors)} error(s)",
                fg=GRN if not errors else YEL))
            win.after(0, self._refresh)
            win.after(0, lambda: tk.Button(win, text="Close", bg=BG3, fg=FG2,
                                           relief=tk.FLAT, font=FONTS,
                                           command=win.destroy).pack(pady=4))

        threading.Thread(target=_run, daemon=True).start()

    def _do_delete(self, wallet_id: str, label: str):
        if not messagebox.askyesno("Confirm Delete",
                f"Delete wallet '{label}'?\n\nThis CANNOT be undone.\n"
                "Make sure you have your mnemonic saved offline!"):
            return
        if wallet_delete(wallet_id):
            self._refresh()
        else:
            messagebox.showerror("Error", f"Wallet '{label}' not found.")

    def _refresh(self):
        if not WALLET_AVAILABLE:
            return
        try:
            self.wallets = wallet_list()
        except Exception as e:
            print(f"[WalletTab] refresh error: {e}")
            self.wallets = []
        self._render_wallets()


# ── PQ DOMAINS tab ───────────────────────────────────────────
class PQDomainsTab:
    """
    Displays OmniBus PQ domains for all stored wallets.
    Allows browsing domain addresses and copying keys.
    """
    PQ_ALGO_COLORS = {
        "ML-KEM":       "#00c8ff",
        "ML-DSA":       "#9945ff",
        "Falcon-512":   "#25c45a",
        "SLH-DSA":      "#f5d020",
        "Falcon-Light": "#f7931a",
    }

    def __init__(self, parent: tk.Frame, svc_lbl: tk.Label):
        self.parent  = parent
        self.svc_lbl = svc_lbl
        self.wallets = []
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        # Header info
        info = tk.Frame(self.parent, bg="#0a0c18", pady=7)
        info.pack(fill=tk.X)
        tk.Label(info, text="OMNIBUS PQ DOMAINS",
                 bg="#0a0c18", fg="#00c8ff", font=("Consolas",11,"bold")).pack(side=tk.LEFT, padx=14)
        tk.Label(info, text="Post-Quantum Cryptography  ·  OmniBus Blockchain",
                 bg="#0a0c18", fg="#1a4050", font=FONTS).pack(side=tk.LEFT, padx=4)

        # Domain legend
        legend = tk.Frame(self.parent, bg=BG3, pady=5)
        legend.pack(fill=tk.X, padx=10, pady=(4,0))
        if OMNIBUS_DOMAINS:
            for d in OMNIBUS_DOMAINS:
                col = self.PQ_ALGO_COLORS.get(d["pq_algorithm"], FG2)
                f = tk.Frame(legend, bg=BG3)
                f.pack(side=tk.LEFT, padx=6)
                tk.Label(f, text=d["domain"], bg=BG3, fg=col,
                         font=("Consolas",8,"bold")).pack()
                tk.Label(f, text=d["pq_variant"], bg=BG3, fg="#303050",
                         font=("Consolas",7)).pack()
        else:
            tk.Label(legend, text="pq_domain module not available",
                     bg=BG3, fg=RED, font=FONTS).pack(padx=8)

        tk.Frame(self.parent, bg="#1a1c2e", height=1).pack(fill=tk.X, padx=10, pady=(6,0))

        # Wallet selector
        sel_frame = tk.Frame(self.parent, bg=BG2, pady=4)
        sel_frame.pack(fill=tk.X, padx=10, pady=(4,0))
        tk.Label(sel_frame, text="WALLET:", bg=BG2, fg=FG2, font=FONTS).pack(side=tk.LEFT, padx=8)
        self.wallet_var = tk.StringVar()
        self.wallet_combo = ttk.Combobox(sel_frame, textvariable=self.wallet_var,
                                          state="readonly", font=FONTS, width=30)
        self.wallet_combo.pack(side=tk.LEFT, padx=4)
        self.wallet_combo.bind("<<ComboboxSelected>>", lambda e: self._render_domains())
        tk.Button(sel_frame, text="Refresh", bg=BG3, fg=FG2, relief=tk.FLAT,
                  font=FONTS, command=self._refresh).pack(side=tk.LEFT, padx=8)

        # Scrollable domain area
        body = tk.Frame(self.parent, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self._cw = self.canvas.create_window((0,0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(
            self._cw, width=e.width))

        # Footer
        bot = tk.Frame(self.parent, bg="#0a0c14", pady=5)
        bot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(bot,
                 text="BIP39 → HKDF-SHA512 → secp256k1 keypairs  ·  Coin types 777-781",
                 bg="#0a0c14", fg="#282838", font=("Consolas",8)).pack(side=tk.RIGHT, padx=10)

    def _refresh(self):
        if not WALLET_AVAILABLE:
            return
        try:
            self.wallets = wallet_list()
        except Exception:
            self.wallets = []
        labels = [w["label"] for w in self.wallets if w.get("pq_domains")]
        self.wallet_combo["values"] = labels
        if labels and (not self.wallet_var.get() or self.wallet_var.get() not in labels):
            self.wallet_var.set(labels[0])
        self._render_domains()

    def _render_domains(self):
        for w in self.inner.winfo_children():
            w.destroy()

        label = self.wallet_var.get()
        wallet = next((w for w in self.wallets if w["label"] == label), None)

        if not wallet:
            tk.Label(self.inner,
                     text="No wallet selected or no wallets with PQ domains.\n\n"
                          "Generate a new wallet with 'Include PQ Domains' checked.",
                     bg=BG, fg=FG2, font=FONTS, justify="left").pack(pady=30, padx=20)
            return

        pq = wallet.get("pq_domains", {})
        if not pq:
            tk.Label(self.inner,
                     text=f"Wallet '{label}' has no PQ domains.\n\n"
                          "Re-generate or use 'Include PQ Domains' when creating.",
                     bg=BG, fg=FG2, font=FONTS, justify="left").pack(pady=30, padx=20)
            return

        tk.Label(self.inner, text=f"  {label}  —  OmniBus PQ Domains",
                 bg=BG, fg=YEL, font=FONTB).pack(anchor="w", padx=8, pady=(8,4))

        for domain_key, dinfo in pq.items():
            alg    = dinfo.get("pq_algorithm","")
            col    = self.PQ_ALGO_COLORS.get(alg, FG2)
            bits   = dinfo.get("security_bits","")
            lvl    = dinfo.get("nist_level")
            lvl_str = f"  NIST L{lvl}" if lvl else ""
            purpose = dinfo.get("purpose","")
            backend = dinfo.get("pq_backend","")

            # Domain header
            dh = tk.Frame(self.inner, bg="#0a0e18", pady=6)
            dh.pack(fill=tk.X, padx=8, pady=(10,0))
            prefix = dinfo.get("prefix","")
            tk.Label(dh, text=f"  {domain_key}",
                     bg="#0a0e18", fg=col, font=FONTB).pack(side=tk.LEFT, padx=6)
            tk.Label(dh, text=f"[{prefix}]", bg="#0a0e18", fg="#2a3050",
                     font=("Consolas",9)).pack(side=tk.LEFT)
            tk.Label(dh, text=f"{alg}  {bits}-bit{lvl_str}",
                     bg="#0a0e18", fg=col, font=("Consolas",9,"bold")).pack(side=tk.LEFT, padx=10)
            tk.Label(dh, text=purpose, bg="#0a0e18", fg="#2a4050",
                     font=("Consolas",8)).pack(side=tk.RIGHT, padx=8)
            if backend == "hkdf-deterministic":
                tk.Label(dh, text="⚠ sim", bg="#0a0e18", fg="#604020",
                         font=("Consolas",8)).pack(side=tk.RIGHT, padx=4)

            # Fields block
            block = tk.Frame(self.inner, bg="#060810")
            block.pack(fill=tk.X, padx=8, pady=(0,2))

            def _row(parent, lbl, val, fg=FG2):
                f = tk.Frame(parent, bg="#060810")
                f.pack(fill=tk.X, padx=0, pady=1)
                tk.Label(f, text=lbl, bg="#060810", fg=fg,
                         font=("Consolas",8), width=22, anchor="w").pack(side=tk.LEFT, padx=(8,2))
                var = tk.StringVar(value=val)
                tk.Entry(f, textvariable=var, bg="#060810", fg=FG, relief=tk.FLAT,
                         font=("Consolas",9), readonlybackground="#060810",
                         state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
                tk.Button(f, text="Copy", font=("Consolas",8),
                          bg="#0e1e2e", fg="#4488cc", relief=tk.FLAT, padx=4,
                          command=lambda v=val: (
                              self.parent.winfo_toplevel().clipboard_clear(),
                              self.parent.winfo_toplevel().clipboard_append(v))
                          ).pack(side=tk.RIGHT, padx=4)

            _row(block, "OmniBus Address",  dinfo.get("addr",""),         col)
            _row(block, "BTC Anchor Addr",  dinfo.get("addr_btc",""),     "#f7931a")
            _row(block, "Derivation Path",  dinfo.get("full_path",""),    "#404060")
            _row(block, "PQ Public Key",    dinfo.get("pubkey",""),       "#406060")
            if dinfo.get("script_pubkey"):
                _row(block, "script_pubkey", dinfo["script_pubkey"],      "#303050")
            _row(block, "Coin Type",
                 str(dinfo.get("chain", "")),                              "#2a4050")

        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


# ── TX HISTORY tab ───────────────────────────────────────────
class TxHistoryTab:
    """
    Fetches and displays transaction history for any chain + address.
    Uses the same public APIs as balance_fetcher.
    """
    def __init__(self, parent: tk.Frame, svc_lbl: tk.Label):
        self.parent  = parent
        self.svc_lbl = svc_lbl
        self.wallets = []
        self._build_ui()
        self._refresh_wallets()

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.parent, bg="#0a0c14", pady=7)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="TX HISTORY", bg="#0a0c14",
                 fg=YEL, font=("Consolas", 11, "bold")).pack(side=tk.LEFT, padx=14)
        tk.Button(hdr, text="Refresh", bg=BG3, fg=FG2, relief=tk.FLAT,
                  font=FONTS, command=self._refresh_wallets).pack(side=tk.RIGHT, padx=10)

        # Selector row
        sel = tk.Frame(self.parent, bg=BG2, pady=5)
        sel.pack(fill=tk.X, padx=10, pady=(4, 0))

        tk.Label(sel, text="WALLET:", bg=BG2, fg=FG2, font=FONTS).pack(side=tk.LEFT, padx=8)
        self.wallet_var = tk.StringVar()
        self.wallet_cb = ttk.Combobox(sel, textvariable=self.wallet_var,
                                       state="readonly", font=FONTS, width=22)
        self.wallet_cb.pack(side=tk.LEFT, padx=4)
        self.wallet_cb.bind("<<ComboboxSelected>>", lambda e: self._on_wallet_select())

        tk.Label(sel, text="CHAIN:", bg=BG2, fg=FG2, font=FONTS).pack(side=tk.LEFT, padx=(14, 4))
        self.chain_var = tk.StringVar()
        self.chain_cb = ttk.Combobox(sel, textvariable=self.chain_var,
                                      state="readonly", font=FONTS, width=12)
        self.chain_cb.pack(side=tk.LEFT, padx=4)

        tk.Button(sel, text="  FETCH  ", bg="#0e2e14", fg=GRN, relief=tk.FLAT,
                  font=FONTB, command=self._do_fetch).pack(side=tk.LEFT, padx=10)

        self.fetch_status = tk.Label(sel, text="", bg=BG2, fg=FG2, font=FONTS)
        self.fetch_status.pack(side=tk.LEFT, padx=6)

        # Results area
        body = tk.Frame(self.parent, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self._cw = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(
            self._cw, width=e.width))

        # Footer
        bot = tk.Frame(self.parent, bg="#0a0c14", pady=5)
        bot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(bot, text="Public APIs: Blockstream · SoChain · Etherscan · Solana · XRPL · Horizon",
                 bg="#0a0c14", fg="#282838", font=("Consolas", 8)).pack(side=tk.RIGHT, padx=10)

    def _refresh_wallets(self):
        if not WALLET_AVAILABLE:
            return
        try:
            self.wallets = wallet_list()
        except Exception:
            self.wallets = []
        labels = [w["label"] for w in self.wallets]
        self.wallet_cb["values"] = labels
        if labels:
            if not self.wallet_var.get() or self.wallet_var.get() not in labels:
                self.wallet_var.set(labels[0])
            self._on_wallet_select()

    def _on_wallet_select(self):
        label = self.wallet_var.get()
        wallet = next((w for w in self.wallets if w["label"] == label), None)
        if not wallet:
            return
        chains = list(wallet.get("addresses", {}).keys())
        self.chain_cb["values"] = chains
        if chains:
            self.chain_var.set(chains[0])

    def _do_fetch(self):
        import threading
        label  = self.wallet_var.get()
        chain  = self.chain_var.get().upper()
        wallet = next((w for w in self.wallets if w["label"] == label), None)
        if not wallet or not chain:
            return

        info    = wallet.get("addresses", {}).get(chain, {})
        address = info.get("address") or info.get("addr", "")
        if not address:
            self.fetch_status.config(text="No address for this chain.", fg=RED)
            return

        self.fetch_status.config(text="Fetching...", fg=FG2)
        for w in self.inner.winfo_children():
            w.destroy()

        def _run():
            txs = _fetch_tx_history(chain, address)
            self.parent.after(0, lambda: self._render_txs(chain, address, txs))

        threading.Thread(target=_run, daemon=True).start()

    def _render_txs(self, chain: str, address: str, txs: list):
        for w in self.inner.winfo_children():
            w.destroy()

        chain_col = CHAIN_COLORS.get(chain, FG2) if WALLET_AVAILABLE else FG2

        # Address row
        ah = tk.Frame(self.inner, bg=BG3, pady=5)
        ah.pack(fill=tk.X, padx=8, pady=(6, 2))
        tk.Label(ah, text=chain, bg=BG3, fg=chain_col, font=FONTB, width=8).pack(side=tk.LEFT, padx=8)
        tk.Label(ah, text=address, bg=BG3, fg=FG, font=FONTS).pack(side=tk.LEFT)
        tk.Button(ah, text="QR", font=FONTS, bg="#0e1a0e", fg=GRN, relief=tk.FLAT,
                  command=lambda: show_qr_popup(self.parent, address, f"Receive {chain}")
                  ).pack(side=tk.RIGHT, padx=6)

        count_text = f"{len(txs)} transaction(s)" if txs else "No transactions found"
        self.fetch_status.config(text=count_text, fg=GRN if txs else FG2)

        if not txs:
            tk.Label(self.inner, text="No transactions found for this address.",
                     bg=BG, fg=FG2, font=FONTS).pack(pady=20)
            self.canvas.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            return

        for tx in txs:
            row = tk.Frame(self.inner, bg=BG2, pady=4)
            row.pack(fill=tk.X, padx=8, pady=2)

            txid = tx.get("txid", "")
            amt  = tx.get("amount", 0.0)
            conf = tx.get("confirmations", 0)
            ts   = tx.get("time", "")
            direction = tx.get("direction", "")  # "in" / "out" / ""

            dir_col  = GRN if direction == "in" else (RED if direction == "out" else FG2)
            dir_text = ("+ " if direction == "in" else "- " if direction == "out" else "  ")
            amt_str  = f"{dir_text}{abs(amt):.8f} {chain}" if amt else ""

            # Left: txid (truncated)
            short_txid = txid[:20] + "..." + txid[-8:] if len(txid) > 32 else txid
            tk.Label(row, text=short_txid, bg=BG2, fg="#4060a0",
                     font=("Consolas", 8), anchor="w").pack(side=tk.LEFT, padx=8)

            # Amount
            if amt_str:
                tk.Label(row, text=amt_str, bg=BG2, fg=dir_col,
                         font=("Consolas", 9, "bold")).pack(side=tk.LEFT, padx=10)

            # Confirmations
            conf_col = GRN if conf >= 6 else YEL if conf > 0 else RED
            conf_text = f"{conf} conf" if isinstance(conf, int) else str(conf)
            tk.Label(row, text=conf_text, bg=BG2, fg=conf_col, font=FONTS).pack(side=tk.RIGHT, padx=8)

            # Timestamp
            if ts:
                tk.Label(row, text=str(ts)[:16], bg=BG2, fg=FG2, font=("Consolas", 8)).pack(
                    side=tk.RIGHT, padx=8)

            # Copy txid button
            tk.Button(row, text="Copy TXID", font=("Consolas", 8), bg="#0e1e2e", fg="#4488cc",
                      relief=tk.FLAT, padx=4,
                      command=lambda t=txid: (self.parent.winfo_toplevel().clipboard_clear(),
                                              self.parent.winfo_toplevel().clipboard_append(t))
                      ).pack(side=tk.RIGHT, padx=4)

            tk.Frame(self.inner, bg="#1a1c2e", height=1).pack(fill=tk.X, padx=8)

        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


def _fetch_tx_history(chain: str, address: str) -> list:
    """
    Fetch transaction history for chain+address.
    Returns list of dicts: {txid, amount, confirmations, time, direction}
    """
    import urllib.request
    import urllib.error

    def _get(url):
        try:
            import requests as _req
            r = _req.get(url, timeout=10, headers={"User-Agent": "OmnibusWallet/1.0"})
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def _post(url, payload):
        try:
            import requests as _req
            r = _req.post(url, json=payload, timeout=10,
                          headers={"User-Agent": "OmnibusWallet/1.0"})
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    txs = []

    if chain == "BTC":
        data = _get(f"https://blockstream.info/api/address/{address}/txs")
        if not data:
            return []
        for t in data[:50]:
            txid = t.get("txid", "")
            status = t.get("status", {})
            confirmed = status.get("confirmed", False)
            conf = 1 if confirmed else 0
            ts = status.get("block_time", "")
            if ts:
                ts = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            # Calculate net amount for this address
            vout_sum = sum(o["value"] for o in t.get("vout", [])
                          if any(address in str(s) for s in [o.get("scriptpubkey_address","")]))
            vin_sum  = sum(i.get("prevout", {}).get("value", 0) for i in t.get("vin", [])
                          if address in str(i.get("prevout", {}).get("scriptpubkey_address","")))
            net = (vout_sum - vin_sum) / 1e8
            txs.append({"txid": txid, "amount": net,
                        "confirmations": conf, "time": ts,
                        "direction": "in" if net > 0 else "out" if net < 0 else ""})

    elif chain in ("LTC", "DOGE", "BCH"):
        sym = chain
        data = _get(f"https://sochain.com/api/v2/get_tx_received/{sym}/{address}")
        if data and data.get("status") == "success":
            for t in (data.get("data", {}).get("txs", []))[:50]:
                txs.append({"txid": t.get("txid",""), "amount": float(t.get("value",0)),
                             "confirmations": int(t.get("confirmations",0)),
                             "time": t.get("time",""), "direction": "in"})

    elif chain in ("ETH", "BNB", "OP"):
        endpoints = {"ETH": "https://api.etherscan.io/api",
                     "BNB": "https://api.bscscan.com/api",
                     "OP":  "https://api-optimistic.etherscan.io/api"}
        base = endpoints.get(chain, endpoints["ETH"])
        params = (f"?module=account&action=txlist&address={address}"
                  f"&startblock=0&endblock=99999999&sort=desc&page=1&offset=50")
        data = _get(base + params)
        if data and isinstance(data.get("result"), list):
            for t in data["result"][:50]:
                amt = int(t.get("value","0")) / 1e18
                direction = "in" if t.get("to","").lower() == address.lower() else "out"
                ts_raw = t.get("timeStamp","")
                ts = (datetime.datetime.fromtimestamp(int(ts_raw)).strftime("%Y-%m-%d %H:%M")
                      if ts_raw else "")
                txs.append({"txid": t.get("hash",""), "amount": amt,
                             "confirmations": int(t.get("confirmations",0)),
                             "time": ts, "direction": direction})

    elif chain == "SOL":
        data = _post("https://api.mainnet-beta.solana.com",
                     {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                      "params": [address, {"limit": 50}]})
        if data and "result" in data:
            for s in data["result"]:
                txs.append({"txid": s.get("signature",""),
                             "amount": 0.0,
                             "confirmations": 1 if not s.get("err") else 0,
                             "time": "", "direction": ""})

    elif chain == "XRP":
        data = _get(f"https://data.ripple.com/v2/accounts/{address}/transactions?limit=50")
        if data:
            for t in (data.get("transactions") or []):
                tx = t.get("tx", {})
                txs.append({"txid": tx.get("hash",""),
                             "amount": float(tx.get("Amount", 0)) / 1e6 if isinstance(tx.get("Amount"), (int,str)) else 0,
                             "confirmations": 1,
                             "time": t.get("date",""), "direction": ""})

    elif chain == "XLM":
        data = _get(f"https://horizon.stellar.org/accounts/{address}/payments?limit=50&order=desc")
        if data:
            for r in data.get("_embedded", {}).get("records", []):
                txs.append({"txid": r.get("transaction_hash",""),
                             "amount": float(r.get("amount",0)),
                             "confirmations": 1,
                             "time": r.get("created_at","")[:16],
                             "direction": "in" if r.get("to","") == address else "out"})

    elif chain == "OMNI":
        # Try local RPC node
        data = _post("http://127.0.0.1:8332",
                     {"jsonrpc": "2.0", "id": 1,
                      "method": "getBalance", "params": [address]})
        if data and isinstance(data.get("result"), dict):
            for t in (data["result"].get("transactions") or []):
                txs.append({"txid": t.get("txid", t.get("id","")),
                             "amount": float(t.get("amount",0)) / 1e8,
                             "confirmations": t.get("confirmations", 1),
                             "time": t.get("time",""), "direction": ""})

    elif chain in ("OMNI_LOVE","OMNI_FOOD","OMNI_RENT","OMNI_VACATION"):
        pass  # non-transferable, no TX history

    return txs


# ── SEND OMNI popup ──────────────────────────────────────────
def show_send_omni_popup(parent, wallet: dict):
    """Send OMNI transaction via local RPC node (port 8332)."""
    import threading

    label   = wallet["label"]
    omni    = wallet.get("addresses", {}).get("OMNI", {})
    from_addr = omni.get("address_native") or omni.get("address") or ""
    priv_key  = omni.get("private_key_hex_native") or omni.get("private_key_hex") or ""

    if not from_addr:
        messagebox.showerror("Send OMNI", "No OMNI address found in this wallet.")
        return

    win = tk.Toplevel(parent)
    win.title(f"Send OMNI — {label}")
    win.geometry("520x400")
    win.configure(bg=BG)
    win.resizable(False, False)
    win.grab_set()

    # Header
    hdr = tk.Frame(win, bg="#0a0c14", pady=7)
    hdr.pack(fill=tk.X)
    tk.Label(hdr, text=f"SEND OMNI  —  {label}", bg="#0a0c14",
             fg=YEL, font=FONTB).pack(side=tk.LEFT, padx=14)
    tk.Button(hdr, text="Close", bg=BG3, fg=FG2, relief=tk.FLAT,
              font=FONTS, command=win.destroy).pack(side=tk.RIGHT, padx=10)

    body = tk.Frame(win, bg=BG, padx=20)
    body.pack(fill=tk.BOTH, expand=True, pady=8)

    # From address (readonly)
    tk.Label(body, text="FROM ADDRESS", bg=BG, fg=FG2, font=FONTS, anchor="w").pack(fill=tk.X, pady=(8,0))
    from_frame = tk.Frame(body, bg=BG2)
    from_frame.pack(fill=tk.X, pady=(2,10))
    from_var = tk.StringVar(value=from_addr)
    tk.Entry(from_frame, textvariable=from_var, bg=BG2, fg=FG,
             relief=tk.FLAT, font=FONTS, readonlybackground=BG2,
             state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(6,0))
    tk.Button(from_frame, text="QR", font=FONTS, bg="#0e1a0e", fg=GRN,
              relief=tk.FLAT, padx=5,
              command=lambda: show_qr_popup(win, from_addr, "From Address")
              ).pack(side=tk.RIGHT, padx=4)

    # Balance display
    bal = omni.get("bal", 0.0)
    bal_lbl = tk.Label(body, text=f"Balance: {bal:.8f} OMNI",
                       bg=BG, fg=GRN if bal > 0 else FG2, font=FONTS, anchor="w")
    bal_lbl.pack(fill=tk.X, pady=(0, 8))

    # To address
    tk.Label(body, text="TO ADDRESS", bg=BG, fg=FG2, font=FONTS, anchor="w").pack(fill=tk.X)
    to_var = tk.StringVar()
    tk.Entry(body, textvariable=to_var, bg=BG2, fg=FG,
             insertbackground=FG, relief=tk.FLAT, font=FONT).pack(
        fill=tk.X, ipady=5, pady=(2, 10))

    # Amount
    tk.Label(body, text="AMOUNT  (OMNI)", bg=BG, fg=FG2, font=FONTS, anchor="w").pack(fill=tk.X)
    amt_frame = tk.Frame(body, bg=BG)
    amt_frame.pack(fill=tk.X, pady=(2, 6))
    amt_var = tk.StringVar()
    tk.Entry(amt_frame, textvariable=amt_var, bg=BG2, fg=FG,
             insertbackground=FG, relief=tk.FLAT, font=FONT).pack(
        side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
    if bal > 0:
        tk.Button(amt_frame, text="MAX", font=FONTS, bg=BG3, fg=FG2, relief=tk.FLAT,
                  command=lambda: amt_var.set(f"{bal:.8f}")
                  ).pack(side=tk.RIGHT, padx=(6, 0))

    # Status
    status_lbl = tk.Label(body, text="", bg=BG, fg=FG2, font=FONTS, wraplength=460)
    status_lbl.pack(fill=tk.X, pady=4)

    # Send button
    def _do_send():
        to_addr = to_var.get().strip()
        amt_str = amt_var.get().strip()
        if not to_addr:
            status_lbl.config(text="Enter destination address.", fg=RED); return
        if not amt_str:
            status_lbl.config(text="Enter amount.", fg=RED); return
        try:
            amount = float(amt_str)
        except ValueError:
            status_lbl.config(text="Invalid amount.", fg=RED); return
        if amount <= 0:
            status_lbl.config(text="Amount must be > 0.", fg=RED); return
        if amount > bal:
            status_lbl.config(text=f"Insufficient balance ({bal:.8f} OMNI).", fg=RED); return

        if not messagebox.askyesno("Confirm Send",
                f"Send {amount:.8f} OMNI\n\nFrom: {from_addr[:40]}\nTo:   {to_addr[:40]}\n\nConfirm?",
                parent=win):
            return

        status_lbl.config(text="Broadcasting...", fg=FG2)
        win.update_idletasks()

        def _broadcast():
            import requests as _req
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "sendTransaction",
                "params": {
                    "from":       from_addr,
                    "to":         to_addr,
                    "amount":     int(amount * 1e8),  # satoshis
                    "privateKey": priv_key,
                },
            }
            try:
                r = _req.post("http://127.0.0.1:8332", json=payload, timeout=10)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                win.after(0, lambda: status_lbl.config(
                    text=f"Node unreachable: {e}", fg=RED))
                return

            if data.get("error"):
                err_msg = str(data["error"])
                win.after(0, lambda: status_lbl.config(
                    text=f"Node error: {err_msg}", fg=RED))
                return

            result = data.get("result", {})
            txid = (result.get("txid") or result.get("id") or
                    (result if isinstance(result, str) else ""))
            msg = f"Sent! TXID: {txid}" if txid else "Sent! (no TXID returned)"
            win.after(0, lambda: status_lbl.config(text=msg, fg=GRN))

        threading.Thread(target=_broadcast, daemon=True).start()

    tk.Button(body, text="  SEND OMNI  ", font=FONTB,
              bg="#0e3518", fg=GRN, relief=tk.FLAT,
              activebackground="#1a5020",
              command=_do_send).pack(fill=tk.X, ipady=7, pady=(4, 0))

    tk.Label(body,
             text="Broadcasts directly to OmniBus node at 127.0.0.1:8332",
             bg=BG, fg="#282838", font=("Consolas", 8)).pack(pady=(4, 0))


# ── Main App (Notebook) ───────────────────────────────────────
class VaultManagerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("OmniBus Vault Manager  v3.0")
        root.geometry("600x680")
        root.configure(bg=BG)
        root.resizable(True, True)
        root.minsize(520, 520)

        self._build_ui()

    def _build_ui(self):
        # Shared header
        hdr = tk.Frame(self.root, bg="#0a0c14", pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="OMNIBUS VAULT", bg="#0a0c14",
                 fg=YEL, font=("Consolas", 13, "bold")).pack(side=tk.LEFT, padx=14)
        self.svc_lbl = tk.Label(hdr, text="checking...", bg="#0a0c14",
                                fg=FG2, font=FONTS)
        self.svc_lbl.pack(side=tk.RIGHT, padx=14)

        # Style the notebook tabs
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Vault.TNotebook",
                         background=BG, borderwidth=0, tabmargins=[2,4,2,0])
        style.configure("Vault.TNotebook.Tab",
                         background=BG3, foreground=FG2,
                         font=("Consolas", 10, "bold"),
                         padding=[18, 6], borderwidth=0)
        style.map("Vault.TNotebook.Tab",
                  background=[("selected", "#1a1c2e"), ("active", "#16182a")],
                  foreground=[("selected", YEL), ("active", FG)])

        # Notebook
        nb = ttk.Notebook(self.root, style="Vault.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Tab frames
        keys_frame   = tk.Frame(nb, bg=BG)
        wallet_frame = tk.Frame(nb, bg=BG)
        pq_frame     = tk.Frame(nb, bg=BG)
        tx_frame     = tk.Frame(nb, bg=BG)
        nb.add(keys_frame,   text="  API KEYS  ")
        nb.add(wallet_frame, text="  WALLET  ")
        nb.add(pq_frame,     text="  PQ DOMAINS  ")
        nb.add(tx_frame,     text="  TX HISTORY  ")

        # Instantiate sub-UIs
        self.keys_tab   = ApiKeysTab(keys_frame,    self.svc_lbl)
        self.wallet_tab = WalletTab(wallet_frame,   self.svc_lbl)
        self.pq_tab     = PQDomainsTab(pq_frame,    self.svc_lbl)
        self.tx_tab     = TxHistoryTab(tx_frame,    self.svc_lbl)

        # Refresh tabs when switching
        nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, event):
        nb = event.widget
        idx = nb.index(nb.select())
        if idx == 1:  # WALLET tab
            self.wallet_tab._refresh()
        elif idx == 2:  # PQ DOMAINS tab
            self.pq_tab._refresh()
        elif idx == 3:  # TX HISTORY tab
            self.tx_tab._refresh_wallets()


# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    # Single instance via mutex
    k32 = ctypes.windll.kernel32
    hMutex = k32.CreateMutexA(None, True, b"Global\\OmnibusVaultManager")
    if k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        messagebox.showwarning("Already running", "VaultManager is already open.")
        sys.exit(1)

    root = tk.Tk()
    app  = VaultManagerApp(root)
    root.mainloop()

    k32.ReleaseMutex(hMutex)
    k32.CloseHandle(hMutex)
