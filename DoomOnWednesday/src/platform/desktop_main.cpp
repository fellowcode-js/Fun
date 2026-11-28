// Headless desktop host: same game + renderer as the Quest build, driven by scripted "VR" input.
// Used for CI-style checks and screenshots:   dow_desktop shots <out_dir>   |   dow_desktop hash <code>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <cmath>
#include "../render/scene.h"
#include "../game/layout.h"

using namespace dow;

// ------------------------------------------------------------------ tiny PNG writer (stored deflate)
static uint32_t crcTable[256];
static void crcInit() { for (uint32_t n = 0; n < 256; n++) { uint32_t c = n; for (int k = 0; k < 8; k++) c = c & 1 ? 0xedb88320u ^ (c >> 1) : c >> 1; crcTable[n] = c; } }
static uint32_t crc(const uint8_t* b, size_t n, uint32_t c = 0xffffffffu) { for (size_t i = 0; i < n; i++) c = crcTable[(c ^ b[i]) & 0xff] ^ (c >> 8); return c; }
static void be32(std::vector<uint8_t>& o, uint32_t v) { o.push_back(v >> 24); o.push_back(v >> 16); o.push_back(v >> 8); o.push_back(v); }
static void chunk(std::vector<uint8_t>& o, const char* t, const std::vector<uint8_t>& d) {
  be32(o, (uint32_t)d.size()); size_t s = o.size(); o.insert(o.end(), t, t + 4); o.insert(o.end(), d.begin(), d.end());
  be32(o, crc(&o[s], d.size() + 4) ^ 0xffffffffu);
}
static bool writePNG(const std::string& path, int w, int h, const std::vector<uint8_t>& rgba) {
  crcInit(); std::vector<uint8_t> raw; raw.reserve((size_t)(w * 3 + 1) * h);
  for (int y = h - 1; y >= 0; y--) { raw.push_back(0); for (int x = 0; x < w; x++) { const uint8_t* p = &rgba[(y * w + x) * 4]; raw.push_back(p[0]); raw.push_back(p[1]); raw.push_back(p[2]); } }
  std::vector<uint8_t> z = {0x78, 0x01}; uint32_t a = 1, b = 0;
  for (size_t i = 0; i < raw.size(); i += 65535) {
    size_t n = std::min<size_t>(65535, raw.size() - i); z.push_back(i + n >= raw.size() ? 1 : 0);
    z.push_back(n & 0xff); z.push_back(n >> 8); z.push_back(~n & 0xff); z.push_back((~n >> 8) & 0xff);
    z.insert(z.end(), raw.begin() + i, raw.begin() + i + n);
  }
  for (uint8_t c : raw) { a = (a + c) % 65521; b = (b + a) % 65521; } be32(z, (b << 16) | a);
  std::vector<uint8_t> o = {0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a}, ih; be32(ih, w); be32(ih, h); ih.push_back(8); ih.push_back(2); ih.push_back(0); ih.push_back(0); ih.push_back(0);
  chunk(o, "IHDR", ih); chunk(o, "IDAT", z); chunk(o, "IEND", {});
  FILE* f = std::fopen(path.c_str(), "wb"); if (!f) return false; std::fwrite(o.data(), 1, o.size(), f); std::fclose(f); return true;
}

// ------------------------------------------------------------------ EGL / FBO
struct Target { GLuint fboMS = 0, fbo = 0, colMS = 0, depMS = 0, col = 0; int w, h; };
static bool initEGL() {
  EGLDisplay d = eglGetDisplay(EGL_DEFAULT_DISPLAY);
  if (!eglInitialize(d, nullptr, nullptr)) { std::fprintf(stderr, "eglInitialize failed\n"); return false; }
  eglBindAPI(EGL_OPENGL_ES_API);
  EGLint ca[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_DEPTH_SIZE, 24, EGL_NONE};
  EGLConfig cfg; EGLint n = 0; eglChooseConfig(d, ca, &cfg, 1, &n); if (n < 1) { std::fprintf(stderr, "no EGL config\n"); return false; }
  EGLint pa[] = {EGL_WIDTH, 16, EGL_HEIGHT, 16, EGL_NONE}; EGLSurface s = eglCreatePbufferSurface(d, cfg, pa);
  EGLint cx[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE}; EGLContext c = eglCreateContext(d, cfg, EGL_NO_CONTEXT, cx);
  if (!c || !eglMakeCurrent(d, s, s, c)) { std::fprintf(stderr, "EGL context failed\n"); return false; }
  std::printf("GL: %s | %s\n", glGetString(GL_RENDERER), glGetString(GL_VERSION));
  return true;
}
static Target makeTarget(int w, int h) {
  Target t; t.w = w; t.h = h;
  glGenRenderbuffers(1, &t.colMS); glBindRenderbuffer(GL_RENDERBUFFER, t.colMS); glRenderbufferStorageMultisample(GL_RENDERBUFFER, 4, GL_SRGB8_ALPHA8, w, h);
  glGenRenderbuffers(1, &t.depMS); glBindRenderbuffer(GL_RENDERBUFFER, t.depMS); glRenderbufferStorageMultisample(GL_RENDERBUFFER, 4, GL_DEPTH_COMPONENT24, w, h);
  glGenFramebuffers(1, &t.fboMS); glBindFramebuffer(GL_FRAMEBUFFER, t.fboMS);
  glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, t.colMS); glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, t.depMS);
  glGenRenderbuffers(1, &t.col); glBindRenderbuffer(GL_RENDERBUFFER, t.col); glRenderbufferStorage(GL_RENDERBUFFER, GL_SRGB8_ALPHA8, w, h);
  glGenFramebuffers(1, &t.fbo); glBindFramebuffer(GL_FRAMEBUFFER, t.fbo); glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, t.col);
  return t;
}

// ------------------------------------------------------------------ scripted rig
struct Sim {
  Game g; Scene sc; Input in; Target tgt;
  void baseInput(float yaw = 0) {
    in = Input{}; in.dt = 1 / 72.f; in.head.p = {0, 1.6f, 0}; in.head.q = Quat::yaw(yaw); in.head.valid = true;
    Quat hold = Quat::yaw(yaw) * Quat::axisAngle({1, 0, 0}, -0.35f);
    in.hand[0].p = Vec3{0, 1.6f, 0} + Quat::yaw(yaw).rotate({-0.25f, -0.75f, -0.18f}); in.hand[1].p = Vec3{0, 1.6f, 0} + Quat::yaw(yaw).rotate({0.25f, -0.75f, -0.18f});
    in.hand[0].q = in.hand[1].q = hold; in.hand[0].valid = in.hand[1].valid = true;
  }
  void steps(int n, float dt = 1 / 72.f) { for (int i = 0; i < n; i++) { in.dt = dt; g.update(in); } }
  void shot(const std::string& path, const Vec3& eye, const Vec3& look, float fovDeg = 75) {
    sc.resetBody(); sc.build(g, in, 1 / 72.f);
    glBindFramebuffer(GL_FRAMEBUFFER, tgt.fboMS); glViewport(0, 0, tgt.w, tgt.h);
    glClearColor(sc.R.fogColor.x, sc.R.fogColor.y, sc.R.fogColor.z, 1); glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    Quat q = lookRotation(look - eye, {0, 1, 0});
    Mat4 view = Mat4::viewFromPose(eye, q), proj = Mat4::perspective(fovDeg * PI / 180, (float)tgt.w / tgt.h, 0.03f, 60);
    sc.render(view, proj, eye);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, tgt.fboMS); glBindFramebuffer(GL_DRAW_FRAMEBUFFER, tgt.fbo);
    glBlitFramebuffer(0, 0, tgt.w, tgt.h, 0, 0, tgt.w, tgt.h, GL_COLOR_BUFFER_BIT, GL_NEAREST);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, tgt.fbo);
    std::vector<uint8_t> px((size_t)tgt.w * tgt.h * 4); glReadPixels(0, 0, tgt.w, tgt.h, GL_RGBA, GL_UNSIGNED_BYTE, px.data());
    writePNG(path, tgt.w, tgt.h, px); std::printf("wrote %s (%d draws, glError 0x%x, px0 %d %d %d, fb 0x%x)\n", path.c_str(), sc.R.drawCalls(), glGetError(), px[0], px[1], px[2], glCheckFramebufferStatus(GL_READ_FRAMEBUFFER));
  }
};

static int shots(const std::string& out) {
  if (!initEGL()) return 1;
  Sim s; if (!s.sc.init()) return 1; s.tgt = makeTarget(1280, 720);
  s.g.init(); s.baseInput(); s.steps(120);
  Game& g = s.g; s.sc.showLocalBody = true; s.sc.showLocalHead = true;

  // 1. lobby overview
  s.shot(out + "/01_lobby.png", {-5.8f, 2.25f, -5.9f}, {2.5f, 0.7f, 3.0f}, 80);

  // 2. first-person: both hands raised in front, palms facing each other, then a curled grip on the right
  s.sc.showLocalBody = false; s.sc.showLocalHead = false;
  s.baseInput(PI); s.in.hand[0].p = {0.2f, 1.35f, 0.42f}; s.in.hand[1].p = {-0.2f, 1.35f, 0.42f};
  s.in.hand[0].q = s.in.hand[1].q = Quat::yaw(PI) * Quat::axisAngle({1, 0, 0}, 0.2f); s.in.grip[1] = 0.9f;
  s.g.loco.teleport({0, 0, -1.0f}, s.in.head); s.steps(40);
  { Vec3 e = g.loco.headW; s.shot(out + "/02_first_person_hands.png", e, e + Quat::yaw(PI).rotate(Vec3{0, -0.28f, -1}), 90); }

  s.sc.showLocalBody = true; s.sc.showLocalHead = true;
  // 3. form statues
  s.g.loco.teleport({3.4f, 0, -1.2f}, s.in.head); s.baseInput(); s.steps(30);
  s.shot(out + "/03_forms.png", {3.0f, 1.55f, -1.25f}, {6.55f, 1.05f, -1.25f}, 85);

  // 4. robot chainsaw slicing a dummy (third person)
  s.g.setForm(FORM_ROBOT); s.g.role = 2;
  s.g.loco.teleport({-4.2f, 0, 1.6f}, s.in.head); s.baseInput(); s.steps(200);
  s.g.spawnBot(0, {-4.2f, 0, 0.75f});
  s.in.a = true; s.steps(2); s.in.a = false; s.steps(100);  // transform to saw (1.2 s)
  for (int i = 0; i < 26; i++) { float t = i / 25.f; s.in.hand[1].p = Vec3{0.55f - 0.9f * t, 1.15f, -0.55f}; s.in.hand[1].q = Quat::axisAngle({0, 0, 1}, -0.2f); s.steps(1); }
  s.steps(14);
  { Vec3 h = g.loco.headW; s.shot(out + "/04_chainsaw.png", h + Vec3{-1.7f, 0.5f, -1.5f}, h + Vec3{0.1f, -0.55f, -0.55f}, 70); }

  // 5. monster rips a runner apart, blood on the carpet
  s.g.clearBots(); s.g.setForm(FORM_MONSTER); s.steps(120);
  s.g.loco.teleport({4.2f, 0, 2.2f}, s.in.head); s.baseInput(); s.steps(30);
  s.g.spawnBot(0, {4.2f, 0, 2.95f}); s.steps(4);
  { Bot& b = s.g.bots[0]; Vec3 head = b.p + Vec3{0, 0.8f, 0}; Vec3 off = head - g.loco.rig; off = Quat::yaw(-g.loco.yaw).rotate(off) / g.loco.scale;
    s.in.hand[1].p = off; s.steps(30); s.in.grip[1] = 1; s.steps(3); s.in.grip[1] = 0; s.in.hand[1].p = {0.3f, 1.3f, 0.2f}; s.steps(50); }
  { Vec3 h = g.loco.headW; s.shot(out + "/05_monster_rip.png", h + Vec3{1.3f, 0.3f, -0.6f}, h + Vec3{-0.2f, -0.6f, 1.0f}, 75); }

  // 6. mod den: Mushroom OS (owner) + keypad
  s.g.clearBots(); s.g.setForm(FORM_GORILLA); s.g.role = 2; s.g.osPage = 1; s.g.platformsOn = true; s.g.lightsDim = false; s.steps(150);
  s.g.loco.teleport({-11.5f, 0, 0.6f}, s.in.head); s.baseInput(PI / 2); s.steps(30);
  s.shot(out + "/06_mod_den.png", {-10.4f, 1.6f, 1.4f}, {-13.1f, 1.25f, -0.2f}, 80);
  s.g.osPage = 0;

  // 7. the backrooms maze
  s.g.loco.teleport({-15.f, 0, -9.f}, s.in.head); s.baseInput(); s.steps(30);
  s.shot(out + "/07_backrooms.png", {-21.0f, 1.5f, -9.0f}, {-14.0f, 1.2f, -9.6f}, 80);

  s.sc.showLocalBody = false; s.sc.showLocalHead = false;
  // 8. hands close-up from the side (orientation check): left + right, palms in, thumbs up
  s.g.loco.teleport({0, 0, -1.0f}, s.in.head); s.baseInput(PI); s.in.hand[0].p = {0.17f, 1.3f, 0.45f}; s.in.hand[1].p = {-0.17f, 1.3f, 0.45f};
  s.in.hand[0].q = s.in.hand[1].q = Quat::yaw(PI); s.in.grip[0] = 0; s.in.grip[1] = 0.6f; s.steps(30);
  { Vec3 c = (g.loco.hand[0].phys + g.loco.hand[1].phys) * 0.5f; s.shot(out + "/08_hands_closeup.png", c + Vec3{0.0f, 0.12f, 0.55f}, c, 60); }
  return 0;
}

int main(int argc, char** argv) {
  if (argc >= 3 && std::string(argv[1]) == "hash") { std::printf("%s\n", sha256hex(sha256hex(argv[2])).c_str()); return 0; }
  if (argc >= 3 && std::string(argv[1]) == "shots") return shots(argv[2]);
  std::printf("usage: dow_desktop shots <dir> | hash <code>\n"); return 2;
}
