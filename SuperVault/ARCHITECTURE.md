# OmniBus SuperVault — Architecture

## VaaS (Vault as a Service)

```
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  OmnibusSidebar     │  │  VaultManager.py    │  │  GridBot / any bot  │
│  (C++ ImGui)        │  │  (Python tkinter)   │  │  (C++ / Python)     │
│  uses vault_client  │  │  uses Named Pipe    │  │  uses vault_client  │
└──────────┬──────────┘  └──────────┬──────────┘  └──────────┬──────────┘
           │                        │                        │
           └────────────────────────┴────────────────────────┘
                                    │
                        \\.\pipe\OmnibusVault
                                    │
                    ┌───────────────▼───────────────┐
                    │     vault_service.exe          │
                    │     (Windows daemon)           │
                    │     Named Pipe server          │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │     VaultCore                  │
                    │     vault_core_windows.cpp     │
                    │     DPAPI encryption           │
                    │     vault.dat storage          │
                    └───────────────────────────────┘
```

## Files

```
SuperVault/
│
├── VaultCore/
│   ├── vault_core.h                  ← Public C interface (opcodes, errors, types)
│   ├── vault_core_windows.cpp        ← Windows: DPAPI + BCrypt backend
│   ├── vault_core_linux.cpp          ← (future) Linux: keyctl / libsodium
│   └── vault_core_omnibus.cpp        ← (future) OmniBus: protected memory + opcodes
│
├── VaultService/
│   └── vault_service.cpp             ← Named Pipe daemon (Windows)
│
├── VaultClient/
│   ├── vault_client.h                ← Client API (service + embedded fallback)
│   └── vault_client.cpp              ← Auto-detects service, falls back to embedded
│
├── VaultManager/
│   └── vault_manager.py              ← Standalone Python GUI manager
│
├── mod_vault.h                       ← ImGui tab for OmnibusSidebar (uses vault_client)
├── mod_vault.cpp                     ← DrawVaultTab() + wrapper around vault_client
└── ARCHITECTURE.md                   ← This file
```

## Opcodes

| Opcode | Hex  | Name         | Description                    |
|--------|------|--------------|--------------------------------|
| 0x40   | INIT | VAULT_INIT   | Init vault (not over pipe)     |
| 0x41   | SET  | VAULT_SET    | Store API key + secret         |
| 0x42   | GET  | VAULT_GET    | Retrieve API key + secret      |
| 0x43   | DEL  | VAULT_DELETE | Delete entry                   |
| 0x44   | LOCK | VAULT_LOCK   | Wipe keys from memory          |
| 0x45   | HAS  | VAULT_HAS    | Check if key exists            |
| 0x46   | SAVE | VAULT_SAVE   | Force save to disk             |

## Wire Protocol (Named Pipe)

```
Request:
  [opcode:u8][exchange:u8][key_len:u16le][key_data][secret_len:u16le][secret_data]

Response:
  [error:u8][key_len:u16le][key_data][secret_len:u16le][secret_data]
```

## Error Codes

| Code | Name               | Meaning                        |
|------|--------------------|--------------------------------|
| 0    | VAULT_OK           | Success                        |
| 1    | VAULT_ERR_NOT_FOUND| No key for this exchange       |
| 2    | VAULT_ERR_DECRYPT  | DPAPI decrypt failed           |
| 3    | VAULT_ERR_IO       | File read/write error          |
| 4    | VAULT_ERR_LOCKED   | Vault locked (memory wiped)    |
| 5    | VAULT_ERR_INVALID  | Invalid parameters             |
| 6    | VAULT_ERR_NO_SERVICE| Pipe not available            |

## Build

### vault_service.exe

```bash
cd SuperVault/VaultService
g++ -std=c++17 vault_service.cpp ../VaultCore/vault_core_windows.cpp \
    -lcrypt32 -lshell32 -ladvapi32 \
    -o vault_service.exe
```

### OmnibusSidebar with vault_client

Add to Makefile SOURCES:
```
SuperVault/VaultClient/vault_client.cpp
SuperVault/VaultCore/vault_core_windows.cpp
```

Add to LDFLAGS:
```
-lcrypt32 -lshell32 -ladvapi32
```

### vault_manager.py

```bash
python vault_manager.py
# requires vault_service.exe to be running
```

## Client mode logic

```
vault_client_init()
    │
    ├── tries \\.\pipe\OmnibusVault
    │       │
    │       ├── SUCCESS → VAULT_MODE_SERVICE
    │       │   All calls go through Named Pipe
    │       │
    │       └── FAIL → VAULT_MODE_EMBEDDED
    │           vault_core_init() called directly
    │           DPAPI used in same process
```

## Future platforms

| Platform   | Backend              | Transport                    |
|------------|----------------------|------------------------------|
| Windows    | DPAPI + BCrypt       | Named Pipe                   |
| Linux      | libsodium + keyctl   | Unix Domain Socket           |
| FreeBSD    | libsodium            | Unix Domain Socket           |
| OmniBus OS | Protected memory zone| Syscall opcodes 0x40-0x46   |
| Zig port   | Cross-platform core  | Replaces vault_core_*.cpp    |
