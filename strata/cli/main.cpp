// Desktop command line for Strata. Used for testing the engine and batch rendering.
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>

#include "../engine/strata.hpp"

using namespace strata;

static std::string readFile(const char* p) {
    std::ifstream f(p, std::ios::binary);
    if (!f) { fprintf(stderr, "cannot open %s\n", p); exit(2); }
    std::stringstream ss; ss << f.rdbuf();
    return ss.str();
}
static void writeFile(const char* p, const void* d, size_t n) {
    std::ofstream f(p, std::ios::binary);
    f.write((const char*)d, (std::streamsize)n);
}
static void writeText(const char* p, const std::string& s) { writeFile(p, s.data(), s.size()); }

static Recipe loadRecipe(const char* p) { return normRecipe(Json::parse(readFile(p))); }

static double opt(int argc, char** argv, const char* name, double def) {
    for (int i = 1; i + 1 < argc; i++) if (!strcmp(argv[i], name)) return atof(argv[i + 1]);
    return def;
}
static const char* optS(int argc, char** argv, const char* name, const char* def) {
    for (int i = 1; i + 1 < argc; i++) if (!strcmp(argv[i], name)) return argv[i + 1];
    return def;
}

// Writes a PPM analyzer image: waveform on top, spectrogram below.
static void writeAnalyzer(const Audio& a, const char* path, int W = 1040, int H = 460) {
    int wh = (int)(H * 0.34), sh = H - wh;
    std::vector<uint8_t> px((size_t)W * H * 3, 0);
    auto put = [&](int x, int y, uint8_t r, uint8_t g, uint8_t b) { if (x >= 0 && x < W && y >= 0 && y < H) { size_t o = ((size_t)y * W + x) * 3; px[o] = r; px[o + 1] = g; px[o + 2] = b; } };
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) put(x, y, 10, 14, 17);
    for (int x = 0; x < W; x++) put(x, wh / 2, 28, 38, 45);
    std::vector<float> env = envelope(a, W);
    for (int x = 0; x < W; x++) {
        int y1 = (int)((0.5 - env[x * 2 + 1] * 0.48) * wh), y2 = (int)((0.5 - env[x * 2] * 0.48) * wh);
        if (y2 <= y1) y2 = y1 + 1;
        for (int y = y1; y <= y2; y++) put(x, y, 217, 243, 239);
    }
    int cols = std::min(W, 520), rows = std::min(sh, 200);
    std::vector<uint32_t> sp = spectrogram(a, cols, rows);
    for (int y = 0; y < sh; y++) for (int x = 0; x < W; x++) {
        int sx = x * cols / W, sy = y * rows / sh;
        uint32_t c = sp[(size_t)sy * cols + sx];
        put(x, wh + y, (c >> 16) & 255, (c >> 8) & 255, c & 255);
    }
    std::string hdr = "P6\n" + std::to_string(W) + " " + std::to_string(H) + "\n255\n";
    std::ofstream f(path, std::ios::binary);
    f.write(hdr.data(), (std::streamsize)hdr.size());
    f.write((const char*)px.data(), (std::streamsize)px.size());
}

static int usage() {
    puts("strata gen <category|any> [--seed N] [--size|--energy|--hardness|--space|--chaos 0..1] -> recipe JSON on stdout\n"
         "strata render <recipe.json> <out.wav> [--bits 16|24|32]\n"
         "strata stems <recipe.json> <out.zip> [--bits 24]\n"
         "strata mutate <recipe.json> <amount> [--seed N] -> recipe JSON on stdout\n"
         "strata analyze <recipe.json> <out.ppm>\n"
         "strata schema | prompt\n"
         "strata selftest");
    return 1;
}

static int selftest() {
    int fails = 0;
    auto check = [&](bool ok, const std::string& what) { printf("%s  %s\n", ok ? "ok  " : "FAIL", what.c_str()); if (!ok) fails++; };
    double totalMs = 0;
    for (auto& c : categories()) {
        GenOptions go; go.category = c.first; go.seed = 4242;
        Recipe r = generate(go);
        Audio a = render(r);
        bool finite = true;
        for (size_t i = 0; i < a.L.size(); i++) if (!std::isfinite(a.L[i]) || !std::isfinite(a.R[i])) { finite = false; break; }
        bool audible = a.peak > 0.05 && a.rms > 1e-4;
        bool clipOk = a.peak <= 1.0001;
        Audio b = render(r);
        bool same = a.L == b.L && a.R == b.R;
        RenderOptions one; one.threads = 1;
        Audio t1 = render(r, one);
        bool threadsSame = a.L == t1.L && a.R == t1.R;
        char buf[200];
        snprintf(buf, sizeof buf, "%-10s %5.2fs %2zu layers peak %.2f rms %.3f %6.0f ms", c.first.c_str(), a.duration, r.layers.size(), a.peak, a.rms, a.renderMs);
        check(finite && audible && clipOk && same && threadsSame, buf);
        if (!finite) puts("      non-finite samples");
        if (!audible) puts("      silent or near silent");
        if (!clipOk) puts("      peak above full scale");
        if (!same) puts("      not deterministic between runs");
        if (!threadsSame) puts("      differs between 1 thread and many");
        totalMs += a.renderMs;
        // recipe survives a JSON round trip
        Recipe rt = normRecipe(Json::parse(recipeToString(r)));
        Audio c2 = render(rt);
        if (!(c2.L == a.L)) check(false, c.first + " recipe JSON round trip changed the audio");
    }
    // sample rate options, mutate, bad input
    {
        Recipe r = generate([] { GenOptions g; g.category = "impact"; g.seed = 7; return g; }());
        r.master.n["sampleRate"] = 96000;
        Audio a = render(r);
        check(a.sr == 96000 && a.peak > 0.05, "96 kHz render");
        Recipe m = mutate(r, 0.3, 5);
        Audio ma = render(m);
        check(ma.peak > 0.01 && m.seed != r.seed, "mutate produces a new audible sound");
        Recipe bad = normRecipe(Json::parse("{\"layers\":[{\"type\":\"nope\"},{\"type\":\"noise\",\"dur\":99999,\"gain\":\"x\"}]}"));
        check(bad.layers.size() == 1 && bad.layers[0].N("dur") == 8, "bad recipe input is clamped and unknown layers dropped");
        bool threw = false;
        try { Json::parse("{oops"); } catch (...) { threw = true; }
        check(threw, "malformed JSON is rejected");
        std::vector<uint8_t> wav = encodeWav(a.L, a.R, a.sr, 24);
        check(wav.size() == 44 + a.L.size() * 6, "24-bit WAV size");
    }
    printf("\n%s (%d failed), total render time %.0f ms\n", fails ? "FAILED" : "ALL PASSED", fails, totalMs);
    return fails ? 1 : 0;
}

int main(int argc, char** argv) {
    if (argc < 2) return usage();
    std::string cmd = argv[1];
    if (cmd == "gen" && argc >= 3) {
        GenOptions o;
        o.category = argv[2];
        o.seed = (int64_t)opt(argc, argv, "--seed", -1);
        o.size = opt(argc, argv, "--size", -1); o.energy = opt(argc, argv, "--energy", -1);
        o.hardness = opt(argc, argv, "--hardness", -1); o.space = opt(argc, argv, "--space", -1); o.chaos = opt(argc, argv, "--chaos", -1);
        puts(recipeToString(generate(o)).c_str());
    } else if (cmd == "render" && argc >= 4) {
        Recipe r = loadRecipe(argv[2]);
        Audio a = render(r);
        auto wav = encodeWav(a.L, a.R, a.sr, (int)opt(argc, argv, "--bits", 24));
        writeFile(argv[3], wav.data(), wav.size());
        printf("%.2f s, %d Hz, peak %.1f dB, %.0f ms\n", a.duration, a.sr, 20 * log10(a.peak + 1e-12), a.renderMs);
    } else if (cmd == "stems" && argc >= 4) {
        Recipe r = loadRecipe(argv[2]);
        int bits = (int)opt(argc, argv, "--bits", 24);
        Audio mix = render(r);
        std::vector<ZipEntry> files;
        files.push_back({"mix.wav", encodeWav(mix.L, mix.R, mix.sr, bits)});
        int k = 1;
        for (size_t i = 0; i < r.layers.size(); i++) {
            if (r.layers[i].mute) continue;
            RenderOptions o; o.only = {(int)i}; o.minLength = mix.duration; o.raw = true;
            Audio s = render(r, o);
            char nm[96]; snprintf(nm, sizeof nm, "stems/%02d-%s.wav", k++, r.layers[i].name.empty() ? r.layers[i].type.c_str() : r.layers[i].name.c_str());
            files.push_back({nm, encodeWav(s.L, s.R, s.sr, bits)});
        }
        auto z = zipStore(files);
        writeFile(argv[3], z.data(), z.size());
        printf("%zu files\n", files.size());
    } else if (cmd == "mutate" && argc >= 4) {
        Recipe r = loadRecipe(argv[2]);
        puts(recipeToString(mutate(r, atof(argv[3]), (int64_t)opt(argc, argv, "--seed", -1))).c_str());
    } else if (cmd == "analyze" && argc >= 4) {
        Audio a = render(loadRecipe(argv[2]));
        writeAnalyzer(a, argv[3]);
        printf("%.2f s peak %.1f dB\n", a.duration, 20 * log10(a.peak + 1e-12));
    } else if (cmd == "schema") {
        puts(schemaJson().c_str());
    } else if (cmd == "prompt") {
        puts(aiPrompt().c_str());
    } else if (cmd == "selftest") {
        return selftest();
    } else return usage();
    return 0;
}
