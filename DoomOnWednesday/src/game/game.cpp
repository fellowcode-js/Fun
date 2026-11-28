#include "game.h"
#include "layout.h"
#include "map_data.h"
#include "staff_codes.h"
#include <cmath>
#include <cstdio>
#include <algorithm>

namespace dow {

static const int UNLOCK_KILLS = 5;

Vec3 osTileCenter(int i) {
  int col = i % kOSCols, row = i / kOSCols;
  return {-13.04f, 1.14f - row * 0.16f, (1 - col) * 0.30f};   // monitor faces +X; columns run toward -Z (player's right)
}
Vec3 keypadKeyCenter(int i) {
  int row, col;
  if (i >= 1 && i <= 9) { row = (i - 1) / 3; col = (i - 1) % 3; }
  else if (i == 0) { row = 3; col = 1; } else if (i == 10) { row = 3; col = 0; } else { row = 3; col = 2; }
  return kKeypadPos + Vec3{0.012f, (1.5f - row) * 0.105f, -(col - 1) * 0.105f};
}

// ---------------------------------------------------------------- setup
void Game::init() {
  world.buildLevel();
  for (int h = 0; h < 2; h++) { plat[h].col = world.add({0, -10, 0}, {0, -10, 0}, SURF_PLATFORM, COL_DYNAMIC); world.cols[plat[h].col].enabled = false; }
  loco.reset(kSpawn);
  buttons.clear();
  struct Look { int id; uint32_t c; const char* l; };
  static const Look looks[] = {{BTN_RESET, 0xe02626, "RESET"}, {BTN_CUBE, 0x338cf2, "CUBE"}, {BTN_LIGHT, 0xf2cc26, "LIGHT"}, {BTN_SAW, 0x33cc40, "SAW"},
                               {BTN_CLEAR_BOTS, 0xaa44ff, "CLEAR"}, {BTN_SPOT_A, 0xff8833, "DUMMY"}, {BTN_SPOT_B, 0xff8833, "RUNNER"},
                               {BTN_FORM_GORILLA, 0x44cc66, "GORILLA"}, {BTN_FORM_MONSTER, 0xcc3344, "MONSTER"}, {BTN_FORM_ROBOT, 0xffaa22, "ROBOT"},
                               {BTN_FORM_STALKER, 0xaa33ff, "STALKER"}, {BTN_RACK_SAW, 0xff3322, "WEAR"}};
  for (int i = 0; i < kNumButtons; i++) {
    const ButtonDef& d = kButtons[i]; Button b; b.id = d.id; b.p = {d.x, d.y - 0.025f, d.z};
    for (const Look& l : looks) if (l.id == d.id) { b.col = rgb(l.c); b.label = l.l; }
    if (d.id >= 10 && d.id <= 14 && d.id != BTN_RACK_SAW) { b.half = {0.11f, 0.03f, 0.11f}; b.p.y = 0.985f; b.p.x = kFormX; }
    if (d.id == BTN_RACK_SAW) { b.p = {-10.0f, 1.0f, -3.40f}; b.half = {0.09f, 0.09f, 0.035f}; }
    buttons.push_back(b);
  }
  resetCubes();
  for (auto& b : bots) b = Bot{};
  gore.clear();
  form = FORM_GORILLA; csaw = false; sawState = 0; sawT = 0; targetScale = 1;
  buildOS();
  load();
}

void Game::resetCubes() {
  cubes.erase(std::remove_if(cubes.begin(), cubes.end(), [](const Cube& c) { return c.spawned; }), cubes.end());
  if (cubes.empty()) {
    Rng r(77);
    for (int i = 0; i < 5; i++) { Cube c; c.half = 0.07f; c.start = {-0.6f + i * 0.3f, 0.9f + c.half + 0.002f, 2.12f}; c.col = mixC(rgb(0xff5533), rgb(0xffcc33), i / 4.f); cubes.push_back(c); }
    for (int i = 0; i < 4; i++) { Cube c; c.half = 0.14f; c.start = {-3.0f + i * 0.5f, 0.14f + 0.002f, 0.5f}; c.col = mixC(rgb(0x3366ff), rgb(0x33ddaa), i / 3.f); c.q = Quat::yaw(r.range(-0.6f, 0.6f)); cubes.push_back(c); }
  }
  for (auto& c : cubes) { c.p = c.start; c.v = c.w = {}; c.held = -1; if (!c.spawned) c.q = Quat::yaw(0.15f * (c.start.x)); }
}

void Game::addCube() {
  if (cubes.size() >= 40) { say("CUBE LIMIT"); return; }
  static Rng r(991); Cube c; c.half = 0.08f; c.start = {r.range(-0.4f, 0.4f), 1.6f, 2.2f}; c.p = c.start; c.spawned = true;
  float h = r.f(); c.col = mixC(rgb(0x55aaff), rgb(0xff55cc), h); c.q = Quat::axisAngle({r.f(), r.f(), r.f()}, r.range(0, 3)); cubes.push_back(c);
}

void Game::spawnBot(int kind, const Vec3& at) {
  static Rng r(4242);
  for (auto& b : bots) if (!b.active) {
    b = Bot{}; b.active = true; b.kind = kind; b.p = at; b.home = at; b.target = at; b.facing = PI;
    static const uint32_t furs[] = {0x6b4a2f, 0x4a4a52, 0x8a5a2a, 0x2f2f36, 0x7a3a22, 0x5a5a3a};
    b.fur = rgb(furs[r.next() % 6]); return;
  }
  say("BOT LIMIT (8)");
}
void Game::clearBots() { for (auto& b : bots) b.active = false; }

void Game::setForm(int f) {
  if (f == form) return;
  form = f;
  if (!hasSaw()) { sawState = 0; sawT = 0; }
  targetScale = form == FORM_GORILLA ? 1.0f : 1.4f;
  static const char* names[] = {"GORILLA", "MONSTER FORM", "ROBOT FORM  (A = chainsaw)", "STALKER FORM  (A = spore burst)"};
  say(names[f]); sfx(SFX_UNLOCK, loco.headW, 0.6f, f == FORM_GORILLA ? 1.3f : 0.8f);
}

void Game::killed() {
  kills++;
  if (kills >= UNLOCK_KILLS && !unlocked) { unlocked = true; say("STALKER UNLOCKED! poke the purple pedestal"); sfx(SFX_UNLOCK, loco.headW, 1, 1); }
  save();
}

void Game::save() const {
  if (savePath.empty()) return;
  if (FILE* f = std::fopen(savePath.c_str(), "w")) { std::fprintf(f, "%d %d %d %d\n", kills, unlocked ? 1 : 0, role, goreLevel); std::fclose(f); }
}
void Game::load() {
  if (savePath.empty()) return;
  if (FILE* f = std::fopen(savePath.c_str(), "r")) {
    int k = 0, u = 0, r = 0, g = 1; if (std::fscanf(f, "%d %d %d %d", &k, &u, &r, &g) >= 2) { kills = k; unlocked = u || k >= UNLOCK_KILLS; role = r; goreLevel = g; }
    std::fclose(f);
  }
}

// ---------------------------------------------------------------- frame
Vec3 Game::fingertip(int h) const {
  return loco.hand[h].phys + handQ[h].rotate(Vec3{0, -0.012f, -0.075f} * loco.scale);
}

void Game::update(const Input& in) {
  const float dt = clampf(in.dt, 0.001f, 0.05f);
  time += dt; sounds.clear();
  for (auto& h : haptic) { h.amp = 0; h.seconds = 0; }

  // smooth growth when changing form
  float s = loco.scale + (targetScale - loco.scale) * std::min(1.f, dt * 3.f);
  if (std::fabs(s - targetScale) < 0.002f) s = targetScale;
  loco.setScale(s, in.head);
  loco.P.speedMul = speedSetting * (form == FORM_STALKER ? 1.25f : form >= 1 ? 1.12f : 1.f);

  // snap turn (right stick), 30 degrees
  snapCd -= dt;
  if (std::fabs(in.stickR.x) > 0.7f) { if (!rxLatch && snapCd <= 0) { loco.snapTurn(in.stickR.x > 0 ? -PI / 6 : PI / 6); snapCd = 0.25f; rxLatch = true; } }
  else if (std::fabs(in.stickR.x) < 0.35f) rxLatch = false;

  lastHead = in.head;
  loco.step(dt, in.head, in.hand, world, role);
  for (int h = 0; h < 2; h++) {
    handQ[h] = loco.toWorld(in.hand[h].q); gripNow[h] = in.grip[h] > 0.7f;
    gripEdge[h] = gripNow[h] && !gripPrev[h];
    const HandSim& H = loco.hand[h];
    if (H.newTouch) {
      float v = clampf(H.touchSpeed / 3.f, 0.15f, 1.f); buzz(h, 0.25f + 0.6f * v, 0.02f + 0.03f * v);
      int surf = H.collider >= 0 ? world.cols[H.collider].surface : 0;
      sfx(SFX_TAP, H.phys, v, surf == SURF_CARPET ? 0.7f : surf == SURF_METAL ? 1.6f : surf == SURF_WOOD ? 1.15f : 1.0f);
    }
  }

  updatePlatforms(in);
  updateSaw(in, dt);
  updateCombat(in, dt);
  updateCubes(in, dt);
  updateButtons(dt);
  updateBots(dt);
  gore.level = goreLevel; gore.update(dt, world);

  if (toast.t > 0) toast.t -= dt;
  if (sporeFx > 0) sporeFx -= dt;
  if (osMsgT > 0) osMsgT -= dt;
  for (int h = 0; h < 2; h++) gripPrev[h] = gripNow[h];
}

void Game::updatePlatforms(const Input& in) {
  for (int h = 0; h < 2; h++) {
    bool ok = platformsOn && role >= 1 && in.hand[h].valid && gripNow[h];
    Collider& c = world.cols[plat[h].col];
    if (ok && gripEdge[h]) { plat[h].on = true; plat[h].p = loco.hand[h].phys - Vec3{0, 0.06f * loco.scale, 0}; sfx(SFX_BEEP, plat[h].p, 0.4f, 1.4f); }
    if (!ok) plat[h].on = false;
    c.enabled = plat[h].on;
    if (plat[h].on) { c.mn = plat[h].p - Vec3{0.22f, 0.04f, 0.22f}; c.mx = plat[h].p + Vec3{0.22f, 0, 0.22f}; }
  }
}

// ---------------------------------------------------------------- chainsaw
void Game::updateSaw(const Input& in, float dt) {
  bool a = in.a;
  if (a && !aPrev) {
    if (form == FORM_STALKER) {
      if (sporeCd <= 0) {
        sporeCd = 4; buzz(1, 0.8f, 0.08f); sporeFx = 0.6f; sporeFxPos = loco.headW - Vec3{0, 0.2f, 0}; sfx(SFX_SPORE, sporeFxPos, 1, 1);
        for (auto& b : bots) if (b.active && b.alive) {
          Vec3 d = b.p - loco.headW; d.y = 0; float dl = length(d);
          if (dl < 3.2f) { b.knock = normalize(d, {1, 0, 0}) * 7.f; b.hitFlash = 0.4f; }
        }
      } else say("SPORES RECHARGING");
    } else if (hasSaw()) {
      if (sawState == 0) { sawState = 1; sfx(SFX_SAW_ON, loco.hand[1].phys); say("CHAINSAW!"); }
      else if (sawState == 2) { sawState = 3; sfx(SFX_SAW_OFF, loco.hand[1].phys); }
    }
  }
  aPrev = a; sporeCd -= dt;
  if (!hasSaw()) { sawState = 0; sawT = std::max(0.f, sawT - dt * 3); }
  // transitions last exactly as long as the original model's animations (Robot_ToChainsaw / Robot_ToHand)
  if (sawState == 1) { sawT += dt / kSawAnimSeconds; if (sawT >= 1) { sawT = 1; sawState = 2; } }
  if (sawState == 3) { sawT -= dt / kSawAnimSeconds; if (sawT <= 0) { sawT = 0; sawState = 0; } }
  bool live = sawState == 2;
  sawSpin += dt * (live ? 14.f : sawState ? 4.f : 0.f);
  sawLevel = live ? 1.f : (sawState ? 0.4f * sawT : 0.f);
  if (live) buzz(1, 0.22f, 0.03f);
  // blade of the original robot_arm_right model: wrist-local (0,-0.14,0)..(0,-0.58,0), mounted +90 deg about X on the grip
  const float S = loco.scale; Quat q = handQ[1];
  bladeA = loco.hand[1].phys + q.rotate(Vec3{0, 0, -0.14f} * S);
  bladeB = loco.hand[1].phys + q.rotate(Vec3{0, 0, -0.14f - 0.44f * sawT} * S);
}

static float segSeg(const Vec3& p1, const Vec3& q1, const Vec3& p2, const Vec3& q2, Vec3& c2) {
  Vec3 d1 = q1 - p1, d2 = q2 - p2, r = p1 - p2; float a = dot(d1, d1), e = dot(d2, d2), f = dot(d2, r), s, t;
  if (a <= 1e-9f && e <= 1e-9f) { s = t = 0; }
  else if (a <= 1e-9f) { s = 0; t = clampf(f / e, 0, 1); }
  else {
    float c = dot(d1, r);
    if (e <= 1e-9f) { t = 0; s = clampf(-c / a, 0, 1); }
    else { float b = dot(d1, d2), den = a * e - b * b; s = den > 1e-9f ? clampf((b * f - c * e) / den, 0, 1) : 0; t = (b * s + f) / e;
      if (t < 0) { t = 0; s = clampf(-c / a, 0, 1); } else if (t > 1) { t = 1; s = clampf((b - c) / a, 0, 1); } }
  }
  Vec3 u = p1 + d1 * s; c2 = p2 + d2 * t; return length2(u - c2);
}

// Bot skeleton points (feet p, facing yaw): shared with the renderer so hits line up with what you see.
static void botPoints(const Bot& b, Vec3& head, Vec3& shL, Vec3& shR) {
  Quat q = Quat::yaw(b.facing); head = b.p + Vec3{0, 0.80f, 0};
  shL = head + q.rotate({-0.19f, -0.26f, 0.02f}); shR = head + q.rotate({0.19f, -0.26f, 0.02f});
}

void Game::updateCombat(const Input& in, float dt) {
  (void)in;
  const float S = loco.scale;
  static Vec3 prevB;
  bool sawLive = sawState == 2;
  Vec3 swing = (bladeB - prevB) / dt; prevB = bladeB;
  for (int bi = 0; bi < 8; bi++) {
    Bot& b = bots[bi]; if (!b.active || !b.alive) continue;
    Vec3 head, shL, shR; botPoints(b, head, shL, shR);
    Vec3 armL = shL + Vec3{0, -0.18f, 0}, armR = shR + Vec3{0, -0.18f, 0};
    for (int h = 0; h < 2; h++) {
      if (!in.hand[h].valid) continue;
      const Vec3 hp = loco.hand[h].phys; const float hs = length(loco.hand[h].vel);
      if (gripEdge[h] && form >= FORM_MONSTER && b.limbs) {
        int pick = -1; float bd = 1e9f; const Vec3 pts[3] = {head, armL, armR};
        for (int pi = 0; pi < 3; pi++) {
          if (!(b.limbs & (1 << pi))) continue;
          float reach = (pi == 0 ? 0.24f : 0.2f) + 0.06f * S + (form == FORM_STALKER ? 0.1f : 0.f), d = length(pts[pi] - hp);
          if (d < reach && d < bd) { bd = d; pick = pi; }
        }
        if (pick >= 0) {
          Vec3 dir = normalize(hp - b.p + Vec3{0, -0.5f, 0}, {0, 1, 0}); dir = normalize(loco.hand[h].vel * 0.3f + dir);
          b.limbs &= ~(1 << pick); b.hitFlash = 0.3f;
          gore.rip(pick == 0 ? GIB_HEAD : pick == 1 ? GIB_ARM_L : GIB_ARM_R, pts[pick], dir, b.fur, 1.f);
          sfx(SFX_RIP, pts[pick], 1, 0.9f + 0.2f * gore.rng.f()); buzz(h, 1, 0.09f);
          if (pick == 0 || (b.limbs & 6) == 0) { b.alive = false; b.deadT = 6; killed(); }
          gripEdge[h] = false;  // this grab was used for the rip
          continue;
        }
      }
      if (!gripNow[h] && hs > (form == FORM_STALKER ? 2.4f : 3.0f) && b.hitFlash <= 0) {
        Vec3 torso = b.p + Vec3{0, 0.45f, 0};
        if (length(torso - hp) < 0.36f + 0.06f * S || length(head - hp) < 0.2f + 0.05f * S) {
          Vec3 dir = loco.hand[h].vel / hs; float k = form == FORM_STALKER ? 6.f : form >= 1 ? 5.f : 3.5f;
          b.knock = Vec3{dir.x, 0, dir.z} * k; b.hitFlash = 0.35f;
          gore.punch(hp, dir); sfx(SFX_PUNCH, hp, clampf(hs / 6, 0.4f, 1), 1); buzz(h, 0.9f, 0.06f);
        }
      }
    }
    if (sawLive) {
      Vec3 c; float d2 = segSeg(bladeA, bladeB, b.p + Vec3{0, 0.1f, 0}, head + Vec3{0, 0.12f, 0}, c);
      if (d2 < 0.28f * 0.28f) {
        Vec3 bd = normalize(bladeB - bladeA), sw = length(swing) > 0.5f ? normalize(swing) : Vec3{0, -1, 0};
        Vec3 n = normalize(cross(bd, sw), {0, 1, 0});
        b.alive = false; b.sliced = true; b.cutN = n; b.cutP = c; b.deadT = 6; b.limbs = 7;
        Quat q = Quat::yaw(b.facing);
        for (int k = 0; k < 2; k++) {
          float sg = k ? -1.f : 1.f; b.halfOff[k] = {}; b.halfQ[k] = Quat{}; (void)q;
          b.halfV[k] = n * (1.6f * sg) + Vec3{0, 1.2f, 0} + sw * 0.8f; b.halfW[k] = cross(n, Vec3{0, 1, 0}) * (3.f * sg) + bd * 2.f;
        }
        gore.slice(c, sw, b.fur, 1.f); sfx(SFX_SLICE, c, 1, 1); buzz(1, 1, 0.14f); killed();
      }
    }
  }
}

// ---------------------------------------------------------------- bots
void Game::updateBots(float dt) {
  static Rng r(555);
  for (auto& b : bots) {
    if (!b.active) continue;
    b.hitFlash -= dt;
    if (!b.alive) {
      b.deadT -= dt; if (b.deadT <= 0) b.active = false;
      if (b.sliced) for (int k = 0; k < 2; k++) {
        b.halfV[k].y -= 9.81f * dt; b.halfOff[k] += b.halfV[k] * dt;
        float wl = length(b.halfW[k]); if (wl > 1e-4f) b.halfQ[k] = normalize(Quat::axisAngle(b.halfW[k] / wl, wl * dt) * b.halfQ[k]);
        if (b.p.y + b.halfOff[k].y < (k ? 0.12f : -0.25f)) { b.halfOff[k].y = (k ? 0.12f : -0.25f) - b.p.y; b.halfV[k] = b.halfV[k] * 0.5f; b.halfV[k].y = 0; b.halfW[k] = b.halfW[k] * 0.8f; }
      }
      continue;
    }
    Vec3 to = loco.headW - b.p; to.y = 0; float dist = length(to);
    Vec3 move; float speed = 0;
    if (b.kind == 1) {
      if (dist < 3.5f && dist > 1e-3f) { move = -to / dist; speed = 2.6f; }
      else {
        b.retarget -= dt;
        if (b.retarget <= 0) { b.target = b.home + Vec3{r.range(-5, 5), 0, r.range(-5, 5)}; b.retarget = 2 + r.range(0, 3); }
        Vec3 t = b.target - b.p; t.y = 0; float td = length(t); if (td > 0.3f) { move = t / td; speed = 1.1f; }
      }
    }
    Vec3 v = move * speed + b.knock; b.knock = b.knock * (1 - std::min(1.f, 6 * dt));
    Vec3 np = b.p + v * dt, probe = np + Vec3{0, 0.5f, 0};
    Vec3 push = world.resolveSphere(probe, 0.28f, 2);
    if (length2(push) > 0) { np = probe - Vec3{0, 0.5f, 0}; np.y = 0; b.retarget = 0; }
    b.vel = (np - b.p) / dt; b.p = np;
    b.walkPhase += length(b.vel) * dt * 5.f;
    Vec3 face = speed > 0 ? move : to;
    if (length(face) > 1e-3f) {
      float want = std::atan2(-face.x, -face.z);   // avatars look down their local -Z
      float d = want - b.facing; while (d > PI) d -= 2 * PI; while (d < -PI) d += 2 * PI;
      b.facing += d * std::min(1.f, 8 * dt);
    }
  }
}

// ---------------------------------------------------------------- cubes
void Game::updateCubes(const Input& in, float dt) {
  const float S = loco.scale;
  for (int h = 0; h < 2; h++) {
    if (!in.hand[h].valid) { for (auto& c : cubes) if (c.held == h) c.held = -1; continue; }
    const Vec3 hp = loco.hand[h].phys;
    if (gripEdge[h]) {
      int best = -1; float bd = 0.12f * S + 0.05f;
      for (int i = 0; i < (int)cubes.size(); i++) { if (cubes[i].held >= 0) continue; float d = length(cubes[i].p - hp) - cubes[i].half; if (d < bd) { bd = d; best = i; } }
      if (best >= 0) {
        Cube& c = cubes[best]; c.held = h; c.holdOff = handQ[h].conj().rotate(c.p - hp); c.holdRot = handQ[h].conj() * c.q;
        sfx(SFX_TAP, c.p, 0.5f, 1.3f); buzz(h, 0.4f, 0.03f);
      }
    } else if (!gripNow[h]) {
      for (auto& c : cubes) if (c.held == h) { c.held = -1; c.v = loco.hand[h].vel * 1.1f; c.w = Vec3{c.v.z, 0, -c.v.x} * (2.f / std::max(c.half, 0.05f)) * 0.2f; }
    }
  }
  for (size_t i = 0; i < cubes.size(); i++) {
    Cube& c = cubes[i];
    if (c.held >= 0) {
      Vec3 np = loco.hand[c.held].phys + handQ[c.held].rotate(c.holdOff);
      c.v = (np - c.p) / dt; c.p = np; c.q = normalize(handQ[c.held] * c.holdRot); continue;
    }
    c.v.y -= 9.81f * dt;
    // free hands shove cubes
    for (int h = 0; h < 2; h++) {
      if (!in.hand[h].valid) continue;
      Vec3 d = c.p - loco.hand[h].phys; float rr = c.half * 1.1f + loco.P.handRadius * S, dl = length(d);
      if (dl < rr && dl > 1e-4f) { Vec3 n = d / dl; c.p += n * (rr - dl); float vn = dot(c.v - loco.hand[h].vel, n); if (vn < 0) c.v -= n * (vn * 1.2f); }
    }
    if (sawState == 2) {
      Vec3 ab = bladeB - bladeA, ap = c.p - bladeA; float t = clampf(dot(ap, ab) / std::max(dot(ab, ab), 1e-6f), 0, 1); Vec3 d = ap - ab * t; float dl = length(d);
      if (dl < c.half + 0.05f) { c.v += normalize(d) * 3.f + Vec3{0, 1.5f, 0}; c.w += Vec3{gore.rng.range(-20, 20), gore.rng.range(-20, 20), gore.rng.range(-20, 20)}; }
    }
    c.p += c.v * dt;
    float r = c.half * 1.12f; Vec3 n; Vec3 push = world.resolveSphere(c.p, r, 2, &n);
    bool ground = false;
    if (length2(push) > 0) {
      float vn = dot(c.v, n); if (vn < 0) { c.v -= n * (vn * 1.3f); if (vn < -1.5f) sfx(SFX_THUD, c.p, clampf(-vn / 6, 0.1f, 0.8f), c.half > 0.1f ? 0.7f : 1.3f); }
      Vec3 vt = c.v - n * dot(c.v, n); c.v -= vt * std::min(1.f, 6 * dt);
      ground = n.y > 0.7f;
    }
    // cube-cube: sphere separation is plenty for toys
    for (size_t j = i + 1; j < cubes.size(); j++) {
      Cube& o = cubes[j]; Vec3 d = c.p - o.p; float rr = (c.half + o.half) * 1.05f, dl = length(d);
      if (dl < rr && dl > 1e-4f) { Vec3 nn = d / dl; float pen = rr - dl; if (o.held < 0) { c.p += nn * pen * 0.5f; o.p -= nn * pen * 0.5f; } else c.p += nn * pen;
        float vn = dot(c.v - o.v, nn); if (vn < 0) { Vec3 imp = nn * (vn * 0.6f); c.v -= imp; if (o.held < 0) o.v += imp; } }
    }
    if (ground) {
      c.w = c.w * std::exp(-5 * dt);
      // settle flat: pick the local axis closest to up and ease it onto +Y (boxes come to rest on a face)
      Vec3 ax[3] = {c.q.rotate({1, 0, 0}), c.q.rotate({0, 1, 0}), c.q.rotate({0, 0, 1})}; int bi = 0; float bd = 0;
      for (int k = 0; k < 3; k++) if (std::fabs(ax[k].y) > bd) { bd = std::fabs(ax[k].y); bi = k; }
      Vec3 up = ax[bi] * (ax[bi].y < 0 ? -1.f : 1.f);
      if (length(c.v) < 1.0f) c.q = normalize(slerp(c.q, fromTo(up, {0, 1, 0}) * c.q, std::min(1.f, 8 * dt)));
    }
    float wl = length(c.w); if (wl > 1e-4f) c.q = normalize(Quat::axisAngle(c.w / wl, wl * dt) * c.q);
    if (c.p.y < -1 || std::fabs(c.p.x) > 31 || std::fabs(c.p.z) > 31) { c.p = c.start; c.v = c.w = {}; }
  }
}

// ---------------------------------------------------------------- buttons, keypad, Mushroom OS
void Game::updateButtons(float dt) {
  osCool -= dt;
  for (auto& b : buttons) { b.cooldown -= dt; b.press = std::max(0.f, b.press - dt * 4); }
  for (int h = 0; h < 2; h++) {
    int inBtn = -1, inKey = -1, inTile = -1;
    if (loco.hand[h].have) {
      Vec3 tip = fingertip(h);
      for (int i = 0; i < (int)buttons.size(); i++) {
        Vec3 d = tip - buttons[i].p, e = buttons[i].half + Vec3{0.03f, 0.04f, 0.03f};
        if (std::fabs(d.x) < e.x && std::fabs(d.y) < e.y && std::fabs(d.z) < e.z) inBtn = i;
      }
      for (int k = 0; k < 12; k++) { Vec3 d = tip - keypadKeyCenter(k); if (std::fabs(d.x) < 0.04f && std::fabs(d.y) < 0.045f && std::fabs(d.z) < 0.045f) inKey = k; }
      if (role >= 1) for (int k = 0; k < (int)osTiles.size(); k++) {
        Vec3 d = tip - osTileCenter(k); if (std::fabs(d.x) < 0.05f && std::fabs(d.y) < 0.065f && std::fabs(d.z) < 0.14f && osTiles[k].action) inTile = k;
      }
    }
    // fire on entry only: a finger resting on a key never repeats
    if (inBtn >= 0 && inBtn != lastBtn[h] && buttons[inBtn].cooldown <= 0) { Button& b = buttons[inBtn]; b.cooldown = 0.35f; b.press = 1; buzz(h, 0.5f, 0.04f); press(b.id, h); }
    if (inKey >= 0 && inKey != lastKey[h]) keypad(inKey, h);
    if (inTile >= 0 && inTile != lastTile[h] && osCool <= 0) { osCool = 0.25f; buzz(h, 0.5f, 0.04f); osAction(osTiles[inTile].action, h); }
    lastBtn[h] = inBtn; lastKey[h] = inKey; lastTile[h] = inTile;
  }
}

void Game::press(int id, int h) {
  Vec3 at = loco.hand[h].phys; sfx(SFX_BEEP, at, 0.6f, 1);
  switch (id) {
    case BTN_RESET: resetCubes(); say("CUBES RESET"); break;
    case BTN_CUBE: addCube(); break;
    case BTN_LIGHT: lightsDim = !lightsDim; say(lightsDim ? "LIGHTS DOWN" : "LIGHTS UP"); break;
    case BTN_SAW:
      if (hasSaw()) { Input fake; fake.a = true; aPrev = false; updateSaw(fake, 0.f); aPrev = false; }
      else { say("NEED ROBOT FORM OR CHAINSAW HAND"); sfx(SFX_DENY, at); }
      break;
    case BTN_SPOT_A: spawnBot(0, kSpotA); say("DUMMY SPAWNED"); break;
    case BTN_SPOT_B: spawnBot(1, kSpotB); say("RUNNER SPAWNED"); break;
    case BTN_CLEAR_BOTS: clearBots(); say("BOTS CLEARED"); break;
    case BTN_FORM_GORILLA: setForm(FORM_GORILLA); break;
    case BTN_FORM_MONSTER: setForm(FORM_MONSTER); break;
    case BTN_FORM_ROBOT: setForm(FORM_ROBOT); break;
    case BTN_FORM_STALKER:
      if (unlocked || role >= 1) setForm(FORM_STALKER);
      else { char t[64]; std::snprintf(t, sizeof t, "STALKER LOCKED: %d MORE KILLS", UNLOCK_KILLS - kills); say(t); sfx(SFX_DENY, at); buzz(h, 1, 0.15f); }
      break;
    case BTN_RACK_SAW:
      if (role >= 1) { csaw = !csaw; say(csaw ? "CHAINSAW HAND ON  (A)" : "chainsaw hand off"); if (!hasSaw()) sawState = 0; }
      else { say("MODERATORS ONLY"); sfx(SFX_DENY, at); buzz(h, 1, 0.15f); }
      break;
  }
}

void Game::keypad(int key, int h) {
  Vec3 at = keypadKeyCenter(key); buzz(h, 0.4f, 0.03f);
  if (key <= 9) { if (keypadBuf.size() < 10) keypadBuf.push_back((char)('0' + key)); sfx(SFX_KEY, at, 0.5f, 1 + 0.05f * key); return; }
  if (key == 10) { keypadBuf.clear(); sfx(SFX_KEY, at, 0.5f, 0.7f); return; }
  std::string h2 = sha256hex(sha256hex(keypadBuf)); keypadBuf.clear(); int newRole = 0;
  for (const char* x : kOwnerHashes) if (h2 == x) newRole = 2;
  if (!newRole) for (const char* x : kModHashes) if (h2 == x) newRole = 1;
  if (newRole) { role = std::max(role, newRole); say(role == 2 ? "OWNER ACCESS GRANTED" : "MODERATOR ACCESS GRANTED"); sfx(SFX_UNLOCK, at, 1, 1.2f); save(); buildOS(); }
  else { say("WRONG CODE"); sfx(SFX_DENY, at); buzz(h, 1, 0.2f); }
}

void Game::buildOS() {
  osTiles.clear();
  auto T = [&](const char* l, int a, bool on = false) { osTiles.push_back({l, a, on}); };
  static const char* speeds[] = {"SPEED X1", "SPEED X1.5", "SPEED X2"};
  static const char* gores[] = {"GORE: OFF", "GORE: ON", "GORE: EXTREME"};
  switch (osPage) {
    case 0: T("TOGGLES", 1); T("FORMS", 2); T("WORLD", 3); T(role >= 2 ? "OWNER" : "OWNER (LOCKED)", role >= 2 ? 4 : 0); T("", 0); T("", 0); T("", 0); T("", 0); T("", 0); break;
    case 1: T(platformsOn ? "PLATFORMS ON" : "PLATFORMS OFF", 10, platformsOn); T(speeds[speedSetting > 1.9f ? 2 : speedSetting > 1.4f ? 1 : 0], 11, speedSetting > 1.01f);
      T(gores[goreLevel], 12, goreLevel > 0); T(lightsDim ? "LIGHTS: DIM" : "LIGHTS: ON", 13, lightsDim); T("", 0); T("", 0); T("", 0); T("", 0); T("< BACK", 9); break;
    case 2: T("GORILLA", 20, form == 0); T("MONSTER", 21, form == 1); T("ROBOT", 22, form == 2); T("STALKER", 23, form == 3); T(csaw ? "SAW HAND ON" : "SAW HAND OFF", 24, csaw); T("", 0); T("", 0); T("", 0); T("< BACK", 9); break;
    case 3: T("SPAWN DUMMY", 30); T("SPAWN RUNNER", 31); T("CLEAR BOTS", 32); T("RESET CUBES", 33); T("ADD CUBE", 35); T("TP LOBBY", 34); T("", 0); T("", 0); T("< BACK", 9); break;
    case 4: T("UNLOCK STALKER", 40, unlocked); T("RESET KILLS", 41); T("BOT PARTY", 42); T("", 0); T("", 0); T("", 0); T("", 0); T("", 0); T("< BACK", 9); break;
  }
}

void Game::osAction(int a, int h) {
  sfx(SFX_BEEP, osTileCenter(0), 0.5f, 1.2f);
  switch (a) {
    case 1: case 2: case 3: osPage = a; break;
    case 4: if (role >= 2) osPage = 4; break;
    case 9: osPage = 0; break;
    case 10: platformsOn = !platformsOn; break;
    case 11: speedSetting = speedSetting > 1.9f ? 1.f : speedSetting > 1.4f ? 2.f : 1.5f; break;
    case 12: goreLevel = (goreLevel + 1) % 3; save(); break;
    case 13: lightsDim = !lightsDim; break;
    case 20: case 21: case 22: case 23: setForm(a - 20); break;
    case 24: press(BTN_RACK_SAW, h); break;
    case 30: spawnBot(0, kDenCenter + Vec3{1.5f, 0, 1.5f}); break;
    case 31: spawnBot(1, kDenCenter + Vec3{1.5f, 0, -1.0f}); break;
    case 32: clearBots(); break;
    case 33: resetCubes(); break;
    case 34: loco.teleport(kSpawn, lastHead); say("WELCOME BACK"); break;
    case 35: addCube(); break;
    case 40: unlocked = true; save(); say("STALKER UNLOCKED"); break;
    case 41: kills = 0; unlocked = false; save(); say("KILLS RESET"); break;
    case 42: for (int i = 0; i < 6; i++) spawnBot(1, Vec3{-3.f + i * 1.2f, 0, -1.f}); say("BOT PARTY IN THE LOBBY"); break;
  }
  buildOS();
}

}  // namespace dow
