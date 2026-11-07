// Parameter schema, recipe normalisation, UI schema export and the AI brief.
#include <algorithm>
#include <cmath>
#include <sstream>

#include "strata.hpp"

namespace strata {

static double clampd(double x, double a, double b) { return x < a ? a : (x > b ? b : x); }

static Param P(const char* key, const char* label, double mn, double mx, double def,
               const char* unit = "", bool log = false, bool isInt = false) {
    Param p;
    p.key = key; p.label = label; p.min = mn; p.max = mx; p.def = def;
    p.unit = unit; p.log = log; p.isInt = isInt;
    return p;
}
static Param EN(const char* key, const char* label, std::vector<std::string> opts, const char* def,
                bool numeric = false) {
    Param p;
    p.key = key; p.label = label; p.isEnum = true; p.options = std::move(opts);
    p.defStr = def; p.numericEnum = numeric;
    if (numeric) p.def = atof(def);
    return p;
}

static const std::vector<std::string> NOISE_COLORS = {"white", "pink", "brown", "blue", "violet", "velvet", "crackle"};
static const std::vector<std::string> WAVES = {"sine", "triangle", "saw", "square", "pulse"};
static const std::vector<std::string> MODELS = {"string", "bar", "plate", "membrane", "tube", "bell", "glass", "wood", "spring", "chaos"};
static const std::vector<std::string> VOWELS = {"a", "e", "i", "o", "u", "ae", "uh"};

const std::vector<Group>& commonGroups() {
    static const std::vector<Group> g = {
        {"Level and timing", {
            P("start", "Start", 0, 6, 0, "s"),
            P("dur", "Length", 0.02, 8, 1, "s", true),
            P("gain", "Layer peak", -48, 6, -6, "dB"),
            P("pan", "Pan", -1, 1, 0)}},
        {"Amplitude envelope", {
            P("attack", "Attack", 0.0002, 2, 0.003, "s", true),
            P("hold", "Hold", 0, 2, 0, "s"),
            P("curve", "Decay steepness", 0.1, 14, 4)}},
        {"Filter sweep", {
            EN("filter", "Filter", {"off", "lowpass", "highpass", "bandpass", "notch"}, "off"),
            P("fcStart", "Cutoff start", 20, 20000, 8000, "Hz", true),
            P("fcEnd", "Cutoff end", 20, 20000, 8000, "Hz", true),
            P("sweep", "Sweep shape", 0.2, 6, 1),
            P("q", "Resonance", 0.3, 24, 0.8, "", true),
            P("lowcut", "Low cut", 20, 2000, 20, "Hz", true),
            P("highcut", "High cut", 200, 20000, 20000, "Hz", true)}},
        {"Color and sends", {
            P("drive", "Saturation", 0, 1, 0),
            P("reverb", "Reverb send", 0, 1, 0.2),
            P("echo", "Echo send", 0, 1, 0)}},
        {"Motion and width", {
            P("move", "Pan travel", -2, 2, 0),
            P("tremRate", "Tremolo rate", 0, 40, 0, "Hz"),
            P("tremDepth", "Tremolo depth", 0, 1, 0),
            P("haas", "Width delay", 0, 30, 0, "ms")}},
        {"Repeats", {
            P("repeat", "Repeat count", 1, 32, 1, "", false, true),
            P("repInterval", "Repeat spacing", 0.02, 2, 0.25, "s", true),
            P("repJitter", "Timing looseness", 0, 1, 0.15),
            P("repDecay", "Level per repeat", 0.3, 1.2, 1),
            P("repVar", "Loudness and pitch variation", 0, 1, 0.3)}},
    };
    return g;
}

const std::vector<TypeDef>& types() {
    static const std::vector<TypeDef> T = [] {
        std::vector<TypeDef> t;
        auto add = [&](const char* id, const char* label, const char* about, std::vector<Param> params,
                       std::unordered_map<std::string, double> defs = {}) {
            TypeDef d; d.id = id; d.label = label; d.about = about; d.params = std::move(params); d.defs = std::move(defs);
            t.push_back(std::move(d));
        };
        add("noise", "Noise", "Colored noise, sparse clicks or crackle, with optional flutter. Air, rushes, hiss, texture, transients.", {
            EN("color", "Color", NOISE_COLORS, "white"),
            P("width", "Stereo width", 0, 1, 0.7),
            P("density", "Click density", 5, 20000, 800, "Hz", true),
            P("modRate", "Flutter rate", 0, 60, 0, "Hz"),
            P("modDepth", "Flutter depth", 0, 1, 0)});
        add("osc", "Osc", "Band-limited oscillator with pitch glide, FM, unison and a sub. Thumps, zaps, drones, risers, tonal bodies.", {
            EN("wave", "Wave", WAVES, "sine"),
            P("pulseW", "Pulse width", 0.05, 0.95, 0.5),
            P("freqStart", "Pitch start", 20, 12000, 440, "Hz", true),
            P("freqEnd", "Pitch end", 20, 12000, 440, "Hz", true),
            P("pitchCurve", "Glide speed", 0.1, 14, 6),
            P("fmRatio", "FM ratio", 0.25, 16, 1),
            P("fmIndex", "FM depth", 0, 20, 0),
            P("fmDecay", "FM decay", 0, 12, 3),
            P("voices", "Unison voices", 1, 7, 1, "", false, true),
            P("detune", "Unison detune", 0, 100, 12, "ct"),
            P("vibRate", "Vibrato rate", 0, 20, 0, "Hz"),
            P("vibDepth", "Vibrato depth", 0, 1200, 0, "ct"),
            P("sub", "Sub octave", 0, 1, 0)});
        add("modal", "Modal", "Resonant body: a struck object modeled as decaying partials. Metal, glass, wood, bells, drums, tubes.", {
            P("freq", "Fundamental", 30, 8000, 300, "Hz", true),
            EN("model", "Material model", MODELS, "bar"),
            P("partials", "Partials", 1, 48, 16, "", false, true),
            P("stiffness", "Stiffness", 0, 1, 0.3),
            P("decay", "Ring time (T60)", 0.03, 8, 1.2, "s", true),
            P("tilt", "High partial damping", 0, 8, 2),
            P("brightness", "Strike hardness", 0, 1, 0.6),
            P("strikePos", "Strike position", 0.05, 0.5, 0.2),
            P("beat", "Beating", 0, 8, 0, "Hz"),
            P("strike", "Contact noise", 0, 1, 0.3)},
            {{"curve", 0.3}, {"attack", 0.0004}, {"dur", 1.5}, {"reverb", 0.25}});
        add("string", "String", "Karplus-Strong plucked or struck string with loss filtering. Plucks, twangs, pipes, resonant tails.", {
            P("freq", "Pitch", 40, 4000, 220, "Hz", true),
            P("decay", "Sustain (T60)", 0.05, 8, 1.5, "s", true),
            P("damp", "Damping", 0, 1, 0.3),
            P("bright", "Pick brightness", 0, 1, 0.7),
            P("pickPos", "Pick position", 0.05, 0.5, 0.2)},
            {{"curve", 0.3}, {"attack", 0.0004}, {"dur", 1.5}});
        add("grain", "Grain", "Granular cloud of tiny tone or noise grains with a density glide. Sparkle, shimmer, swarm, rain, fizz.", {
            EN("source", "Grain source", {"tone", "noise"}, "tone"),
            P("densStart", "Density start", 1, 2000, 80, "/s", true),
            P("densEnd", "Density end", 1, 2000, 80, "/s", true),
            P("grainMs", "Grain size", 1, 200, 12, "ms", true),
            P("fLo", "Low pitch", 40, 16000, 800, "Hz", true),
            P("fHi", "High pitch", 40, 16000, 6000, "Hz", true),
            P("scatter", "Stereo scatter", 0, 1, 0.8)},
            {{"curve", 2}});
        add("debris", "Debris", "Random physical hits that speed up or slow down: scatter, bounces, rubble, coins, glass shards, footsteps.", {
            P("rate", "Hits per second", 1, 400, 30, "/s", true),
            P("accel", "Speed change", -1, 1, 0),
            P("fLo", "Low pitch", 40, 12000, 500, "Hz", true),
            P("fHi", "High pitch", 40, 12000, 4000, "Hz", true),
            P("hitMs", "Hit ring time", 3, 600, 60, "ms", true),
            P("partials", "Partials per hit", 1, 6, 3, "", false, true),
            P("hardness", "Hardness", 0, 1, 0.6),
            P("velVar", "Velocity variation", 0, 1, 0.7)},
            {{"curve", 2}});
        add("wind", "Wind", "Gusting air: noise through three wandering resonant bands, with optional howl and turbulence. Gales, drafts, whooshes, breath.", {
            P("wCenter", "Center pitch", 60, 4000, 500, "Hz", true),
            P("wQ", "Band sharpness", 0.5, 12, 3, "", true),
            P("gustRate", "Gust rate", 0.05, 4, 0.4, "Hz", true),
            P("gustDepth", "Gust depth", 0, 1.5, 0.6),
            P("howl", "Howl", 0, 1, 0.2),
            P("turb", "Turbulence", 0, 1, 0.3),
            P("width", "Stereo width", 0, 1, 0.8)},
            {{"curve", 0.6}, {"attack", 0.4}, {"dur", 4}});
        add("bubble", "Bubble", "Resonant air bubbles with an upward pitch chirp, clustered like real water. Drips, streams, boiling, gurgles, slime.", {
            P("rate", "Bubbles per second", 0.5, 300, 20, "/s", true),
            P("accel", "Speed change", -1, 1, 0),
            P("fLo", "Largest bubble", 100, 6000, 300, "Hz", true),
            P("fHi", "Smallest bubble", 200, 12000, 2500, "Hz", true),
            P("rise", "Pitch rise", 0, 1.5, 0.6),
            P("ring", "Ring (Q)", 3, 100, 20, "", true),
            P("cluster", "Clustering", 0, 1, 0.2),
            P("scatter", "Stereo scatter", 0, 1, 0.7)},
            {{"curve", 0.6}, {"attack", 0.005}, {"dur", 2}});
        add("motor", "Motor", "Engine and motor model: a firing-pulse harmonic stack shaped by an exhaust resonance, with misfire roughness, whine and intake noise. Engines, servos, rotors, hums.", {
            P("fStart", "Firing rate start", 5, 800, 40, "Hz", true),
            P("fEnd", "Firing rate end", 5, 800, 60, "Hz", true),
            P("rampShape", "Ramp shape", 0.2, 5, 1),
            P("harmonics", "Harmonics", 4, 80, 40, "", false, true),
            P("tilt", "Spectral slope", 0, 3, 1.2),
            P("formant", "Body resonance", 60, 4000, 350, "Hz", true),
            P("resBoost", "Resonance amount", 0, 1, 0.6),
            P("rough", "Roughness and misfire", 0, 1, 0.25),
            P("half", "Half-order rumble", 0, 1, 0),
            P("whine", "Turbine whine", 0, 1, 0),
            P("noise", "Intake noise", 0, 1, 0.15)},
            {{"curve", 0.5}, {"attack", 0.05}, {"dur", 2.5}});
        add("voice", "Voice", "Formant voice: glottal source through a morphing vowel filter bank with growl, breath and jitter. Creatures, roars, moans, chants, vocal textures.", {
            P("pStart", "Pitch start", 40, 800, 140, "Hz", true),
            P("pEnd", "Pitch end", 40, 800, 110, "Hz", true),
            P("pitchCurve", "Glide speed", 0.1, 14, 3),
            EN("vowelA", "Start vowel", VOWELS, "a"),
            EN("vowelB", "End vowel", VOWELS, "o"),
            P("morph", "Morph shape", 0.2, 6, 1),
            P("shift", "Formant scale (size)", 0.5, 2, 1),
            P("growl", "Growl", 0, 1, 0),
            P("growlRate", "Growl rate", 15, 90, 45, "Hz"),
            P("breath", "Breath", 0, 1, 0.1),
            P("tension", "Source brightness", 0, 1, 0.5),
            P("vibRate", "Vibrato rate", 0, 12, 5, "Hz"),
            P("vibDepth", "Vibrato depth", 0, 300, 20, "ct"),
            P("jitter", "Pitch jitter", 0, 1, 0.2)},
            {{"curve", 2}, {"attack", 0.03}, {"dur", 1.2}});
        add("friction", "Friction", "Stick-slip friction into a resonant body. Low rates make creaks and ratchets, high rates make squeaks and squeals, grit makes scrapes.", {
            P("rateStart", "Slip rate start", 2, 4000, 40, "Hz", true),
            P("rateEnd", "Slip rate end", 2, 4000, 60, "Hz", true),
            P("rateCurve", "Rate glide", 0.1, 14, 2),
            P("pulse", "Impulse to saw", 0, 1, 0.3),
            P("jitter", "Irregularity", 0, 1, 0.3),
            P("grit", "Grit", 0, 1, 0.2),
            P("resFreq", "Body resonance", 100, 9000, 900, "Hz", true),
            P("rq", "Body ring (Q)", 2, 100, 18, "", true),
            P("inharm", "Inharmonicity", 0, 1, 0.3),
            P("pressure", "Pressure wobble", 0, 1, 0.4)},
            {{"curve", 1}, {"attack", 0.05}, {"dur", 1.2}});
        return t;
    }();
    return T;
}

const TypeDef* findType(const std::string& id) {
    for (auto& t : types()) if (t.id == id) return &t;
    return nullptr;
}

const std::vector<Group>& masterGroups() {
    static const std::vector<Group> g = {
        {"Room (feedback delay network)", {
            P("revMix", "Return level", 0, 1.5, 0.6),
            P("revSize", "Room size", 0.3, 2.5, 1),
            P("revDecay", "Decay time (T60)", 0.2, 10, 1.8, "s", true),
            P("revDamp", "High damping", 0, 1, 0.4),
            P("revPre", "Pre-delay", 0, 120, 12, "ms"),
            P("revEarly", "Early reflections", 0, 1.5, 0.5),
            P("revMod", "Modulation", 0, 1, 0.4),
            P("revLow", "Low cut on send", 20, 800, 120, "Hz", true)}},
        {"Ping-pong echo", {
            P("echoTime", "Time", 20, 900, 260, "ms", true),
            P("echoFb", "Feedback", 0, 0.9, 0.35),
            P("echoTone", "Tone", 500, 16000, 4500, "Hz", true)}},
        {"Tone and space", {
            P("lowShelf", "Low shelf 120 Hz", -12, 12, 0, "dB"),
            P("midGain", "Mid bell", -12, 12, 0, "dB"),
            P("midFreq", "Mid frequency", 150, 8000, 1200, "Hz", true),
            P("midQ", "Mid width", 0.3, 6, 1),
            P("highShelf", "High shelf 6 kHz", -12, 12, 0, "dB"),
            P("distance", "Distance", 0, 1, 0),
            P("width", "Stereo width", 0, 2, 1),
            P("drive", "Master saturation", 0, 1, 0)}},
        {"Dynamics", {
            P("transient", "Transient shaping", -1, 1, 0),
            P("compThresh", "Compressor threshold (0 = off)", -40, 0, 0, "dB"),
            P("compRatio", "Ratio", 1, 20, 3, "", true),
            P("compAttack", "Attack", 0.1, 100, 8, "ms", true),
            P("compRelease", "Release", 20, 1000, 120, "ms", true),
            P("compMakeup", "Makeup gain", 0, 24, 0, "dB")}},
        {"Output", {
            P("ceiling", "Limiter ceiling", -12, 0, -1, "dB"),
            EN("normalize", "Normalize to ceiling", {"on", "off"}, "on"),
            EN("sampleRate", "Sample rate", {"44100", "48000", "96000"}, "48000", true)}},
    };
    return g;
}

const std::vector<std::pair<std::string, std::string>>& categories() {
    static const std::vector<std::pair<std::string, std::string>> c = {
        {"impact", "Impact"}, {"explosion", "Explosion"}, {"weapon", "Gunshot"}, {"whoosh", "Whoosh"},
        {"magic", "Magic"}, {"zap", "Energy zap"}, {"creature", "Creature"}, {"vehicle", "Vehicle"},
        {"machine", "Machine"}, {"water", "Water"}, {"rain", "Rain"}, {"glass", "Glass break"},
        {"metal", "Metal clang"}, {"creak", "Creak and scrape"}, {"footsteps", "Footsteps"},
        {"wind", "Wind"}, {"ui", "Interface tone"}, {"alarm", "Alarm"}};
    return c;
}

// ---------- normalisation ----------
static void normParams(const Json& raw, const std::vector<Param>& list,
                       const std::unordered_map<std::string, double>* defs, Bag& out) {
    for (const Param& p : list) {
        const Json* v = raw.isObj() ? raw.find(p.key) : nullptr;
        double d = p.def;
        if (defs) { auto it = defs->find(p.key); if (it != defs->end()) d = it->second; }
        if (p.isEnum) {
            if (p.numericEnum) {
                double x = p.def;
                if (v && v->isNum()) {
                    for (auto& o : p.options) if (atof(o.c_str()) == v->n) { x = v->n; break; }
                }
                out.n[p.key] = x;
            } else {
                std::string x = p.defStr;
                if (v && v->isStr() && std::find(p.options.begin(), p.options.end(), v->s) != p.options.end()) x = v->s;
                out.s[p.key] = x;
            }
        } else {
            double x = (v && v->isNum() && std::isfinite(v->n)) ? v->n : d;
            x = clampd(x, p.min, p.max);
            if (p.isInt) x = std::floor(x + 0.5);
            out.n[p.key] = x;
        }
    }
}

static bool normLayer(const Json& raw, Layer& L) {
    if (!raw.isObj()) return false;
    const Json* ty = raw.find("type");
    if (!ty || !ty->isStr()) return false;
    const TypeDef* T = findType(ty->s);
    if (!T) return false;
    L.type = T->id;
    const Json* nm = raw.find("name");
    if (nm && nm->isStr()) L.name = nm->s.substr(0, 40);
    const Json* mu = raw.find("mute");
    const Json* so = raw.find("solo");
    L.mute = mu && ((mu->t == Json::Bool && mu->b) || (mu->isNum() && mu->n != 0));
    L.solo = so && ((so->t == Json::Bool && so->b) || (so->isNum() && so->n != 0));
    normParams(raw, T->params, &T->defs, L);
    for (auto& g : commonGroups()) normParams(raw, g.params, &T->defs, L);
    double dur = L.n["dur"];
    L.n["attack"] = std::min(L.n["attack"], dur * 0.9);
    L.n["hold"] = std::min(L.n["hold"], std::max(0.0, dur - L.n["attack"] - 0.001));
    if (L.n.count("fLo") && L.n.count("fHi") && L.n["fHi"] < L.n["fLo"]) std::swap(L.n["fLo"], L.n["fHi"]);
    return true;
}

Recipe normRecipe(const Json& raw) {
    Recipe R;
    double seed = 1;
    if (raw.isObj()) {
        const Json* s = raw.find("seed");
        if (s && s->isNum() && std::isfinite(s->n)) seed = clampd(std::floor(s->n), 0, 999999999);
        std::vector<Param> flat;
        for (auto& g : masterGroups()) for (auto& p : g.params) flat.push_back(p);
        const Json* m = raw.find("master");
        normParams(m ? *m : Json::object(), flat, nullptr, R.master);
        const Json* ls = raw.find("layers");
        if (ls && ls->isArr()) {
            for (size_t i = 0; i < ls->a.size() && i < 16; i++) {
                Layer L;
                if (normLayer(ls->a[i], L)) R.layers.push_back(std::move(L));
            }
        }
    } else {
        std::vector<Param> flat;
        for (auto& g : masterGroups()) for (auto& p : g.params) flat.push_back(p);
        normParams(Json::object(), flat, nullptr, R.master);
    }
    R.seed = (uint32_t)seed;
    return R;
}

Layer defaultLayer(const std::string& type) {
    Json j = Json::object();
    j.set("type", type);
    Layer L;
    normLayer(j, L);
    return L;
}

static Json paramValue(const Bag& b, const Param& p) {
    if (p.isEnum && !p.numericEnum) return Json(b.S(p.key.c_str()));
    return Json(b.N(p.key.c_str()));
}

Json recipeToJson(const Recipe& r) {
    Json out = Json::object();
    out.set("seed", Json((double)r.seed));
    Json m = Json::object();
    for (auto& g : masterGroups()) for (auto& p : g.params) m.set(p.key, paramValue(r.master, p));
    out.set("master", m);
    Json ls = Json::array();
    for (auto& L : r.layers) {
        const TypeDef* T = findType(L.type);
        Json j = Json::object();
        j.set("type", L.type);
        j.set("name", L.name);
        j.set("mute", Json(L.mute));
        j.set("solo", Json(L.solo));
        for (auto& p : T->params) j.set(p.key, paramValue(L, p));
        for (auto& g : commonGroups()) for (auto& p : g.params) j.set(p.key, paramValue(L, p));
        ls.push(j);
    }
    out.set("layers", ls);
    return out;
}
std::string recipeToString(const Recipe& r, int indent) { return recipeToJson(r).dump(indent); }

// ---------- UI schema ----------
static Json paramSchema(const Param& p, const std::unordered_map<std::string, double>* defs) {
    Json j = Json::object();
    j.set("key", p.key);
    j.set("label", p.label);
    if (p.isEnum) {
        Json o = Json::array();
        for (auto& s : p.options) o.push(p.numericEnum ? Json(atof(s.c_str())) : Json(s));
        j.set("options", o);
        j.set("def", p.numericEnum ? Json(p.def) : Json(p.defStr));
    } else {
        double d = p.def;
        if (defs) { auto it = defs->find(p.key); if (it != defs->end()) d = it->second; }
        j.set("min", Json(p.min));
        j.set("max", Json(p.max));
        j.set("def", Json(d));
        j.set("log", Json(p.log));
        j.set("int", Json(p.isInt));
        j.set("unit", p.unit);
    }
    return j;
}
static Json groupsSchema(const std::vector<Group>& gs, const std::unordered_map<std::string, double>* defs) {
    Json a = Json::array();
    for (auto& g : gs) {
        Json gj = Json::object();
        gj.set("group", g.name);
        Json ps = Json::array();
        for (auto& p : g.params) ps.push(paramSchema(p, defs));
        gj.set("params", ps);
        a.push(gj);
    }
    return a;
}
std::string schemaJson() {
    Json root = Json::object();
    Json ts = Json::array();
    for (auto& T : types()) {
        Json t = Json::object();
        t.set("id", T.id);
        t.set("label", T.label);
        t.set("about", T.about);
        Json ps = Json::array();
        for (auto& p : T.params) ps.push(paramSchema(p, &T.defs));
        t.set("params", ps);
        // common groups with this type's default overrides applied
        t.set("common", groupsSchema(commonGroups(), &T.defs));
        ts.push(t);
    }
    root.set("types", ts);
    root.set("master", groupsSchema(masterGroups(), nullptr));
    Json cs = Json::array();
    for (auto& c : categories()) { Json x = Json::array(); x.push(c.first); x.push(c.second); cs.push(x); }
    root.set("categories", cs);
    return root.dump();
}

// ---------- AI brief ----------
static std::string fmtNum(double v) { std::string s; Json::num(s, v); return s; }
static std::string fmtRange(const Param& p, const std::unordered_map<std::string, double>* defs) {
    if (p.isEnum) {
        std::string s = "one of ";
        for (size_t i = 0; i < p.options.size(); i++) {
            if (i) s += ", ";
            s += p.numericEnum ? p.options[i] : "\"" + p.options[i] + "\"";
        }
        s += " (default " + (p.numericEnum ? fmtNum(p.def) : "\"" + p.defStr + "\"") + ")";
        return s;
    }
    double d = p.def;
    if (defs) { auto it = defs->find(p.key); if (it != defs->end()) d = it->second; }
    std::string s = fmtNum(p.min) + " to " + fmtNum(p.max);
    if (!p.unit.empty()) s += " " + p.unit;
    if (p.log) s += ", log-scaled";
    if (p.isInt) s += ", integer";
    s += " (default " + fmtNum(d) + ")";
    return s;
}
std::string aiPrompt() {
    std::ostringstream o;
    o << "You write sound-effect recipes for Strata, a procedural synthesizer. Reply with ONE JSON object and nothing else.\n\n";
    o << "Recipe shape: {\"seed\": integer 0-999999999, \"master\": {...optional master params...}, \"layers\": [ {\"type\": \"...\", \"name\": \"optional label\", ...params} ]}\n";
    o << "Any omitted parameter takes its default. Values outside a range are clamped. Up to 16 layers. All layers play at once, offset by \"start\" seconds. \"gain\" is the layer peak level in dB, so quieter support layers get lower gain.\n";
    o << "The same recipe and seed always render the same audio. Change the seed for a variation of the same sound.\n\nLAYER TYPES\n";
    for (auto& T : types()) {
        o << "- \"" << T.id << "\": " << T.about << "\n";
        for (auto& p : T.params) o << "    " << p.key << " (" << p.label << "): " << fmtRange(p, nullptr) << "\n";
        if (!T.defs.empty()) {
            Json d = Json::object();
            for (auto& kv : T.defs) d.set(kv.first, Json(kv.second));
            o << "    type defaults that differ: " << d.dump() << "\n";
        }
    }
    o << "\nPARAMETERS EVERY LAYER HAS\n";
    for (auto& g : commonGroups()) for (auto& p : g.params) o << "  " << p.key << " (" << p.label << "): " << fmtRange(p, nullptr) << "\n";
    o << "Envelope: rises over attack, holds, then decays toward silence at the end of \"dur\". Higher \"curve\" means a faster initial drop. Filter cutoff glides from fcStart to fcEnd over the layer, \"sweep\" below 1 makes it move early.\n";
    o << "Repeats: \"repeat\" plays the layer N times, \"repInterval\" seconds apart. Layers that share the same repeat, repInterval and repJitter stay in sync and share the same loudness variation, so a footstep thud, tap and scuff land together. \"repVar\" varies loudness and pitch per hit.\n";
    o << "Motion: \"pan\" is the start position and \"move\" is how far the pan travels over the layer (a pass-by uses pan -0.9, move 1.8). \"haas\" delays the right channel for width.\n\nMASTER PARAMETERS\n";
    for (auto& g : masterGroups()) for (auto& p : g.params) o << "  " << p.key << " (" << p.label << "): " << fmtRange(p, nullptr) << "\n";
    o << "The compressor is off when compThresh is 0. Set it to about -16 with ratio 3 to 5 for punchy impacts and gunshots.\n\nHOW TO MAKE IT SOUND REAL\n";
    o << "- Build every sound as a stack of 3 to 6 layers: a short transient (1 to 60 ms), a body (the pitched or resonant core), a tail (noise or reverb, longer and quieter), and optionally a sweetener (grain, debris or bubble) at -12 to -20 dB.\n";
    o << "- Use \"modal\" for anything struck or resonant and choose the material to match: bar for metal bars, plate for sheet metal, glass for glass, wood for blocks and knocks, membrane for drums and thuds, tube for pipes and casings, bell for bells, string for wires, spring for springs and reverb tanks.\n";
    o << "- Use \"noise\" through a sweeping lowpass or bandpass for air movement and \"wind\" for gusting, howling air. Brown or pink noise gives weight, white or blue gives hiss.\n";
    o << "- Use \"osc\" with a fast downward pitch glide (high pitchCurve) and a sub for weight, FM for metallic or electric character.\n";
    o << "- Use \"voice\" for growls, roars, moans and vocal textures: low pStart, a vowel morph, growl and breath. Lower \"shift\" makes a larger creature.\n";
    o << "- Use \"motor\" for engines, servos and rotors, and \"friction\" for creaks (rate 5 to 40, low pulse), squeaks (rate 600 to 2500, pulse near 1) and scrapes. Use \"bubble\" for water and \"debris\" for rain, shards, rubble and coins.\n";
    o << "- Offset layers by 0 to 40 ms and vary lengths so they do not stack into one flat blob. Never give two layers the same decay.\n";
    o << "- Use \"drive\" sparingly (0.1 to 0.4) for grit. Sustained loudness comes from a longer body, not high gain.\n";
    o << "- Reverb sends place the sound in a space. Short revDecay (0.3 to 0.8 s) for small rooms, 2 to 5 s for halls and caves. Keep dry transients at a low send. Raise \"distance\" to push a sound back.\n";
    o << "- Keep total length matched to the event: UI click 0.05 to 0.3 s, impact 0.5 to 2 s, explosion 2 to 5 s.\n";
    o << "- Describe the sound by choosing parameters. Do not rely on any preset or named sound.\n\n";
    o << "Format example (a tiny two-layer sound, not a template to copy): {\"seed\":7,\"master\":{\"revDecay\":1.2},\"layers\":[{\"type\":\"noise\",\"name\":\"click\",\"color\":\"white\",\"dur\":0.02,\"filter\":\"highpass\",\"fcStart\":2500,\"fcEnd\":2500,\"gain\":-3},{\"type\":\"modal\",\"name\":\"body\",\"model\":\"wood\",\"freq\":180,\"decay\":0.25,\"dur\":0.5,\"gain\":-5}]}\n\n";
    o << "Now write the recipe for this sound: [DESCRIBE THE SOUND HERE]";
    return o.str();
}

}  // namespace strata
