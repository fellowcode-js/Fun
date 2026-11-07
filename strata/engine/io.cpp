// WAV and zip encoding, waveform envelope and spectrogram for the analyzer view.
#include <algorithm>
#include <cmath>
#include <cstring>

#include "strata.hpp"

namespace strata {

static double clampd(double x, double a, double b) { return x < a ? a : (x > b ? b : x); }

std::vector<uint8_t> encodeWav(const std::vector<float>& L, const std::vector<float>& R, int sr, int bits) {
    const size_t n = L.size();
    const int bps = bits / 8;
    const size_t dl = n * 2 * bps;
    std::vector<uint8_t> out(44 + dl);
    auto u16 = [&](size_t o, uint16_t v) { out[o] = v & 255; out[o + 1] = v >> 8; };
    auto u32 = [&](size_t o, uint32_t v) { for (int i = 0; i < 4; i++) out[o + i] = (v >> (8 * i)) & 255; };
    memcpy(&out[0], "RIFF", 4); u32(4, (uint32_t)(36 + dl)); memcpy(&out[8], "WAVE", 4); memcpy(&out[12], "fmt ", 4);
    u32(16, 16); u16(20, bits == 32 ? 3 : 1); u16(22, 2); u32(24, sr); u32(28, sr * 2 * bps); u16(32, 2 * bps); u16(34, bits);
    memcpy(&out[36], "data", 4); u32(40, (uint32_t)dl);
    size_t o = 44;
    uint32_t lcg = 12345;  // deterministic TPDF dither for 16-bit
    auto rnd = [&]() { lcg = lcg * 1664525u + 1013904223u; return (double)(lcg >> 8) / 16777216.0; };
    for (size_t i = 0; i < n; i++) {
        for (int c = 0; c < 2; c++) {
            double x = clampd(c ? R[i] : L[i], -1, 1);
            if (bits == 16) {
                double v = std::floor(x * 32767 + (rnd() - rnd()) + 0.5);
                int16_t s = (int16_t)clampd(v, -32768, 32767);
                out[o++] = s & 255; out[o++] = (s >> 8) & 255;
            } else if (bits == 24) {
                int32_t v = (int32_t)std::floor(x * 8388607 + 0.5);
                out[o++] = v & 255; out[o++] = (v >> 8) & 255; out[o++] = (v >> 16) & 255;
            } else {
                float f = (float)x;
                memcpy(&out[o], &f, 4); o += 4;
            }
        }
    }
    return out;
}

static uint32_t crc32(const std::vector<uint8_t>& d) {
    static uint32_t T[256];
    static bool init = false;
    if (!init) {
        for (uint32_t n = 0; n < 256; n++) { uint32_t c = n; for (int k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1; T[n] = c; }
        init = true;
    }
    uint32_t c = 0xFFFFFFFFu;
    for (uint8_t b : d) c = T[(c ^ b) & 255] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

std::vector<uint8_t> zipStore(const std::vector<ZipEntry>& files) {
    std::vector<uint8_t> out, cd;
    auto p16 = [](std::vector<uint8_t>& v, uint16_t x) { v.push_back(x & 255); v.push_back(x >> 8); };
    auto p32 = [](std::vector<uint8_t>& v, uint32_t x) { for (int i = 0; i < 4; i++) v.push_back((x >> (8 * i)) & 255); };
    for (auto& f : files) {
        uint32_t crc = crc32(f.data), sz = (uint32_t)f.data.size(), off = (uint32_t)out.size();
        p32(out, 0x04034b50); p16(out, 20); p16(out, 0x0800); p16(out, 0); p16(out, 0); p16(out, 0x21);
        p32(out, crc); p32(out, sz); p32(out, sz); p16(out, (uint16_t)f.name.size()); p16(out, 0);
        out.insert(out.end(), f.name.begin(), f.name.end());
        out.insert(out.end(), f.data.begin(), f.data.end());
        p32(cd, 0x02014b50); p16(cd, 20); p16(cd, 20); p16(cd, 0x0800); p16(cd, 0); p16(cd, 0); p16(cd, 0x21);
        p32(cd, crc); p32(cd, sz); p32(cd, sz); p16(cd, (uint16_t)f.name.size()); p16(cd, 0); p16(cd, 0); p16(cd, 0); p16(cd, 0); p32(cd, 0); p32(cd, off);
        cd.insert(cd.end(), f.name.begin(), f.name.end());
    }
    uint32_t cdOff = (uint32_t)out.size(), cdSize = (uint32_t)cd.size();
    out.insert(out.end(), cd.begin(), cd.end());
    p32(out, 0x06054b50); p16(out, 0); p16(out, 0); p16(out, (uint16_t)files.size()); p16(out, (uint16_t)files.size());
    p32(out, cdSize); p32(out, cdOff); p16(out, 0);
    return out;
}

std::vector<float> envelope(const Audio& a, int width) {
    const size_t n = a.L.size();
    std::vector<float> out((size_t)width * 2, 0.0f);
    for (int x = 0; x < width; x++) {
        size_t s = (size_t)((double)x / width * n), e = std::max(s + 1, (size_t)((double)(x + 1) / width * n));
        size_t step = std::max<size_t>(1, (e - s) / 64);
        float mn = 1, mx = -1;
        for (size_t i = s; i < e && i < n; i += step) { float v = (a.L[i] + a.R[i]) * 0.5f; mn = std::min(mn, v); mx = std::max(mx, v); }
        out[x * 2] = mn; out[x * 2 + 1] = mx;
    }
    return out;
}

namespace {
const int FN = 1024;
struct FFT {
    float cosT[FN / 2], sinT[FN / 2], hann[FN];
    FFT() {
        for (int i = 0; i < FN / 2; i++) { cosT[i] = (float)std::cos(2 * M_PI * i / FN); sinT[i] = (float)-std::sin(2 * M_PI * i / FN); }
        for (int i = 0; i < FN; i++) hann[i] = (float)(0.5 - 0.5 * std::cos(2 * M_PI * i / (FN - 1)));
    }
    void run(float* re, float* im) const {
        const int n = FN;
        for (int i = 1, j = 0; i < n; i++) {
            int b = n >> 1;
            for (; j & b; b >>= 1) j ^= b;
            j ^= b;
            if (i < j) { std::swap(re[i], re[j]); std::swap(im[i], im[j]); }
        }
        for (int len = 2; len <= n; len <<= 1) {
            int h = len >> 1, st = n / len;
            for (int i = 0; i < n; i += len)
                for (int j = 0, k = 0; j < h; j++, k += st) {
                    float wr = cosT[k], wi = sinT[k];
                    int a = i + j, b = a + h;
                    float tr = re[b] * wr - im[b] * wi, ti = re[b] * wi + im[b] * wr;
                    re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
                }
        }
    }
};
struct Lut {
    uint8_t c[256][3];
    Lut() {
        const double st[5][4] = {{0, 10, 14, 18}, {0.22, 16, 48, 66}, {0.5, 63, 176, 170}, {0.78, 236, 176, 92}, {1, 255, 248, 226}};
        for (int i = 0; i < 256; i++) {
            double t = i / 255.0;
            int k = 0;
            while (k < 3 && t > st[k + 1][0]) k++;
            double u = clampd((t - st[k][0]) / (st[k + 1][0] - st[k][0]), 0, 1);
            for (int ch = 0; ch < 3; ch++) c[i][ch] = (uint8_t)(st[k][1 + ch] + (st[k + 1][1 + ch] - st[k][1 + ch]) * u);
        }
    }
};
}  // namespace

std::vector<uint32_t> spectrogram(const Audio& a, int cols, int rows) {
    static const FFT fft;
    static const Lut lut;
    std::vector<uint32_t> img((size_t)cols * rows, 0xFF0A0E12u);
    const long n = (long)a.L.size();
    if (n == 0 || cols < 1 || rows < 2) return img;
    const double sr = a.sr, fmin = 30, fmax = sr / 2 * 0.95;
    const int half = FN / 2;
    std::vector<float> binOf(rows);
    for (int y = 0; y < rows; y++) binOf[y] = (float)(fmin * std::pow(fmax / fmin, 1 - (double)y / (rows - 1)) / (sr / 2) * half);
    float re[FN], im[FN];
    for (int c = 0; c < cols; c++) {
        long centre = (long)std::floor((c + 0.5) / cols * n) - FN / 2;
        for (int i = 0; i < FN; i++) {
            long k = centre + i;
            re[i] = (k >= 0 && k < n ? (a.L[k] + a.R[k]) * 0.5f : 0.0f) * fft.hann[i];
            im[i] = 0;
        }
        fft.run(re, im);
        for (int y = 0; y < rows; y++) {
            double bf = binOf[y];
            int b0 = std::min(half - 1, (int)std::floor(bf)), b1 = std::min(half - 1, b0 + 1);
            double fr = bf - b0;
            double m0 = std::hypot(re[b0], im[b0]), m1 = std::hypot(re[b1], im[b1]), m = (m0 * (1 - fr) + m1 * fr) / (FN / 4);
            double db = 20 * std::log10(m + 1e-9), t = clampd((db + 95) / 80, 0, 1);
            int li = (int)std::floor(t * 255);
            img[(size_t)y * cols + c] = 0xFF000000u | ((uint32_t)lut.c[li][0] << 16) | ((uint32_t)lut.c[li][1] << 8) | lut.c[li][2];
        }
    }
    return img;
}

}  // namespace strata
