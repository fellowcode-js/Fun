#include "mesh.h"
#include <cmath>

namespace dow {

static uint8_t u8(float f) { return (uint8_t)clampf(f * 255.f + 0.5f, 0, 255); }

uint32_t Mesh::vert(const Vec3& p, const Vec3& n, float u, float w) {
  Vertex x;
  x.px = p.x; x.py = p.y; x.pz = p.z; x.nx = n.x; x.ny = n.y; x.nz = n.z; x.u = u; x.v = w;
  x.r = u8(paint.c.r); x.g = u8(paint.c.g); x.b = u8(paint.c.b); x.emissive = u8(paint.emissive);
  x.tint = paint.tint ? 255 : 0; x.wobble = u8(paint.wobble); x.pad0 = x.pad1 = 0;
  v.push_back(x); return (uint32_t)v.size() - 1;
}

static Vec3 P(const Vertex& x) { return {x.px, x.py, x.pz}; }
static Vec3 N(const Vertex& x) { return {x.nx, x.ny, x.nz}; }

// Emit a triangle wound so its face normal agrees with the vertex normals (CCW = front).
static void triN(Mesh& m, uint32_t a, uint32_t b, uint32_t c) {
  Vec3 fa = P(m.v[a]), fb = P(m.v[b]), fc = P(m.v[c]);
  Vec3 fn = cross(fb - fa, fc - fa), vn = N(m.v[a]) + N(m.v[b]) + N(m.v[c]);
  if (dot(fn, vn) < 0) m.tri(a, c, b); else m.tri(a, b, c);
}
static void quadN(Mesh& m, uint32_t a, uint32_t b, uint32_t c, uint32_t d) { triN(m, a, b, c); triN(m, a, c, d); }

void Mesh::append(const Mesh& o) {
  uint32_t base = (uint32_t)v.size(); v.insert(v.end(), o.v.begin(), o.v.end());
  for (uint32_t i : o.idx) idx.push_back(base + i);
}

void Mesh::box(const Vec3& c, const Vec3& h, const Quat& q, float uvScale) {
  static const Vec3 ns[6] = {{1, 0, 0}, {-1, 0, 0}, {0, 1, 0}, {0, -1, 0}, {0, 0, 1}, {0, 0, -1}};
  for (const Vec3& n : ns) {
    Vec3 u = std::fabs(n.y) > 0.5f ? Vec3{1, 0, 0} : Vec3{0, 1, 0};
    Vec3 w = cross(n, u);  // n x u
    u = cross(w, n);       // so that u x w = n
    Vec3 hn = mul(n, h), hu = mul(u, h), hw = mul(w, h);
    Vec3 corners[4] = {hn - hu - hw, hn + hu - hw, hn + hu + hw, hn - hu + hw};
    uint32_t id[4];
    for (int k = 0; k < 4; k++) {
      Vec3 lp = corners[k], wp = c + q.rotate(lp), wn = q.rotate(n);
      float uu = (k == 1 || k == 2) ? 1.f : 0.f, vv = (k >= 2) ? 1.f : 0.f;
      if (uvScale > 0) {
        if (std::fabs(wn.y) > 0.5f) { uu = wp.x * uvScale; vv = wp.z * uvScale; }
        else if (std::fabs(wn.x) > 0.5f) { uu = wp.z * uvScale; vv = wp.y * uvScale; }
        else { uu = wp.x * uvScale; vv = wp.y * uvScale; }
      }
      id[k] = vert(wp, wn, uu, vv);
    }
    triN(*this, id[0], id[1], id[2]); triN(*this, id[0], id[2], id[3]);
  }
}

static float spow(float x, float e) { return (x < 0 ? -1.f : 1.f) * std::pow(std::fabs(x), e); }

void Mesh::roundBox(const Vec3& c, const Vec3& h, float e, const Quat& q, int seg) {
  // Superellipsoid: e=1 sphere, e->0 box. Normals from the implicit gradient.
  int rings = seg; size_t base = v.size();
  for (int i = 0; i <= rings; i++) {
    float t = -PI / 2 + PI * i / rings, ct = std::cos(t), st = std::sin(t);
    for (int j = 0; j <= seg * 2; j++) {
      float p = -PI + 2 * PI * j / (seg * 2), cp = std::cos(p), sp = std::sin(p);
      Vec3 lp{h.x * spow(ct, e) * spow(cp, e), h.y * spow(st, e), h.z * spow(ct, e) * spow(sp, e)};
      float ie = 2 - e;
      Vec3 ln{spow(ct, ie) * spow(cp, ie) / h.x, spow(st, ie) / h.y, spow(ct, ie) * spow(sp, ie) / h.z};
      vert(c + q.rotate(lp), normalize(q.rotate(ln)), (float)j / (seg * 2), (float)i / rings);
    }
  }
  int W = seg * 2 + 1;
  for (int i = 0; i < rings; i++) for (int j = 0; j < seg * 2; j++) {
    uint32_t a = (uint32_t)(base + i * W + j), b = a + 1, cc = a + W + 1, d = a + W;
    quadN(*this, a, b, cc, d);
  }
}

void Mesh::ellipsoid(const Vec3& c, const Vec3& r, const Quat& q, int seg, int rings) {
  size_t base = v.size();
  for (int i = 0; i <= rings; i++) {
    float t = PI * i / rings, st = std::sin(t), ct = std::cos(t);
    for (int j = 0; j <= seg; j++) {
      float p = 2 * PI * j / seg;
      Vec3 u{st * std::cos(p), ct, st * std::sin(p)};
      Vec3 lp = mul(u, r), ln = normalize(Vec3{u.x / r.x, u.y / r.y, u.z / r.z});
      vert(c + q.rotate(lp), q.rotate(ln), (float)j / seg, (float)i / rings);
    }
  }
  int W = seg + 1;
  for (int i = 0; i < rings; i++) for (int j = 0; j < seg; j++) {
    uint32_t a = (uint32_t)(base + i * W + j), b = a + 1, cc = a + W + 1, d = a + W;
    if (i == 0) triN(*this, a, cc, d); else if (i == rings - 1) triN(*this, a, b, cc); else quadN(*this, a, b, cc, d);
  }
}

void Mesh::lathe(const std::vector<Vec2>& prof, const Vec3& c, const Quat& q, int seg, const Vec3& sc) {
  size_t base = v.size(); int n = (int)prof.size();
  for (int i = 0; i < n; i++) {
    Vec2 a = prof[i > 0 ? i - 1 : i], b = prof[i < n - 1 ? i + 1 : i];
    float dr = b.x - a.x, dy = b.y - a.y; float l = std::sqrt(dr * dr + dy * dy); if (l < 1e-7f) { dr = 0; dy = 1; l = 1; }
    float nr = dy / l, ny = -dr / l;
    for (int j = 0; j <= seg; j++) {
      float p = 2 * PI * j / seg, cp = std::cos(p), sp = std::sin(p);
      Vec3 lp{prof[i].x * cp * sc.x, prof[i].y * sc.y, prof[i].x * sp * sc.z};
      Vec3 ln = normalize(Vec3{nr * cp / sc.x, ny / sc.y, nr * sp / sc.z});
      vert(c + q.rotate(lp), q.rotate(ln), (float)j / seg, (float)i / (n - 1));
    }
  }
  int W = seg + 1;
  for (int i = 0; i < n - 1; i++) for (int j = 0; j < seg; j++) {
    uint32_t a = (uint32_t)(base + i * W + j), b = a + 1, cc = a + W + 1, d = a + W;
    bool degA = prof[i].x < 1e-5f, degB = prof[i + 1].x < 1e-5f;
    if (degA && degB) continue;
    if (degA) triN(*this, a, cc, d); else if (degB) triN(*this, a, b, cc); else quadN(*this, a, b, cc, d);
  }
}

void Mesh::capsule(const Vec3& a, const Vec3& b, float ra, float rb, int seg, int rings) {
  Vec3 d = b - a; float L = length(d); Quat q = fromTo({0, 1, 0}, normalize(d));
  std::vector<Vec2> prof;
  for (int i = 0; i <= rings; i++) { float t = -PI / 2 + (PI / 2) * i / rings; prof.push_back({ra * std::cos(t), ra * std::sin(t)}); }
  for (int i = 0; i <= rings; i++) { float t = (PI / 2) * i / rings; prof.push_back({rb * std::cos(t), L + rb * std::sin(t)}); }
  prof.front().x = 0; prof.back().x = 0;
  lathe(prof, a, q, seg);
}

void Mesh::cylinder(const Vec3& a, const Vec3& b, float ra, float rb, int seg, bool caps) {
  Vec3 d = b - a; float L = length(d); Quat q = fromTo({0, 1, 0}, normalize(d));
  size_t base = v.size(); float slope = (ra - rb) / std::max(L, 1e-6f);
  for (int k = 0; k < 2; k++) for (int j = 0; j <= seg; j++) {
    float p = 2 * PI * j / seg, cp = std::cos(p), sp = std::sin(p), r = k ? rb : ra;
    vert(a + q.rotate({r * cp, k ? L : 0.f, r * sp}), q.rotate(normalize(Vec3{cp, slope, sp})), (float)j / seg, (float)k);
  }
  int W = seg + 1;
  for (int j = 0; j < seg; j++) quadN(*this, (uint32_t)(base + j), (uint32_t)(base + j + 1), (uint32_t)(base + W + j + 1), (uint32_t)(base + W + j));
  if (!caps) return;
  for (int k = 0; k < 2; k++) {
    float r = k ? rb : ra; if (r < 1e-5f) continue; Vec3 n = q.rotate({0, k ? 1.f : -1.f, 0});
    uint32_t cidx = vert(a + q.rotate({0, k ? L : 0.f, 0}), n, 0.5f, 0.5f); size_t rb0 = v.size();
    for (int j = 0; j <= seg; j++) { float p = 2 * PI * j / seg; vert(a + q.rotate({r * std::cos(p), k ? L : 0.f, r * std::sin(p)}), n, 0.5f + 0.5f * std::cos(p), 0.5f + 0.5f * std::sin(p)); }
    for (int j = 0; j < seg; j++) triN(*this, cidx, (uint32_t)(rb0 + j), (uint32_t)(rb0 + j + 1));
  }
}

void Mesh::tube(const std::vector<Vec3>& pts, const std::vector<float>& rad, int seg, bool caps) {
  int n = (int)pts.size(); if (n < 2) return;
  size_t base = v.size();
  Vec3 t0 = normalize(pts[1] - pts[0]);
  Vec3 ref = std::fabs(t0.y) < 0.9f ? Vec3{0, 1, 0} : Vec3{1, 0, 0};
  Vec3 nrm = normalize(cross(t0, ref)), bin;
  for (int i = 0; i < n; i++) {
    Vec3 t = normalize(i == 0 ? pts[1] - pts[0] : i == n - 1 ? pts[n - 1] - pts[n - 2] : pts[i + 1] - pts[i - 1]);
    nrm = normalize(nrm - t * dot(nrm, t), {1, 0, 0}); bin = cross(t, nrm);
    for (int j = 0; j <= seg; j++) {
      float p = 2 * PI * j / seg; Vec3 dir = nrm * std::cos(p) + bin * std::sin(p);
      vert(pts[i] + dir * rad[i], dir, (float)j / seg, (float)i / (n - 1));
    }
  }
  int W = seg + 1;
  for (int i = 0; i < n - 1; i++) for (int j = 0; j < seg; j++) {
    uint32_t a = (uint32_t)(base + i * W + j); quadN(*this, a, a + 1, a + W + 1, a + W);
  }
  if (!caps) return;
  for (int k = 0; k < 2; k++) {
    int i = k ? n - 1 : 0; Vec3 t = normalize(k ? pts[n - 1] - pts[n - 2] : pts[0] - pts[1]);
    uint32_t cidx = vert(pts[i], t); size_t r0 = v.size();
    for (int j = 0; j <= seg; j++) { Vertex x = v[base + i * W + j]; vert(P(x), t); }
    for (int j = 0; j < seg; j++) triN(*this, cidx, (uint32_t)(r0 + j), (uint32_t)(r0 + j + 1));
  }
}

void Mesh::torus(const Vec3& c, float R, float r, const Quat& q, int seg, int sides) {
  size_t base = v.size();
  for (int i = 0; i <= seg; i++) {
    float a = 2 * PI * i / seg; Vec3 dir{std::cos(a), 0, std::sin(a)};
    for (int j = 0; j <= sides; j++) {
      float b = 2 * PI * j / sides; Vec3 n = dir * std::cos(b) + Vec3{0, std::sin(b), 0};
      vert(c + q.rotate(dir * R + n * r), q.rotate(n), (float)i / seg, (float)j / sides);
    }
  }
  int W = sides + 1;
  for (int i = 0; i < seg; i++) for (int j = 0; j < sides; j++) { uint32_t a = (uint32_t)(base + i * W + j); quadN(*this, a, a + 1, a + W + 1, a + W); }
}

void Mesh::disc(const Vec3& c, float r, const Quat& q, int seg) {
  Vec3 n = q.rotate({0, 1, 0}); uint32_t ci = vert(c, n, 0.5f, 0.5f); size_t r0 = v.size();
  for (int j = 0; j <= seg; j++) { float p = 2 * PI * j / seg; vert(c + q.rotate({r * std::cos(p), 0, r * std::sin(p)}), n, 0.5f + 0.5f * std::cos(p), 0.5f + 0.5f * std::sin(p)); }
  for (int j = 0; j < seg; j++) triN(*this, ci, (uint32_t)(r0 + j), (uint32_t)(r0 + j + 1));
}

void Mesh::quadXY(const Vec3& c, float w, float h, const Quat& q, Vec2 a, Vec2 b) {
  Vec3 n = q.rotate({0, 0, 1});
  uint32_t i0 = vert(c + q.rotate({-w / 2, -h / 2, 0}), n, a.x, b.y);
  uint32_t i1 = vert(c + q.rotate({w / 2, -h / 2, 0}), n, b.x, b.y);
  uint32_t i2 = vert(c + q.rotate({w / 2, h / 2, 0}), n, b.x, a.y);
  uint32_t i3 = vert(c + q.rotate({-w / 2, h / 2, 0}), n, a.x, a.y);
  tri(i0, i1, i2); tri(i0, i2, i3);
}

void Mesh::transform(size_t from, const Mat4& m) {
  for (size_t i = from; i < v.size(); i++) {
    Vec3 p = m.point(P(v[i])), n = normalize(m.dir(N(v[i])));
    v[i].px = p.x; v[i].py = p.y; v[i].pz = p.z; v[i].nx = n.x; v[i].ny = n.y; v[i].nz = n.z;
  }
}

void Mesh::mirrorX(size_t from) {
  size_t n = v.size(); uint32_t off = (uint32_t)(n - from);
  size_t i0 = 0; while (i0 < idx.size() && idx[i0] < from) i0 += 3;  // first triangle touching the range
  size_t iend = idx.size();
  for (size_t i = from; i < n; i++) { Vertex x = v[i]; x.px = -x.px; x.nx = -x.nx; v.push_back(x); }
  for (size_t i = i0; i < iend; i += 3) {
    if (idx[i] < from) continue;
    tri(idx[i] + off, idx[i + 2] + off, idx[i + 1] + off);
  }
}

void Mesh::flipX() {
  for (auto& x : v) { x.px = -x.px; x.nx = -x.nx; }
  for (size_t i = 0; i + 2 < idx.size(); i += 3) std::swap(idx[i + 1], idx[i + 2]);
}

void Mesh::faceted(size_t fromIdx) {
  std::vector<uint32_t> old(idx.begin() + fromIdx, idx.end()); idx.resize(fromIdx);
  for (size_t i = 0; i + 2 < old.size(); i += 3) {
    Vertex a = v[old[i]], b = v[old[i + 1]], c = v[old[i + 2]];
    Vec3 fn = normalize(cross(P(b) - P(a), P(c) - P(a)));
    for (Vertex* x : {&a, &b, &c}) { x->nx = fn.x; x->ny = fn.y; x->nz = fn.z; v.push_back(*x); }
    uint32_t base = (uint32_t)v.size() - 3; tri(base, base + 1, base + 2);
  }
}

static float noise3(const Vec3& p, uint32_t s) { return (valueNoise(p.x + p.z * 0.71f, p.y, s) + valueNoise(p.y + 13.1f, p.z - p.x * 0.37f, s + 7)) * 0.5f; }

void Mesh::displace(size_t from, float amp, float freq, uint32_t seed) {
  for (size_t i = from; i < v.size(); i++) {
    Vec3 p = P(v[i]), n = N(v[i]); float d = (noise3(p * freq, seed) - 0.5f) * 2 * amp; p += n * d;
    v[i].px = p.x; v[i].py = p.y; v[i].pz = p.z;
  }
}

void Mesh::shadeVertical(size_t from, float y0, float y1, float dark) {
  for (size_t i = from; i < v.size(); i++) {
    float t = smooth01((v[i].py - y0) / (y1 - y0)), s = lerpf(1 - dark, 1, t);
    v[i].r = (uint8_t)(v[i].r * s); v[i].g = (uint8_t)(v[i].g * s); v[i].b = (uint8_t)(v[i].b * s);
  }
}

void Mesh::recolor(size_t from, Color c) { for (size_t i = from; i < v.size(); i++) { v[i].r = u8(c.r); v[i].g = u8(c.g); v[i].b = u8(c.b); } }

Vec3 Mesh::boundsMin() const { Vec3 m{1e9f, 1e9f, 1e9f}; for (auto& x : v) m = vmin(m, P(x)); return m; }
Vec3 Mesh::boundsMax() const { Vec3 m{-1e9f, -1e9f, -1e9f}; for (auto& x : v) m = vmax(m, P(x)); return m; }

}  // namespace dow
