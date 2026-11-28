#include "maps.h"
#include "map_data.h"
#include "layout.h"
#include <cmath>

namespace dow {

// ------------------------------------------------------------------------------------------ zone table
static const ZoneInfo kZones[ZONE_COUNT] = {
    {"MAIN LOBBY", "pick your name, colour and mode", {0, 0, 100}, 14, 3.4f, TEX_WOOD, TEX_PLANKS, TEX_PLANKS,
     {1.0f, 0.72f, 0.42f}, 0, 7.f, 0.04f, {0.05f, 0.035f, 0.025f}, 5, 22, {0.08f, 0.06f, 0.05f}, {0.2f, 0.16f, 0.12f}, false, 0xffb347},
    {"THE BACKROOMS", "Level 0. Endless yellow halls.", {0, 0, 0}, 30, 3.2f, TEX_WALLPAPER, TEX_CARPET, TEX_CEILING,
     {1.05f, 0.95f, 0.62f}, 4, 7.5f, 0.1f, {0.09f, 0.075f, 0.03f}, 4, 28, {0.1f, 0.09f, 0.05f}, {0.3f, 0.27f, 0.16f}, false, 0xf2cc26},
    {"THE POOLROOMS", "Warm water. Too quiet.", {200, 0, 0}, 18, 4.5f, TEX_TILE, TEX_TILE, TEX_TILE,
     {0.9f, 1.0f, 1.05f}, 6, 9.f, 0.02f, {0.55f, 0.66f, 0.7f}, 6, 34, {0.22f, 0.26f, 0.28f}, {0.45f, 0.55f, 0.6f}, false, 0x44ccee},
    {"PARKING GARAGE", "Level 1. Something is under the cars.", {-200, 0, 0}, 20, 2.9f, TEX_CONCRETE, TEX_CONCRETE, TEX_CONCRETE,
     {1.1f, 0.62f, 0.22f}, 8, 8.f, 0.25f, {0.03f, 0.025f, 0.02f}, 2, 20, {0.04f, 0.035f, 0.03f}, {0.1f, 0.08f, 0.06f}, false, 0xff8822},
    {"LIGHTS OUT", "The power is gone. Bring a friend.", {0, 0, -200}, 18, 3.0f, TEX_WALLPAPER, TEX_CARPET, TEX_CEILING,
     {1.0f, 0.12f, 0.08f}, 0, 6.f, 0.3f, {0.004f, 0.003f, 0.003f}, 1, 13, {0.01f, 0.008f, 0.006f}, {0.02f, 0.015f, 0.01f}, true, 0xcc2222},
    {"ADMIN ROOM", "staff only: test everything", {0, 0, 300}, 10, 3.6f, TEX_CONCRETE, TEX_TILE, TEX_CONCRETE,
     {0.85f, 0.92f, 1.05f}, 4, 8.f, 0.0f, {0.05f, 0.055f, 0.07f}, 6, 30, {0.12f, 0.13f, 0.15f}, {0.3f, 0.32f, 0.36f}, false, 0x66ccff},
};
const ZoneInfo& zoneInfo(int z) { return kZones[(z >= 0 && z < ZONE_COUNT) ? z : 0]; }

int zoneAt(const Vec3& p) {
  for (int z = 0; z < ZONE_COUNT; z++) { const ZoneInfo& Z = kZones[z]; if (std::fabs(p.x - Z.origin.x) < Z.half + 3 && std::fabs(p.z - Z.origin.z) < Z.half + 3) return z; }
  return ZONE_BACKROOMS;
}

static float uvScaleFor(int tex) { return tex == TEX_WALLPAPER ? 0.4f : tex == TEX_TILE ? 1 / 1.6f : tex == TEX_CONCRETE ? 0.5f : 0.5f; }

// ------------------------------------------------------------------------------------------ builder
struct ZB {
  int zone; World* w; ZoneMeshes* m; Vec3 O; float uv;
  void wall(Vec3 a, Vec3 b, bool trim = true, uint8_t surf = SURF_WALL) {          // local min/max corners
    Vec3 mn = O + vmin(a, b), mx = O + vmax(a, b);
    if (w) { int i = w->add(mn, mx, surf); w->cols[i].zone = (int8_t)zone; }
    if (m) {
      m->walls.paint = Paint{}; m->walls.box((mn + mx) * 0.5f, (mx - mn) * 0.5f, {}, uv);
      if (trim && mn.y < 0.01f) { Vec3 c = (mn + mx) * 0.5f, h = (mx - mn) * 0.5f + Vec3{0.014f, 0, 0.014f}; m->trim.box({c.x, 0.06f, c.z}, {h.x, 0.06f, h.z}); }
    }
  }
  void solid(Vec3 c, Vec3 h, uint8_t surf = SURF_METAL) { if (w) { int i = w->add(O + c - h, O + c + h, surf); w->cols[i].zone = (int8_t)zone; } }
  Mesh* props() { return m ? &m->props : nullptr; }
  void light(Vec3 p) { if (m) m->lights.push_back(O + p); }
  void floorCeil(float half, float H, int floorTex, int ceilTex) {
    if (w) { int i = w->add(O + Vec3{-half - 1, H, -half - 1}, O + Vec3{half + 1, H + 5, half + 1}, SURF_CEILING); w->cols[i].zone = (int8_t)zone; }
    if (!m) return;
    float fs = floorTex == TEX_CARPET ? 0.5f : floorTex == TEX_TILE ? 1 / 1.6f : 0.5f, cs = ceilTex == TEX_CEILING ? 1 / 1.2f : ceilTex == TEX_TILE ? 1 / 1.6f : 0.5f;
    float a = half + 0.5f;
    Mesh& f = m->floor; uint32_t i0 = f.vert(O + Vec3{-a, 0, -a}, {0, 1, 0}, (O.x - a) * fs, (O.z - a) * fs), i1 = f.vert(O + Vec3{a, 0, -a}, {0, 1, 0}, (O.x + a) * fs, (O.z - a) * fs),
             i2 = f.vert(O + Vec3{a, 0, a}, {0, 1, 0}, (O.x + a) * fs, (O.z + a) * fs), i3 = f.vert(O + Vec3{-a, 0, a}, {0, 1, 0}, (O.x - a) * fs, (O.z + a) * fs);
    f.tri(i0, i2, i1); f.tri(i0, i3, i2);
    Mesh& c = m->ceiling; uint32_t j0 = c.vert(O + Vec3{-a, H, -a}, {0, -1, 0}, (O.x - a) * cs, (O.z - a) * cs), j1 = c.vert(O + Vec3{a, H, -a}, {0, -1, 0}, (O.x + a) * cs, (O.z - a) * cs),
             j2 = c.vert(O + Vec3{a, H, a}, {0, -1, 0}, (O.x + a) * cs, (O.z + a) * cs), j3 = c.vert(O + Vec3{-a, H, a}, {0, -1, 0}, (O.x - a) * cs, (O.z + a) * cs);
    c.tri(j0, j1, j2); c.tri(j0, j2, j3);
  }
};

static void P(Mesh* m, uint32_t hex, float em = 0) { if (m) m->paint = Paint{rgb(hex), em, false, 0}; }

// ------------------------------------------------------------------------------------------ main lobby
const char* const kLobbyKeys[] = {
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "UP",
    "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "DOWN",
    "A", "S", "D", "F", "G", "H", "J", "K", "L", "DEL",
    "Z", "X", "C", "V", "B", "N", "M", "ENTER",
    "OPT1", "OPT2", "OPT3", "OPT4"};
const int kNumLobbyKeys = sizeof(kLobbyKeys) / sizeof(kLobbyKeys[0]);
static const int kRowStart[6] = {0, 11, 22, 32, 40, 44};

Vec3 lobbyKey(int i) {
  int row = 0; while (row < 4 && i >= kRowStart[row + 1]) row++;
  int col = i - kRowStart[row]; float pitch = 0.078f, w = (kRowStart[row + 1] - kRowStart[row]) * pitch;
  float x = -w / 2 + pitch / 2 + col * pitch + (row == 4 ? 0 : row * 0.018f);
  if (row == 4) { pitch = 0.16f; x = -0.24f + col * pitch; }
  return kZones[ZONE_LOBBY].origin + Vec3{x, 0.735f, -3.17f + row * 0.08f};
}
Vec3 lobbyScreenCenter() { return kZones[ZONE_LOBBY].origin + Vec3{0, 1.22f, -3.536f}; }
Vec3 votePadButton(int map) { return kZones[ZONE_LOBBY].origin + Vec3{-12.2f, 0.935f, -3.0f + map * 2.0f}; }
Vec3 readyButton() { return kZones[ZONE_LOBBY].origin + Vec3{-7.0f, 0.935f, 3.2f}; }
Vec3 adminSpawn() { return kZones[ZONE_ADMIN].origin + Vec3{0, 0, 1.0f}; }
Vec3 adminButton(int row, int col) { return kZones[ZONE_ADMIN].origin + Vec3{-2.1f + col * 0.6f, 0.895f, -4.62f - row * 0.2f}; }
Vec3 lobbySpawn() { return kZones[ZONE_LOBBY].origin + Vec3{0, 0.47f, -2.3f}; }
float lobbySpawnYaw() { return 0; }

static void buildLobby(ZB& b) {
  const float H = 3.4f, T = 0.3f;
  // main room x[-5,5] z[-4,4]; door on the west wall (your left at the computer) into the vote room x[-13,-5]
  b.wall({-5, 0, -4 - T}, {5, H, -4});  b.wall({-5, 0, 4}, {5, H, 4 + T});  b.wall({5, 0, -4}, {5 + T, H, 4});
  b.wall({-5 - T, 0, -4}, {-5, H, -1.1f}); b.wall({-5 - T, 0, 1.1f}, {-5, H, 4}); b.wall({-5 - T, 2.5f, -1.1f}, {-5, H, 1.1f}, false);
  b.wall({-13, 0, -4 - T}, {-5, H, -4}); b.wall({-13, 0, 4}, {-5, H, 4 + T}); b.wall({-13 - T, 0, -4}, {-13, H, 4});
  b.floorCeil(14, H, TEX_PLANKS, TEX_PLANKS);
  // computer desk, keyboard, monitor, stool (spawn)
  b.solid({0, 0.35f, -3.2f}, {1.1f, 0.35f, 0.45f}, SURF_WOOD);
  b.solid({0, 0.23f, -2.3f}, {0.2f, 0.23f, 0.2f}, SURF_WOOD);
  for (int i = 0; i < kNumMaps; i++) b.solid({-12.2f, 0.45f, -3.0f + i * 2.0f}, {0.32f, 0.45f, 0.4f}, SURF_METAL);
  b.solid({-7.0f, 0.45f, 3.2f}, {0.32f, 0.45f, 0.32f}, SURF_METAL);
  Mesh* p = b.props(); if (!p) { return; }
  const Vec3 O = b.O;
  P(p, 0x4a2e1a); p->box(O + Vec3{0, 0.68f, -3.2f}, {1.12f, 0.025f, 0.47f});
  for (int sx = -1; sx <= 1; sx += 2) for (int sz = -1; sz <= 1; sz += 2) p->box(O + Vec3{sx * 1.02f, 0.33f, -3.2f + sz * 0.38f}, {0.04f, 0.33f, 0.04f});
  P(p, 0x2a1c12); p->box(O + Vec3{0, 0.36f, -3.62f}, {1.06f, 0.3f, 0.02f});
  P(p, 0x141418); p->box(O + Vec3{0, 0.713f, -3.0f}, {0.97f, 0.012f, 0.22f});
  P(p, 0x1c1c22); p->roundBox(O + Vec3{0, 1.22f, -3.6f}, {0.92f, 0.5f, 0.05f}, 0.15f, {}, 8);
  P(p, 0x2a2a30); p->box(O + Vec3{0, 0.82f, -3.6f}, {0.08f, 0.12f, 0.04f});
  P(p, 0x9a2a22); p->cylinder(O + Vec3{0, 0.43f, -2.3f}, O + Vec3{0, 0.47f, -2.3f}, 0.21f, 0.2f, 20, true);
  P(p, 0x5a5a62); for (int i = 0; i < 3; i++) { float a = i * 2 * PI / 3; p->cylinder(O + Vec3{0.16f * std::cos(a), 0, -2.3f + 0.16f * std::sin(a)}, O + Vec3{0.06f * std::cos(a), 0.43f, -2.3f + 0.06f * std::sin(a)}, 0.015f, 0.015f, 6, true); }
  // door frame
  P(p, 0x2a1a10); p->box(O + Vec3{-5.15f, 2.55f, 0}, {0.2f, 0.06f, 1.2f}); p->box(O + Vec3{-5.15f, 1.25f, -1.15f}, {0.2f, 1.25f, 0.06f}); p->box(O + Vec3{-5.15f, 1.25f, 1.15f}, {0.2f, 1.25f, 0.06f});
  // vote pads + portal frames on the west wall
  for (int i = 0; i < kNumMaps; i++) {
    float z = -3.0f + i * 2.0f; const ZoneInfo& Z = kZones[1 + i];
    P(p, 0x2a2a30); p->box(O + Vec3{-12.2f, 0.45f, z}, {0.32f, 0.45f, 0.4f});
    P(p, Z.accent, 0.5f); p->box(O + Vec3{-12.2f, 0.905f, z}, {0.34f, 0.012f, 0.42f});
    P(p, 0x15100c); p->box(O + Vec3{-12.95f, 1.75f, z}, {0.04f, 0.75f, 0.85f});
    P(p, Z.accent, 0.9f); p->box(O + Vec3{-12.9f, 2.52f, z}, {0.03f, 0.03f, 0.86f}); p->box(O + Vec3{-12.9f, 0.98f, z}, {0.03f, 0.03f, 0.86f});
    p->box(O + Vec3{-12.9f, 1.75f, z - 0.85f}, {0.03f, 0.78f, 0.03f}); p->box(O + Vec3{-12.9f, 1.75f, z + 0.85f}, {0.03f, 0.78f, 0.03f});
  }
  P(p, 0x2a2a30); p->box(O + Vec3{-7.0f, 0.45f, 3.2f}, {0.32f, 0.45f, 0.32f});
  P(p, 0xffd34d); for (int i = 0; i < 4; i++) { P(p, i % 2 ? 0x111111 : 0xe8b820); p->box(O + Vec3{-7.0f, 0.1f + i * 0.04f, 3.2f}, {0.325f, 0.02f, 0.325f}); }
  // hanging lanterns (also the lights)
  for (Vec3 l : {Vec3{-2.5f, 2.9f, -1.5f}, Vec3{2.5f, 2.9f, -1.5f}, Vec3{0, 2.9f, 2.2f}, Vec3{-9, 2.9f, -2}, Vec3{-9, 2.9f, 2}}) {
    P(p, 0x1a1a1a); p->cylinder(O + l + Vec3{0, 0.12f, 0}, O + l + Vec3{0, 3.4f - l.y, 0}, 0.006f, 0.006f, 4, false);
    p->box(O + l + Vec3{0, 0.13f, 0}, {0.1f, 0.012f, 0.1f}); p->box(O + l - Vec3{0, 0.13f, 0}, {0.1f, 0.012f, 0.1f});
    P(p, 0xffb060, 1.0f); p->box(O + l, {0.085f, 0.12f, 0.085f});
    b.light(l);
  }
  // crates, a rug, cobwebby shelves for mood
  P(p, 0x5a3a1c); for (Vec3 c : {Vec3{4.2f, 0.3f, -3.3f}, Vec3{4.2f, 0.3f, -2.6f}, Vec3{4.25f, 0.85f, -3.0f}}) p->box(O + c, {0.3f, 0.3f, 0.3f}, Quat::yaw(c.z * 0.4f));
  b.solid({4.2f, 0.55f, -3.0f}, {0.35f, 0.55f, 0.7f}, SURF_WOOD);
  P(p, 0x4a1414); p->box(O + Vec3{0, 0.004f, 0.8f}, {2.2f, 0.004f, 1.6f}); P(p, 0x7a5a1a); p->box(O + Vec3{0, 0.006f, 0.8f}, {2.0f, 0.004f, 1.4f}); P(p, 0x4a1414); p->box(O + Vec3{0, 0.008f, 0.8f}, {1.8f, 0.004f, 1.2f});
}

// ------------------------------------------------------------------------------------------ maps
static void buildBackrooms(ZB& b) {
  for (int i = 0; i < kNumWalls; i++) {
    const WallDef& w = kWalls[i]; Vec3 mn{w.mn[0], w.mn[1], w.mn[2]}, mx{w.mx[0], w.mx[1], w.mx[2]};
    if (w.flag == 1) { if (b.w) { int k = b.w->add(mn, mx, SURF_WALL, COL_MOD_GATE); b.w->cols[k].zone = (int8_t)b.zone; } continue; }
    b.wall(mn, mx);
  }
  for (const PropBox& p : kPropBoxes) b.solid(p.c, p.h, p.surface);
  b.floorCeil(30, kRoomH, TEX_CARPET, TEX_CEILING);
  if (b.m) for (float x = -28; x <= 28.01f; x += 4) for (float z = -28; z <= 28.01f; z += 4) b.light({x, kRoomH, z});
}

static void buildPoolrooms(ZB& b) {
  const float S = 18, H = 4.5f, T = 0.4f;
  b.wall({-S - T, 0, -S - T}, {S + T, H, -S}); b.wall({-S - T, 0, S}, {S + T, H, S + T}); b.wall({-S - T, 0, -S}, {-S, H, S}); b.wall({S, 0, -S}, {S + T, H, S});
  for (int i = -2; i <= 2; i++) for (int j = -2; j <= 2; j++) { if (!i && !j) continue; b.wall({i * 6.f - 0.4f, 0, j * 6.f - 0.4f}, {i * 6.f + 0.4f, H, j * 6.f + 0.4f}, false); }
  // half walls / alcoves
  b.wall({-12, 0, -3.2f}, {-6.4f, 1.2f, -2.8f}, false); b.wall({6.4f, 0, 2.8f}, {12, 1.2f, 3.2f}, false); b.wall({-3, 0, 9}, {3, 2.2f, 9.4f}, false);
  b.wall({-17.6f, 0, 8}, {-12, 2.8f, 8.4f}, false); b.wall({12, 0, -8.4f}, {17.6f, 2.8f, -8}, false);
  // raised tiled platforms you can climb with your arms
  b.wall({8, 0, -16}, {14, 0.55f, -11}, false); b.wall({-15, 0, 11}, {-9, 0.9f, 16}, false); b.wall({-2, 0, -16}, {2, 1.4f, -13.5f}, false);
  b.floorCeil(S, H, TEX_TILE, TEX_TILE);
  // pools: tiled rims + glowing water
  struct Pool { float x0, z0, x1, z1; } pools[] = {{-14, -14, -8, -8}, {2, 6, 10, 12}, {-4, -6, 4, -1}};
  for (auto& q : pools) {
    b.wall({q.x0, 0, q.z0}, {q.x1, 0.3f, q.z0 + 0.25f}, false); b.wall({q.x0, 0, q.z1 - 0.25f}, {q.x1, 0.3f, q.z1}, false);
    b.wall({q.x0, 0, q.z0}, {q.x0 + 0.25f, 0.3f, q.z1}, false); b.wall({q.x1 - 0.25f, 0, q.z0}, {q.x1, 0.3f, q.z1}, false);
    if (b.m) { b.m->water.paint = Paint{rgb(0x2a9ab8), 0.35f, false, 0}; Vec3 c = b.O + Vec3{(q.x0 + q.x1) / 2, 0.2f, (q.z0 + q.z1) / 2}; b.m->water.box(c, {(q.x1 - q.x0) / 2 - 0.25f, 0.005f, (q.z1 - q.z0) / 2 - 0.25f}); }
  }
  if (b.m) for (float x = -15; x <= 15.01f; x += 6) for (float z = -15; z <= 15.01f; z += 6) b.light({x, H, z});
}

static float side_(int i) { return (i % 2) ? -1.f : 1.f; }

static void car(ZB& b, Vec3 c, float yaw, uint32_t col) {
  Quat q = Quat::yaw(yaw); bool along = std::fabs(std::sin(yaw)) > 0.5f;
  Vec3 h = along ? Vec3{2.1f, 0.55f, 0.95f} : Vec3{0.95f, 0.55f, 2.1f};
  b.solid(c + Vec3{0, 0.55f, 0}, h, SURF_METAL);
  Mesh* p = b.props(); if (!p) return; Vec3 O = b.O;
  P(p, col); p->roundBox(O + c + Vec3{0, 0.55f, 0}, {0.92f, 0.32f, 2.05f}, 0.25f, q, 10);
  P(p, col); p->roundBox(O + c + Vec3{0, 0.98f, 0} + q.rotate({0, 0, 0.2f}), {0.82f, 0.28f, 1.05f}, 0.3f, q, 10);
  P(p, 0x0a0c10, 0.05f); p->roundBox(O + c + Vec3{0, 1.0f, 0} + q.rotate({0, 0, 0.2f}), {0.84f, 0.2f, 0.95f}, 0.25f, q, 8);
  P(p, 0x111111); for (int sx = -1; sx <= 1; sx += 2) for (int sz = -1; sz <= 1; sz += 2) { Vec3 w = c + q.rotate({sx * 0.86f, 0.32f, sz * 1.35f}); p->cylinder(O + w - q.rotate({0.12f, 0, 0}), O + w + q.rotate({0.12f, 0, 0}), 0.32f, 0.32f, 14, true); }
  P(p, 0xfff0c0, 0.3f); for (int sx = -1; sx <= 1; sx += 2) p->box(O + c + q.rotate({sx * 0.6f, 0.62f, -2.06f}), {0.15f, 0.05f, 0.01f}, q);
  P(p, 0xaa1111, 0.4f); for (int sx = -1; sx <= 1; sx += 2) p->box(O + c + q.rotate({sx * 0.65f, 0.65f, 2.06f}), {0.12f, 0.05f, 0.01f}, q);
}

static void buildGarage(ZB& b) {
  const float S = 20, H = 2.9f, T = 0.4f;
  b.wall({-S - T, 0, -S - T}, {S + T, H, -S}); b.wall({-S - T, 0, S}, {S + T, H, S + T}); b.wall({-S - T, 0, -S}, {-S, H, S}); b.wall({S, 0, -S}, {S + T, H, S});
  for (int i = -3; i <= 3; i++) for (int j = -3; j <= 3; j++) b.wall({i * 5.f - 0.3f, 0, j * 5.f + 2.5f - 0.3f}, {i * 5.f + 0.3f, H, j * 5.f + 2.5f + 0.3f}, false);
  b.wall({-20, 0, -0.2f}, {-6, 1.0f, 0.2f}, false); b.wall({6, 0, -0.2f}, {20, 1.0f, 0.2f}, false);   // jersey barriers
  b.floorCeil(S, H, TEX_CONCRETE, TEX_CONCRETE);
  static const uint32_t cols[] = {0x7a1a1a, 0x1a3a6a, 0x2a2a2a, 0x8a8a8a, 0x2a5a2a, 0x6a5a1a};
  Rng r(404); int k = 0;
  for (int i = -3; i < 3; i++) for (int side = -1; side <= 1; side += 2) {
    if (r.f() < 0.35f) continue;
    car(b, {i * 5.f + 2.5f, 0, side * 6.2f}, 0, cols[k++ % 6]);
  }
  for (int i = -3; i < 3; i++) if (r.f() < 0.6f) car(b, {i * 5.f + 2.5f, 0, side_(i) * 15.f}, 0, cols[k++ % 6]);
  if (Mesh* p = b.props()) { P(p, 0xd8b020); for (int i = -4; i <= 4; i++) for (int s = -1; s <= 1; s += 2) p->box(b.O + Vec3{i * 5.f, 0.004f, s * 6.2f}, {0.05f, 0.004f, 2.2f}); }
  if (b.m) for (float x = -16; x <= 16.01f; x += 8) for (float z = -16; z <= 16.01f; z += 8) b.light({x, H, z});
}

static void buildLightsOut(ZB& b) {
  // generated maze: 9 x 9 cells of 4 m, depth-first carve + extra loops so monsters can cut you off
  const int N = 9; const float C = 4, S = N * C / 2, H = 3.0f, T = 0.3f;
  bool east[N][N], south[N][N], seen[N][N] = {};
  for (int i = 0; i < N; i++) for (int j = 0; j < N; j++) east[i][j] = south[i][j] = true;
  Rng r(1337); std::vector<std::pair<int, int>> st{{0, 0}}; seen[0][0] = true;
  while (!st.empty()) {
    auto [x, y] = st.back(); int opts[4], n = 0;
    if (x > 0 && !seen[x - 1][y]) opts[n++] = 0; if (x < N - 1 && !seen[x + 1][y]) opts[n++] = 1; if (y > 0 && !seen[x][y - 1]) opts[n++] = 2; if (y < N - 1 && !seen[x][y + 1]) opts[n++] = 3;
    if (!n) { st.pop_back(); continue; }
    int d = opts[r.next() % n];
    if (d == 0) { east[x - 1][y] = false; seen[x - 1][y] = true; st.push_back({x - 1, y}); }
    if (d == 1) { east[x][y] = false; seen[x + 1][y] = true; st.push_back({x + 1, y}); }
    if (d == 2) { south[x][y - 1] = false; seen[x][y - 1] = true; st.push_back({x, y - 1}); }
    if (d == 3) { south[x][y] = false; seen[x][y + 1] = true; st.push_back({x, y + 1}); }
  }
  for (int k = 0; k < 22; k++) { int x = r.next() % (N - 1), y = r.next() % (N - 1); if (r.f() < 0.5f) east[x][y] = false; else south[x][y] = false; }
  b.wall({-S - T, 0, -S - T}, {S + T, H, -S}); b.wall({-S - T, 0, S}, {S + T, H, S + T}); b.wall({-S - T, 0, -S}, {-S, H, S}); b.wall({S, 0, -S}, {S + T, H, S});
  for (int i = 0; i < N; i++) for (int j = 0; j < N; j++) {
    float x0 = -S + i * C, z0 = -S + j * C;
    if (i < N - 1 && east[i][j]) b.wall({x0 + C - T / 2, 0, z0}, {x0 + C + T / 2, H, z0 + C});
    if (j < N - 1 && south[i][j]) b.wall({x0, 0, z0 + C - T / 2}, {x0 + C, H, z0 + C + T / 2});
  }
  b.floorCeil(S, H, TEX_CARPET, TEX_CEILING);
  if (b.m) for (int k = 0; k < 10; k++) { int i = r.next() % N, j = r.next() % N; Vec3 l{-S + i * C + C / 2, H - 0.05f, -S + j * C + C / 2}; b.light(l);
    P(&b.m->props, 0xff2010, 1.0f); b.m->props.box(b.O + l, {0.12f, 0.04f, 0.06f}); }
}

static void buildAdmin(ZB& b) {
  const float S = 8, D = 6, H = 3.6f, T = 0.3f;
  b.wall({-S - T, 0, -D - T}, {S + T, H, -D}); b.wall({-S - T, 0, D}, {S + T, H, D + T}); b.wall({-S - T, 0, -D}, {-S, H, D}); b.wall({S, 0, -D}, {S + T, H, D});
  b.floorCeil(10, H, TEX_TILE, TEX_CONCRETE);
  b.solid({0, 0.42f, -5.05f}, {2.7f, 0.42f, 0.55f}, SURF_METAL);                       // button console
  for (int i = 0; i < 7; i++) b.solid({-5.4f + i * 1.8f, 0.1f, 5.1f}, {0.45f, 0.1f, 0.45f}, SURF_METAL);   // monster lineup plinths
  if (Mesh* p = b.props()) {
    const Vec3 O = b.O;
    P(p, 0x22262c); p->box(O + Vec3{0, 0.42f, -5.05f}, {2.7f, 0.42f, 0.55f});
    P(p, 0x3a4048); p->box(O + Vec3{0, 0.855f, -5.05f}, {2.72f, 0.015f, 0.57f});
    P(p, 0x66ccff, 0.8f); p->box(O + Vec3{0, 0.75f, -4.495f}, {2.7f, 0.012f, 0.004f});
    for (int r = 0; r < 4; r++) { P(p, r == 0 ? 0x44cc66 : r == 1 ? 0xcc4444 : r == 2 ? 0xffaa22 : 0x66ccff, 0.6f); p->box(O + Vec3{-2.62f, 0.872f, -4.62f - r * 0.2f}, {0.04f, 0.004f, 0.07f}); }
    for (int i = 0; i < 7; i++) { P(p, 0x2a2e34); p->box(O + Vec3{-5.4f + i * 1.8f, 0.1f, 5.1f}, {0.45f, 0.1f, 0.45f}); P(p, 0x66ccff, 0.7f); p->box(O + Vec3{-5.4f + i * 1.8f, 0.205f, 5.1f}, {0.46f, 0.006f, 0.46f}); }
    P(p, 0x15171a); for (int i = -3; i <= 3; i++) p->box(O + Vec3{i * 2.2f, 0.002f, 0.5f}, {0.9f, 0.002f, 0.9f});   // test spawn pads
    for (float x = -6; x <= 6.01f; x += 4) for (float z = -4; z <= 4.01f; z += 4) b.light({x, H, z});
  }
}

static void buildZone(int z, World* w, ZoneMeshes* m) {
  const ZoneInfo& Z = kZones[z]; ZB b{z, w, m, z == ZONE_BACKROOMS ? Vec3{} : Z.origin, uvScaleFor(Z.wallTex)};
  if (m) { m->walls.paint = Paint{}; m->trim.paint = Paint{z == ZONE_GARAGE ? rgb(0xc8a020) : z == ZONE_POOLROOMS ? rgb(0x8aa0a8) : rgb(0x6a4a28), 0, false, 0}; }
  switch (z) { case ZONE_LOBBY: buildLobby(b); break; case ZONE_BACKROOMS: buildBackrooms(b); break; case ZONE_POOLROOMS: buildPoolrooms(b); break; case ZONE_GARAGE: buildGarage(b); break; case ZONE_ADMIN: buildAdmin(b); break; default: buildLightsOut(b); break; }
}

void buildZoneColliders(World& w) { for (int z = 0; z < ZONE_COUNT; z++) buildZone(z, &w, nullptr); }
void buildZoneMeshes(std::vector<ZoneMeshes>& out) { out.assign(ZONE_COUNT, ZoneMeshes{}); for (int z = 0; z < ZONE_COUNT; z++) buildZone(z, nullptr, &out[z]); }

std::vector<Vec3> zoneSpawns(int z) {
  // candidates on a grid; the round manager keeps the ones that are not inside walls
  std::vector<Vec3> s; const ZoneInfo& Z = kZones[z]; float step = z == ZONE_LIGHTSOUT ? 4.f : 3.f, h = Z.half - 1.5f;
  Vec3 O = z == ZONE_BACKROOMS ? Vec3{} : Z.origin;
  float start = z == ZONE_LIGHTSOUT ? -Z.half + 2 : -h;
  for (float x = start; x <= h; x += step) for (float zz = start; zz <= h; zz += step) s.push_back(O + Vec3{x, 0, zz});
  return s;
}

}  // namespace dow
