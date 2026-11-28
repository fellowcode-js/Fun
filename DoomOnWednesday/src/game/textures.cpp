#include "textures.h"
#include <cmath>
#include <cstring>

namespace dow {

static uint8_t to8(float f) { return (uint8_t)clampf(f * 255.f + 0.5f, 0, 255); }
static void put(Image& im, int x, int y, Color c) { uint8_t* p = &im.px[(y * im.w + x) * 4]; p[0] = to8(c.r); p[1] = to8(c.g); p[2] = to8(c.b); p[3] = 255; }
static Image blank(int w, int h) { Image im; im.w = w; im.h = h; im.px.assign((size_t)w * h * 4, 255); return im; }

// Tileable noise: sample on a torus so textures wrap seamlessly.
static float tnoise(float u, float v, float freq, int oct, uint32_t seed) {
  float s = 0, a = 0.5f, n = 0;
  for (int o = 0; o < oct; o++) {
    int f = (int)freq << o; float x = u * f, y = v * f; int xi = (int)std::floor(x), yi = (int)std::floor(y); float fx = x - xi, fy = y - yi;
    fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy);
    auto H = [&](int X, int Y) { return hash2(((X % f) + f) % f, ((Y % f) + f) % f, seed + o * 31); };
    float val = lerpf(lerpf(H(xi, yi), H(xi + 1, yi), fx), lerpf(H(xi, yi + 1), H(xi + 1, yi + 1), fx), fy);
    s += val * a; n += a; a *= 0.5f;
  }
  return s / n;
}

Image makeWallpaper(int N) {
  // Backrooms wallpaper: mustard base, faint vertical bands, a repeating lozenge motif, grime and damp.
  Image im = blank(N, N);
  Color base = rgb(0xc9b468), band = rgb(0xbba65a), motif = rgb(0xa8924a), grime = rgb(0x7a6a34);
  for (int y = 0; y < N; y++) for (int x = 0; x < N; x++) {
    float u = (float)x / N, v = (float)y / N;
    Color c = base;
    float bands = 0.5f + 0.5f * std::cos(u * 2 * PI * 8);
    c = mixC(c, band, 0.35f * smooth01((bands - 0.6f) * 4));
    // lozenge grid: 4 x 4 per tile
    float gu = std::fmod(u * 4, 1.f) - 0.5f, gv = std::fmod(v * 4, 1.f) - 0.5f; float dd = std::fabs(gu) + std::fabs(gv) * 0.8f;
    float ring = std::fabs(dd - 0.28f); c = mixC(c, motif, 0.55f * (1 - smooth01(ring / 0.025f)));
    float dot = std::sqrt(gu * gu + gv * gv); c = mixC(c, motif, 0.5f * (1 - smooth01((dot - 0.035f) / 0.015f)));
    float n = tnoise(u, v, 8, 4, 3), stain = tnoise(u, v, 2, 3, 17);
    c = scaleC(c, 0.9f + 0.2f * n);
    c = mixC(c, grime, 0.35f * smooth01((stain - 0.62f) * 6));
    float fiber = hash2(x, y, 9) - 0.5f; c = scaleC(c, 1 + fiber * 0.05f);
    put(im, x, y, c);
  }
  return im;
}

Image makeCarpet(int N) {
  Image im = blank(N, N);
  Color base = rgb(0x9c8a4c), dark = rgb(0x6e5f30), damp = rgb(0x5c5028);
  for (int y = 0; y < N; y++) for (int x = 0; x < N; x++) {
    float u = (float)x / N, v = (float)y / N;
    float fib = hash2(x, y, 5), clump = tnoise(u, v, 32, 3, 7), patch = tnoise(u, v, 3, 3, 11);
    Color c = mixC(base, dark, 0.25f + 0.5f * (fib * 0.4f + clump * 0.6f) - 0.25f);
    c = mixC(c, damp, 0.55f * smooth01((patch - 0.6f) * 5));
    float loop = 0.5f + 0.5f * std::sin((x + y * 0.5f) * 1.7f) * std::sin(y * 1.9f); c = scaleC(c, 0.92f + 0.12f * loop);
    put(im, x, y, c);
  }
  return im;
}

Image makeCeiling(int N) {
  // one 1.2 m acoustic tile per texture repeat: off-white with pinholes, T-bar grid around the edge
  Image im = blank(N, N);
  Color tile = rgb(0xd6cfae), grid = rgb(0x9a9478), hole = rgb(0xa49e82), stain = rgb(0xb0a070);
  for (int y = 0; y < N; y++) for (int x = 0; x < N; x++) {
    float u = (float)x / N, v = (float)y / N; Color c = tile;
    float n = tnoise(u, v, 16, 3, 23); c = scaleC(c, 0.93f + 0.1f * n);
    if (hash2(x, y, 41) > 0.93f) c = mixC(c, hole, 0.8f);
    c = mixC(c, stain, 0.5f * smooth01((tnoise(u, v, 2, 3, 71) - 0.66f) * 5));
    int e = std::min(std::min(x, N - 1 - x), std::min(y, N - 1 - y)); if (e < 4) c = grid; else if (e < 6) c = scaleC(c, 0.85f);
    put(im, x, y, c);
  }
  return im;
}

// ---------------------------------------------------------------------------- font (5x7, drawn by hand)
static const uint8_t* glyph(char ch) {
  static const uint8_t blankG[7] = {0};
  struct G { char c; uint8_t r[7]; };
  static const G font[] = {
      {'A', {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}}, {'B', {0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E}}, {'C', {0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E}},
      {'D', {0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C}}, {'E', {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F}}, {'F', {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10}},
      {'G', {0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F}}, {'H', {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}}, {'I', {0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E}},
      {'J', {0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C}}, {'K', {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11}}, {'L', {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F}},
      {'M', {0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11}}, {'N', {0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11}}, {'O', {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E}},
      {'P', {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10}}, {'Q', {0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D}}, {'R', {0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11}},
      {'S', {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E}}, {'T', {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04}}, {'U', {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E}},
      {'V', {0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04}}, {'W', {0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A}}, {'X', {0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11}},
      {'Y', {0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04}}, {'Z', {0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F}},
      {'0', {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E}}, {'1', {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E}}, {'2', {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F}},
      {'3', {0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E}}, {'4', {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02}}, {'5', {0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E}},
      {'6', {0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E}}, {'7', {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08}}, {'8', {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E}},
      {'9', {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C}},
      {'!', {0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04}}, {'.', {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C}}, {',', {0x00, 0x00, 0x00, 0x00, 0x0C, 0x04, 0x08}},
      {':', {0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00}}, {'-', {0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00}}, {'+', {0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00}},
      {'=', {0x00, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00}}, {'/', {0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10}}, {'(', {0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02}},
      {')', {0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08}}, {'<', {0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02}}, {'>', {0x08, 0x04, 0x02, 0x01, 0x02, 0x04, 0x08}},
      {'?', {0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04}}, {'\'', {0x04, 0x04, 0x08, 0x00, 0x00, 0x00, 0x00}}, {'&', {0x0C, 0x12, 0x14, 0x08, 0x15, 0x12, 0x0D}},
      {'*', {0x00, 0x04, 0x15, 0x0E, 0x15, 0x04, 0x00}}, {'#', {0x0A, 0x0A, 0x1F, 0x0A, 0x1F, 0x0A, 0x0A}}, {'_', {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F}},
      {'"', {0x0A, 0x0A, 0x00, 0x00, 0x00, 0x00, 0x00}}, {'%', {0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03}},
  };
  if (ch >= 'a' && ch <= 'z') ch = (char)(ch - 32);
  for (const G& g : font) if (g.c == ch) return g.r;
  return blankG;
}

static const int CELL = 8, SCALE = 4, COLS = 16, ROWS = 6;

Image makeFontAtlas() {
  Image im; im.w = COLS * CELL * SCALE; im.h = ROWS * CELL * SCALE; im.px.assign((size_t)im.w * im.h * 4, 0);
  for (int ci = 0; ci < COLS * ROWS; ci++) {
    const uint8_t* g = glyph((char)(32 + ci)); int cx = (ci % COLS) * CELL, cy = (ci / COLS) * CELL;
    for (int r = 0; r < 7; r++) for (int b = 0; b < 5; b++) if (g[r] & (0x10 >> b))
      for (int sy = 0; sy < SCALE; sy++) for (int sx = 0; sx < SCALE; sx++) {
        int x = (cx + 1 + b) * SCALE + sx, y = (cy + r) * SCALE + sy; uint8_t* p = &im.px[(y * im.w + x) * 4]; p[0] = p[1] = p[2] = p[3] = 255;
      }
  }
  return im;
}

float textWidth(const std::string& t, float charH) {
  size_t best = 0, cur = 0; for (char c : t) { if (c == '\n') { best = std::max(best, cur); cur = 0; } else cur++; } best = std::max(best, cur);
  return best * charH * (6.f / 8.f);
}

void addText(Mesh& m, const std::string& text, const Vec3& origin, const Vec3& right, const Vec3& up, float H, Color c, float em) {
  // count lines
  std::vector<std::string> lines; { std::string cur; for (char ch : text) { if (ch == '\n') { lines.push_back(cur); cur.clear(); } else cur.push_back(ch); } lines.push_back(cur); }
  float adv = H * 6.f / 8.f, lh = H * 1.15f; Vec3 nrm = normalize(cross(right, up));
  Paint old = m.paint; m.paint = Paint{c, em, false, 0};
  for (size_t li = 0; li < lines.size(); li++) {
    const std::string& L = lines[li]; float w = L.size() * adv;
    float y0 = ((lines.size() - 1) * 0.5f - li) * lh;
    for (size_t i = 0; i < L.size(); i++) {
      int ci = (unsigned char)L[i] - 32; if (ci <= 0 || ci >= COLS * ROWS) continue;
      float u0 = (ci % COLS) * (float)CELL / (COLS * CELL), v0 = (ci / COLS) * (float)CELL / (ROWS * CELL), du = (float)CELL / (COLS * CELL), dv = (float)CELL / (ROWS * CELL);
      float x0 = -w * 0.5f + i * adv;
      Vec3 p0 = origin + right * x0 + up * (y0 - H * 0.5f), p1 = p0 + right * H, p2 = p1 + up * H, p3 = p0 + up * H;
      uint32_t a = m.vert(p0, nrm, u0, v0 + dv), b = m.vert(p1, nrm, u0 + du, v0 + dv), cc = m.vert(p2, nrm, u0 + du, v0), d = m.vert(p3, nrm, u0, v0);
      m.tri(a, b, cc); m.tri(a, cc, d);
    }
  }
  m.paint = old;
}

}  // namespace dow
