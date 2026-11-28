// Small GLES 3.0 renderer: one uber-shader, instancing, a per-frame draw list replayed for each eye.
#pragma once
#include <vector>
#include "gl.h"
#include "../core/mesh.h"
#include "../game/textures.h"

namespace dow {

struct GpuMesh {
  GLuint vao = 0, vbo = 0, ibo = 0; int count = 0; size_t vcap = 0, icap = 0;
  void upload(const Mesh& m, bool dynamic = false);
  bool ok() const { return count > 0; }
};

enum DrawMode { MODE_LIT = 0, MODE_TEX = 1, MODE_TEXT = 2, MODE_DECAL = 3, MODE_GLOW = 4 };

struct Instance { float m[16]; float col[4]; };

struct DrawItem {
  const GpuMesh* mesh = nullptr;
  int mode = MODE_LIT; GLuint tex = 0;
  Vec3 fur{1, 1, 1};
  int inst0 = 0, instN = 1;     // range in the frame instance buffer
  bool blend = false, cull = true, flesh = false, depthWrite = true;
  Vec4 clip{0, 0, 0, 1};        // keep fragment if dot(clip, worldPos) >= 0
  Mat4 half;                    // applied after clipping (sliced halves fly apart)
};

struct LightSet { Vec4 pos[8]; Vec4 col[8]; int n = 0; };

class Renderer {
 public:
  GLuint texWall = 0, texCarpet = 0, texCeil = 0, texFont = 0, texWhite = 0;
  GLuint tex[8] = {0};   // indexed by TexId (maps.h)
  Vec3 fogColor{0.09f, 0.075f, 0.03f}; float fogNear = 4, fogFar = 28;
  Vec3 ambient{0.10f, 0.09f, 0.05f}, sky{0.30f, 0.27f, 0.16f}, ground{0.10f, 0.08f, 0.03f};
  LightSet lights;

  bool init();
  GLuint makeTexture(const Image& im, bool mips, bool nearestMag);
  // frame building
  void begin();
  void add(const GpuMesh& m, const Mat4& model, Vec4 col = {1, 1, 1, 0}, int mode = MODE_LIT, GLuint tex = 0, Vec3 fur = {1, 1, 1});
  DrawItem& addItem(const GpuMesh& m, const Mat4& model, Vec4 col = {1, 1, 1, 0});
  void addInstanced(const GpuMesh& m, const std::vector<Instance>& inst, int mode = MODE_LIT, bool blend = false);
  void finish();                         // uploads instances
  void renderEye(const Mat4& view, const Mat4& proj, const Vec3& eye);
  int drawCalls() const { return (int)items.size(); }

 private:
  GLuint prog = 0, instVbo = 0; size_t instCap = 0;
  GLint uViewProj, uHalf, uClip, uTex, uMode, uFur, uCam, uFogCol, uFog, uAmb, uSky, uGnd, uLP, uLC, uNL, uFlesh, uTime;
  std::vector<DrawItem> items; std::vector<Instance> inst;
};

Instance makeInst(const Mat4& m, Vec4 c = {1, 1, 1, 0});

}  // namespace dow
