#include "nav.h"
#include "maps.h"
#include <cmath>
#include <deque>
#include <algorithm>

namespace dow {

void Nav::build(World& w, int zone) {
  NavGrid& g = grids[zone]; if (g.built) return;
  const ZoneInfo& Z = zoneInfo(zone); Vec3 O = zone == ZONE_BACKROOMS ? Vec3{} : Z.origin;
  g.origin = O - Vec3{Z.half, 0, Z.half}; g.w = g.h = (int)std::ceil(Z.half * 2 / g.cell); g.free.assign((size_t)g.w * g.h, 0);
  int saved = w.activeZone; w.activeZone = zone;
  for (int y = 0; y < g.h; y++) for (int x = 0; x < g.w; x++) {
    Vec3 c = center(g, x, y);
    bool ok = !w.sphereContact(c + Vec3{0, 0.45f, 0}, 0.3f, 0).hit && !w.sphereContact(c + Vec3{0, 0.95f, 0}, 0.3f, 0).hit;
    g.free[y * g.w + x] = ok;
  }
  w.activeZone = saved; g.built = true;
}

bool Nav::cellOf(const NavGrid& g, const Vec3& p, int& x, int& y) const {
  x = (int)std::floor((p.x - g.origin.x) / g.cell); y = (int)std::floor((p.z - g.origin.z) / g.cell);
  return x >= 0 && y >= 0 && x < g.w && y < g.h;
}

bool Nav::isFree(int zone, const Vec3& p) const { const NavGrid& g = grids[zone]; int x, y; return g.built && cellOf(g, p, x, y) && g.free[y * g.w + x]; }

bool Nav::lineFree(int zone, const Vec3& a, const Vec3& b) const {
  const NavGrid& g = grids[zone]; Vec3 d = b - a; d.y = 0; int n = (int)(length(d) / (g.cell * 0.5f)) + 1;
  for (int i = 0; i <= n; i++) if (!isFree(zone, a + d * ((float)i / n))) return false;
  return true;
}

Vec3 Nav::randomFree(int zone, Rng& r) const {
  const NavGrid& g = grids[zone];
  for (int k = 0; k < 200; k++) { int x = (int)(r.f() * g.w), y = (int)(r.f() * g.h); if (x < g.w && y < g.h && g.free[y * g.w + x]) return center(g, x, y); }
  return g.origin + Vec3{g.w * g.cell / 2, 0, g.h * g.cell / 2};
}

bool Nav::findPath(int zone, const Vec3& from, const Vec3& to, NavPath& out) const {
  out.pts.clear(); out.idx = 0; const NavGrid& g = grids[zone]; if (!g.built) return false;
  int sx, sy, tx, ty; if (!cellOf(g, from, sx, sy) || !cellOf(g, to, tx, ty)) return false;
  auto snap = [&](int& x, int& y) {  // nearest free cell (bots can stand half inside a corner)
    if (g.free[y * g.w + x]) return true;
    for (int r = 1; r < 6; r++) for (int dy = -r; dy <= r; dy++) for (int dx = -r; dx <= r; dx++) {
      int nx = x + dx, ny = y + dy; if (nx >= 0 && ny >= 0 && nx < g.w && ny < g.h && g.free[ny * g.w + nx]) { x = nx; y = ny; return true; } }
    return false;
  };
  if (!snap(sx, sy) || !snap(tx, ty)) return false;
  std::vector<int> prev((size_t)g.w * g.h, -1); std::deque<int> q; int s = sy * g.w + sx, t = ty * g.w + tx; prev[s] = s; q.push_back(s);
  static const int DX[8] = {1, -1, 0, 0, 1, 1, -1, -1}, DY[8] = {0, 0, 1, -1, 1, -1, 1, -1};
  while (!q.empty() && prev[t] < 0) {
    int c = q.front(); q.pop_front(); int cx = c % g.w, cy = c / g.w;
    for (int k = 0; k < 8; k++) {
      int nx = cx + DX[k], ny = cy + DY[k]; if (nx < 0 || ny < 0 || nx >= g.w || ny >= g.h) continue; int n = ny * g.w + nx;
      if (prev[n] >= 0 || !g.free[n]) continue;
      if (k >= 4 && (!g.free[cy * g.w + nx] || !g.free[ny * g.w + cx])) continue;   // no corner cutting
      prev[n] = c; q.push_back(n);
    }
  }
  if (prev[t] < 0) return false;
  std::vector<Vec3> raw; for (int c = t; c != s; c = prev[c]) raw.push_back(center(g, c % g.w, c / g.w)); raw.push_back(center(g, sx, sy));
  std::reverse(raw.begin(), raw.end());
  // string-pull: keep only the corners we cannot see past
  Vec3 cur = raw[0]; size_t i = 0;
  while (i + 1 < raw.size()) { size_t j = raw.size() - 1; while (j > i + 1 && !lineFree(zone, cur, raw[j])) j--; out.pts.push_back(raw[j]); cur = raw[j]; i = j; }
  if (!out.pts.empty()) out.pts.back() = Vec3{to.x, 0, to.z};
  return true;
}

}  // namespace dow
