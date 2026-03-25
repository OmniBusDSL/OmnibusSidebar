// ============================================================
//  mod_vault.h  —  Secure API key storage (DPAPI encrypted)
//
//  Storage:  %APPDATA%\OmnibusSidebar\vault.dat
//  Crypto:   Windows DPAPI (tied to current user account)
//  Memory:   keys in plaintext while app runs, zeroed on Lock
// ============================================================
#pragma once
#include <string>

enum VaultExchange {
    VAULT_LCX      = 0,
    VAULT_KRAKEN   = 1,
    VAULT_COINBASE = 2,
    VAULT_COUNT    = 3
};

// ── Lifecycle ────────────────────────────────────────────────
bool Vault_Init();    // load from disk or create empty vault
bool Vault_Save();    // encrypt + write vault.dat to %APPDATA%

// ── Key management ───────────────────────────────────────────
bool Vault_SetKey(VaultExchange ex, const std::string& apiKey, const std::string& apiSecret);
bool Vault_GetKey(VaultExchange ex, std::string& outKey, std::string& outSecret);
bool Vault_DeleteKey(VaultExchange ex);
bool Vault_HasKey(VaultExchange ex);

// ── Security ─────────────────────────────────────────────────
void Vault_Lock();    // SecureZeroMemory — clears keys from RAM

// ── UI ───────────────────────────────────────────────────────
void DrawVaultTab();
