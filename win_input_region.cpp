// win_input_region.cpp
// Fara raylib.h — doar WinAPI pur
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "win_input_region.h"

// Gaseste fereastra aplicatiei dupa titlu
static HWND FindAppWindow()
{
    return FindWindowA(nullptr, "OmnibusSidebar");
}

void UpdateInputRegion(bool chartOpen, int monW, int monH, int sidebarW)
{
    HWND hwnd = FindAppWindow();
    if(!hwnd) return;

    HRGN rgn;
    if(chartOpen){
        // Toata fereastra primeste input
        rgn = CreateRectRgn(0, 0, monW, monH);
    } else {
        // Doar zona sidebar (dreapta)
        rgn = CreateRectRgn(monW - sidebarW, 0, monW, monH);
    }
    SetWindowRgn(hwnd, rgn, FALSE);
}
