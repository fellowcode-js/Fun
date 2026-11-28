// Arm locomotion ("gorilla movement"), written from scratch for DOW.
//
// Each hand is a physical sphere that chases the tracked controller. When it is blocked by a surface it
// stays there, and the gap between where the hand *is* and where the controller *wants* it is fed back
// into the body, so pushing a hand into the floor lifts you and dragging it backwards moves you forward.
// While anchored, hands grip (no sliding unless the surface is slippery); lifting the hand away from the
// surface releases it. On release the body keeps the averaged momentum of the last few frames, which is
// what lets you run, leap and climb. The body itself is a head sphere + torso sphere with gravity,
// ground friction and an arm-length limit that keeps both the physics and the visuals believable.
#pragma once
#include "world.h"

namespace dow {

struct Pose { Vec3 p; Quat q; bool valid = false; };

struct LocoParams {
  float handRadius = 0.055f;
  float maxArm = 0.92f;          // shoulder -> hand reach (metres at scale 1)
  float jumpMultiplier = 1.12f;  // release boost, like a good gorilla game
  float maxJumpSpeed = 7.2f;
  float maxSpeed = 11.f;
  float gravity = 9.81f;
  float airDrag = 0.08f;         // per second
  float groundFriction = 7.0f;   // body sliding on the floor
  float unstickLift = 0.004f;    // how far you must lift a hand off the surface to release it
  float maxStretch = 0.30f;      // anchor torn off if the controller is this far from the hand
  float maxCorrection = 0.16f;   // per-frame body correction cap (tracking glitch guard)
  float bodyHeight = 0.72f;      // head to "feet" — gorillas are short
  float headRadius = 0.15f;
  float torsoRadius = 0.21f;
  float speedMul = 1.f;          // forms move faster
};

struct HandSim {
  Vec3 phys;          // where the hand really is (rendered here)
  Vec3 target;        // where the tracked controller wants it
  Vec3 normal{0, 1, 0};
  bool contact = false, wasContact = false, have = false;
  int collider = -1;
  float touchSpeed = 0;   // impact speed of a new touch (for haptics + taps)
  bool newTouch = false;
  Vec3 vel;           // smoothed hand velocity (world)
  Vec3 lastPhys;
};

class Locomotion {
 public:
  LocoParams P;
  Vec3 rig;           // tracking-space origin in the world
  float yaw = 0;      // tracking-space rotation about +Y
  float scale = 1;    // tracking-space scale (monster forms are bigger)
  Vec3 vel;
  HandSim hand[2];
  Vec3 headW;
  Quat headQW;
  bool bodyGrounded = false;
  int skipVel = 0;

  void reset(const Vec3& spawn, float yaw0 = 0);
  Vec3 toWorld(const Vec3& tracked) const { return rig + Quat::yaw(yaw).rotate(tracked * scale); }
  Quat toWorld(const Quat& q) const { return Quat::yaw(yaw) * q; }
  Vec3 shoulder(int h) const;  // world-space shoulder estimate from the head pose
  void step(float dt, const Pose& head, const Pose hands[2], const World& w, int role);
  void snapTurn(float angle);
  void setScale(float s, const Pose& head);      // keeps the head where it is
  void teleport(const Vec3& feet, const Pose& head);

 private:
  Vec3 hist[8]; int histN = 0, histI = 0;
  void pushHist(const Vec3& v) { hist[histI] = v; histI = (histI + 1) % 8; if (histN < 8) histN++; }
  Vec3 avgHist(int n) const;
  void bodyCollide(const World& w, int role, float dt);
};

}  // namespace dow
