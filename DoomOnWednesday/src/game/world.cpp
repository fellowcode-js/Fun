#include "world.h"
#include "map_data.h"
#include "layout.h"
#include "maps.h"
#include <cmath>

namespace dow {

int World::add(const Vec3& mn, const Vec3& mx, uint8_t surface, uint8_t flag, float friction) {
  Collider c; c.mn = mn; c.mx = mx; c.surface = surface; c.flag = flag; c.friction = friction; cols.push_back(c); return (int)cols.size() - 1;
}

void World::buildLevel() {
  cols.clear();
  floorIdx = add({-400, -50, -400}, {400, 0, 400}, SURF_CARPET);
  buildZoneColliders(*this);
  ceilIdx = -1;
}

bool World::solidFor(int i, int role) const {
  const Collider& c = cols[i];
  if (!c.enabled) return false;
  if (c.zone >= 0 && activeZone >= 0 && c.zone != activeZone) return false;
  if (c.flag == COL_MOD_GATE) return role < 1;
  return true;
}

static inline bool boxContact(const Collider& b, const Vec3& p, float r, Contact& out) {
  Vec3 q = vclamp(p, b.mn, b.mx), d = p - q; float d2 = length2(d);
  if (d2 >= r * r) return false;
  if (d2 > 1e-12f) { float dl = std::sqrt(d2); out.normal = d / dl; out.depth = r - dl; return true; }
  float pen[6] = {p.x - b.mn.x, b.mx.x - p.x, p.y - b.mn.y, b.mx.y - p.y, p.z - b.mn.z, b.mx.z - p.z};
  int bi = 0; for (int k = 1; k < 6; k++) if (pen[k] < pen[bi]) bi = k;
  out.normal = {0, 0, 0}; out.normal[bi >> 1] = (bi & 1) ? 1.f : -1.f; out.depth = pen[bi] + r; return true;
}

Contact World::sphereContact(const Vec3& p, float r, int role, float skin) const {
  Contact best; float rr = r + skin;
  for (int i = 0; i < (int)cols.size(); i++) {
    const Collider& b = cols[i];
    if (p.x + rr < b.mn.x || p.x - rr > b.mx.x || p.z + rr < b.mn.z || p.z - rr > b.mx.z || p.y + rr < b.mn.y || p.y - rr > b.mx.y) continue;
    if (!solidFor(i, role)) continue;
    Contact c; if (!boxContact(b, p, rr, c)) continue;
    c.depth -= skin;
    if (!best.hit || c.depth > best.depth) { best = c; best.hit = true; best.collider = i; }
  }
  return best;
}

Vec3 World::resolveSphere(Vec3& p, float r, int role, Vec3* lastNormal) const {
  Vec3 start = p;
  for (int it = 0; it < 4; it++) {
    Contact c = sphereContact(p, r, role);
    if (!c.hit || c.depth <= 0) break;
    p += c.normal * (c.depth + 1e-4f);
    if (lastNormal) *lastNormal = c.normal;
  }
  return p - start;
}

SweepHit World::sweepSphere(const Vec3& a, const Vec3& b, float r, int role) const {
  SweepHit h; Vec3 d = b - a; float len = length(d);
  int steps = (int)std::ceil(len / std::max(r * 0.5f, 0.005f)); steps = std::max(1, std::min(steps, 48));
  Vec3 prev = a;
  for (int s = 1; s <= steps; s++) {
    float t = (float)s / steps; Vec3 p = a + d * t;
    Contact c = sphereContact(p, r, role);
    if (c.hit && c.depth > 0) {
      // bisect between prev (free) and p (touching) for the first contact point
      float lo = (float)(s - 1) / steps, hi = t;
      for (int k = 0; k < 6; k++) { float m = (lo + hi) * 0.5f; Contact cm = sphereContact(a + d * m, r, role); if (cm.hit && cm.depth > 0) hi = m; else lo = m; }
      Vec3 pos = a + d * hi; Contact ch = sphereContact(pos, r, role);
      if (ch.hit && ch.depth > 0) { pos += ch.normal * (ch.depth + 2e-4f); h.normal = ch.normal; h.collider = ch.collider; }
      else { h.normal = c.normal; h.collider = c.collider; }
      h.hit = true; h.pos = pos; h.t = hi; return h;
    }
    prev = p;
  }
  h.pos = b; h.t = 1; return h;
}

bool World::segmentBlocked(const Vec3& a, const Vec3& b, int role) const {
  Vec3 d = b - a;
  for (int i = 0; i < (int)cols.size(); i++) {
    if (i == floorIdx || i == ceilIdx || !solidFor(i, role)) continue;
    const Collider& c = cols[i]; float t0 = 0, t1 = 1; bool ok = true;
    for (int k = 0; k < 3 && ok; k++) {
      if (std::fabs(d[k]) < 1e-9f) { if (a[k] < c.mn[k] || a[k] > c.mx[k]) ok = false; continue; }
      float ta = (c.mn[k] - a[k]) / d[k], tb = (c.mx[k] - a[k]) / d[k]; if (ta > tb) std::swap(ta, tb);
      t0 = std::max(t0, ta); t1 = std::min(t1, tb); if (t0 > t1) ok = false;
    }
    if (ok) return true;
  }
  return false;
}

}  // namespace dow
