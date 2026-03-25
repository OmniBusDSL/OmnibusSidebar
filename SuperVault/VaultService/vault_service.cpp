// ============================================================
//  vault_service.cpp  —  VaaS Named Pipe server v2
//
//  Single-instance: uses a named mutex to prevent multiple copies.
//  Pipe: \\.\pipe\OmnibusVault
//
//  Protocol:
//    Request:  [opcode:1][exchange:1][slot:2][payload_len:2][payload]
//    Response: [error:1][payload_len:2][payload]
//
//  GET_SECRET (0x4A) is NOT served over the pipe — security boundary.
// ============================================================
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string>
#include <thread>
#include <atomic>
#include <cstring>

#include "../VaultCore/vault_core.h"

#define PIPE_NAME    "\\\\.\\pipe\\OmnibusVault"
#define MUTEX_NAME   "Global\\OmnibusVaultService"
#define PIPE_BUFSIZE  8192

static std::atomic<bool> g_running(true);

// ─── Vault data path ─────────────────────────────────────────
static std::string GetVaultDataPath()
{
    char appdata[MAX_PATH] = {};
    GetEnvironmentVariableA("APPDATA", appdata, sizeof(appdata));
    return std::string(appdata) + "\\OmnibusSidebar";
}

// ─── Protocol helpers ────────────────────────────────────────
static void PU8(std::string& b, uint8_t v)  { b.push_back((char)v); }
static void PU16(std::string& b, uint16_t v){ b.push_back(v&0xFF); b.push_back((v>>8)&0xFF); }
static void PStr(std::string& b, const char* s, size_t len){ PU16(b,(uint16_t)len); b.append(s,len); }

static bool GU8(const char* d, size_t len, size_t& p, uint8_t& v){
    if(p>=len) return false; v=(uint8_t)d[p++]; return true; }
static bool GU16(const char* d, size_t len, size_t& p, uint16_t& v){
    if(p+2>len) return false;
    v=(uint8_t)d[p]|((uint8_t)d[p+1]<<8); p+=2; return true; }
static bool GStrN(const char* d, size_t len, size_t& p, char* out, size_t max){
    uint16_t sl; if(!GU16(d,len,p,sl)) return false;
    if(p+sl>len) return false;
    size_t n=sl<max-1?sl:max-1; memcpy(out,d+p,n); out[n]=0; p+=sl; return true; }

// ─── Build response ──────────────────────────────────────────
static std::string MakeResp(VaultError err, const char* payload=nullptr, size_t plen=0)
{
    std::string r;
    PU8(r,(uint8_t)err);
    PU16(r,(uint16_t)(payload?plen:0));
    if(payload&&plen) r.append(payload,plen);
    return r;
}

// ─── Handle one client ───────────────────────────────────────
static void HandleClient(HANDLE pipe)
{
    char req[PIPE_BUFSIZE]; DWORD bread=0;
    if(!ReadFile(pipe,req,sizeof(req)-1,&bread,NULL)||bread==0){
        CloseHandle(pipe); return; }

    size_t p=0;
    uint8_t  opcode=0, exchange=0;
    uint16_t slot_u16=0, payload_len=0;
    GU8(req,bread,p,opcode);
    GU8(req,bread,p,exchange);
    GU16(req,bread,p,slot_u16);
    GU16(req,bread,p,payload_len);

    VaultExchange ex = (VaultExchange)(exchange < VAULT_EXCHANGE_COUNT ? exchange : 0);
    uint32_t slot = slot_u16;
    std::string resp;

    switch(opcode)
    {
    case VAULT_OP_LIST:
    {
        VaultKeyMeta list[VAULT_MAX_KEYS] = {};
        uint32_t cnt = 0;
        VaultError err = vault_core_list(ex, list, &cnt);
        // serialize: [count:4] { [name_len:2][name][key_len:2][key][slot:4][status:1] }
        std::string payload;
        payload.clear();
        uint8_t cb[4]={(uint8_t)(cnt&0xFF),0,0,0}; payload.append((char*)cb,4);
        for(uint32_t i=0;i<cnt;i++){
            PStr(payload, list[i].name,    strlen(list[i].name));
            PStr(payload, list[i].api_key, strlen(list[i].api_key));
            uint32_t si=list[i].slot_index;
            uint8_t sb[4]={(uint8_t)(si&0xFF),(uint8_t)((si>>8)&0xFF),
                           (uint8_t)((si>>16)&0xFF),(uint8_t)((si>>24)&0xFF)};
            payload.append((char*)sb,4);
            payload.push_back(list[i].status);
        }
        resp = MakeResp(err, payload.data(), payload.size());
        break;
    }
    case VAULT_OP_ADD:
    {
        char name[VAULT_NAME_MAX]={}, key[VAULT_KEY_MAX]={}, sec[VAULT_SECRET_MAX]={};
        GStrN(req,bread,p,name,sizeof(name));
        GStrN(req,bread,p,key, sizeof(key));
        GStrN(req,bread,p,sec, sizeof(sec));
        printf("[ADD] ex=%d name='%s' key_len=%d sec_len=%d\n",
            (int)ex, name, (int)strlen(key), (int)strlen(sec));
        fflush(stdout);
        uint32_t out_slot=0;
        VaultError err = vault_core_add(ex,name,key,sec,&out_slot);
        printf("[ADD] vault_core_add returned %d (%s) slot=%u\n",
            (int)err, vault_error_str(err), out_slot);
        fflush(stdout);
        SecureZeroMemory(sec,sizeof(sec));
        resp = MakeResp(err);
        break;
    }
    case VAULT_OP_DELETE:
        resp = MakeResp(vault_core_delete(ex, slot));
        break;

    case VAULT_OP_SET_STATUS:
    {
        // payload byte 0 = new status (0=FREE, 1=PAID, 2=NOTPAID)
        uint8_t new_status = 0;
        GU8(req, bread, p, new_status);
        printf("[SETSTATUS] ex=%d slot=%u status=%u (%s)\n",
            (int)ex, slot, new_status, vault_key_status_str(new_status));
        fflush(stdout);
        resp = MakeResp(vault_core_set_status(ex, slot, new_status));
        break;
    }
    case VAULT_OP_COUNT:
    {
        uint32_t c = vault_core_count(ex);
        uint8_t cb[4]={(uint8_t)(c&0xFF),(uint8_t)((c>>8)&0xFF),
                       (uint8_t)((c>>16)&0xFF),(uint8_t)((c>>24)&0xFF)};
        std::string payload((char*)cb,4);
        resp = MakeResp(VAULT_OK, payload.data(), 4);
        break;
    }
    case VAULT_OP_LOCK:
        vault_core_lock();
        resp = MakeResp(VAULT_OK);
        break;

    case VAULT_OP_GET_SECRET:
        // Deliberately refused over pipe
        resp = MakeResp(VAULT_ERR_INVALID);
        break;

    default:
        resp = MakeResp(VAULT_ERR_INVALID);
        break;
    }

    DWORD written=0;
    WriteFile(pipe, resp.data(), (DWORD)resp.size(), &written, NULL);
    FlushFileBuffers(pipe);
    DisconnectNamedPipe(pipe);
    CloseHandle(pipe);
}

// ─── Server loop ─────────────────────────────────────────────
static void ServerLoop()
{
    printf("[VaultService] Listening on %s\n", PIPE_NAME);
    printf("[VaultService] Send Ctrl+C to stop.\n\n");

    while(g_running.load())
    {
        HANDLE pipe = CreateNamedPipeA(
            PIPE_NAME,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_BYTE|PIPE_READMODE_BYTE|PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES,
            PIPE_BUFSIZE, PIPE_BUFSIZE, 0, NULL);

        if(pipe==INVALID_HANDLE_VALUE){ Sleep(1000); continue; }

        if(ConnectNamedPipe(pipe,NULL)||GetLastError()==ERROR_PIPE_CONNECTED)
            std::thread(HandleClient,pipe).detach();
        else
            CloseHandle(pipe);
    }
}

// ─── Main ────────────────────────────────────────────────────
int main(void)
{
    // ── Single instance guard ─────────────────────────────────
    HANDLE hMutex = CreateMutexA(NULL, TRUE, MUTEX_NAME);
    if(GetLastError() == ERROR_ALREADY_EXISTS){
        printf("[VaultService] Already running! Only one instance allowed.\n");
        if(hMutex) CloseHandle(hMutex);
        return 1;
    }

    printf("\xC9"); for(int i=0;i<38;i++) printf("\xCD"); printf("\xBB\n");
    printf("\xBA  OmniBus Vault Service  v2.0         \xBA\n");
    printf("\xBA  Pipe: \\\\.\\pipe\\OmnibusVault         \xBA\n");
    printf("\xC8"); for(int i=0;i<38;i++) printf("\xCD"); printf("\xBC\n\n");

    std::string vaultPath = GetVaultDataPath();
    printf("[VaultService] Vault: %s\n", vaultPath.c_str());

    VaultError err = vault_core_init(vaultPath.c_str());
    if(err != VAULT_OK){
        printf("[VaultService] FATAL: %s\n", vault_error_str(err));
        CloseHandle(hMutex);
        return 1;
    }
    printf("[VaultService] Vault OK.\n");

    // ── Count stored entries ─────────────────────────────────
    // Exchange 0 (LCX) holds both API keys and crypto wallets (name prefix "WALLET:")
    // We split them for display.
    {
        VaultKeyMeta list0[VAULT_MAX_KEYS] = {};
        uint32_t cnt0 = 0;
        vault_core_list(VAULT_EXCHANGE_LCX, list0, &cnt0);

        int lcx_keys = 0, wallets = 0;
        for(uint32_t i = 0; i < cnt0; i++){
            if(strncmp(list0[i].name, "WALLET:", 7) == 0)
                wallets++;
            else
                lcx_keys++;
        }
        printf("[VaultService] LCX: %d key(s)\n", lcx_keys);

        const char* exch_names[] = {"Kraken","Coinbase"};
        for(int e = 1; e < VAULT_EXCHANGE_COUNT; e++)
            printf("[VaultService] %s: %d key(s)\n", exch_names[e-1], vault_core_count((VaultExchange)e));

        printf("[VaultService] Crypto Wallets: %d wallet(s)\n", wallets);
    }

    ServerLoop();

    vault_core_lock();
    CloseHandle(hMutex);
    printf("\n[VaultService] Locked and stopped.\n");
    return 0;
}
