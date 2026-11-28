// Turns the game state into a draw list: level, props, avatars (with two-bone IK arms), bots, gore, UI.
#pragma once
#include "renderer.h"
#include "../game/game.h"
#include "../game/models.h"
#include "model_asset.h"

namespace dow {

struct AvatarGpu {
  GpuMesh head, torso, upperArm, foreArm, palm[2], finger[2], thumb[2];
  AvatarKit kit;
};

struct AvatarPose {
  Vec3 head; Quat headQ; float bodyYaw = 0; float scale = 1;
  Vec3 hand[2]; Quat handQ[2]; float curl[2] = {0, 0};
  bool drawHead = true, drawTorso = true; Vec3 torsoOffset;
  int limbs = 7;             // bit0 head, bit1 left arm, bit2 right arm
  bool robotRight = false;   // right hand replaced by the chainsaw hand
};

class Scene {
 public:
  Renderer R;
  bool init();
  // Build this frame's draw list. `eyeCenter` is the midpoint between the eyes.
  void build(const Game& g, const Input& in, float dt);
  void render(const Mat4& view, const Mat4& proj, const Vec3& eye) { R.renderEye(view, proj, eye); }
  bool showLocalBody = false;   // first person: arms + hands only (torso would block the view)
  bool showLocalHead = false;   // third-person screenshots only
  void resetBody() { bodyYawInit = false; }   // after teleports: body snaps to the head's facing

 private:
  AvatarGpu kits[KIT_COUNT];
  ModelAsset robotArm;   // the original chainsaw hand (assets/robot_arm_right.dowm)
  PropKit props; GpuMesh mLightPanel, mLightDiff, mPedRing, mButtonCap, mCube, mDrop, mDecal, mGibChunk, mGibBone, mKeyCap;
  struct ZoneGpu { GpuMesh walls, floor, ceiling, trim, props, water; std::vector<Vec3> lights; std::vector<float> flicker; };
  ZoneGpu zones[ZONE_COUNT];
  GpuMesh mLobbyKeyCap, mLobbyScreen;
  GpuMesh mStatic, mStaticText, mLobbyText, mLobbyDyn, mHud, mTags, mBanner; std::string lobbyCache, bannerKey, hudKey;
  GpuMesh mOSBg, mOSText, mDyn, mToast; std::string osKey, dynKey, toastKey;
  std::vector<Vec3> lightPos; std::vector<float> lightFlicker;
  float bodyYaw = 0; bool bodyYawInit = false;

  void drawAvatar(int kit, const AvatarPose& p, Vec3 fur, const Game& g, const Vec4* clip = nullptr, const Mat4* half = nullptr);
  void drawRobotHand(const Vec3& pos, const Quat& q, float s, const Game& g);
  void buildStatic();
  void pickLights(const Game& g, const Vec3& head);
  void buildLobbyStatic();
  void drawLobby(const Game& g);
  void drawOverlays(const Game& g);
  void drawBots(const Game& g);
};

}  // namespace dow
