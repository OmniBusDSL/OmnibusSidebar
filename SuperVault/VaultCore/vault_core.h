// ============================================================
//  vault_core.h  v4  —  multi-key vault, C interface
//
//  Breaking change from v3: removed active-slot concept,
//  added per-key status (FREE / PAID / NOTPAID).
//  Secret never returned via LIST.
// ============================================================
#pragma once
#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

// ─── Constants ───────────────────────────────────────────────
typedef enum {
    VAULT_EXCHANGE_LCX      = 0,
    VAULT_EXCHANGE_KRAKEN   = 1,
    VAULT_EXCHANGE_COINBASE = 2,
    VAULT_EXCHANGE_COUNT    = 3
} VaultExchange;

#define VAULT_MAX_KEYS   8
#define VAULT_NAME_MAX   64
#define VAULT_KEY_MAX    8192    // enlarged: wallet pub JSON can be 4-5KB
#define VAULT_SECRET_MAX 16384   // enlarged: wallet secret JSON (mnemonic + all privkeys)

// ─── Key status ──────────────────────────────────────────────
#define VAULT_KEY_STATUS_FREE    0   // no subscription — limited access
#define VAULT_KEY_STATUS_PAID    1   // active subscription — full access
#define VAULT_KEY_STATUS_NOTPAID 2   // subscription expired — blocked

// ─── Opcodes (for VaaS pipe protocol + OmniBus syscalls) ─────
#define VAULT_OP_INIT        0x40
#define VAULT_OP_ADD         0x41
#define VAULT_OP_GET_META    0x42
#define VAULT_OP_DELETE      0x43
#define VAULT_OP_LOCK        0x44
#define VAULT_OP_LIST        0x45
#define VAULT_OP_SET_STATUS  0x46   // set key status (FREE/PAID/NOTPAID)
#define VAULT_OP_SAVE        0x48
#define VAULT_OP_COUNT       0x49
#define VAULT_OP_GET_SECRET  0x4A   // NOT proxied over pipe
#define VAULT_OP_SET_STATUS2 0x4B   // alias for compatibility

// ─── Error codes ─────────────────────────────────────────────
typedef enum {
    VAULT_OK               = 0,
    VAULT_ERR_NOT_FOUND    = 1,
    VAULT_ERR_DECRYPT      = 2,
    VAULT_ERR_IO           = 3,
    VAULT_ERR_LOCKED       = 4,
    VAULT_ERR_INVALID      = 5,
    VAULT_ERR_NO_SERVICE   = 6,
    VAULT_ERR_FULL         = 7,
    VAULT_ERR_DUPLICATE    = 8,
} VaultError;

// ─── Key metadata (safe to show in UI, no secret) ────────────
typedef struct {
    char     name[VAULT_NAME_MAX];
    char     api_key[VAULT_KEY_MAX];
    uint32_t slot_index;
    uint8_t  status;     // VAULT_KEY_STATUS_FREE / PAID / NOTPAID
} VaultKeyMeta;

// ─── Lifecycle ───────────────────────────────────────────────
VaultError  vault_core_init(const char* data_path);
VaultError  vault_core_save(void);
void        vault_core_lock(void);

// ─── Multi-key management ────────────────────────────────────
VaultError  vault_core_add(VaultExchange ex,
                            const char* name,
                            const char* api_key,
                            const char* api_secret,
                            uint32_t*   out_slot);

VaultError  vault_core_delete(VaultExchange ex, uint32_t slot);

VaultError  vault_core_get_meta(VaultExchange ex, uint32_t slot,
                                 VaultKeyMeta* out);

// Caller MUST SecureZeroMemory(secret_out, VAULT_SECRET_MAX) after use
VaultError  vault_core_get_secret(VaultExchange ex, uint32_t slot,
                                   char secret_out[VAULT_SECRET_MAX]);

VaultError  vault_core_list(VaultExchange ex,
                             VaultKeyMeta out_list[VAULT_MAX_KEYS],
                             uint32_t* out_count);

uint32_t    vault_core_count(VaultExchange ex);

// ─── Key status management ───────────────────────────────────
// status: VAULT_KEY_STATUS_FREE / PAID / NOTPAID
VaultError  vault_core_set_status(VaultExchange ex, uint32_t slot, uint8_t status);

// ─── Info ────────────────────────────────────────────────────
const char* vault_error_str(VaultError err);
const char* vault_key_status_str(uint8_t status);

#ifdef __cplusplus
}
#endif
