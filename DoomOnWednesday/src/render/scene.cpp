#include "scene.h"
#include "../game/layout.h"
#include "../game/map_data.h"
#include <cmath>
#include <cstdio>
#include <algorithm>
#include "../game/maps.h"

namespace dow {

// ------------------------------------------------------------------------------------------ helpers
static void bake(Mesh& out, const Mesh& part, const Mat4& m, Vec3 fur) {
  size_t from = out.v.size(); Mesh tmp = part; tmp.transform(0, m);
  for (auto& x : tmp.v) if (x.tint) { x.r = (uint8_t)clampf(x.r * fur.x * 2, 0, 255); x.g = (uint8_t)clampf(x.g * fur.y * 2, 0, 255); x.b = (uint8_t)clampf(x.b * fur.z * 2, 0, 255); x.tint = 0; }
  out.append(tmp); (void)from;
}
static Vec3 C3(Color c) { return {c.r, c.g, c.b}; }

struct Bone { Mat4 upper, fore; };
// Two-bone IK: shoulder -> elbow -> wrist, elbow bends toward `pole`. Segments stretch a little past full reach.
static Bone solveArm(const Vec3& S, const Vec3& W, float a, float b, const Vec3& pole, float s, float upperLen, float foreLen) {
  Vec3 d = W - S; float dl = std::max(length(d), 1e-4f); Vec3 dir = d / dl;
  float k = 1; if (dl > (a + b) * 0.999f) { k = std::min(dl / ((a + b) * 0.999f), 1.3f); a *= k; b *= k; }
  Vec3 bend = pole - dir * dot(pole, dir); bend = normalize(bend, Vec3{0, -1, 0});
  float cosA = clampf((a * a + dl * dl - b * b) / (2 * a * dl), -1, 1), sinA = std::sqrt(std::max(0.f, 1 - cosA * cosA));
  Vec3 E = S + dir * (a * cosA) + bend * (a * sinA);
  auto seg = [&](const Vec3& p, const Vec3& q, float len0) {
    Vec3 v = q - p; float L = std::max(length(v), 1e-4f);
    // twist-stable frame: keep the segment's local Z near the bend plane normal
    Quat r = fromTo({0, 1, 0}, v / L);
    return Mat4::translate(p) * Mat4::rotate(r) * Mat4::scale({s, L / len0, s});
  };
  return {seg(S, E, upperLen), seg(E, W, foreLen)};
}

// ------------------------------------------------------------------------------------------ init
bool Scene::init() {
  if (!R.init()) return false;
  for (int i = 0; i < KIT_COUNT; i++) {
    AvatarGpu& a = kits[i]; a.kit = buildAvatar(i);
    a.head.upload(a.kit.head); a.torso.upload(a.kit.torso); a.upperArm.upload(a.kit.upperArm); a.foreArm.upload(a.kit.foreArm);
    for (int h = 0; h < 2; h++) { a.palm[h].upload(a.kit.palm[h]); a.finger[h].upload(a.kit.finger[h]); a.thumb[h].upload(a.kit.thumb[h]); }
  }
  if (!robotArm.load("robot_arm_right.dowm", R)) std::fprintf(stderr, "DOW: chainsaw hand model missing\n");
  props = buildProps();
  mLightPanel.upload(props.lightPanel); mLightDiff.upload(props.lightDiffuser); mPedRing.upload(props.pedestalRing); mButtonCap.upload(props.buttonCap);
  mCube.upload(props.cube); mDrop.upload(props.dropGeo); mDecal.upload(props.decalQuad); mGibChunk.upload(props.gibChunk); mGibBone.upload(props.gibBone); mKeyCap.upload(props.keyCap);
  { std::vector<ZoneMeshes> zm; buildZoneMeshes(zm);
    for (int z = 0; z < ZONE_COUNT; z++) {
      ZoneGpu& G = zones[z]; G.walls.upload(zm[z].walls); G.floor.upload(zm[z].floor); G.ceiling.upload(zm[z].ceiling); G.trim.upload(zm[z].trim); G.props.upload(zm[z].props); G.water.upload(zm[z].water);
      G.lights = zm[z].lights; for (const Vec3& l : G.lights) { float h = hash2((int)(l.x * 7), (int)(l.z * 7), 99); G.flicker.push_back(h > 1 - zoneInfo(z).flickerChance ? h : 0.f); }
    } }
  buildStatic(); buildLobbyStatic();
  return true;
}

void Scene::buildStatic() {
  Mesh st, tx; const Vec3 noFur{0.5f, 0.5f, 0.5f};
  bake(st, props.table, Mat4::translate({0, 0, 2.2f}), noFur);
  bake(st, props.stool, Mat4::translate({0, 0, -2.4f}), noFur);
  for (int i = 0; i < 3; i++) bake(st, props.pillar, Mat4::translate({kFormX, 0, kFormZ[i]}), noFur);
  bake(st, props.pedestal, Mat4::translate({kFormX, 0, kFormZ[3]}), noFur);
  for (int i = 0; i < 4; i++) bake(st, props.plinth, Mat4::translate({6.55f, 0, kFormZ[i]}), noFur);
  for (const Vec3& sp : {kSpotA, kSpotB}) { (void)sp; }
  bake(st, props.padA, Mat4::translate(kSpotA), noFur); bake(st, props.padB, Mat4::translate(kSpotB), noFur);
  bake(st, props.rack, Mat4::translate({-10.0f, 0, -3.5f}), noFur);
  bake(st, props.osDesk, Mat4::translate({-13.35f, 0, 0}), noFur);
  bake(st, props.osMushroom, Mat4::translate(kOSPos), noFur);
  bake(st, props.osMonitorFrame, Mat4::translate({kOSPos.x, 0, 0}), noFur);
  bake(st, props.vent, Mat4::translate({-7.0f, 0, 0}), noFur);
  for (auto p : {Vec3{-2, 0, -2}, Vec3{2, 0, -5}, Vec3{0, 0, 3}, Vec3{-5, 0, -4}, Vec3{5, 0, 2}, Vec3{-3, 0, 6}, Vec3{-11, 0, 2}}) bake(st, props.sporePod, Mat4::trs({p.x, kRoomH, p.z}, {}, 0.6f), noFur);
  bake(st, props.mushroomCluster, Mat4::trs({-13.3f, 0, 2.7f}, {}, 2.0f), noFur);
  bake(st, props.mushroomCluster, Mat4::trs({-8.2f, 0, 3.0f}, Quat::yaw(1), 1.4f), noFur);
  bake(st, props.mushroomCluster, Mat4::trs({-12.8f, 0, -2.6f}, Quat::yaw(2), 1.2f), noFur);
  for (const Button& b : std::vector<Button>{}) (void)b;
  // button bases (caps are dynamic)
  for (int i = 0; i < kNumButtons; i++) {
    const ButtonDef& d = kButtons[i];
    if (d.id == BTN_RACK_SAW) { Mesh m; m.paint.c = rgb(0x1a1a20); m.box({-10.0f, 1.0f, -3.435f}, {0.13f, 0.13f, 0.01f}); st.append(m); continue; }
    float hx = (d.id >= 10) ? 0.15f : 0.13f; float bx = (d.id >= 10) ? kFormX : d.x; Mesh m; m.paint.c = rgb(0x1a1a20); m.box({bx, d.y - 0.045f, d.z}, {hx, 0.012f, hx * 0.85f}); st.append(m);
  }
  // keypad
  { Mesh m = props.keypadPlate; m.transform(0, Mat4::translate(kKeypadPos + Vec3{-0.0f, 0, 0})); st.append(m); }
  // form statues on the plinths (baked avatars, looking into the lobby)
  static const uint32_t statueFur[4] = {0x5a3b24, 0x3a1414, 0x808080, 0x808080};
  for (int f = 0; f < 4; f++) {
    const AvatarKit& K = kits[f].kit; float s = f == 0 ? 1.0f : 1.35f; Vec3 fur = C3(rgb(statueFur[f]));
    Quat q = Quat::yaw(PI / 2); Vec3 feet{6.55f, 0.16f, kFormZ[f]}; Vec3 head = feet + Vec3{0, 0.8f * s, 0};
    bake(st, K.head, Mat4::trs(head, q, s), fur);
    bake(st, K.torso, Mat4::trs(head + Vec3{0, -K.torsoDrop * s, 0}, q, s), fur);
    for (int h = 0; h < 2; h++) {
      float side = h ? 1.f : -1.f; Vec3 sh = head + q.rotate(Vec3{K.shoulderX * side, K.shoulderY, 0.02f} * s);
      Vec3 hand = feet + q.rotate(Vec3{0.3f * side, 0.06f, -0.22f} * s) + Vec3{0, 0.04f * s, 0};
      Quat hq = q * Quat::axisAngle({1, 0, 0}, -1.2f);
      Vec3 wrist = hand + hq.rotate(Vec3{0, 0, 0.05f} * s * K.handScale);
      Bone b = solveArm(sh, wrist, K.upperLen * s, K.foreLen * s, q.rotate({side * 0.6f, -0.3f, 0.4f}), s, K.upperLen, K.foreLen);
      bake(st, K.upperArm, b.upper, fur); bake(st, K.foreArm, b.fore, fur);
      float hs = s * K.handScale; Mat4 hm = Mat4::trs(hand, hq, hs);
      bake(st, K.palm[h], hm, fur);
      for (int i = 0; i < 4; i++) bake(st, K.finger[h], hm * Mat4::translate({K.knuckle.x * side, K.fingerY[i], K.knuckle.z}) * Mat4::rotate(Quat::yaw(side * 0.5f)), fur);
      bake(st, K.thumb[h], hm * Mat4::translate({K.thumbRoot.x * side, K.thumbRoot.y, K.thumbRoot.z}), fur);
    }
  }
  // signs: dark backing + pixel text
  auto sign = [&](const std::string& t, Vec3 at, Vec3 right, float charH, Color c, bool back = true) {
    Vec3 up{0, 1, 0}, n = normalize(cross(right, up));
    float w = textWidth(t, charH) + charH * 1.2f; int lines = 1; for (char ch : t) if (ch == '\n') lines++;
    float h = lines * charH * 1.15f + charH * 0.8f;
    if (back) { Mesh m; m.paint.c = rgb(0x0e0b06); Quat q = lookRotation(-n, up); m.box(at - n * 0.012f, {w / 2, h / 2, 0.006f}, q); st.append(m); }
    addText(tx, t, at, right, up, charH, c);
  };
  const Vec3 RZ{-1, 0, 0}, RX{0, 0, -1}, RNX{0, 0, 1}, RPZ{1, 0, 0};  // right vectors for signs facing -Z, +X, -X, +Z
  sign("DOOM ON WEDNESDAY", {0, 2.65f, 6.83f}, RZ, 0.22f, rgb(0xffd34d));
  sign("SWING YOUR ARMS: PUSH OFF FLOORS, WALLS & CEILINGS", {0, 2.2f, 6.83f}, RZ, 0.07f, rgb(0xffffff));
  sign("GRIP = GRAB / RIP    A = CHAINSAW / SPORES\nRIGHT STICK = SNAP TURN    NO STICK WALKING!", {0, 1.85f, 6.83f}, RZ, 0.055f, rgb(0xcfc7a0));
  sign("TEST SPOT A\nSTANDING DUMMY", {-4.2f, 1.6f, 6.83f}, RZ, 0.08f, rgb(0xff9944));
  sign("TEST SPOT B\nRUNNING BOT", {4.2f, 1.6f, 6.83f}, RZ, 0.08f, rgb(0x66aaff));
  static const char* fn[4] = {"GORILLA", "MONSTER", "ROBOT", "STALKER"};
  for (int f = 0; f < 4; f++) sign(fn[f], {6.83f, 2.75f, kFormZ[f]}, RNX, 0.1f, f == 3 ? rgb(0xbb66ff) : rgb(0xffffff));
  sign("BECOME A MONSTER: POKE THE BUTTONS", {6.83f, 2.45f, -1.25f}, RNX, 0.07f, rgb(0xff6655));
  sign("MODS ONLY", {-6.83f, 2.5f, 0}, RX, 0.1f, rgb(0xff4444));
  sign("STAFF CODE", {kKeypadPos.x + 0.01f, kKeypadPos.y + 0.43f, kKeypadPos.z}, RX, 0.05f, rgb(0xffd34d));
  sign("CHAINSAW HAND\nPOKE TO WEAR", {-10.0f, 1.6f, -3.43f}, RPZ, 0.06f, rgb(0xff5533), false);
  sign("MUSHROOM OS", {-13.05f, 1.4f, 0}, RX, 0.06f, rgb(0xdd99ff), false);
  sign("LEVEL 0", {0, 2.75f, -6.83f}, RPZ, 0.12f, rgb(0xffd34d));
  // button labels
  for (const auto& d : kButtons) {
    std::string l; Color c = rgb(0xffffff);
    switch (d.id) { case BTN_RESET: l = "RESET"; break; case BTN_CUBE: l = "CUBE"; break; case BTN_LIGHT: l = "LIGHT"; break; case BTN_SAW: l = "SAW"; break;
      case BTN_CLEAR_BOTS: l = "CLEAR"; break; case BTN_SPOT_A: l = "DUMMY"; break; case BTN_SPOT_B: l = "RUNNER"; break; default: break; }
    if (!l.empty()) { Vec3 at{d.x, d.y - 0.03f, d.z - 0.14f}; addText(tx, l, at, RPZ, normalize(Vec3{0, 1, -0.0f}) * 0 + Vec3{0, 0.55f, 0.83f}, 0.03f, c); }
  }
  // keypad key labels
  for (int k = 0; k < 12; k++) { Vec3 c = keypadKeyCenter(k) + Vec3{0.014f, 0, 0}; addText(tx, k <= 9 ? std::string(1, (char)('0' + k)) : k == 10 ? "C" : "OK", c, RX, {0, 1, 0}, 0.035f, rgb(0x111111), 0.2f); }
  mStatic.upload(st); mStaticText.upload(tx);
  std::printf("DOW: static mesh %zu verts, text %zu verts\n", st.v.size(), tx.v.size());
}

// ------------------------------------------------------------------------------------------ per frame
void Scene::pickLights(const Game& g, const Vec3& head) {
  LightSet& L = R.lights; L.n = 0; const ZoneInfo& Z = zoneInfo(g.zone); const ZoneGpu& G = zones[g.zone];
  bool blackout = g.eventT[EV_BLACKOUT] > 0, blood = g.eventT[EV_BLOOD_MOON] > 0;
  float dim = (g.lightsDim && g.zone == ZONE_BACKROOMS) ? 0.25f : 1.f;
  Vec3 lc = Z.lightColor * dim; if (blood) lc = Vec3{1.2f, 0.12f, 0.08f}; if (blackout) lc = Vec3{0.25f, 0.02f, 0.02f};
  int maxN = Z.dark || blackout ? 5 : 6;
  std::vector<std::pair<float, int>> d; for (int i = 0; i < (int)G.lights.size(); i++) d.push_back({length2(G.lights[i] - head), i});
  std::sort(d.begin(), d.end());
  for (int k = 0; k < (int)d.size() && L.n < maxN; k++) {
    int i = d[k].second; float f = 1;
    if (G.flicker[i] > 0) { float t = g.time * (8 + G.flicker[i] * 10); f = 0.55f + 0.45f * (std::sin(t) * std::sin(t * 2.3f + i) > -0.2f ? 1.f : 0.f); }
    if (blackout && (i % 5)) continue;
    L.pos[L.n] = {G.lights[i].x, G.lights[i].y - 0.15f, G.lights[i].z, Z.lightRadius}; L.col[L.n] = {lc.x * f, lc.y * f, lc.z * f, 0}; L.n++;
  }
  if (g.zone == ZONE_BACKROOMS && length(head - kDenCenter) < 12 && L.n < 7) {
    L.pos[L.n] = {-10.5f, 2.4f, 0, 9}; L.col[L.n] = {0.7f, 0.35f, 1.0f, 0}; L.n++;
  }
  if ((Z.dark || blackout) && L.n < 8) {   // your own dim head-lamp in the dark
    Vec3 f = g.loco.headQW.rotate({0, 0, -1.2f}); L.pos[L.n] = {head.x + f.x, head.y + f.y + 0.2f, head.z + f.z, 6.5f}; L.col[L.n] = {0.55f, 0.5f, 0.4f, 0}; L.n++;
  }
  if (g.sawState && L.n < 8) { L.pos[L.n] = {g.bladeB.x, g.bladeB.y, g.bladeB.z, 2.0f}; L.col[L.n] = {0.6f * g.sawT, 0.35f * g.sawT, 0.1f * g.sawT, 0}; L.n++; }
  float amb = (blackout ? 0.25f : 1.f) * dim;
  R.ambient = Z.ambient * amb; R.sky = Z.sky * amb; R.ground = Z.ambient * 0.8f * amb;
  R.fogColor = blood ? Vec3{0.12f, 0.01f, 0.01f} : blackout ? Z.fog * 0.2f : Z.fog; R.fogNear = Z.fogNear; R.fogFar = blackout ? std::min(Z.fogFar, 12.f) : Z.fogFar;
  if (g.phase == PH_HIDE && g.myRole() == PR_MONSTER) { R.fogNear = 0.2f; R.fogFar = 1.2f; R.fogColor = {0, 0, 0}; }   // monsters can't peek
}

void Scene::drawRobotHand(const Vec3& pos, const Quat& q, float s, const Game& g) {
  if (!robotArm.ok()) return;
  // Same playback as the original game: Hand_Idle -> Robot_ToChainsaw -> Chainsaw_Idle -> Robot_ToHand
  static const int aIdle = robotArm.anim("Hand_Idle"), aTo = robotArm.anim("Robot_ToChainsaw"), aBack = robotArm.anim("Robot_ToHand"), aSaw = robotArm.anim("Chainsaw_Idle");
  robotArm.resetPose();
  switch (g.sawState) {
    case 0: robotArm.apply(aIdle, g.time, true); break;
    case 1: robotArm.apply(aTo, g.sawT * kSawAnimSeconds, false); break;
    case 2: robotArm.apply(aTo, kSawAnimSeconds, false); robotArm.apply(aSaw, g.time, true); break;
    case 3: robotArm.apply(aBack, (1 - g.sawT) * kSawAnimSeconds, false); break;
  }
  robotArm.computeWorld();
  // original mount: the model's fingers run down its -Y, rotated +90 deg about X onto the grip's -Z
  robotArm.draw(R, Mat4::trs(pos, q, s) * Mat4::rotate(Quat::axisAngle({1, 0, 0}, PI / 2)));
}

void Scene::drawAvatar(int ki, const AvatarPose& p, Vec3 fur, const Game& g, const Vec4* clip, const Mat4* half) {
  const AvatarGpu& A = kits[ki]; const AvatarKit& K = A.kit; const float s = p.scale;
  Quat body = Quat::yaw(p.bodyYaw);
  auto put = [&](const GpuMesh& m, const Mat4& mm) {
    DrawItem& d = R.addItem(m, mm); d.fur = fur;
    if (clip) { d.clip = *clip; d.half = *half; d.flesh = true; d.cull = false; }
  };
  if (p.drawHead && (p.limbs & 1)) put(A.head, Mat4::trs(p.head, p.headQ, s));
  if (!(p.limbs & 1) && clip == nullptr) {   // neck stump
    DrawItem& d = R.addItem(mGibChunk, Mat4::trs(p.head + Vec3{0, -0.13f * s, 0}, {}, s * 1.6f)); (void)d;
  }
  Vec3 torsoPos = p.head + Vec3{0, -K.torsoDrop * s, 0} + body.rotate(p.torsoOffset * s);
  if (p.drawTorso) put(A.torso, Mat4::trs(torsoPos, body, s));
  for (int h = 0; h < 2; h++) {
    if (!(p.limbs & (2 << h))) continue;
    float side = h ? 1.f : -1.f;
    Vec3 sh = p.head + body.rotate(Vec3{K.shoulderX * side, K.shoulderY, 0.02f} * s) + body.rotate(p.torsoOffset * s);
    float hs = s * K.handScale;
    Vec3 wrist = p.hand[h] + p.handQ[h].rotate(Vec3{0, 0, 0.05f} * hs);
    Vec3 pole = body.rotate(Vec3{side * 0.7f, -0.5f, 0.45f});
    Bone b = solveArm(sh, wrist, K.upperLen * s, K.foreLen * s, pole, s, K.upperLen, K.foreLen);
    put(A.upperArm, b.upper); put(A.foreArm, b.fore);
    if (h == 1 && p.robotRight) { if (!clip) drawRobotHand(p.hand[h], p.handQ[h], s, g); continue; }
    Mat4 hm = Mat4::trs(p.hand[h], p.handQ[h], hs);
    put(A.palm[h], hm);
    float c = p.curl[h];
    for (int i = 0; i < 4; i++) put(A.finger[h], hm * Mat4::translate({K.knuckle.x * side, K.fingerY[i], K.knuckle.z}) * Mat4::rotate(Quat::yaw(side * (0.15f + c * 1.35f) * (1 - i * 0.04f))));
    put(A.thumb[h], hm * Mat4::translate({K.thumbRoot.x * side, K.thumbRoot.y, K.thumbRoot.z}) * Mat4::rotate(Quat::yaw(side * c * 0.6f)));
  }
}

void Scene::drawBots(const Game& g) {
  Mesh tags; Quat yq = Quat::yaw(yawOf(g.loco.headQW)); Vec3 right = yq.rotate({1, 0, 0});
  for (const Bot& b : g.bots) {
    if (!b.active) continue;
    if (b.part >= 0 && zoneAt(b.p) != g.zone) continue;
    bool monster = b.part >= 0 && b.role == PR_MONSTER && !b.disguised;
    float sc = monster ? 1.35f : 1.f;
    AvatarPose p; p.scale = sc; p.bodyYaw = b.facing; p.limbs = b.limbs;
    Quat q = Quat::yaw(b.facing); float bob = std::sin(b.walkPhase * 2) * 0.02f;
    p.head = b.p + Vec3{0, (0.8f + bob) * sc, 0}; p.headQ = q * Quat::axisAngle({1, 0, 0}, b.alive ? -0.1f : 0.f);
    if (!b.alive && !b.sliced) {   // ragdoll-lite: slump over
      float k = clampf((6 - b.deadT) * 2.5f, 0, 1); p.head = b.p + q.rotate({0, 0.8f - 0.55f * k, -0.35f * k}); p.headQ = q * Quat::axisAngle({1, 0, 0}, -1.3f * k);
    }
    for (int h = 0; h < 2; h++) {
      float side = h ? 1.f : -1.f, sw = std::sin(b.walkPhase + h * PI) * std::min(1.f, length(b.vel)) * 0.25f;
      p.hand[h] = b.p + q.rotate(Vec3{0.3f * side, 0.06f + std::max(0.f, -sw) * 0.3f, -0.18f + sw} * sc);
      p.handQ[h] = q * Quat::axisAngle({1, 0, 0}, -1.25f); p.curl[h] = 0.4f;
    }
    Vec3 fur = b.hitFlash > 0 ? lerp(C3(b.fur), Vec3{1, 0.3f, 0.3f}, b.hitFlash * 2) : C3(b.fur);
    if (b.sliced) {
      for (int k = 0; k < 2; k++) {
        float sg = k ? -1.f : 1.f; Vec4 clip{b.cutN.x * sg, b.cutN.y * sg, b.cutN.z * sg, -dot(b.cutN, b.cutP) * sg};
        Mat4 half = Mat4::translate(b.cutP + b.halfOff[k]) * Mat4::rotate(b.halfQ[k]) * Mat4::translate(-b.cutP);
        drawAvatar(KIT_GORILLA, p, fur, g, &clip, &half);
      }
    } else drawAvatar(monster ? KIT_MONSTER : KIT_GORILLA, p, monster ? C3(rgb(0x3a1414)) : fur, g);
    if (b.part >= 0 && b.alive && b.part < (int)g.parts.size()) {
      const Participant& P = g.parts[b.part];
      Color tc = (monster || (P.role == PR_MONSTER && g.phase == PH_END)) ? rgb(0xff4444) : rgb(0xffffff);
      addText(tags, P.name, p.head + Vec3{0, 0.32f * sc, 0}, right, {0, 1, 0}, 0.05f, tc);
    }
  }
  mTags.upload(tags, true); R.add(mTags, Mat4{}, {1, 1, 1, 0}, MODE_TEXT, R.texFont);
}

void Scene::build(const Game& g, const Input& in, float dt) {
  R.begin();
  const Locomotion& L = g.loco;
  pickLights(g, L.headW);
  // level: only the zone you are in
  { const ZoneInfo& Z = zoneInfo(g.zone); const ZoneGpu& G = zones[g.zone];
    R.add(G.walls, Mat4{}, {1, 1, 1, 0}, MODE_TEX, R.tex[Z.wallTex]);
    R.add(G.floor, Mat4{}, {1, 1, 1, 0}, MODE_TEX, R.tex[Z.floorTex]);
    R.add(G.ceiling, Mat4{}, {1, 1, 1, 0}, MODE_TEX, R.tex[Z.ceilTex]);
    R.add(G.trim, Mat4{}); R.add(G.props, Mat4{});
    if (G.water.ok()) R.add(G.water, Mat4::translate({0, 0.008f * std::sin(g.time * 1.3f), 0}), {1, 1, 1, 0.05f * std::sin(g.time * 2.f)});
    if (g.zone != ZONE_LOBBY && g.zone != ZONE_LIGHTSOUT) {   // ceiling light panels
      std::vector<Instance> panels, diff; float dim = (g.lightsDim && g.zone == ZONE_BACKROOMS) ? 0.2f : 1.f; if (g.eventT[EV_BLACKOUT] > 0) dim = 0.03f;
      Vec3 c = g.eventT[EV_BLOOD_MOON] > 0 ? Vec3{1, 0.15f, 0.1f} : Vec3{1, 1, 1};
      for (size_t i = 0; i < G.lights.size(); i++) {
        if (length2(G.lights[i] - L.headW) > 34 * 34) continue;
        Mat4 m = Mat4::translate(G.lights[i]); panels.push_back(makeInst(m));
        float f = 1; if (G.flicker[i] > 0) { float t = g.time * (8 + G.flicker[i] * 10); f = std::sin(t) * std::sin(t * 2.3f + i) > -0.2f ? 1.f : 0.35f; }
        diff.push_back(makeInst(m, {f * dim * c.x * Z.lightColor.x, f * dim * c.y * Z.lightColor.y, f * dim * c.z * Z.lightColor.z, 0}));
      }
      R.addInstanced(mLightPanel, panels); R.addInstanced(mLightDiff, diff);
    }
  }
  if (g.zone == ZONE_LOBBY) drawLobby(g);
  if (g.zone == ZONE_BACKROOMS) {
  R.add(mStatic, Mat4{});
  R.add(mStaticText, Mat4{}, {1, 1, 1, 0}, MODE_TEXT, R.texFont);
  // pedestal ring + kill counter
  { Vec4 c = g.unlocked ? Vec4{0.3f, 1.f, 0.4f, 0.4f} : Vec4{1.f, 0.2f, 0.2f, 0.4f}; R.add(mPedRing, Mat4::translate({kFormX, 0, kFormZ[3]}), c); }
  // buttons
  { std::vector<Instance> caps;
    for (const Button& b : g.buttons) {
      Vec3 h = b.half; Vec3 p = b.p; if (b.id == BTN_RACK_SAW) p.z -= 0.02f * b.press; else p.y -= 0.018f * b.press;
      Vec4 col{b.col.r, b.col.g, b.col.b, 0.25f + 0.5f * b.press};
      if (b.id == BTN_FORM_STALKER && !g.unlocked && g.role < 1) col = {0.35f, 0.25f, 0.4f, 0.05f};
      if (b.id == BTN_RACK_SAW && g.csaw) col.w = 0.9f;
      caps.push_back(makeInst(Mat4::trs(p, {}, h), col));
    }
    R.addInstanced(mButtonCap, caps); }
  // keypad keys
  { std::vector<Instance> keys; for (int k = 0; k < 12; k++) keys.push_back(makeInst(Mat4::translate(keypadKeyCenter(k)), k == 10 ? Vec4{1, 0.5f, 0.5f, 0.1f} : k == 11 ? Vec4{0.5f, 1, 0.5f, 0.1f} : Vec4{1, 1, 1, 0.05f})); R.addInstanced(mKeyCap, keys); }
  // dynamic text: OS screen, keypad display, kill counter
  {
    std::string key = std::to_string(g.osPage) + "|" + std::to_string(g.role) + "|";
    for (auto& t : g.osTiles) key += t.label + (t.on ? "*" : "") + ";";
    if (key != osKey) {
      osKey = key; Mesh bg, txt; const Vec3 right{0, 0, -1}, up{0, 1, 0};
      bg.paint = Paint{rgb(0x120a1e), 0.6f, false, 0}; bg.box({-13.056f, 0.98f, 0}, {0.002f, 0.28f, 0.52f});
      static const char* titles[] = {"HOME", "TOGGLES", "FORMS", "WORLD", "OWNER"};
      if (g.role < 1) addText(txt, "MUSHROOM OS\n\nSTAFF ONLY\nENTER YOUR CODE\nON THE KEYPAD", {-13.053f, 0.98f, 0}, right, up, 0.05f, rgb(0xdd99ff));
      else {
        addText(txt, std::string("MUSHROOM OS / ") + titles[g.osPage] + (g.role >= 2 ? "   [OWNER]" : "   [MOD]"), {-13.053f, 1.235f, 0}, right, up, 0.035f, rgb(0xdd99ff));
        for (int i = 0; i < (int)g.osTiles.size(); i++) {
          const OSTile& t = g.osTiles[i]; if (t.label.empty()) continue; Vec3 c = osTileCenter(i); c.x = -13.054f;
          bg.paint = Paint{t.on ? rgb(0x2a7a3a) : t.action ? rgb(0x3a2a5a) : rgb(0x2a2a2a), 0.8f, false, 0}; bg.box(c, {0.001f, 0.065f, 0.135f});
          addText(txt, t.label, c + Vec3{0.002f, 0, 0}, right, up, t.label.size() > 12 ? 0.022f : 0.028f, rgb(0xffffff));
        }
      }
      mOSBg.upload(bg, true); mOSText.upload(txt, true);
    }
    R.add(mOSBg, Mat4{}, {1, 1, 1, 0}, MODE_GLOW); R.add(mOSText, Mat4{}, {1, 1, 1, 0}, MODE_TEXT, R.texFont);
    char kc[64]; std::snprintf(kc, sizeof kc, "%d/5", std::min(g.kills, 5));
    std::string dkey = g.keypadBuf + "|" + kc + "|" + (g.unlocked ? "U" : "L") + std::to_string(g.role);
    if (dkey != dynKey) {
      dynKey = dkey; Mesh t;
      std::string shown = g.keypadBuf.empty() ? (g.role == 2 ? "OWNER" : g.role == 1 ? "MOD" : "----") : std::string(g.keypadBuf.size(), '*');
      addText(t, shown, kKeypadPos + Vec3{0.014f, 0.31f, 0}, {0, 0, -1}, {0, 1, 0}, 0.05f, rgb(0x55ff77));
      addText(t, g.unlocked ? "UNLOCKED!" : std::string("LOCKED: KILLS ") + kc, {6.83f, 2.45f, kFormZ[3]}, {0, 0, 1}, {0, 1, 0}, 0.06f, g.unlocked ? rgb(0x66ff77) : rgb(0xff5555));
      mDyn.upload(t, true);
    }
    R.add(mDyn, Mat4{}, {1, 1, 1, 0}, MODE_TEXT, R.texFont);
  }
  // cubes
  { std::vector<Instance> ci; for (const Cube& c : g.cubes) ci.push_back(makeInst(Mat4::trs(c.p, c.q, c.half), {c.col.r, c.col.g, c.col.b, c.held >= 0 ? 0.15f : 0.f})); R.addInstanced(mCube, ci); }
  }   // backrooms-only content

  // ---- local player body (head hidden: you are looking out of it)
  {
    float hy = yawOf(L.headQW);
    if (!bodyYawInit) { bodyYaw = hy; bodyYawInit = true; }
    float d = hy - bodyYaw; while (d > PI) d -= 2 * PI; while (d < -PI) d += 2 * PI;
    float rate = std::fabs(d) > 0.6f ? 6.f : 1.5f; bodyYaw += d * std::min(1.f, rate * dt);
    AvatarPose p; p.head = L.headW; p.headQ = L.headQW; p.bodyYaw = bodyYaw; p.scale = L.scale; p.drawHead = showLocalHead; p.drawTorso = showLocalBody;
    p.torsoOffset = {0, -0.02f, 0.1f};
    for (int h = 0; h < 2; h++) { p.hand[h] = L.hand[h].phys; p.handQ[h] = g.handQ[h]; p.curl[h] = std::max(in.grip[h], in.trigger[h] * 0.5f); if (!in.hand[h].valid) p.limbs &= ~(2 << h); }
    p.robotRight = g.hasSaw();
    int ki = g.form; Vec3 fur = g.form == FORM_GORILLA ? C3(g.fur) : g.form == FORM_MONSTER ? C3(rgb(0x3a1414)) : Vec3{0.5f, 0.5f, 0.5f};
    if (g.myRole() == PR_GHOST) fur = Vec3{0.75f, 0.8f, 0.85f};
    drawAvatar(ki, p, fur, g);
  }
  drawBots(g);
  // ---- gore
  {
    std::vector<Instance> drops, poofs, decals;
    for (const Drop& d : g.gore.drops) if (d.life > 0) {
      if (d.poof) poofs.push_back(makeInst(Mat4::trs(d.p, {}, d.size * std::min(1.f, d.life * 2)), {1.6f, 1.6f, 1.6f, 0.4f}));
      else { Vec3 v = d.v; float sp = length(v); Quat q = sp > 0.1f ? fromTo({0, 1, 0}, v / sp) : Quat{}; drops.push_back(makeInst(Mat4::trs(d.p, q, Vec3{d.size, d.size * (1 + std::min(sp * 0.25f, 1.5f)), d.size} * 0.55f))); }
    }
    for (const Decal& d : g.gore.decals) if (d.live) {
      Quat q = fromTo({0, 1, 0}, d.n) * Quat::yaw(d.rot); float fade = d.age > 80 ? (90 - d.age) / 10 : 1;
      decals.push_back(makeInst(Mat4::trs(d.p, q, d.size * 0.5f * std::min(1.f, d.age * 8 + 0.3f)), {fade, 1, 1, d.rot}));
    }
    R.addInstanced(mDrop, drops); R.addInstanced(mDrop, poofs, MODE_GLOW);
    if (!decals.empty()) { R.addInstanced(mDecal, decals, MODE_DECAL, true); }
    for (const Gib& gb : g.gore.gibs) if (gb.live) {
      Mat4 m = Mat4::trs(gb.p, gb.q, gb.scale); Vec3 fur = C3(gb.fur);
      const AvatarGpu& A = kits[KIT_GORILLA];
      if (gb.type == GIB_HEAD) { R.add(A.head, m, {1, 1, 1, 0}, MODE_LIT, 0, fur); R.add(mGibChunk, m * Mat4::trs({0, -0.13f, 0}, {}, 1.6f)); }
      else if (gb.type == GIB_ARM_L || gb.type == GIB_ARM_R) {
        int h = gb.type == GIB_ARM_R ? 1 : 0;
        R.add(A.upperArm, m * Mat4::translate({0, -0.4f, 0}), {1, 1, 1, 0}, MODE_LIT, 0, fur); R.add(A.foreArm, m * Mat4::translate({0, -0.83f, 0}) * Mat4::rotate(Quat::axisAngle({1, 0, 0}, PI)) * Mat4::translate({0, -0.43f, 0}), {1, 1, 1, 0}, MODE_LIT, 0, fur);
        R.add(A.palm[h], m * Mat4::translate({0, -0.86f, 0}) * Mat4::rotate(Quat::axisAngle({1, 0, 0}, PI / 2)), {1, 1, 1, 0}, MODE_LIT, 0, fur);
        R.add(mGibChunk, m * Mat4::trs({0, 0.0f, 0}, {}, 1.4f));
      } else if (gb.type == GIB_BONE) R.add(mGibBone, m);
      else R.add(mGibChunk, m);
    }
    if (g.sporeFx > 0) { float k = 1 - g.sporeFx / 0.6f; std::vector<Instance> s; Rng r(3);
      for (int i = 0; i < 60; i++) { Vec3 d = normalize(Vec3{r.range(-1, 1), r.range(-0.3f, 1), r.range(-1, 1)}); s.push_back(makeInst(Mat4::trs(g.sporeFxPos + d * (0.3f + 3.0f * k), {}, 0.03f * (1 - k) + 0.01f), {0.3f, 1.4f, 0.4f, 1.0f})); }
      R.addInstanced(mDrop, s, MODE_GLOW); }
  }
  drawOverlays(g);
  // ---- toast (head-locked, slightly below eye line)
  if (g.toast.t > 0) {
    if (toastKey != g.toast.text) { toastKey = g.toast.text; Mesh t; addText(t, g.toast.text, {0, 0, 0}, {1, 0, 0}, {0, 1, 0}, 0.03f, rgb(0xffd34d)); mToast.upload(t, true); }
    Quat yq = Quat::yaw(yawOf(L.headQW)); Vec3 pos = L.headW + yq.rotate({0, -0.18f, -0.75f});
    R.add(mToast, Mat4::trs(pos, yq, 1), {1, 1, 1, 0}, MODE_TEXT, R.texFont);
  }
  R.finish();
}

}  // namespace dow

namespace dow {

static const char* kModeLabel[] = {"ONE MONSTER", "TWO MONSTERS", "INFECTION", "SHAPESHIFTER"};
static std::string fmtTime(float t) { int s = (int)std::ceil(std::max(t, 0.f)); char b[16]; std::snprintf(b, sizeof b, "%d:%02d", s / 60, s % 60); return b; }

void Scene::buildLobbyStatic() {
  Mesh t; const Vec3 O = zoneInfo(ZONE_LOBBY).origin;
  const Vec3 X{1, 0, 0}, NZ{0, 0, -1}, Y{0, 1, 0};
  for (int k = 0; k < kNumLobbyKeys; k++) {   // labels printed on the key tops, readable from the stool
    std::string l = kLobbyKeys[k]; float h = l.size() > 2 ? 0.014f : 0.03f; if (l.rfind("OPT", 0) == 0) l = "OPT" + l.substr(3);
    addText(t, l, lobbyKey(k) + Vec3{0, 0.0135f, 0}, X, NZ, h, rgb(0x101010), 0.1f);
  }
  addText(t, "DOOM ON WEDNESDAY", O + Vec3{0, 2.55f, -3.97f}, X, Y, 0.2f, rgb(0xffd34d));
  addText(t, "UP / DOWN = PAGE    OPT 1-4 = CHOOSE    ENTER = CONFIRM", O + Vec3{0, 1.83f, -3.6f + 0.06f}, X, Y, 0.028f, rgb(0xcfc7a0));
  addText(t, "<  MAP VOTE", O + Vec3{-4.97f, 2.85f, 0}, NZ, Y, 0.12f, rgb(0xffb347));
  addText(t, "VOTE FOR THE NEXT MAP", O + Vec3{-9, 2.7f, -3.97f}, X, Y, 0.13f, rgb(0xffd34d));
  addText(t, "POKE A PAD TO VOTE", O + Vec3{-9, 2.4f, -3.97f}, X, Y, 0.06f, rgb(0xcfc7a0));
  addText(t, "READY", readyButton() + Vec3{0, 0.75f, 0.2f}, X, Y, 0.1f, rgb(0xffd34d));
  addText(t, "GAME MODES\nBE THE MONSTER  - LIVE\nREGULAR  - COMING SOON\nDON'T SPLASH  - COMING SOON", O + Vec3{4.97f, 2.55f, 2.4f}, Vec3{0, 0, 1}, Y, 0.065f, rgb(0xddd5b0));
  for (int m = 0; m < kNumMaps; m++) {
    const ZoneInfo& Z = zoneInfo(1 + m); Vec3 c = O + Vec3{-12.86f, 1.95f, -3.0f + m * 2.0f};
    addText(t, Z.name, c + Vec3{0, 0.15f, 0}, NZ, Y, 0.1f, rgb(Z.accent)); addText(t, Z.blurb, c + Vec3{0, -0.12f, 0}, NZ, Y, 0.045f, rgb(0xcfc7a0));
  }
  mLobbyText.upload(t);
  Mesh k; k.paint = Paint{rgb(0xd8d4c8), 0.12f, false, 0}; k.roundBox({0, 0, 0}, {0.033f, 0.012f, 0.033f}, 0.35f, {}, 6); mLobbyKeyCap.upload(k);
  Mesh sc; sc.paint = Paint{rgb(0x0a140c), 0.5f, false, 0}; sc.box(lobbyScreenCenter() + Vec3{0, 0, -0.004f}, {0.86f, 0.45f, 0.002f}); mLobbyScreen.upload(sc);
}

void Scene::drawLobby(const Game& g) {
  R.add(mLobbyScreen, Mat4{}, {1, 1, 1, 0}, MODE_GLOW);
  R.add(mLobbyText, Mat4{}, {1, 1, 1, 0}, MODE_TEXT, R.texFont);
  { std::vector<Instance> keys;
    for (int k = 0; k < kNumLobbyKeys; k++) { bool opt = std::string(kLobbyKeys[k]).rfind("OPT", 0) == 0, big = std::string(kLobbyKeys[k]).size() > 1 && !opt;
      Vec4 c = opt ? Vec4{0.6f, 0.85f, 1, 0.1f} : big ? Vec4{1, 0.85f, 0.5f, 0.1f} : Vec4{1, 1, 1, 0.05f};
      keys.push_back(makeInst(Mat4::trs(lobbyKey(k), {}, Vec3{opt ? 2.0f : big ? 1.0f : 1.f, 1, 1}), c)); }
    R.addInstanced(mLobbyKeyCap, keys); }
  // computer screen + vote counts + round board, rebuilt when anything shown changes
  char buf[256]; std::string key;
  const Profile& P = g.profile;
  std::snprintf(buf, sizeof buf, "%d|%s|%s|%s|%d%d%d|%d|%d|%d|%d|%d|%d|%s|%d|%d%d%d%d|%d|%d", g.page, g.typed.c_str(), P.name.c_str(), P.room.c_str(), P.r, P.g, P.b, P.voice, P.mode, P.monsterMode,
                g.phase, (int)g.phaseT, g.role, g.screenMsgT > 0 ? g.screenMsg.c_str() : "", g.colorChan, g.votes[0], g.votes[1], g.votes[2], g.votes[3], g.myVote, (int)g.parts.size());
  key = buf; for (auto& p : g.parts) key += p.name + std::to_string((int)p.pity);
  if (key != lobbyCache) {
    lobbyCache = key; Mesh t; const Vec3 X{1, 0, 0}, Y{0, 1, 0}, NZ{0, 0, -1}, Z1{0, 0, 1};
    Vec3 sc = lobbyScreenCenter(); Color green = rgb(0x66ff88), dim = rgb(0x2e7a40), white = rgb(0xe8ffe8);
    static const char* pages[CP_COUNT] = {"ROOM", "NAME", "COLOR", "VOICE", "GAME MODE", "MONSTER MODE", "QUEUE", "STAFF"};
    for (int i = 0; i < CP_COUNT; i++) addText(t, std::string(i == g.page ? "> " : "  ") + pages[i], sc + Vec3{-0.62f, 0.36f - i * 0.075f, 0}, X, Y, 0.04f, i == g.page ? white : dim);
    std::string body; static const char* gm[] = {"BE THE MONSTER", "REGULAR (SOON)", "DON'T SPLASH (SOON)"};
    switch (g.page) {
      case CP_ROOM: body = "ROOM: " + P.room + "\n\nTYPE A CODE + ENTER\nOPT1 = PUBLIC ROOM\n\n> " + g.typed + "_\n\nONLINE ROOMS ARE NOT LIVE YET:\nBOTS FILL YOUR ROOM"; break;
      case CP_NAME: body = "NAME: " + P.name + "\n\nTYPE A NEW NAME + ENTER\n\n> " + g.typed + "_"; break;
      case CP_COLOR: std::snprintf(buf, sizeof buf, "COLOR\n\n%sRED   %d\n%sGREEN %d\n%sBLUE  %d\n\nOPT1-3 PICK, 0-9 SET", g.colorChan == 0 ? "> " : "  ", P.r, g.colorChan == 1 ? "> " : "  ", P.g, g.colorChan == 2 ? "> " : "  ", P.b); body = buf; break;
      case CP_VOICE: body = std::string("VOICE CHAT: ") + (P.voice ? "ON" : "OFF") + "\n\nOPT1 = ON\nOPT2 = OFF\n\n(VOICE NEEDS ONLINE PLAY)"; break;
      case CP_MODE: body = std::string("MODE: ") + gm[P.mode] + "\n\nOPT1 BE THE MONSTER\nOPT2 REGULAR (SOON)\nOPT3 DON'T SPLASH (SOON)\nOPT4 PRACTICE AREA"; break;
      case CP_MONSTER: body = std::string("NEXT ROUND: ") + kModeLabel[P.monsterMode] + "\n\nOPT1 ONE MONSTER\nOPT2 TWO MONSTERS\nOPT3 INFECTION\nOPT4 SHAPESHIFTER  (B = SHIFT)"; break;
      case CP_QUEUE: std::snprintf(buf, sizeof buf, "NEXT ROUND IN %s\nMODE: %s\nYOUR MONSTER CHANCE: %d%%\n\nOPT1 = READY (START NOW)", fmtTime(g.phaseT).c_str(), kModeLabel[P.monsterMode], (int)std::lround(g.monsterChance(0) * 100)); body = buf; break;
      case CP_STAFF:
        if (g.role < 1) body = "STAFF ONLY\n\nTYPE YOUR CODE + ENTER\n\n> " + std::string(g.typed.size(), '*') + "_";
        else body = std::string(g.role >= 2 ? "OWNER PANEL\n" : "MOD PANEL\n") + "OPT1 BLACKOUT   OPT2 LOW GRAVITY\nOPT3 BLOOD MOON OPT4 GIANT MODE\n1 START ROUND  2 END ROUND\n3 MONSTER RUSH 4 BOT PARTY\n5 ME MONSTER NEXT (OWNER)\n6 UNLOCK STALKER (OWNER)\n7 CLEAR GORE   8 MOD DEN\n9 BACK TO LOBBY";
        break;
    }
    addText(t, body, sc + Vec3{0.22f, 0.06f, 0}, X, Y, 0.036f, green);
    if (g.screenMsgT > 0) addText(t, g.screenMsg, sc + Vec3{0, -0.39f, 0}, X, Y, 0.032f, rgb(0xffd34d));
    for (int m = 0; m < kNumMaps; m++) {
      std::snprintf(buf, sizeof buf, "%d VOTE%s%s", g.votes[m], g.votes[m] == 1 ? "" : "S", g.myVote == m ? "\n(YOURS)" : "");
      addText(t, buf, votePadButton(m) + Vec3{0.05f, 0.42f, 0}, NZ, Y, 0.08f, g.myVote == m ? rgb(0x66ff88) : rgb(0xffffff));
    }
    // round board on the east wall
    std::string board; std::snprintf(buf, sizeof buf, "BE THE MONSTER\nNEXT ROUND IN %s\n%s\n\nMONSTER CHANCE\n", fmtTime(g.phaseT).c_str(), kModeLabel[P.monsterMode]); board = buf;
    for (int i = 0; i < (int)g.parts.size(); i++) { std::snprintf(buf, sizeof buf, "%-8s %3d%%\n", g.parts[i].name.c_str(), (int)std::lround(g.monsterChance(i) * 100)); board += buf; }
    addText(t, board, zoneInfo(ZONE_LOBBY).origin + Vec3{4.97f, 1.55f, -1.2f}, Z1, Y, 0.06f, rgb(0xffd34d));
    mLobbyDyn.upload(t, true);
  }
  R.add(mLobbyDyn, Mat4{}, {1, 1, 1, 0}, MODE_TEXT, R.texFont);
}

void Scene::drawOverlays(const Game& g) {
  const Locomotion& L = g.loco; Quat hq = L.headQW, yq = Quat::yaw(yawOf(hq));
  // big banner (round start / end / events), follows your gaze
  if (g.bannerT > 0) {
    if (bannerKey != g.banner) { bannerKey = g.banner; Mesh t; addText(t, g.banner, {0, 0, 0}, {1, 0, 0}, {0, 1, 0}, 0.06f, rgb(0xff4433)); mBanner.upload(t, true); }
    R.add(mBanner, Mat4::trs(L.headW + hq.rotate({0, 0.12f, -1.1f}) , hq, 1), {1, 1, 1, 0}, MODE_TEXT, R.texFont);
  }
  // round HUD, small, low in view
  std::string hud;
  if (g.phase == PH_LOBBY && g.zone == ZONE_LOBBY && g.profile.mode == GM_BE_THE_MONSTER) hud = "NEXT ROUND " + fmtTime(g.phaseT);
  else if (g.phase >= PH_STARTING && g.phase <= PH_HUNT) {
    int alive = 0; for (auto& p : g.parts) alive += p.role == PR_SURVIVOR;
    static const char* ph[] = {"", "GET READY", "HIDE", "HUNT", ""}; static const char* rl[] = {"SURVIVOR", "MONSTER", "GHOST"};
    char b[160]; std::snprintf(b, sizeof b, "%s %s   SURVIVORS %d   YOU: %s%s", ph[g.phase], fmtTime(g.phaseT).c_str(), alive, rl[g.myRole()],
                               g.myRole() == PR_MONSTER && g.roundMode == MM_SHAPESHIFTER ? (g.parts[0].shifted ? "  (B: HIDE)" : "  (B: SHIFT)") : "");
    hud = b;
  }
  if (!hud.empty()) {
    if (hud != hudKey) { hudKey = hud; Mesh t; addText(t, hud, {0, 0, 0}, {1, 0, 0}, {0, 1, 0}, 0.022f, g.myRole() == PR_MONSTER ? rgb(0xff6655) : rgb(0xddd5b0)); mHud.upload(t, true); }
    R.add(mHud, Mat4::trs(L.headW + yq.rotate({0, -0.32f, -0.8f}), yq * Quat::axisAngle({1, 0, 0}, 0.35f), 1), {1, 1, 1, 0}, MODE_TEXT, R.texFont);
  }
  // jumpscare: the monster's face right in yours
  if (g.jumpscare > 0) {
    float k = g.jumpscare, shake = std::sin(g.time * 90) * 0.01f;
    Mat4 m = Mat4::trs(L.headW + hq.rotate({shake, -0.03f, -0.34f + 0.05f * (1.4f - k)}), hq * Quat::yaw(PI), 1.7f);
    R.add(kits[KIT_MONSTER].head, m, {1, 1, 1, 0.15f}, MODE_LIT, 0, C3(rgb(0x3a1414)));
  }
}

}  // namespace dow
