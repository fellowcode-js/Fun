// Procedural models for DOW. Built once at startup from primitives: nothing is loaded from disk.
#include "models.h"
#include "map_data.h"
#include "layout.h"
#include <cmath>

namespace dow {

static void P(Mesh& m, uint32_t hex, float em = 0) { m.paint = Paint{rgb(hex), em, false, 0}; }
static void FUR(Mesh& m, float shade = 0.5f) { m.paint = Paint{{shade, shade, shade}, 0, true, 0}; }

// Per-vertex colour variation so fur and skin don't look like flat plastic.
static void mottle(Mesh& m, size_t from, float amt, float freq, uint32_t seed) {
  for (size_t i = from; i < m.v.size(); i++) {
    Vertex& x = m.v[i];
    float n = valueNoise(x.px * freq + x.pz * 0.7f * freq, x.py * freq, seed) - 0.5f, s = 1 + n * 2 * amt;
    x.r = (uint8_t)clampf(x.r * s, 0, 255); x.g = (uint8_t)clampf(x.g * s, 0, 255); x.b = (uint8_t)clampf(x.b * s, 0, 255);
  }
}

// --------------------------------------------------------------------------------------------- hands
// Right hand in grip space. Palm faces -X. `skin` colours the palm, `back` the back of the hand.
static void buildHand(AvatarKit& k, uint32_t skin, uint32_t back, bool furBack, float fingerLen, float fingerR, bool claws, uint32_t clawCol) {
  Mesh& pm = k.palm[1]; pm.clear();
  size_t s0 = pm.v.size();
  P(pm, skin); pm.roundBox({-0.004f, 0, -0.022f}, {0.024f, 0.048f, 0.046f}, 0.45f, {}, 8);   // palm pad
  if (furBack) FUR(pm, 0.46f); else P(pm, back);
  pm.roundBox({0.016f, 0.002f, -0.012f}, {0.022f, 0.05f, 0.05f}, 0.5f, {}, 8);               // back of hand / wrist
  pm.capsule({0.012f, 0, 0.03f}, {0.008f, 0, -0.01f}, 0.04f, 0.036f, 10, 3);                  // wrist
  P(pm, skin);
  for (int i = 0; i < 4; i++) pm.sphere({0.004f, k.fingerY[i], -0.058f}, 0.015f, 8, 5);         // knuckle pads
  mottle(pm, s0, 0.08f, 40, 3);
  // finger: two phalanges with a natural bend toward the palm (-X)
  Mesh& f = k.finger[1]; f.clear(); P(f, skin);
  Vec3 a{0, 0, 0}, b{-0.004f, 0, -fingerLen * 0.55f}, c{-0.016f, 0, -fingerLen};
  f.capsule(a, b, fingerR, fingerR * 0.92f, 8, 3); f.capsule(b, c, fingerR * 0.92f, fingerR * 0.8f, 8, 3);
  if (claws) { P(f, clawCol); f.cylinder(c + Vec3{0.002f, 0, 0.004f}, c + Vec3{-0.02f, 0, -0.03f}, fingerR * 0.75f, 0.001f, 8, true); }
  Mesh& t = k.thumb[1]; t.clear(); P(t, skin);
  t.capsule({0, 0, 0}, {-0.018f, 0.022f, -0.03f}, fingerR * 1.05f, fingerR, 8, 3);
  t.capsule({-0.018f, 0.022f, -0.03f}, {-0.03f, 0.028f, -0.055f}, fingerR, fingerR * 0.85f, 8, 3);
  if (claws) { P(t, clawCol); t.cylinder({-0.03f, 0.028f, -0.055f}, {-0.04f, 0.03f, -0.08f}, fingerR * 0.7f, 0.001f, 8, true); }
  for (int i = 0; i < 2; i++) {}
  k.palm[0] = k.palm[1]; k.palm[0].flipX();
  k.finger[0] = k.finger[1]; k.finger[0].flipX();
  k.thumb[0] = k.thumb[1]; k.thumb[0].flipX();
}

// --------------------------------------------------------------------------------------------- gorilla
static void gorillaHead(Mesh& h, uint32_t skin, bool monster) {
  size_t s0 = h.v.size();
  FUR(h, 0.52f); h.ellipsoid({0, 0.012f, 0.012f}, {0.152f, 0.158f, 0.15f}, {}, 22, 14);              // cranium
  h.ellipsoid({0, 0.115f, 0.04f}, {0.055f, 0.07f, 0.11f}, {}, 12, 8);                                  // crest
  h.ellipsoid({0, -0.07f, 0.03f}, {0.13f, 0.09f, 0.12f}, {}, 16, 9);                                   // jowls
  h.displace(s0, 0.006f, 18, 11); mottle(h, s0, 0.1f, 14, 5);
  size_t s1 = h.v.size();
  P(h, skin); h.ellipsoid({0, -0.005f, -0.112f}, {0.118f, 0.112f, 0.06f}, {}, 18, 10);                // face mask
  P(h, 0x2a221f); h.capsule({-0.085f, 0.047f, -0.142f}, {0.085f, 0.047f, -0.142f}, 0.03f, 0.03f, 10, 3); // brow ridge
  P(h, skin); h.ellipsoid({0, -0.062f, -0.148f}, {0.088f, 0.062f, 0.064f}, {}, 16, 9);                // muzzle
  mottle(h, s1, 0.07f, 30, 9);
  P(h, 0x0c0908); h.sphere({-0.024f, -0.042f, -0.206f}, 0.013f, 8, 5); h.sphere({0.024f, -0.042f, -0.206f}, 0.013f, 8, 5);  // nostrils
  P(h, 0x140e0c); h.capsule({-0.05f, -0.098f, -0.19f}, {0.05f, -0.098f, -0.19f}, 0.008f, 0.008f, 6, 2);      // mouth line
  P(h, skin); h.sphere({-0.148f, 0.0f, 0.0f}, 0.032f, 10, 6); h.sphere({0.148f, 0.0f, 0.0f}, 0.032f, 10, 6);     // ears
  for (int s = -1; s <= 1; s += 2) {
    if (monster) { P(h, 0xff2a14, 1.0f); h.sphere({0.046f * s, 0.014f, -0.157f}, 0.021f, 10, 6); P(h, 0xffee66, 1.0f); h.sphere({0.046f * s, 0.016f, -0.175f}, 0.008f, 6, 4); }
    else {
      P(h, 0xece6da); h.sphere({0.046f * s, 0.014f, -0.157f}, 0.022f, 10, 7);
      P(h, 0x3a2412); h.sphere({0.046f * s, 0.014f, -0.172f}, 0.0125f, 8, 5);
      P(h, 0x050303); h.sphere({0.046f * s, 0.014f, -0.178f}, 0.007f, 6, 4);
      P(h, 0xffffff, 1.0f); h.sphere({0.046f * s + 0.004f, 0.019f, -0.183f}, 0.0028f, 4, 3);
    }
  }
}

static void gorillaTorso(Mesh& t, uint32_t belly) {
  size_t s0 = t.v.size();
  FUR(t, 0.5f);
  t.ellipsoid({0, 0.05f, 0}, {0.215f, 0.235f, 0.17f}, {}, 22, 14);                       // chest
  t.ellipsoid({-0.14f, 0.17f, 0.015f}, {0.115f, 0.095f, 0.115f}, {}, 14, 8);             // shoulders / traps
  t.ellipsoid({0.14f, 0.17f, 0.015f}, {0.115f, 0.095f, 0.115f}, {}, 14, 8);
  t.ellipsoid({0, 0.23f, 0.05f}, {0.1f, 0.08f, 0.09f}, {}, 12, 8);                        // neck hump
  t.ellipsoid({0, -0.14f, 0.02f}, {0.17f, 0.12f, 0.14f}, {}, 16, 9);                      // hips
  t.capsule({-0.1f, -0.2f, 0.0f}, {-0.12f, -0.36f, -0.03f}, 0.075f, 0.065f, 12, 3);      // stubby legs
  t.capsule({0.1f, -0.2f, 0.0f}, {0.12f, -0.36f, -0.03f}, 0.075f, 0.065f, 12, 3);
  t.displace(s0, 0.008f, 14, 21); mottle(t, s0, 0.1f, 12, 7);
  size_t s1 = t.v.size();
  P(t, belly); t.ellipsoid({0, -0.02f, -0.125f}, {0.145f, 0.17f, 0.065f}, {}, 16, 10);   // bare chest / belly
  t.ellipsoid({-0.06f, 0.1f, -0.15f}, {0.07f, 0.045f, 0.03f}, {}, 10, 6); t.ellipsoid({0.06f, 0.1f, -0.15f}, {0.07f, 0.045f, 0.03f}, {}, 10, 6);  // pecs
  P(t, 0x2a221f); t.ellipsoid({-0.125f, -0.405f, -0.06f}, {0.055f, 0.03f, 0.08f}, {}, 10, 6); t.ellipsoid({0.125f, -0.405f, -0.06f}, {0.055f, 0.03f, 0.08f}, {}, 10, 6);  // feet
  mottle(t, s1, 0.06f, 25, 13);
}

static void furArm(Mesh& m, float len, float r0, float r1, uint32_t seed) {
  size_t s0 = m.v.size(); FUR(m, 0.5f); m.capsule({0, 0, 0}, {0, len, 0}, r0, r1, 14, 4);
  m.ellipsoid({0, len * 0.45f, 0}, {r0 * 1.12f, len * 0.33f, r0 * 1.1f}, {}, 12, 8);   // muscle bulge
  m.displace(s0, 0.006f, 20, seed); mottle(m, s0, 0.1f, 16, seed);
}

static AvatarKit gorilla() {
  AvatarKit k; k.handScale = 1.3f;
  gorillaHead(k.head, 0x3b312c, false);
  gorillaTorso(k.torso, 0x4c3f37);
  furArm(k.upperArm, k.upperLen, 0.062f, 0.054f, 31); furArm(k.foreArm, k.foreLen, 0.058f, 0.045f, 37);
  buildHand(k, 0x2e2622, 0x2e2622, true, 0.06f, 0.0135f, false, 0);
  return k;
}

static AvatarKit monster() {
  AvatarKit k; k.upperLen = 0.45f; k.foreLen = 0.45f; k.handScale = 1.4f;
  Mesh& h = k.head;
  gorillaHead(h, 0x2a1414, true);
  P(h, 0x1a0404); h.ellipsoid({0, -0.1f, -0.15f}, {0.09f, 0.05f, 0.05f}, {}, 12, 6);              // gaping mouth
  P(h, 0xe8dcc0);
  for (int i = 0; i < 7; i++) {                                                                    // fangs
    float x = -0.066f + i * 0.022f, l = (i == 1 || i == 5) ? 0.05f : 0.026f;
    h.cylinder({x, -0.075f, -0.186f}, {x * 0.96f, -0.075f - l, -0.19f}, 0.008f, 0.0005f, 6, true);
    h.cylinder({x + 0.011f, -0.13f, -0.18f}, {x + 0.011f, -0.13f + l * 0.7f, -0.186f}, 0.007f, 0.0005f, 6, true);
  }
  P(h, 0xcfc1a0);
  for (int s = -1; s <= 1; s += 2) {                                                               // curled horns
    std::vector<Vec3> pts; std::vector<float> rr;
    for (int i = 0; i <= 10; i++) { float t = i / 10.f; pts.push_back({s * (0.09f + 0.12f * t), 0.1f + 0.14f * std::sin(t * 2.2f), 0.02f + 0.1f * t - 0.16f * t * t}); rr.push_back(0.032f * (1 - t) + 0.003f); }
    h.tube(pts, rr, 10, true);
  }
  Mesh& t = k.torso; gorillaTorso(t, 0x3a1c1a);
  P(t, 0x8a7a6a);
  for (int i = 0; i < 6; i++) { float y = 0.24f - i * 0.075f; t.cylinder({0, y, 0.14f}, {0, y + 0.03f, 0.25f - i * 0.01f}, 0.03f, 0.001f, 8, true); }  // back spikes
  furArm(k.upperArm, k.upperLen, 0.085f, 0.07f, 41); furArm(k.foreArm, k.foreLen, 0.08f, 0.06f, 43);
  buildHand(k, 0x241414, 0x241414, true, 0.066f, 0.0155f, true, 0xd9cfb8);
  return k;
}

static AvatarKit robot() {
  AvatarKit k; k.upperLen = 0.44f; k.foreLen = 0.44f; k.handScale = 1.25f;
  Mesh& h = k.head;
  P(h, 0x8e949c); h.roundBox({0, 0.0f, 0}, {0.13f, 0.12f, 0.13f}, 0.28f, {}, 10);
  P(h, 0x1a1d22); h.roundBox({0, 0.015f, -0.1f}, {0.105f, 0.045f, 0.045f}, 0.25f, {}, 8);
  P(h, 0x22ffee, 1.0f); h.roundBox({0, 0.015f, -0.142f}, {0.09f, 0.022f, 0.006f}, 0.2f, {}, 6);   // visor
  P(h, 0x5a6068); h.cylinder({-0.14f, 0, 0}, {0.14f, 0, 0}, 0.04f, 0.04f, 14, true);               // ear bolts
  h.cylinder({0.06f, 0.11f, 0.03f}, {0.07f, 0.24f, 0.05f}, 0.008f, 0.006f, 6, true);
  P(h, 0xff3322, 1.0f); h.sphere({0.07f, 0.25f, 0.05f}, 0.018f, 8, 5);                              // antenna light
  P(h, 0x3a3e44); for (int i = 0; i < 4; i++) h.box({-0.045f + i * 0.03f, -0.075f, -0.128f}, {0.009f, 0.012f, 0.004f});  // grille
  Mesh& t = k.torso;
  P(t, 0x9aa0a8); t.roundBox({0, 0.04f, 0}, {0.21f, 0.22f, 0.16f}, 0.3f, {}, 12);
  P(t, 0x6a7078); t.roundBox({-0.2f, 0.16f, 0.0f}, {0.1f, 0.07f, 0.11f}, 0.3f, {}, 8); t.roundBox({0.2f, 0.16f, 0.0f}, {0.1f, 0.07f, 0.11f}, 0.3f, {}, 8);
  P(t, 0x2a2e34); t.roundBox({0, 0.04f, -0.155f}, {0.12f, 0.12f, 0.012f}, 0.2f, {}, 6);
  P(t, 0x22ffee, 0.9f); for (int i = 0; i < 3; i++) t.box({0, 0.1f - i * 0.05f, -0.168f}, {0.09f - i * 0.015f, 0.008f, 0.003f});
  P(t, 0x5a6068); t.cylinder({0, -0.18f, 0}, {0, -0.1f, 0}, 0.12f, 0.15f, 16, true);
  P(t, 0x7a8088); t.capsule({-0.1f, -0.2f, 0}, {-0.11f, -0.36f, -0.02f}, 0.06f, 0.055f, 10, 3); t.capsule({0.1f, -0.2f, 0}, {0.11f, -0.36f, -0.02f}, 0.06f, 0.055f, 10, 3);
  P(t, 0x3a3e44); t.roundBox({-0.115f, -0.405f, -0.05f}, {0.05f, 0.025f, 0.08f}, 0.3f, {}, 6); t.roundBox({0.115f, -0.405f, -0.05f}, {0.05f, 0.025f, 0.08f}, 0.3f, {}, 6);
  P(k.upperArm, 0x8e949c); k.upperArm.cylinder({0, 0.02f, 0}, {0, k.upperLen, 0}, 0.05f, 0.045f, 12, true); P(k.upperArm, 0x4a5058); k.upperArm.sphere({0, 0, 0}, 0.065f, 12, 8);
  P(k.foreArm, 0x9aa0a8); k.foreArm.cylinder({0, 0.02f, 0}, {0, k.foreLen, 0}, 0.045f, 0.04f, 12, true); P(k.foreArm, 0x4a5058); k.foreArm.sphere({0, 0, 0}, 0.055f, 12, 8);
  P(k.foreArm, 0xffaa22, 0.6f); k.foreArm.torus({0, k.foreLen * 0.6f, 0}, 0.046f, 0.006f, {}, 16, 6);
  buildHand(k, 0x5a6068, 0x8e949c, false, 0.058f, 0.013f, false, 0);
  return k;
}

static AvatarKit stalker() {
  AvatarKit k; k.upperLen = 0.5f; k.foreLen = 0.5f; k.handScale = 1.3f;
  Mesh& h = k.head; size_t s0 = 0;
  P(h, 0x9aa39a); h.ellipsoid({0, 0.05f, 0.01f}, {0.118f, 0.2f, 0.13f}, {}, 20, 14);              // long skull
  h.ellipsoid({0, -0.09f, -0.06f}, {0.075f, 0.07f, 0.075f}, {}, 14, 8);                            // narrow jaw
  mottle(h, s0, 0.12f, 20, 51);
  P(h, 0x030504);
  for (int s = -1; s <= 1; s += 2) {
    h.ellipsoid({0.045f * s, 0.035f, -0.108f}, {0.034f, 0.046f, 0.03f}, Quat::axisAngle({0, 0, 1}, 0.35f * s), 10, 7);  // hollow sockets
  }
  P(h, 0x66ff55, 1.0f); h.sphere({-0.045f, 0.03f, -0.13f}, 0.006f, 6, 4); h.sphere({0.045f, 0.03f, -0.13f}, 0.006f, 6, 4);  // pinpoint eyes
  P(h, 0x4a524a); h.capsule({-0.035f, -0.11f, -0.128f}, {0.035f, -0.11f, -0.128f}, 0.004f, 0.004f, 6, 2);           // sewn mouth
  for (int i = 0; i < 5; i++) { float x = -0.028f + i * 0.014f; h.capsule({x, -0.098f, -0.13f}, {x, -0.122f, -0.128f}, 0.0025f, 0.0025f, 4, 2); }
  P(h, 0x44ff66, 0.8f); for (int i = 0; i < 4; i++) h.sphere({-0.05f + i * 0.035f, 0.19f, 0.08f - i * 0.01f}, 0.016f, 8, 5);   // spore nodes
  Mesh& t = k.torso;
  P(t, 0x8c968c); t.ellipsoid({0, 0.06f, 0}, {0.15f, 0.22f, 0.1f}, {}, 18, 12);
  P(t, 0x7a837a); for (int i = 0; i < 5; i++) t.torus({0, 0.14f - i * 0.05f, -0.01f}, 0.135f - i * 0.006f, 0.008f, {}, 18, 5);  // ribs
  P(t, 0x8c968c); t.ellipsoid({0, -0.14f, 0}, {0.1f, 0.09f, 0.08f}, {}, 12, 8);
  t.capsule({-0.06f, -0.2f, 0}, {-0.07f, -0.4f, -0.02f}, 0.04f, 0.035f, 10, 3); t.capsule({0.06f, -0.2f, 0}, {0.07f, -0.4f, -0.02f}, 0.04f, 0.035f, 10, 3);
  P(t, 0x44ff66, 0.9f); for (int i = 0; i < 6; i++) t.sphere({(i % 2 ? 0.05f : -0.05f), 0.2f - i * 0.06f, 0.095f}, 0.022f, 8, 5);   // spore sacs on the back
  P(k.upperArm, 0x8c968c); k.upperArm.capsule({0, 0, 0}, {0, k.upperLen, 0}, 0.04f, 0.032f, 10, 3);
  P(k.foreArm, 0x8c968c); k.foreArm.capsule({0, 0, 0}, {0, k.foreLen, 0}, 0.034f, 0.026f, 10, 3);
  buildHand(k, 0x7a837a, 0x8c968c, false, 0.09f, 0.01f, true, 0x1a1a14);
  return k;
}

AvatarKit buildAvatar(int form) {
  switch (form) { case KIT_MONSTER: return monster(); case KIT_ROBOT: return robot(); case KIT_STALKER: return stalker(); default: return gorilla(); }
}

// --------------------------------------------------------------------------------------------- props
static void woodBox(Mesh& m, const Vec3& c, const Vec3& h, uint32_t col) { P(m, col); size_t s = m.v.size(); m.box(c, h); mottle(m, s, 0.08f, 22, 3); }

PropKit buildProps() {
  PropKit k;
  // ceiling light: aluminium frame + glowing diffuser (diffuser drawn separately so it can flicker)
  P(k.lightPanel, 0xd8d6cc); k.lightPanel.box({0, -0.012f, 0}, {0.31f, 0.012f, 0.31f});
  P(k.lightPanel, 0xb8b6ac); k.lightPanel.box({0, -0.026f, 0.3f}, {0.31f, 0.006f, 0.012f}); k.lightPanel.box({0, -0.026f, -0.3f}, {0.31f, 0.006f, 0.012f});
  k.lightPanel.box({0.3f, -0.026f, 0}, {0.012f, 0.006f, 0.31f}); k.lightPanel.box({-0.3f, -0.026f, 0}, {0.012f, 0.006f, 0.31f});
  P(k.lightDiffuser, 0xfff6d0, 1.0f); k.lightDiffuser.box({0, -0.026f, 0}, {0.29f, 0.004f, 0.29f});
  P(k.lightDiffuser, 0xfffbe8, 1.0f); k.lightDiffuser.box({0, -0.031f, 0}, {0.27f, 0.002f, 0.04f});

  // lobby table (top at 0.9 m)
  woodBox(k.table, {0, 0.875f, 0}, {0.86f, 0.025f, 0.38f}, 0x7a5432);
  woodBox(k.table, {0, 0.8f, 0}, {0.8f, 0.05f, 0.33f}, 0x5e3e22);
  for (int sx = -1; sx <= 1; sx += 2) for (int sz = -1; sz <= 1; sz += 2) woodBox(k.table, {sx * 0.76f, 0.39f, sz * 0.3f}, {0.035f, 0.39f, 0.035f}, 0x5a3a20);
  // stool
  P(k.stool, 0x8a2a22); k.stool.cylinder({0, 0.44f, 0}, {0, 0.47f, 0}, 0.2f, 0.19f, 18, true);
  P(k.stool, 0x6a6a70); for (int i = 0; i < 3; i++) { float a = i * 2 * PI / 3; k.stool.cylinder({0.15f * std::cos(a), 0, 0.15f * std::sin(a)}, {0.06f * std::cos(a), 0.44f, 0.06f * std::sin(a)}, 0.014f, 0.014f, 6, true); }
  k.stool.torus({0, 0.18f, 0}, 0.11f, 0.008f, {}, 16, 5);
  // form pillar: hazard-striped metal post (top at 0.96)
  P(k.pillar, 0x2a2a30); k.pillar.box({0, 0.48f, 0}, {0.25f, 0.48f, 0.25f});
  for (int i = 0; i < 4; i++) { P(k.pillar, i % 2 ? 0x111111 : 0xe8b820); k.pillar.box({0, 0.08f + i * 0.04f, 0}, {0.252f, 0.02f, 0.252f}); }
  P(k.pillar, 0x3a3a42); k.pillar.box({0, 0.955f, 0}, {0.26f, 0.012f, 0.26f});
  // stalker pedestal: stacked stone with a glowing lock ring
  P(k.pedestal, 0x4a4652); { size_t s = k.pedestal.v.size(); k.pedestal.box({0, 0.1f, 0}, {0.34f, 0.1f, 0.34f}); k.pedestal.box({0, 0.55f, 0}, {0.27f, 0.36f, 0.27f}); k.pedestal.box({0, 0.935f, 0}, {0.31f, 0.025f, 0.31f}); mottle(k.pedestal, s, 0.15f, 9, 5); }
  P(k.pedestalRing, 0xffffff, 1.0f); k.pedestalRing.torus({0, 0.5f, 0}, 0.28f, 0.012f, {}, 28, 6); k.pedestalRing.torus({0, 0.25f, 0}, 0.28f, 0.012f, {}, 28, 6);
  woodBox(k.plinth, {0, 0.08f, 0}, {0.28f, 0.08f, 0.4f}, 0x3a2a1a);
  // chainsaw rack: pegboard with hooks (board faces +Z)
  P(k.rack, 0x8a6a42); { size_t s = k.rack.v.size(); k.rack.box({0, 0.9f, 0}, {0.7f, 0.9f, 0.05f}); mottle(k.rack, s, 0.06f, 15, 9); }
  P(k.rack, 0x3a2a18); for (int x = 0; x < 13; x++) for (int y = 0; y < 16; y++) k.rack.disc({-0.6f + x * 0.1f, 0.15f + y * 0.1f, 0.0505f}, 0.008f, Quat::axisAngle({1, 0, 0}, PI / 2), 6);
  P(k.rack, 0x9a9aa2); for (int i = 0; i < 3; i++) { float x = -0.3f + i * 0.3f; k.rack.cylinder({x, 1.25f, 0.05f}, {x, 1.25f, 0.14f}, 0.008f, 0.008f, 6, true); k.rack.cylinder({x, 1.25f, 0.14f}, {x, 1.3f, 0.15f}, 0.008f, 0.008f, 6, true); }
  P(k.rack, 0xff3322, 0.6f); k.rack.box({0, 1.45f, 0.052f}, {0.5f, 0.05f, 0.002f});
  // Mushroom OS: metal desk + giant mushroom computer with a monitor on its stem (faces +X)
  P(k.osDesk, 0x3a3a44); k.osDesk.box({0, 0.53f, 0}, {0.45f, 0.02f, 0.8f});
  P(k.osDesk, 0x2a2a30); k.osDesk.box({0, 0.255f, 0}, {0.42f, 0.255f, 0.76f});
  P(k.osDesk, 0x15151a); k.osDesk.box({0.36f, 0.56f, 0}, {0.07f, 0.012f, 0.32f});
  P(k.osDesk, 0x55557a, 0.25f); for (int x = 0; x < 3; x++) for (int z = 0; z < 12; z++) k.osDesk.box({0.32f + x * 0.04f, 0.575f, -0.27f + z * 0.05f}, {0.015f, 0.006f, 0.018f});
  { Mesh& m = k.osMushroom; P(m, 0xe8dcc0); size_t s = m.v.size();
    m.lathe({{0.0f, 0.55f}, {0.14f, 0.55f}, {0.11f, 1.0f}, {0.12f, 1.7f}, {0.16f, 2.05f}, {0.0f, 2.06f}}, {-0.1f, 0, 0}, {}, 18); mottle(m, s, 0.08f, 10, 2);
    P(m, 0xc8241c); s = m.v.size();
    m.lathe({{0.0f, 2.62f}, {0.3f, 2.58f}, {0.55f, 2.44f}, {0.7f, 2.25f}, {0.72f, 2.12f}, {0.6f, 2.08f}, {0.0f, 2.1f}}, {-0.1f, 0, 0}, {}, 28); mottle(m, s, 0.1f, 6, 4);
    P(m, 0xf4efe4); Rng r(9);
    for (int i = 0; i < 16; i++) { float a = r.range(0, 2 * PI), t = r.range(0.15f, 0.85f); float rad = 0.7f * t; float y = 2.62f - 0.5f * t * t - 0.02f;
      Vec3 c{-0.1f + rad * std::cos(a), y, rad * std::sin(a)}; Vec3 n = normalize(Vec3{rad * std::cos(a), 0.35f, rad * std::sin(a)});
      m.ellipsoid(c, {0.07f, 0.02f, 0.07f}, fromTo({0, 1, 0}, n), 10, 5); }
    P(m, 0xb8a888); for (int i = 0; i < 24; i++) { float a = i * 2 * PI / 24; m.box({-0.1f + 0.45f * std::cos(a), 2.09f, 0.45f * std::sin(a)}, {0.01f, 0.02f, 0.06f}, Quat::yaw(-a)); }
  }
  P(k.osMonitorFrame, 0x1c1c22); k.osMonitorFrame.roundBox({0.09f, 0.98f, 0}, {0.05f, 0.31f, 0.56f}, 0.2f, {}, 8);
  P(k.osMonitorFrame, 0x050508); k.osMonitorFrame.box({0.141f, 0.98f, 0}, {0.002f, 0.28f, 0.52f});
  // mod vent (doorway grille at x = -7, z -0.7..0.7, 2.1 high), modelled in its own frame facing +X
  P(k.vent, 0x6a6e72); k.vent.box({0, 1.05f, -0.68f}, {0.16f, 1.05f, 0.03f}); k.vent.box({0, 1.05f, 0.68f}, {0.16f, 1.05f, 0.03f}); k.vent.box({0, 2.07f, 0}, {0.16f, 0.03f, 0.7f});
  P(k.vent, 0x8a8e92); for (int i = 0; i < 13; i++) k.vent.box({0, 0.1f + i * 0.155f, 0}, {0.01f, 0.012f, 0.66f}, Quat::axisAngle({0, 0, 1}, 0.6f));
  P(k.vent, 0x9a2a2a, 0.5f); k.vent.box({0.165f, 2.07f, 0}, {0.004f, 0.02f, 0.5f});
  // test pads
  for (int i = 0; i < 2; i++) {
    Mesh& m = i ? k.padB : k.padA;
    P(m, 0x2a2a30); m.cylinder({0, 0, 0}, {0, 0.03f, 0}, 0.62f, 0.6f, 32, true);
    P(m, i ? 0x3399ff : 0xff8833, 0.9f); m.torus({0, 0.032f, 0}, 0.52f, 0.018f, {}, 40, 6); m.torus({0, 0.032f, 0}, 0.3f, 0.01f, {}, 30, 5);
    P(m, 0x15151a); m.cylinder({0, 0.03f, 0}, {0, 0.034f, 0}, 0.25f, 0.25f, 24, true);
  }
  // spore pod (hangs from the ceiling)
  { Mesh& m = k.sporePod; P(m, 0x2a3a22); size_t s = m.v.size(); m.ellipsoid({0, -0.18f, 0}, {0.16f, 0.22f, 0.16f}, {}, 16, 10); m.displace(s, 0.02f, 10, 3); mottle(m, s, 0.2f, 12, 3);
    P(m, 0x66ff55, 1.0f); Rng r(5); for (int i = 0; i < 14; i++) { float a = r.range(0, 2 * PI), y = r.range(-0.34f, -0.06f); float rad = 0.16f * std::sqrt(std::max(0.f, 1 - std::pow((y + 0.18f) / 0.22f, 2.f))); m.sphere({rad * std::cos(a), y, rad * std::sin(a)}, 0.018f, 6, 4); }
    P(m, 0x1a2a14); m.cylinder({0, 0.0f, 0}, {0, 0.04f, 0}, 0.04f, 0.06f, 8, true); }
  { Mesh& m = k.mushroomCluster; Rng r(17);
    for (int i = 0; i < 7; i++) { float a = r.range(0, 2 * PI), d = r.range(0, 0.25f), h = r.range(0.08f, 0.26f), cr = h * 0.6f; Vec3 b{d * std::cos(a), 0, d * std::sin(a)};
      P(m, 0xe8dcc0); m.cylinder(b, b + Vec3{0, h, 0}, cr * 0.25f, cr * 0.2f, 8, true);
      P(m, i % 2 ? 0xb83a2a : 0x8a4ad8, i % 2 ? 0.f : 0.6f); m.lathe({{0, h + cr * 0.5f}, {cr * 0.6f, h + cr * 0.4f}, {cr, h}, {0.0f, h - 0.005f}}, b, {}, 12); } }
  // buttons
  P(k.buttonBase, 0x1a1a20); k.buttonBase.box({0, 0.01f, 0}, {1, 0.01f, 1});
  P(k.buttonCap, 0xffffff, 0.15f); k.buttonCap.roundBox({0, 0.0f, 0}, {1, 1, 1}, 0.3f, {}, 8);
  P(k.keypadPlate, 0x2a2a30); k.keypadPlate.box({0, 0, 0}, {0.01f, 0.27f, 0.2f});
  P(k.keypadPlate, 0x101014); k.keypadPlate.box({0.011f, 0.31f, 0}, {0.002f, 0.045f, 0.19f});
  P(k.keyCap, 0xd8d8dc, 0.1f); k.keyCap.roundBox({0, 0, 0}, {0.012f, 0.04f, 0.04f}, 0.35f, {}, 6);
  P(k.signBack, 0x000000); k.signBack.box({0, 0, 0}, {0.5f, 0.5f, 0.008f});
  // toys + gore pieces
  P(k.cube, 0xffffff); k.cube.roundBox({0, 0, 0}, {1, 1, 1}, 0.12f, {}, 8);
  P(k.dropGeo, 0x7a0606); k.dropGeo.sphere({0, 0, 0}, 1, 6, 4);
  P(k.decalQuad, 0xffffff); k.decalQuad.quadXY({0, 0, 0}, 2, 2, Quat::axisAngle({1, 0, 0}, -PI / 2));
  { Mesh& m = k.gibChunk; P(m, 0x8a1010); size_t s = m.v.size(); m.ellipsoid({0, 0, 0}, {0.035f, 0.028f, 0.03f}, {}, 10, 6); m.displace(s, 0.008f, 60, 7); mottle(m, s, 0.25f, 80, 7);
    P(m, 0xd8c8a8); m.sphere({0.02f, 0.012f, 0}, 0.01f, 6, 4); }
  { Mesh& m = k.gibBone; P(m, 0xe8e0cc); m.capsule({0, -0.05f, 0}, {0, 0.05f, 0}, 0.012f, 0.012f, 8, 3); m.sphere({0.008f, -0.06f, 0}, 0.018f, 8, 5); m.sphere({-0.008f, -0.06f, 0}, 0.018f, 8, 5);
    P(m, 0x8a1010); m.ellipsoid({0, 0.05f, 0}, {0.022f, 0.02f, 0.022f}, {}, 8, 5); }
  return k;
}

// --------------------------------------------------------------------------------------------- level
LevelMeshes buildLevelMeshes() {
  LevelMeshes L;
  for (int i = 0; i < kNumWalls; i++) {
    const WallDef& w = kWalls[i]; if (w.flag == 1) continue;
    Vec3 mn{w.mn[0], w.mn[1], w.mn[2]}, mx{w.mx[0], w.mx[1], w.mx[2]};
    P(L.walls, 0xffffff); L.walls.box((mn + mx) * 0.5f, (mx - mn) * 0.5f, {}, 0.4f);
    // baseboard + a thin dado rail
    Vec3 c = (mn + mx) * 0.5f, h = (mx - mn) * 0.5f + Vec3{0.014f, 0, 0.014f};
    P(L.trim, 0x6a4a28); L.trim.box({c.x, 0.06f, c.z}, {h.x, 0.06f, h.z});
    P(L.trim, 0x7a5a30); L.trim.box({c.x, 3.17f, c.z}, {h.x, 0.03f, h.z});
  }
  // floor and ceiling tiles (UVs in metres, textures repeat)
  P(L.floor, 0xffffff); { Mesh& m = L.floor; uint32_t a = m.vert({-31, 0, -31}, {0, 1, 0}, -31 * 0.5f, -31 * 0.5f), b = m.vert({31, 0, -31}, {0, 1, 0}, 31 * 0.5f, -31 * 0.5f), c = m.vert({31, 0, 31}, {0, 1, 0}, 31 * 0.5f, 31 * 0.5f), d = m.vert({-31, 0, 31}, {0, 1, 0}, -31 * 0.5f, 31 * 0.5f); m.tri(a, c, b); m.tri(a, d, c); }
  P(L.ceiling, 0xffffff); { Mesh& m = L.ceiling; float y = kRoomH, s = 1 / 1.2f; uint32_t a = m.vert({-31, y, -31}, {0, -1, 0}, -31 * s, -31 * s), b = m.vert({31, y, -31}, {0, -1, 0}, 31 * s, -31 * s), c = m.vert({31, y, 31}, {0, -1, 0}, 31 * s, 31 * s), d = m.vert({-31, y, 31}, {0, -1, 0}, -31 * s, 31 * s); m.tri(a, b, c); m.tri(a, c, d); }
  return L;
}

}  // namespace dow
