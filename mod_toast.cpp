// ============================================================
//  mod_toast.cpp
// ============================================================
#include "mod_toast.h"
#include "app_state.h"
#include <string>
#include <deque>
#include <mutex>
#include <math.h>

struct Toast {
    std::string msg;
    ImVec4      col;
    float       life;
    float       total;
};

static std::deque<Toast> g_toasts;
static std::mutex        g_toast_mtx;

void PushToast(const char* msg, ImVec4 col, float dur)
{
    std::lock_guard<std::mutex> lk(g_toast_mtx);
    if(g_toasts.size()>=5) g_toasts.pop_front();
    Toast t; t.msg=msg; t.col=col; t.life=dur; t.total=dur;
    g_toasts.push_back(t);
}

void DrawToasts(float dt, int screenW, int screenH)
{
    std::lock_guard<std::mutex> lk(g_toast_mtx);
    const float W=280.f, H=44.f, PAD=8.f;
    float yBase = (float)screenH - 30.f;

    for(int i=(int)g_toasts.size()-1; i>=0; i--)
    {
        Toast& t = g_toasts[i];
        t.life -= dt;
        if(t.life<=0){ g_toasts.erase(g_toasts.begin()+i); continue; }

        float elapsed = t.total - t.life;
        float slideProgress = (elapsed < 0.3f) ? elapsed/0.3f : 1.f;
        float alpha = (t.life < 0.4f) ? t.life/0.4f : 1.f;

        float xPos = (float)screenW - W - 8.f + (1.f-slideProgress)*(W+20.f);
        float yPos = yBase - H - PAD;
        yBase = yPos;

        ImDrawList* dl = ImGui::GetForegroundDrawList();

        dl->AddRectFilled({xPos+3,yPos+3},{xPos+W+3,yPos+H+3},
            IM_COL32(0,0,0,(int)(60*alpha)), 10.f);
        dl->AddRectFilled({xPos,yPos},{xPos+W,yPos+H},
            IM_COL32(20,23,33,(int)(alpha*245)), 10.f);
        dl->AddRectFilled({xPos,yPos},{xPos+4,yPos+H},
            IM_COL32((int)(t.col.x*255),(int)(t.col.y*255),(int)(t.col.z*255),(int)(alpha*255)),
            10.f, ImDrawFlags_RoundCornersLeft);
        dl->AddRect({xPos,yPos},{xPos+W,yPos+H},
            IM_COL32(40,45,70,(int)(alpha*200)), 10.f, 0, 1.f);

        float prog = t.life/t.total;
        dl->AddRectFilled({xPos+4,yPos+H-3},{xPos+4+(W-4)*prog,yPos+H},
            IM_COL32((int)(t.col.x*255),(int)(t.col.y*255),(int)(t.col.z*255),(int)(alpha*180)),
            0.f, ImDrawFlags_RoundCornersBottom);

        dl->AddText(fntMedium, 13.f, {xPos+14, yPos+H/2.f-7.f},
            IM_COL32(230,230,240,(int)(alpha*255)), t.msg.c_str());
    }
}
