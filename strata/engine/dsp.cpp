// Strata DSP: layer generators, reverb, master chain and the renderer.
// The synthesis models follow the original web prototype so recipes carry over unchanged.
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <functional>
#include <thread>

#include "strata.hpp"

namespace strata {
namespace {

const double TAU = 6.283185307179586476925286766559;
const double PI_ = 3.14159265358979323846;

inline double clampd(double x, double a, double b) { return x < a ? a : (x > b ? b : x); }
inline double dBtoLin(double x) { return std::pow(10.0, x / 20.0); }
inline double jsRound(double x) { return std::floor(x + 0.5); }

// mulberry32, identical stream to the web prototype
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
uint32_t seedFrom(double x) { return (uint32_t)(uint64_t)x; }

using Buf = std::vector<float>;
using Coef = std::array<double, 5>;
enum FT { LP, HP, BP, NOTCH };

Coef bq(FT type, double f, double q, double sr) {
    double w = TAU * clampd(f, 10, sr * 0.45) / sr, c = std::cos(w), s = std::sin(w), al = s / (2 * q);
    double b0, b1, b2, a0 = 1 + al, a1 = -2 * c, a2 = 1 - al;
    switch (type) {
        case LP: b0 = (1 - c) / 2; b1 = 1 - c; b2 = b0; break;
        case HP: b0 = (1 + c) / 2; b1 = -(1 + c); b2 = b0; break;
        case BP: b0 = al; b1 = 0; b2 = -al; break;
        default: b0 = 1; b1 = -2 * c; b2 = 1;
    }
    return {b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0};
}
Coef shelf(bool low, double f, double gdb, double sr) {
    double A = std::pow(10.0, gdb / 40), w = TAU * f / sr, c = std::cos(w), s = std::sin(w);
    double al = s / 2 * std::sqrt(2.0), sq = 2 * std::sqrt(A) * al;
    double b0, b1, b2, a0, a1, a2;
    if (low) {
        b0 = A * ((A + 1) - (A - 1) * c + sq); b1 = 2 * A * ((A - 1) - (A + 1) * c); b2 = A * ((A + 1) - (A - 1) * c - sq);
        a0 = (A + 1) + (A - 1) * c + sq; a1 = -2 * ((A - 1) + (A + 1) * c); a2 = (A + 1) + (A - 1) * c - sq;
    } else {
        b0 = A * ((A + 1) + (A - 1) * c + sq); b1 = -2 * A * ((A - 1) + (A + 1) * c); b2 = A * ((A + 1) + (A - 1) * c - sq);
        a0 = (A + 1) - (A - 1) * c + sq; a1 = 2 * ((A - 1) - (A + 1) * c); a2 = (A + 1) - (A - 1) * c - sq;
    }
    return {b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0};
}
Coef peaking(double f, double gdb, double q, double sr) {
    double A = std::pow(10.0, gdb / 40), w = TAU * f / sr, c = std::cos(w), al = std::sin(w) / (2 * q), a0 = 1 + al / A;
    return {(1 + al * A) / a0, -2 * c / a0, (1 - al * A) / a0, -2 * c / a0, (1 - al / A) / a0};
}
void applyBq(Buf& x, const Coef& c) {
    double x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (size_t i = 0; i < x.size(); i++) {
        double xi = x[i];
        double y = c[0] * xi + c[1] * x1 + c[2] * x2 - c[3] * y1 - c[4] * y2;
        x2 = x1; x1 = xi; y2 = y1; y1 = y;
        x[i] = (float)y;
    }
}
FT ftOf(const std::string& s) {
    if (s == "lowpass") return LP;
    if (s == "highpass") return HP;
    if (s == "bandpass") return BP;
    return NOTCH;
}
void sweepFilter(Buf& x, const Layer& l, double sr) {
    const std::string& ft = l.S("filter");
    if (ft == "off") return;
    FT type = ftOf(ft);
    const double fcS = l.N("fcStart"), fcE = l.N("fcEnd"), sw = l.N("sweep"), q = l.N("q");
    const size_t n = x.size();
    const int B = 16;
    double x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (size_t s = 0; s < n; s += B) {
        double xr = clampd((s + B / 2.0) / n, 0, 1), u = std::pow(xr, sw), f = fcS * std::pow(fcE / fcS, u);
        Coef c = bq(type, f, q, sr);
        size_t e = std::min(n, s + B);
        for (size_t i = s; i < e; i++) {
            double xi = x[i];
            double y = c[0] * xi + c[1] * x1 + c[2] * x2 - c[3] * y1 - c[4] * y2;
            x2 = x1; x1 = xi; y2 = y1; y1 = y;
            x[i] = (float)y;
        }
    }
}
double peakOf(const Buf& a) {
    double p = 0;
    for (float v : a) { double m = v < 0 ? -v : v; if (m > p) p = m; }
    return p;
}
void scaleBuf(Buf& a, double g) { for (auto& v : a) v = (float)(v * g); }

// ---- 4x oversampled waveshaper: cuts the aliasing that hard saturation folds back into the audible band ----
struct OSKernel {
    static const int C = 32, T = 65;
    double h[T];
    OSKernel() {
        const double fc = 0.1125;
        double sum = 0;
        for (int k = 0; k < T; k++) {
            double x = k - C, sinc = x == 0 ? 2 * fc : std::sin(TAU * fc * x) / (PI_ * x);
            double t = (double)k / (T - 1);
            double w = 0.35875 - 0.48829 * std::cos(TAU * t) + 0.14128 * std::cos(2 * TAU * t) - 0.01168 * std::cos(3 * TAU * t);
            h[k] = sinc * w; sum += h[k];
        }
        for (int k = 0; k < T; k++) h[k] /= sum;
    }
};
template <class F>
void oversampled(Buf& x, F shape) {
    static const OSKernel K;
    const int OS = 4, C = OSKernel::C;
    const long n = (long)x.size(), m4 = n * OS;
    std::vector<float> up((size_t)m4);
    for (long m = 0; m < m4; m++) {
        int r = (int)(m % OS);
        double acc = 0;
        for (int d = -C + r; d <= C; d += OS) {
            long idx = (m - d) / OS;
            if (idx < 0 || idx >= n) continue;
            acc += K.h[C + d] * x[(size_t)idx];
        }
        up[(size_t)m] = (float)shape(acc * OS);
    }
    for (long i = 0; i < n; i++) {
        double acc = 0;
        for (int d = -C; d <= C; d++) {
            long j = i * OS + d;
            if (j < 0 || j >= m4) continue;
            acc += K.h[C + d] * up[(size_t)j];
        }
        x[(size_t)i] = (float)acc;
    }
}

// ---------- generators ----------
struct Gen {
    Buf L, R;
    bool mono = true;
};

struct NoiseSrc {
    enum K { White, Pink, Brown, Blue, Violet, Velvet, Crackle } k = White;
    double pr = 0, b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0, p = 0, p1 = 0, p2 = 0, e = 0, b = 0;
    NoiseSrc(const std::string& c, double dens, double sr) {
        if (c == "pink") k = Pink; else if (c == "brown") k = Brown; else if (c == "blue") k = Blue;
        else if (c == "violet") k = Violet; else if (c == "velvet") k = Velvet; else if (c == "crackle") k = Crackle;
        pr = std::min(0.5, dens / sr);
    }
    double next(Rng& rng) {
        switch (k) {
            case Pink: {
                double w = rng() * 2 - 1;
                b0 = 0.99886 * b0 + w * 0.0555179; b1 = 0.99332 * b1 + w * 0.0750759; b2 = 0.969 * b2 + w * 0.153852;
                b3 = 0.8665 * b3 + w * 0.3104856; b4 = 0.55 * b4 + w * 0.5329522; b5 = -0.7616 * b5 - w * 0.016898;
                double o = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11;
                b6 = w * 0.115926;
                return o;
            }
            case Brown: b = (b + 0.02 * (rng() * 2 - 1)) / 1.02; return b * 3.5;
            case Blue: { double w = rng() * 2 - 1; double o = (w - p) * 0.7; p = w; return o; }
            case Violet: { double w = rng() * 2 - 1; double o = (w - 2 * p1 + p2) * 0.35; p2 = p1; p1 = w; return o; }
            case Velvet: {
                if (rng() < pr) {
                    double sg = rng() < 0.5 ? -1 : 1;
                    double mg = 0.5 + 0.5 * rng();
                    return sg * mg;
                }
                return 0;
            }
            case Crackle: {
                if (rng() < pr) { double q = rng(); e = q * q; }
                double o = (rng() * 2 - 1) * e;
                e *= 0.62;
                return o;
            }
            default: return rng() * 2 - 1;
        }
    }
};

Gen genNoise(const Layer& l, int n, double sr, Rng& rng) {
    Gen g; g.L.assign(n, 0);
    NoiseSrc nsA(l.S("color"), l.N("density"), sr);
    double ph = rng() * TAU;
    const double md = l.N("modDepth"), mr = l.N("modRate"), width = l.N("width");
    auto mod = [&](int i) { return md > 0 ? 1 - md * (0.5 + 0.5 * std::sin(ph + TAU * mr * i / sr)) : 1.0; };
    if (width < 0.001) {
        for (int i = 0; i < n; i++) g.L[i] = (float)(nsA.next(rng) * mod(i));
        return g;
    }
    g.mono = false; g.R.assign(n, 0);
    NoiseSrc nsB(l.S("color"), l.N("density"), sr);
    for (int i = 0; i < n; i++) {
        double a = nsA.next(rng), b = nsB.next(rng), m = mod(i);
        g.L[i] = (float)(a * m);
        g.R[i] = (float)((width * b + (1 - width) * a) * m);
    }
    return g;
}

double polyblep(double t, double dt) {
    if (t < dt) { t /= dt; return t + t - t * t - 1; }
    if (t > 1 - dt) { t = (t - 1) / dt; return t * t + t + t + 1; }
    return 0;
}
double waveAt(int w, double p, double dt, double pw) {
    switch (w) {
        case 1: return 2 * std::fabs(2 * p - 1) - 1;
        case 2: return 2 * p - 1 - polyblep(p, dt);
        case 4: { double q = p + 1 - pw; if (q >= 1) q -= 1; return (p < pw ? 1 : -1) + polyblep(p, dt) - polyblep(q, dt) - (2 * pw - 1); }
        case 3: { double q = p + 0.5; if (q >= 1) q -= 1; return (p < 0.5 ? 1 : -1) + polyblep(p, dt) - polyblep(q, dt); }
        default: return std::sin(TAU * p);
    }
}
Gen genOsc(const Layer& l, int n, double sr, Rng& rng) {
    const int V = (int)l.N("voices");
    std::vector<double> ph(V, 0), mph(V, 0), dm(V, 1);
    const double detune = l.N("detune");
    for (int v = 0; v < V; v++) {
        double d = V > 1 ? (((double)v / (V - 1)) * 2 - 1) * detune : 0;
        dm[v] = std::pow(2.0, d / 1200);
        ph[v] = V > 1 ? rng() : 0;
    }
    const std::string& ws = l.S("wave");
    int wave = ws == "triangle" ? 1 : ws == "saw" ? 2 : ws == "square" ? 3 : ws == "pulse" ? 4 : 0;
    Gen g; g.L.assign(n, 0);
    const double fS = l.N("freqStart"), fE = l.N("freqEnd"), ratio = fE / fS, k = l.N("pitchCurve"), ek = 1 - std::exp(-k);
    const double vph = rng() * TAU, nyq = sr * 0.45, norm = 1 / std::sqrt((double)V);
    const double vibD = l.N("vibDepth"), vibR = l.N("vibRate"), fmI = l.N("fmIndex"), fmD = l.N("fmDecay"), fmR = l.N("fmRatio");
    const double pw = l.N("pulseW"), subAmt = l.N("sub");
    double sub = 0;
    for (int i = 0; i < n; i++) {
        double x = (double)i / n, u = (1 - std::exp(-k * x)) / ek;
        double f = fS * std::pow(ratio, u);
        if (vibD > 0) f *= std::pow(2.0, vibD / 1200 * std::sin(vph + TAU * vibR * i / sr));
        if (f > nyq) f = nyq;
        double idx = fmI * std::exp(-fmD * x);
        double s = 0;
        for (int v = 0; v < V; v++) {
            double fv = std::min(nyq, f * dm[v]), dt = fv / sr;
            ph[v] += dt; if (ph[v] >= 1) ph[v] -= 1;
            double p = ph[v];
            if (idx > 0.0005) {
                mph[v] += fv * fmR / sr; mph[v] -= std::floor(mph[v]);
                p += idx * std::sin(TAU * mph[v]) / TAU; p -= std::floor(p);
            }
            s += waveAt(wave, p, std::min(0.45, dt), pw);
        }
        s *= norm;
        if (subAmt > 0) { sub += f * 0.5 / sr; sub -= std::floor(sub); s += subAmt * std::sin(TAU * sub); }
        g.L[i] = (float)s;
    }
    return g;
}

// ---- modal resonator bank ----
const double MEMBRANE[] = {1, 1.593, 2.136, 2.296, 2.653, 2.918, 3.156, 3.501, 3.600, 3.652, 4.060, 4.154, 4.234, 4.472, 4.602};
const double BELL[] = {0.5, 1, 1.183, 1.506, 2, 2.514, 2.662, 3.011, 4.166, 5.433, 6.796, 8.215, 9.64, 11.0, 12.4};
std::vector<double> modeRatios(const std::string& model, int N, double stiff, Rng& rng) {
    std::vector<double> r;
    double acc = 1;
    for (int i = 1; i <= N; i++) {
        double x;
        if (model == "string") x = i * std::sqrt(1 + stiff * 0.01 * i * i);
        else if (model == "bar") x = std::pow((2.0 * i + 1) / 3, 2);
        else if (model == "plate") x = std::pow((double)i, 1.2 + stiff * 0.8) * (1 + 0.04 * std::sin(i * 2.1));
        else if (model == "membrane") x = i <= 15 ? MEMBRANE[i - 1] : MEMBRANE[14] + 0.33 * (i - 15);
        else if (model == "tube") x = 2 * i - 1;
        else if (model == "glass") { double nn = i + 1; x = nn * (nn * nn - 1) / std::sqrt(nn * nn + 1) / 2.683; }
        else if (model == "wood") x = i == 1 ? 1 : (i == 2 ? 3.9 : (i == 3 ? 9.2 : 9.2 + (i - 3) * 5.5));
        else if (model == "spring") x = i * std::sqrt(1 + i * 0.4);
        else if (model == "bell") x = i <= 15 ? BELL[i - 1] : BELL[14] * (1 + 0.11 * (i - 15));
        else { if (i > 1) { double q = rng(); acc += 0.3 + q * 1.7; } x = acc; }
        r.push_back(x);
    }
    return r;
}
Gen genModal(const Layer& l, int n, double sr, Rng& rng) {
    const double freq = l.N("freq"), bright = l.N("brightness"), strikePos = l.N("strikePos"), tilt = l.N("tilt"), decayT = l.N("decay"), beat = l.N("beat");
    std::vector<double> ratios = modeRatios(l.S("model"), (int)l.N("partials"), l.N("stiffness"), rng);
    double p = 0.3 + (1 - bright) * 2.2;
    std::vector<double> c, s, rr, am;
    for (size_t i = 0; i < ratios.size(); i++) {
        double r = ratios[i], f = freq * r;
        if (f > sr * 0.45) continue;
        double q = rng();
        double a = std::pow(r, -p) * (0.35 + 0.65 * std::fabs(std::sin(PI_ * (i + 1) * strikePos))) * (0.8 + 0.4 * q);
        double T = decayT / (1 + tilt * 0.15 * (r - 1)), dec = std::pow(10.0, -3 / (T * sr));
        if (beat > 0.001) {
            double bt = beat * (0.3 + 0.7 * rng()) * 0.5;
            for (int sg = -1; sg <= 1; sg += 2) {
                double ff = std::max(5.0, f + sg * bt), w = TAU * ff / sr;
                c.push_back(std::cos(w)); s.push_back(std::sin(w)); rr.push_back(dec); am.push_back(a * 0.5);
            }
        } else {
            double w = TAU * f / sr;
            c.push_back(std::cos(w)); s.push_back(std::sin(w)); rr.push_back(dec); am.push_back(a);
        }
    }
    const size_t M = c.size();
    std::vector<double> re(M, 1.0), im(M, 0.0);
    Gen g; g.L.assign(n, 0);
    for (int i = 0; i < n; i++) {
        double o = 0;
        for (size_t m = 0; m < M; m++) {
            o += am[m] * im[m];
            double nr = rr[m] * (re[m] * c[m] - im[m] * s[m]), ni = rr[m] * (re[m] * s[m] + im[m] * c[m]);
            re[m] = nr; im[m] = ni;
        }
        g.L[i] = (float)o;
    }
    double pk = peakOf(g.L);
    const double strike = l.N("strike");
    if (strike > 0) {
        double tau = 0.0015 * sr, lpA = 0.1 + 0.9 * bright, y = 0;
        int lim = (int)std::min((double)n, std::ceil(tau * 8));
        for (int i = 0; i < lim; i++) {
            y += lpA * ((rng() * 2 - 1) - y);
            g.L[i] += (float)(strike * 0.6 * (pk > 0 ? pk : 1) * y * std::exp(-i / tau));
        }
    }
    return g;
}

// ---- Karplus-Strong ----
Gen genString(const Layer& l, int n, double sr, Rng& rng) {
    const double freq = l.N("freq"), N = sr / freq, d = l.N("damp"), Neff = std::max(2.0, N - d);
    const int M = (int)std::ceil(N) + 4;
    Buf buf(M, 0.0f);
    double gk = std::pow(10.0, -3 / (freq * l.N("decay")));
    int ni = (int)std::floor(N);
    Buf ex(ni, 0.0f);
    double lpa = 0.08 + 0.92 * l.N("bright"), y = 0;
    for (int i = 0; i < ni; i++) { y += lpa * ((rng() * 2 - 1) - y); ex[i] = (float)y; }
    int pp = std::max(1, (int)std::floor(l.N("pickPos") * N));
    for (int i = ni - 1; i >= pp; i--) ex[i] -= ex[i - pp];
    for (int i = 0; i < ni; i++) buf[i] = ex[i];
    int w = ni % M;
    double prev = 0;
    Gen g; g.L.assign(n, 0);
    for (int i = 0; i < n; i++) {
        double pos = w - Neff;
        if (pos < 0) pos += M;
        int i0 = (int)std::floor(pos);
        double fr = pos - i0;
        int i1 = (i0 + 1) % M;
        double yv = buf[i0] * (1 - fr) + buf[i1] * fr;
        double nw = gk * ((1 - d) * yv + d * prev);
        prev = yv;
        buf[w] = (float)nw; w = (w + 1) % M;
        g.L[i] = (float)nw;
    }
    return g;
}

// ---- granular ----
Gen genGrain(const Layer& l, int n, double sr, Rng& rng) {
    Gen g; g.mono = false; g.L.assign(n, 0); g.R.assign(n, 0);
    const double dur = (double)n / sr, dS = l.N("densStart"), dE = l.N("densEnd"), gms = l.N("grainMs"), fLo = l.N("fLo"), fHi = l.N("fHi"), sc = l.N("scatter");
    const bool tone = l.S("source") == "tone";
    double t = 0; int cnt = 0;
    while (cnt < 6000) {
        double x = t / dur, rate = dS * std::pow(dE / dS, x);
        t += -std::log(1 - rng()) / rate;
        if (t >= dur) break;
        cnt++;
        int i0 = (int)std::floor(t * sr);
        int gn = (int)std::max(8.0, jsRound(gms * (0.6 + 0.8 * rng()) * sr / 1000));
        int len = std::min(gn, n - i0);
        if (len < 4) continue;
        double f = fLo * std::pow(fHi / fLo, rng());
        double amp = 0.3 + 0.7 * rng();
        double pn = clampd(0.5 + (rng() - 0.5) * sc, 0, 1);
        double gL = std::cos(pn * PI_ / 2), gR = std::sin(pn * PI_ / 2);
        if (tone) {
            double w = TAU * f / sr, p0 = rng() * TAU;
            for (int j = 0; j < len; j++) {
                double win = 0.5 - 0.5 * std::cos(TAU * j / (len - 1)), v = std::sin(p0 + w * j) * win * amp;
                g.L[i0 + j] += (float)(v * gL); g.R[i0 + j] += (float)(v * gR);
            }
        } else {
            double a = 1 - std::exp(-TAU * f / sr), cg = std::min(6.0, 1 / std::sqrt(a)) * 0.3, y = 0;
            for (int j = 0; j < len; j++) {
                y += a * ((rng() * 2 - 1) - y);
                double win = 0.5 - 0.5 * std::cos(TAU * j / (len - 1)), v = y * win * amp * cg;
                g.L[i0 + j] += (float)(v * gL); g.R[i0 + j] += (float)(v * gR);
            }
        }
    }
    return g;
}

// ---- debris ----
Gen genDebris(const Layer& l, int n, double sr, Rng& rng) {
    Gen g; g.mono = false; g.L.assign(n, 0); g.R.assign(n, 0);
    const double dur = (double)n / sr, rate0 = l.N("rate"), accel = l.N("accel"), fLo = l.N("fLo"), fHi = l.N("fHi"), hitMs = l.N("hitMs");
    const double velVar = l.N("velVar"), hard = l.N("hardness");
    const int K = (int)l.N("partials");
    double t = 0; int cnt = 0;
    while (cnt < 3000) {
        double x = std::min(1.0, t / dur), rate = rate0 * std::exp(accel * 3 * x);
        t += -std::log(1 - rng()) / rate;
        if (t >= dur) break;
        cnt++;
        int i0 = (int)std::floor(t * sr);
        double f0 = fLo * std::pow(fHi / fLo, rng());
        double td = (hitMs / 1000) * (0.5 + rng());
        int len = (int)std::min((double)(n - i0), std::ceil(td * sr));
        if (len < 8) continue;
        double q1 = rng(), q2 = rng();
        double vel = (1 - velVar) + velVar * q1 * q2;
        double pn = rng(), gL = std::cos(pn * PI_ / 2) * vel, gR = std::sin(pn * PI_ / 2) * vel;
        double ro = 0.5 + (1 - hard) * 2;
        for (int k = 0; k < K; k++) {
            double ratio = 1;
            if (k != 0) ratio = 1 + k * (0.9 + rng() * 0.9);
            double f = f0 * ratio;
            if (f > sr * 0.45) continue;
            double w = TAU * f / sr, c = std::cos(w), s = std::sin(w), a = std::pow(ratio, -ro), dec = std::pow(10.0, -3 / ((td / (1 + k * 0.5)) * sr));
            double re = 1, im = 0;
            for (int j = 0; j < len; j++) {
                double v = a * im;
                g.L[i0 + j] += (float)(v * gL); g.R[i0 + j] += (float)(v * gR);
                double nr = dec * (re * c - im * s), ni = dec * (re * s + im * c);
                re = nr; im = ni;
            }
        }
        int cl = (int)std::min((double)len, std::ceil(0.0005 * sr * (1 + hard)));
        for (int j = 0; j < cl; j++) {
            double v = (rng() * 2 - 1) * hard * 0.5 * (1 - (double)j / cl);
            g.L[i0 + j] += (float)(v * gL); g.R[i0 + j] += (float)(v * gR);
        }
    }
    return g;
}

// ---- wind: noise through wandering resonant bands ----
Gen genWind(const Layer& l, int n, double sr, Rng& rng) {
    const int B = 16, nb = (n + B - 1) / B;
    const double nyq = sr * 0.45, ratios[3] = {1, 1.83, 2.9}, wts[3] = {1, 0.7, 0.45};
    const double wCenter = l.N("wCenter"), wQ = l.N("wQ"), gustDepth = l.N("gustDepth"), howl = l.N("howl"), turb = l.N("turb"), width = l.N("width");
    const double ra = 1 - std::exp(-TAU * l.N("gustRate") * B / sr), sd = std::sqrt(ra / (2 - ra) / 3);
    auto walk = [&]() {
        std::vector<float> g(nb);
        double v = 0;
        for (int b = 0; b < nb; b++) { v += ra * ((rng() * 2 - 1) - v); g[b] = (float)clampd(v / sd / 2.2, -1, 1); }
        return g;
    };
    std::vector<float> gs = walk();
    const double tt = 1 - std::exp(-TAU * 22 * B / sr), tsd = std::sqrt(tt / (2 - tt) / 3);
    const int chn = width < 0.01 ? 1 : 2;
    std::vector<Buf> outs;
    for (int ch = 0; ch < chn; ch++) {
        std::vector<float> go = walk();
        Buf A(n, 0.0f);
        double co[30] = {0}, s[24] = {0}, tv = 0;
        for (int b = 0; b < nb; b++) {
            double g = gs[b] * (1 - 0.45 * width) + go[b] * 0.45 * width;
            tv += tt * ((rng() * 2 - 1) - tv);
            double tur = clampd(1 + turb * 0.5 * tv / tsd, 0, 2.5), amp = tur * (0.35 + 0.65 * (0.5 + 0.5 * g));
            for (int k = 0; k < 3; k++) {
                double fc = clampd(wCenter * ratios[k] * std::pow(2.0, gustDepth * g), 40, nyq);
                Coef c1 = bq(BP, fc, wQ, sr), c2 = bq(BP, fc, wQ * 8, sr);
                for (int j = 0; j < 5; j++) { co[(2 * k) * 5 + j] = c1[j]; co[(2 * k + 1) * 5 + j] = c2[j]; }
            }
            int e = std::min(n, (b + 1) * B);
            for (int i = b * B; i < e; i++) {
                double x = rng() * 2 - 1, y = 0;
                for (int f = 0; f < 6; f++) {
                    int o = f * 5, so = f * 4;
                    double yy = co[o] * x + co[o + 1] * s[so] + co[o + 2] * s[so + 1] - co[o + 3] * s[so + 2] - co[o + 4] * s[so + 3];
                    s[so + 1] = s[so]; s[so] = x; s[so + 3] = s[so + 2]; s[so + 2] = yy;
                    y += yy * ((f & 1) ? howl * 2.8 : (1 - howl)) * wts[f >> 1];
                }
                A[i] = (float)(y * amp);
            }
        }
        outs.push_back(std::move(A));
    }
    Gen g;
    g.L = std::move(outs[0]);
    if (chn == 2) { g.R = std::move(outs[1]); g.mono = false; }
    return g;
}

// ---- bubbles: Minnaert-style resonant air pockets with an upward chirp ----
Gen genBubble(const Layer& l, int n, double sr, Rng& rng) {
    Gen g; g.mono = false; g.L.assign(n, 0); g.R.assign(n, 0);
    const double dur = (double)n / sr, fLo = l.N("fLo"), fHi = l.N("fHi"), ring = l.N("ring"), rise = l.N("rise"), sc = l.N("scatter"), cluster = l.N("cluster");
    int cnt = 0;
    std::function<void(double, int)> spawn = [&](double ts, int depth) {
        int i0 = (int)std::floor(ts * sr);
        if (i0 >= n - 8 || cnt > 2500) return;
        cnt++;
        double f0 = fLo * std::pow(fHi / fLo, std::pow(rng(), 1.3)), tau = ring / (PI_ * f0);
        int len = (int)std::min({(double)(n - i0), std::ceil(tau * 7 * sr), std::floor(0.6 * sr)});
        if (len < 8) return;
        double amp = std::pow(fLo / f0, 0.4) * (0.4 + 0.6 * rng());
        double pn = clampd(0.5 + (rng() - 0.5) * sc, 0, 1), gL = std::cos(pn * PI_ / 2) * amp, gR = std::sin(pn * PI_ / 2) * amp;
        double fade = std::max(2.0, 0.00025 * sr), dec = std::exp(-1 / (tau * sr)), ph = 0, env = 1;
        for (int j = 0; j < len; j++) {
            double tj = j / sr, f = f0 * (1 + rise * (1 - std::exp(-tj / tau)));
            ph += TAU * f / sr;
            double v = std::sin(ph) * env * std::min(1.0, j / fade);
            env *= dec;
            g.L[i0 + j] += (float)(v * gL); g.R[i0 + j] += (float)(v * gR);
        }
        if (depth < 1 && rng() < cluster) {
            double off = 0.004 + rng() * 0.03;
            spawn(ts + off, depth + 1);
        }
    };
    double t = 0;
    const double rate0 = l.N("rate"), accel = l.N("accel");
    while (cnt < 2500) {
        double x = std::min(1.0, t / dur), rate = rate0 * std::exp(accel * 3 * x);
        t += -std::log(1 - rng()) / rate;
        if (t >= dur) break;
        spawn(t, 0);
    }
    return g;
}

// ---- motor: pulse-train harmonic engine with exhaust resonance ----
Gen genMotor(const Layer& l, int n, double sr, Rng& rng) {
    const double nyq = sr * 0.45, fS = l.N("fStart"), fE = l.N("fEnd"), rampShape = l.N("rampShape"), tilt = l.N("tilt"), formant = l.N("formant");
    const double resBoost = l.N("resBoost"), rough = l.N("rough"), half = l.N("half"), whine = l.N("whine"), noiseAmt = l.N("noise");
    const int H = (int)l.N("harmonics");
    std::vector<double> amps(H + 2, 0.0);
    double phi = 0, ph2 = 0, whPh = 0, jit = 0, cyc = 1, tgt = 1, nz = 0, rms = 1;
    const double ja = 1 - std::exp(-TAU * 25 / sr), jsd = std::sqrt(ja / (2 - ja) / 3);
    Gen g; g.L.assign(n, 0);
    for (int i = 0; i < n; i++) {
        double x = (double)i / n, f0 = fS * std::pow(fE / fS, std::pow(x, rampShape));
        jit += ja * ((rng() * 2 - 1) - jit);
        double f = std::max(1.0, f0 * (1 + rough * 0.03 * clampd(jit / jsd, -3, 3)));
        if ((i & 127) == 0) {
            double ss = 0;
            for (int h = 1; h <= H; h++) {
                double fh = f * h;
                if (fh > nyq) { amps[h] = 0; continue; }
                double a = std::pow((double)h, -tilt);
                if (resBoost > 0) a *= 1 + resBoost * 3 * std::exp(-0.5 * std::pow(std::log2(fh / formant) / 0.6, 2));
                amps[h] = a; ss += a * a;
            }
            rms = std::sqrt(ss / 2) + 1e-6;
        }
        phi += f / sr;
        if (phi >= 1) {
            phi -= 1;
            double q1 = rng(), q2 = rng();
            tgt = 1 - rough * 0.6 * q1 * q2;
            if (rng() < rough * 0.03) tgt = 0.25;
        }
        cyc += (tgt - cyc) * 0.02;
        ph2 += f * 0.5 / sr; if (ph2 >= 1) ph2 -= 1;
        double xx = TAU * phi, c1 = std::cos(xx), k2 = 2 * c1, cm = 1, cc = c1, hs = 0;
        for (int h = 1; h <= H; h++) { hs += amps[h] * cc; double nx = k2 * cc - cm; cm = cc; cc = nx; }
        double y = cyc * (hs / rms) * 0.7;
        if (half > 0) y += half * 0.5 * (std::sin(TAU * ph2) + 0.5 * std::sin(TAU * ph2 * 3));
        if (whine > 0) {
            double wf = f * 5.7;
            if (wf < nyq) { whPh += wf / sr; whPh -= std::floor(whPh); y += whine * 0.3 * std::sin(TAU * whPh); }
        }
        if (noiseAmt > 0) {
            double fc = clampd(f * 4, 100, 5000), a = 1 - std::exp(-TAU * fc / sr), sdn = std::sqrt(a / (2 - a) / 3);
            nz += a * ((rng() * 2 - 1) - nz);
            y += noiseAmt * 0.5 * nz / sdn;
        }
        g.L[i] = (float)y;
    }
    return g;
}

// ---- voice: glottal source through morphing formants ----
bool vowelOf(const std::string& v, double out[3]) {
    static const struct { const char* n; double f[3]; } T[] = {
        {"a", {730, 1090, 2440}}, {"e", {530, 1840, 2480}}, {"i", {270, 2290, 3010}}, {"o", {570, 840, 2410}},
        {"u", {300, 870, 2240}}, {"ae", {660, 1720, 2410}}, {"uh", {640, 1190, 2390}}};
    for (auto& t : T) if (v == t.n) { for (int i = 0; i < 3; i++) out[i] = t.f[i]; return true; }
    for (int i = 0; i < 3; i++) out[i] = 730;
    return false;
}
Gen genVoice(const Layer& l, int n, double sr, Rng& rng) {
    double va[3], vb[3];
    vowelOf(l.S("vowelA"), va); vowelOf(l.S("vowelB"), vb);
    const double fx[2] = {3300, 3750}, Q[5] = {7, 9, 11, 14, 16}, W[5] = {1, 0.7, 0.45, 0.2, 0.12}, nyq = sr * 0.45;
    const double shift = l.N("shift"), morph = l.N("morph"), pS = l.N("pStart"), pE = l.N("pEnd"), vibD = l.N("vibDepth"), vibR = l.N("vibRate");
    const double jitter = l.N("jitter"), growl = l.N("growl"), growlRate = l.N("growlRate"), breath = l.N("breath");
    double st[20] = {0}, co[25] = {0};
    const double lpa = 0.12 + 0.88 * l.N("tension"), k = l.N("pitchCurve"), ek = 1 - std::exp(-k);
    const double ja = 1 - std::exp(-TAU * 9 / sr), jsd = std::sqrt(ja / (2 - ja) / 3);
    double ph = 0, vph = rng() * TAU, gph = rng() * TAU, jit = 0, lp = 0;
    Gen g; g.L.assign(n, 0);
    for (int i = 0; i < n; i++) {
        double x = (double)i / n;
        if (i % 24 == 0) {
            double m = std::pow(x, morph);
            for (int f = 0; f < 5; f++) {
                double fr = std::min(nyq, (f < 3 ? va[f] + (vb[f] - va[f]) * m : fx[f - 3]) * shift);
                Coef c = bq(BP, fr, Q[f], sr);
                for (int j = 0; j < 5; j++) co[f * 5 + j] = c[j];
            }
        }
        double u = (1 - std::exp(-k * x)) / ek;
        double f0 = pS * std::pow(pE / pS, u);
        jit += ja * ((rng() * 2 - 1) - jit);
        f0 *= std::pow(2.0, (vibD / 1200) * std::sin(vph + TAU * vibR * i / sr) + jitter * 0.02 * clampd(jit / jsd, -3, 3));
        f0 = std::min(f0, nyq * 0.5);
        double dt = f0 / sr;
        ph += dt; if (ph >= 1) ph -= 1;
        double s = 2 * ph - 1 - polyblep(ph, dt);
        lp += lpa * (s - lp); s = lp;
        gph += TAU * growlRate / sr;
        if (growl > 0) s *= 1 - growl * 0.5 * (1 + std::sin(gph));
        double ex = (1 - breath * 0.8) * s * 1.6 + breath * (rng() * 2 - 1) * 0.9;
        double y = 0;
        for (int f = 0; f < 5; f++) {
            int o = f * 5, so = f * 4;
            double yy = co[o] * ex + co[o + 1] * st[so] + co[o + 2] * st[so + 1] - co[o + 3] * st[so + 2] - co[o + 4] * st[so + 3];
            st[so + 1] = st[so]; st[so] = ex; st[so + 3] = st[so + 2]; st[so + 2] = yy;
            y += yy * W[f];
        }
        g.L[i] = (float)y;
    }
    return g;
}

// ---- friction: stick-slip pulses into a resonant body ----
Gen genFriction(const Layer& l, int n, double sr, Rng& rng) {
    const double nyq = sr * 0.45, rat[4] = {1, 2.13, 3.37, 5.02}, gw[4] = {1, 0.65, 0.4, 0.25};
    const double resFreq = l.N("resFreq"), inharm = l.N("inharm"), rq = l.N("rq"), rS = l.N("rateStart"), rE = l.N("rateEnd");
    const double pressureAmt = l.N("pressure"), jitter = l.N("jitter"), pulse = l.N("pulse"), grit = l.N("grit");
    double st[16] = {0}, co[20] = {0};
    const double k = l.N("rateCurve"), ek = 1 - std::exp(-k), pa = 1 - std::exp(-TAU * 3 / sr), psd = std::sqrt(pa / (2 - pa) / 3);
    double ph = 0, press = 0, imp = 0, ampc = 1;
    Gen g; g.L.assign(n, 0);
    for (int i = 0; i < n; i++) {
        double x = (double)i / n;
        if (i % 32 == 0) {
            for (int b = 0; b < 4; b++) {
                double fr = std::min(nyq, resFreq * rat[b] * (1 + inharm * 0.3 * b));
                Coef c = bq(BP, fr, rq, sr);
                for (int j = 0; j < 5; j++) co[b * 5 + j] = c[j];
            }
        }
        press += pa * ((rng() * 2 - 1) - press);
        double pn = clampd(press / psd, -3, 3), u = (1 - std::exp(-k * x)) / ek;
        double rate = rS * std::pow(rE / rS, u) * (1 + 0.15 * pressureAmt * pn);
        double dt = std::min(0.45, std::max(1e-5, rate / sr));
        ph += dt * (1 + jitter * 0.5 * (rng() * 2 - 1));
        if (ph >= 1) { ph -= 1; ampc = 1 - jitter * 0.7 * rng(); imp = ampc; }
        imp *= std::exp(-dt * 40);
        double sw = (1 - ph * 2) * 0.6 * ampc;
        double e = (1 - pulse) * imp * 3 + pulse * sw;
        e += grit * (rng() * 2 - 1) * 0.5 * (0.4 + 0.6 * std::min(1.0, std::fabs(pn) / 2));
        double y = 0;
        for (int b = 0; b < 4; b++) {
            int o = b * 5, so = b * 4;
            double yy = co[o] * e + co[o + 1] * st[so] + co[o + 2] * st[so + 1] - co[o + 3] * st[so + 2] - co[o + 4] * st[so + 3];
            st[so + 1] = st[so]; st[so] = e; st[so + 3] = st[so + 2]; st[so + 2] = yy;
            y += yy * gw[b];
        }
        g.L[i] = (float)(y * clampd(1 + pressureAmt * 0.6 * pn, 0.1, 2));
    }
    return g;
}

double envAt(double a, double h, double d, double k, double t) {
    double v;
    if (t < a) v = std::pow(t / a, 1.6);
    else if (t < a + h) v = 1;
    else {
        double span = std::max(1e-4, d - a - h), x = clampd((t - a - h) / span, 0, 1);
        v = (std::exp(-k * x) - std::exp(-k)) / (1 - std::exp(-k));
    }
    double tail = d - t;
    if (tail < 0.004) v *= std::max(0.0, tail / 0.004);
    return v;
}

Gen renderLayer(const Layer& l, double sr, Rng& rng) {
    const double dur = l.N("dur");
    const int n = (int)std::max(16.0, jsRound(dur * sr));
    Gen g;
    const std::string& t = l.type;
    if (t == "noise") g = genNoise(l, n, sr, rng);
    else if (t == "osc") g = genOsc(l, n, sr, rng);
    else if (t == "modal") g = genModal(l, n, sr, rng);
    else if (t == "string") g = genString(l, n, sr, rng);
    else if (t == "grain") g = genGrain(l, n, sr, rng);
    else if (t == "debris") g = genDebris(l, n, sr, rng);
    else if (t == "wind") g = genWind(l, n, sr, rng);
    else if (t == "bubble") g = genBubble(l, n, sr, rng);
    else if (t == "motor") g = genMotor(l, n, sr, rng);
    else if (t == "voice") g = genVoice(l, n, sr, rng);
    else g = genFriction(l, n, sr, rng);
    std::vector<Buf*> chans = {&g.L};
    if (!g.mono) chans.push_back(&g.R);
    for (Buf* c : chans) sweepFilter(*c, l, sr);
    if (l.N("lowcut") > 25) { Coef cf = bq(HP, l.N("lowcut"), 0.707, sr); for (Buf* c : chans) applyBq(*c, cf); }
    if (l.N("highcut") < 19000) { Coef cf = bq(LP, l.N("highcut"), 0.707, sr); for (Buf* c : chans) applyBq(*c, cf); }
    const double a = l.N("attack"), h = l.N("hold"), k = l.N("curve"), td = l.N("tremDepth"), tr = l.N("tremRate");
    const bool trem = td > 0.001 && tr > 0.01;
    Buf env(n);
    for (int i = 0; i < n; i++) {
        double tt = i / sr;
        env[i] = (float)(envAt(a, h, dur, k, tt) * (trem ? 1 - td * 0.5 * (1 - std::cos(TAU * tr * tt)) : 1));
    }
    for (Buf* c : chans) for (int i = 0; i < n; i++) (*c)[i] *= env[i];
    auto norm = [&](double target) {
        double pk = 0;
        for (Buf* c : chans) pk = std::max(pk, peakOf(*c));
        if (pk > 0) for (Buf* c : chans) scaleBuf(*c, target / pk);
    };
    norm(0.9);
    const double drive = l.N("drive");
    if (drive > 0.001) {
        double gn = 1 + drive * 14, bias = 0.25 * drive, nb = std::tanh(bias);
        for (Buf* c : chans) oversampled(*c, [&](double v) { return std::tanh(gn * v + bias) - nb; });
        norm(0.9);
    }
    norm(1.0);
    return g;
}

// ---------- reverb: 8-line FDN with modulated delays, input diffusion and early reflections ----------
void reverb(const Buf& inp, size_t N, double sr, const Bag& M, Buf& oL, Buf& oR) {
    const double size = M.N("revSize"), T60 = M.N("revDecay"), d = clampd(M.N("revDamp"), 0, 1) * 0.85, md = M.N("revMod");
    const int pre = (int)jsRound(M.N("revPre") / 1000 * sr);
    const double ms[8] = {31.7, 37.9, 43.3, 47.9, 53.9, 61.1, 67.3, 73.9};
    const int mp = (int)jsRound(0.0007 * sr * md) + 1;
    int base[8], len[8];
    std::vector<Buf> bufs(8);
    double gk[8], lp[8] = {0}, w0[8], p0[8];
    int wp[8] = {0};
    for (int k = 0; k < 8; k++) {
        base[k] = (int)std::max(8.0, jsRound(ms[k] * size * sr / 1000));
        len[k] = base[k] + mp + 8;
        bufs[k].assign(len[k], 0.0f);
        gk[k] = std::pow(10.0, -3.0 * base[k] / (sr * T60));
        w0[k] = TAU * (0.11 + 0.043 * k) / sr;
        p0[k] = k * 1.7;
    }
    const double apm[3] = {4.3, 6.7, 9.1};
    int apL[3], apP[3] = {0, 0, 0};
    std::vector<Buf> apB(3);
    for (int a = 0; a < 3; a++) { apL[a] = (int)jsRound(apm[a] * sr / 1000); apB[a].assign(apL[a], 0.0f); }
    const double ag = 0.6;
    const double etm[10] = {5.1, 8.3, 11.7, 15.9, 19.3, 24.7, 29.9, 36.1, 43.7, 52.3};
    int et[10];
    for (int i = 0; i < 10; i++) et[i] = (int)jsRound(etm[i] * std::sqrt(size) * sr / 1000);
    const double eg[10] = {0.7, -0.6, 0.55, -0.5, 0.42, -0.38, 0.3, -0.26, 0.2, -0.16}, early = M.N("revEarly");
    oL.assign(N, 0.0f); oR.assign(N, 0.0f);
    double o[8], v[8];
    const double H = 0.35355339;
    for (size_t i = 0; i < N; i++) {
        double x = (long)i >= pre ? inp[i - pre] : 0;
        if (early > 0) {
            double eL = 0, eR = 0;
            for (int t = 0; t < 10; t++) {
                long j = (long)i - pre - et[t];
                if (j >= 0) { double s = inp[(size_t)j] * eg[t]; if (t & 1) eR += s; else eL += s; }
            }
            oL[i] = (float)(eL * early * 0.5); oR[i] = (float)(eR * early * 0.5);
        }
        for (int a = 0; a < 3; a++) {
            double dl = apB[a][apP[a]], y = -ag * x + dl;
            apB[a][apP[a]] = (float)(x + ag * y);
            if (++apP[a] >= apL[a]) apP[a] = 0;
            x = y;
        }
        for (int k = 0; k < 8; k++) {
            double dly = base[k] + mp * std::sin(w0[k] * (double)i + p0[k]);
            double rp = wp[k] - dly;
            if (rp < 0) rp += len[k];
            int i0 = (int)std::floor(rp);
            double fr = rp - i0;
            int i1 = i0 + 1 >= len[k] ? 0 : i0 + 1;
            o[k] = bufs[k][i0] * (1 - fr) + bufs[k][i1] * fr;
            lp[k] = (1 - d) * o[k] + d * lp[k];
            v[k] = gk[k] * lp[k];
        }
        for (int h = 1; h < 8; h <<= 1)
            for (int j = 0; j < 8; j += h << 1)
                for (int q = j; q < j + h; q++) { double a = v[q], b = v[q + h]; v[q] = a + b; v[q + h] = a - b; }
        for (int k = 0; k < 8; k++) {
            bufs[k][wp[k]] = (float)(x * 0.3 + v[k] * H);
            if (++wp[k] >= len[k]) wp[k] = 0;
        }
        oL[i] += (float)((o[0] - o[2] + o[4] - o[6]) * 0.35);
        oR[i] += (float)((o[1] - o[3] + o[5] - o[7]) * 0.35);
    }
}

void pingpong(const Buf& inp, size_t N, double sr, double time, double fb, double tone, Buf& y1, Buf& y2) {
    long d = std::max(1L, (long)jsRound(time * sr));
    y1.assign(N, 0.0f); y2.assign(N, 0.0f);
    double a = 1 - std::exp(-TAU * tone / sr), l1 = 0, l2 = 0;
    for (long i = 0; i < (long)N; i++) {
        double r1 = i >= d ? inp[i - d] + y2[i - d] : 0;
        l1 += a * (r1 - l1); y1[i] = (float)l1;
        double r2 = i >= d ? fb * y1[i - d] : 0;
        l2 += a * (r2 - l2); y2[i] = (float)l2;
    }
}

void compress(Buf& L, Buf& R, const Bag& M, double sr) {
    if (M.N("compThresh") > -0.5) return;
    double th = M.N("compThresh"), ra = M.N("compRatio"), at = std::exp(-1 / (M.N("compAttack") / 1000 * sr)), re = std::exp(-1 / (M.N("compRelease") / 1000 * sr)), mk = dBtoLin(M.N("compMakeup")), env = 0;
    for (size_t i = 0; i < L.size(); i++) {
        double lv = 20 * std::log10(std::max({std::fabs((double)L[i]), std::fabs((double)R[i]), 1e-6}));
        double tg = std::max(0.0, lv - th) * (1 - 1 / ra);
        env = tg > env ? at * env + (1 - at) * tg : re * env + (1 - re) * tg;
        double g = dBtoLin(-env) * mk;
        L[i] = (float)(L[i] * g); R[i] = (float)(R[i] * g);
    }
}
void transient(Buf& L, Buf& R, double amt, double sr) {
    if (std::fabs(amt) < 0.01) return;
    double af = 1 - std::exp(-1 / (0.001 * sr)), as = 1 - std::exp(-1 / (0.025 * sr)), ef = 0, es = 0;
    for (size_t i = 0; i < L.size(); i++) {
        double p = std::max(std::fabs((double)L[i]), std::fabs((double)R[i]));
        ef += af * (p - ef); es += as * (p - es);
        double g = clampd(1 + amt * 0.6 * clampd((ef - es) / (es + 1e-3), -1, 3), 0.15, 3.5);
        L[i] = (float)(L[i] * g); R[i] = (float)(R[i] * g);
    }
}
// Look-ahead limiter. Sliding-window minimum via a monotonic queue keeps it linear in length.
void limiter(Buf& L, Buf& R, double ceil, double sr) {
    const long N = (long)L.size();
    const long la = std::max(8L, (long)jsRound(0.0015 * sr));
    std::vector<float> g((size_t)(N + la + 1), 1.0f), m((size_t)N);
    for (long i = 0; i < N; i++) { double p = std::max(std::fabs((double)L[i]), std::fabs((double)R[i])); g[i] = p > ceil ? (float)(ceil / p) : 1.0f; }
    std::vector<long> dq((size_t)(N + la + 2));
    size_t head = 0, tail = 0;
    long pushed = 0;
    for (long i = 0; i < N; i++) {
        long e = i + la;
        while (pushed <= e) {
            while (tail > head && g[dq[tail - 1]] >= g[pushed]) tail--;
            dq[tail++] = pushed++;
        }
        while (dq[head] < i) head++;
        m[i] = g[dq[head]];
    }
    double rel = std::exp(-1 / (0.06 * sr)), prev = 1, run = (double)la;
    std::vector<float> buf((size_t)la, 1.0f);
    long bi = 0;
    for (long i = 0; i < N; i++) {
        run += m[i] - buf[bi]; buf[bi] = m[i]; bi = (bi + 1) % la;
        double s = run / la, r = prev + (1 - prev) * (1 - rel);
        if (s < r) r = s;
        prev = r;
        L[i] = (float)(L[i] * r); R[i] = (float)(R[i] * r);
    }
}

const char* PKEYS[] = {"freq", "freqStart", "freqEnd", "pStart", "pEnd", "fLo", "fHi", "resFreq", "fStart", "fEnd", "wCenter"};
Layer varyLayer(const Layer& l, double amt, Rng& rng) {
    if (amt <= 0.001) return l;
    Layer c = l;
    double s = std::pow(2.0, (rng() - 0.5) * amt * 0.5);
    double s2 = std::pow(2.0, (rng() - 0.5) * amt * 0.8);
    for (const char* k : PKEYS) { auto it = c.n.find(k); if (it != c.n.end()) it->second *= s; }
    if (c.S("filter") != "off") {
        c.n["fcStart"] = clampd(c.n["fcStart"] * s2, 20, 20000);
        c.n["fcEnd"] = clampd(c.n["fcEnd"] * s2, 20, 20000);
    }
    return c;
}
double layerSpan(const Layer& l) {
    return l.N("start") + (l.N("repeat") - 1) * l.N("repInterval") * (1 + l.N("repJitter") * 0.5) + l.N("dur") + l.N("haas") / 1000;
}

struct Task {
    int idx, rep;
    double st, vel;
    uint32_t seed;
};

}  // namespace

Audio render(const Recipe& R, const RenderOptions& opts) {
    auto t0 = std::chrono::steady_clock::now();
    const Bag& M = R.master;
    const int sri = (int)M.N("sampleRate");
    const double sr = sri;
    std::vector<int> items;
    for (size_t i = 0; i < R.layers.size(); i++) if (!R.layers[i].mute) items.push_back((int)i);
    if (!opts.only.empty()) items = opts.only;
    else {
        bool anySolo = false;
        for (int i : items) if (R.layers[i].solo) anySolo = true;
        if (anySolo) { std::vector<int> f; for (int i : items) if (R.layers[i].solo) f.push_back(i); items = f; }
    }
    double maxEnd = 0;
    for (int i : items) maxEnd = std::max(maxEnd, layerSpan(R.layers[i]));
    if (items.empty()) maxEnd = 0.1;
    bool usesRev = false, usesEcho = false;
    for (int i : items) { if (R.layers[i].N("reverb") > 0.001) usesRev = true; if (R.layers[i].N("echo") > 0.001) usesEcho = true; }
    usesRev = usesRev && M.N("revMix") > 0.001;
    double tail = 0.03;
    if (usesRev) tail = std::max(tail, M.N("revDecay") * 0.9 + M.N("revPre") / 1000);
    if (usesEcho) {
        double fb = std::max(M.N("echoFb"), 0.05), reps = std::min(30.0, std::log(0.001) / std::log(fb));
        tail = std::max(tail, std::min(5.0, reps * M.N("echoTime") / 1000));
    }
    const double total = std::min(24.0, std::max(maxEnd + tail, opts.minLength));
    const size_t N = (size_t)std::ceil(total * sr);
    Buf dL(N, 0.0f), dR(N, 0.0f), sRev(N, 0.0f), sEch(N, 0.0f);

    // Build the work list in the same order the mix is summed, then render in parallel batches.
    std::vector<Task> tasks;
    for (int idx : items) {
        const Layer& l = R.layers[idx];
        for (int rep = 0; rep < (int)l.N("repeat"); rep++) {
            Rng a(seedFrom((double)R.seed * 31 + rep * 7 + 1)), b(seedFrom((double)R.seed * 37 + rep * 11 + 3));
            double tj = a(), vj = b();
            Task t;
            t.idx = idx; t.rep = rep;
            t.st = l.N("start") + (rep ? rep * l.N("repInterval") + (tj * 2 - 1) * l.N("repJitter") * l.N("repInterval") * 0.5 : 0);
            t.vel = std::pow(l.N("repDecay"), rep) * (1 - l.N("repVar") * 0.65 * vj);
            t.seed = seedFrom((double)R.seed * 1000003 + idx * 7919 + 17 + rep * 104729);
            tasks.push_back(t);
        }
    }
    int nth = opts.threads > 0 ? opts.threads : (int)std::thread::hardware_concurrency();
    nth = std::max(1, std::min(nth, 8));
    const size_t batch = (size_t)nth * 2;
    for (size_t b0 = 0; b0 < tasks.size(); b0 += batch) {
        size_t b1 = std::min(tasks.size(), b0 + batch);
        std::vector<Gen> outs(b1 - b0);
        std::atomic<size_t> next(b0);
        auto work = [&]() {
            while (true) {
                size_t i = next.fetch_add(1);
                if (i >= b1) break;
                const Task& t = tasks[i];
                const Layer& l = R.layers[t.idx];
                Rng rng(t.seed);
                Layer ll = t.rep ? varyLayer(l, l.N("repVar"), rng) : l;
                outs[i - b0] = renderLayer(ll, sr, rng);
            }
        };
        std::vector<std::thread> pool;
        for (int k = 1; k < nth && (size_t)k < b1 - b0; k++) pool.emplace_back(work);
        work();
        for (auto& th : pool) th.join();
        for (size_t i = b0; i < b1; i++) {
            const Task& t = tasks[i];
            const Layer& l = R.layers[t.idx];
            Gen& out = outs[i - b0];
            const Buf& oL = out.L;
            const Buf& oR = out.mono ? out.L : out.R;
            long off = (long)jsRound(t.st * sr), hs = (long)jsRound(l.N("haas") / 1000 * sr);
            double gn = dBtoLin(l.N("gain")) * t.vel;
            long n = (long)oL.size();
            bool mv = std::fabs(l.N("move")) > 0.001;
            double p0 = l.N("pan"), p1 = clampd(l.N("pan") + l.N("move"), -1, 1), gl = 1, gr = 1;
            const double rv = l.N("reverb"), ec = l.N("echo");
            for (long k = 0; k < n; k++) {
                long j = off + k;
                if (j >= (long)N) break;
                if (j < 0) continue;
                if (mv || k == 0) {
                    double p = p0 + (p1 - p0) * k / n, th = (p + 1) * PI_ / 4;
                    gl = std::cos(th) * std::sqrt(2.0); gr = std::sin(th) * std::sqrt(2.0);
                }
                double a = oL[k] * gn * gl, bb = oR[k] * gn * gr;
                dL[j] += (float)a;
                if (j + hs < (long)N) dR[j + hs] += (float)bb;
                double mid = (a + bb) * 0.5;
                sRev[j] += (float)(mid * rv); sEch[j] += (float)(mid * ec);
            }
        }
    }

    const double dist = M.N("distance");
    if (dist > 0.001) {
        double g = 1 - 0.55 * dist;
        Coef c = bq(LP, 18000 * std::pow(0.1, dist), 0.707, sr);
        applyBq(dL, c); applyBq(dR, c); scaleBuf(dL, g); scaleBuf(dR, g);
    }
    if (usesRev) {
        applyBq(sRev, bq(HP, M.N("revLow"), 0.707, sr));
        Buf wL, wR;
        reverb(sRev, N, sr, M, wL, wR);
        double k = M.N("revMix") * 0.8 * (1 + dist * 1.2);
        for (size_t i = 0; i < N; i++) { dL[i] += (float)(wL[i] * k); dR[i] += (float)(wR[i] * k); }
    }
    if (usesEcho) {
        Buf e1, e2;
        pingpong(sEch, N, sr, M.N("echoTime") / 1000, M.N("echoFb"), M.N("echoTone"), e1, e2);
        for (size_t i = 0; i < N; i++) { dL[i] += e1[i]; dR[i] += e2[i]; }
    }
    Coef hp = bq(HP, 18, 0.707, sr);
    applyBq(dL, hp); applyBq(dR, hp);
    if (std::fabs(M.N("lowShelf")) > 0.05) { Coef c = shelf(true, 120, M.N("lowShelf"), sr); applyBq(dL, c); applyBq(dR, c); }
    if (std::fabs(M.N("midGain")) > 0.05) { Coef c = peaking(M.N("midFreq"), M.N("midGain"), M.N("midQ"), sr); applyBq(dL, c); applyBq(dR, c); }
    if (std::fabs(M.N("highShelf")) > 0.05) { Coef c = shelf(false, 6000, M.N("highShelf"), sr); applyBq(dL, c); applyBq(dR, c); }
    transient(dL, dR, M.N("transient"), sr);
    compress(dL, dR, M, sr);
    if (M.N("drive") > 0.001) {
        double pk = std::max(peakOf(dL), peakOf(dR));
        if (pk > 0) { scaleBuf(dL, 0.9 / pk); scaleBuf(dR, 0.9 / pk); }
        double gn = 1 + M.N("drive") * 5, nrm = 1 / std::tanh(gn * 0.9);
        auto sh = [&](double v) { return std::tanh(gn * v) * nrm * 0.9; };
        oversampled(dL, sh); oversampled(dR, sh);
    }
    const double width = M.N("width");
    if (std::fabs(width - 1) > 0.01) {
        for (size_t i = 0; i < N; i++) {
            double m = ((double)dL[i] + dR[i]) * 0.5, s = ((double)dL[i] - dR[i]) * 0.5 * width;
            dL[i] = (float)(m + s); dR[i] = (float)(m - s);
        }
    }
    const double ceil = dBtoLin(M.N("ceiling"));
    limiter(dL, dR, ceil, sr);
    double pk = std::max(peakOf(dL), peakOf(dR));
    if (M.S("normalize") != "off" && !opts.raw && pk > 1e-6) { scaleBuf(dL, ceil / pk); scaleBuf(dR, ceil / pk); }
    size_t fi = std::min(N, (size_t)jsRound(0.0004 * sr)), fo = std::min(N, (size_t)jsRound(0.02 * sr));
    for (size_t i = 0; i < fi; i++) { double g = (double)i / fi; dL[i] = (float)(dL[i] * g); dR[i] = (float)(dR[i] * g); }
    for (size_t i = 0; i < fo; i++) { double g = (double)i / fo; size_t j = N - 1 - i; dL[j] = (float)(dL[j] * g); dR[j] = (float)(dR[j] * g); }
    Audio A;
    A.sr = sri;
    A.peak = std::max(peakOf(dL), peakOf(dR));
    double ss = 0;
    for (size_t i = 0; i < N; i++) ss += (double)dL[i] * dL[i] + (double)dR[i] * dR[i];
    A.rms = std::sqrt(ss / (2.0 * N));
    A.duration = (double)N / sr;
    A.L = std::move(dL); A.R = std::move(dR);
    A.renderMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    return A;
}

}  // namespace strata
