# OmnibusSidebar — SuperVault

Modul de stocare securizata a cheilor API pentru exchange-uri.

## Librarii folosite

| Librarie | Scop | Origine |
|---|---|---|
| **DPAPI** `crypt32.lib` | Cripteaza/decripteaza vault.dat | Windows SDK built-in |
| **BCrypt** `bcrypt.lib` | HMAC-SHA256 pentru semnaturi ordine | Windows SDK built-in |
| **WinINet** `wininet.lib` | POST autentificat pentru ordine reale | Deja in proiect |
| **shell32** `shlobj.h` | Gaseste %APPDATA% | Windows SDK built-in |
| **ImGui** | Tab UI, input fields cu mascare | Deja in proiect |
| **STL** | std::string, std::vector, std::mutex | Deja in proiect |

**Zero dependente externe noi.** Doar `-lcrypt32 -lbcrypt` adaugate in Makefile.

---

## Securitate

- **Pe disc**: vault.dat este criptat cu DPAPI, legat de contul Windows curent. Alt user = nu poate decripta.
- **In memorie**: cheile sunt in plaintext cat timp aplicatia ruleaza. Butonul "Lock" le sterge cu `SecureZeroMemory`.
- **La salvare**: bufferele UI sunt sterse imediat dupa salvare cu `SecureZeroMemory`.
- **Nu se logheaza niciodata cheile** in tab-ul LOG.

---

## Fisiere

```
SuperVault/
├── mod_vault.h       ← interfata publica
├── mod_vault.cpp     ← implementare DPAPI + UI
└── VAULT_README.md   ← acest fisier
```

---

## Integrare in OmnibusSidebar

### 1. Copiaza fisierele in radacina proiectului

```bash
cp SuperVault/mod_vault.h   .
cp SuperVault/mod_vault.cpp .
```

### 2. Modifica Makefile

Adauga in SOURCES:
```makefile
SOURCES = main.cpp \
          mod_vault.cpp \    # <-- adaugat
          fetch.cpp \
          ...
```

Adauga in LDFLAGS:
```makefile
LDFLAGS = -lraylib -lopengl32 -lgdi32 -lwinmm -lwininet \
          -lcrypt32 -lbcrypt \   # <-- adaugat
          -mwindows
```

### 3. Modifica main.cpp

Adauga include:
```cpp
#include "mod_vault.h"
```

In `main()`, dupa `InitWindow()`:
```cpp
if (!Vault_Init())
    Log("Vault init failed", {1.f,0.3f,0.3f,1.f});
else
    Log("Vault loaded OK", {0.25f,1.f,0.45f,1.f});
```

In tab bar, adauga:
```cpp
if (ImGui::BeginTabItem(" VAULT ")) {
    DrawVaultTab();
    ImGui::EndTabItem();
}
```

### 4. Modifica mod_trade.cpp

In `DoOrder()`, inlocuieste simularea cu:
```cpp
#include "mod_vault.h"

// map UI s_exch -> VaultExchange
VaultExchange vex = (s_exch == 0) ? VAULT_LCX
                  : (s_exch == 1) ? VAULT_KRAKEN
                                  : VAULT_COINBASE;

std::string apiKey, apiSecret;
if (!Vault_GetKey(vex, apiKey, apiSecret)) {
    Log("[TRADE] No API keys — set them in VAULT tab", {1.f,0.6f,0.1f,1.f});
    PushToast("Set API keys in VAULT tab", {1.f,0.6f,0.1f,1.f});
    // zero pentru siguranta
    SecureZeroMemory((void*)apiKey.data(),    apiKey.size());
    SecureZeroMemory((void*)apiSecret.data(), apiSecret.size());
    return;
}

// TODO: construieste semnatura si trimite ordinul
// (vezi sectiunea HMAC mai jos)
```

---

## Format vault.dat (binar, DPAPI-encrypted)

```
[OMNV]          4 bytes  magic
[version]       4 bytes  uint32_le = 1
[count]         4 bytes  uint32_le = 3 (VAULT_COUNT)

Pentru fiecare exchange:
  [has]         4 bytes  uint32_le  (0 sau 1)
  [key_len]     4 bytes  uint32_le
  [key_data]    key_len bytes  (plaintext inainte de criptare DPAPI)
  [secret_len]  4 bytes  uint32_le
  [secret_data] secret_len bytes

Intregul buffer de mai sus este trecut prin CryptProtectData
inainte de a fi scris pe disc.
```

---

## Semnatura HMAC pentru Kraken (urmatorul pas)

Adauga in `fetch.cpp`:

```cpp
#include <bcrypt.h>
#pragma comment(lib, "bcrypt.lib")

// Computes HMAC-SHA256(key, data) -> raw bytes
std::vector<BYTE> HmacSha256(const std::string& key, const std::string& data)
{
    std::vector<BYTE> result;

    BCRYPT_ALG_HANDLE hAlg = NULL;
    BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_SHA256_ALGORITHM, NULL,
                                BCRYPT_ALG_HANDLE_HMAC_FLAG);

    BCRYPT_HASH_HANDLE hHash = NULL;
    BCryptCreateHash(hAlg, &hHash, NULL, 0,
                     (PUCHAR)key.data(), (ULONG)key.size(), 0);

    BCryptHashData(hHash, (PUCHAR)data.data(), (ULONG)data.size(), 0);

    ULONG hashLen = 32;
    result.resize(hashLen);
    BCryptFinishHash(hHash, result.data(), hashLen, 0);

    BCryptDestroyHash(hHash);
    BCryptCloseAlgorithmProvider(hAlg, 0);

    return result;
}

// Base64 encode
std::string Base64Encode(const std::vector<BYTE>& data) { /* ... */ }

// Kraken signature:
// nonce + postData -> SHA256 -> prepend URI path -> HMAC-SHA512(base64(secret), ...)
std::string KrakenSign(const std::string& secret, const std::string& path,
                       const std::string& nonce, const std::string& postData)
{
    // Step 1: SHA256(nonce + postData)
    // Step 2: path + step1
    // Step 3: HMAC-SHA512(base64_decode(secret), step2)
    // Step 4: base64(step3)
    return ""; // implementare completa in pasul urmator
}
```

---

## Roadmap

- [x] Stocare criptata DPAPI (vault.dat)
- [x] UI in sidebar (tab VAULT)
- [x] Lock / SecureZeroMemory
- [ ] POST autentificat Kraken (HMAC-SHA512)
- [ ] POST autentificat LCX (HMAC-SHA256)
- [ ] POST autentificat Coinbase
- [ ] Windows Hello pentru deblocare (viitor)
- [ ] Port Zig cross-platform (viitor)
