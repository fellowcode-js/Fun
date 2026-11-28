// Procedural audio: every sound in DOW is synthesised (noise, oscillators, filters). No sample files.
// The game thread queues events; the audio thread mixes. Lock-free single-producer/single-consumer ring.
#pragma once
#include <atomic>
#include <cstdint>

namespace dow {

struct SynthEvent { int id; float vol, pitch, pan; };

class Synth {
 public:
  void push(int id, float vol, float pitch, float pan);   // game thread
  void setSaw(float level) { saw.store(level); }
  void setHum(float level) { hum.store(level); }
  void render(float* stereo, int frames, int rate);       // audio thread
 private:
  static const int QN = 64, VN = 24;
  SynthEvent q[QN]; std::atomic<int> qHead{0}, qTail{0};
  std::atomic<float> saw{0}, hum{1};
  struct Voice { int id = -1; float t = 0, dur = 0, vol = 0, pitch = 1, pan = 0, ph = 0, ph2 = 0, lp = 0, lp2 = 0; uint32_t rng = 1; };
  Voice v[VN];
  float sawLvl = 0, sawPh = 0, sawPh2 = 0, humPh = 0, buzzPh = 0, rumbleLp = 0; uint32_t nrng = 0x1234567;
  float noise() { nrng ^= nrng << 13; nrng ^= nrng >> 17; nrng ^= nrng << 5; return (nrng >> 8) * (2.0f / 16777216.0f) - 1.0f; }
};

// Platform backends (AAudio on Quest, null on desktop)
bool audioStart(Synth* s);
void audioStop();

}  // namespace dow
