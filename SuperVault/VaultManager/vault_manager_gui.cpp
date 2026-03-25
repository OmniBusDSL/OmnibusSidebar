// ============================================================
//  vault_manager_gui.cpp  —  Standalone Vault Manager EXE
//
//  Single instance (named mutex).
//  Talks to vault_service via \\.\pipe\OmnibusVault
//  Uses same Raylib + ImGui as OmnibusSidebar.
//
//  Build:
//    g++ -std=c++17 vault_manager_gui.cpp
//        ../../VaultCore/vault_core_windows.cpp
//        -I../../VaultCore -I../../.. -I../../../imgui
//        -I../../../raylib_pkg/raylib-5.0_win64_mingw-w64/include
//        -L../../../raylib_pkg/raylib-5.0_win64_mingw-w64/lib
//        ../../../imgui/imgui.cpp ../../../imgui/imgui_draw.cpp
//        ../../../imgui/imgui_widgets.cpp ../../../imgui/imgui_tables.cpp
//        ../../../rlImGui.cpp
//        -lraylib -lopengl32 -lgdi32 -lwinmm -lcrypt32 -ladvapi32 -mwindows
//        -o VaultManager.exe
// ============================================================
// raylib MUST come before windows.h to avoid Rectangle/CloseWindow conflicts
#include "raylib.h"
#include "rlImGui.h"
#include "imgui/imgui.h"

// WinAPI needed for: named mutex, named pipe, SecureZeroMemory
// NOUSER avoids CloseWindow/ShowCursor conflicts with raylib
#define WIN32_LEAN_AND_MEAN
#define NOGDI
#define NOUSER
#include <windows.h>
#undef NOGDI
#undef NOUSER

// Forward-declare MessageBoxA manually (from winuser.h, but NOUSER excluded it)
extern "C" __declspec(dllimport) int __stdcall
MessageBoxA(void* hWnd, const char* lpText, const char* lpCaption, unsigned int uType);
#define MB_ICONWARNING 0x00000030L

#include <stdint.h>
#include <stdio.h>
#include <string>
#include <cstring>
#include <vector>

#include "../VaultCore/vault_core.h"

#define MUTEX_NAME   "Global\\OmnibusVaultManager"
#define PIPE_NAME    "\\\\.\\pipe\\OmnibusVault"
#define PIPE_TIMEOUT  2000

// ─── Pipe helpers (same protocol as vault_service) ───────────
static void PU8(std::string& b, uint8_t v)  { b.push_back((char)v); }
static void PU16(std::string& b, uint16_t v){ b.push_back(v&0xFF); b.push_back((v>>8)&0xFF); }
static void PStr(std::string& b, const char* s){
    uint16_t l=s?(uint16_t)strlen(s):0; PU16(b,l); if(l) b.append(s,l); }

static bool pipe_call(const std::string& req, std::string& resp)
{
    char buf[8192]; DWORD rd=0;
    printf("[PIPE] Sending %d bytes, opcode=0x%02X exch=%d\n",
        (int)req.size(), (unsigned char)req[0], (unsigned char)req[1]);
    fflush(stdout);
    BOOL ok = CallNamedPipeA(PIPE_NAME,
        (void*)req.data(), (DWORD)req.size(),
        buf, sizeof(buf), &rd, PIPE_TIMEOUT);
    DWORD lastErr = GetLastError();
    if(!ok||rd==0){
        printf("[PIPE] FAILED ok=%d rd=%d LastError=%lu\n", (int)ok, (int)rd, lastErr);
        fflush(stdout);
        return false;
    }
    printf("[PIPE] OK, got %d bytes back, resp[0]=0x%02X\n", (int)rd, (unsigned char)buf[0]);
    fflush(stdout);
    resp.assign(buf,rd);
    return true;
}

static bool GU8(const std::string& b, size_t& p, uint8_t& v){
    if(p>=b.size()) return false; v=(uint8_t)b[p++]; return true; }
static bool GU16(const std::string& b, size_t& p, uint16_t& v){
    if(p+2>b.size()) return false;
    v=(uint8_t)b[p]|((uint8_t)b[p+1]<<8); p+=2; return true; }
static bool GU32(const std::string& b, size_t& p, uint32_t& v){
    if(p+4>b.size()) return false;
    v=(uint8_t)b[p]|((uint8_t)b[p+1]<<8)|((uint8_t)b[p+2]<<16)|((uint32_t)(uint8_t)b[p+3]<<24);
    p+=4; return true; }
static bool GStr(const std::string& b, size_t& p, char* out, size_t max){
    uint16_t l; if(!GU16(b,p,l)) return false;
    if(p+l>b.size()) return false;
    size_t n=l<max-1?l:max-1; memcpy(out,b.data()+p,n); out[n]=0; p+=l; return true; }

// ─── Pipe operations ─────────────────────────────────────────
static bool svc_connected()
{
    HANDLE h=CreateFileA(PIPE_NAME,GENERIC_READ|GENERIC_WRITE,0,NULL,OPEN_EXISTING,0,NULL);
    if(h==INVALID_HANDLE_VALUE){
        printf("[CONN] Pipe NOT available, LastError=%lu\n", GetLastError());
        fflush(stdout);
        return false;
    }
    CloseHandle(h);
    printf("[CONN] Pipe OK\n"); fflush(stdout);
    return true;
}

struct KeyEntry { char name[VAULT_NAME_MAX]; char api_key[VAULT_KEY_MAX];
                  uint32_t slot; bool active; };

static VaultError svc_list(int exch, std::vector<KeyEntry>& out)
{
    std::string req,resp;
    PU8(req,VAULT_OP_LIST); PU8(req,(uint8_t)exch);
    PU16(req,0); PU16(req,0);
    printf("[LIST] exch=%d\n", exch); fflush(stdout);
    if(!pipe_call(req,resp)) return VAULT_ERR_NO_SERVICE;
    size_t p=0; uint8_t err; GU8(resp,p,err);
    uint16_t plen; GU16(resp,p,plen);
    uint32_t cnt=0; GU32(resp,p,cnt);
    printf("[LIST] err=%d cnt=%u\n", (int)err, cnt); fflush(stdout);
    out.clear();
    for(uint32_t i=0;i<cnt;i++){
        KeyEntry e={};
        GStr(resp,p,e.name,    sizeof(e.name));
        GStr(resp,p,e.api_key, sizeof(e.api_key));
        GU32(resp,p,e.slot);
        uint8_t act=0; GU8(resp,p,act); e.active=(act!=0);
        printf("[LIST]   [%u] name='%s' slot=%u active=%d\n", i, e.name, e.slot, (int)e.active);
        fflush(stdout);
        out.push_back(e);
    }
    return (VaultError)err;
}

static VaultError svc_add(int exch, const char* name, const char* key, const char* secret)
{
    printf("[ADD] exch=%d name='%s' key_len=%d secret_len=%d\n",
        exch, name, (int)strlen(key), (int)strlen(secret));
    fflush(stdout);
    std::string req,resp;
    PU8(req,VAULT_OP_ADD); PU8(req,(uint8_t)exch);
    PU16(req,0); // slot unused for ADD
    std::string payload; PStr(payload,name); PStr(payload,key); PStr(payload,secret);
    PU16(req,(uint16_t)payload.size()); req.append(payload);
    printf("[ADD] total req=%d bytes payload=%d bytes\n", (int)req.size(), (int)payload.size());
    fflush(stdout);
    if(!pipe_call(req,resp)) return VAULT_ERR_NO_SERVICE;
    size_t p=0; uint8_t err; GU8(resp,p,err);
    printf("[ADD] response err=%d (%s)\n", (int)err, vault_error_str((VaultError)err));
    fflush(stdout);
    return (VaultError)err;
}

static VaultError svc_delete(int exch, uint32_t slot)
{
    std::string req,resp;
    PU8(req,VAULT_OP_DELETE); PU8(req,(uint8_t)exch);
    PU16(req,(uint16_t)slot); PU16(req,0);
    if(!pipe_call(req,resp)) return VAULT_ERR_NO_SERVICE;
    size_t p=0; uint8_t err; GU8(resp,p,err);
    return (VaultError)err;
}

static VaultError svc_set_active(int exch, uint32_t slot)
{
    std::string req,resp;
    PU8(req,VAULT_OP_SET_ACTIVE); PU8(req,(uint8_t)exch);
    PU16(req,(uint16_t)slot); PU16(req,0);
    if(!pipe_call(req,resp)) return VAULT_ERR_NO_SERVICE;
    size_t p=0; uint8_t err; GU8(resp,p,err);
    return (VaultError)err;
}

// ─── Fonts ───────────────────────────────────────────────────
static ImFont* fntReg  = nullptr;
static ImFont* fntBold = nullptr;
static ImFont* fntSm   = nullptr;

// ─── UI state ────────────────────────────────────────────────
static int   s_exch = 0;
static std::vector<KeyEntry> s_keys[3];
static bool  s_connected = false;
static char  s_status[128] = "Checking...";
static float s_statusTimer = 0.f;

static char  s_new_name[VAULT_NAME_MAX]    = {};
static char  s_new_key[VAULT_KEY_MAX]      = {};
static char  s_new_sec[VAULT_SECRET_MAX]   = {};
static bool  s_show_add = false;
static int   s_confirm_del = -1; // slot awaiting delete confirm

static const char* EXCH_NAMES[] = {"LCX","Kraken","Coinbase"};
static ImVec4      EXCH_COLS[]  = {
    {0.20f,0.55f,1.00f,1.f},
    {0.60f,0.35f,1.00f,1.f},
    {0.15f,0.80f,0.58f,1.f}
};

static void Refresh()
{
    s_connected = svc_connected();
    if(s_connected){
        for(int e=0;e<3;e++) svc_list(e, s_keys[e]);
        snprintf(s_status,sizeof(s_status),"Connected to vault service");
    } else {
        snprintf(s_status,sizeof(s_status),"Service not running — start vault_service.exe");
    }
}

// Mask api_key: show first 8 + ... + last 4
static std::string MaskKey(const char* k)
{
    std::string s(k);
    if(s.size()<=12) return s;
    return s.substr(0,8) + "..." + s.substr(s.size()-4);
}

static void DrawUI(float monW, float monH)
{
    ImGui::SetNextWindowPos({0,0});
    ImGui::SetNextWindowSize({monW, monH});
    ImGui::Begin("##vm", nullptr,
        ImGuiWindowFlags_NoDecoration|ImGuiWindowFlags_NoMove|
        ImGuiWindowFlags_NoBringToFrontOnFocus);

    // ── Header ───────────────────────────────────────────────
    ImGui::PushFont(fntBold);
    ImGui::TextColored({0.95f,0.82f,0.20f,1.f}, "OMNIBUS VAULT MANAGER");
    ImGui::PopFont();
    ImGui::SameLine();
    ImGui::PushFont(fntSm);
    ImGui::TextColored({0.25f,0.75f,0.45f,1.f}, "  v2.0");
    ImGui::PopFont();
    ImGui::SameLine(monW-220.f);
    ImGui::PushFont(fntSm);
    if(s_connected)
        ImGui::TextColored({0.25f,1.f,0.45f,1.f}, "Service: connected");
    else
        ImGui::TextColored({1.f,0.35f,0.35f,1.f}, "Service: NOT running");
    ImGui::PopFont();

    ImGui::PushFont(fntSm);
    ImGui::TextColored({0.30f,0.30f,0.48f,1.f}, "  %s", s_status);
    ImGui::PopFont();
    ImGui::Separator();
    ImGui::Spacing();

    // ── Exchange selector ─────────────────────────────────────
    float bw = (monW-36.f)/3.f;
    for(int i=0;i<3;i++){
        bool sel=(s_exch==i);
        ImVec4 ac=EXCH_COLS[i];
        if(sel){
            ImGui::PushStyleColor(ImGuiCol_Button,       {ac.x*.3f,ac.y*.3f,ac.z*.3f,1.f});
            ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{ac.x*.4f,ac.y*.4f,ac.z*.4f,1.f});
            ImGui::PushStyleColor(ImGuiCol_Text, ac);
        }
        ImGui::PushFont(fntBold);
        if(ImGui::Button(EXCH_NAMES[i],{bw,32.f})){
            s_exch=i; s_confirm_del=-1; s_show_add=false;
        }
        ImGui::PopFont();
        if(sel) ImGui::PopStyleColor(3);
        if(i<2) ImGui::SameLine(0,4);
    }

    ImGui::Spacing();

    // ── Key list ─────────────────────────────────────────────
    ImVec4 ac = EXCH_COLS[s_exch];
    ImGui::PushFont(fntSm);
    ImGui::TextColored({0.40f,0.40f,0.55f,1.f},
        "STORED KEYS (%d / %d)", (int)s_keys[s_exch].size(), VAULT_MAX_KEYS);
    ImGui::PopFont();

    float listH = monH - 380.f;
    ImGui::BeginChild("##klist", {0, listH}, true);

    if(s_keys[s_exch].empty()){
        ImGui::Spacing();
        ImGui::SetCursorPosX(20.f);
        ImGui::TextColored({0.40f,0.40f,0.55f,1.f}, "No keys stored for %s", EXCH_NAMES[s_exch]);
    }

    for(auto& k : s_keys[s_exch]){
        ImGui::PushID((int)k.slot);
        bool isActive = k.active;
        ImVec4 rowCol = isActive ? ac : ImVec4{0.55f,0.55f,0.65f,1.f};

        // Active marker + name
        ImGui::PushFont(fntBold);
        ImGui::TextColored(rowCol, isActive ? "  [*]" : "  [ ]");
        ImGui::PopFont();
        ImGui::SameLine();
        ImGui::PushFont(fntReg);
        ImGui::TextColored(rowCol, "%s", k.name);
        ImGui::PopFont();

        // API key (masked)
        ImGui::PushFont(fntSm);
        ImGui::SetCursorPosX(48.f);
        ImGui::TextColored({0.35f,0.35f,0.50f,1.f},
            "API: %s", MaskKey(k.api_key).c_str());
        ImGui::PopFont();

        // Buttons
        ImGui::SetCursorPosX(48.f);
        if(!isActive){
            ImGui::PushStyleColor(ImGuiCol_Button,{ac.x*.25f,ac.y*.25f,ac.z*.25f,1.f});
            ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{ac.x*.4f,ac.y*.4f,ac.z*.4f,1.f});
            ImGui::PushFont(fntSm);
            if(ImGui::Button("Set Active",{90,22})){
                svc_set_active(s_exch, k.slot);
                Refresh();
            }
            ImGui::PopFont();
            ImGui::PopStyleColor(2);
            ImGui::SameLine(0,6);
        } else {
            ImGui::PushFont(fntSm);
            ImGui::TextColored(ac, "  ACTIVE");
            ImGui::PopFont();
            ImGui::SameLine(0,6);
        }

        ImGui::PushStyleColor(ImGuiCol_Button,{0.35f,0.06f,0.06f,1.f});
        ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{0.55f,0.08f,0.08f,1.f});
        ImGui::PushFont(fntSm);
        if(ImGui::Button("Delete",{60,22})){
            s_confirm_del = (int)k.slot;
            ImGui::OpenPopup("##cdel");
        }
        ImGui::PopFont();
        ImGui::PopStyleColor(2);

        ImGui::Separator();
        ImGui::PopID();
    }

    // Delete confirm popup
    if(ImGui::BeginPopupModal("##cdel",nullptr,ImGuiWindowFlags_AlwaysAutoResize)){
        ImGui::PushFont(fntBold);
        ImGui::TextColored({1.f,0.35f,0.35f,1.f},"CONFIRM DELETE");
        ImGui::PopFont();
        ImGui::Separator();
        if(s_confirm_del>=0 && s_confirm_del<(int)s_keys[s_exch].size()){
            auto& ck=s_keys[s_exch][s_confirm_del];
            ImGui::Text("Exchange: %s", EXCH_NAMES[s_exch]);
            ImGui::Text("Key: %s", ck.name);
        }
        ImGui::Spacing();
        ImGui::PushStyleColor(ImGuiCol_Button,{0.45f,0.06f,0.06f,1.f});
        if(ImGui::Button("DELETE",{120,30})){
            if(s_confirm_del>=0 && s_confirm_del<(int)s_keys[s_exch].size()){
                svc_delete(s_exch, s_keys[s_exch][s_confirm_del].slot);
                Refresh();
            }
            s_confirm_del=-1; ImGui::CloseCurrentPopup();
        }
        ImGui::PopStyleColor();
        ImGui::SameLine();
        if(ImGui::Button("Cancel",{100,30})){
            s_confirm_del=-1; ImGui::CloseCurrentPopup();
        }
        ImGui::EndPopup();
    }

    ImGui::EndChild();

    // ── Add new key ───────────────────────────────────────────
    ImGui::Spacing();
    ImGui::PushStyleColor(ImGuiCol_Button,{0.06f,0.25f,0.10f,1.f});
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{0.08f,0.38f,0.14f,1.f});
    ImGui::PushFont(fntBold);
    if(ImGui::Button(s_show_add?"  - CANCEL  ":"  + ADD KEY  ",{-1,30}))
        s_show_add = !s_show_add;
    ImGui::PopFont();
    ImGui::PopStyleColor(2);

    if(s_show_add){
        ImGui::Spacing();
        ImGui::PushFont(fntSm); ImGui::TextColored({0.40f,0.40f,0.55f,1.f},"NAME"); ImGui::PopFont();
        ImGui::SetNextItemWidth(-1);
        ImGui::InputText("##nm", s_new_name, sizeof(s_new_name));

        ImGui::PushFont(fntSm); ImGui::TextColored({0.40f,0.40f,0.55f,1.f},"API KEY"); ImGui::PopFont();
        ImGui::SetNextItemWidth(-1);
        ImGui::InputText("##nk", s_new_key, sizeof(s_new_key));

        ImGui::PushFont(fntSm); ImGui::TextColored({0.40f,0.40f,0.55f,1.f},"API SECRET (encrypted, never shown again)"); ImGui::PopFont();
        ImGui::SetNextItemWidth(-1);
        ImGui::InputText("##ns", s_new_sec, sizeof(s_new_sec), ImGuiInputTextFlags_Password);

        ImGui::Spacing();
        ImGui::PushStyleColor(ImGuiCol_Button,{0.06f,0.35f,0.12f,1.f});
        ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{0.08f,0.50f,0.18f,1.f});
        ImGui::PushFont(fntBold);
        bool doAdd = ImGui::Button("  SAVE KEY  ",{-1,32});
        ImGui::PopFont();
        ImGui::PopStyleColor(2);

        if(doAdd){
            if(strlen(s_new_name)==0||strlen(s_new_key)==0||strlen(s_new_sec)==0){
                snprintf(s_status,sizeof(s_status),"Fill all fields (name, key, secret)");
            } else {
                VaultError e=svc_add(s_exch,s_new_name,s_new_key,s_new_sec);
                SecureZeroMemory(s_new_name,sizeof(s_new_name));
                SecureZeroMemory(s_new_key, sizeof(s_new_key));
                SecureZeroMemory(s_new_sec, sizeof(s_new_sec));
                s_show_add = false;
                if(e==VAULT_OK){
                    snprintf(s_status,sizeof(s_status),"Key saved and encrypted.");
                    Refresh();
                } else {
                    snprintf(s_status,sizeof(s_status),"Error: %s", vault_error_str(e));
                }
            }
        }
    }

    // ── Footer ───────────────────────────────────────────────
    ImGui::SetCursorPosY(monH-30.f);
    ImGui::PushFont(fntSm);
    if(ImGui::Button("Refresh",{70,22})) Refresh();
    ImGui::SameLine(0,10);
    ImGui::TextColored({0.22f,0.22f,0.38f,1.f},
        "vault.dat @ %%APPDATA%%\\OmnibusSidebar  |  DPAPI encrypted");
    ImGui::PopFont();

    ImGui::End();
}

// ─── Main ────────────────────────────────────────────────────
int main(void)
{
    // Single instance
    HANDLE hMutex = CreateMutexA(NULL,TRUE,MUTEX_NAME);
    if(GetLastError()==ERROR_ALREADY_EXISTS){
        MessageBoxA(NULL,"VaultManager is already running!","OmniBus Vault",MB_ICONWARNING);
        if(hMutex) CloseHandle(hMutex);
        return 1;
    }

    SetConfigFlags(FLAG_MSAA_4X_HINT);
    InitWindow(580, 820, "OmniBus Vault Manager");
    SetTargetFPS(60);

    // Use Begin/End init so we can disable ini BEFORE fonts are built.
    // rlImGuiSetup() would do Begin+StyleDark+End, but that reads imgui.ini
    // which may contain stale font paths from OmnibusSidebar's main.cpp.
    rlImGuiBeginInitImGui();
    {
        ImGuiIO& io = ImGui::GetIO();
        io.IniFilename = nullptr;   // never read/write imgui.ini
        ImGui::StyleColorsDark();
    }
    rlImGuiEndInitImGui();

    ImGuiIO& io = ImGui::GetIO();

    // Use ImGui built-in font only — no TTF files needed
    fntReg  = io.FontDefault;
    fntBold = io.FontDefault;
    fntSm   = io.FontDefault;

    ImGui::StyleColorsDark();
    ImGuiStyle& S = ImGui::GetStyle();
    S.WindowRounding=12.f; S.FrameRounding=8.f; S.WindowPadding={12,10};
    auto C=[](float r,float g,float b,float a=1.f)->ImVec4{return{r,g,b,a};};
    S.Colors[ImGuiCol_WindowBg]  = C(0.05f,0.06f,0.09f,1.f);
    S.Colors[ImGuiCol_ChildBg]   = C(0.04f,0.04f,0.07f,1.f);
    S.Colors[ImGuiCol_FrameBg]   = C(0.09f,0.11f,0.16f,1.f);
    S.Colors[ImGuiCol_Button]    = C(0.11f,0.13f,0.19f,1.f);
    S.Colors[ImGuiCol_Separator] = C(0.12f,0.14f,0.22f,1.f);

    Refresh();

    float monW = (float)GetScreenWidth();
    float monH = (float)GetScreenHeight();

    while(!WindowShouldClose())
    {
        s_statusTimer += GetFrameTime();

        BeginDrawing();
        ClearBackground({7,8,12,255});

        rlImGuiBegin();
        DrawUI(monW, monH);
        rlImGuiEnd();

        EndDrawing();
    }

    rlImGuiShutdown();
    CloseWindow();
    CloseHandle(hMutex);
    return 0;
}
