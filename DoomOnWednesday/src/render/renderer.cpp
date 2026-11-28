#include "renderer.h"
#include <cstdio>
#include <cstring>

namespace dow {

static const char* VS = R"(#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec3 aNrm; layout(location=2) in vec2 aUV;
layout(location=3) in vec4 aCol; layout(location=4) in vec4 aMat;
layout(location=5) in vec4 iM0; layout(location=6) in vec4 iM1; layout(location=7) in vec4 iM2; layout(location=8) in vec4 iM3;
layout(location=9) in vec4 iCol;
uniform mat4 uViewProj; uniform mat4 uHalf; uniform vec4 uClip;
out vec3 vW; out vec3 vN; out vec2 vUV; out vec4 vCol; out vec4 vMat; out vec4 vICol; out float vClip;
void main() {
  mat4 M = mat4(iM0, iM1, iM2, iM3);
  vec4 w = M * vec4(aPos, 1.0);
  vClip = dot(uClip.xyz, w.xyz) + uClip.w;
  w = uHalf * w;
  vN = mat3(uHalf) * (mat3(M) * aNrm);
  vW = w.xyz; vUV = aUV; vCol = aCol; vMat = aMat; vICol = iCol;
  gl_Position = uViewProj * w;
})";

static const char* FS = R"(#version 300 es
precision mediump float;
in vec3 vW; in vec3 vN; in vec2 vUV; in vec4 vCol; in vec4 vMat; in vec4 vICol; in float vClip;
uniform sampler2D uTex; uniform int uMode; uniform vec3 uFur; uniform vec3 uCam;
uniform vec3 uFogCol; uniform vec2 uFog; uniform vec3 uAmb; uniform vec3 uSky; uniform vec3 uGnd;
uniform vec4 uLP[8]; uniform vec4 uLC[8]; uniform int uNL; uniform float uFlesh;
out vec4 oColor;
// sine-free hash in highp: mediump is real fp16 on Quest GPUs and sin()-hashes overflow there
float h21(highp vec2 p) { highp vec2 q = fract(p * vec2(0.1031, 0.1030)); q += dot(q, q.yx + 33.33); return fract((q.x + q.y) * q.x); }
void main() {
  if (vClip < 0.0) discard;
  vec3 base = vCol.rgb * vICol.rgb;
  if (vMat.r > 0.5) {                      // fur: tinted, with procedural strands so it never reads as plastic
    highp vec2 g = floor(vUV * vec2(150.0, 260.0)); float s = h21(g), s2 = h21(floor(vUV * vec2(40.0, 70.0)));
    base = uFur * vCol.rgb * 2.0 * (0.88 + 0.2 * s) * (0.94 + 0.1 * s2);
  }
  base = base * base;                       // vertex colours are authored in sRGB; ~gamma 2 to linear
  float em = vCol.a + vICol.a;
  if (uMode == 2) {                         // pixel-font text, unlit
    vec4 t = texture(uTex, vUV); if (t.a < 0.5) discard;
    oColor = vec4(base * (0.25 + em), 1.0); return;
  }
  if (uMode == 3) {                         // blood splat: irregular disc from UVs
    vec2 q = vUV * 2.0 - 1.0; float a = atan(q.y, q.x), r = length(q);
    float edge = 0.7 + 0.18 * sin(a * 5.0 + vICol.a * 30.0) + 0.1 * sin(a * 11.0 + vICol.a * 17.0);
    float drops = step(0.93, h21(floor((q + 2.0) * 9.0) + vICol.a)) * step(r, 1.0);
    float m = max(1.0 - smoothstep(edge - 0.08, edge, r), drops);
    if (m < 0.02) discard;
    vec3 c = vec3(0.22, 0.01, 0.01) * (0.7 + 0.3 * (1.0 - r));
    float f = clamp((length(vW - uCam) - uFog.x) / (uFog.y - uFog.x), 0.0, 1.0);
    oColor = vec4(mix(c, uFogCol, f), m * 0.92); return;
  }
  if (uMode == 1) base *= texture(uTex, vUV).rgb;
  vec3 N = normalize(vN);
  if (!gl_FrontFacing) { N = -N; if (uFlesh > 0.5) { base = vec3(0.30, 0.015, 0.015); em = 0.05; } }
  vec3 L = uAmb + mix(uGnd, uSky, N.y * 0.5 + 0.5);
  for (int i = 0; i < 8; i++) {
    if (i >= uNL) break;
    vec3 d = uLP[i].xyz - vW; float dist = length(d);
    float att = clamp(1.0 - dist / uLP[i].w, 0.0, 1.0); att *= att;
    float ndl = clamp(dot(N, d / max(dist, 1e-3)) * 0.85 + 0.15, 0.0, 1.0);
    L += uLC[i].rgb * (att * ndl);
  }
  vec3 c = base * L + base * em * 1.6;
  if (uMode == 4) c = base * (0.6 + em * 1.6);
  float f = clamp((length(vW - uCam) - uFog.x) / (uFog.y - uFog.x), 0.0, 1.0);
  c = mix(c, uFogCol, f * (1.0 - clamp(em, 0.0, 1.0) * 0.6));
  oColor = vec4(c, 1.0);
})";

static GLuint compile(GLenum type, const char* src) {
  GLuint s = glCreateShader(type); glShaderSource(s, 1, &src, nullptr); glCompileShader(s);
  GLint ok = 0; glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
  if (!ok) { char log[2048]; glGetShaderInfoLog(s, sizeof log, nullptr, log); std::fprintf(stderr, "DOW shader error: %s\n", log); }
  return s;
}

void GpuMesh::upload(const Mesh& m, bool dynamic) {
  if (!vao) { glGenVertexArrays(1, &vao); glGenBuffers(1, &vbo); glGenBuffers(1, &ibo); }
  glBindVertexArray(vao);
  glBindBuffer(GL_ARRAY_BUFFER, vbo);
  size_t vb = m.v.size() * sizeof(Vertex), ib = m.idx.size() * sizeof(uint32_t);
  if (vb > vcap || !dynamic) { glBufferData(GL_ARRAY_BUFFER, std::max<size_t>(vb, 64), m.v.empty() ? nullptr : m.v.data(), dynamic ? GL_DYNAMIC_DRAW : GL_STATIC_DRAW); vcap = vb; }
  else if (vb) glBufferSubData(GL_ARRAY_BUFFER, 0, vb, m.v.data());
  glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo);
  if (ib > icap || !dynamic) { glBufferData(GL_ELEMENT_ARRAY_BUFFER, std::max<size_t>(ib, 64), m.idx.empty() ? nullptr : m.idx.data(), dynamic ? GL_DYNAMIC_DRAW : GL_STATIC_DRAW); icap = ib; }
  else if (ib) glBufferSubData(GL_ELEMENT_ARRAY_BUFFER, 0, ib, m.idx.data());
  const GLsizei st = sizeof(Vertex);
  glEnableVertexAttribArray(0); glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, st, (void*)0);
  glEnableVertexAttribArray(1); glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, st, (void*)12);
  glEnableVertexAttribArray(2); glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, st, (void*)24);
  glEnableVertexAttribArray(3); glVertexAttribPointer(3, 4, GL_UNSIGNED_BYTE, GL_TRUE, st, (void*)32);
  glEnableVertexAttribArray(4); glVertexAttribPointer(4, 4, GL_UNSIGNED_BYTE, GL_TRUE, st, (void*)36);
  glBindVertexArray(0);
  count = (int)m.idx.size();
}

Instance makeInst(const Mat4& m, Vec4 c) { Instance i; std::memcpy(i.m, m.m, sizeof i.m); i.col[0] = c.x; i.col[1] = c.y; i.col[2] = c.z; i.col[3] = c.w; return i; }

GLuint Renderer::makeTexture(const Image& im, bool mips, bool nearestMag) {
  GLuint t; glGenTextures(1, &t); glBindTexture(GL_TEXTURE_2D, t);
  glTexImage2D(GL_TEXTURE_2D, 0, GL_SRGB8_ALPHA8, im.w, im.h, 0, GL_RGBA, GL_UNSIGNED_BYTE, im.px.data());
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT); glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, nearestMag ? GL_NEAREST : GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, mips ? GL_LINEAR_MIPMAP_LINEAR : GL_LINEAR);
  if (mips) glGenerateMipmap(GL_TEXTURE_2D);
#ifdef GL_TEXTURE_MAX_ANISOTROPY_EXT
  const char* ext = (const char*)glGetString(GL_EXTENSIONS);
  if (mips && ext && std::strstr(ext, "texture_filter_anisotropic")) glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY_EXT, 4.f);
#endif
  return t;
}

bool Renderer::init() {
  prog = glCreateProgram(); GLuint vs = compile(GL_VERTEX_SHADER, VS), fs = compile(GL_FRAGMENT_SHADER, FS);
  glAttachShader(prog, vs); glAttachShader(prog, fs); glLinkProgram(prog);
  GLint ok = 0; glGetProgramiv(prog, GL_LINK_STATUS, &ok);
  if (!ok) { char log[2048]; glGetProgramInfoLog(prog, sizeof log, nullptr, log); std::fprintf(stderr, "DOW link error: %s\n", log); return false; }
  glDeleteShader(vs); glDeleteShader(fs);
#define U(n) n = glGetUniformLocation(prog, #n)
  U(uViewProj); U(uHalf); U(uClip); U(uTex); U(uMode); U(uFur); U(uCam); U(uFogCol); U(uFog); U(uAmb); U(uSky); U(uGnd); U(uLP); U(uLC); U(uNL); U(uFlesh); U(uTime);
#undef U
  glGenBuffers(1, &instVbo);
  texWall = makeTexture(makeWallpaper(), true, false);
  texCarpet = makeTexture(makeCarpet(), true, false);
  texCeil = makeTexture(makeCeiling(), true, false);
  texFont = makeTexture(makeFontAtlas(), true, true);
  tex[0] = texWall; tex[1] = texCarpet; tex[2] = texCeil;
  tex[3] = makeTexture(makeTiles(), true, false); tex[4] = makeTexture(makeConcrete(), true, false);
  tex[5] = makeTexture(makeWood(), true, false); tex[6] = makeTexture(makePlanks(), true, false);
  Image w; w.w = w.h = 2; w.px.assign(16, 255); texWhite = makeTexture(w, false, false);
  return true;
}

void Renderer::begin() { items.clear(); inst.clear(); }

DrawItem& Renderer::addItem(const GpuMesh& m, const Mat4& model, Vec4 col) {
  DrawItem d; d.mesh = &m; d.inst0 = (int)inst.size(); d.instN = 1; inst.push_back(makeInst(model, col)); items.push_back(d); return items.back();
}

void Renderer::add(const GpuMesh& m, const Mat4& model, Vec4 col, int mode, GLuint tex, Vec3 fur) {
  if (!m.ok()) return;
  DrawItem& d = addItem(m, model, col); d.mode = mode; d.tex = tex; d.fur = fur;
}

void Renderer::addInstanced(const GpuMesh& m, const std::vector<Instance>& in, int mode, bool blend) {
  if (in.empty() || !m.ok()) return;
  DrawItem d; d.mesh = &m; d.mode = mode; d.inst0 = (int)inst.size(); d.instN = (int)in.size(); d.blend = blend; d.depthWrite = !blend;
  inst.insert(inst.end(), in.begin(), in.end()); items.push_back(d);
}

void Renderer::finish() {
  glBindBuffer(GL_ARRAY_BUFFER, instVbo);
  size_t bytes = inst.size() * sizeof(Instance);
  if (bytes > instCap) { instCap = bytes * 2; glBufferData(GL_ARRAY_BUFFER, instCap, nullptr, GL_STREAM_DRAW); }
  if (bytes) glBufferSubData(GL_ARRAY_BUFFER, 0, bytes, inst.data());
  // draw opaque first, blended last (stable)
  std::stable_sort(items.begin(), items.end(), [](const DrawItem& a, const DrawItem& b) { return a.blend < b.blend; });
}

void Renderer::renderEye(const Mat4& view, const Mat4& proj, const Vec3& eye) {
  glUseProgram(prog);
  Mat4 vp = proj * view; glUniformMatrix4fv(uViewProj, 1, GL_FALSE, vp.m);
  glUniform3f(uCam, eye.x, eye.y, eye.z);
  glUniform3f(uFogCol, fogColor.x, fogColor.y, fogColor.z); glUniform2f(uFog, fogNear, fogFar);
  glUniform3f(uAmb, ambient.x, ambient.y, ambient.z); glUniform3f(uSky, sky.x, sky.y, sky.z); glUniform3f(uGnd, ground.x, ground.y, ground.z);
  glUniform4fv(uLP, 8, &lights.pos[0].x); glUniform4fv(uLC, 8, &lights.col[0].x); glUniform1i(uNL, lights.n);
  glUniform1i(uTex, 0); glActiveTexture(GL_TEXTURE0);
  glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LEQUAL);
  int lastMode = -1; GLuint lastTex = (GLuint)-1; bool lastBlend = false, lastCull = true, lastDW = true; glDisable(GL_BLEND); glEnable(GL_CULL_FACE); glCullFace(GL_BACK); glDepthMask(GL_TRUE);
  Mat4 ident; glUniformMatrix4fv(uHalf, 1, GL_FALSE, ident.m); glUniform4f(uClip, 0, 0, 0, 1); glUniform1f(uFlesh, 0);
  bool special = false;
  glBindBuffer(GL_ARRAY_BUFFER, instVbo);
  for (const DrawItem& d : items) {
    if (d.mode != lastMode) { glUniform1i(uMode, d.mode); lastMode = d.mode; }
    GLuint t = d.tex ? d.tex : texWhite; if (t != lastTex) { glBindTexture(GL_TEXTURE_2D, t); lastTex = t; }
    if (d.blend != lastBlend) { if (d.blend) { glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA); } else glDisable(GL_BLEND); lastBlend = d.blend; }
    if (d.cull != lastCull) { if (d.cull) glEnable(GL_CULL_FACE); else glDisable(GL_CULL_FACE); lastCull = d.cull; }
    if (d.depthWrite != lastDW) { glDepthMask(d.depthWrite ? GL_TRUE : GL_FALSE); lastDW = d.depthWrite; }
    glUniform3f(uFur, d.fur.x, d.fur.y, d.fur.z);
    bool sp = d.clip.x != 0 || d.clip.y != 0 || d.clip.z != 0 || d.flesh;
    if (sp || special) { glUniformMatrix4fv(uHalf, 1, GL_FALSE, d.half.m); glUniform4f(uClip, d.clip.x, d.clip.y, d.clip.z, d.clip.w); glUniform1f(uFlesh, d.flesh ? 1.f : 0.f); special = sp; }
    glBindVertexArray(d.mesh->vao);
    size_t base = (size_t)d.inst0 * sizeof(Instance);
    for (int k = 0; k < 5; k++) {
      glEnableVertexAttribArray(5 + k);
      glVertexAttribPointer(5 + k, 4, GL_FLOAT, GL_FALSE, sizeof(Instance), (void*)(base + k * 16));
      glVertexAttribDivisor(5 + k, 1);
    }
    glDrawElementsInstanced(GL_TRIANGLES, d.mesh->count, GL_UNSIGNED_INT, nullptr, d.instN);
  }
  glBindVertexArray(0); glDepthMask(GL_TRUE); glDisable(GL_BLEND); glEnable(GL_CULL_FACE);
}

}  // namespace dow
