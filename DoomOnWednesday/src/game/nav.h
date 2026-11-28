// Bot navigation: a 0.5 m walkability grid per zone + breadth-first paths, smoothed by line of sight.
#pragma once
#include <vector>
#include "world.h"

namespace dow {

struct NavPath { std::vector<Vec3> pts; size_t idx = 0; bool done() const { return idx >= pts.size(); } };

struct NavGrid { Vec3 origin; int w = 0, h = 0; float cell = 0.5f; std::vector<uint8_t> free; bool built = false; };

class Nav {
 public:
  NavGrid grids[8];
  void build(World& w, int zone);
  bool isFree(int zone, const Vec3& p) const;
  bool findPath(int zone, const Vec3& from, const Vec3& to, NavPath& out) const;
  Vec3 randomFree(int zone, Rng& r) const;
  bool lineFree(int zone, const Vec3& a, const Vec3& b) const;
 private:
  bool cellOf(const NavGrid& g, const Vec3& p, int& x, int& y) const;
  Vec3 center(const NavGrid& g, int x, int y) const { return {g.origin.x + (x + 0.5f) * g.cell, 0, g.origin.z + (y + 0.5f) * g.cell}; }
};

}  // namespace dow
