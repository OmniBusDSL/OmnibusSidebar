# ─────────────────────────────────────────────────────────────────
#  OmnibusSidebar  –  Raylib + Dear ImGui  +  WinINet (built-in)
#  Requires: MinGW-w64 (g++), windres
#  Raylib via MSYS2:  pacman -S mingw-w64-x86_64-raylib
# ─────────────────────────────────────────────────────────────────

TARGET   = OmnibusSidebar.exe
CXX      = g++
WINDRES  = windres

IMGUI_DIR  = ./imgui
RAYLIB_DIR = ./raylib_pkg/raylib-5.0_win64_mingw-w64

CXXFLAGS = -std=c++17 -O2 \
           -I. \
           -I$(IMGUI_DIR) \
           -I$(RAYLIB_DIR)/include \
           -DWIN32_LEAN_AND_MEAN

# WinINet  = Windows built-in HTTP  (no libcurl needed)
# -mwindows = no console window at startup
LDFLAGS  = -L$(RAYLIB_DIR)/lib \
           -lraylib \
           -lopengl32 \
           -lgdi32    \
           -lwinmm    \
           -lwininet  \
           -lwinhttp  \
           -mwindows

SOURCES  = main.cpp \
           fetch.cpp \
           win_input_region.cpp \
           mod_toast.cpp \
           mod_log.cpp \
           mod_prices.cpp \
           mod_trade.cpp \
           mod_wallet.cpp \
           mod_charts.cpp \
           rlImGui.cpp \
           $(IMGUI_DIR)/imgui.cpp \
           $(IMGUI_DIR)/imgui_draw.cpp \
           $(IMGUI_DIR)/imgui_widgets.cpp \
           $(IMGUI_DIR)/imgui_tables.cpp

all: resource.o
	$(CXX) $(SOURCES) resource.o -o $(TARGET) $(CXXFLAGS) $(LDFLAGS)
	@echo.
	@echo  =============================================
	@echo    OK:  $(TARGET)
	@echo  =============================================

resource.o: resource.rc
	$(WINDRES) resource.rc -O coff -o resource.o

clean:
	del /Q $(TARGET) resource.o 2>nul || true

.PHONY: all clean
