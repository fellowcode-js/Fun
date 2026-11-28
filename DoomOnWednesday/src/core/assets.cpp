#include "assets.h"
#include <cstdio>
#include <cstdlib>
namespace dow {
static bool fileReader(const std::string& name, std::vector<uint8_t>& out) {
  const char* dir = std::getenv("DOW_ASSETS"); std::string p = std::string(dir ? dir : "android/app/src/main/assets") + "/" + name;
  FILE* f = std::fopen(p.c_str(), "rb"); if (!f) return false;
  std::fseek(f, 0, SEEK_END); long n = std::ftell(f); std::fseek(f, 0, SEEK_SET); out.resize((size_t)n);
  bool ok = std::fread(out.data(), 1, (size_t)n, f) == (size_t)n; std::fclose(f); return ok;
}
static AssetReader gReader = fileReader;
void setAssetReader(AssetReader r) { gReader = r ? r : fileReader; }
bool readAsset(const std::string& name, std::vector<uint8_t>& out) { return gReader(name, out); }
}
