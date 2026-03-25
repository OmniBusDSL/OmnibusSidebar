// ============================================================
//  vault_client.cpp  —  VaaS client with embedded fallback
//
//  1. Tries to connect to \\.\pipe\OmnibusVault (service mode)
//  2. If service not available, uses vault_core directly (embedded)
//
//  This means OmnibusSidebar works both with and without
//  the vault service running.
// ============================================================
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <string>
#include <cstring>

#include "vault_client.h"
#include "../VaultCore/vault_core.h"

#define PIPE_NAME "\\\\.\\pipe\\OmnibusVault"
#define PIPE_TIMEOUT_MS 500

static VaultClientMode s_mode = VAULT_MODE_EMBEDDED;

// ─── Pipe communication helpers ──────────────────────────────
static bool PipeTransaction(const std::string& request, std::string& response)
{
    char resp[4096] = {};
    DWORD respLen   = 0;

    BOOL ok = CallNamedPipeA(
        PIPE_NAME,
        (void*)request.data(), (DWORD)request.size(),
        resp, sizeof(resp),
        &respLen,
        PIPE_TIMEOUT_MS);

    if (!ok || respLen == 0) return false;
    response.assign(resp, respLen);
    return true;
}

static bool ServiceAvailable()
{
    HANDLE h = CreateFileA(PIPE_NAME, GENERIC_READ | GENERIC_WRITE,
                           0, NULL, OPEN_EXISTING, 0, NULL);
    if (h != INVALID_HANDLE_VALUE) {
        CloseHandle(h);
        return true;
    }
    return false;
}

// ─── Protocol builders ───────────────────────────────────────
static void AppendU8(std::string& b, uint8_t v)   { b.push_back((char)v); }
static void AppendU16(std::string& b, uint16_t v) {
    b.push_back(v & 0xFF);
    b.push_back((v >> 8) & 0xFF);
}
static void AppendStr(std::string& b, const char* s) {
    uint16_t len = s ? (uint16_t)strlen(s) : 0;
    AppendU16(b, len);
    if (len) b.append(s, len);
}

static bool ParseU8(const std::string& b, size_t& pos, uint8_t& out) {
    if (pos >= b.size()) return false;
    out = (uint8_t)b[pos++];
    return true;
}
static bool ParseU16(const std::string& b, size_t& pos, uint16_t& out) {
    if (pos + 2 > b.size()) return false;
    out = (uint8_t)b[pos] | ((uint8_t)b[pos+1] << 8);
    pos += 2;
    return true;
}
static bool ParseStr(const std::string& b, size_t& pos, char* out, size_t max) {
    uint16_t len;
    if (!ParseU16(b, pos, len)) return false;
    if (pos + len > b.size()) return false;
    size_t n = len < max - 1 ? len : max - 1;
    memcpy(out, b.data() + pos, n);
    out[n] = 0;
    pos += len;
    return true;
}

// ─── Service mode implementations ────────────────────────────
static VaultError SvcSet(VaultExchange ex, const char* key, const char* secret)
{
    std::string req;
    AppendU8(req, VAULT_OP_SET);
    AppendU8(req, (uint8_t)ex);
    AppendStr(req, key);
    AppendStr(req, secret);

    std::string resp;
    if (!PipeTransaction(req, resp)) return VAULT_ERR_NO_SERVICE;

    uint8_t err; size_t pos = 0;
    if (!ParseU8(resp, pos, err)) return VAULT_ERR_NO_SERVICE;
    return (VaultError)err;
}

static VaultError SvcGet(VaultExchange ex, VaultKeyEntry* out)
{
    std::string req;
    AppendU8(req, VAULT_OP_GET);
    AppendU8(req, (uint8_t)ex);

    std::string resp;
    if (!PipeTransaction(req, resp)) return VAULT_ERR_NO_SERVICE;

    uint8_t err; size_t pos = 0;
    if (!ParseU8(resp, pos, err)) return VAULT_ERR_NO_SERVICE;
    if (err != VAULT_OK) return (VaultError)err;
    ParseStr(resp, pos, out->key,    VAULT_KEY_MAX);
    ParseStr(resp, pos, out->secret, VAULT_SECRET_MAX);
    return VAULT_OK;
}

static VaultError SvcDelete(VaultExchange ex)
{
    std::string req;
    AppendU8(req, VAULT_OP_DELETE);
    AppendU8(req, (uint8_t)ex);

    std::string resp;
    if (!PipeTransaction(req, resp)) return VAULT_ERR_NO_SERVICE;
    uint8_t err; size_t pos = 0;
    if (!ParseU8(resp, pos, err)) return VAULT_ERR_NO_SERVICE;
    return (VaultError)err;
}

static bool SvcHas(VaultExchange ex)
{
    std::string req;
    AppendU8(req, VAULT_OP_HAS);
    AppendU8(req, (uint8_t)ex);
    std::string resp;
    if (!PipeTransaction(req, resp)) return false;
    uint8_t err; size_t pos = 0;
    ParseU8(resp, pos, err);
    return err == VAULT_OK;
}

static void SvcLock()
{
    std::string req;
    AppendU8(req, VAULT_OP_LOCK);
    AppendU8(req, 0);
    std::string resp;
    PipeTransaction(req, resp);
}

// ─── Public API ──────────────────────────────────────────────
VaultError vault_client_init(const char* data_path, VaultClientMode* out_mode)
{
    if (ServiceAvailable()) {
        s_mode = VAULT_MODE_SERVICE;
    } else {
        s_mode = VAULT_MODE_EMBEDDED;
        VaultError err = vault_core_init(data_path);
        if (err != VAULT_OK) return err;
    }
    if (out_mode) *out_mode = s_mode;
    return VAULT_OK;
}

VaultError vault_client_set(VaultExchange ex, const char* key, const char* secret)
{
    return s_mode == VAULT_MODE_SERVICE
        ? SvcSet(ex, key, secret)
        : vault_core_set(ex, key, secret);
}

VaultError vault_client_get(VaultExchange ex, VaultKeyEntry* out)
{
    return s_mode == VAULT_MODE_SERVICE
        ? SvcGet(ex, out)
        : vault_core_get(ex, out);
}

VaultError vault_client_delete(VaultExchange ex)
{
    return s_mode == VAULT_MODE_SERVICE
        ? SvcDelete(ex)
        : vault_core_delete(ex);
}

bool vault_client_has(VaultExchange ex)
{
    return s_mode == VAULT_MODE_SERVICE
        ? SvcHas(ex)
        : vault_core_has(ex);
}

void vault_client_lock(void)
{
    s_mode == VAULT_MODE_SERVICE ? SvcLock() : vault_core_lock();
}

VaultClientMode vault_client_mode(void) { return s_mode; }

const char* vault_client_mode_str(void)
{
    return s_mode == VAULT_MODE_SERVICE ? "Service (pipe)" : "Embedded (DPAPI)";
}
