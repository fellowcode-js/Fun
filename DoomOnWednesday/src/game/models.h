// Every DOW model, generated in code (see models.cpp). Units: metres. Characters face -Z, +Y up.
#pragma once
#include "../core/mesh.h"

namespace dow {

// Per-form avatar kit. Arm segments run along +Y from 0 to their rest length; hands are in OpenXR grip
// space (right hand: palm faces -X, fingers point -Z, thumb +Y). Left hands are true mirror images.
struct AvatarKit {
  Mesh head, torso, upperArm, foreArm;
  Mesh palm[2], finger[2], thumb[2];    // [0] left, [1] right
  float upperLen = 0.43f, foreLen = 0.43f;
  float shoulderX = 0.19f, shoulderY = -0.26f;   // relative to the head centre
  float torsoDrop = 0.38f;                       // head centre -> torso origin
  float fingerY[4] = {0.033f, 0.011f, -0.011f, -0.033f};
  Vec3 knuckle{0.004f, 0, -0.058f};              // right hand finger root (left mirrors X)
  Vec3 thumbRoot{-0.012f, 0.045f, -0.012f};
  float handScale = 1.0f;
};

enum FormKit { KIT_GORILLA = 0, KIT_MONSTER, KIT_ROBOT, KIT_STALKER, KIT_COUNT };
AvatarKit buildAvatar(int form);

// Robot chainsaw hand (right). Parts are drawn with an animation parameter t (0 = hand, 1 = saw).
struct RobotHandKit { Mesh palm, finger, blade, tooth, motor; };
RobotHandKit buildRobotHand();

struct PropKit {
  Mesh lightPanel, lightDiffuser;
  Mesh table, stool, pillar, pedestal, pedestalRing, plinth;
  Mesh rack, osDesk, osMushroom, osMonitorFrame, vent, padA, padB, sporePod, mushroomCluster;
  Mesh buttonBase, buttonCap, keypadPlate, keyCap, signBack;
  Mesh cube, dropGeo, decalQuad;
  Mesh gibChunk, gibBone;
};
PropKit buildProps();

// Static level geometry, split by texture.
struct LevelMeshes { Mesh walls, floor, ceiling, trim; };
LevelMeshes buildLevelMeshes();

}  // namespace dow
