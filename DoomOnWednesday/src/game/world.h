// Collision world: axis-aligned boxes (walls, props, floor, ceiling, mod platforms) with sphere queries.
#pragma once
#include <vector>
#include "../core/math.h"

namespace dow {

enum Surface : uint8_t { SURF_CARPET = 0, SURF_WALL, SURF_WOOD, SURF_METAL, SURF_CEILING, SURF_PLATFORM };
enum ColliderFlag : uint8_t { COL_SOLID = 0, COL_MOD_GATE = 1, COL_DYNAMIC = 2 };

struct Collider {
  Vec3 mn, mx;
  uint8_t flag = COL_SOLID;
  uint8_t surface = SURF_WALL;
  bool enabled = true;
  float friction = 1.0f;  // 1 = sticky (gorilla grip), 0 = ice (hands slide)
  int8_t zone = -1;       // -1 = everywhere, else the zone (lobby / map) it belongs to
};

struct Contact {
  bool hit = false;
  Vec3 normal{0, 1, 0};
  float depth = 0;       // penetration (>0 means overlapping)
  int collider = -1;
};

struct SweepHit {
  bool hit = false;
  Vec3 pos;              // sphere centre where it came to rest
  Vec3 normal{0, 1, 0};
  float t = 1;           // fraction travelled
  int collider = -1;
};

class World {
 public:
  std::vector<Collider> cols;
  int floorIdx = -1, ceilIdx = -1;
  int activeZone = -1;                       // only this zone's colliders (and global ones) are solid

  int add(const Vec3& mn, const Vec3& mx, uint8_t surface, uint8_t flag = COL_SOLID, float friction = 1.f);
  void buildLevel();                         // every zone: main lobby + the four maps
  bool solidFor(int i, int role) const;
  // Deepest contact of a sphere against everything solid for `role`.
  Contact sphereContact(const Vec3& p, float r, int role, float skin = 0.f) const;
  // Push a sphere out of all geometry (few iterations). Returns accumulated push.
  Vec3 resolveSphere(Vec3& p, float r, int role, Vec3* lastNormal = nullptr) const;
  // Move a sphere from a to b, stopping at the first surface (sub-stepped, tunnel-proof for r >= 3 cm).
  SweepHit sweepSphere(const Vec3& a, const Vec3& b, float r, int role) const;
  // Segment vs world (for line-of-sight / bots); returns true if blocked.
  bool segmentBlocked(const Vec3& a, const Vec3& b, int role) const;
};

}  // namespace dow
