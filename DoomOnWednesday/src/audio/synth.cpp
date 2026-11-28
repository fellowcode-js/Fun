#include "synth.h"
#include "../game/game.h"
#include <cmath>

namespace dow {

void Synth::push(int id, float vol, float pitch, float pan) {
  int h = qHead.load(std::memory_order_relaxed), n = (h + 1) % QN;
  if (n == qTail.load(std::memory_order_acquire)) return;  // full: drop
  q[h] = {id, vol, pitch, pan}; qHead.store(n, std::memory_order_release);
}

static float durOf(int id) {
  switch (id) {
    case SFX_TAP: return 0.07f; case SFX_THUD: return 0.18f; case SFX_GORE: case SFX_RIP: return 0.5f; case SFX_SLICE: return 0.45f;
    case SFX_BEEP: return 0.09f; case SFX_DENY: return 0.28f; case SFX_SPORE: return 0.7f; case SFX_SAW_ON: return 0.45f; case SFX_SAW_OFF: return 0.4f;
    case SFX_UNLOCK: return 0.5f; case SFX_PUNCH: return 0.14f; case SFX_KEY: return 0.035f; default: return 0.1f;
  }
}

void Synth::render(float* out, int frames, int rate) {
  while (qTail.load(std::memory_order_relaxed) != qHead.load(std::memory_order_acquire)) {
    int t = qTail.load(std::memory_order_relaxed); SynthEvent e = q[t]; qTail.store((t + 1) % QN, std::memory_order_release);
    int slot = 0; float best = -1; for (int i = 0; i < VN; i++) { if (v[i].id < 0) { slot = i; break; } float age = v[i].t / v[i].dur; if (age > best) { best = age; slot = i; } }
    Voice& vo = v[slot]; vo = Voice{}; vo.id = e.id; vo.vol = e.vol; vo.pitch = e.pitch; vo.pan = e.pan; vo.dur = durOf(e.id); vo.rng = 0x9e3779b9u * (slot + 1);
  }
  const float dt = 1.0f / rate, TAU = 6.2831853f; float sawT = saw.load(), humT = hum.load();
  for (int f = 0; f < frames; f++) {
    float L = 0, R = 0;
    // continuous: chainsaw engine + fluorescent hum + distant rumble
    sawLvl += (sawT - sawLvl) * 0.0008f;
    if (sawLvl > 0.002f) {
      float wob = 1 + 0.05f * std::sin(sawPh2 * 0.07f); sawPh += 88 * wob * dt; sawPh2 += 131 * wob * dt; sawPh -= std::floor(sawPh); sawPh2 -= std::floor(sawPh2);
      float s = (sawPh * 2 - 1) * 0.6f + (sawPh2 < 0.5f ? 0.25f : -0.25f) + noise() * 0.12f; s *= sawLvl * 0.22f; L += s; R += s;
    }
    humPh += 120 * dt; humPh -= std::floor(humPh); buzzPh += 60 * dt; buzzPh -= std::floor(buzzPh);
    float hm = (std::sin(humPh * TAU) * 0.6f + (buzzPh < 0.5f ? 0.15f : -0.15f)) * 0.012f * humT; rumbleLp += (noise() - rumbleLp) * 0.01f;
    L += hm + rumbleLp * 0.05f; R += hm + rumbleLp * 0.05f;
    for (Voice& vo : v) {
      if (vo.id < 0) continue;
      float t = vo.t, k = t / vo.dur, env = 1 - k, s = 0;
      auto nz = [&]() { vo.rng ^= vo.rng << 13; vo.rng ^= vo.rng >> 17; vo.rng ^= vo.rng << 5; return (vo.rng >> 8) * (2.0f / 16777216.0f) - 1.0f; };
      switch (vo.id) {
        case SFX_TAP: { float c = 0.08f + 0.25f * vo.pitch; vo.lp += (nz() - vo.lp) * c; vo.ph += 70 * vo.pitch * dt; s = vo.lp * env * env * 0.9f + std::sin(vo.ph * TAU) * env * env * env * 0.6f; break; }
        case SFX_THUD: case SFX_PUNCH: { float fr = (vo.id == SFX_PUNCH ? 140 : 110) * vo.pitch * (1 - 0.6f * k); vo.ph += fr * dt; vo.lp += (nz() - vo.lp) * 0.15f; s = (std::sin(vo.ph * TAU) * 0.9f + vo.lp * 0.6f) * env * env; break; }
        case SFX_GORE: case SFX_RIP: { vo.lp += (nz() - vo.lp) * (0.06f + 0.05f * std::sin(t * 60)); vo.ph += (90 + 40 * std::sin(t * 23)) * vo.pitch * dt; float sq = std::sin(vo.ph * TAU) * std::max(0.f, std::sin(t * 37)); s = (vo.lp * 1.6f + sq * 0.5f) * env; break; }
        case SFX_SLICE: { vo.ph += 420 * vo.pitch * (1 + 0.3f * k) * dt; vo.ph -= std::floor(vo.ph); vo.lp += (nz() - vo.lp) * 0.3f; s = ((vo.ph * 2 - 1) * 0.5f + vo.lp * 0.8f) * env; break; }
        case SFX_BEEP: case SFX_KEY: { vo.ph += (vo.id == SFX_KEY ? 1500 : 880) * vo.pitch * dt; s = std::sin(vo.ph * TAU) * (k < 0.85f ? 1.f : (1 - k) / 0.15f) * 0.35f; break; }
        case SFX_DENY: { vo.ph += 180 * dt; vo.ph -= std::floor(vo.ph); float gate = (k < 0.4f || (k > 0.55f && k < 0.95f)) ? 1.f : 0.f; s = (vo.ph < 0.5f ? 0.3f : -0.3f) * gate; break; }
        case SFX_SPORE: { vo.lp += (nz() - vo.lp) * (0.02f + 0.2f * k); vo.lp2 += (vo.lp - vo.lp2) * 0.3f; s = (vo.lp - vo.lp2) * 3.f * std::sin(k * 3.14159f); break; }
        case SFX_SAW_ON: case SFX_SAW_OFF: { float up = vo.id == SFX_SAW_ON ? k : 1 - k; vo.ph += (40 + 70 * up) * dt; vo.ph -= std::floor(vo.ph); s = ((vo.ph * 2 - 1) * 0.5f + nz() * 0.2f) * (0.3f + 0.7f * std::sin(k * 3.14159f)) * 0.6f; break; }
        case SFX_UNLOCK: { float note = k < 0.33f ? 1.f : k < 0.66f ? 1.26f : 1.5f; vo.ph += 523 * note * vo.pitch * dt; s = std::sin(vo.ph * TAU) * 0.3f * (1 - std::fmod(k * 3, 1.f) * 0.6f); break; }
      }
      s *= vo.vol; float pl = std::sqrt(0.5f * (1 - vo.pan)), pr = std::sqrt(0.5f * (1 + vo.pan));
      L += s * pl; R += s * pr;
      vo.t += dt; if (vo.t >= vo.dur) vo.id = -1;
    }
    out[f * 2] = std::tanh(L * 0.9f); out[f * 2 + 1] = std::tanh(R * 0.9f);
  }
}

}  // namespace dow
