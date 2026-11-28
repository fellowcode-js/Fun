#include "model_asset.h"
#include "../core/assets.h"
#include <cstring>
#include <cstdio>

namespace dow {

namespace {
struct Reader {
  const std::vector<uint8_t>& b; size_t o = 0; bool bad = false;
  explicit Reader(const std::vector<uint8_t>& d) : b(d) {}
  void raw(void* dst, size_t n) { if (o + n > b.size()) { bad = true; std::memset(dst, 0, n); return; } std::memcpy(dst, &b[o], n); o += n; }
  uint32_t u() { uint32_t v; raw(&v, 4); return v; }
  int32_t i() { int32_t v; raw(&v, 4); return v; }
  float f() { float v; raw(&v, 4); return v; }
  std::string name() { char s[33] = {0}; raw(s, 32); return s; }
};
}

bool loadModelMeshes(const std::string& assetName, std::vector<std::pair<std::string, Mesh>>& out) {
  std::vector<uint8_t> data; if (!readAsset(assetName, data)) return false;
  Reader rd(data); char magic[4]; rd.raw(magic, 4); if (std::memcmp(magic, "DOWM", 4) || rd.u() != 1) return false;
  struct N { std::string name; int parent, mesh; Vec3 t; Quat r; Vec3 s; }; std::vector<N> nodes(rd.u());
  for (auto& n : nodes) { n.name = rd.name(); n.parent = rd.i(); n.mesh = rd.i(); n.t = {rd.f(), rd.f(), rd.f()}; n.r = {rd.f(), rd.f(), rd.f(), rd.f()}; n.s = {rd.f(), rd.f(), rd.f()}; }
  struct MR { uint32_t v0, vn, i0, in; int mat; }; std::vector<MR> mr(rd.u());
  for (auto& m : mr) { m.v0 = rd.u(); m.vn = rd.u(); m.i0 = rd.u(); m.in = rd.u(); m.mat = rd.i(); }
  std::vector<Vertex> verts(rd.u()); rd.raw(verts.data(), verts.size() * sizeof(Vertex));
  std::vector<uint32_t> idx(rd.u()); rd.raw(idx.data(), idx.size() * 4);
  if (rd.bad) return false;
  for (auto& n : nodes) {
    if (n.mesh < 0 || n.mesh >= (int)mr.size()) continue; const MR& m = mr[n.mesh]; Mesh out1;
    out1.v.assign(verts.begin() + m.v0, verts.begin() + m.v0 + m.vn);
    for (uint32_t k = 0; k < m.in; k++) out1.idx.push_back(idx[m.i0 + k] - m.v0);
    out1.transform(0, Mat4::trs(n.t, n.r, n.s));
    out.push_back({n.name, std::move(out1)});
  }
  return true;
}

bool ModelAsset::load(const std::string& assetName, Renderer& R) {
  std::vector<uint8_t> data;
  if (!readAsset(assetName, data)) { std::fprintf(stderr, "DOW: missing asset %s\n", assetName.c_str()); return false; }
  Reader rd(data); char magic[4]; rd.raw(magic, 4); if (std::memcmp(magic, "DOWM", 4) || rd.u() != 1) return false;
  nodes.resize(rd.u());
  for (auto& n : nodes) { n.name = rd.name(); n.parent = rd.i(); n.mesh = rd.i(); n.t = {rd.f(), rd.f(), rd.f()}; n.r = {rd.f(), rd.f(), rd.f(), rd.f()}; n.s = {rd.f(), rd.f(), rd.f()}; }
  struct MR { uint32_t v0, vn, i0, in; int mat; }; std::vector<MR> mr(rd.u());
  for (auto& m : mr) { m.v0 = rd.u(); m.vn = rd.u(); m.i0 = rd.u(); m.in = rd.u(); m.mat = rd.i(); }
  std::vector<Vertex> verts(rd.u()); rd.raw(verts.data(), verts.size() * sizeof(Vertex));
  std::vector<uint32_t> idx(rd.u()); rd.raw(idx.data(), idx.size() * 4);
  uint32_t nm = rd.u(); for (uint32_t k = 0; k < nm; k++) { matTex.push_back(rd.i()); for (int q = 0; q < 6; q++) rd.f(); }
  uint32_t nt = rd.u();
  for (uint32_t k = 0; k < nt; k++) { Image im; im.w = (int)rd.u(); im.h = (int)rd.u(); im.px.resize((size_t)im.w * im.h * 4); rd.raw(im.px.data(), im.px.size()); tex.push_back(rd.bad ? 0 : R.makeTexture(im, true, false)); }
  anims.resize(rd.u());
  for (auto& a : anims) {
    a.name = rd.name(); a.duration = rd.f(); a.ch.resize(rd.u());
    for (auto& c : a.ch) { c.node = rd.i(); c.path = (int)rd.u(); uint32_t n = rd.u(); c.times.resize(n); for (auto& t : c.times) t = rd.f();
      int comp = c.path == 1 ? 4 : 3; c.values.resize((size_t)n * comp); for (auto& v : c.values) v = rd.f(); }
  }
  if (rd.bad) { std::fprintf(stderr, "DOW: corrupt asset %s\n", assetName.c_str()); return false; }
  meshes.resize(mr.size());
  for (size_t k = 0; k < mr.size(); k++) {
    Mesh m; m.v.assign(verts.begin() + mr[k].v0, verts.begin() + mr[k].v0 + mr[k].vn); m.idx.assign(idx.begin() + mr[k].i0, idx.begin() + mr[k].i0 + mr[k].in);
    meshes[k].upload(m); meshMat.push_back(mr[k].mat);
  }
  world.resize(nodes.size()); resetPose(); computeWorld(); loaded = true; return true;
}

int ModelAsset::anim(const std::string& n) const { for (size_t i = 0; i < anims.size(); i++) if (anims[i].name == n) return (int)i; return -1; }
int ModelAsset::node(const std::string& n) const { for (size_t i = 0; i < nodes.size(); i++) if (nodes[i].name == n) return (int)i; return -1; }

void ModelAsset::resetPose() {
  pt.resize(nodes.size()); pr.resize(nodes.size()); ps.resize(nodes.size());
  for (size_t i = 0; i < nodes.size(); i++) { pt[i] = nodes[i].t; pr[i] = nodes[i].r; ps[i] = nodes[i].s; }
}

void ModelAsset::apply(int ai, float time, bool loop) {
  if (ai < 0) return; const ModelAnim& a = anims[ai];
  if (loop && a.duration > 0) { time = std::fmod(time, a.duration); if (time < 0) time += a.duration; }
  time = clampf(time, 0, a.duration);
  for (const auto& c : a.ch) {
    size_t n = c.times.size(); if (!n) continue; size_t k = 0; while (k + 1 < n && c.times[k + 1] <= time) k++;
    size_t k2 = std::min(k + 1, n - 1); float t0 = c.times[k], t1 = c.times[k2], u = t1 > t0 ? clampf((time - t0) / (t1 - t0), 0, 1) : 0;
    if (c.path == 1) { const float* A = &c.values[k * 4]; const float* B = &c.values[k2 * 4]; pr[c.node] = slerp(Quat{A[0], A[1], A[2], A[3]}, Quat{B[0], B[1], B[2], B[3]}, u); }
    else { const float* A = &c.values[k * 3]; const float* B = &c.values[k2 * 3]; Vec3 v = lerp(Vec3{A[0], A[1], A[2]}, Vec3{B[0], B[1], B[2]}, u); if (c.path == 0) pt[c.node] = v; else ps[c.node] = v; }
  }
}

void ModelAsset::computeWorld() {
  // glTF lists parents before or after children; resolve recursively with a done-flag
  std::vector<char> done(nodes.size(), 0);
  for (size_t i = 0; i < nodes.size(); i++) {
    std::vector<int> chain; int k = (int)i; while (k >= 0 && !done[k]) { chain.push_back(k); k = nodes[k].parent; }
    for (int q = (int)chain.size() - 1; q >= 0; q--) { int n = chain[q]; Mat4 local = Mat4::trs(pt[n], pr[n], ps[n]); world[n] = nodes[n].parent >= 0 ? world[nodes[n].parent] * local : local; done[n] = 1; }
  }
}

void ModelAsset::draw(Renderer& R, const Mat4& model, Vec4 tint) {
  for (size_t i = 0; i < nodes.size(); i++) {
    int m = nodes[i].mesh; if (m < 0 || m >= (int)meshes.size()) continue;
    int mat = meshMat[m]; GLuint t = (mat >= 0 && matTex[mat] >= 0 && matTex[mat] < (int)tex.size()) ? tex[matTex[mat]] : 0;
    R.add(meshes[m], model * world[i], tint, t ? MODE_TEX : MODE_LIT, t);
  }
}

}  // namespace dow
