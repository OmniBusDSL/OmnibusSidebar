// ============================================================
//  mod_wallet.cpp  —  WALLET tab
//  Balance live + TX history + Send via JSON-RPC 2.0 (HTTP direct)
//  Conectat la omnibus-node.exe pe http://127.0.0.1:8332
// ============================================================
#include "mod_wallet.h"
#include "mod_log.h"
#include "imgui/imgui.h"

#include <windows.h>
#include <winhttp.h>
#include <string>
#include <vector>
#include <thread>
#include <mutex>
#include <atomic>
#include <cstdio>
#include <cstring>

#pragma comment(lib, "winhttp.lib")

// ── Config ──────────────────────────────────────────────────
static const wchar_t* RPC_HOST = L"127.0.0.1";
static const INTERNET_PORT    RPC_PORT = 8332;

// ── Structuri date ──────────────────────────────────────────
struct TxEntry {
    char txid[80];
    char direction[12];   // "sent" / "received"
    char counterparty[80];
    char status[16];      // "confirmed" / "pending"
    double amount;
    int blockHeight;
};

struct WalletState {
    double   balance    = 0.0;
    int      tx_count   = 0;
    int      node_height= 0;
    char     address[120] = "";
    char     error[256]   = "";
    bool     node_ok    = false;
    std::vector<TxEntry> history;
};

// ── State global ────────────────────────────────────────────
static WalletState       g_wallet;
static std::mutex        g_walletMtx;
static std::atomic<bool> g_fetching(false);
static std::atomic<bool> g_sending(false);
static char              g_sendResult[512] = "";
static std::mutex        g_sendMtx;

// ── UI state ────────────────────────────────────────────────
static char  g_toAddr[120]  = "";
static char  g_toAmount[24] = "1.0";
static float g_lastFetch    = -999.f;
static float g_fetchInterval= 5.f;
static bool  g_autoRefresh  = true;

// ── WinHTTP POST helper ─────────────────────────────────────
// Trimite un JSON-RPC 2.0 request si returneaza body-ul raspunsului
static std::string RpcPost(const std::string& body)
{
    std::string result;

    HINTERNET hSession = WinHttpOpen(
        L"OmnibusSidebar/1.0",
        WINHTTP_ACCESS_TYPE_NO_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession) return "";

    HINTERNET hConnect = WinHttpConnect(hSession, RPC_HOST, RPC_PORT, 0);
    if (!hConnect) { WinHttpCloseHandle(hSession); return ""; }

    HINTERNET hRequest = WinHttpOpenRequest(
        hConnect, L"POST", L"/",
        NULL, WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
    if (!hRequest) {
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return "";
    }

    // Timeout 3s
    WinHttpSetTimeouts(hRequest, 3000, 3000, 3000, 3000);

    LPCWSTR hdrs = L"Content-Type: application/json\r\n";
    BOOL ok = WinHttpSendRequest(
        hRequest, hdrs, (DWORD)-1L,
        (LPVOID)body.c_str(), (DWORD)body.size(),
        (DWORD)body.size(), 0);

    if (ok) ok = WinHttpReceiveResponse(hRequest, NULL);

    if (ok) {
        DWORD avail = 0;
        while (WinHttpQueryDataAvailable(hRequest, &avail) && avail > 0) {
            std::string chunk(avail, '\0');
            DWORD read = 0;
            WinHttpReadData(hRequest, &chunk[0], avail, &read);
            chunk.resize(read);
            result += chunk;
        }
    }

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);
    return result;
}

// ── Simple JSON extract ─────────────────────────────────────
static std::string JsonGet(const std::string& json, const std::string& key)
{
    std::string search = "\"" + key + "\": ";
    size_t pos = json.find(search);
    if (pos == std::string::npos) {
        search = "\"" + key + "\":";
        pos = json.find(search);
    }
    if (pos == std::string::npos) return "";

    pos += search.size();
    while (pos < json.size() && json[pos] == ' ') pos++;

    if (json[pos] == '"') {
        pos++;
        size_t end = json.find('"', pos);
        if (end == std::string::npos) return "";
        return json.substr(pos, end - pos);
    } else {
        size_t end = pos;
        while (end < json.size() &&
               json[end] != ',' && json[end] != '}' && json[end] != '\n')
            end++;
        return json.substr(pos, end - pos);
    }
}

// ── Fetch balance in background thread ──────────────────────
static void FetchWalletAsync()
{
    if (g_fetching.exchange(true)) return;

    std::thread([](){
        // getbalance → {"address", "balance", "balanceOMNI", "confirmed",
        //               "unconfirmed", "txCount", "nodeHeight"}
        std::string req =
            "{\"jsonrpc\":\"2.0\",\"id\":1,"
            "\"method\":\"getbalance\",\"params\":[]}";

        std::string resp = RpcPost(req);

        WalletState ws;

        if (resp.empty()) {
            ws.node_ok = false;
            strncpy_s(ws.error, "Node offline (http://127.0.0.1:8332)", sizeof(ws.error)-1);
        } else {
            // Extrage result
            std::string result_block;
            size_t rp = resp.find("\"result\":");
            if (rp != std::string::npos) {
                size_t rb = resp.find('{', rp);
                if (rb != std::string::npos) {
                    size_t re = resp.find('}', rb);
                    if (re != std::string::npos)
                        result_block = resp.substr(rb, re - rb + 1);
                }
            }

            std::string addr = JsonGet(result_block, "address");
            strncpy_s(ws.address, addr.c_str(), sizeof(ws.address)-1);

            std::string bal = JsonGet(result_block, "balanceOMNI");
            ws.balance = bal.empty() ? 0.0 : std::stod(bal);

            std::string txc = JsonGet(result_block, "txCount");
            ws.tx_count = txc.empty() ? 0 : std::stoi(txc);

            std::string nh = JsonGet(result_block, "nodeHeight");
            ws.node_height = nh.empty() ? 0 : std::stoi(nh);

            ws.node_ok = true;
        }

        {
            std::lock_guard<std::mutex> lk(g_walletMtx);
            g_wallet = ws;
        }
        g_fetching = false;
    }).detach();
}

// ── Send TX in background thread ────────────────────────────
static void SendTxAsync(const char* to_addr, const char* amount_omni_str)
{
    if (g_sending.exchange(true)) return;

    std::string to  = to_addr;
    std::string amt = amount_omni_str;

    std::thread([to, amt](){
        // Converteste OMNI → SAT (1 OMNI = 1e9 SAT)
        double omni_val = 1.0;
        try { omni_val = std::stod(amt); } catch (...) {}
        long long sat = (long long)(omni_val * 1e9);

        // sendtransaction(to, amount_sat)
        char req[512];
        snprintf(req, sizeof(req),
            "{\"jsonrpc\":\"2.0\",\"id\":2,"
            "\"method\":\"sendtransaction\","
            "\"params\":[\"%s\",%lld]}",
            to.c_str(), sat);

        std::string resp = RpcPost(std::string(req));

        {
            std::lock_guard<std::mutex> lk(g_sendMtx);

            if (resp.empty()) {
                snprintf(g_sendResult, sizeof(g_sendResult),
                    "EROARE: node offline");
            } else {
                // Check "error" key first
                size_t ep = resp.find("\"error\":");
                bool has_err = false;
                if (ep != std::string::npos) {
                    // Check it's not null
                    size_t vp = ep + 8;
                    while (vp < resp.size() && resp[vp] == ' ') vp++;
                    if (vp < resp.size() && resp[vp] != 'n')
                        has_err = true;
                }

                if (!has_err) {
                    std::string txid = JsonGet(resp, "txid");
                    snprintf(g_sendResult, sizeof(g_sendResult),
                        "OK  txid: %.28s", txid.c_str());
                } else {
                    std::string errmsg = JsonGet(resp, "message");
                    snprintf(g_sendResult, sizeof(g_sendResult),
                        "EROARE: %s", errmsg.c_str());
                }
            }
        }

        g_sending = false;
        g_lastFetch = -999.f;  // trigger re-fetch
    }).detach();
}

// ── Draw ────────────────────────────────────────────────────
void DrawWalletTab()
{
    float now = (float)ImGui::GetTime();
    if (g_autoRefresh && (now - g_lastFetch) > g_fetchInterval && !g_fetching) {
        g_lastFetch = now;
        FetchWalletAsync();
    }

    WalletState ws;
    {
        std::lock_guard<std::mutex> lk(g_walletMtx);
        ws = g_wallet;
    }

    ImGui::Spacing();

    // ── Status nod ───────────────────────────────────────────
    {
        ImVec4 nodeCol = ws.node_ok
            ? ImVec4(0.25f, 0.85f, 0.45f, 1.f)
            : ImVec4(0.85f, 0.25f, 0.25f, 1.f);
        const char* nodeStr = ws.node_ok ? "NODE OK" : "NODE OFF";
        ImGui::TextColored(nodeCol, "%s", nodeStr);
        ImGui::SameLine();
        ImGui::PushFont(fntSmall);
        ImGui::TextColored({0.4f,0.4f,0.6f,1.f}, "  block %d", ws.node_height);
        ImGui::PopFont();
    }

    ImGui::Spacing();

    // Balance mare
    ImGui::PushFont(fntLarge);
    ImGui::TextColored({0.95f,0.82f,0.20f,1.f}, "%.4f OMNI", ws.balance);
    ImGui::PopFont();

    ImGui::PushFont(fntSmall);
    if (ws.address[0]) {
        ImGui::TextColored({0.4f,0.4f,0.6f,1.f}, "%s", ws.address);
    }
    ImGui::TextColored({0.4f,0.4f,0.6f,1.f}, "%d tranzactii", ws.tx_count);
    ImGui::PopFont();

    if (ws.error[0] && !ws.node_ok) {
        ImGui::PushFont(fntSmall);
        ImGui::TextColored({0.9f,0.3f,0.3f,1.f}, "! %s", ws.error);
        ImGui::PopFont();
    }

    ImGui::Spacing();

    // ── Buton Refresh ────────────────────────────────────────
    bool busy = g_fetching.load();
    if (busy) ImGui::BeginDisabled();
    if (ImGui::Button(busy ? "Se incarca..." : "  Refresh  ")) {
        g_lastFetch = now;
        FetchWalletAsync();
    }
    if (busy) ImGui::EndDisabled();
    ImGui::SameLine();
    ImGui::Checkbox("Auto 5s", &g_autoRefresh);

    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();

    // ── Send ─────────────────────────────────────────────────
    ImGui::PushFont(fntMedium);
    ImGui::TextColored({0.55f,0.55f,0.85f,1.f}, "TRIMITE OMNI");
    ImGui::PopFont();

    ImGui::Spacing();
    ImGui::SetNextItemWidth(-1);
    ImGui::InputText("##toaddr", g_toAddr, sizeof(g_toAddr));
    ImGui::PushFont(fntSmall);
    ImGui::TextColored({0.35f,0.35f,0.55f,1.f}, "adresa destinatie (ob_...)");
    ImGui::PopFont();

    ImGui::Spacing();
    ImGui::SetNextItemWidth(120.f);
    ImGui::InputText("##amt", g_toAmount, sizeof(g_toAmount));
    ImGui::SameLine();
    ImGui::TextUnformatted("OMNI");

    ImGui::Spacing();

    bool sendBusy = g_sending.load();
    if (sendBusy) ImGui::BeginDisabled();
    bool doSend = ImGui::Button(sendBusy ? "Se trimite..." : "  SEND  ");
    if (sendBusy) ImGui::EndDisabled();

    if (doSend && g_toAddr[0] && g_toAmount[0]) {
        {
            std::lock_guard<std::mutex> lk(g_sendMtx);
            g_sendResult[0] = '\0';
        }
        SendTxAsync(g_toAddr, g_toAmount);
        Log("WALLET: TX trimis...", {0.55f, 0.85f, 0.55f, 1.f});
    }

    {
        std::lock_guard<std::mutex> lk(g_sendMtx);
        if (g_sendResult[0]) {
            bool ok = (strncmp(g_sendResult, "OK", 2) == 0);
            ImGui::PushFont(fntSmall);
            ImGui::TextColored(
                ok ? ImVec4{0.2f,0.9f,0.4f,1.f} : ImVec4{0.9f,0.3f,0.3f,1.f},
                "%s", g_sendResult);
            ImGui::PopFont();
        }
    }

    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();

    // ── History TX ───────────────────────────────────────────
    ImGui::PushFont(fntMedium);
    ImGui::TextColored({0.55f,0.55f,0.85f,1.f}, "TRANZACTII RECENTE");
    ImGui::PopFont();

    ImGui::Spacing();

    {
        std::lock_guard<std::mutex> lk(g_walletMtx);
        if (g_wallet.history.empty()) {
            ImGui::PushFont(fntSmall);
            ImGui::TextColored({0.35f,0.35f,0.55f,1.f}, "Nicio tranzactie.");
            ImGui::PopFont();
        } else {
            ImGui::PushFont(fntSmall);
            ImGui::TextColored({0.4f,0.4f,0.6f,1.f},
                "%-10s %-8s %-8s  %s", "STATUS", "DIR", "OMNI", "TXID");
            ImGui::Separator();

            float listH = ImGui::GetContentRegionAvail().y - 4.f;
            ImGui::BeginChild("##txlist", {0, listH}, false);

            for (auto& tx : g_wallet.history) {
                ImVec4 dirCol = (strncmp(tx.direction, "sent", 4) == 0)
                    ? ImVec4{0.9f, 0.4f, 0.4f, 1.f}
                    : ImVec4{0.3f, 0.85f, 0.5f, 1.f};
                ImVec4 stCol = (strncmp(tx.status, "confirmed", 9) == 0)
                    ? ImVec4{0.25f, 0.85f, 0.45f, 1.f}
                    : ImVec4{0.85f, 0.75f, 0.15f, 1.f};

                ImGui::TextColored(stCol, "%-10s", tx.status);
                ImGui::SameLine();
                ImGui::TextColored(dirCol, "%-8s", tx.direction);
                ImGui::SameLine();
                ImGui::TextColored({0.95f,0.82f,0.20f,1.f}, "%-8.4f", tx.amount);
                ImGui::SameLine();
                if (tx.blockHeight >= 0)
                    ImGui::TextColored({0.4f,0.4f,0.6f,1.f},
                        "blk=%-5d  %.28s", tx.blockHeight, tx.txid);
                else
                    ImGui::TextColored({0.5f,0.5f,0.3f,1.f},
                        "pending  %.28s", tx.txid);
            }

            ImGui::EndChild();
            ImGui::PopFont();
        }
    }
}
