// ============================================================
//  mod_vault.cpp  —  Secure API key storage
//
//  Libraries used (all Windows built-in, no extra deps):
//    - DPAPI      : CryptProtectData / CryptUnprotectData (crypt32.lib)
//    - SHGetFolderPath : locate %APPDATA% (shell32.lib)
//    - SecureZeroMemory: wipe plaintext from RAM (windows.h)
//    - fstream    : read/write vault.dat
//    - ImGui      : tab UI (already in project)
// ============================================================
#define WIN32_LEAN_AND_MEAN
#define NOGDI
#define NOUSER
#include <windows.h>
#undef NOGDI
#undef NOUSER

#include <dpapi.h>
#include <shlobj.h>
#include <fstream>
#include <vector>
#include <mutex>
#include <cstring>
#include <string>
#include <sys/stat.h>

#include "mod_vault.h"
#include "mod_log.h"
#include "mod_toast.h"
#include "app_state.h"
#include "imgui/imgui.h"

// ─── Internal state ──────────────────────────────────────────
static std::mutex g_vaultMutex;

static struct VaultState {
    bool        has[VAULT_COUNT];
    std::string key[VAULT_COUNT];
    std::string secret[VAULT_COUNT];
} g_v;

static const char* EXCH_NAMES[VAULT_COUNT] = { "LCX", "Kraken", "Coinbase" };

// ─── Helpers ─────────────────────────────────────────────────
static std::string GetVaultDir()
{
    char appdata[MAX_PATH];
    SHGetFolderPathA(NULL, CSIDL_APPDATA, NULL, 0, appdata);
    return std::string(appdata) + "\\OmnibusSidebar";
}

static std::string GetVaultPath()
{
    return GetVaultDir() + "\\vault.dat";
}

static bool EnsureVaultDir()
{
    std::string dir = GetVaultDir();
    DWORD attr = GetFileAttributesA(dir.c_str());
    if (attr == INVALID_FILE_ATTRIBUTES)
        return CreateDirectoryA(dir.c_str(), NULL) != 0;
    return (attr & FILE_ATTRIBUTE_DIRECTORY) != 0;
}

// ─── DPAPI encrypt / decrypt ─────────────────────────────────
static bool DpapiEncrypt(const std::string& plain, std::vector<BYTE>& cipher)
{
    DATA_BLOB in  = { (DWORD)plain.size(), (BYTE*)plain.data() };
    DATA_BLOB out = {};
    if (!CryptProtectData(&in, L"OmnibusSidebarVault", NULL, NULL, NULL,
                          CRYPTPROTECT_UI_FORBIDDEN, &out))
        return false;
    cipher.assign(out.pbData, out.pbData + out.cbData);
    LocalFree(out.pbData);
    return true;
}

static bool DpapiDecrypt(const std::vector<BYTE>& cipher, std::string& plain)
{
    DATA_BLOB in  = { (DWORD)cipher.size(), (BYTE*)cipher.data() };
    DATA_BLOB out = {};
    if (!CryptUnprotectData(&in, NULL, NULL, NULL, NULL, 0, &out))
        return false;
    plain.assign((char*)out.pbData, out.cbData);
    SecureZeroMemory(out.pbData, out.cbData);
    LocalFree(out.pbData);
    return true;
}

// ─── Serialization helpers ───────────────────────────────────
// Write 4-byte little-endian uint32
static void WriteU32(std::vector<BYTE>& buf, uint32_t v)
{
    buf.push_back(v & 0xFF);
    buf.push_back((v >> 8) & 0xFF);
    buf.push_back((v >> 16) & 0xFF);
    buf.push_back((v >> 24) & 0xFF);
}

// Write length-prefixed string
static void WriteStr(std::vector<BYTE>& buf, const std::string& s)
{
    WriteU32(buf, (uint32_t)s.size());
    buf.insert(buf.end(), (BYTE*)s.data(), (BYTE*)s.data() + s.size());
}

static bool ReadU32(const std::vector<BYTE>& buf, size_t& pos, uint32_t& out)
{
    if (pos + 4 > buf.size()) return false;
    out = buf[pos] | (buf[pos+1]<<8) | (buf[pos+2]<<16) | (buf[pos+3]<<24);
    pos += 4;
    return true;
}

static bool ReadStr(const std::vector<BYTE>& buf, size_t& pos, std::string& out)
{
    uint32_t len;
    if (!ReadU32(buf, pos, len)) return false;
    if (pos + len > buf.size()) return false;
    out.assign((char*)&buf[pos], len);
    pos += len;
    return true;
}

// ─── Vault_Save ──────────────────────────────────────────────
// Format: [magic:4] [version:4] [count:4] { [has:4][key_str][secret_str] } * count
// Entire payload is DPAPI-encrypted before writing to disk.
bool Vault_Save()
{
    if (!EnsureVaultDir()) return false;

    std::lock_guard<std::mutex> lk(g_vaultMutex);

    std::vector<BYTE> plain;

    // magic + version + count
    plain.push_back('O'); plain.push_back('M'); plain.push_back('N'); plain.push_back('V');
    WriteU32(plain, 1);                   // version
    WriteU32(plain, VAULT_COUNT);         // entries

    for (int i = 0; i < VAULT_COUNT; i++) {
        WriteU32(plain, g_v.has[i] ? 1 : 0);
        WriteStr(plain, g_v.has[i] ? g_v.key[i]    : "");
        WriteStr(plain, g_v.has[i] ? g_v.secret[i] : "");
    }

    std::vector<BYTE> cipher;
    if (!DpapiEncrypt(std::string((char*)plain.data(), plain.size()), cipher)) {
        SecureZeroMemory(plain.data(), plain.size());
        return false;
    }
    SecureZeroMemory(plain.data(), plain.size());

    std::ofstream f(GetVaultPath(), std::ios::binary | std::ios::trunc);
    if (!f) return false;
    f.write((char*)cipher.data(), cipher.size());
    return f.good();
}

// ─── Vault_Init ──────────────────────────────────────────────
bool Vault_Init()
{
    memset(&g_v, 0, sizeof(g_v));

    std::ifstream f(GetVaultPath(), std::ios::binary);
    if (!f) {
        // no vault yet — create empty one
        return Vault_Save();
    }

    std::vector<BYTE> cipher((std::istreambuf_iterator<char>(f)),
                              std::istreambuf_iterator<char>());
    f.close();

    std::string plainStr;
    if (!DpapiDecrypt(cipher, plainStr)) return false;

    std::vector<BYTE> plain(plainStr.begin(), plainStr.end());
    SecureZeroMemory((void*)plainStr.data(), plainStr.size());
    plainStr.clear();

    size_t pos = 0;

    // magic
    if (plain.size() < 4) return false;
    if (plain[0]!='O'||plain[1]!='M'||plain[2]!='N'||plain[3]!='V') return false;
    pos = 4;

    uint32_t version, count;
    if (!ReadU32(plain, pos, version)) return false;
    if (!ReadU32(plain, pos, count))   return false;

    std::lock_guard<std::mutex> lk(g_vaultMutex);
    for (uint32_t i = 0; i < count && i < VAULT_COUNT; i++) {
        uint32_t has;
        if (!ReadU32(plain, pos, has)) break;
        std::string k, s;
        if (!ReadStr(plain, pos, k)) break;
        if (!ReadStr(plain, pos, s)) break;
        g_v.has[i]    = (has != 0);
        g_v.key[i]    = k;
        g_v.secret[i] = s;
    }

    SecureZeroMemory(plain.data(), plain.size());
    return true;
}

// ─── Public API ──────────────────────────────────────────────
bool Vault_SetKey(VaultExchange ex, const std::string& apiKey, const std::string& apiSecret)
{
    {
        std::lock_guard<std::mutex> lk(g_vaultMutex);
        g_v.has[ex]    = true;
        g_v.key[ex]    = apiKey;
        g_v.secret[ex] = apiSecret;
    }
    return Vault_Save();
}

bool Vault_GetKey(VaultExchange ex, std::string& outKey, std::string& outSecret)
{
    std::lock_guard<std::mutex> lk(g_vaultMutex);
    if (!g_v.has[ex]) return false;
    outKey    = g_v.key[ex];
    outSecret = g_v.secret[ex];
    return true;
}

bool Vault_DeleteKey(VaultExchange ex)
{
    {
        std::lock_guard<std::mutex> lk(g_vaultMutex);
        SecureZeroMemory((void*)g_v.key[ex].data(),    g_v.key[ex].size());
        SecureZeroMemory((void*)g_v.secret[ex].data(), g_v.secret[ex].size());
        g_v.has[ex]    = false;
        g_v.key[ex]    = "";
        g_v.secret[ex] = "";
    }
    return Vault_Save();
}

bool Vault_HasKey(VaultExchange ex)
{
    std::lock_guard<std::mutex> lk(g_vaultMutex);
    return g_v.has[ex];
}

void Vault_Lock()
{
    std::lock_guard<std::mutex> lk(g_vaultMutex);
    for (int i = 0; i < VAULT_COUNT; i++) {
        if (!g_v.key[i].empty())
            SecureZeroMemory((void*)g_v.key[i].data(), g_v.key[i].size());
        if (!g_v.secret[i].empty())
            SecureZeroMemory((void*)g_v.secret[i].data(), g_v.secret[i].size());
        g_v.has[i]    = false;
        g_v.key[i]    = "";
        g_v.secret[i] = "";
    }
}

// ─── UI ──────────────────────────────────────────────────────
void DrawVaultTab()
{
    static int        s_sel       = 0;
    static char       s_keyBuf[256]    = {};
    static char       s_secretBuf[512] = {};
    static bool       s_showSecret     = false;
    static bool       s_dirty          = false;

    ImGui::Spacing();

    // ── Exchange selector ─────────────────────────────────
    ImGui::PushFont(fntSmall);
    ImGui::TextColored({0.40f,0.40f,0.55f,1.f}, "EXCHANGE");
    ImGui::PopFont();

    ImVec4 exchCols[] = {
        {0.20f,0.55f,1.00f,1.f},
        {0.60f,0.35f,1.00f,1.f},
        {0.15f,0.80f,0.58f,1.f}
    };

    float bw = ((float)(g_sidebarW-4)-28.f)/3.f;
    for (int i = 0; i < VAULT_COUNT; i++) {
        bool sel = (s_sel == i);
        ImVec4 ac = exchCols[i];
        if (sel) {
            ImGui::PushStyleColor(ImGuiCol_Button,       {ac.x*.3f,ac.y*.3f,ac.z*.3f,1.f});
            ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{ac.x*.4f,ac.y*.4f,ac.z*.4f,1.f});
            ImGui::PushStyleColor(ImGuiCol_Text, ac);
        }
        ImGui::PushFont(fntMedium);
        if (ImGui::Button(EXCH_NAMES[i], {bw, 30.f})) {
            s_sel = i;
            // load existing keys into buffers for display (masked)
            memset(s_keyBuf, 0, sizeof(s_keyBuf));
            memset(s_secretBuf, 0, sizeof(s_secretBuf));
            s_dirty = false;
        }
        ImGui::PopFont();
        if (sel) ImGui::PopStyleColor(3);
        if (i < 2) ImGui::SameLine(0, 4);
    }

    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();

    // ── Status indicator ─────────────────────────────────
    bool hasKey = Vault_HasKey((VaultExchange)s_sel);
    if (hasKey)
        ImGui::TextColored({0.25f,1.f,0.45f,1.f}, "  Keys stored and encrypted");
    else
        ImGui::TextColored({0.70f,0.35f,0.35f,1.f}, "  No keys stored for %s", EXCH_NAMES[s_sel]);

    ImGui::Spacing();

    // ── Input fields ─────────────────────────────────────
    ImGui::PushFont(fntSmall);
    ImGui::TextColored({0.40f,0.40f,0.55f,1.f}, "API KEY");
    ImGui::PopFont();
    ImGui::SetNextItemWidth(-1);
    ImGuiInputTextFlags flags = ImGuiInputTextFlags_Password;
    if (ImGui::InputText("##vkey", s_keyBuf, sizeof(s_keyBuf), flags))
        s_dirty = true;

    ImGui::PushFont(fntSmall);
    ImGui::TextColored({0.40f,0.40f,0.55f,1.f}, "API SECRET");
    ImGui::PopFont();
    ImGui::SetNextItemWidth(-1);
    if (ImGui::InputText("##vsec", s_secretBuf, sizeof(s_secretBuf), flags))
        s_dirty = true;

    ImGui::Spacing();

    // ── Buttons ───────────────────────────────────────────
    float bw2 = ((float)(g_sidebarW-4)-24.f)/2.f;

    ImGui::PushStyleColor(ImGuiCol_Button,        {0.06f,0.30f,0.10f,1.f});
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, {0.08f,0.45f,0.15f,1.f});
    ImGui::PushFont(fntBold);
    bool doSave = ImGui::Button("  SAVE  ", {bw2, 34.f});
    ImGui::PopFont();
    ImGui::PopStyleColor(2);

    ImGui::SameLine(0, 4);

    ImGui::PushStyleColor(ImGuiCol_Button,        {0.35f,0.06f,0.06f,1.f});
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, {0.55f,0.08f,0.08f,1.f});
    ImGui::PushFont(fntBold);
    bool doDelete = ImGui::Button("  DELETE  ", {bw2, 34.f});
    ImGui::PopFont();
    ImGui::PopStyleColor(2);

    // ── Actions ───────────────────────────────────────────
    if (doSave) {
        std::string k(s_keyBuf);
        std::string s(s_secretBuf);
        if (k.empty() || s.empty()) {
            PushToast("Fill in Key and Secret first", {1.f,0.6f,0.1f,1.f});
        } else {
            if (Vault_SetKey((VaultExchange)s_sel, k, s)) {
                Log(std::string("Vault: saved keys for ") + EXCH_NAMES[s_sel],
                    {0.25f,1.f,0.45f,1.f});
                PushToast("Keys saved & encrypted", {0.25f,0.9f,0.45f,1.f});
                // zero buffers immediately after save
                SecureZeroMemory(s_keyBuf,    sizeof(s_keyBuf));
                SecureZeroMemory(s_secretBuf, sizeof(s_secretBuf));
                s_dirty = false;
            } else {
                PushToast("Save failed (DPAPI error?)", {1.f,0.3f,0.3f,1.f});
            }
        }
    }

    if (doDelete) {
        Vault_DeleteKey((VaultExchange)s_sel);
        Log(std::string("Vault: deleted keys for ") + EXCH_NAMES[s_sel],
            {0.70f,0.35f,0.35f,1.f});
        PushToast("Keys deleted", {1.f,0.4f,0.4f,1.f});
        SecureZeroMemory(s_keyBuf,    sizeof(s_keyBuf));
        SecureZeroMemory(s_secretBuf, sizeof(s_secretBuf));
        s_dirty = false;
    }

    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();

    // ── Lock button ───────────────────────────────────────
    ImGui::PushStyleColor(ImGuiCol_Button,        {0.10f,0.10f,0.20f,1.f});
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, {0.15f,0.15f,0.30f,1.f});
    ImGui::PushFont(fntSmall);
    if (ImGui::Button("Lock (clear keys from memory)", {-1, 24.f})) {
        Vault_Lock();
        Log("Vault locked — keys cleared from RAM", {0.40f,0.40f,0.65f,1.f});
        PushToast("Vault locked", {0.5f,0.5f,0.8f,1.f});
    }
    ImGui::PopFont();
    ImGui::PopStyleColor(2);

    if (ImGui::IsItemHovered())
        ImGui::SetTooltip("Keys are wiped from memory.\nReopen app to reload from encrypted vault.dat");

    ImGui::Spacing();
    ImGui::PushFont(fntSmall);
    ImGui::TextColored({0.22f,0.22f,0.38f,1.f},
        "  Stored in: %%APPDATA%%\\OmnibusSidebar\\vault.dat");
    ImGui::TextColored({0.22f,0.22f,0.38f,1.f},
        "  Encrypted with Windows DPAPI (current user)");
    ImGui::PopFont();
}
