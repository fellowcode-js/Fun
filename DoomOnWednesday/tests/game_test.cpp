// Game-rule tests: forms, saw kills, ripping, unlocks, keypad, cubes. Run with: build-desktop/dow_tests
#include "../src/game/game.h"
#include "../src/game/layout.h"
#include "../src/game/models.h"
#include <cstdio>
#include <cstdlib>
using namespace dow;
int locoTests();
static int gf = 0;
#define GCHECK(c, ...) do { if (!(c)) { gf++; std::printf("FAIL: "); } else std::printf("ok:   "); std::printf(__VA_ARGS__); std::printf("\n"); } while (0)

static Input rest() { Input in; in.head.p = {0, 1.6f, 0}; in.head.valid = true; in.hand[0].p = {-0.25f, 0.85f, -0.15f}; in.hand[1].p = {0.25f, 0.85f, -0.15f}; in.hand[0].valid = in.hand[1].valid = true; return in; }
static void run(Game& g, Input& in, int n) { for (int i = 0; i < n; i++) g.update(in); }
static Vec3 trackedFor(const Game& g, const Vec3& world) { return Quat::yaw(-g.loco.yaw).rotate(world - g.loco.rig) / g.loco.scale; }

int main() {
  int lf = locoTests();
  std::printf("\n-- game rules --\n");
  { Game g; g.init(); Input in = rest(); run(g, in, 60);
    GCHECK(g.form == FORM_GORILLA && g.kills == 0 && !g.unlocked, "starts as a gorilla, stalker locked");
    // poke the robot form button
    Vec3 btn{kFormX, 0.99f, -0.0f}; in.hand[1].p = trackedFor(g, btn + Vec3{0, 0.02f, 0.05f}); run(g, in, 40);
    g.loco.teleport({kFormX - 0.6f, 0, 0}, in.head); run(g, in, 10);
    in.hand[1].p = trackedFor(g, btn); run(g, in, 20);
    GCHECK(g.form == FORM_ROBOT, "poking the ROBOT button changes form (form %d)", g.form);
    run(g, in, 200); GCHECK(g.loco.scale > 1.35f, "robot form grows the player (scale %.2f)", g.loco.scale); }
  { Game g; g.init(); g.setForm(FORM_ROBOT); Input in = rest(); run(g, in, 200);
    in.a = true; run(g, in, 1); in.a = false; run(g, in, 100);   // Robot_ToChainsaw is 1.2 s
    GCHECK(g.sawState == 2, "A transforms the robot hand into a chainsaw (state %d)", g.sawState);
    for (int k = 0; k < 5; k++) {
      g.clearBots(); Vec3 head = g.loco.headW; Vec3 f = Quat::yaw(g.loco.yaw).rotate({0, 0, -1});
      g.spawnBot(0, Vec3{head.x, 0, head.z} + f * 0.75f); run(g, in, 2);
      for (int i = 0; i < 30; i++) { float t = i / 29.f; in.hand[1].p = {0.6f - 1.2f * t, 1.0f, -0.45f}; run(g, in, 1); }
      in.hand[1].p = {0.25f, 0.85f, -0.15f}; run(g, in, 20);
    }
    GCHECK(g.kills == 5, "chainsaw sweeps kill dummies (%d kills)", g.kills);
    GCHECK(g.unlocked, "5 kills unlock the stalker");
    int live = 0; for (auto& d : g.gore.decals) live += d.live; GCHECK(live > 5, "blood lands as splats (%d decals)", live); }
  { Game g; g.init(); g.setForm(FORM_MONSTER); Input in = rest(); run(g, in, 200);
    g.spawnBot(0, Vec3{g.loco.headW.x, 0, g.loco.headW.z - 0.8f}); run(g, in, 2);
    Vec3 head = g.bots[0].p + Vec3{0, 0.8f, 0}; in.hand[1].p = trackedFor(g, head); run(g, in, 30);
    in.grip[1] = 1; run(g, in, 2);
    GCHECK(!(g.bots[0].limbs & 1) && !g.bots[0].alive, "monster grip rips the head off (limbs %d)", g.bots[0].limbs);
    int gibs = 0; for (auto& x : g.gore.gibs) gibs += x.live; GCHECK(gibs >= 1, "ripped head flies off as a gib (%d)", gibs); }
  { Game g; g.init(); Input in = rest(); run(g, in, 30);
    GCHECK(g.role == 0, "no staff role by default");
    in.hand[1].q = Quat::yaw(PI / 2);   // index finger pointing at the wall (-X)
    const Vec3 tip{0.075f, 0.012f, 0};  // grip origin sits this far behind the fingertip
    g.loco.teleport({kKeypadPos.x + 0.45f, 0, kKeypadPos.z}, in.head); run(g, in, 120);   // let the body settle first
    auto poke = [&](int key) { Vec3 k = keypadKeyCenter(key);
      in.hand[1].p = trackedFor(g, k + tip + Vec3{0.08f, 0, 0}); run(g, in, 12); in.hand[1].p = trackedFor(g, k + tip); run(g, in, 30);
      if (getenv("DOW_DEBUG")) std::printf("  key %d buf=%s tip=(%.3f %.3f %.3f) key=(%.3f %.3f %.3f)\n", key, g.keypadBuf.c_str(), g.loco.hand[1].phys.x, g.loco.hand[1].phys.y, g.loco.hand[1].phys.z, k.x, k.y, k.z); };
    for (char c : std::string("135790")) poke(c - '0');
    poke(11);
    GCHECK(g.role == 1, "keypad mod code grants moderator (role %d)", g.role); }
  { Game g; g.init(); Input in = rest(); run(g, in, 120); Vec3 c0 = g.cubes[0].p;
    GCHECK(std::fabs(c0.y - (0.9f + g.cubes[0].half)) < 0.03f, "cubes rest on the table (y %.3f)", c0.y); }
  { int tris = 0; for (int f = 0; f < KIT_COUNT; f++) { AvatarKit k = buildAvatar(f); tris += (int)(k.head.idx.size() + k.torso.idx.size()) / 3; }
    GCHECK(tris > 2000 && tris < 120000, "avatar kits build (%d head+torso tris over 4 forms)", tris); }
  std::printf(gf || lf ? "\nSOME TESTS FAILED\n" : "\nall tests passed\n"); return gf || lf;
}
