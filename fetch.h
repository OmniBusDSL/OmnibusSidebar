// ============================================================
//  fetch.h  —  HTTP + JSON + background fetch thread
// ============================================================
#pragma once
#include <string>

std::string HttpGet(const char* host, const char* path);
std::string Jx(const std::string& json, const char* key);
void        NowStr(char* buf, int sz);
void        FetchLoop();
