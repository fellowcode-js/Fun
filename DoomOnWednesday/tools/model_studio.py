#!/usr/bin/env python3
"""DOW model studio: sculpts every avatar with the production-3d-kit (aim) and writes the game's .dowm format.

Each part (head, torso, upper arm, forearm, palm) is one watertight signed-distance surface built from blended
primitives, displaced fur clumps and carved features, plus kit appendages (eyeballs, horns, fangs, claws).
Vertex colours come from region fields (fur / skin / bone / glow ...) with ambient occlusion baked from the field.
Fur regions of the gorilla are flagged "tint" so the player's chosen colour still applies in game.

Usage:  PYTHONPATH=<kit> python3 tools/model_studio.py <out_dir> [--preview <png_dir>]
Coordinates follow the game: metres, +Y up, faces look down -Z. Head origin = head centre, torso origin = chest,
arm segments run +Y from 0 to their length, the palm is the right hand in OpenXR grip space (palm faces -X).
"""
import math, os, struct, sys
import numpy as np
from production3d import vsdf as V, appendages as AP, decimate as DEC

# ------------------------------------------------------------------ helpers
def hexc(h): return ((h >> 16) & 255) / 255.0, ((h >> 8) & 255) / 255.0, (h & 255) / 255.0

class Mat:
    def __init__(self, color, emissive=0.0, tint=False, vary=0.10, ao=1.0):
        self.c = np.array(hexc(color) if isinstance(color, int) else (color, color, color) if isinstance(color, float) else color, dtype=float); self.e = emissive; self.tint = tint; self.vary = vary; self.ao = ao

def nz(scale=40.0, amount=0.004, seed=1, octaves=3):
    return V.noise(scale=scale, amount=amount, octaves=octaves, seed=seed)

class Part:
    """A sculpted part: the shape field, colour regions, and extra appendage meshes."""
    def __init__(self, name, field, regions, extras=(), res=88, bounds=None):
        self.name, self.field, self.regions, self.extras, self.res, self.bounds = name, field, regions, list(extras), res, bounds

def field_normals(f, P, eps=0.0015):
    g = np.zeros_like(P)
    for k in range(3):
        d = np.zeros(3); d[k] = eps
        g[:, k] = f(P + d) - f(P - d)
    n = np.linalg.norm(g, axis=1, keepdims=True); n[n < 1e-12] = 1
    return g / n

def bake_ao(f, P, N, step=0.012, n=5):
    occ = np.zeros(len(P))
    for i in range(1, n + 1):
        h = step * i; occ += (h - np.minimum(f(P + N * h), h)) / (2 ** i)
    return np.clip(1.0 - 3.2 * occ / step, 0.25, 1.0)

def colour_regions(P, regions, f, N):
    """regions: list of (VSDF, Mat, bias). The nearest region surface (minus bias) owns the vertex."""
    D = np.stack([np.abs(r[0](P)) - r[2] for r in regions], axis=1)
    own = np.argmin(D, axis=1)
    ao = bake_ao(f, P, N)
    rng = np.random.default_rng(7)
    out_c = np.zeros((len(P), 3)); out_e = np.zeros(len(P)); out_t = np.zeros(len(P), dtype=bool)
    # low-frequency mottling + per-vertex grain so surfaces never look like flat plastic
    mott = 0.5 + 0.5 * np.sin(P[:, 0] * 37.0 + np.sin(P[:, 1] * 23.0) * 2.0) * np.sin(P[:, 2] * 29.0 + P[:, 1] * 11.0)
    for i, (_, m, _) in enumerate(regions):
        sel = own == i
        if not sel.any(): continue
        grain = 1.0 + 0.6 * m.vary * (rng.random(sel.sum()) - 0.5) + 0.35 * m.vary * (mott[sel] - 0.5)
        a = 1.0 - m.ao * (1.0 - ao[sel])
        out_c[sel] = np.clip(m.c[None, :] * (grain * a)[:, None], 0, 1)
        out_e[sel] = m.e; out_t[sel] = m.tint
    return out_c, out_e, out_t

def mesh_arrays(m):
    """kit Mesh -> (positions, triangles, face material index)"""
    P = np.array(m.verts, dtype=np.float64); tris, fm = [], []
    for fi, f in enumerate(m.faces):
        mi = m.mats[fi] if m.mats else 0
        for k in range(1, len(f) - 1): tris.append((f[0], f[k], f[k + 1])); fm.append(mi)
    return P, np.array(tris, dtype=np.int64), np.array(fm)

def flat_normals(P, T):
    N = np.zeros_like(P); fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    for k in range(3): np.add.at(N, T[:, k], fn)
    n = np.linalg.norm(N, axis=1, keepdims=True); n[n < 1e-12] = 1; return N / n

BUDGET = {'head': 5200, 'torso': 5200, 'upper': 1300, 'fore': 1300, 'palm': 1000}   # triangles per part (Quest: ~14k per character)

def build(part):
    m = part.field.mesh(resolution=part.res, bounds=part.bounds)
    tgt = BUDGET.get(part.name, 4000)
    if m.tri_count > tgt * 1.15: m = DEC.decimate(m, target_tris=tgt)
    P, T, _ = mesh_arrays(m)
    f = part.field
    N = field_normals(f, P)
    C, E, TI = colour_regions(P, part.regions, f, N)
    verts = [(P, N, C, E, TI, T)]
    for em, mats in part.extras:   # appendages: per-face kit materials -> our colours
        Q, U, FM = mesh_arrays(em); NN = flat_normals(Q, U)
        cc = np.zeros((len(Q), 3)); ee = np.zeros(len(Q)); tt = np.zeros(len(Q), dtype=bool)
        for t, mi in zip(U, FM):
            mm = mats[min(mi, len(mats) - 1)]
            for v in t: cc[v] = mm.c; ee[v] = mm.e; tt[v] = mm.tint
        verts.append((Q, NN, cc, ee, tt, U))
    return verts

# ------------------------------------------------------------------ .dowm writer (same layout as tools/glb_to_dowm.py)
def write_dowm(path, parts):
    nodes, meshes, vbytes, idx = [], [], bytearray(), []
    nv = 0
    for name, chunks in parts:
        v0, i0 = nv, len(idx)
        for (P, N, C, E, TI, T) in chunks:
            base = nv
            for k in range(len(P)):
                r, g, b = (int(round(x * 255)) for x in C[k]); e = int(round(min(E[k], 1) * 255))
                vbytes += struct.pack('<8f4B4B', P[k][0], P[k][1], P[k][2], N[k][0], N[k][1], N[k][2], 0.0, 0.0, r, g, b, e, 255 if TI[k] else 0, 0, 0, 0)
            idx += [int(base + x) for x in T.reshape(-1)]; nv += len(P)
        meshes.append((v0, nv - v0, i0, len(idx) - i0, -1)); nodes.append((name, len(meshes) - 1))
    out = bytearray(b'DOWM') + struct.pack('<I', 1) + struct.pack('<I', len(nodes))
    for name, mi in nodes: out += name.encode()[:31].ljust(32, b'\0') + struct.pack('<ii10f', -1, mi, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1)
    out += struct.pack('<I', len(meshes))
    for m in meshes: out += struct.pack('<IIIIi', *m)
    out += struct.pack('<I', nv) + vbytes + struct.pack('<I', len(idx)) + struct.pack('<%dI' % len(idx), *idx)
    out += struct.pack('<III', 0, 0, 0)   # materials, textures, animations
    open(path, 'wb').write(out)
    return nv, len(idx) // 3

# ------------------------------------------------------------------ shared anatomy
def E(c, r): return V.ellipsoid(c, r)
def S(c, r): return V.sphere(c, r)
def C(a, b, r1, r2=None): return V.round_cone(a, b, r1, r2 if r2 is not None else r1)
def B(parts, k=0.02): return V.blend(parts, k)

def eyes(x, y, z, r, iris, glow=0.0, pupil='round'):
    out = []
    for s in (-1, 1):
        e = AP.eyeball(r, iris=iris, pupil=pupil).rotate('y', 180).translate(s * x, y, z)   # kit eyes look +Z, ours look -Z
        mats = [Mat((0.93, 0.91, 0.86), 0.0, vary=0), Mat(iris, glow, vary=0), Mat((0.01, 0.01, 0.01), 0.0, vary=0)]
        if glow: mats = [Mat(iris, glow * 0.6, vary=0), Mat(iris, glow, vary=0), Mat((1, 1, 0.8), 1.0, vary=0)]
        out.append((e, mats))
    return out

def arm_part(name, length, r0, r1, fur, skin=None, bulge=1.12, seed=3, noise_amt=0.005):
    shaft = C((0, 0, 0), (0, length, 0), r0, r1)
    mus = E((0, length * 0.42, 0.004), (r0 * bulge, length * 0.3, r0 * 1.05))
    f = B([shaft, mus], 0.03).displace(nz(55, noise_amt, seed))
    regions = [(f, fur, 0)]
    return Part(name, f, regions, res=64, bounds=((-r0 * 1.6, -r0 * 1.2, -r0 * 1.6), (r0 * 1.6, length + r1 * 1.3, r0 * 1.6)))

def palm_part(name, skin, back, knuckles=True, claw=None):
    pad = V.box((-0.004, 0, -0.022), (0.048, 0.096, 0.092), 0.018)
    backf = V.box((0.016, 0.002, -0.012), (0.044, 0.1, 0.1), 0.02)
    wrist = C((0.012, 0, 0.035), (0.008, 0, -0.01), 0.04, 0.036)
    parts = [pad, backf, wrist] + ([S((0.004, y, -0.058), 0.016) for y in (0.033, 0.011, -0.011, -0.033)] if knuckles else [])
    f = B(parts, 0.012)
    regions = [(B([pad] + parts[3:], 0.01), skin, 0.002), (B([backf, wrist], 0.01), back, 0)]
    return Part(name, f, regions, res=60, bounds=((-0.05, -0.08, -0.09), (0.06, 0.08, 0.07)))

# ------------------------------------------------------------------ the cast
def gorilla():
    FUR = Mat(0.5, tint=True, vary=0.12, ao=0.45); SKIN = Mat(0x2e2622, vary=0.06); FACE = Mat(0x3a302b, vary=0.06); DARK = Mat(0x120c0a, vary=0.05)
    # head: crested skull, heavy brow, deep sockets, broad nose, muzzle
    skull = E((0, 0.012, 0.012), (0.15, 0.158, 0.148)); crest = E((0, 0.118, 0.05), (0.045, 0.07, 0.11)); jowl = E((0, -0.07, 0.03), (0.135, 0.09, 0.12))
    furf = B([skull, crest, jowl], 0.03).displace(nz(70, 0.0035, 11))
    face = E((0, -0.008, -0.112), (0.118, 0.11, 0.062)); muzzle = E((0, -0.066, -0.15), (0.09, 0.064, 0.066))
    brow = C((-0.09, 0.046, -0.142), (0.09, 0.046, -0.142), 0.03)
    nose = E((0, -0.03, -0.19), (0.045, 0.026, 0.03))
    skin = B([face, muzzle, brow, nose], 0.022)
    head = B([furf, skin], 0.018)
    for s in (-1, 1):
        head = head.smooth_subtract(S((s * 0.046, 0.012, -0.168), 0.03), 0.012)        # eye sockets
        head = head.smooth_subtract(S((s * 0.02, -0.04, -0.215), 0.011), 0.006)       # nostrils
    head = head.smooth_subtract(C((-0.055, -0.1, -0.205), (0.055, -0.1, -0.205), 0.008), 0.01)   # mouth
    for s in (-1, 1): head = head.smooth_union(E((s * 0.148, 0.0, 0.0), (0.02, 0.034, 0.028)), 0.012)  # ears
    H = Part('head', head, [(furf, FUR, 0), (skin, FACE, 0.004), (nose, SKIN, 0.006), (brow, DARK, 0.0)],
             extras=eyes(0.046, 0.012, -0.165, 0.021, (0.32, 0.18, 0.08)), res=96, bounds=((-0.2, -0.2, -0.25), (0.2, 0.22, 0.2)))
    # torso: barrel chest, traps, broad back, rounded seat (no legs: you move with your arms)
    chest = E((0, 0.05, 0), (0.215, 0.235, 0.17)); traps = [E((s * 0.145, 0.17, 0.015), (0.12, 0.1, 0.12)) for s in (-1, 1)]
    hump = E((0, 0.23, 0.05), (0.1, 0.08, 0.09)); seat = E((0, -0.15, 0.03), (0.185, 0.15, 0.155)); back = E((0, -0.02, 0.11), (0.17, 0.2, 0.07))
    furt = B([chest, hump, seat, back] + traps, 0.04).displace(nz(60, 0.0045, 21))
    pecs = [E((s * 0.07, 0.11, -0.148), (0.085, 0.045, 0.03)) for s in (-1, 1)]; belly = E((0, -0.04, -0.125), (0.13, 0.15, 0.06))
    sk = B(pecs + [belly], 0.03); torso = B([furt, sk], 0.02)
    T = Part('torso', torso, [(furt, FUR, 0), (sk, Mat(0x3a302a, vary=0.06), 0.004)], res=96, bounds=((-0.3, -0.34, -0.25), (0.3, 0.34, 0.24)))
    return [H, T, arm_part('upper', 0.43, 0.062, 0.054, FUR), arm_part('fore', 0.43, 0.058, 0.045, FUR, seed=7), palm_part('palm', SKIN, Mat(0.46, tint=True, vary=0.2))]

def monster():
    FUR = Mat(0x2a1010, vary=0.18); HIDE = Mat(0x3a1414, vary=0.18); BONE = Mat(0xd8cbb0, vary=0.08); MOUTH = Mat(0x1a0303, vary=0.05); GLOW = Mat(0xff3010, 0.9, vary=0)
    skull = E((0, 0.03, 0.02), (0.15, 0.15, 0.16)); snout = E((0, -0.05, -0.15), (0.1, 0.075, 0.12)); jaw = E((0, -0.14, -0.12), (0.095, 0.045, 0.11))
    ridge = C((-0.1, 0.06, -0.12), (0.1, 0.06, -0.12), 0.034)
    furf = B([skull], 0.03).displace(nz(42, 0.009, 31)); hide = B([snout, jaw, ridge], 0.03).displace(nz(90, 0.002, 5))
    head = B([furf, hide], 0.025)
    head = head.smooth_subtract(E((0, -0.1, -0.2), (0.075, 0.03, 0.09)), 0.01)                      # gaping maw
    for s in (-1, 1): head = head.smooth_subtract(S((s * 0.055, 0.025, -0.15), 0.032), 0.01)
    extras = eyes(0.055, 0.025, -0.145, 0.022, (1.0, 0.25, 0.05), glow=1.0)
    for i in range(8):
        x = -0.06 + i * 0.017; l = 0.05 if i in (1, 6) else 0.028
        extras.append((AP.fang((x, -0.075, -0.205 + abs(x) * 0.4), (x * 0.95, -0.075 - l, -0.212 + abs(x) * 0.4), 0.007), [BONE]))
        extras.append((AP.fang((x + 0.008, -0.135, -0.2 + abs(x) * 0.4), (x + 0.008, -0.135 + l * 0.7, -0.205 + abs(x) * 0.4), 0.006), [BONE]))
    for s in (-1, 1):
        extras.append((AP.horn((s * 0.09, 0.1, 0.0), (s * 0.24, 0.24, 0.12), 0.036, bend=(s * 0.05, 0.08, -0.06), ridges=0.3), [BONE]))
        extras.append((AP.fang((s * 0.06, -0.14, -0.17), (s * 0.08, -0.04, -0.21), 0.013), [BONE]))   # tusks
    H = Part('head', head, [(furf, FUR, 0), (hide, HIDE, 0.003), (E((0, -0.1, -0.2), (0.07, 0.03, 0.085)), MOUTH, 0.02)], extras, res=100,
             bounds=((-0.22, -0.24, -0.3), (0.22, 0.22, 0.22)))
    chest = E((0, 0.05, 0), (0.24, 0.25, 0.18)); traps = [E((s * 0.17, 0.22, 0.03), (0.14, 0.12, 0.14)) for s in (-1, 1)]
    hunch = E((0, 0.2, 0.1), (0.15, 0.12, 0.12)); seat = E((0, -0.16, 0.04), (0.2, 0.16, 0.17))
    furt = B([chest, hunch, seat] + traps, 0.05).displace(nz(36, 0.011, 41))
    plates = [E((0, 0.24 - i * 0.075, 0.2 - i * 0.012), (0.04, 0.03, 0.02)) for i in range(6)]
    belly = E((0, -0.02, -0.14), (0.15, 0.18, 0.07))
    torso = B([furt, B(plates, 0.01), belly], 0.02)
    extras = [(AP.horn((0, 0.26 - i * 0.075, 0.21 - i * 0.012), (0, 0.3 - i * 0.075, 0.3 - i * 0.012), 0.026), [BONE]) for i in range(6)]
    T = Part('torso', torso, [(furt, FUR, 0), (B(plates, 0.01), BONE, 0.004), (belly, HIDE, 0.004)], extras, res=100, bounds=((-0.34, -0.36, -0.26), (0.34, 0.4, 0.34)))
    palm = palm_part('palm', MOUTH, FUR)
    return [H, T, arm_part('upper', 0.45, 0.085, 0.07, FUR, bulge=1.2, seed=9, noise_amt=0.008), arm_part('fore', 0.45, 0.08, 0.06, FUR, seed=13, noise_amt=0.008), palm]

def stalker():
    SKIN = Mat(0x9aa39a, vary=0.18); DARK = Mat(0x030504, vary=0); RIB = Mat(0x8c968c, vary=0.1, ao=0.3); SPORE = Mat(0x44ff66, 0.9, vary=0)
    skull = E((0, 0.05, 0.01), (0.118, 0.2, 0.13)); jaw = E((0, -0.09, -0.06), (0.075, 0.07, 0.075))
    head = B([skull, jaw], 0.04).displace(nz(70, 0.0025, 51))
    for s in (-1, 1): head = head.smooth_subtract(E((s * 0.045, 0.035, -0.12), (0.034, 0.046, 0.035)), 0.012)
    head = head.smooth_subtract(C((-0.035, -0.11, -0.135), (0.035, -0.11, -0.135), 0.004), 0.004)
    extras = eyes(0.045, 0.03, -0.118, 0.008, (0.4, 1.0, 0.35), glow=1.0)
    H = Part('head', head, [(head, SKIN, 0), (B([E((s * 0.045, 0.035, -0.12), (0.03, 0.042, 0.03)) for s in (-1, 1)], 0.01), DARK, -0.004)], extras, res=96,
             bounds=((-0.16, -0.2, -0.2), (0.16, 0.28, 0.17)))
    core = E((0, 0.06, 0), (0.15, 0.22, 0.1)); ribs = [V.torus((0, 0.14 - i * 0.05, -0.01), 0.135 - i * 0.006, 0.009) for i in range(5)]
    ribs = [r for r in ribs if r is not None]
    pelvis = E((0, -0.14, 0), (0.1, 0.09, 0.08)); tend = [C(((i - 1.5) * 0.035, -0.2, 0), ((i - 1.5) * 0.05, -0.42 + 0.03 * (i % 2), 0.02), 0.018, 0.003) for i in range(4)]
    body = B([core, pelvis] + tend, 0.03)
    torso = B([body] + ribs, 0.01)
    sacs = [S(((0.05 if i % 2 else -0.05), 0.2 - i * 0.06, 0.095), 0.022) for i in range(6)]
    torso = B([torso] + sacs, 0.008)
    T = Part('torso', torso, [(body, SKIN, 0), (B(ribs, 0.01) if ribs else body, RIB, 0.003), (B(sacs, 0.005), SPORE, 0.006)], res=96,
             bounds=((-0.22, -0.48, -0.18), (0.22, 0.32, 0.16)))
    return [H, T, arm_part('upper', 0.5, 0.04, 0.032, SKIN, bulge=1.05, seed=17, noise_amt=0.002), arm_part('fore', 0.5, 0.034, 0.026, SKIN, bulge=1.0, seed=19, noise_amt=0.002),
            palm_part('palm', Mat(0x7a837a), SKIN)]

def wendigo():
    BONE = Mat(0xe4dcc6, vary=0.12); FUR = Mat(0x2b2420, vary=0.3); HIDE = Mat(0x5a4a40, vary=0.15); GLOW = (0.9, 0.95, 1.0)
    # deer skull: long muzzle, empty sockets, antlers
    cran = E((0, 0.03, 0.03), (0.1, 0.1, 0.11)); muz = C((0, -0.01, -0.03), (0, -0.05, -0.2), 0.065, 0.032); jaw = C((0, -0.07, -0.04), (0, -0.085, -0.18), 0.03, 0.018)
    skull = B([cran, muz, jaw], 0.03)
    for s in (-1, 1): skull = skull.smooth_subtract(S((s * 0.055, 0.02, -0.06), 0.03), 0.008)
    skull = skull.smooth_subtract(E((0, -0.04, -0.205), (0.018, 0.02, 0.03)), 0.006)
    mane = E((0, 0.0, 0.11), (0.12, 0.14, 0.09)).displace(nz(30, 0.012, 61))
    head = B([skull, mane], 0.02)
    extras = eyes(0.055, 0.02, -0.06, 0.007, GLOW, glow=1.0)
    for s in (-1, 1):   # antlers: main beam + tines
        base = (s * 0.06, 0.1, 0.02)
        extras.append((AP.horn(base, (s * 0.22, 0.36, 0.08), 0.018, bend=(s * 0.04, 0.0, -0.05), ridges=0.25, segments=16), [BONE]))
        for t, (u, h) in enumerate([(0.35, 0.12), (0.6, 0.14), (0.85, 0.1)]):
            p = (base[0] + (s * 0.16) * u, base[1] + 0.26 * u, base[2] + 0.06 * u - 0.02 * u * u)
            extras.append((AP.horn(p, (p[0] + s * 0.02, p[1] + h, p[2] - 0.05), 0.009, bend=(0, 0.02, -0.02)), [BONE]))
        extras.append((AP.fang((s * 0.02, -0.05, -0.17), (s * 0.022, -0.085, -0.175), 0.006), [BONE]))
    H = Part('head', head, [(skull, BONE, 0), (mane, FUR, 0.004)], extras, res=104, bounds=((-0.16, -0.16, -0.25), (0.16, 0.17, 0.22)))
    spine = [S((0, 0.28 - i * 0.07, 0.1 + 0.02 * math.sin(i)), 0.03) for i in range(8)]
    cage = E((0, 0.06, -0.01), (0.15, 0.2, 0.11)); gut = E((0, -0.13, 0.0), (0.09, 0.08, 0.07)); pel = E((0, -0.22, 0.02), (0.12, 0.06, 0.08))
    body = B([cage, gut, pel] + spine, 0.035)
    for i in range(5): body = body.smooth_subtract(E((0, 0.16 - i * 0.055, -0.115), (0.13, 0.012, 0.03)), 0.01)   # rib gaps
    furry = B([E((0, 0.22, 0.06), (0.16, 0.1, 0.1)), E((0, 0.05, 0.1), (0.13, 0.15, 0.06))], 0.04).displace(nz(26, 0.015, 71))
    torso = B([body, furry], 0.02)
    T = Part('torso', torso, [(body, HIDE, 0), (B(spine, 0.02), BONE, 0.006), (furry, FUR, 0.004)], res=100, bounds=((-0.24, -0.32, -0.2), (0.24, 0.38, 0.22)))
    return [H, T, arm_part('upper', 0.55, 0.036, 0.028, HIDE, bulge=1.0, seed=23, noise_amt=0.002), arm_part('fore', 0.55, 0.03, 0.022, HIDE, bulge=1.0, seed=29, noise_amt=0.002),
            palm_part('palm', Mat(0x3a302a), HIDE)]

def smiler():
    SHADOW = Mat(0x050506, vary=0.3, ao=0.4); TEETH = Mat((1, 1, 0.96), 1.0, vary=0.05); GUM = Mat(0x200006, 0.2, vary=0)
    blob = E((0, 0.0, 0.0), (0.17, 0.18, 0.16)).displace(nz(16, 0.022, 81, octaves=4))
    head = blob.smooth_subtract(E((0, -0.045, -0.15), (0.12, 0.04, 0.06)), 0.01)
    extras = eyes(0.06, 0.06, -0.15, 0.022, (1, 1, 1), glow=1.0)
    for row, (y, d) in enumerate([(-0.025, -1), (-0.068, 1)]):            # the grin: two arcs of glowing teeth
        for i in range(15):
            t = (i - 7) / 7.0; x = t * 0.11; z = -0.165 + 0.04 * t * t; yy = y + 0.02 * t * t * (1 if row == 0 else -1)
            extras.append((AP.fang((x, yy, z), (x, yy + d * 0.022, z - 0.004), 0.008), [TEETH]))
    H = Part('head', head, [(head, SHADOW, 0), (E((0, -0.045, -0.15), (0.11, 0.035, 0.05)), GUM, -0.003)], extras, res=88, bounds=((-0.24, -0.24, -0.24), (0.24, 0.24, 0.24)))
    torso = B([E((0, 0.02, 0), (0.2, 0.26, 0.16)), E((0, -0.22, 0.02), (0.12, 0.14, 0.1)), C((0, -0.3, 0.02), (0, -0.5, 0.05), 0.08, 0.005)], 0.08).displace(nz(12, 0.03, 91, octaves=4))
    T = Part('torso', torso, [(torso, SHADOW, 0)], res=88, bounds=((-0.3, -0.6, -0.25), (0.3, 0.36, 0.25)))
    arm = lambda n, L, r0, r1, sd: Part(n, C((0, 0, 0), (0, L, 0), r0, r1).displace(nz(20, 0.012, sd)), [(C((0, 0, 0), (0, L, 0), r0, r1), SHADOW, 0)], res=56,
                                         bounds=((-r0 * 2, -r0 * 2, -r0 * 2), (r0 * 2, L + r1 * 2, r0 * 2)))
    return [H, T, arm('upper', 0.5, 0.05, 0.04, 97), arm('fore', 0.5, 0.045, 0.03, 101), palm_part('palm', SHADOW, SHADOW, knuckles=False)]

def crawler():
    CHITIN = Mat(0x1a1612, vary=0.25); SHELL = Mat(0x3a2a1e, vary=0.2); EYE = (1.0, 0.1, 0.05); FANG = Mat(0x0a0806, vary=0)
    head = B([E((0, 0.0, -0.02), (0.13, 0.1, 0.15)), E((0, 0.05, 0.05), (0.12, 0.08, 0.1))], 0.04).displace(nz(60, 0.003, 111))
    extras = []
    for k, (x, y, z, r) in enumerate([(0.035, 0.05, -0.15, 0.02), (-0.035, 0.05, -0.15, 0.02), (0.075, 0.07, -0.12, 0.014), (-0.075, 0.07, -0.12, 0.014),
                                       (0.02, 0.095, -0.11, 0.011), (-0.02, 0.095, -0.11, 0.011), (0.1, 0.04, -0.09, 0.01), (-0.1, 0.04, -0.09, 0.01)]):
        e = AP.eyeball(r, iris=EYE).rotate('y', 180).translate(x, y, z); extras.append((e, [Mat(EYE, 0.8, vary=0), Mat(EYE, 1.0, vary=0), Mat((1, 0.8, 0.5), 1.0, vary=0)]))
    for s in (-1, 1):   # mandibles
        extras.append((AP.claw((s * 0.05, -0.05, -0.15), (s * -0.3, -0.4, -1.0), length=0.11, radius=0.016, curve=0.6), [FANG]))
    H = Part('head', head, [(head, CHITIN, 0)], extras, res=92, bounds=((-0.18, -0.15, -0.22), (0.18, 0.16, 0.18)))
    segs = [E((0, 0.18 - i * 0.12, 0.02 * i), (0.2 - i * 0.02, 0.08, 0.15 - i * 0.01)) for i in range(4)]
    body = B(segs, 0.04).displace(nz(50, 0.004, 121))
    extras = []
    for s in (-1, 1):   # extra spider legs folded along the back
        for i in range(3):
            root = (s * 0.12, 0.15 - i * 0.11, 0.08)
            extras.append((AP.claw(root, (s * 0.6, 0.5, 0.6), length=0.32, radius=0.02, curve=0.7), [SHELL]))
    T = Part('torso', body, [(body, CHITIN, 0)], extras, res=92, bounds=((-0.26, -0.3, -0.2), (0.26, 0.3, 0.24)))
    return [H, T, arm_part('upper', 0.47, 0.045, 0.038, CHITIN, bulge=1.0, seed=131, noise_amt=0.003), arm_part('fore', 0.47, 0.04, 0.03, SHELL, bulge=1.0, seed=137, noise_amt=0.003),
            palm_part('palm', CHITIN, SHELL, knuckles=False)]

CAST = {'gorilla': gorilla, 'monster': monster, 'stalker': stalker, 'wendigo': wendigo, 'smiler': smiler, 'crawler': crawler}

if __name__ == '__main__':
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    only = [a for a in sys.argv[2:] if not a.startswith('-')]
    for name, fn in CAST.items():
        if only and name not in only: continue
        parts = fn(); built = []
        for p in parts: built.append((p.name, build(p)))
        nv, nt = write_dowm(os.path.join(out, 'avatar_%s.dowm' % name), built)
        print('%-8s %6d verts %6d tris  -> avatar_%s.dowm' % (name, nv, nt, name))
