// DOW game rules: forms, chainsaw, bots, ripping, cubes, buttons, staff keypad, Mushroom OS, platforms.
// Pure simulation: no GL, no XR, no audio API. The platform layer fills Input, calls update(), then reads
// the state (and the event queues) to render, play sounds and fire haptics.
#pragma once
#include <string>
#include <vector>
#include "locomotion.h"
#include "gore.h"

namespace dow {

constexpr float kSawAnimSeconds = 1.2f;   // length of Robot_ToChainsaw / Robot_ToHand in robot_arm_right.glb

enum Form { FORM_GORILLA = 0, FORM_MONSTER = 1, FORM_ROBOT = 2, FORM_STALKER = 3 };
enum Sfx { SFX_TAP, SFX_THUD, SFX_GORE, SFX_SLICE, SFX_BEEP, SFX_DENY, SFX_RIP, SFX_SPORE, SFX_SAW_ON, SFX_SAW_OFF, SFX_UNLOCK, SFX_PUNCH, SFX_KEY };

struct Input {
  float dt = 1 / 72.f;
  Pose head, hand[2];           // tracking space (metres, OpenXR grip pose for hands)
  float grip[2] = {0, 0}, trigger[2] = {0, 0};
  bool a = false, b = false, x = false, y = false;  // a/b right, x/y left
  Vec2 stickL, stickR;
};

struct SoundEvent { Sfx id; Vec3 pos; float vol, pitch; };
struct Haptic { float amp = 0, seconds = 0; };

struct Cube {
  Vec3 p, v, w;  // position, velocity, angular velocity
  Quat q;
  float half = 0.07f;
  Color col;
  int held = -1;  // hand index
  Vec3 holdOff; Quat holdRot;
  Vec3 start; bool spawned = false;
};

struct Bot {
  bool active = false, alive = true;
  int kind = 0;           // 0 standing dummy, 1 runner
  Vec3 p;                 // feet position
  float facing = 0;       // yaw
  Vec3 vel, knock;
  int limbs = 7;          // bit0 head, bit1 left arm, bit2 right arm
  float deadT = 0, walkPhase = 0, retarget = 0, hitFlash = 0;
  Vec3 home, target;
  Color fur;
  // chainsaw slice: two halves fly apart along the cut plane
  bool sliced = false; Vec3 cutN, cutP; Vec3 halfV[2], halfW[2]; Vec3 halfOff[2]; Quat halfQ[2];
};

struct Button {
  Vec3 p; int id; float press = 0; float cooldown = 0; Vec3 half{0.1f, 0.03f, 0.08f}; Color col; std::string label;
};

struct Platform { bool on = false; Vec3 p; int col = -1; };

struct Toast { std::string text; float t = 0; };

struct OSTile { std::string label; int action; bool on = false; };

class Game {
 public:
  World world;
  Locomotion loco;
  Gore gore;
  std::vector<Cube> cubes;
  Bot bots[8];
  std::vector<Button> buttons;
  Platform plat[2];

  int form = FORM_GORILLA;
  bool csaw = false;        // chainsaw hand (mods) on the gorilla
  int sawState = 0;         // 0 hand, 1 -> saw, 2 saw, 3 -> hand
  float sawT = 0;           // transform progress 0 (hand) .. 1 (saw)
  float sawSpin = 0;        // chain animation phase
  Vec3 bladeA, bladeB;      // blade segment in world (for hits + rendering)
  int kills = 0; bool unlocked = false;
  int role = 0;             // 0 player, 1 mod, 2 owner
  bool platformsOn = false; float speedSetting = 1; int goreLevel = 1; bool lightsDim = false;
  float sporeCd = 0, sporeFx = 0; Vec3 sporeFxPos;
  float targetScale = 1;
  float time = 0;
  Color fur = rgb(0x5a3b24);

  std::string keypadBuf;   // staff keypad
  int osPage = 0;          // 0 home, 1 toggles, 2 forms, 3 world, 4 owner
  std::vector<OSTile> osTiles; float osCool = 0; std::string osMsg; float osMsgT = 0;

  Toast toast;
  std::vector<SoundEvent> sounds;   // drained by the platform each frame
  Haptic haptic[2];
  float sawLevel = 0;               // continuous chainsaw sound level

  Quat handQ[2];                    // hand rotations in the world (grip pose)
  bool gripNow[2] = {false, false}, gripEdge[2] = {false, false};
  Pose lastHead;

  std::string savePath;             // where kills/unlock persist (empty = no save)

  void init();
  void update(const Input& in);
  bool hasSaw() const { return form == FORM_ROBOT || csaw; }
  void setForm(int f);
  void say(const std::string& t) { toast.text = t; toast.t = 3.0f; }
  void spawnBot(int kind, const Vec3& at);
  void clearBots();
  void resetCubes();
  void addCube();
  void save() const; void load();

 private:
  bool gripPrev[2] = {false, false}, aPrev = false, rxLatch = false;
  float snapCd = 0;
  int lastBtn[2] = {-1, -1}, lastKey[2] = {-1, -1}, lastTile[2] = {-1, -1};
  void sfx(Sfx id, const Vec3& p, float vol = 1, float pitch = 1) { sounds.push_back({id, p, vol, pitch}); }
  void buzz(int h, float amp, float s) { if (amp > haptic[h].amp) { haptic[h].amp = amp; haptic[h].seconds = s; } }
  void killed();
  void updateSaw(const Input& in, float dt);
  void updateBots(float dt);
  void updateCubes(const Input& in, float dt);
  void updateButtons(float dt);
  void updateCombat(const Input& in, float dt);
  void updatePlatforms(const Input& in);
  void press(int id, int hand);
  void buildOS();
  void osAction(int a, int hand);
  void keypad(int key, int hand);
  Vec3 fingertip(int h) const;
};

// Where things sit, for the renderer and for poke tests.
Vec3 osTileCenter(int i);
constexpr int kOSCols = 3, kOSRows = 3;
Vec3 keypadKeyCenter(int i);  // 0-9, 10 = clear, 11 = enter

// Button ids (match the original DOW map)
enum ButtonId { BTN_RESET = 1, BTN_CUBE = 2, BTN_LIGHT = 3, BTN_SAW = 4, BTN_SPOT_A = 5, BTN_SPOT_B = 6, BTN_CLEAR_BOTS = 7,
                BTN_FORM_GORILLA = 10, BTN_FORM_MONSTER = 11, BTN_FORM_ROBOT = 12, BTN_RACK_SAW = 13, BTN_FORM_STALKER = 14 };

// Staff codes are never stored, only sha256(sha256(code)) in hex. Change them in staff_codes.h.
std::string sha256hex(const std::string& s);

}  // namespace dow
