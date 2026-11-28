// Cosmetic gore: blood droplets with real arcs, splat decals where they land, flying gibs (ripped heads and
// arms, meat chunks) that bounce and keep bleeding. Gore level 0 = poof only, 1 = normal, 2 = extreme.
#pragma once
#include <vector>
#include "world.h"
#include "../core/mesh.h"

namespace dow {

enum GibType { GIB_CHUNK = 0, GIB_HEAD, GIB_ARM_L, GIB_ARM_R, GIB_BONE };

struct Drop { Vec3 p, v; float life = 0, size = 0.012f; bool poof = false; };
struct Decal { Vec3 p, n; float size = 0, rot = 0, age = 0; bool live = false; };
struct Gib { Vec3 p, v, w; Quat q; float life = 0, scale = 1, bleed = 0; int type = 0; Color fur; bool live = false; bool rest = false; };

class Gore {
 public:
  int level = 1;
  std::vector<Drop> drops; size_t nextDrop = 0;
  std::vector<Decal> decals; size_t nextDecal = 0;
  std::vector<Gib> gibs; size_t nextGib = 0;
  Rng rng{1234};

  Gore();
  void clear();
  void spray(const Vec3& p, const Vec3& dir, int count, float speed, float spread);
  void poof(const Vec3& p, int count);
  void punch(const Vec3& p, const Vec3& dir);
  void rip(int type, const Vec3& p, const Vec3& dir, Color fur, float scale);
  void slice(const Vec3& p, const Vec3& dir, Color fur, float scale);
  void update(float dt, const World& w);
 private:
  void decalAt(const Vec3& p, const Vec3& n, float size);
};

}  // namespace dow
