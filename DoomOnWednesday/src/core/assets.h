// Read-only game data files (shipped in the APK's assets/ folder; read from disk on desktop).
#pragma once
#include <vector>
#include <string>
#include <cstdint>
namespace dow {
using AssetReader = bool (*)(const std::string& name, std::vector<uint8_t>& out);
void setAssetReader(AssetReader r);
bool readAsset(const std::string& name, std::vector<uint8_t>& out);
}
