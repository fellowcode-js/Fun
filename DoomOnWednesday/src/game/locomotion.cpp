#include "locomotion.h"
#include <cmath>

namespace dow {

void Locomotion::reset(const Vec3& spawn, float yaw0) {
  rig = spawn; yaw = yaw0; vel = {}; histN = histI = 0; skipVel = 0;
  for (auto& h : hand) h = HandSim{};
}

Vec3 Locomotion::shoulder(int h) const {
  Vec3 f = headQW.rotate({0, 0, -1}); f.y = 0; f = normalize(f, {0, 0, -1});
  Vec3 right{-f.z, 0, f.x};
  return headW + right * ((h ? 0.19f : -0.19f) * scale) + Vec3{0, -0.24f * scale, 0} - f * (0.04f * scale);
}

Vec3 Locomotion::avgHist(int n) const {
  n = std::min(n, histN); if (n <= 0) return {};
  Vec3 s; for (int i = 0; i < n; i++) s += hist[(histI - 1 - i + 16) % 8]; return s / (float)n;
}

void Locomotion::snapTurn(float a) {
  Quat r = Quat::yaw(a);
  rig = headW + r.rotate(rig - headW); yaw += a; vel = r.rotate(vel);
  for (int i = 0; i < 8; i++) hist[i] = r.rotate(hist[i]);
  for (auto& h : hand) { h.phys = headW + r.rotate(h.phys - headW); h.contact = false; h.lastPhys = h.phys; h.have = false; }
  skipVel = 2;
}

void Locomotion::setScale(float s, const Pose& head) {
  if (std::fabs(s - scale) < 1e-5f) return;
  Vec3 hw = toWorld(head.p); scale = s; rig = hw - Quat::yaw(yaw).rotate(head.p * s);
  for (auto& h : hand) { h.have = false; h.contact = false; }
}

void Locomotion::teleport(const Vec3& feet, const Pose& head) {
  Vec3 off = Quat::yaw(yaw).rotate(head.p * scale); rig = {feet.x - off.x, feet.y, feet.z - off.z};
  vel = {}; histN = histI = 0; for (auto& h : hand) { h.have = false; h.contact = false; }
}

void Locomotion::step(float dt, const Pose& head, const Pose hands[2], const World& w, int role) {
  const float S = scale, hr = P.handRadius * S;
  headW = toWorld(head.p); headQW = toWorld(head.q);
  const bool anyPrev = hand[0].contact || hand[1].contact;
  const Vec3 rig0 = rig;

  // 1. ballistic flight when nothing is gripping
  if (!anyPrev) {
    vel.y -= P.gravity * dt;
    float drag = 1 - P.airDrag * dt; vel.x *= drag; vel.z *= drag;
    // sub-stepped body motion so fast flights cannot tunnel through 30 cm walls
    Vec3 move = vel * dt; int n = std::max(1, (int)std::ceil(length(move) / (0.08f * S)));
    for (int i = 0; i < n; i++) { rig += move / (float)n; headW = toWorld(head.p); bodyCollide(w, role, dt / n); }
  }
  headW = toWorld(head.p);

  // 2. tracked targets, limited by arm length
  for (int h = 0; h < 2; h++) {
    HandSim& H = hand[h]; H.newTouch = false; H.wasContact = H.contact;
    if (!hands[h].valid) { H.have = false; H.contact = false; continue; }
    Vec3 T = toWorld(hands[h].p), sh = shoulder(h), d = T - sh; float dl = length(d), reach = P.maxArm * S;
    if (dl > reach) T = sh + d * (reach / dl);
    H.target = T;
  }

  // 3. hand physics -> body correction
  Vec3 corr, impactExclude; int nc = 0;
  for (int h = 0; h < 2; h++) {
    HandSim& H = hand[h]; if (!hands[h].valid) continue;
    const Vec3 T = H.target;
    if (!H.have) {  // (re)acquire: bring the hand in from the head so it never spawns inside a wall
      SweepHit s = w.sweepSphere(headW, T, hr, role); H.phys = s.pos; H.lastPhys = H.phys; H.have = true; H.contact = false; H.vel = {};
      continue;
    }
    if (H.contact) {
      Vec3 m = T - H.phys; float lift = dot(m, H.normal);
      bool still = w.sphereContact(H.phys, hr, role, 0.012f * S).hit;  // surface may have vanished (mod platform)
      if (lift > P.unstickLift * S || length(m) > P.maxStretch * S || !still) {
        H.contact = false;  // released — fall through to a free move from the anchor
      } else {
        float fr = (H.collider >= 0 && H.collider < (int)w.cols.size()) ? w.cols[H.collider].friction : 1.f;
        if (fr < 1) { Vec3 tang = m - H.normal * dot(m, H.normal); H.phys += tang * (1 - fr); }
        Vec3 c = H.phys - T;
        // pressing into a wall holds you on it instead of slowly shoving you off (makes climbing feel solid)
        if (std::fabs(H.normal.y) < 0.5f) impactExclude += H.normal * (dot(c, H.normal) * 0.6f);
        corr += c; nc++;
        continue;
      }
    }
    Vec3 from = H.phys;
    if (length(T - from) > 0.6f * S) from = headW;  // lost track: re-enter from the head, never through walls
    SweepHit s = w.sweepSphere(from, T, hr, role);
    if (s.hit) {
      H.phys = s.pos; H.normal = s.normal; H.collider = s.collider; H.contact = true;
      Vec3 c = H.phys - T;
      if (!H.wasContact) {
        H.newTouch = true; H.touchSpeed = length(H.vel);
        // the slap itself pushes you back, but only part of it becomes momentum (no accidental rocket-wall launches)
        impactExclude += s.normal * (dot(c, s.normal) * 0.7f);
      }
      corr += c; nc++;
    } else { H.phys = T; H.contact = false; }
  }

  const bool anyNow = nc > 0;
  if (anyNow) {
    Vec3 c = corr / (float)nc; float cl = length(c), cap = P.maxCorrection * S;
    if (cl > cap) c = c * (cap / cl);
    rig += c;
    for (auto& H : hand) H.target += c;
    headW = toWorld(head.p);
    bodyCollide(w, role, dt);
  }

  // 4. momentum: average recent body motion while gripping, launch with it on release
  Vec3 frameV = (rig - rig0 - (nc ? impactExclude / (float)nc : Vec3{})) / dt;
  if (skipVel > 0) { skipVel--; frameV = {}; histN = histI = 0; }
  if (anyNow) {
    pushHist(frameV); vel = avgHist(3);
  } else if (anyPrev) {
    Vec3 v = avgHist(5) * (P.jumpMultiplier * P.speedMul); float vl = length(v), cap = P.maxJumpSpeed * S * P.speedMul;
    if (vl > cap) v = v * (cap / vl);
    vel = v; histN = histI = 0; pushHist(vel);
  } else pushHist(vel);
  float vm = length(vel), vmax = P.maxSpeed * S * P.speedMul; if (vm > vmax) vel = vel * (vmax / vm);

  // 5. hand velocities (world space, include body motion) for punches, throws and haptics
  for (int h = 0; h < 2; h++) {
    HandSim& H = hand[h]; if (!H.have) continue;
    Vec3 v = (H.target - H.lastPhys) / dt; if (length(v) > 40) v = {};
    H.vel = lerp(H.vel, v, 0.45f); H.lastPhys = H.target;
  }
}

void Locomotion::bodyCollide(const World& w, int role, float dt) {
  const float S = scale; bodyGrounded = false;
  Vec3 hw = headW, n;
  Vec3 push = w.resolveSphere(hw, P.headRadius * S, role, &n);
  if (length2(push) > 0) { rig += push; headW += push; float vn = dot(vel, n); if (vn < 0) vel -= n * vn; }
  Vec3 tp = headW + Vec3{0, -0.38f * S, 0};
  push = w.resolveSphere(tp, P.torsoRadius * S, role, &n);
  if (length2(push) > 0) { rig += push; headW += push; float vn = dot(vel, n); if (vn < 0) vel -= n * vn; if (n.y > 0.6f) bodyGrounded = true; }
  float bottom = headW.y - P.bodyHeight * S;
  if (bottom < 0) { rig.y -= bottom; headW.y -= bottom; if (vel.y < 0) vel.y = 0; bodyGrounded = true; }
  if (bodyGrounded) { float k = std::exp(-P.groundFriction * dt); vel.x *= k; vel.z *= k; }
}

}  // namespace dow
