// Strata: procedural sound-effect synthesis engine. Public API.
#pragma once
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

#include "json.hpp"

namespace strata {

// ---------- schema ----------
struct Param {
    std::string key, label, unit;
    double min = 0, max = 1, def = 0;
    bool log = false, isInt = false;
    bool isEnum = false, numericEnum = false;
    std::vector<std::string> options;
    std::string defStr;
};
struct Group {
    std::string name;
    std::vector<Param> params;
};
struct TypeDef {
    std::string id, label, about;
    std::vector<Param> params;
    std::unordered_map<std::string, double> defs;
};
const std::vector<TypeDef>& types();
const TypeDef* findType(const std::string& id);
const std::vector<Group>& commonGroups();
const std::vector<Group>& masterGroups();
const std::vector<std::pair<std::string, std::string>>& categories();
std::string schemaJson();  // everything a UI needs to build its controls
std::string aiPrompt();    // brief that lets any AI write recipes

// ---------- recipe ----------
struct Bag {
    std::unordered_map<std::string, double> n;
    std::unordered_map<std::string, std::string> s;
    double N(const char* k) const { auto it = n.find(k); return it == n.end() ? 0.0 : it->second; }
    const std::string& S(const char* k) const {
        static const std::string empty;
        auto it = s.find(k);
        return it == s.end() ? empty : it->second;
    }
};
struct Layer : Bag {
    std::string type, name;
    bool mute = false, solo = false;
};
struct Recipe {
    uint32_t seed = 1;
    Bag master;
    std::vector<Layer> layers;
    std::string category;
};
Recipe normRecipe(const Json& raw);
Json recipeToJson(const Recipe& r);
std::string recipeToString(const Recipe& r, int indent = 1);
Layer defaultLayer(const std::string& type);

// ---------- rendering ----------
struct RenderOptions {
    std::vector<int> only;   // render just these layer indexes (stems)
    double minLength = 0;    // pad output to at least this many seconds
    bool raw = false;        // skip peak normalize (stems)
    int threads = 0;         // 0 = automatic
};
struct Audio {
    int sr = 48000;
    std::vector<float> L, R;
    double peak = 0, rms = 0, duration = 0;
    double renderMs = 0;
};
Audio render(const Recipe& r, const RenderOptions& opt = {});

// ---------- generation ----------
struct GenOptions {
    std::string category = "any";
    int64_t seed = -1;  // negative = random
    double size = -1, energy = -1, hardness = -1, space = -1, chaos = -1;  // negative = random
};
Recipe generate(const GenOptions& o);
Recipe mutate(const Recipe& r, double amount, int64_t seed = -1);

// ---------- io ----------
std::vector<uint8_t> encodeWav(const std::vector<float>& L, const std::vector<float>& R, int sr, int bits);
struct ZipEntry { std::string name; std::vector<uint8_t> data; };
std::vector<uint8_t> zipStore(const std::vector<ZipEntry>& files);
// Waveform min/max pairs for `width` columns: [min0,max0,min1,max1,...]
std::vector<float> envelope(const Audio& a, int width);
// Spectrogram as ARGB pixels (cols x rows), low frequencies at the bottom.
std::vector<uint32_t> spectrogram(const Audio& a, int cols, int rows);

}  // namespace strata
