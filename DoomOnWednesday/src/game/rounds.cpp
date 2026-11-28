// Be the Monster: main lobby computer, map voting, monster RNG (pity system), round flow, bot players,
// staff events. Bots stand in for online players until multiplayer exists.
#include "game.h"
#include "layout.h"
#include "staff_codes.h"
#include <algorithm>
#include <cmath>
#include <cstdio>

namespace dow {

static const char* kBotNames[] = {"MONKE", "SHADOW", "BANANA", "GRIMM", "PIXEL", "TOAST", "VOID", "NUTS", "GHOUL", "LEMON", "STATIC", "HOLLOW"};
static const char* kModeNames[] = {"ONE MONSTER", "TWO MONSTERS", "INFECTION", "SHAPESHIFTER"};
static const char* kPageNames[CP_COUNT] = {"ROOM", "NAME", "COLOR", "VOICE", "GAME MODE", "MONSTER MODE", "QUEUE", "STAFF"};
static const int kBotPlayers = 7;
static Rng gR(20261128);

Color Game::furColor() const { return {0.06f + profile.r / 9.f * 0.8f, 0.06f + profile.g / 9.f * 0.8f, 0.06f + profile.b / 9.f * 0.8f}; }

float Game::monsterChance(int i) const {
  float sum = 0; for (auto& p : parts) sum += p.pity;
  if (i < 0 || i >= (int)parts.size()) return 0;
  return sum > 0 ? parts[i].pity / sum : 1.f / parts.size();
}

void Game::setupParticipants() {
  parts.clear();
  Participant me; me.name = profile.name; me.local = true; me.fur = furColor(); parts.push_back(me);
  static const uint32_t furs[] = {0x6b4a2f, 0x4a4a52, 0x8a5a2a, 0x2f2f36, 0x7a3a22, 0x5a5a3a, 0x3a5a7a, 0x7a2a5a};
  for (int i = 0; i < kBotPlayers; i++) {
    for (int k = 0; k < kMaxBots; k++) if (!bots[k].active) {
      Bot& b = bots[k]; b = Bot{}; b.active = true; b.kind = 2; b.part = (int)parts.size(); b.fur = rgb(furs[i % 8]);
      Participant p; p.name = kBotNames[i]; p.bot = k; p.fur = b.fur; parts.push_back(p); break;
    }
  }
}

// ------------------------------------------------------------------ lobby
void Game::goToLobby() {
  phase = PH_LOBBY; phaseT = 45; ready = false; myVote = -1; winner = -1;
  for (int& v : votes) v = 0;
  nav.build(world, ZONE_LOBBY);
  for (auto& p : parts) {
    p.role = PR_SURVIVOR; p.shifted = false; p.vote = -1;
    if (p.bot >= 0) {
      Bot& b = bots[p.bot]; Color f = b.fur; int part = b.part; b = Bot{}; b.active = true; b.kind = 2; b.part = part; b.fur = f;
      b.p = nav.randomFree(ZONE_LOBBY, gR); b.facing = gR.range(-PI, PI);
      p.vote = (int)(gR.f() * kNumMaps) % kNumMaps; votes[p.vote]++;   // bots vote like players would
    }
  }
  setForm(FORM_GORILLA); csaw = false; targetScale = 1;
  loco.teleport(lobbySpawn(), lastHead); loco.yaw = lobbySpawnYaw();
  gore.clear();
}

void Game::computerKey(const std::string& k, int h) {
  sfx(SFX_KEY, lobbyScreenCenter(), 0.5f, 1.1f); buzz(h, 0.35f, 0.03f);
  auto msg = [&](const std::string& m) { screenMsg = m; screenMsgT = 4; };
  if (k == "UP" || k == "DOWN") { page = (page + (k == "UP" ? CP_COUNT - 1 : 1)) % CP_COUNT; typed.clear(); return; }
  bool digit = k.size() == 1 && k[0] >= '0' && k[0] <= '9', letter = k.size() == 1 && !digit;
  if (page == CP_STAFF && role >= 1 && digit) { staffAction(k[0] - '0'); return; }
  if (page == CP_STAFF && role >= 1 && k.rfind("OPT", 0) == 0) { triggerEvent(k[3] - '1'); return; }
  if (k == "DEL") { if (!typed.empty()) typed.pop_back(); return; }
  if ((digit || letter) && (page == CP_ROOM || page == CP_NAME || (page == CP_STAFF && digit))) { if (typed.size() < 12) typed += k; return; }
  switch (page) {
    case CP_ROOM:
      if (k == "ENTER" && !typed.empty()) { profile.room = typed; typed.clear(); msg("JOINED " + profile.room + "  (OFFLINE: BOTS FILL THE ROOM)"); saveProfile(); }
      if (k == "OPT1") { profile.room = "PUBLIC"; msg("JOINED A PUBLIC ROOM"); saveProfile(); }
      break;
    case CP_NAME:
      if (k == "ENTER" && !typed.empty()) { profile.name = typed; typed.clear(); if (!parts.empty()) parts[0].name = profile.name; msg("NAME SET: " + profile.name); saveProfile(); }
      break;
    case CP_COLOR:
      if (k == "OPT1" || k == "OPT2" || k == "OPT3") colorChan = k[3] - '1';
      if (digit) { int v = k[0] - '0'; (colorChan == 0 ? profile.r : colorChan == 1 ? profile.g : profile.b) = v; fur = furColor(); if (!parts.empty()) parts[0].fur = fur; saveProfile(); }
      break;
    case CP_VOICE:
      if (k == "OPT1") { profile.voice = true; msg("VOICE CHAT ON (NEEDS ONLINE PLAY)"); saveProfile(); }
      if (k == "OPT2") { profile.voice = false; msg("VOICE CHAT OFF"); saveProfile(); }
      break;
    case CP_MODE:
      if (k == "OPT1") { profile.mode = GM_BE_THE_MONSTER; msg("BE THE MONSTER"); }
      if (k == "OPT2") { profile.mode = GM_REGULAR; msg("REGULAR: COMING SOON"); }
      if (k == "OPT3") { profile.mode = GM_DONT_SPLASH; msg("DON'T SPLASH: COMING SOON"); }
      if (k == "OPT4") { loco.teleport(kSpawn, lastHead); loco.yaw = 0; say("PRACTICE AREA  (TEST DUMMIES, FORMS)"); }
      saveProfile(); break;
    case CP_MONSTER:
      if (k.rfind("OPT", 0) == 0) { profile.monsterMode = k[3] - '1'; msg(std::string("NEXT ROUND: ") + kModeNames[profile.monsterMode]); saveProfile(); }
      break;
    case CP_QUEUE:
      if (k == "OPT1" && phase == PH_LOBBY) { ready = true; phaseT = std::min(phaseT, 5.f); msg("READY! ROUND STARTS IN 5"); }
      break;
    case CP_STAFF:
      if (k == "ENTER") {
        std::string h2 = sha256hex(sha256hex(typed)); typed.clear(); int r = 0;
        for (const char* x : kOwnerHashes) if (h2 == x) r = 2;
        if (!r) for (const char* x : kModHashes) if (h2 == x) r = 1;
        if (r) { role = std::max(role, r); msg(role == 2 ? "OWNER ACCESS" : "MODERATOR ACCESS"); sfx(SFX_UNLOCK, lobbyScreenCenter()); save(); buildOS(); }
        else { msg("WRONG CODE"); sfx(SFX_DENY, lobbyScreenCenter()); }
      }
      break;
  }
}

void Game::updateLobbyInputs() {
  if (zone != ZONE_LOBBY) return;
  for (int h = 0; h < 2; h++) {
    int inKey = -1, inVote = -1, inReady = -1;
    if (loco.hand[h].have) {
      Vec3 tip = fingertip(h);
      for (int k = 0; k < kNumLobbyKeys; k++) { Vec3 d = tip - lobbyKey(k); if (std::fabs(d.x) < 0.04f && std::fabs(d.y) < 0.045f && std::fabs(d.z) < 0.04f) inKey = k; }
      for (int m = 0; m < kNumMaps; m++) { Vec3 d = tip - votePadButton(m); if (std::fabs(d.x) < 0.3f && std::fabs(d.y) < 0.07f && std::fabs(d.z) < 0.36f) inVote = m; }
      { Vec3 d = tip - readyButton(); if (std::fabs(d.x) < 0.3f && std::fabs(d.y) < 0.07f && std::fabs(d.z) < 0.3f) inReady = 0; }
    }
    if (inKey >= 0 && inKey != lastLobbyKey[h]) computerKey(kLobbyKeys[inKey], h);
    if (inVote >= 0 && inVote != lastVote[h] && phase == PH_LOBBY) {
      if (myVote >= 0) votes[myVote]--; myVote = inVote; votes[myVote]++; if (!parts.empty()) parts[0].vote = myVote;
      sfx(SFX_BEEP, votePadButton(inVote), 0.7f, 1.2f); buzz(h, 0.6f, 0.05f); say(std::string("VOTED: ") + zoneInfo(1 + inVote).name);
    }
    if (inReady >= 0 && inReady != lastReady[h] && phase == PH_LOBBY) {
      if (profile.mode != GM_BE_THE_MONSTER) say("THAT MODE IS COMING SOON - PICK BE THE MONSTER");
      else { ready = true; phaseT = std::min(phaseT, 5.f); say("READY! ROUND STARTS IN 5"); sfx(SFX_UNLOCK, readyButton()); }
      buzz(h, 0.7f, 0.06f);
    }
    lastLobbyKey[h] = inKey; lastVote[h] = inVote; lastReady[h] = inReady;
  }
}

// ------------------------------------------------------------------ round flow
void Game::startRound() {
  // map: most votes wins, ties broken at random
  int best = -1, bv = -1; for (int m = 0; m < kNumMaps; m++) { int v = votes[m] * 16 + (int)(gR.f() * 15); if (v > bv) { bv = v; best = m; } }
  roundMap = 1 + best; roundMode = profile.monsterMode;
  nav.build(world, roundMap);
  // monster pick: weighted by pity (0% right after you were the monster, rising every round you are not)
  int nMon = roundMode == MM_TWO ? 2 : 1; std::vector<int> pool; for (int i = 0; i < (int)parts.size(); i++) pool.push_back(i);
  std::vector<int> mons;
  if (forceMeMonster) { mons.push_back(0); forceMeMonster = false; }
  while ((int)mons.size() < nMon) {
    float sum = 0; for (int i : pool) if (std::find(mons.begin(), mons.end(), i) == mons.end()) sum += std::max(parts[i].pity, 0.f);
    float x = gR.f() * sum; int pick = -1;
    for (int i : pool) { if (std::find(mons.begin(), mons.end(), i) != mons.end()) continue; float w = std::max(parts[i].pity, 0.f); if (sum <= 0 || x < w) { pick = i; break; } x -= w; }
    if (pick < 0) for (int i : pool) if (std::find(mons.begin(), mons.end(), i) == mons.end()) { pick = i; break; }
    mons.push_back(pick);
  }
  for (int i = 0; i < (int)parts.size(); i++) {
    bool m = std::find(mons.begin(), mons.end(), i) != mons.end();
    parts[i].role = m ? PR_MONSTER : PR_SURVIVOR; parts[i].pity = m ? 0 : parts[i].pity + 1; parts[i].shifted = false; parts[i].catches = 0;
  }
  // spawns: survivors spread out, monsters as far from them as the map allows
  std::vector<Vec3> sp; for (Vec3 c : zoneSpawns(roundMap)) if (nav.isFree(roundMap, c)) sp.push_back(c);
  for (size_t i = sp.size(); i > 1; i--) std::swap(sp[i - 1], sp[gR.next() % i]);
  if (sp.empty()) sp.push_back(zoneInfo(roundMap).origin);
  Vec3 cen; int ns = 0; size_t si = 0; std::vector<Vec3> place(parts.size());
  for (int i = 0; i < (int)parts.size(); i++) if (parts[i].role == PR_SURVIVOR) { place[i] = sp[si++ % sp.size()]; cen += place[i]; ns++; }
  if (ns) cen = cen / (float)ns;
  std::sort(sp.begin(), sp.end(), [&](const Vec3& a, const Vec3& b) { return length2(a - cen) > length2(b - cen); });
  int mi = 0; for (int i = 0; i < (int)parts.size(); i++) if (parts[i].role == PR_MONSTER) place[i] = sp[(mi++ * 3) % sp.size()];
  for (int i = 0; i < (int)parts.size(); i++) {
    Participant& p = parts[i];
    if (p.local) {
      loco.teleport(place[i], lastHead);
      bool shape = roundMode == MM_SHAPESHIFTER;
      setForm(p.role == PR_MONSTER && !shape ? FORM_MONSTER : FORM_GORILLA);
    } else if (p.bot >= 0) {
      Bot& b = bots[p.bot]; b.p = place[i]; b.alive = true; b.limbs = 7; b.sliced = false; b.role = p.role; b.disguised = roundMode == MM_SHAPESHIFTER && p.role == PR_MONSTER;
      b.path = NavPath{}; b.think = 0; b.knock = {};
    }
  }
  for (auto& b : bots) if (b.active && b.part < 0) b.active = false;   // practice dummies stay home
  phase = PH_STARTING; phaseT = 3;
  char t[160]; std::snprintf(t, sizeof t, "%s  -  %s\n%s", zoneInfo(roundMap).name, kModeNames[roundMode], myRole() == PR_MONSTER ? "YOU ARE THE MONSTER" : "YOU ARE A SURVIVOR");
  banner = t; bannerT = 5; sfx(SFX_ROUND, loco.headW, 1, myRole() == PR_MONSTER ? 0.7f : 1.f);
}

void Game::endRound(int w) {
  phase = PH_END; phaseT = 8; winner = w; roundsPlayed++;
  banner = w == PR_MONSTER ? "THE MONSTERS WIN" : "THE SURVIVORS WIN"; bannerT = 7; sfx(SFX_ROUND, loco.headW, 1, w == PR_MONSTER ? 0.6f : 1.3f);
}

void Game::catchPart(int v, int by) {
  Participant& P = parts[v]; if (P.role != PR_SURVIVOR) return;
  if (by >= 0) parts[by].catches++;
  if (roundMode == MM_INFECTION) {
    P.role = PR_MONSTER;
    if (P.local) { setForm(FORM_MONSTER); banner = "YOU'VE BEEN INFECTED\nHUNT THEM DOWN"; bannerT = 4; jumpscare = 0.9f; sfx(SFX_SCREAM, loco.headW); }
    else { Bot& b = bots[P.bot]; b.role = PR_MONSTER; b.hitFlash = 0.5f; gore.punch(b.p + Vec3{0, 0.8f, 0}, {0, 1, 0}); sfx(SFX_SCREAM, b.p, 0.6f, 1.3f); }
  } else {
    P.role = PR_GHOST;
    if (P.local) { jumpscare = 1.4f; banner = "YOU WERE CAUGHT\nSPECTATING UNTIL THE ROUND ENDS"; bannerT = 4; sfx(SFX_SCREAM, loco.headW); buzz(0, 1, 0.5f); buzz(1, 1, 0.5f); }
    else {
      Bot& b = bots[P.bot]; Vec3 head = b.p + Vec3{0, 0.8f, 0};
      if (b.alive) { b.alive = false; b.deadT = 6; b.limbs &= ~1; gore.rip(GIB_HEAD, head, normalize(head - loco.headW + Vec3{0, 0.5f, 0}), b.fur, 1.f); }
      sfx(SFX_RIP, head, 1, 0.9f);
    }
  }
}

void Game::updateRound(const Input& in, float dt) {
  if (bannerT > 0) bannerT -= dt;
  if (jumpscare > 0) jumpscare -= dt;
  if (screenMsgT > 0) screenMsgT -= dt;
  for (int e = 0; e < EV_COUNT; e++) if (eventT[e] > 0) eventT[e] -= dt;
  if (parts.empty()) return;
  // bots that were ripped/sawed during a hunt count as caught
  for (auto& b : bots) if (b.active && b.part >= 0 && !b.alive && parts[b.part].role == PR_SURVIVOR && phase == PH_HUNT) catchPart(b.part, 0);
  switch (phase) {
    case PH_LOBBY:
      if (profile.mode == GM_BE_THE_MONSTER) { phaseT -= dt; if (phaseT <= 0) startRound(); } else phaseT = 45;
      break;
    case PH_STARTING: phaseT -= dt; if (phaseT <= 0) { phase = PH_HIDE; phaseT = 12; if (myRole() == PR_MONSTER) { banner = "WAIT... THEY ARE HIDING"; bannerT = 3; } } break;
    case PH_HIDE: phaseT -= dt; if (phaseT <= 0) { phase = PH_HUNT; phaseT = 150; banner = myRole() == PR_MONSTER ? "HUNT!" : "IT'S COMING"; bannerT = 2.5f; sfx(SFX_SCREAM, loco.headW, 0.5f, 0.7f); } break;
    case PH_HUNT: {
      phaseT -= dt; int alive = 0; for (auto& p : parts) alive += p.role == PR_SURVIVOR;
      if (alive == 0) endRound(PR_MONSTER); else if (phaseT <= 0) endRound(PR_SURVIVOR);
      break;
    }
    case PH_END: phaseT -= dt; if (phaseT <= 0) goToLobby(); break;
  }
  // you as the monster: tag survivors with your hands (shapeshifters must reveal first, B)
  Participant& me = parts[0];
  bool bNow = in.b; if (bNow && !bPrev && me.role == PR_MONSTER && roundMode == MM_SHAPESHIFTER && me.shiftCd <= 0) {
    me.shifted = !me.shifted; me.shiftCd = 2; setForm(me.shifted ? FORM_MONSTER : FORM_GORILLA); sfx(SFX_SPORE, loco.headW, 0.8f, me.shifted ? 0.7f : 1.3f);
  }
  bPrev = bNow; me.shiftCd -= dt;
  if (phase == PH_HUNT && me.role == PR_MONSTER && (roundMode != MM_SHAPESHIFTER || me.shifted)) {
    for (auto& b : bots) if (b.active && b.alive && b.part >= 0 && parts[b.part].role == PR_SURVIVOR)
      for (int h = 0; h < 2; h++) {
        if (!in.hand[h].valid) continue; Vec3 hp = loco.hand[h].phys;
        if (length(hp - (b.p + Vec3{0, 0.45f, 0})) < 0.36f || length(hp - (b.p + Vec3{0, 0.8f, 0})) < 0.24f) { catchPart(b.part, 0); buzz(h, 1, 0.12f); break; }
      }
  }
}

// ------------------------------------------------------------------ bot players
void Game::updateRoundBots(float dt) {
  const Vec3 myFeet{loco.headW.x, loco.headW.y - loco.P.bodyHeight * loco.scale, loco.headW.z};
  int botZone = (phase == PH_LOBBY || phase == PH_END) ? ZONE_LOBBY : roundMap;
  if (phase == PH_END && zone == ZONE_LOBBY) botZone = ZONE_LOBBY; else if (phase == PH_END) botZone = roundMap;
  for (int bi = 0; bi < kMaxBots; bi++) {
    Bot& b = bots[bi]; if (!b.active || b.part < 0) continue;
    b.hitFlash -= dt;
    if (!b.alive) { b.deadT -= dt; if (b.deadT <= 0) b.active = false; continue; }
    if (zone != botZone) continue;     // not in the zone you're simulating
    Participant& P = parts[b.part];
    float speed = 0; Vec3 face;
    auto goTo = [&](const Vec3& goal, float repath) {
      b.think -= dt;
      if (b.think <= 0 || b.path.done()) { b.think = repath; nav.findPath(botZone, b.p, goal, b.path); b.goal = goal; }
    };
    bool lobbyish = phase == PH_LOBBY || phase == PH_END || phase == PH_STARTING;
    if (lobbyish) {
      if (b.path.done()) { b.think -= dt; if (b.think <= 0) { nav.findPath(botZone, b.p, nav.randomFree(botZone, gR), b.path); b.think = 2 + gR.f() * 4; } }
      speed = phase == PH_STARTING ? 0 : 1.1f;
    } else if (P.role == PR_MONSTER) {
      if (phase == PH_HIDE) speed = 0;
      else {
        // nearest survivor (you included) — monsters can smell, no line of sight needed
        Vec3 tgt; float bd = 1e9f; int tp = -1;
        for (int i = 0; i < (int)parts.size(); i++) {
          if (parts[i].role != PR_SURVIVOR) continue;
          Vec3 q = parts[i].local ? myFeet : bots[parts[i].bot].p; float d = length2(q - b.p); if (d < bd) { bd = d; tgt = q; tp = i; }
        }
        if (tp >= 0) {
          float d = std::sqrt(bd);
          bool reveal = !b.disguised || d < 4.5f || b.chaseT > 0;
          if (b.disguised && d < 4.5f) { b.disguised = false; b.chaseT = 7; sfx(SFX_SCREAM, b.p, 0.7f, 0.8f); }
          if (!b.disguised && roundMode == MM_SHAPESHIFTER) { b.chaseT -= dt; if (b.chaseT <= 0 && d > 6) b.disguised = true; }
          goTo(tgt, d < 6 ? 0.35f : 0.9f);
          speed = reveal ? (d < 3 ? 3.4f : 3.0f) : 1.4f;
          if (nav.lineFree(botZone, b.p, tgt) && d < 3) { b.path.pts = {Vec3{tgt.x, 0, tgt.z}}; b.path.idx = 0; }
          // catch: reach you unless you climbed out of reach
          float dy = (parts[tp].local ? myFeet.y : 0) - b.p.y; Vec3 flat = tgt - b.p; flat.y = 0;
          if (!b.disguised && length(flat) < 0.7f && dy < 1.3f) catchPart(tp, b.part);
        }
      }
    } else {   // survivor bot: flee visible monsters, otherwise roam
      float md = 1e9f; Vec3 mpos;
      for (int i = 0; i < (int)parts.size(); i++) {
        if (parts[i].role != PR_MONSTER) continue; Vec3 q; bool hidden = false;
        if (parts[i].local) { q = myFeet; hidden = roundMode == MM_SHAPESHIFTER && !parts[i].shifted; }
        else { q = bots[parts[i].bot].p; hidden = bots[parts[i].bot].disguised; }
        float d = length(q - b.p); if (!hidden && d < md) { md = d; mpos = q; }
      }
      if (md < 8 && phase == PH_HUNT) {
        b.think -= dt;
        if (b.think <= 0 || b.path.done()) {
          Vec3 best = b.p; float score = -1;
          for (int k = 0; k < 12; k++) { Vec3 c = nav.randomFree(botZone, gR); float s = length(c - mpos) - 0.5f * length(c - b.p); if (s > score) { score = s; best = c; } }
          nav.findPath(botZone, b.p, best, b.path); b.think = 1.2f;
        }
        speed = 2.75f;
      } else { if (b.path.done()) { b.think -= dt; if (b.think <= 0) { nav.findPath(botZone, b.p, nav.randomFree(botZone, gR), b.path); b.think = 1 + gR.f() * 3; } } speed = 1.3f; }
    }
    // follow the path
    Vec3 move;
    if (!b.path.done() && speed > 0) {
      Vec3 d = b.path.pts[b.path.idx] - b.p; d.y = 0; float dl = length(d);
      if (dl < 0.3f) b.path.idx++; else move = d / dl;
    }
    Vec3 v = move * speed + b.knock; b.knock = b.knock * (1 - std::min(1.f, 6 * dt));
    Vec3 np = b.p + v * dt, probe = np + Vec3{0, 0.5f, 0};
    if (length2(world.resolveSphere(probe, 0.28f, 0)) > 0) { np = probe - Vec3{0, 0.5f, 0}; np.y = 0; }
    b.vel = (np - b.p) / dt; b.p = np; b.walkPhase += length(b.vel) * dt * 5.f;
    face = speed > 0 && length(move) > 0 ? move : (myFeet - b.p);
    face.y = 0;
    if (length(face) > 1e-3f) { float want = std::atan2(-face.x, -face.z), d = want - b.facing; while (d > PI) d -= 2 * PI; while (d < -PI) d += 2 * PI; b.facing += d * std::min(1.f, 8 * dt); }
  }
}

// ------------------------------------------------------------------ staff
void Game::triggerEvent(int ev) {
  if (role < 1 || ev < 0 || ev >= EV_COUNT) return;
  static const char* names[EV_COUNT] = {"BLACKOUT", "LOW GRAVITY", "BLOOD MOON", "GIANT MODE"};
  static const float dur[EV_COUNT] = {30, 40, 60, 30};
  eventT[ev] = eventT[ev] > 0 ? 0 : dur[ev];
  banner = std::string(eventT[ev] > 0 ? "STAFF EVENT: " : "EVENT ENDED: ") + names[ev]; bannerT = 3.5f; sfx(SFX_EVENT, loco.headW, 1, 1);
}

void Game::staffAction(int a) {
  if (role < 1) return;
  switch (a) {
    case 1: if (phase == PH_LOBBY) { ready = true; phaseT = 3; banner = "STAFF: ROUND STARTING"; bannerT = 2; } break;
    case 2: if (phase >= PH_STARTING && phase <= PH_HUNT) endRound(PR_SURVIVOR); break;
    case 3: if (phase == PH_HUNT) for (auto& p : parts) if (!p.local && p.role == PR_SURVIVOR) { p.role = PR_MONSTER; bots[p.bot].role = PR_MONSTER; bots[p.bot].disguised = false; banner = "STAFF: MONSTER RUSH"; bannerT = 3; break; } break;
    case 4: for (int i = 0; i < 4; i++) spawnBot(1, loco.headW + Vec3{gR.range(-2, 2), -loco.headW.y, gR.range(-2, 2)}); banner = "STAFF: BOT PARTY"; bannerT = 2; break;
    case 5: if (role >= 2) { forceMeMonster = true; banner = "OWNER: YOU ARE THE MONSTER NEXT ROUND"; bannerT = 3; } break;
    case 6: if (role >= 2) { unlocked = true; save(); banner = "OWNER: STALKER UNLOCKED"; bannerT = 3; } break;
    case 7: gore.clear(); banner = "STAFF: GORE CLEARED"; bannerT = 2; break;
    case 8: loco.teleport(kDenCenter + Vec3{0, 0, 1.5f}, lastHead); say("MOD DEN"); break;
    case 9: goToLobby(); break;
  }
  sfx(SFX_EVENT, loco.headW, 0.6f, 1.2f);
}

// ------------------------------------------------------------------ profile
void Game::saveProfile() const {
  if (savePath.empty()) return;
  if (FILE* f = std::fopen((savePath + ".profile").c_str(), "w")) {
    std::fprintf(f, "%s\n%s\n%d %d %d %d %d %d\n", profile.name.c_str(), profile.room.c_str(), profile.r, profile.g, profile.b, profile.voice ? 1 : 0, profile.mode, profile.monsterMode);
    std::fclose(f);
  }
}
void Game::loadProfile() {
  if (savePath.empty()) return;
  if (FILE* f = std::fopen((savePath + ".profile").c_str(), "r")) {
    char n[64] = {0}, r[64] = {0}; int a, b, c, v, m, mm;
    if (std::fscanf(f, "%63s %63s %d %d %d %d %d %d", n, r, &a, &b, &c, &v, &m, &mm) == 8) {
      profile.name = n; profile.room = r; profile.r = a % 10; profile.g = b % 10; profile.b = c % 10; profile.voice = v; profile.mode = m % 3; profile.monsterMode = mm % 4;
    }
    std::fclose(f);
  }
}

}  // namespace dow
