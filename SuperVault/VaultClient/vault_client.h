// ============================================================
//  vault_client.h  —  Client library for VaaS (Named Pipe)
//
//  Use this in OmnibusSidebar, GridBot, Python via ctypes, etc.
//  Talks to vault_service.exe via \\.\pipe\OmnibusVault
//
//  Fallback: if service not running, falls back to direct
//  vault_core embedded mode (same process, DPAPI).
// ============================================================
#pragma once
#ifdef __cplusplus
extern "C" {
#endif

#include "../VaultCore/vault_core.h"

// ─── Mode ────────────────────────────────────────────────────
typedef enum {
    VAULT_MODE_EMBEDDED = 0,   // direct vault_core in same process
    VAULT_MODE_SERVICE  = 1,   // talks to vault_service via named pipe
} VaultClientMode;

// ─── Init ────────────────────────────────────────────────────
// Try to connect to service first; if not available, use embedded.
// data_path only used in embedded mode.
VaultError vault_client_init(const char* data_path, VaultClientMode* out_mode);

// ─── Same API as vault_core ───────────────────────────────────
VaultError vault_client_set(VaultExchange ex, const char* key, const char* secret);
VaultError vault_client_get(VaultExchange ex, VaultKeyEntry* out);
VaultError vault_client_delete(VaultExchange ex);
bool       vault_client_has(VaultExchange ex);
void       vault_client_lock(void);

// ─── Info ────────────────────────────────────────────────────
VaultClientMode vault_client_mode(void);
const char*     vault_client_mode_str(void);

#ifdef __cplusplus
}
#endif
