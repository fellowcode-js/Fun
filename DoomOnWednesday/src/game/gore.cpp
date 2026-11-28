#include "gore.h"
#include <cmath>

namespace dow {

Gore::Gore() { drops.resize(900); decals.resize(220); gibs.resize(48); }

void Gore::clear() { for (auto& d : drops) d.life = 0; for (auto& d : decals) d.live = false; for (auto& g : gibs) g.live = false; }

static Vec3 randDir(Rng& r) { for (;;) { Vec3 v{r.range(-1, 1), r.range(-1, 1), r.range(-1, 1)}; float l = length2(v); if (l > 0.01f && l <= 1) return v / std::sqrt(l); } }

void Gore::spray(const Vec3& p, const Vec3& dir, int count, float speed, float spread) {
  if (level <= 0) { poof(p, count / 3 + 4); return; }
  if (level >= 2) count *= 2;
  for (int i = 0; i < count; i++) {
    Drop& d = drops[nextDrop]; nextDrop = (nextDrop + 1) % drops.size();
    Vec3 v = normalize(dir + randDir(rng) * spread) * (speed * rng.range(0.35f, 1.15f));
    d.p = p + randDir(rng) * 0.03f; d.v = v; d.life = rng.range(1.2f, 2.4f); d.size = rng.range(0.008f, 0.02f) * (level >= 2 ? 1.3f : 1.f); d.poof = false;
  }
}

void Gore::poof(const Vec3& p, int count) {
  for (int i = 0; i < count; i++) {
    Drop& d = drops[nextDrop]; nextDrop = (nextDrop + 1) % drops.size();
    d.p = p + randDir(rng) * 0.08f; d.v = randDir(rng) * rng.range(0.3f, 1.2f) + Vec3{0, 0.6f, 0}; d.life = rng.range(0.4f, 0.8f); d.size = rng.range(0.03f, 0.06f); d.poof = true;
  }
}

void Gore::punch(const Vec3& p, const Vec3& dir) { spray(p, dir + Vec3{0, 0.4f, 0}, 14, 2.2f, 0.6f); }

void Gore::rip(int type, const Vec3& p, const Vec3& dir, Color fur, float scale) {
  Gib& g = gibs[nextGib]; nextGib = (nextGib + 1) % gibs.size();
  g = Gib{}; g.live = true; g.type = type; g.p = p; g.v = dir * 3.2f + Vec3{0, 2.0f, 0}; g.w = randDir(rng) * 9.f; g.life = 14; g.scale = scale; g.fur = fur; g.bleed = level > 0 ? 2.5f : 0;
  spray(p, dir + Vec3{0, 0.8f, 0}, 60, 3.6f, 0.55f);
  for (int i = 0; i < (level >= 2 ? 4 : 2); i++) {
    Gib& c = gibs[nextGib]; nextGib = (nextGib + 1) % gibs.size();
    c = Gib{}; c.live = level > 0; c.type = GIB_CHUNK; c.p = p; c.v = normalize(dir + randDir(rng) * 0.8f) * rng.range(2, 4) + Vec3{0, 1.5f, 0};
    c.w = randDir(rng) * 14.f; c.life = 10; c.scale = scale * rng.range(0.6f, 1.2f); c.fur = fur; c.bleed = 0.6f;
  }
}

void Gore::slice(const Vec3& p, const Vec3& dir, Color fur, float scale) {
  spray(p, dir + Vec3{0, 1.0f, 0}, 140, 4.5f, 0.7f);
  spray(p, -dir + Vec3{0, 0.6f, 0}, 60, 3.0f, 0.6f);
  for (int i = 0; i < (level >= 2 ? 8 : 4); i++) {
    Gib& c = gibs[nextGib]; nextGib = (nextGib + 1) % gibs.size();
    c = Gib{}; c.live = level > 0; c.type = i % 3 == 0 ? GIB_BONE : GIB_CHUNK; c.p = p; c.v = randDir(rng) * rng.range(1.5f, 4.f) + Vec3{0, 2.2f, 0};
    c.w = randDir(rng) * 16.f; c.life = 10; c.scale = scale * rng.range(0.6f, 1.3f); c.fur = fur; c.bleed = 0.8f;
  }
}

void Gore::decalAt(const Vec3& p, const Vec3& n, float size) {
  if (level <= 0) return;
  // merge into a nearby splat instead of stacking hundreds (keeps fill rate low on Quest)
  for (auto& d : decals) if (d.live && length2(d.p - p) < 0.0025f && dot(d.n, n) > 0.9f) { d.size = std::min(d.size + size * 0.25f, 0.35f); return; }
  Decal& d = decals[nextDecal]; nextDecal = (nextDecal + 1) % decals.size();
  d.live = true; d.p = p + n * 0.003f; d.n = n; d.size = size; d.rot = rng.range(0, 2 * PI); d.age = 0;
}

void Gore::update(float dt, const World& w) {
  for (auto& d : drops) {
    if (d.life <= 0) continue;
    d.life -= dt;
    if (d.poof) { d.v = d.v * (1 - 3 * dt); d.p += d.v * dt; continue; }
    d.v.y -= 9.81f * dt; Vec3 np = d.p + d.v * dt;
    Contact c = w.sphereContact(np, 0.006f, 2);
    if (c.hit) { decalAt(np + c.normal * (c.depth - 0.006f), c.normal, d.size * rng.range(3.5f, 7.f)); d.life = 0; continue; }
    d.p = np;
  }
  for (auto& d : decals) if (d.live) { d.age += dt; if (d.age > 90) d.live = false; }
  for (auto& g : gibs) {
    if (!g.live) continue;
    g.life -= dt; if (g.life <= 0) { g.live = false; continue; }
    if (g.bleed > 0 && level > 0) { g.bleed -= dt; if (rng.f() < 0.5f) spray(g.p, Vec3{0, -0.2f, 0} + g.v * 0.1f, 1, 0.6f, 0.5f); }
    if (g.rest) continue;
    float r = (g.type == GIB_HEAD ? 0.11f : g.type == GIB_CHUNK ? 0.035f : 0.06f) * g.scale;
    g.v.y -= 9.81f * dt; Vec3 np = g.p + g.v * dt;
    Vec3 q = np, n; Vec3 push = w.resolveSphere(q, r, 2, &n);
    if (length2(push) > 0) {
      float vn = dot(g.v, n); if (vn < 0) g.v -= n * (vn * 1.35f);  // bounce, restitution 0.35
      g.v = g.v * 0.82f; g.w = g.w * 0.7f;
      if (vn < -1.2f && level > 0) decalAt(q - n * r, n, 0.08f * g.scale);
      if (n.y > 0.7f && length(g.v) < 0.25f) { g.rest = true; g.v = {}; }
    }
    g.p = q;
    float wl = length(g.w); if (wl > 1e-4f) g.q = normalize(Quat::axisAngle(g.w / wl, wl * dt) * g.q);
  }
}

}  // namespace dow
