// Level layout shared by the collision world, the scene builder and the game rules (one source of truth).
#pragma once
#include "../core/math.h"

namespace dow {

struct PropBox { Vec3 c, h; uint8_t surface; };

constexpr Vec3 kSpawn{0, 0, -3.2f};
constexpr Vec3 kSpotA{-4.2f, 0, 3.2f}, kSpotB{4.2f, 0, 3.2f};
constexpr Vec3 kDenCenter{-10.5f, 0, 0};
constexpr Vec3 kOSPos{-13.2f, 0, 0};          // Mushroom OS terminal, faces +X
constexpr Vec3 kRackPos{-10.0f, 0, -3.4f};    // chainsaw-hand rack, faces +Z
constexpr Vec3 kKeypadPos{-6.83f, 0.95f, -2.4f};  // staff keypad on the lobby's west wall, faces +X
constexpr float kFormX = 5.3f;   // form buttons stand in front of the statues
constexpr float kFormZ[4] = {-5.0f, -2.5f, 0.0f, 2.5f};

// surfaces: 0 carpet, 1 wall, 2 wood, 3 metal
static const PropBox kPropBoxes[] = {
    {{0, 0.45f, 2.2f}, {0.85f, 0.45f, 0.375f}, 2},           // lobby prop table (buttons on top)
    {{-3.25f, 0.455f, 3.2f}, {0.16f, 0.455f, 0.16f}, 3},     // test spot A podium
    {{5.15f, 0.455f, 3.2f}, {0.16f, 0.455f, 0.16f}, 3},      // test spot B podium
    {{kFormX, 0.48f, -5.0f}, {0.25f, 0.48f, 0.25f}, 3},      // form pillars
    {{kFormX, 0.48f, -2.5f}, {0.25f, 0.48f, 0.25f}, 3},
    {{kFormX, 0.48f, 0.0f}, {0.25f, 0.48f, 0.25f}, 3},
    {{kFormX, 0.48f, 2.5f}, {0.3f, 0.48f, 0.3f}, 3},         // stalker pedestal
    {{6.55f, 0.08f, -5.0f}, {0.28f, 0.08f, 0.4f}, 2},        // display plinths
    {{6.55f, 0.08f, -2.5f}, {0.28f, 0.08f, 0.4f}, 2},
    {{6.55f, 0.08f, 0.0f}, {0.28f, 0.08f, 0.4f}, 2},
    {{6.55f, 0.08f, 2.5f}, {0.28f, 0.08f, 0.4f}, 2},
    {{0, 0.23f, -2.4f}, {0.2f, 0.23f, 0.2f}, 2},             // stool
    {{-1.2f, 0.455f, -5.2f}, {0.16f, 0.455f, 0.16f}, 3},     // back-to-lobby podium
    {{-10.0f, 0.9f, -3.5f}, {0.7f, 0.9f, 0.06f}, 3},         // chainsaw rack board
    {{-13.35f, 0.275f, 0}, {0.45f, 0.275f, 0.8f}, 3},        // Mushroom OS desk (low: gorillas are short)
};
constexpr int kNumPropBoxes = sizeof(kPropBoxes) / sizeof(kPropBoxes[0]);

// Ceiling light grid (every 4 m) — also used as point-light candidates.
constexpr float kLightStep = 4.0f;

}  // namespace dow
