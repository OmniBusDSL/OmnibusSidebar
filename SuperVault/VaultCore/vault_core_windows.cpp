// ============================================================
//  vault_core_windows.cpp  —  v4 multi-key backend (DPAPI)
//
//  Format v4: per-key status (FREE/PAID/NOTPAID), no active-slot
//  Breaking change: v1/v2/v3 files are detected and wiped
//
//  Libraries: crypt32.lib (DPAPI), windows.h, STL
// ============================================================
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <dpapi.h>
#include <stdio.h>
#include <fstream>
#include <vector>
#include <mutex>
#include <cstring>
#include <string>

#include "vault_core.h"

// ─── Internal slot ───────────────────────────────────────────
struct Slot {
    bool    in_use = false;
    uint8_t status = VAULT_KEY_STATUS_FREE;
    char    name[VAULT_NAME_MAX]    = {};
    char    key[VAULT_KEY_MAX]      = {};
    char    secret[VAULT_SECRET_MAX] = {};
};

struct ExchangeStore {
    Slot     slots[VAULT_MAX_KEYS];
    uint32_t count = 0;
};

static std::mutex    s_mtx;
static bool          s_locked    = true;
static ExchangeStore s_store[VAULT_EXCHANGE_COUNT];
static char          s_data_path[512] = {};

// ─── Helpers ─────────────────────────────────────────────────
static std::string VaultFilePath()
{
    return std::string(s_data_path) + "\\vault.dat";
}

static bool EnsureDir()
{
    DWORD a = GetFileAttributesA(s_data_path);
    if (a == INVALID_FILE_ATTRIBUTES)
        return CreateDirectoryA(s_data_path, NULL) != 0;
    return (a & FILE_ATTRIBUTE_DIRECTORY) != 0;
}

// ─── DPAPI ───────────────────────────────────────────────────
static bool DpapiEncrypt(const std::vector<uint8_t>& plain,
                          std::vector<uint8_t>& cipher)
{
    DATA_BLOB in  = { (DWORD)plain.size(), (BYTE*)plain.data() };
    DATA_BLOB out = {};
    if (!CryptProtectData(&in, L"OmnibusVaultV4", NULL, NULL, NULL,
                          CRYPTPROTECT_UI_FORBIDDEN, &out))
        return false;
    cipher.assign(out.pbData, out.pbData + out.cbData);
    LocalFree(out.pbData);
    return true;
}

static bool DpapiDecrypt(const std::vector<uint8_t>& cipher,
                          std::vector<uint8_t>& plain)
{
    DATA_BLOB in  = { (DWORD)cipher.size(), (BYTE*)cipher.data() };
    DATA_BLOB out = {};
    if (!CryptUnprotectData(&in, NULL, NULL, NULL, NULL, 0, &out))
        return false;
    plain.assign(out.pbData, out.pbData + out.cbData);
    SecureZeroMemory(out.pbData, out.cbData);
    LocalFree(out.pbData);
    return true;
}

// ─── Serialization helpers ───────────────────────────────────
static void WU32(std::vector<uint8_t>& b, uint32_t v) {
    b.push_back(v & 0xFF); b.push_back((v>>8)&0xFF);
    b.push_back((v>>16)&0xFF); b.push_back((v>>24)&0xFF);
}
static void WStr(std::vector<uint8_t>& b, const char* s) {
    uint32_t len = s ? (uint32_t)strlen(s) : 0;
    WU32(b, len);
    if (len) b.insert(b.end(), (uint8_t*)s, (uint8_t*)s + len);
}

static bool RU32(const std::vector<uint8_t>& b, size_t& p, uint32_t& v) {
    if (p + 4 > b.size()) return false;
    v = b[p]|(b[p+1]<<8)|(b[p+2]<<16)|((uint32_t)b[p+3]<<24); p+=4; return true;
}
static bool RStr(const std::vector<uint8_t>& b, size_t& p, char* out, size_t max) {
    uint32_t len; if (!RU32(b,p,len)) return false;
    if (p + len > b.size()) return false;
    size_t n = len < max-1 ? len : max-1;
    memcpy(out, b.data()+p, n); out[n]=0; p+=len; return true;
}

// ─── Serialize / Deserialize ─────────────────────────────────
#define MAGIC_0 'O'
#define MAGIC_1 'M'
#define MAGIC_2 'N'
#define MAGIC_3 'V'
#define FORMAT_VERSION 4

static void Serialize(std::vector<uint8_t>& buf)
{
    buf.clear();
    buf.push_back(MAGIC_0); buf.push_back(MAGIC_1);
    buf.push_back(MAGIC_2); buf.push_back(MAGIC_3);
    WU32(buf, FORMAT_VERSION);
    WU32(buf, VAULT_EXCHANGE_COUNT);

    for (int e = 0; e < VAULT_EXCHANGE_COUNT; e++) {
        const ExchangeStore& es = s_store[e];
        WU32(buf, es.count);
        for (uint32_t i = 0; i < es.count; i++) {
            const Slot& sl = es.slots[i];
            buf.push_back(sl.in_use ? 1 : 0);
            buf.push_back(sl.status);
            WStr(buf, sl.name);
            WStr(buf, sl.key);
            WStr(buf, sl.secret);
        }
    }
}

static bool Deserialize(const std::vector<uint8_t>& buf)
{
    if (buf.size() < 12) return false;
    if (buf[0]!=MAGIC_0||buf[1]!=MAGIC_1||buf[2]!=MAGIC_2||buf[3]!=MAGIC_3) return false;
    size_t p = 4;
    uint32_t ver, count;
    if (!RU32(buf,p,ver))   return false;
    if (ver != FORMAT_VERSION) return false;  // old format — wipe
    if (!RU32(buf,p,count)) return false;

    for (uint32_t e = 0; e < count && e < VAULT_EXCHANGE_COUNT; e++) {
        ExchangeStore& es = s_store[e];
        uint32_t kcount;
        if (!RU32(buf,p,kcount)) return false;
        es.count = kcount < VAULT_MAX_KEYS ? kcount : VAULT_MAX_KEYS;
        for (uint32_t i = 0; i < es.count; i++) {
            if (p + 2 > buf.size()) return false;
            Slot& sl = es.slots[i];
            sl.in_use = (buf[p++] != 0);
            sl.status = buf[p++];
            if (!RStr(buf,p,sl.name,   VAULT_NAME_MAX))   return false;
            if (!RStr(buf,p,sl.key,    VAULT_KEY_MAX))     return false;
            if (!RStr(buf,p,sl.secret, VAULT_SECRET_MAX))  return false;
        }
    }
    return true;
}

// ─── Public API ──────────────────────────────────────────────
VaultError vault_core_init(const char* data_path)
{
    std::lock_guard<std::mutex> lk(s_mtx);
    strncpy_s(s_data_path, data_path, sizeof(s_data_path)-1);
    memset(s_store, 0, sizeof(s_store));

    EnsureDir();

    std::ifstream f(VaultFilePath(), std::ios::binary);
    if (!f) { s_locked = false; return VAULT_OK; }

    std::vector<uint8_t> cipher((std::istreambuf_iterator<char>(f)),
                                  std::istreambuf_iterator<char>());
    f.close();

    std::vector<uint8_t> plain;
    if (!DpapiDecrypt(cipher, plain)) return VAULT_ERR_DECRYPT;

    bool ok = Deserialize(plain);
    SecureZeroMemory(plain.data(), plain.size());

    if (!ok) {
        memset(s_store, 0, sizeof(s_store));
    }

    s_locked = false;
    return VAULT_OK;
}

VaultError vault_core_save(void)
{
    printf("[SAVE] acquiring lock...\n"); fflush(stdout);
    std::lock_guard<std::mutex> lk(s_mtx);
    printf("[SAVE] lock acquired, locked=%d\n", (int)s_locked); fflush(stdout);
    if (s_locked) return VAULT_ERR_LOCKED;
    if (!EnsureDir()) { printf("[SAVE] EnsureDir failed\n"); fflush(stdout); return VAULT_ERR_IO; }

    std::vector<uint8_t> plain;
    Serialize(plain);
    printf("[SAVE] serialized %d bytes\n", (int)plain.size()); fflush(stdout);

    std::vector<uint8_t> cipher;
    bool ok = DpapiEncrypt(plain, cipher);
    SecureZeroMemory(plain.data(), plain.size());
    if (!ok) { printf("[SAVE] DpapiEncrypt FAILED\n"); fflush(stdout); return VAULT_ERR_DECRYPT; }
    printf("[SAVE] encrypted %d bytes -> %s\n", (int)cipher.size(), VaultFilePath().c_str());
    fflush(stdout);

    std::ofstream f(VaultFilePath(), std::ios::binary | std::ios::trunc);
    if (!f) { printf("[SAVE] open FAILED\n"); fflush(stdout); return VAULT_ERR_IO; }
    f.write((char*)cipher.data(), cipher.size());
    VaultError result = f.good() ? VAULT_OK : VAULT_ERR_IO;
    printf("[SAVE] result=%d\n", (int)result); fflush(stdout);
    return result;
}

void vault_core_lock(void)
{
    std::lock_guard<std::mutex> lk(s_mtx);
    for (auto& es : s_store)
        for (auto& sl : es.slots) {
            SecureZeroMemory(sl.key,    VAULT_KEY_MAX);
            SecureZeroMemory(sl.secret, VAULT_SECRET_MAX);
            sl.in_use = false;
        }
    s_locked = true;
}

VaultError vault_core_add(VaultExchange ex, const char* name,
                           const char* api_key, const char* api_secret,
                           uint32_t* out_slot)
{
    if (ex < 0 || ex >= VAULT_EXCHANGE_COUNT) return VAULT_ERR_INVALID;
    if (!name || !api_key || !api_secret)      return VAULT_ERR_INVALID;
    {
        std::lock_guard<std::mutex> lk(s_mtx);
        if (s_locked) return VAULT_ERR_LOCKED;
        ExchangeStore& es = s_store[ex];
        if (es.count >= VAULT_MAX_KEYS) return VAULT_ERR_FULL;
        for (uint32_t i = 0; i < es.count; i++)
            if (es.slots[i].in_use && strcmp(es.slots[i].name, name) == 0)
                return VAULT_ERR_DUPLICATE;
        uint32_t slot = es.count++;
        Slot& sl = es.slots[slot];
        sl.in_use = true;
        sl.status = VAULT_KEY_STATUS_FREE;  // default: FREE
        strncpy_s(sl.name,   name,       VAULT_NAME_MAX-1);
        strncpy_s(sl.key,    api_key,    VAULT_KEY_MAX-1);
        strncpy_s(sl.secret, api_secret, VAULT_SECRET_MAX-1);
        if (out_slot) *out_slot = slot;
    }
    return vault_core_save();
}

VaultError vault_core_delete(VaultExchange ex, uint32_t slot)
{
    if (ex < 0 || ex >= VAULT_EXCHANGE_COUNT) return VAULT_ERR_INVALID;
    {
        std::lock_guard<std::mutex> lk(s_mtx);
        if (s_locked) return VAULT_ERR_LOCKED;
        ExchangeStore& es = s_store[ex];
        if (slot >= es.count) return VAULT_ERR_NOT_FOUND;
        SecureZeroMemory(&es.slots[slot], sizeof(Slot));
        for (uint32_t i = slot; i+1 < es.count; i++)
            es.slots[i] = es.slots[i+1];
        SecureZeroMemory(&es.slots[es.count-1], sizeof(Slot));
        es.count--;
    }
    return vault_core_save();
}

VaultError vault_core_get_meta(VaultExchange ex, uint32_t slot, VaultKeyMeta* out)
{
    if (!out || ex < 0 || ex >= VAULT_EXCHANGE_COUNT) return VAULT_ERR_INVALID;
    std::lock_guard<std::mutex> lk(s_mtx);
    if (s_locked) return VAULT_ERR_LOCKED;
    ExchangeStore& es = s_store[ex];
    if (slot >= es.count || !es.slots[slot].in_use) return VAULT_ERR_NOT_FOUND;
    strncpy_s(out->name,    es.slots[slot].name, VAULT_NAME_MAX-1);
    strncpy_s(out->api_key, es.slots[slot].key,  VAULT_KEY_MAX-1);
    out->slot_index = slot;
    out->status     = es.slots[slot].status;
    return VAULT_OK;
}

VaultError vault_core_get_secret(VaultExchange ex, uint32_t slot,
                                  char secret_out[VAULT_SECRET_MAX])
{
    if (!secret_out || ex < 0 || ex >= VAULT_EXCHANGE_COUNT) return VAULT_ERR_INVALID;
    std::lock_guard<std::mutex> lk(s_mtx);
    if (s_locked) return VAULT_ERR_LOCKED;
    ExchangeStore& es = s_store[ex];
    if (slot >= es.count || !es.slots[slot].in_use) return VAULT_ERR_NOT_FOUND;
    strncpy_s(secret_out, VAULT_SECRET_MAX, es.slots[slot].secret, VAULT_SECRET_MAX-1);
    return VAULT_OK;
}

VaultError vault_core_list(VaultExchange ex,
                            VaultKeyMeta out_list[VAULT_MAX_KEYS],
                            uint32_t* out_count)
{
    if (!out_list || !out_count || ex < 0 || ex >= VAULT_EXCHANGE_COUNT)
        return VAULT_ERR_INVALID;
    std::lock_guard<std::mutex> lk(s_mtx);
    if (s_locked) { *out_count = 0; return VAULT_ERR_LOCKED; }
    ExchangeStore& es = s_store[ex];
    *out_count = 0;
    for (uint32_t i = 0; i < es.count; i++) {
        if (!es.slots[i].in_use) continue;
        VaultKeyMeta& m = out_list[(*out_count)++];
        strncpy_s(m.name,    es.slots[i].name, VAULT_NAME_MAX-1);
        strncpy_s(m.api_key, es.slots[i].key,  VAULT_KEY_MAX-1);
        m.slot_index = i;
        m.status     = es.slots[i].status;
    }
    return VAULT_OK;
}

uint32_t vault_core_count(VaultExchange ex)
{
    if (ex < 0 || ex >= VAULT_EXCHANGE_COUNT) return 0;
    std::lock_guard<std::mutex> lk(s_mtx);
    return s_store[ex].count;
}

VaultError vault_core_set_status(VaultExchange ex, uint32_t slot, uint8_t status)
{
    if (ex < 0 || ex >= VAULT_EXCHANGE_COUNT) return VAULT_ERR_INVALID;
    if (status > VAULT_KEY_STATUS_NOTPAID)    return VAULT_ERR_INVALID;
    {
        std::lock_guard<std::mutex> lk(s_mtx);
        if (s_locked) return VAULT_ERR_LOCKED;
        ExchangeStore& es = s_store[ex];
        if (slot >= es.count || !es.slots[slot].in_use) return VAULT_ERR_NOT_FOUND;
        es.slots[slot].status = status;
    }
    return vault_core_save();
}

const char* vault_error_str(VaultError err)
{
    switch (err) {
        case VAULT_OK:              return "OK";
        case VAULT_ERR_NOT_FOUND:   return "Key not found";
        case VAULT_ERR_DECRYPT:     return "Decrypt failed";
        case VAULT_ERR_IO:          return "File I/O error";
        case VAULT_ERR_LOCKED:      return "Vault locked";
        case VAULT_ERR_INVALID:     return "Invalid parameter";
        case VAULT_ERR_NO_SERVICE:  return "Service not running";
        case VAULT_ERR_FULL:        return "Max keys reached (8)";
        case VAULT_ERR_DUPLICATE:   return "Name already exists";
        default:                    return "Unknown error";
    }
}

const char* vault_key_status_str(uint8_t status)
{
    switch (status) {
        case VAULT_KEY_STATUS_FREE:    return "FREE";
        case VAULT_KEY_STATUS_PAID:    return "PAID";
        case VAULT_KEY_STATUS_NOTPAID: return "NOTPAID";
        default:                       return "UNKNOWN";
    }
}
