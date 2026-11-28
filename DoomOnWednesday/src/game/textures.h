// Procedural textures (wallpaper, carpet, ceiling tiles) and DOW's own 5x7 pixel font. RGBA8, sRGB.
#pragma once
#include <vector>
#include <string>
#include <cstdint>
#include "../core/mesh.h"

namespace dow {

struct Image { int w = 0, h = 0; std::vector<uint8_t> px; };

Image makeWallpaper(int size = 512);
Image makeCarpet(int size = 512);
Image makeCeiling(int size = 256);
Image makeTiles(int size = 512);      // poolrooms: white glazed tile, grout
Image makeConcrete(int size = 512);   // parking garage
Image makeWood(int size = 512);       // lobby wall boards
Image makePlanks(int size = 512);     // lobby floor
Image makeFontAtlas();   // 16 x 6 cells, ASCII 32..127

// Append text quads. origin = centre of the text block; right/up span one character cell each.
void addText(Mesh& m, const std::string& text, const Vec3& origin, const Vec3& right, const Vec3& up, float charH, Color c, float emissive = 1.f);
float textWidth(const std::string& text, float charH);   // widest line

}  // namespace dow
