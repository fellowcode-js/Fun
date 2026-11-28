// Quest (standalone) host: NativeActivity + OpenXR + EGL/GLES3. No engine, no Java code.
// Hands use the OpenXR *grip* pose, so the hand models sit exactly where your real hands are and the
// left hand is a true mirror of the right one (the web build's flipped/inverted hands are gone).
#include <android_native_app_glue.h>
#include <android/log.h>
#include <android/asset_manager.h>
#include <jni.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <GLES2/gl2ext.h>
#define XR_USE_PLATFORM_ANDROID
#define XR_USE_GRAPHICS_API_OPENGL_ES
#include <openxr/openxr.h>
#include <openxr/openxr_platform.h>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>
#include "../render/scene.h"
#include "../audio/synth.h"
#include "../core/assets.h"

using namespace dow;

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, "DOW", __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, "DOW", __VA_ARGS__)
#define XRC(x) do { XrResult r_ = (x); if (XR_FAILED(r_)) { LOGE("%s failed: %d (line %d)", #x, (int)r_, __LINE__); } } while (0)

typedef void (*PFNGLFRAMEBUFFERTEXTURE2DMULTISAMPLEEXTPROC_)(GLenum, GLenum, GLenum, GLuint, GLint, GLsizei);
typedef void (*PFNGLRENDERBUFFERSTORAGEMULTISAMPLEEXTPROC_)(GLenum, GLsizei, GLenum, GLsizei, GLsizei);

struct EyeChain {
  XrSwapchain sc = XR_NULL_HANDLE; int w = 0, h = 0;
  std::vector<XrSwapchainImageOpenGLESKHR> imgs; std::vector<GLuint> fbos; GLuint depth = 0;
};

struct App {
  android_app* app = nullptr;
  bool resumed = false, running = false, focused = false, quit = false;
  XrInstance inst = XR_NULL_HANDLE; XrSystemId sys = XR_NULL_SYSTEM_ID; XrSession session = XR_NULL_HANDLE;
  XrSessionState state = XR_SESSION_STATE_UNKNOWN;
  XrSpace stage = XR_NULL_HANDLE, view = XR_NULL_HANDLE; bool stageIsLocal = false;
  EGLDisplay dpy = EGL_NO_DISPLAY; EGLConfig cfg = nullptr; EGLContext ctx = EGL_NO_CONTEXT; EGLSurface surf = EGL_NO_SURFACE;
  EyeChain eye[2]; int msaa = 0;
  PFNGLFRAMEBUFFERTEXTURE2DMULTISAMPLEEXTPROC_ fbTexMS = nullptr; PFNGLRENDERBUFFERSTORAGEMULTISAMPLEEXTPROC_ rbMS = nullptr;
  XrActionSet set = XR_NULL_HANDLE;
  XrAction aGrip, aTrigger, aPrimary, aSecondary, aStick, aPose, aHaptic;
  XrPath hand[2]; XrSpace gripSpace[2] = {XR_NULL_HANDLE, XR_NULL_HANDLE};
  bool hasRefresh = false; PFN_xrRequestDisplayRefreshRateFB requestRefresh = nullptr;
  Game game; Scene scene; Synth synth; Input in;
  XrTime lastTime = 0;
};
static App A;

// Game data (the original chainsaw hand model) ships inside the APK's assets/ folder.
static bool apkAsset(const std::string& name, std::vector<uint8_t>& out) {
  AAsset* a = AAssetManager_open(A.app->activity->assetManager, name.c_str(), AASSET_MODE_BUFFER);
  if (!a) { LOGE("asset %s not found", name.c_str()); return false; }
  size_t n = (size_t)AAsset_getLength(a); out.resize(n); bool ok = AAsset_read(a, out.data(), n) == (int)n; AAsset_close(a); return ok;
}

static XrPath path(const char* s) { XrPath p = XR_NULL_PATH; xrStringToPath(A.inst, s, &p); return p; }

static Pose toPose(const XrPosef& p, bool valid) {
  Pose o; o.p = {p.position.x, p.position.y, p.position.z}; o.q = {p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w}; o.valid = valid; return o;
}

// ------------------------------------------------------------------ android lifecycle
static void onCmd(android_app* app, int32_t cmd) {
  switch (cmd) {
    case APP_CMD_RESUME: A.resumed = true; break;
    case APP_CMD_PAUSE: A.resumed = false; A.game.save(); break;
    case APP_CMD_DESTROY: A.quit = true; break;
    default: break;
  }
}

// ------------------------------------------------------------------ setup
static bool initInstance() {
  PFN_xrInitializeLoaderKHR initLoader = nullptr;
  xrGetInstanceProcAddr(XR_NULL_HANDLE, "xrInitializeLoaderKHR", (PFN_xrVoidFunction*)&initLoader);
  if (initLoader) {
    XrLoaderInitInfoAndroidKHR li{XR_TYPE_LOADER_INIT_INFO_ANDROID_KHR};
    li.applicationVM = A.app->activity->vm; li.applicationContext = A.app->activity->clazz;
    initLoader((const XrLoaderInitInfoBaseHeaderKHR*)&li);
  }
  uint32_t n = 0; xrEnumerateInstanceExtensionProperties(nullptr, 0, &n, nullptr);
  std::vector<XrExtensionProperties> props(n, {XR_TYPE_EXTENSION_PROPERTIES}); xrEnumerateInstanceExtensionProperties(nullptr, n, &n, props.data());
  std::vector<const char*> exts = {XR_KHR_ANDROID_CREATE_INSTANCE_EXTENSION_NAME, XR_KHR_OPENGL_ES_ENABLE_EXTENSION_NAME};
  for (auto& p : props) if (!std::strcmp(p.extensionName, XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME)) { exts.push_back(XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME); A.hasRefresh = true; }
  XrInstanceCreateInfoAndroidKHR ai{XR_TYPE_INSTANCE_CREATE_INFO_ANDROID_KHR};
  ai.applicationVM = A.app->activity->vm; ai.applicationActivity = A.app->activity->clazz;
  XrInstanceCreateInfo ci{XR_TYPE_INSTANCE_CREATE_INFO}; ci.next = &ai;
  std::strcpy(ci.applicationInfo.applicationName, "Doom on Wednesday"); ci.applicationInfo.applicationVersion = 1;
  std::strcpy(ci.applicationInfo.engineName, "DOW (no engine)"); ci.applicationInfo.engineVersion = 1;
  ci.applicationInfo.apiVersion = XR_API_VERSION_1_0;
  ci.enabledExtensionCount = (uint32_t)exts.size(); ci.enabledExtensionNames = exts.data();
  if (XR_FAILED(xrCreateInstance(&ci, &A.inst))) { LOGE("xrCreateInstance failed"); return false; }
  XrSystemGetInfo sg{XR_TYPE_SYSTEM_GET_INFO}; sg.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
  if (XR_FAILED(xrGetSystem(A.inst, &sg, &A.sys))) { LOGE("xrGetSystem failed"); return false; }
  if (A.hasRefresh) xrGetInstanceProcAddr(A.inst, "xrRequestDisplayRefreshRateFB", (PFN_xrVoidFunction*)&A.requestRefresh);
  return true;
}

static bool initEGL() {
  PFN_xrGetOpenGLESGraphicsRequirementsKHR req = nullptr;
  xrGetInstanceProcAddr(A.inst, "xrGetOpenGLESGraphicsRequirementsKHR", (PFN_xrVoidFunction*)&req);
  XrGraphicsRequirementsOpenGLESKHR gr{XR_TYPE_GRAPHICS_REQUIREMENTS_OPENGL_ES_KHR}; if (req) req(A.inst, A.sys, &gr);
  A.dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY); eglInitialize(A.dpy, nullptr, nullptr);
  EGLint ca[] = {EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_DEPTH_SIZE, 0, EGL_STENCIL_SIZE, 0, EGL_SAMPLES, 0,
                 EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT_KHR, EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_NONE};
  EGLint n = 0; eglChooseConfig(A.dpy, ca, &A.cfg, 1, &n); if (n < 1) { LOGE("no EGL config"); return false; }
  EGLint cx[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
  A.ctx = eglCreateContext(A.dpy, A.cfg, EGL_NO_CONTEXT, cx);
  EGLint pa[] = {EGL_WIDTH, 16, EGL_HEIGHT, 16, EGL_NONE}; A.surf = eglCreatePbufferSurface(A.dpy, A.cfg, pa);
  if (!eglMakeCurrent(A.dpy, A.surf, A.surf, A.ctx)) { LOGE("eglMakeCurrent failed"); return false; }
  const char* ext = (const char*)glGetString(GL_EXTENSIONS);
  if (ext && std::strstr(ext, "GL_EXT_multisampled_render_to_texture")) {
    A.fbTexMS = (PFNGLFRAMEBUFFERTEXTURE2DMULTISAMPLEEXTPROC_)eglGetProcAddress("glFramebufferTexture2DMultisampleEXT");
    A.rbMS = (PFNGLRENDERBUFFERSTORAGEMULTISAMPLEEXTPROC_)eglGetProcAddress("glRenderbufferStorageMultisampleEXT");
    if (A.fbTexMS && A.rbMS) A.msaa = 4;
  }
  LOGI("GL %s | %s | MSAA %d", glGetString(GL_RENDERER), glGetString(GL_VERSION), A.msaa);
  return true;
}

static bool initSession() {
  XrGraphicsBindingOpenGLESAndroidKHR gb{XR_TYPE_GRAPHICS_BINDING_OPENGL_ES_ANDROID_KHR};
  gb.display = A.dpy; gb.config = A.cfg; gb.context = A.ctx;
  XrSessionCreateInfo si{XR_TYPE_SESSION_CREATE_INFO}; si.next = &gb; si.systemId = A.sys;
  if (XR_FAILED(xrCreateSession(A.inst, &si, &A.session))) { LOGE("xrCreateSession failed"); return false; }
  // tracking space: STAGE (floor-level origin) when available, else LOCAL lowered to an average standing height
  uint32_t n = 0; xrEnumerateReferenceSpaces(A.session, 0, &n, nullptr); std::vector<XrReferenceSpaceType> types(n); xrEnumerateReferenceSpaces(A.session, n, &n, types.data());
  bool hasStage = false; for (auto t : types) if (t == XR_REFERENCE_SPACE_TYPE_STAGE) hasStage = true;
  XrReferenceSpaceCreateInfo rs{XR_TYPE_REFERENCE_SPACE_CREATE_INFO}; rs.poseInReferenceSpace.orientation.w = 1;
  rs.referenceSpaceType = hasStage ? XR_REFERENCE_SPACE_TYPE_STAGE : XR_REFERENCE_SPACE_TYPE_LOCAL;
  if (!hasStage) { rs.poseInReferenceSpace.position.y = -1.6f; A.stageIsLocal = true; }
  XRC(xrCreateReferenceSpace(A.session, &rs, &A.stage));
  rs.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_VIEW; rs.poseInReferenceSpace.position.y = 0;
  XRC(xrCreateReferenceSpace(A.session, &rs, &A.view));
  // swapchains, one per eye
  uint32_t vc = 0; xrEnumerateViewConfigurationViews(A.inst, A.sys, XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO, 0, &vc, nullptr);
  std::vector<XrViewConfigurationView> vcv(vc, {XR_TYPE_VIEW_CONFIGURATION_VIEW}); xrEnumerateViewConfigurationViews(A.inst, A.sys, XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO, vc, &vc, vcv.data());
  uint32_t fc = 0; xrEnumerateSwapchainFormats(A.session, 0, &fc, nullptr); std::vector<int64_t> fmts(fc); xrEnumerateSwapchainFormats(A.session, fc, &fc, fmts.data());
  int64_t fmt = fmts.empty() ? GL_RGBA8 : fmts[0]; for (int64_t f : fmts) if (f == GL_SRGB8_ALPHA8) fmt = f;
  for (int e = 0; e < 2 && e < (int)vc; e++) {
    EyeChain& E = A.eye[e]; E.w = (int)vcv[e].recommendedImageRectWidth; E.h = (int)vcv[e].recommendedImageRectHeight;
    XrSwapchainCreateInfo sc{XR_TYPE_SWAPCHAIN_CREATE_INFO}; sc.usageFlags = XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT | XR_SWAPCHAIN_USAGE_SAMPLED_BIT;
    sc.format = fmt; sc.sampleCount = 1; sc.width = E.w; sc.height = E.h; sc.faceCount = 1; sc.arraySize = 1; sc.mipCount = 1;
    if (XR_FAILED(xrCreateSwapchain(A.session, &sc, &E.sc))) { LOGE("xrCreateSwapchain failed"); return false; }
    uint32_t ic = 0; xrEnumerateSwapchainImages(E.sc, 0, &ic, nullptr); E.imgs.assign(ic, {XR_TYPE_SWAPCHAIN_IMAGE_OPENGL_ES_KHR});
    xrEnumerateSwapchainImages(E.sc, ic, &ic, (XrSwapchainImageBaseHeader*)E.imgs.data());
    glGenRenderbuffers(1, &E.depth); glBindRenderbuffer(GL_RENDERBUFFER, E.depth);
    if (A.msaa) A.rbMS(GL_RENDERBUFFER, A.msaa, GL_DEPTH_COMPONENT24, E.w, E.h); else glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, E.w, E.h);
    E.fbos.resize(ic); glGenFramebuffers((GLsizei)ic, E.fbos.data());
    for (uint32_t i = 0; i < ic; i++) {
      glBindFramebuffer(GL_FRAMEBUFFER, E.fbos[i]);
      if (A.msaa) A.fbTexMS(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, E.imgs[i].image, 0, A.msaa);
      else glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, E.imgs[i].image, 0);
      glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, E.depth);
      if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) LOGE("eye %d fbo %u incomplete", e, i);
    }
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    LOGI("eye %d swapchain %dx%d, %u images, format 0x%llx", e, E.w, E.h, ic, (long long)fmt);
  }
  return true;
}

static XrAction makeAction(const char* name, const char* loc, XrActionType type) {
  XrActionCreateInfo ac{XR_TYPE_ACTION_CREATE_INFO}; std::strcpy(ac.actionName, name); std::strcpy(ac.localizedActionName, loc);
  ac.actionType = type; ac.countSubactionPaths = 2; ac.subactionPaths = A.hand;
  XrAction a = XR_NULL_HANDLE; XRC(xrCreateAction(A.set, &ac, &a)); return a;
}

static void initActions() {
  XrActionSetCreateInfo as{XR_TYPE_ACTION_SET_CREATE_INFO}; std::strcpy(as.actionSetName, "gameplay"); std::strcpy(as.localizedActionSetName, "Gameplay");
  XRC(xrCreateActionSet(A.inst, &as, &A.set));
  A.hand[0] = path("/user/hand/left"); A.hand[1] = path("/user/hand/right");
  A.aGrip = makeAction("grip", "Grip", XR_ACTION_TYPE_FLOAT_INPUT);
  A.aTrigger = makeAction("trigger", "Trigger", XR_ACTION_TYPE_FLOAT_INPUT);
  A.aPrimary = makeAction("primary", "A / X", XR_ACTION_TYPE_BOOLEAN_INPUT);
  A.aSecondary = makeAction("secondary", "B / Y", XR_ACTION_TYPE_BOOLEAN_INPUT);
  A.aStick = makeAction("stick", "Thumbstick", XR_ACTION_TYPE_VECTOR2F_INPUT);
  A.aPose = makeAction("hand_pose", "Hand pose", XR_ACTION_TYPE_POSE_INPUT);
  A.aHaptic = makeAction("haptic", "Haptics", XR_ACTION_TYPE_VIBRATION_OUTPUT);
  std::vector<XrActionSuggestedBinding> b = {
      {A.aGrip, path("/user/hand/left/input/squeeze/value")}, {A.aGrip, path("/user/hand/right/input/squeeze/value")},
      {A.aTrigger, path("/user/hand/left/input/trigger/value")}, {A.aTrigger, path("/user/hand/right/input/trigger/value")},
      {A.aPrimary, path("/user/hand/left/input/x/click")}, {A.aPrimary, path("/user/hand/right/input/a/click")},
      {A.aSecondary, path("/user/hand/left/input/y/click")}, {A.aSecondary, path("/user/hand/right/input/b/click")},
      {A.aStick, path("/user/hand/left/input/thumbstick")}, {A.aStick, path("/user/hand/right/input/thumbstick")},
      {A.aPose, path("/user/hand/left/input/grip/pose")}, {A.aPose, path("/user/hand/right/input/grip/pose")},
      {A.aHaptic, path("/user/hand/left/output/haptic")}, {A.aHaptic, path("/user/hand/right/output/haptic")}};
  XrInteractionProfileSuggestedBinding sb{XR_TYPE_INTERACTION_PROFILE_SUGGESTED_BINDING};
  sb.interactionProfile = path("/interaction_profiles/oculus/touch_controller"); sb.countSuggestedBindings = (uint32_t)b.size(); sb.suggestedBindings = b.data();
  XRC(xrSuggestInteractionProfileBindings(A.inst, &sb));
  for (int h = 0; h < 2; h++) {
    XrActionSpaceCreateInfo sc{XR_TYPE_ACTION_SPACE_CREATE_INFO}; sc.action = A.aPose; sc.subactionPath = A.hand[h]; sc.poseInActionSpace.orientation.w = 1;
    XRC(xrCreateActionSpace(A.session, &sc, &A.gripSpace[h]));
  }
  XrSessionActionSetsAttachInfo at{XR_TYPE_SESSION_ACTION_SETS_ATTACH_INFO}; at.countActionSets = 1; at.actionSets = &A.set;
  XRC(xrAttachSessionActionSets(A.session, &at));
}

// ------------------------------------------------------------------ per frame
static void pollXr() {
  XrEventDataBuffer ev{XR_TYPE_EVENT_DATA_BUFFER};
  while (xrPollEvent(A.inst, &ev) == XR_SUCCESS) {
    if (ev.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
      auto* s = (XrEventDataSessionStateChanged*)&ev; A.state = s->state;
      switch (s->state) {
        case XR_SESSION_STATE_READY: {
          XrSessionBeginInfo bi{XR_TYPE_SESSION_BEGIN_INFO}; bi.primaryViewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
          if (XR_SUCCEEDED(xrBeginSession(A.session, &bi))) A.running = true;
          if (A.requestRefresh) A.requestRefresh(A.session, 90.0f);   // Quest 2+: 90 Hz feels much better for arm movement
          break;
        }
        case XR_SESSION_STATE_STOPPING: xrEndSession(A.session); A.running = false; break;
        case XR_SESSION_STATE_FOCUSED: A.focused = true; break;
        case XR_SESSION_STATE_VISIBLE: A.focused = false; break;
        case XR_SESSION_STATE_EXITING: case XR_SESSION_STATE_LOSS_PENDING: A.quit = true; break;
        default: break;
      }
    } else if (ev.type == XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING) A.quit = true;
    ev = {XR_TYPE_EVENT_DATA_BUFFER};
  }
}

static float getF(XrAction a, int h) { XrActionStateGetInfo gi{XR_TYPE_ACTION_STATE_GET_INFO}; gi.action = a; gi.subactionPath = A.hand[h]; XrActionStateFloat s{XR_TYPE_ACTION_STATE_FLOAT}; xrGetActionStateFloat(A.session, &gi, &s); return s.isActive ? s.currentState : 0.f; }
static bool getB(XrAction a, int h) { XrActionStateGetInfo gi{XR_TYPE_ACTION_STATE_GET_INFO}; gi.action = a; gi.subactionPath = A.hand[h]; XrActionStateBoolean s{XR_TYPE_ACTION_STATE_BOOLEAN}; xrGetActionStateBoolean(A.session, &gi, &s); return s.isActive && s.currentState; }
static Vec2 getV(XrAction a, int h) { XrActionStateGetInfo gi{XR_TYPE_ACTION_STATE_GET_INFO}; gi.action = a; gi.subactionPath = A.hand[h]; XrActionStateVector2f s{XR_TYPE_ACTION_STATE_VECTOR2F}; xrGetActionStateVector2f(A.session, &gi, &s); return s.isActive ? Vec2{s.currentState.x, s.currentState.y} : Vec2{}; }

static void frame() {
  XrFrameWaitInfo fw{XR_TYPE_FRAME_WAIT_INFO}; XrFrameState fs{XR_TYPE_FRAME_STATE};
  if (XR_FAILED(xrWaitFrame(A.session, &fw, &fs))) return;
  XrFrameBeginInfo fb{XR_TYPE_FRAME_BEGIN_INFO}; xrBeginFrame(A.session, &fb);
  const XrTime t = fs.predictedDisplayTime;
  float dt = A.lastTime ? (float)((t - A.lastTime) * 1e-9) : 1 / 72.f; A.lastTime = t; dt = clampf(dt, 1 / 144.f, 1 / 30.f);

  Input& in = A.in; in.dt = dt;
  if (A.focused) {
    XrActiveActionSet aas{A.set, XR_NULL_PATH}; XrActionsSyncInfo si{XR_TYPE_ACTIONS_SYNC_INFO}; si.countActiveActionSets = 1; si.activeActionSets = &aas;
    xrSyncActions(A.session, &si);
  }
  XrSpaceLocation hl{XR_TYPE_SPACE_LOCATION}; xrLocateSpace(A.view, A.stage, t, &hl);
  bool headOk = (hl.locationFlags & XR_SPACE_LOCATION_POSITION_VALID_BIT) && (hl.locationFlags & XR_SPACE_LOCATION_ORIENTATION_VALID_BIT);
  if (headOk) in.head = toPose(hl.pose, true);
  for (int h = 0; h < 2; h++) {
    XrSpaceLocation l{XR_TYPE_SPACE_LOCATION}; xrLocateSpace(A.gripSpace[h], A.stage, t, &l);
    bool ok = A.focused && (l.locationFlags & XR_SPACE_LOCATION_POSITION_VALID_BIT) && (l.locationFlags & XR_SPACE_LOCATION_ORIENTATION_VALID_BIT);
    in.hand[h] = toPose(l.pose, ok);
    in.grip[h] = A.focused ? getF(A.aGrip, h) : 0; in.trigger[h] = A.focused ? getF(A.aTrigger, h) : 0;
  }
  in.a = A.focused && getB(A.aPrimary, 1); in.x = A.focused && getB(A.aPrimary, 0);
  in.b = A.focused && getB(A.aSecondary, 1); in.y = A.focused && getB(A.aSecondary, 0);
  in.stickL = A.focused ? getV(A.aStick, 0) : Vec2{}; in.stickR = A.focused ? getV(A.aStick, 1) : Vec2{};

  A.game.update(in);

  // haptics + sound
  for (int h = 0; h < 2; h++) if (A.game.haptic[h].amp > 0) {
    XrHapticVibration v{XR_TYPE_HAPTIC_VIBRATION}; v.amplitude = clampf(A.game.haptic[h].amp, 0, 1);
    v.duration = (XrDuration)(A.game.haptic[h].seconds * 1e9); v.frequency = XR_FREQUENCY_UNSPECIFIED;
    XrHapticActionInfo hi{XR_TYPE_HAPTIC_ACTION_INFO}; hi.action = A.aHaptic; hi.subactionPath = A.hand[h];
    xrApplyHapticFeedback(A.session, &hi, (const XrHapticBaseHeader*)&v);
  }
  const Vec3 head = A.game.loco.headW; const Vec3 right = A.game.loco.headQW.rotate({1, 0, 0});
  for (const SoundEvent& s : A.game.sounds) {
    Vec3 d = s.pos - head; float dist = length(d); float pan = dist > 0.05f ? clampf(dot(d / dist, right), -1, 1) * 0.85f : 0.f;
    A.synth.push(s.id, s.vol / (1 + 0.45f * dist), s.pitch, pan);
  }
  A.synth.setSaw(A.game.sawLevel); A.synth.setHum(A.game.lightsDim ? 0.3f : 1.f);

  // render
  XrCompositionLayerProjectionView pv[2] = {{XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW}, {XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW}};
  XrCompositionLayerProjection layer{XR_TYPE_COMPOSITION_LAYER_PROJECTION};
  const XrCompositionLayerBaseHeader* layers[1] = {(XrCompositionLayerBaseHeader*)&layer}; uint32_t nLayers = 0;
  if (fs.shouldRender) {
    XrViewLocateInfo vl{XR_TYPE_VIEW_LOCATE_INFO}; vl.viewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO; vl.displayTime = t; vl.space = A.stage;
    XrViewState vs{XR_TYPE_VIEW_STATE}; XrView views[2] = {{XR_TYPE_VIEW}, {XR_TYPE_VIEW}}; uint32_t nv = 0;
    xrLocateViews(A.session, &vl, &vs, 2, &nv, views);
    if (nv == 2 && (vs.viewStateFlags & XR_VIEW_STATE_POSITION_VALID_BIT)) {
      A.scene.build(A.game, in, dt);
      for (int e = 0; e < 2; e++) {
        EyeChain& E = A.eye[e]; uint32_t idx = 0;
        XrSwapchainImageAcquireInfo ai{XR_TYPE_SWAPCHAIN_IMAGE_ACQUIRE_INFO}; xrAcquireSwapchainImage(E.sc, &ai, &idx);
        XrSwapchainImageWaitInfo wi{XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO}; wi.timeout = XR_INFINITE_DURATION; xrWaitSwapchainImage(E.sc, &wi);
        glBindFramebuffer(GL_FRAMEBUFFER, E.fbos[idx]); glViewport(0, 0, E.w, E.h);
        Vec3 fc = A.scene.R.fogColor; glClearColor(fc.x, fc.y, fc.z, 1); glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        Pose ep = toPose(views[e].pose, true);
        Vec3 eyeW = A.game.loco.toWorld(ep.p); Quat eyeQ = A.game.loco.toWorld(ep.q);
        const XrFovf& f = views[e].fov;
        Mat4 proj = Mat4::projectionFov(std::tan(f.angleLeft), std::tan(f.angleRight), std::tan(f.angleUp), std::tan(f.angleDown), 0.04f, 80.f);
        A.scene.render(Mat4::viewFromPose(eyeW, eyeQ), proj, eyeW);
        const GLenum discard[] = {GL_DEPTH_ATTACHMENT}; glInvalidateFramebuffer(GL_FRAMEBUFFER, 1, discard);   // tiler: never write depth back
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        XrSwapchainImageReleaseInfo ri{XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO}; xrReleaseSwapchainImage(E.sc, &ri);
        pv[e].pose = views[e].pose; pv[e].fov = views[e].fov;
        pv[e].subImage.swapchain = E.sc; pv[e].subImage.imageRect.offset = {0, 0}; pv[e].subImage.imageRect.extent = {E.w, E.h};
      }
      layer.space = A.stage; layer.viewCount = 2; layer.views = pv; nLayers = 1;
    }
  }
  XrFrameEndInfo fe{XR_TYPE_FRAME_END_INFO}; fe.displayTime = t; fe.environmentBlendMode = XR_ENVIRONMENT_BLEND_MODE_OPAQUE;
  fe.layerCount = nLayers; fe.layers = nLayers ? layers : nullptr;
  xrEndFrame(A.session, &fe);
}

// ------------------------------------------------------------------ entry
void android_main(android_app* app) {
  JNIEnv* env = nullptr; app->activity->vm->AttachCurrentThread(&env, nullptr);
  A.app = app; app->userData = &A; app->onAppCmd = onCmd;
  setAssetReader(apkAsset);
  bool ok = initInstance() && initEGL() && initSession();
  if (ok) {
    initActions();
    if (!A.scene.init()) LOGE("renderer init failed");
    A.game.savePath = std::string(app->activity->internalDataPath ? app->activity->internalDataPath : ".") + "/dow_save.txt";
    A.game.init();
    // start-of-session tracking defaults so the first frame has something sensible
    A.in.head.p = {0, 1.6f, 0}; A.in.head.valid = true;
    audioStart(&A.synth);
    LOGI("Doom on Wednesday ready");
  }
  while (!app->destroyRequested) {
    for (;;) {
      int events = 0; android_poll_source* src = nullptr;
      int timeout = (!A.resumed && !A.running && !app->destroyRequested) ? -1 : 0;
      if (ALooper_pollOnce(timeout, nullptr, &events, (void**)&src) < 0) break;
      if (src) src->process(app, src);
      if (app->destroyRequested) break;
    }
    if (!ok) continue;
    pollXr();
    if (A.quit) { ANativeActivity_finish(app->activity); A.quit = false; ok = false; continue; }
    if (!A.running) continue;
    frame();
  }
  audioStop();
  A.game.save();
  if (A.session) xrDestroySession(A.session);
  if (A.inst) xrDestroyInstance(A.inst);
  app->activity->vm->DetachCurrentThread();
}
