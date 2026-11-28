// Authored models loaded from .dowm files (converted from .glb by tools/glb_to_dowm.py), with node animation.
#pragma once
#include <string>
#include <vector>
#include "renderer.h"

namespace dow {

struct ModelNode { std::string name; int parent = -1, mesh = -1; Vec3 t; Quat r; Vec3 s{1, 1, 1}; };
struct ModelAnimChannel { int node, path; std::vector<float> times, values; };
struct ModelAnim { std::string name; float duration = 0; std::vector<ModelAnimChannel> ch; };

// CPU meshes of a .dowm file by node name (node transforms baked in). Used for the sculpted avatar parts.
bool loadModelMeshes(const std::string& assetName, std::vector<std::pair<std::string, Mesh>>& out);

class ModelAsset {
 public:
  bool load(const std::string& assetName, Renderer& R);
  bool ok() const { return loaded; }
  int anim(const std::string& name) const;
  int node(const std::string& name) const;
  // Pose: start from the bind pose, then apply animations in order (later ones override channels).
  void resetPose();
  void apply(int anim, float time, bool loop);
  void computeWorld();
  Mat4 nodeWorld(int i) const { return world[i]; }
  void draw(Renderer& R, const Mat4& model, Vec4 tint = {1, 1, 1, 0});
  std::vector<ModelNode> nodes; std::vector<ModelAnim> anims;
 private:
  bool loaded = false;
  std::vector<GpuMesh> meshes; std::vector<int> meshMat; std::vector<int> matTex; std::vector<GLuint> tex;
  std::vector<Vec3> pt, ps; std::vector<Quat> pr; std::vector<Mat4> world;
};

}  // namespace dow
