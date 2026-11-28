// DOW math: small, header-only, no dependencies. Right-handed, Y up, -Z forward (matches OpenXR).
#pragma once
#include <cmath>
#include <cstdint>
#include <algorithm>

namespace dow {

constexpr float PI = 3.14159265358979f;
inline float clampf(float x, float a, float b) { return x < a ? a : (x > b ? b : x); }
inline float lerpf(float a, float b, float t) { return a + (b - a) * t; }
inline float smooth01(float t) { t = clampf(t, 0, 1); return t * t * (3 - 2 * t); }

struct Vec2 { float x = 0, y = 0; };

struct Vec3 {
  float x = 0, y = 0, z = 0;
  Vec3() = default;
  constexpr Vec3(float a, float b, float c) : x(a), y(b), z(c) {}
  Vec3 operator+(const Vec3& o) const { return {x + o.x, y + o.y, z + o.z}; }
  Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
  Vec3 operator*(float s) const { return {x * s, y * s, z * s}; }
  Vec3 operator/(float s) const { return {x / s, y / s, z / s}; }
  Vec3 operator-() const { return {-x, -y, -z}; }
  Vec3& operator+=(const Vec3& o) { x += o.x; y += o.y; z += o.z; return *this; }
  Vec3& operator-=(const Vec3& o) { x -= o.x; y -= o.y; z -= o.z; return *this; }
  Vec3& operator*=(float s) { x *= s; y *= s; z *= s; return *this; }
  float& operator[](int i) { return (&x)[i]; }
  float operator[](int i) const { return (&x)[i]; }
};
inline Vec3 operator*(float s, const Vec3& v) { return v * s; }
inline Vec3 mul(const Vec3& a, const Vec3& b) { return {a.x * b.x, a.y * b.y, a.z * b.z}; }
inline float dot(const Vec3& a, const Vec3& b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline Vec3 cross(const Vec3& a, const Vec3& b) { return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x}; }
inline float length(const Vec3& a) { return std::sqrt(dot(a, a)); }
inline float length2(const Vec3& a) { return dot(a, a); }
inline Vec3 normalize(const Vec3& a, const Vec3& fallback = {0, 1, 0}) { float l = length(a); return l > 1e-8f ? a / l : fallback; }
inline Vec3 lerp(const Vec3& a, const Vec3& b, float t) { return a + (b - a) * t; }
inline Vec3 vmin(const Vec3& a, const Vec3& b) { return {std::min(a.x, b.x), std::min(a.y, b.y), std::min(a.z, b.z)}; }
inline Vec3 vmax(const Vec3& a, const Vec3& b) { return {std::max(a.x, b.x), std::max(a.y, b.y), std::max(a.z, b.z)}; }
inline Vec3 vclamp(const Vec3& p, const Vec3& mn, const Vec3& mx) { return {clampf(p.x, mn.x, mx.x), clampf(p.y, mn.y, mx.y), clampf(p.z, mn.z, mx.z)}; }

struct Vec4 { float x = 0, y = 0, z = 0, w = 0; };

struct Quat {
  float x = 0, y = 0, z = 0, w = 1;
  Quat() = default;
  constexpr Quat(float a, float b, float c, float d) : x(a), y(b), z(c), w(d) {}
  static Quat axisAngle(const Vec3& axis, float ang) { Vec3 a = normalize(axis); float s = std::sin(ang * 0.5f); return {a.x * s, a.y * s, a.z * s, std::cos(ang * 0.5f)}; }
  static Quat yaw(float a) { return axisAngle({0, 1, 0}, a); }
  Quat operator*(const Quat& b) const {
    return {w * b.x + x * b.w + y * b.z - z * b.y, w * b.y - x * b.z + y * b.w + z * b.x,
            w * b.z + x * b.y - y * b.x + z * b.w, w * b.w - x * b.x - y * b.y - z * b.z};
  }
  Vec3 rotate(const Vec3& v) const {
    Vec3 q{x, y, z}; Vec3 t = cross(q, v) * 2.0f; return v + t * w + cross(q, t);
  }
  Quat conj() const { return {-x, -y, -z, w}; }
};
inline Quat normalize(const Quat& q) { float l = std::sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w); if (l < 1e-8f) return {}; return {q.x / l, q.y / l, q.z / l, q.w / l}; }
inline Quat slerp(Quat a, Quat b, float t) {
  float d = a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w; if (d < 0) { b = {-b.x, -b.y, -b.z, -b.w}; d = -d; }
  if (d > 0.9995f) return normalize(Quat{a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t, a.w + (b.w - a.w) * t});
  float th = std::acos(d), s = std::sin(th), wa = std::sin((1 - t) * th) / s, wb = std::sin(t * th) / s;
  return {a.x * wa + b.x * wb, a.y * wa + b.y * wb, a.z * wa + b.z * wb, a.w * wa + b.w * wb};
}
// Shortest rotation taking unit vector a onto unit vector b.
inline Quat fromTo(const Vec3& a, const Vec3& b) {
  float d = dot(a, b);
  if (d < -0.99999f) { Vec3 ax = cross({1, 0, 0}, a); if (length2(ax) < 1e-6f) ax = cross({0, 1, 0}, a); return Quat::axisAngle(ax, PI); }
  Vec3 c = cross(a, b); return normalize(Quat{c.x, c.y, c.z, 1 + d});
}
// Rotation whose local -Z looks along fwd and local +Y is as close to up as possible.
inline Quat lookRotation(const Vec3& fwd, const Vec3& up) {
  Vec3 z = normalize(-fwd), x = normalize(cross(up, z), {1, 0, 0}), y = cross(z, x);
  float m00 = x.x, m11 = y.y, m22 = z.z, tr = m00 + m11 + m22; Quat q;
  if (tr > 0) { float s = std::sqrt(tr + 1) * 2; q = {(y.z - z.y) / s, (z.x - x.z) / s, (x.y - y.x) / s, 0.25f * s}; }
  else if (m00 > m11 && m00 > m22) { float s = std::sqrt(1 + m00 - m11 - m22) * 2; q = {0.25f * s, (y.x + x.y) / s, (z.x + x.z) / s, (y.z - z.y) / s}; }
  else if (m11 > m22) { float s = std::sqrt(1 + m11 - m00 - m22) * 2; q = {(y.x + x.y) / s, 0.25f * s, (z.y + y.z) / s, (z.x - x.z) / s}; }
  else { float s = std::sqrt(1 + m22 - m00 - m11) * 2; q = {(z.x + x.z) / s, (z.y + y.z) / s, 0.25f * s, (x.y - y.x) / s}; }
  return normalize(q);
}
inline float yawOf(const Quat& q) { Vec3 f = q.rotate({0, 0, -1}); return std::atan2(-f.x, -f.z); }

// Column-major 4x4 (OpenGL layout).
struct Mat4 {
  float m[16] = {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
  float& at(int r, int c) { return m[c * 4 + r]; }
  float at(int r, int c) const { return m[c * 4 + r]; }
  Mat4 operator*(const Mat4& b) const {
    Mat4 o; for (int c = 0; c < 4; c++) for (int r = 0; r < 4; r++) { float s = 0; for (int k = 0; k < 4; k++) s += at(r, k) * b.at(k, c); o.at(r, c) = s; } return o;
  }
  Vec3 point(const Vec3& p) const { return {at(0, 0) * p.x + at(0, 1) * p.y + at(0, 2) * p.z + at(0, 3), at(1, 0) * p.x + at(1, 1) * p.y + at(1, 2) * p.z + at(1, 3), at(2, 0) * p.x + at(2, 1) * p.y + at(2, 2) * p.z + at(2, 3)}; }
  Vec3 dir(const Vec3& p) const { return {at(0, 0) * p.x + at(0, 1) * p.y + at(0, 2) * p.z, at(1, 0) * p.x + at(1, 1) * p.y + at(1, 2) * p.z, at(2, 0) * p.x + at(2, 1) * p.y + at(2, 2) * p.z}; }
  static Mat4 translate(const Vec3& t) { Mat4 o; o.m[12] = t.x; o.m[13] = t.y; o.m[14] = t.z; return o; }
  static Mat4 scale(const Vec3& s) { Mat4 o; o.m[0] = s.x; o.m[5] = s.y; o.m[10] = s.z; return o; }
  static Mat4 rotate(const Quat& q) {
    Mat4 o; float x = q.x, y = q.y, z = q.z, w = q.w;
    o.m[0] = 1 - 2 * (y * y + z * z); o.m[1] = 2 * (x * y + z * w); o.m[2] = 2 * (x * z - y * w);
    o.m[4] = 2 * (x * y - z * w); o.m[5] = 1 - 2 * (x * x + z * z); o.m[6] = 2 * (y * z + x * w);
    o.m[8] = 2 * (x * z + y * w); o.m[9] = 2 * (y * z - x * w); o.m[10] = 1 - 2 * (x * x + y * y); return o;
  }
  static Mat4 trs(const Vec3& t, const Quat& r, const Vec3& s) { return translate(t) * rotate(r) * scale(s); }
  static Mat4 trs(const Vec3& t, const Quat& r, float s = 1) { return trs(t, r, {s, s, s}); }
  // Asymmetric-frustum projection from OpenXR fov tangents (GL clip space, -1..1 depth).
  static Mat4 projectionFov(float tanL, float tanR, float tanU, float tanD, float n, float f) {
    Mat4 o; float w = tanR - tanL, h = tanU - tanD;
    for (float& v : o.m) v = 0;
    o.m[0] = 2 / w; o.m[5] = 2 / h; o.m[8] = (tanR + tanL) / w; o.m[9] = (tanU + tanD) / h;
    o.m[10] = -(f + n) / (f - n); o.m[11] = -1; o.m[14] = -2 * f * n / (f - n); return o;
  }
  static Mat4 perspective(float fovY, float aspect, float n, float f) { float t = std::tan(fovY * 0.5f); return projectionFov(-t * aspect, t * aspect, t, -t, n, f); }
  // Inverse of a rigid transform (rotation + translation).
  static Mat4 viewFromPose(const Vec3& p, const Quat& q) { return rotate(q.conj()) * translate(-p); }
};

// Deterministic RNG (xorshift) so every run builds identical models.
struct Rng {
  uint32_t s;
  explicit Rng(uint32_t seed = 0x9E3779B9u) : s(seed ? seed : 1) {}
  uint32_t next() { s ^= s << 13; s ^= s >> 17; s ^= s << 5; return s; }
  float f() { return (next() >> 8) * (1.0f / 16777216.0f); }
  float range(float a, float b) { return a + (b - a) * f(); }
};

// Hash noise, used by procedural textures and mesh jitter.
inline float hash2(int x, int y, uint32_t seed = 0) {
  uint32_t h = (uint32_t)x * 374761393u + (uint32_t)y * 668265263u + seed * 2246822519u; h = (h ^ (h >> 13)) * 1274126177u; h ^= h >> 16; return (h & 0xFFFFFF) / 16777215.0f;
}
inline float valueNoise(float x, float y, uint32_t seed = 0) {
  int xi = (int)std::floor(x), yi = (int)std::floor(y); float fx = x - xi, fy = y - yi; fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy);
  float a = hash2(xi, yi, seed), b = hash2(xi + 1, yi, seed), c = hash2(xi, yi + 1, seed), d = hash2(xi + 1, yi + 1, seed);
  return lerpf(lerpf(a, b, fx), lerpf(c, d, fx), fy);
}
inline float fbm(float x, float y, int oct, uint32_t seed = 0) { float s = 0, a = 0.5f, n = 0; for (int i = 0; i < oct; i++) { s += valueNoise(x, y, seed + i * 17) * a; n += a; a *= 0.5f; x *= 2.03f; y *= 2.03f; } return s / n; }

}  // namespace dow
