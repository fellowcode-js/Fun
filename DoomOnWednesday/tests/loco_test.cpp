// Headless locomotion tests: scripted controller motion, check the body really moves the way a player expects.
#include "../src/game/locomotion.h"
#include "../src/game/layout.h"
#include <cstdio>
#include <cmath>
#include <algorithm>
using namespace dow;

static int fails = 0;  // locomotion
#define CHECK(c, ...) do { if (!(c)) { fails++; std::printf("FAIL: "); std::printf(__VA_ARGS__); std::printf("\n"); } else { std::printf("ok:   "); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

struct Rig { World w; Locomotion L; Pose head, hands[2]; };
static void init(Rig& r, Vec3 spawn) {
  r.w.buildLevel(); r.L.reset(spawn); r.head.p = {0, 1.6f, 0}; r.head.valid = true;
  r.hands[0].p = {-0.25f, 0.85f, -0.15f}; r.hands[1].p = {0.25f, 0.85f, -0.15f}; r.hands[0].valid = r.hands[1].valid = true;
}
static float gPeak = 0;
static void run(Rig& r, float secs, void (*f)(Rig&, float)) { const float dt = 1 / 72.f; gPeak = -1e9f; for (float t = 0; t < secs; t += dt) { if (f) f(r, t); r.L.step(dt, r.head, r.hands, r.w, 0); gPeak = std::max(gPeak, r.L.headW.y); } }

int locoTests() {
  { Rig r; init(r, kSpawn); run(r, 2.0f, nullptr);
    float headY = r.L.headW.y; CHECK(r.L.hand[0].contact && r.L.hand[1].contact, "idle: both hands rest on the floor");
    CHECK(headY > 0.7f && headY < 1.0f, "idle: settles at gorilla height (head %.2f m)", headY);
    Vec3 p0 = r.L.rig; run(r, 1.0f, nullptr); CHECK(length(r.L.rig - p0) < 0.01f, "idle: no drift (%.4f m)", length(r.L.rig - p0)); }
  { Rig r; init(r, kSpawn); run(r, 1.5f, nullptr); Vec3 p0 = r.L.headW;
    // knuckle-walk: each hand plants forward low, drags back, lifts and returns (alternating)
    run(r, 4.0f, [](Rig& r, float t) { for (int h = 0; h < 2; h++) { float ph = std::fmod(t * 1.6f + h * 0.5f, 1.f), x = h ? 0.28f : -0.28f;
      if (ph < 0.5f) { float k = ph / 0.5f; r.hands[h].p = {x, 0.70f, -0.45f + 0.75f * k}; } else { float k = (ph - 0.5f) / 0.5f; r.hands[h].p = {x, 0.70f + 0.25f * std::sin(k * PI), 0.30f - 0.75f * k}; } } });
    float dz = p0.z - r.L.headW.z; CHECK(dz > 2.0f, "walk: arm swings move you forward (%.2f m in 4 s)", dz);
    CHECK(std::fabs(r.L.headW.x - p0.x) < 0.6f, "walk: goes straight (drift %.2f m)", r.L.headW.x - p0.x); }
  { Rig r; init(r, kSpawn); run(r, 1.5f, nullptr); float y0 = r.L.headW.y, peak = y0;
    // jump: shove both hands down hard then fling them up
    const float dt = 1 / 72.f; float t = 0;
    for (; t < 0.18f; t += dt) { for (int h = 0; h < 2; h++) r.hands[h].p.y -= 2.6f * dt; r.L.step(dt, r.head, r.hands, r.w, 0); }
    for (; t < 0.30f; t += dt) { for (int h = 0; h < 2; h++) r.hands[h].p.y += 4.0f * dt; r.L.step(dt, r.head, r.hands, r.w, 0); }
    for (; t < 1.6f; t += dt) { r.L.step(dt, r.head, r.hands, r.w, 0); peak = std::max(peak, r.L.headW.y); }
    CHECK(peak - y0 > 0.25f, "jump: push-and-release launches you (%.2f m up)", peak - y0);
    CHECK(r.L.hand[0].contact || r.L.headW.y < y0 + 0.2f, "jump: lands again"); }
  { Rig r; init(r, {-4.5f, 0, -6.45f}); run(r, 1.5f, nullptr);   // face the lobby's north wall (z = -6.85)
    float y0 = r.L.headW.y;
    run(r, 5.0f, [](Rig& r, float t) { for (int h = 0; h < 2; h++) { float ph = std::fmod(t * 1.2f + h * 0.5f, 1.f), x = h ? 0.22f : -0.22f;
      if (ph < 0.5f) { float k = ph / 0.5f; r.hands[h].p = {x, 2.0f - 0.8f * k, -0.62f}; } else { float k = (ph - 0.5f) / 0.5f; r.hands[h].p = {x, 1.2f + 0.8f * k, -0.62f + 0.3f * std::sin(k * PI)}; }
      float e = std::min(1.f, t / 0.8f); Vec3 rest{h ? 0.25f : -0.25f, 0.85f, -0.15f}; r.hands[h].p = lerp(rest, r.hands[h].p, e); } });
    float best = gPeak; CHECK(best - y0 > 0.25f, "climb: pulling down the wall lifts you (%.2f m per stroke)", best - y0); }
  { Rig r; init(r, kSpawn); run(r, 1.5f, nullptr);
    run(r, 3.0f, [](Rig& r, float t) { r.hands[1].p = {0.25f + 3.0f * t, 0.85f, -0.15f}; });  // controller flies away
    CHECK(length(r.L.hand[1].phys - r.L.shoulder(1)) < r.L.P.maxArm + 0.12f, "arm limit: hand stays within reach (%.2f m)", length(r.L.hand[1].phys - r.L.shoulder(1))); }
  { Rig r; init(r, {-4.5f, 0, -3.0f}); run(r, 1.0f, nullptr); r.L.vel = {0, 0, -14}; r.L.hand[0].contact = r.L.hand[1].contact = false;
    for (int h = 0; h < 2; h++) r.hands[h].p.y = 1.5f;
    run(r, 2.0f, nullptr); CHECK(r.L.headW.z > -6.85f, "walls: a 14 m/s fling does not tunnel (z %.2f)", r.L.headW.z); }
  std::printf(fails ? "\n%d FAILED\n" : "\nall locomotion tests passed\n", fails); return fails ? 1 : 0;
}
