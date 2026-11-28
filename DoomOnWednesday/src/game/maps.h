// Zones: the main lobby and the four Be the Monster maps. Each zone lives at its own spot in the world;
// only the zone you are in collides and renders. Layouts are generated in maps.cpp.
#pragma once
#include <string>
#include <vector>
#include "world.h"
#include "../core/mesh.h"

namespace dow {

enum ZoneId { ZONE_LOBBY = 0, ZONE_BACKROOMS = 1, ZONE_POOLROOMS = 2, ZONE_GARAGE = 3, ZONE_LIGHTSOUT = 4, ZONE_COUNT = 5 };
constexpr int kNumMaps = 4;   // zones 1..4 are votable maps
enum TexId { TEX_WALLPAPER = 0, TEX_CARPET, TEX_CEILING, TEX_TILE, TEX_CONCRETE, TEX_WOOD, TEX_PLANKS, TEX_COUNT };

struct ZoneInfo {
  const char* name; const char* blurb;
  Vec3 origin; float half; float height;
  int wallTex, floorTex, ceilTex;
  Vec3 lightColor; float lightStep, lightRadius, flickerChance;
  Vec3 fog; float fogNear, fogFar; Vec3 ambient, sky;
  bool dark;                    // personal head-lamp, emergency lights only
  uint32_t accent;              // vote-pad colour
};
const ZoneInfo& zoneInfo(int z);
int zoneAt(const Vec3& p);      // which zone contains a world position

struct ZoneMeshes { Mesh walls, floor, ceiling, trim, props, water; std::vector<Vec3> lights; };

// Adds every zone's colliders to the world (tagged with their zone).
void buildZoneColliders(World& w);
// Geometry for rendering (props baked in). Called once by the scene.
void buildZoneMeshes(std::vector<ZoneMeshes>& out);
// Where players appear when a round starts on this map, and the lobby spawn (standing on the stool).
std::vector<Vec3> zoneSpawns(int z);
Vec3 lobbySpawn();
float lobbySpawnYaw();

// Main lobby furniture positions (world space)
Vec3 lobbyKey(int i);           // computer keyboard key centres, see kLobbyKeys
extern const char* const kLobbyKeys[];
extern const int kNumLobbyKeys;
Vec3 lobbyScreenCenter();
Vec3 votePadButton(int map);    // map 0..3 -> vote button
Vec3 readyButton();

}  // namespace dow
