// Recipe generator (18 sound categories driven by five macros) and mutation.
#include <algorithm>
#include <cmath>
#include <initializer_list>
#include <random>

#include "strata.hpp"

namespace strata {
namespace {

double clampd(double x, double a, double b) { return x < a ? a : (x > b ? b : x); }

struct Rng {
    uint32_t a;
    explicit Rng(uint32_t s) : a(s) {}
    double operator()() {
        a += 0x6D2B79F5u;
        uint32_t t = a;
        t = (t ^ (t >> 15)) * (t | 1u);
        t ^= t + (t ^ (t >> 7)) * (t | 61u);
        return (double)(t ^ (t >> 14)) / 4294967296.0;
    }
};

using KV = std::vector<std::pair<std::string, Json>>;

uint32_t randomSeed() {
    static std::random_device rd;
    return rd() % 1000000000u;
}

struct G {
    Rng r;
    explicit G(uint32_t s) : r(s) {}
    double U(double a, double b) { return a + (b - a) * r(); }
    double LU(double a, double b) { return a * std::pow(b / a, r()); }
    bool ch(double p) { return r() < p; }
    int I(double a, double b) { return (int)std::floor(U(a, b) + 0.5); }
    const char* pickS(std::initializer_list<const char*> l) { return *(l.begin() + (size_t)std::floor(r() * l.size())); }
    double pickD(std::initializer_list<double> l) { return *(l.begin() + (size_t)std::floor(r() * l.size())); }
};

}  // namespace

Recipe generate(const GenOptions& o) {
    uint32_t seed = o.seed < 0 ? randomSeed() : (uint32_t)clampd((double)o.seed, 0, 999999999);
    G g(seed ^ 0x9e3779b9u);
    std::string cat = o.category;
    bool known = false;
    for (auto& c : categories()) if (c.first == cat) known = true;
    if (!known) cat = categories()[(size_t)std::floor(g.r() * categories().size())].first;
    auto mac = [&](double v) { return v >= 0 ? clampd(v, 0, 1) : g.r(); };
    const double S = mac(o.size);
    const double En = mac(o.energy);
    const double H = mac(o.hardness);
    const double Sp = mac(o.space);
    const double C = o.chaos >= 0 ? clampd(o.chaos, 0, 1) : g.U(0.2, 0.6);
    const double fs = std::pow(2.0, (0.5 - S) * 3), ds = std::pow(2.0, (S - 0.5) * 2);

    Json layers = Json::array();
    auto add = [&](const char* type, const KV& a, const KV& b = {}, const KV& c = {}) {
        Json j = Json::object();
        j.set("type", type);
        for (auto& kv : a) j.set(kv.first, kv.second);
        for (auto& kv : b) j.set(kv.first, kv.second);
        for (auto& kv : c) j.set(kv.first, kv.second);
        layers.push(j);
    };
    auto U_ = [&](double a, double b) { return g.U(a, b); };
    auto LU = [&](double a, double b) { return g.LU(a, b); };
    auto ch = [&](double p) { return g.ch(p); };
    auto I = [&](double a, double b) { return g.I(a, b); };
    const KV HP = {{"filter", "highpass"}, {"q", 0.7}}, LPF = {{"filter", "lowpass"}}, BPF = {{"filter", "bandpass"}};
    auto NOTE = [](double k) { return 440 * std::pow(2.0, k / 12); };
    const double SCALE[] = {0, 2, 4, 7, 9, 12, 14, 16};
    KV extra;

    if (cat == "impact") {
        bool metal = H > 0.55 && ch(0.7);
        double f = LU(70, 420) * fs;
        add("noise", {{"name", "contact"}, {"color", g.pickS({"white", "velvet", "pink"})}, {"density", 2500}, {"width", 0.5}, {"dur", U_(0.012, 0.05) * (1.4 - H)}, {"attack", 0.0002}, {"curve", 9}, {"fcStart", LU(800, 4000) * (0.5 + H)}, {"fcEnd", 1500}, {"gain", -3 - (1 - H) * 6}, {"reverb", 0.15}}, HP);
        add("osc", {{"name", "thump"}, {"wave", "sine"}, {"freqStart", f * 2.2}, {"freqEnd", f * 0.55}, {"pitchCurve", 9}, {"dur", U_(0.15, 0.4) * ds}, {"attack", 0.0006}, {"curve", 5}, {"sub", 0.3 * S}, {"drive", 0.15 + En * 0.45}, {"gain", -2}, {"reverb", 0.1}});
        const char* model = metal ? g.pickS({"bar", "plate", "bell", "glass"}) : g.pickS({"membrane", "wood", "tube"});
        double freq = f * U_(1.2, 3);
        int parts = I(10, 26);
        double stiff = U_(0, 0.6);
        double decay = (metal ? U_(0.3, 1.4) : U_(0.06, 0.35)) * ds;
        double tilt = U_(1, 4);
        double sp = U_(0.1, 0.4);
        double beat = (metal && ch(0.5)) ? U_(0.5, 4) : 0.0;
        add("modal", {{"name", "body"}, {"model", model}, {"freq", freq}, {"partials", parts}, {"stiffness", stiff}, {"decay", decay}, {"tilt", tilt}, {"brightness", H}, {"strikePos", sp}, {"beat", beat}, {"strike", 0.3 + H * 0.5}, {"dur", (metal ? 1.6 : 0.5) * ds}, {"gain", -5}, {"reverb", 0.3}});
        add("noise", {{"name", "air"}, {"color", "brown"}, {"width", 1}, {"start", 0.01}, {"dur", U_(0.3, 0.9) * ds}, {"attack", 0.004}, {"curve", 3}, {"fcStart", LU(2500, 7000) * (0.5 + H)}, {"fcEnd", 200}, {"sweep", 0.5}, {"gain", -16 + En * 4}, {"reverb", 0.5}}, LPF);
        if (ch(0.25 + C * 0.5))
            add("debris", {{"name", "fallout"}, {"rate", LU(10, 60)}, {"accel", -0.6}, {"fLo", 300 * fs}, {"fHi", 3500 * fs}, {"hitMs", U_(15, 80)}, {"partials", 3}, {"hardness", H}, {"velVar", 0.8}, {"start", U_(0.08, 0.25)}, {"dur", U_(0.3, 0.9) * ds}, {"curve", 2}, {"gain", -15}, {"reverb", 0.4}});
        extra = {{"compThresh", -16}, {"compRatio", 3}, {"compMakeup", 2}};
    } else if (cat == "explosion") {
        double bd = U_(1.3, 2.4) * ds;
        add("noise", {{"name", "crack"}, {"color", "white"}, {"width", 1}, {"dur", U_(0.02, 0.07)}, {"attack", 0.0002}, {"curve", 8}, {"fcStart", 1500}, {"fcEnd", 1500}, {"gain", -2}, {"reverb", 0.2}}, HP);
        double bs = LU(110, 170) * fs;
        double be = LU(24, 38) * fs;
        double pc = U_(3, 6);
        add("osc", {{"name", "boom"}, {"wave", "sine"}, {"freqStart", bs}, {"freqEnd", be}, {"pitchCurve", pc}, {"dur", bd * 0.7}, {"attack", 0.003}, {"curve", 3.5}, {"sub", 0.5}, {"drive", 0.35 + En * 0.4}, {"gain", -1}, {"reverb", 0.15}});
        const char* col = g.pickS({"brown", "pink"});
        double fc0 = LU(5000, 9000);
        double fc1 = LU(120, 300);
        add("noise", {{"name", "blast"}, {"color", col}, {"width", 1}, {"start", 0.004}, {"dur", bd}, {"attack", 0.003}, {"curve", 3}, {"fcStart", fc0}, {"fcEnd", fc1}, {"sweep", 0.45}, {"q", 0.8}, {"drive", 0.2}, {"gain", -3}, {"reverb", 0.5}}, LPF);
        add("noise", {{"name", "rumble"}, {"color", "brown"}, {"width", 1}, {"start", 0.05}, {"dur", bd * 1.5}, {"attack", 0.08}, {"curve", 2.4}, {"fcStart", 160}, {"fcEnd", 60}, {"gain", -8}, {"reverb", 0.6}}, LPF);
        double rate = LU(60, 160);
        double hm = U_(20, 120);
        double st = U_(0.2, 0.5);
        add("debris", {{"name", "fallout"}, {"rate", rate}, {"accel", -0.9}, {"fLo", 250 * fs}, {"fHi", 5000 * fs}, {"hitMs", hm}, {"partials", 3}, {"hardness", 0.5}, {"velVar", 0.9}, {"start", st}, {"dur", bd * 1.2}, {"curve", 2}, {"gain", -12}, {"reverb", 0.5}});
        if (ch(0.5)) {
            double dens = LU(400, 3000);
            add("noise", {{"name", "sizzle"}, {"color", "crackle"}, {"density", dens}, {"width", 1}, {"dur", bd}, {"start", 0.3}, {"attack", 0.1}, {"curve", 2}, {"fcStart", 2500}, {"fcEnd", 2500}, {"gain", -18}, {"reverb", 0.4}}, HP);
        }
        extra = {{"compThresh", -14}, {"compRatio", 4}, {"compMakeup", 3}, {"echoFb", 0.3}};
    } else if (cat == "weapon") {
        double tl = U_(0.8, 2.2) * (0.5 + Sp);
        double c0 = U_(0.02, 0.05);
        double fc0 = LU(1500, 3500);
        add("noise", {{"name", "crack"}, {"color", "white"}, {"width", 1}, {"dur", c0}, {"attack", 0.0001}, {"curve", 9}, {"fcStart", fc0}, {"fcEnd", 1200}, {"gain", -1}, {"reverb", 0.15}, {"drive", 0.3}}, HP);
        double b0 = LU(160, 260) * fs;
        double b1 = LU(40, 70) * fs;
        double bd = U_(0.15, 0.4) * ds;
        add("osc", {{"name", "boom"}, {"wave", "sine"}, {"freqStart", b0}, {"freqEnd", b1}, {"pitchCurve", 9}, {"dur", bd}, {"attack", 0.0004}, {"curve", 5}, {"drive", 0.3 + En * 0.4}, {"gain", -2}, {"reverb", 0.2}});
        double bl = U_(0.15, 0.4) * ds;
        double f0 = LU(5000, 9000);
        add("noise", {{"name", "blast"}, {"color", "pink"}, {"width", 1}, {"dur", bl}, {"attack", 0.001}, {"curve", 5}, {"fcStart", f0}, {"fcEnd", 300}, {"sweep", 0.5}, {"gain", -4}, {"reverb", 0.4}}, LPF);
        double t0 = LU(2500, 5000);
        add("noise", {{"name", "tail"}, {"color", "pink"}, {"width", 1}, {"start", 0.02}, {"dur", tl}, {"attack", 0.01}, {"curve", 3.5}, {"fcStart", t0}, {"fcEnd", 250}, {"sweep", 0.5}, {"gain", -14}, {"reverb", 0.8}, {"echo", 0.35}}, LPF);
        double af = LU(500, 1800);
        double as = U_(0.0, 0.012);
        add("modal", {{"name", "action"}, {"model", "bar"}, {"freq", af}, {"partials", 8}, {"decay", 0.06}, {"brightness", 0.9}, {"strike", 0.8}, {"start", as}, {"dur", 0.15}, {"gain", -14}, {"reverb", 0.2}});
        if (ch(0.6)) {
            double cf = LU(2800, 5200);
            double cd = U_(0.08, 0.2);
            double cs = U_(0.3, 0.6);
            int rp = I(2, 4);
            double ri = U_(0.07, 0.14);
            add("modal", {{"name", "casing"}, {"model", "tube"}, {"freq", cf}, {"partials", 6}, {"decay", cd}, {"brightness", 0.8}, {"start", cs}, {"dur", 0.4}, {"gain", -18}, {"repeat", rp}, {"repInterval", ri}, {"repJitter", 0.5}, {"repDecay", 0.6}, {"repVar", 0.5}, {"reverb", 0.4}});
        }
        double et = LU(120, 380);
        extra = {{"compThresh", -16}, {"compRatio", 5}, {"compMakeup", 4}, {"transient", 0.4}, {"echoTime", et}, {"echoFb", 0.3}};
    } else if (cat == "whoosh") {
        double d = U_(0.5, 1.6) * ds;
        bool up = ch(0.5);
        double dir = ch(0.5) ? 1 : -1;
        double a = LU(350, 1100) * (0.6 + En * 0.8);
        double b = LU(2200, 7000) * (0.6 + En * 0.8);
        double att = d * U_(0.35, 0.6);
        double curve = U_(1.2, 3), sw = U_(0.6, 1.4), q = U_(1.2, 4), mr = U_(6, 24), mdp = U_(0.1, 0.4) * (C + 0.3);
        add("noise", {{"name", "air"}, {"color", "pink"}, {"width", 1}, {"dur", d}, {"attack", att}, {"curve", curve}, {"filter", "bandpass"}, {"fcStart", up ? a : b}, {"fcEnd", up ? b : a}, {"sweep", sw}, {"q", q}, {"modRate", mr}, {"modDepth", mdp}, {"pan", -0.9 * dir}, {"move", 1.8 * dir}, {"gain", -3}, {"reverb", 0.25}});
        add("noise", {{"name", "hiss"}, {"color", "white"}, {"width", 1}, {"start", 0.02}, {"dur", d * 0.9}, {"attack", att}, {"curve", 2}, {"fcStart", 3500}, {"fcEnd", 3500}, {"gain", -14}, {"pan", -0.9 * dir}, {"move", 1.8 * dir}, {"reverb", 0.2}}, HP);
        double wq = U_(1.5, 4), gr = U_(1, 3), gd = U_(0.3, 0.8), hw = U_(0, 0.3);
        add("wind", {{"name", "body"}, {"wCenter", (a + b) * 0.25}, {"wQ", wq}, {"gustRate", gr}, {"gustDepth", gd}, {"howl", hw}, {"turb", 0.5}, {"dur", d}, {"attack", att}, {"curve", 2}, {"gain", -9}, {"pan", -0.9 * dir}, {"move", 1.8 * dir}, {"reverb", 0.2}});
        add("noise", {{"name", "weight"}, {"color", "brown"}, {"width", 1}, {"dur", d}, {"attack", att}, {"curve", 2.5}, {"fcStart", 300}, {"fcEnd", 150}, {"gain", -10}, {"reverb", 0.2}}, LPF);
    } else if (cat == "magic") {
        double d = U_(1.1, 2.4), f = LU(300, 1200);
        const char* wv = g.pickS({"sine", "triangle"});
        double mult = g.pickD({1.5, 2, 3});
        double pcv = U_(1, 4);
        double fmr = g.pickD({1.5, 2, 3, 4.01});
        double fmi = U_(1, 5), fmd = U_(1, 4);
        double vc = g.pickD({3, 5});
        double dt = U_(6, 25), vr = U_(4, 7), vd = U_(5, 30), at = U_(0.02, 0.25), cv = U_(1.5, 3.5);
        add("osc", {{"name", "tone"}, {"wave", wv}, {"freqStart", f}, {"freqEnd", f * mult}, {"pitchCurve", pcv}, {"fmRatio", fmr}, {"fmIndex", fmi}, {"fmDecay", fmd}, {"voices", vc}, {"detune", dt}, {"vibRate", vr}, {"vibDepth", vd}, {"dur", d}, {"attack", at}, {"curve", cv}, {"gain", -6}, {"reverb", 0.6}, {"echo", 0.3}});
        double ds0 = LU(10, 40), de = LU(80, 300), gm = U_(4, 22), fh = LU(5000, 12000), gs = U_(0, 0.3), gc = U_(1.2, 3);
        add("grain", {{"name", "sparkle"}, {"source", "tone"}, {"densStart", ds0}, {"densEnd", de}, {"grainMs", gm}, {"fLo", f * 3}, {"fHi", fh}, {"scatter", 1}, {"start", gs}, {"dur", d}, {"attack", 0.05}, {"curve", gc}, {"gain", -9}, {"reverb", 0.6}, {"echo", 0.25}});
        const char* cm = g.pickS({"bell", "glass", "tube"});
        double cmul = g.pickD({2, 3, 4});
        double cd = U_(1, 3), cb = U_(0, 3), cst = U_(0.02, 0.2);
        add("modal", {{"name", "chime"}, {"model", cm}, {"freq", f * cmul}, {"partials", 12}, {"decay", cd}, {"brightness", 0.7}, {"beat", cb}, {"start", cst}, {"dur", d * 1.3}, {"attack", 0.0005}, {"gain", -9}, {"reverb", 0.7}, {"echo", 0.3}});
        double d0 = LU(1500, 3000), d1 = LU(5000, 9000);
        add("noise", {{"name", "dust"}, {"color", "pink"}, {"width", 1}, {"dur", d * 0.9}, {"attack", d * 0.5}, {"curve", 2}, {"filter", "bandpass"}, {"fcStart", d0}, {"fcEnd", d1}, {"q", 2}, {"gain", -16}, {"reverb", 0.6}});
        double et = LU(180, 420);
        extra = {{"revDecay", 2.5 + Sp * 3}, {"echoTime", et}, {"echoFb", 0.4}};
    } else if (cat == "zap") {
        double d = U_(0.15, 0.55) * (0.6 + S * 0.8);
        const char* wv = g.pickS({"saw", "square", "pulse"});
        double pw = U_(0.1, 0.5), f0 = LU(1800, 6000), f1 = LU(60, 300) * fs, pc = U_(6, 16);
        double fmr = g.pickD({0.5, 1, 2, 3.01}), fmi = U_(2, 12), fmd = U_(3, 10), vc = g.pickD({1, 2, 3}), dt = U_(5, 30), cv = U_(2, 5);
        double c0 = LU(6000, 15000), c1 = LU(400, 2500), q = U_(1, 6);
        add("osc", {{"name", "beam"}, {"wave", wv}, {"pulseW", pw}, {"freqStart", f0}, {"freqEnd", f1}, {"pitchCurve", pc}, {"fmRatio", fmr}, {"fmIndex", fmi}, {"fmDecay", fmd}, {"voices", vc}, {"detune", dt}, {"dur", d}, {"attack", 0.0008}, {"curve", cv}, {"filter", "lowpass"}, {"fcStart", c0}, {"fcEnd", c1}, {"sweep", 0.6}, {"q", q}, {"drive", 0.2 + En * 0.4}, {"gain", -2}, {"echo", 0.3}, {"reverb", 0.25}});
        double dens = LU(1500, 9000), dm = U_(0.8, 1.6), a0 = LU(2500, 6000), a1 = LU(1500, 3500), mr = U_(30, 60);
        add("noise", {{"name", "arc"}, {"color", "crackle"}, {"density", dens}, {"width", 1}, {"dur", d * dm}, {"attack", 0.001}, {"curve", 2.5}, {"filter", "bandpass"}, {"fcStart", a0}, {"fcEnd", a1}, {"q", 1.5}, {"modRate", mr}, {"modDepth", 0.5}, {"gain", -8}, {"reverb", 0.3}});
        const char* rm = g.pickS({"plate", "spring", "chaos"});
        double rf = LU(150, 700), rd = U_(0.2, 0.8);
        add("modal", {{"name", "ring"}, {"model", rm}, {"freq", rf}, {"decay", rd}, {"brightness", 0.8}, {"beat", 2}, {"start", 0.002}, {"dur", d * 3}, {"gain", -12}, {"echo", 0.4}, {"reverb", 0.5}});
        add("osc", {{"name", "thump"}, {"wave", "sine"}, {"freqStart", 200 * fs}, {"freqEnd", 50 * fs}, {"pitchCurve", 10}, {"dur", 0.14}, {"attack", 0.0005}, {"curve", 5}, {"gain", -6}});
        double et = LU(120, 300);
        extra = {{"echoTime", et}, {"echoFb", 0.4}};
    } else if (cat == "creature") {
        double p = LU(70, 220) * fs;
        const char* vs[] = {"a", "e", "i", "o", "u", "ae", "uh"};
        double d = U_(0.8, 2) * ds;
        auto pv = [&]() { return vs[(size_t)std::floor(g.r() * 7)]; };
        double pe = U_(0.4, 1.1), pcv = U_(1.5, 5);
        const char* va = pv();
        const char* vb = pv();
        double mo = U_(0.5, 2.5), grr = U_(25, 70), br = U_(0.1, 0.4), te = U_(0.3, 0.9), vr = U_(3, 7), vd = U_(5, 40), ji = U_(0.2, 0.8), at = U_(0.03, 0.15), cv = U_(1.5, 3);
        add("voice", {{"name", "voice"}, {"pStart", p}, {"pEnd", p * pe}, {"pitchCurve", pcv}, {"vowelA", va}, {"vowelB", vb}, {"morph", mo}, {"shift", std::pow(2.0, (0.5 - S) * 0.9)}, {"growl", En * 0.8}, {"growlRate", grr}, {"breath", br}, {"tension", te}, {"vibRate", vr}, {"vibDepth", vd}, {"jitter", ji}, {"dur", d}, {"attack", at}, {"curve", cv}, {"drive", 0.15 + En * 0.3}, {"gain", -2}, {"reverb", 0.3}});
        add("osc", {{"name", "chest"}, {"wave", "sine"}, {"freqStart", p * 0.8}, {"freqEnd", p * 0.4}, {"pitchCurve", 2}, {"sub", 0.4}, {"dur", d * 0.9}, {"attack", 0.05}, {"curve", 2.5}, {"gain", -10}, {"reverb", 0.2}});
        double b0 = LU(700, 1500), b1 = LU(500, 2500);
        add("noise", {{"name", "breath"}, {"color", "pink"}, {"width", 1}, {"dur", d * 1.1}, {"attack", 0.1}, {"curve", 2}, {"filter", "bandpass"}, {"fcStart", b0}, {"fcEnd", b1}, {"q", 1.5}, {"gain", -14}, {"reverb", 0.4}});
        if (ch(0.4 + C * 0.3)) {
            double rt = LU(8, 30);
            add("bubble", {{"name", "wet"}, {"rate", rt}, {"fLo", 300}, {"fHi", 1800}, {"rise", 0.6}, {"ring", 15}, {"cluster", 0.5}, {"scatter", 0.4}, {"dur", d}, {"attack", 0.05}, {"curve", 1.2}, {"gain", -18}, {"reverb", 0.3}});
        }
        extra = {{"compThresh", -18}, {"compRatio", 3}, {"compMakeup", 2}};
    } else if (cat == "vehicle") {
        bool pass = ch(0.55);
        double f = LU(18, 48) * (0.7 + (1 - S) * 0.6);
        double dir = ch(0.5) ? 1 : -1;
        double d = pass ? U_(2.5, 5.5) : U_(2.5, 4.5);
        int hm = I(30, 60);
        double tl = U_(0.8, 1.5), fm = LU(120, 500), rb = U_(0.4, 0.9), ro = U_(0.1, 0.5) * (0.5 + C), hf = U_(0, 0.5);
        double wh = 0;
        if (ch(0.3)) wh = U_(0.2, 0.5);
        double nz = U_(0.1, 0.35);
        KV mo = {{"name", "engine"}, {"harmonics", hm}, {"tilt", tl}, {"formant", fm}, {"resBoost", rb}, {"rough", ro}, {"half", hf}, {"whine", wh}, {"noise", nz}, {"gain", -2}, {"reverb", 0.2}};
        if (pass) {
            double s0 = f * U_(1.2, 2.2);
            double c0 = LU(7000, 12000), c1 = LU(1500, 3200);
            KV more = {{"fStart", s0}, {"fEnd", f}, {"rampShape", 1}, {"dur", d}, {"attack", d * 0.45}, {"curve", 4}, {"filter", "lowpass"}, {"fcStart", c0}, {"fcEnd", c1}, {"sweep", 0.7}, {"q", 0.7}, {"pan", -0.9 * dir}, {"move", 1.8 * dir}};
            mo.insert(mo.end(), more.begin(), more.end());
            add("motor", mo);
        } else {
            double e = f * U_(2, 5) * (0.5 + En);
            double rs = U_(0.5, 1.2);
            double c1 = LU(5000, 9000);
            KV more = {{"fStart", f}, {"fEnd", e}, {"rampShape", rs}, {"dur", d}, {"attack", 0.1}, {"curve", 0.4}, {"filter", "lowpass"}, {"fcStart", 2500}, {"fcEnd", c1}, {"sweep", 1}, {"q", 0.7}};
            mo.insert(mo.end(), more.begin(), more.end());
            add("motor", mo);
        }
        double t0 = LU(900, 1800), t1 = LU(500, 1000);
        add("noise", {{"name", "tires"}, {"color", "pink"}, {"width", 1}, {"dur", d}, {"attack", pass ? d * 0.45 : 0.2}, {"curve", pass ? 3 : 0.5}, {"filter", "bandpass"}, {"fcStart", t0}, {"fcEnd", t1}, {"q", 0.8}, {"pan", pass ? -0.9 * dir : 0}, {"move", pass ? 1.8 * dir : 0}, {"gain", -15}, {"reverb", 0.2}});
        double wc = LU(300, 900), gr = U_(0.2, 1);
        add("wind", {{"name", "air"}, {"wCenter", wc}, {"wQ", 2}, {"gustRate", gr}, {"gustDepth", 0.5}, {"howl", 0.05}, {"turb", 0.4}, {"dur", d}, {"attack", pass ? d * 0.45 : 0.5}, {"curve", pass ? 3 : 0.6}, {"pan", pass ? -0.9 * dir : 0}, {"move", pass ? 1.8 * dir : 0}, {"gain", -18}, {"reverb", 0.2}});
    } else if (cat == "machine") {
        double f = LU(30, 120) * (0.7 + (1 - S) * 0.6), d = U_(1.5, 3.5), rf = f * U_(0.8, 1.3);
        int hm = I(20, 45);
        double tl = U_(0.6, 1.4), fm = LU(250, 900), rb = U_(0.3, 0.8), ro = U_(0.05, 0.3), wh = U_(0.2, 0.6), nz = U_(0.05, 0.2);
        add("motor", {{"name", "motor"}, {"fStart", f}, {"fEnd", rf}, {"harmonics", hm}, {"tilt", tl}, {"formant", fm}, {"resBoost", rb}, {"rough", ro}, {"whine", wh}, {"noise", nz}, {"dur", d}, {"attack", 0.08}, {"curve", 0.5}, {"gain", -3}, {"reverb", 0.25}});
        double r0 = LU(60, 200), r1 = LU(60, 200), rf2 = LU(900, 2400), rq = U_(12, 30);
        add("friction", {{"name", "gears"}, {"rateStart", r0}, {"rateEnd", r1}, {"pulse", 0.1}, {"jitter", 0.3}, {"grit", 0.4}, {"resFreq", rf2}, {"rq", rq}, {"inharm", 0.5}, {"pressure", 0.3}, {"dur", d}, {"attack", 0.1}, {"curve", 0.5}, {"gain", -14}, {"reverb", 0.25}});
        const char* cm = g.pickS({"bar", "plate", "membrane"});
        double cf = LU(120, 400) * fs, cd = U_(0.1, 0.35);
        int rp = I(2, 5);
        double ri = U_(0.15, 0.5);
        add("modal", {{"name", "clunk"}, {"model", cm}, {"freq", cf}, {"partials", 14}, {"decay", cd}, {"brightness", 0.6}, {"strike", 0.6}, {"dur", 0.5}, {"gain", -9}, {"repeat", rp}, {"repInterval", ri}, {"repJitter", 0.3}, {"repDecay", 0.85}, {"repVar", 0.5}, {"reverb", 0.3}});
        add("noise", {{"name", "air"}, {"color", "pink"}, {"width", 1}, {"dur", d}, {"attack", 0.2}, {"curve", 0.6}, {"fcStart", 2500}, {"fcEnd", 1500}, {"gain", -18}, {"reverb", 0.2}}, LPF);
    } else if (cat == "water") {
        double d = U_(1.2, 3.2), dens = LU(8, 60) * (0.4 + En);
        double ac = U_(-0.5, 0.5), bl = LU(200, 500) * fs, bh = LU(1800, 4000), rs = U_(0.3, 1), rg = U_(12, 40);
        add("bubble", {{"name", "bubbles"}, {"rate", dens}, {"accel", ac}, {"fLo", bl}, {"fHi", bh}, {"rise", rs}, {"ring", rg}, {"cluster", C * 0.7}, {"scatter", 0.8}, {"dur", d}, {"attack", 0.01}, {"curve", 1.4}, {"gain", -4}, {"reverb", 0.4}});
        double f0 = LU(900, 1800), f1 = LU(900, 2200), mr = U_(5, 14);
        add("noise", {{"name", "flow"}, {"color", "pink"}, {"width", 1}, {"dur", d}, {"attack", 0.1}, {"curve", 1.2}, {"filter", "bandpass"}, {"fcStart", f0}, {"fcEnd", f1}, {"q", 0.9}, {"modRate", mr}, {"modDepth", 0.5}, {"gain", -14}, {"reverb", 0.4}});
        double dr = U_(2, 7);
        add("bubble", {{"name", "drops"}, {"rate", dr}, {"fLo", 1200}, {"fHi", 5000}, {"rise", 0.8}, {"ring", 20}, {"cluster", 0}, {"scatter", 1}, {"start", 0.05}, {"dur", d}, {"attack", 0.01}, {"curve", 0.6}, {"gain", -9}, {"reverb", 0.6}});
        add("noise", {{"name", "body"}, {"color", "brown"}, {"width", 1}, {"dur", d}, {"attack", 0.2}, {"curve", 1}, {"fcStart", 400}, {"fcEnd", 300}, {"gain", -18}, {"reverb", 0.4}}, LPF);
    } else if (cat == "rain") {
        double d = U_(3.5, 6), dens = LU(150, 500) * (0.5 + En);
        add("debris", {{"name", "drops"}, {"rate", dens}, {"accel", 0}, {"fLo", 2500}, {"fHi", 9000}, {"hitMs", 6}, {"partials", 2}, {"hardness", 0.3}, {"velVar", 0.9}, {"dur", d}, {"attack", 0.4}, {"curve", 0.5}, {"gain", -5}, {"reverb", 0.4}});
        double mr = U_(0.5, 3);
        add("noise", {{"name", "wash"}, {"color", "pink"}, {"width", 1}, {"dur", d}, {"attack", 0.5}, {"curve", 0.5}, {"filter", "highpass"}, {"fcStart", 1500}, {"fcEnd", 1500}, {"q", 0.7}, {"modRate", mr}, {"modDepth", 0.15}, {"gain", -14}, {"reverb", 0.4}});
        double sr_ = LU(8, 25);
        add("debris", {{"name", "surface"}, {"rate", sr_}, {"accel", 0}, {"fLo", 300 * fs}, {"fHi", 900 * fs}, {"hitMs", 50}, {"partials", 3}, {"hardness", 0.4}, {"velVar", 0.8}, {"dur", d}, {"attack", 0.4}, {"curve", 0.5}, {"gain", -12}, {"reverb", 0.5}});
        double pr = LU(3, 12);
        add("bubble", {{"name", "puddles"}, {"rate", pr}, {"fLo", 400}, {"fHi", 2500}, {"rise", 0.6}, {"ring", 15}, {"cluster", 0.3}, {"scatter", 1}, {"dur", d}, {"attack", 0.4}, {"curve", 0.5}, {"gain", -16}, {"reverb", 0.4}});
        add("noise", {{"name", "low"}, {"color", "brown"}, {"width", 1}, {"dur", d}, {"attack", 0.6}, {"curve", 0.5}, {"fcStart", 500}, {"fcEnd", 500}, {"gain", -20}, {"reverb", 0.4}}, LPF);
        extra = {{"revDecay", 0.8 + Sp * 2.2}};
    } else if (cat == "glass") {
        double f = LU(900, 3000) * std::pow(2.0, 0.5 - S);
        double cd = U_(0.015, 0.04);
        add("noise", {{"name", "crack"}, {"color", "white"}, {"width", 1}, {"dur", cd}, {"attack", 0.0002}, {"curve", 9}, {"fcStart", 3000}, {"fcEnd", 3000}, {"gain", -2}, {"reverb", 0.2}}, HP);
        double pd = U_(0.15, 0.5);
        add("modal", {{"name", "pane"}, {"model", "glass"}, {"freq", f}, {"partials", 14}, {"decay", pd}, {"brightness", 0.9}, {"strike", 0.7}, {"dur", 0.7}, {"gain", -6}, {"reverb", 0.4}});
        double sr_ = LU(100, 220), sd = U_(0.9, 1.8) * ds;
        add("debris", {{"name", "shards"}, {"rate", sr_}, {"accel", -0.7}, {"fLo", 2500}, {"fHi", 9000}, {"hitMs", 40}, {"partials", 3}, {"hardness", 0.9}, {"velVar", 0.9}, {"start", 0.015}, {"dur", sd}, {"curve", 2}, {"gain", -5}, {"reverb", 0.4}});
        double pf = LU(500, 1000);
        int rp = I(4, 8);
        double ri = U_(0.06, 0.14);
        add("modal", {{"name", "pieces"}, {"model", "plate"}, {"freq", pf}, {"partials", 10}, {"decay", 0.25}, {"brightness", 0.8}, {"strike", 0.5}, {"start", 0.06}, {"dur", 0.5}, {"gain", -12}, {"repeat", rp}, {"repInterval", ri}, {"repJitter", 0.8}, {"repDecay", 0.82}, {"repVar", 0.9}, {"reverb", 0.4}});
        double rd = U_(0.8, 2), rb = U_(1, 4);
        add("modal", {{"name", "ring"}, {"model", "glass"}, {"freq", f * 0.8}, {"partials", 6}, {"decay", rd}, {"brightness", 0.5}, {"beat", rb}, {"start", 0.01}, {"dur", 2.2}, {"gain", -15}, {"reverb", 0.6}});
        add("noise", {{"name", "air"}, {"color", "white"}, {"width", 1}, {"dur", 0.8}, {"attack", 0.01}, {"curve", 4}, {"fcStart", 6000}, {"fcEnd", 6000}, {"gain", -24}, {"reverb", 0.4}}, HP);
        extra = {{"compThresh", -14}, {"compRatio", 3}, {"compMakeup", 2}};
    } else if (cat == "metal") {
        double f = LU(120, 900) * fs;
        const char* m = g.pickS({"bar", "plate", "bell", "tube"});
        double d = U_(1, 2.6) * ds;
        double sd = U_(0.008, 0.03), sf = LU(2000, 5000);
        add("noise", {{"name", "strike"}, {"color", "white"}, {"width", 0.6}, {"dur", sd}, {"attack", 0.0002}, {"curve", 9}, {"fcStart", sf}, {"fcEnd", 2000}, {"gain", -6}, {"reverb", 0.2}}, HP);
        int pt = I(14, 30);
        double st = U_(0, 1), tl = U_(0.5, 3), sp = U_(0.1, 0.45);
        double beat = ch(0.6) ? U_(0.5, 5) : 0.0;
        add("modal", {{"name", "main"}, {"model", m}, {"freq", f}, {"partials", pt}, {"stiffness", st}, {"decay", d}, {"tilt", tl}, {"brightness", H}, {"strikePos", sp}, {"beat", beat}, {"strike", 0.3 + H * 0.5}, {"dur", d * 1.3}, {"gain", -3}, {"reverb", 0.4}});
        const char* om = g.pickS({"bell", "chaos", "plate"});
        double omul = g.pickD({1.5, 2.4, 3.1}), ob = U_(0, 4);
        add("modal", {{"name", "overtones"}, {"model", om}, {"freq", f * omul}, {"partials", 10}, {"decay", d * 0.6}, {"tilt", 2}, {"brightness", 0.8}, {"beat", ob}, {"start", 0.002}, {"dur", d}, {"gain", -10}, {"reverb", 0.5}});
        add("osc", {{"name", "thud"}, {"wave", "sine"}, {"freqStart", f * 1.5}, {"freqEnd", f * 0.5}, {"pitchCurve", 9}, {"dur", 0.15 * ds}, {"attack", 0.0005}, {"curve", 5}, {"gain", -8}});
        extra = {{"compThresh", -18}, {"compRatio", 3}, {"compMakeup", 2}};
    } else if (cat == "creak") {
        double d = U_(0.8, 2.5), rf = LU(6, 30), res = LU(300, 1200);
        double re = rf * U_(0.5, 2.5), rc = U_(0.5, 3), rq = U_(8, 30), ih = U_(0.2, 0.8);
        add("friction", {{"name", "creak"}, {"rateStart", rf}, {"rateEnd", re}, {"rateCurve", rc}, {"pulse", 0.1}, {"jitter", 0.6}, {"grit", 0.4}, {"resFreq", res}, {"rq", rq}, {"inharm", ih}, {"pressure", 0.6}, {"dur", d}, {"attack", 0.1}, {"curve", 0.8}, {"gain", -4}, {"reverb", 0.3}});
        if (ch(0.6)) {
            double s0 = LU(600, 2200), s1 = LU(600, 2200), rm = U_(1.5, 3), st = U_(0, 0.3);
            add("friction", {{"name", "squeal"}, {"rateStart", s0}, {"rateEnd", s1}, {"rateCurve", 2}, {"pulse", 0.9}, {"jitter", 0.1}, {"grit", 0.1}, {"resFreq", res * rm}, {"rq", 40}, {"inharm", 0.1}, {"pressure", 0.5}, {"start", st}, {"dur", d * 0.7}, {"attack", 0.15}, {"curve", 1.2}, {"gain", -14}, {"reverb", 0.3}});
        }
        double wf = LU(80, 220) * fs, ri = U_(0.3, 0.9);
        add("modal", {{"name", "wood"}, {"model", "wood"}, {"freq", wf}, {"partials", 8}, {"decay", 0.4}, {"brightness", 0.4}, {"strike", 0.4}, {"dur", 0.6}, {"gain", -11}, {"repeat", 2}, {"repInterval", ri}, {"repJitter", 0.5}, {"repDecay", 0.7}, {"repVar", 0.5}, {"reverb", 0.4}});
        add("noise", {{"name", "rub"}, {"color", "pink"}, {"width", 0.5}, {"dur", d}, {"attack", 0.1}, {"curve", 0.8}, {"fcStart", 1500}, {"fcEnd", 1500}, {"gain", -20}, {"reverb", 0.2}}, LPF);
    } else if (cat == "footsteps") {
        int n = I(4, 8);
        double iv = U_(0.3, 0.55);
        bool hard = H > 0.5;
        double f = LU(70, 160) * fs;
        KV rp = {{"repeat", n}, {"repInterval", iv}, {"repJitter", 0.12 + C * 0.15}, {"repDecay", 1}, {"repVar", 0.4}};
        add("modal", {{"name", "thud"}, {"model", hard ? "plate" : "membrane"}, {"freq", hard ? f * 3 : f}, {"partials", 12}, {"decay", hard ? 0.1 : 0.12}, {"brightness", hard ? 0.8 : 0.3}, {"strike", 0.5}, {"dur", 0.4}, {"gain", -3}, {"reverb", 0.3}}, rp);
        add("noise", {{"name", "tap"}, {"color", hard ? "white" : "pink"}, {"width", 0.5}, {"dur", hard ? 0.025 : 0.07}, {"attack", 0.0004}, {"curve", 7}, {"fcStart", hard ? 3000 : 1800}, {"fcEnd", hard ? 3000 : 900}, {"gain", hard ? -5 : -9}, {"reverb", 0.2}}, hard ? HP : BPF, rp);
        add("noise", {{"name", "scuff"}, {"color", "pink"}, {"width", 0.7}, {"start", 0.02}, {"dur", 0.1}, {"attack", 0.01}, {"curve", 3}, {"fcStart", 1500}, {"fcEnd", 700}, {"q", 1.2}, {"gain", -15}, {"reverb", 0.2}}, BPF, rp);
        double gf = LU(400, 900);
        add("modal", {{"name", "gear"}, {"model", "string"}, {"freq", gf}, {"partials", 6}, {"decay", 0.08}, {"brightness", 0.6}, {"strike", 0.8}, {"dur", 0.2}, {"gain", -22}, {"reverb", 0.2}}, rp);
    } else if (cat == "wind") {
        double d = U_(4, 7);
        double c0 = LU(250, 900), q0 = U_(1.5, 5), g0 = U_(0.1, 0.6), gd0 = U_(0.4, 1.1);
        add("wind", {{"name", "gale"}, {"wCenter", c0}, {"wQ", q0}, {"gustRate", g0}, {"gustDepth", gd0}, {"howl", H * 0.5}, {"turb", 0.3 + C * 0.3}, {"width", 0.9}, {"dur", d}, {"attack", 1}, {"curve", 0.6}, {"gain", -3}, {"reverb", 0.4}});
        double c1 = LU(1200, 3000), q1 = U_(2, 6), g1 = U_(0.2, 0.9), gd1 = U_(0.3, 0.8);
        add("wind", {{"name", "upper"}, {"wCenter", c1}, {"wQ", q1}, {"gustRate", g1}, {"gustDepth", gd1}, {"howl", H * 0.4}, {"turb", 0.4}, {"width", 1}, {"dur", d}, {"attack", 1.2}, {"curve", 0.6}, {"gain", -12}, {"reverb", 0.5}});
        double mr = U_(0.2, 0.8);
        add("noise", {{"name", "rumble"}, {"color", "brown"}, {"width", 1}, {"dur", d}, {"attack", 1}, {"curve", 0.6}, {"fcStart", 200}, {"fcEnd", 150}, {"modRate", mr}, {"modDepth", 0.4}, {"gain", -12}, {"reverb", 0.3}}, LPF);
        double ds0 = LU(8, 30), ds1 = LU(8, 30), gm = U_(6, 25);
        add("grain", {{"name", "leaves"}, {"source", "noise"}, {"densStart", ds0}, {"densEnd", ds1}, {"grainMs", gm}, {"fLo", 2500}, {"fHi", 9000}, {"scatter", 1}, {"dur", d}, {"attack", 1}, {"curve", 0.6}, {"gain", -22}, {"reverb", 0.5}});
    } else if (cat == "ui") {
        double base = g.pickD({-12, -7, -5, 0});
        double k1 = SCALE[(size_t)std::floor(g.r() * 8)], k2 = SCALE[(size_t)std::floor(g.r() * 8)];
        double f1 = NOTE(base + k1), f2 = NOTE(base + k2);
        bool two = ch(0.6);
        const char* mm = g.pickS({"tube", "bell", "bar", "glass"});
        double d1 = U_(0.15, 0.5);
        add("modal", {{"name", "note1"}, {"model", mm}, {"freq", f1}, {"partials", 8}, {"decay", d1}, {"brightness", 0.75}, {"strike", 0.2}, {"dur", 0.7}, {"attack", 0.0004}, {"gain", -4}, {"reverb", 0.3}});
        if (two) {
            double d2 = U_(0.15, 0.5), st = U_(0.07, 0.14);
            add("modal", {{"name", "note2"}, {"model", mm}, {"freq", f2}, {"partials", 8}, {"decay", d2}, {"brightness", 0.75}, {"strike", 0.2}, {"start", st}, {"dur", 0.8}, {"attack", 0.0004}, {"gain", -5}, {"reverb", 0.3}});
        }
        const char* sw = g.pickS({"sine", "triangle"});
        double fi = U_(0, 1.5);
        add("osc", {{"name", "soft"}, {"wave", sw}, {"freqStart", f1}, {"freqEnd", f1}, {"fmRatio", 2}, {"fmIndex", fi}, {"fmDecay", 5}, {"dur", 0.4}, {"attack", 0.004}, {"curve", 3}, {"gain", -12}, {"reverb", 0.2}});
        add("noise", {{"name", "tick"}, {"color", "velvet"}, {"density", 3000}, {"width", 0.5}, {"dur", 0.01}, {"attack", 0.0002}, {"curve", 6}, {"fcStart", 3000}, {"fcEnd", 3000}, {"gain", -12}}, HP);
        extra = {{"revDecay", 0.4 + Sp * 1.2}, {"revMix", 0.3 + Sp * 0.4}};
    } else {  // alarm
        int n = I(3, 8);
        double iv = U_(0.14, 0.3), f = LU(500, 1800);
        KV rp = {{"repeat", n}, {"repInterval", iv}, {"repJitter", 0}, {"repDecay", 1}, {"repVar", 0}};
        const char* wv = g.pickS({"square", "triangle", "saw"});
        double fmr = g.pickD({1, 2, 3.01}), fmi = U_(0, 2), vc = g.pickD({1, 2, 3}), dt = U_(3, 15), dm = U_(0.45, 0.7);
        double c0 = LU(3000, 8000), c1 = LU(3000, 8000);
        add("osc", {{"name", "beep"}, {"wave", wv}, {"freqStart", f}, {"freqEnd", f}, {"fmRatio", fmr}, {"fmIndex", fmi}, {"fmDecay", 2}, {"voices", vc}, {"detune", dt}, {"dur", iv * dm}, {"attack", 0.003}, {"hold", iv * 0.2}, {"curve", 3}, {"filter", "lowpass"}, {"fcStart", c0}, {"fcEnd", c1}, {"q", 1}, {"drive", 0.2}, {"gain", -3}, {"reverb", 0.2}}, rp);
        add("modal", {{"name", "ping"}, {"model", "tube"}, {"freq", f * 2}, {"partials", 6}, {"decay", 0.08}, {"brightness", 0.8}, {"strike", 0.3}, {"dur", 0.2}, {"gain", -12}, {"reverb", 0.2}}, rp);
        add("noise", {{"name", "case"}, {"color", "white"}, {"width", 0.5}, {"dur", 0.01}, {"attack", 0.0002}, {"curve", 6}, {"fcStart", 4000}, {"fcEnd", 4000}, {"gain", -16}}, HP, rp);
        extra = {{"revDecay", 0.5 + Sp * 1.5}};
    }

    Json master = Json::object();
    double rd = 0.25 + Sp * Sp * 5.5;
    double dmp = g.U(0.25, 0.65);
    double pre = g.U(0, 30) * (0.3 + Sp);
    double early = 0.3 + g.U(0, 0.5);
    double mod = g.U(0.3, 0.6);
    double wid = g.U(0.95, 1.35);
    master.set("revMix", Json(0.2 + 0.8 * Sp));
    master.set("revSize", Json(0.5 + Sp * 1.4));
    master.set("revDecay", Json(rd));
    master.set("revDamp", Json(dmp));
    master.set("revPre", Json(pre));
    master.set("revEarly", Json(early));
    master.set("revMod", Json(mod));
    master.set("width", Json(wid));
    master.set("ceiling", Json(-1));
    master.set("normalize", Json("on"));
    master.set("sampleRate", Json(48000));
    for (auto& kv : extra) master.set(kv.first, kv.second);

    Json raw = Json::object();
    raw.set("seed", Json((double)seed));
    raw.set("master", master);
    raw.set("layers", layers);
    Recipe out = normRecipe(raw);
    out.category = cat;
    return out;
}

Recipe mutate(const Recipe& in, double amount, int64_t seedIn) {
    Recipe R = in;
    Rng r(seedIn < 0 ? randomSeed() : (uint32_t)seedIn);
    auto gauss = [&]() { double s = 0; for (int i = 0; i < 4; i++) s += r(); return (s - 2) * 1.7; };
    auto jit = [&](Bag& obj, const std::vector<Param>& list, double pr, const std::vector<std::string>& skip) {
        for (const Param& p : list) {
            if (std::find(skip.begin(), skip.end(), p.key) != skip.end()) continue;
            if (p.isEnum) {
                if (r() < 0.06 * amount * 4 && p.options.size() > 1) {
                    const std::string& pick = p.options[(size_t)std::floor(r() * p.options.size())];
                    if (p.numericEnum) obj.n[p.key] = atof(pick.c_str()); else obj.s[p.key] = pick;
                }
                continue;
            }
            if (r() > pr) continue;
            double v = obj.n[p.key];
            if (p.log) v *= std::exp(gauss() * amount * std::log(p.max / p.min) * 0.25);
            else v += gauss() * amount * (p.max - p.min) * 0.25;
            obj.n[p.key] = clampd(v, p.min, p.max);
        }
    };
    std::vector<Param> common;
    for (auto& g : commonGroups()) for (auto& p : g.params) common.push_back(p);
    std::vector<Param> master;
    for (auto& g : masterGroups()) for (auto& p : g.params) master.push_back(p);
    for (auto& l : R.layers) {
        const TypeDef* T = findType(l.type);
        jit(l, T->params, 0.6, {});
        jit(l, common, 0.3, {"start", "pan", "move", "dur", "repeat", "repInterval", "haas"});
    }
    jit(R.master, master, 0.2, {"ceiling", "sampleRate", "normalize", "compThresh", "compRatio"});
    R.seed = (uint32_t)((R.seed + 1 + (uint32_t)std::floor(r() * 1000)) % 1000000000u);
    Recipe out = normRecipe(recipeToJson(R));
    out.category = in.category;
    return out;
}

}  // namespace strata
