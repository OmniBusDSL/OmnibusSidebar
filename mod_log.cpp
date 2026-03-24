// ============================================================
//  mod_log.cpp
// ============================================================
#include "mod_log.h"
#include "app_state.h"
#include <string.h>
#include <mutex>

#define LOG_MAX 256
struct LogLine { char txt[160]; ImVec4 col; };

static LogLine    g_log[LOG_MAX];
static int        g_logN = 0;
static std::mutex g_logMtx;
static bool       g_logScrollNeeded = false;

void Log(const char* msg, ImVec4 col)
{
    std::lock_guard<std::mutex> lk(g_logMtx);
    if(g_logN < LOG_MAX){
        strncpy_s(g_log[g_logN].txt, msg, 159);
        g_log[g_logN].col = col;
        g_logN++;
    } else {
        memmove(g_log, g_log+1, sizeof(LogLine)*(LOG_MAX-1));
        strncpy_s(g_log[LOG_MAX-1].txt, msg, 159);
        g_log[LOG_MAX-1].col = col;
    }
    g_logScrollNeeded = true;
}

void DrawLogTab()
{
    ImGui::BeginChild("##lsc", {0,0}, false);
    {
        std::lock_guard<std::mutex> lk(g_logMtx);
        for(int i=0; i<g_logN; i++){
            ImGui::PushFont(fntSmall);
            ImGui::TextColored(g_log[i].col, "%s", g_log[i].txt);
            ImGui::PopFont();
        }
    }
    if(g_logScrollNeeded){ ImGui::SetScrollHereY(1.f); g_logScrollNeeded=false; }
    ImGui::EndChild();
}
