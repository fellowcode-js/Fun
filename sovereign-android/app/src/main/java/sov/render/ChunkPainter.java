package sov.render;

import sov.core.*;

import static sov.core.Terrain.*;

/** Paints a chunk to pixels: 16px per tile detail, plus a 1px per tile overview. Thread safe (read only). */
public final class ChunkPainter {
    private ChunkPainter() {}

    public static final int TP = 16;
    public static final int CP = Chunk.S * TP;

    private static final int[][] PAL = new int[16][];

    static {
        PAL[SAND] = new int[]{0xe8d9a0, 0xe0cf8c, 0xd5c27c, 0xc9b56c};
        PAL[GRASS] = new int[]{0x66b04a, 0x5fa844, 0x559c3c, 0x4b9036};
        PAL[SAVANNA] = new int[]{0xc9bf66, 0xbdb25a, 0xb0a650, 0xa39946};
        PAL[JUNGLE] = new int[]{0x33903f, 0x2f8a3a, 0x297c34, 0x236f2e};
        PAL[DESERT] = new int[]{0xedcd80, 0xe3c070, 0xd9b462, 0xcea858};
        PAL[TUNDRA] = new int[]{0x9fb095, 0x93a58a, 0x8a9c82, 0x7f9179};
        PAL[SNOW] = new int[]{0xf6f9fc, 0xeef3f8, 0xe3ebf3, 0xd6e0ea};
        PAL[SWAMP] = new int[]{0x55794f, 0x4a6f48, 0x436640, 0x3b5a3a};
        PAL[ROCK] = new int[]{0x978f84, 0x8a8378, 0x7e776d, 0x736c63};
        PAL[PEAK] = new int[]{0xe2e6ec, 0xd8dde4, 0xcdd3dc, 0xc1c9d4};
    }

    private static int prio(int t) {
        switch (t) {
            case SAND: return 1;
            case DESERT: return 2;
            case SAVANNA: return 3;
            case GRASS: return 4;
            case JUNGLE: return 5;
            case SWAMP: return 5;
            case TUNDRA: return 6;
            case SNOW: return 7;
            case ROCK: return 8;
            case PEAK: return 9;
            case DEEP: return 0;
            case SHALLOW: return 1;
            case RIVER: return 2;
            default: return 0;
        }
    }

    private static int tone(int[] pal, int gx, int gy) {
        double patch = Noise.rand01(gx >> 3, gy >> 3, 4);
        double clump = Noise.rand01(gx >> 1, gy >> 1, 3);
        double v = patch * 0.55 + clump * 0.45;
        int i = v < 0.30 ? 0 : v < 0.52 ? 1 : v < 0.76 ? 2 : 3;
        if (Noise.rand01(gx, gy, 9) > 0.93) i = Math.min(3, i + 1);
        return pal[i];
    }

    private static int landColor(int t, int gx, int gy) {
        int c = tone(PAL[t], gx, gy);
        double r = Noise.rand01(gx, gy, 21);
        switch (t) {
            case GRASS:
                if (r > 0.988) c = Pix.shade(c, 0.78);
                else if (r < 0.004) c = 0xf4f0d8;
                else if (r < 0.007) c = 0xf0d84a;
                else if (r < 0.009) c = 0xe86a8a;
                break;
            case SAVANNA:
                if (r > 0.985) c = 0x8a8038;
                break;
            case DESERT: {
                double w = Math.sin(gx * 0.11 + Math.sin(gy * 0.07) * 3 + gy * 0.17);
                if (w > 0.7) c = Pix.shade(c, 1.06);
                else if (w < -0.75) c = Pix.shade(c, 0.93);
                break;
            }
            case TUNDRA:
                if (Noise.rand01(gx >> 2, gy >> 2, 33) > 0.82) c = 0xe6edf3;
                break;
            case SNOW:
                if (r > 0.985) c = 0xbccbe0;
                break;
            case SWAMP:
                if (Noise.rand01(gx >> 2, gy >> 2, 34) > 0.86) c = 0x3a6a6a;
                break;
            case JUNGLE:
                if (r > 0.97) c = 0x4cae4a;
                break;
            case SAND:
                if (r > 0.985) c = 0xb8a45e;
                break;
            default:
                break;
        }
        return c;
    }

    private static int waterColor(int t, int gx, int gy, int elev) {
        double r = Noise.rand01(gx, gy, 41);
        if (t == DEEP) {
            int c = 0x1b3f7a;
            double wv = Noise.rand01(gx >> 2, gy >> 1, 5);
            if (wv > 0.93) c = 0x2a5496;
            else if (wv < 0.06) c = 0x16356b;
            return c;
        }
        if (t == SHALLOW) {
            double d = (elev / 255.0 - 0.30) / 0.08 + (r - 0.5) * 0.45;
            int c = d < 0.25 ? 0x2a6db0 : d < 0.55 ? 0x337db9 : d < 0.8 ? 0x3f8dc4 : 0x52a2d2;
            double wv = Noise.rand01(gx >> 2, gy >> 1, 6);
            if (wv > 0.95) c = 0x7cc0e4;
            return c;
        }
        int c = 0x3f90d2;
        double wv = Noise.rand01(gx >> 1, gy >> 2, 7);
        if (wv > 0.9) c = 0x66b0e4;
        else if (wv < 0.08) c = 0x3482c0;
        return c;
    }

    /** Hash for stable per-tile variation. */
    private static int th(int x, int y) {
        return Noise.randInt(x, y, 1234);
    }

    public static int[] paintDetail(World w, Chunk c) {
        final int S = Chunk.S, B = S + 2;
        int[] px = new int[CP * CP];
        byte[] tb = new byte[B * B], fb = new byte[B * B];
        int ox = c.cx * S, oy = c.cy * S;
        Chunk[] nbr = new Chunk[9];
        for (int dy = -1; dy <= 1; dy++)
            for (int dx = -1; dx <= 1; dx++) nbr[(dy + 1) * 3 + dx + 1] = (dx == 0 && dy == 0) ? c : w.peek(c.cx + dx, c.cy + dy);
        for (int ty = -1; ty <= S; ty++)
            for (int tx = -1; tx <= S; tx++) {
                int i = (ty + 1) * B + tx + 1;
                if (tx >= 0 && ty >= 0 && tx < S && ty < S) {
                    tb[i] = c.terrain[ty * S + tx];
                    fb[i] = c.feat[ty * S + tx];
                } else {
                    tb[i] = w.terrainAt(ox + tx, oy + ty);
                    int ddx = tx < 0 ? -1 : tx >= S ? 1 : 0, ddy = ty < 0 ? -1 : ty >= S ? 1 : 0;
                    Chunk n = nbr[(ddy + 1) * 3 + ddx + 1];
                    if (n != null) fb[i] = n.feat[(((ty + S) % S) * S) + ((tx + S) % S)];
                }
            }

        for (int ty = 0; ty < S; ty++) {
            for (int tx = 0; tx < S; tx++) {
                int ti = ty * S + tx, bi = (ty + 1) * B + tx + 1;
                int t = tb[bi];
                int nT = tb[bi - B], sT = tb[bi + B], wT = tb[bi - 1], eT = tb[bi + 1];
                int nwT = tb[bi - B - 1], neT = tb[bi - B + 1], swT = tb[bi + B - 1], seT = tb[bi + B + 1];
                boolean land = isLand(t);
                int elev = c.elev[ti] & 0xff;
                double shade = land ? 1 + c.shade[ti] / 280.0 : 1;
                int wtx = ox + tx, wty = oy + ty;
                for (int py = 0; py < TP; py++) {
                    int gy = wty * TP + py;
                    for (int pxl = 0; pxl < TP; pxl++) {
                        int gx = wtx * TP + pxl;
                        int eff = t;
                        // bleed from higher priority same-medium neighbours
                        if (pxl < 3 && wT != t && land == isLand(wT) && prio(wT) > prio(t) && Noise.rand01(gx, gy, 1) < (3 - pxl) / 4.0) eff = wT;
                        else if (pxl > 12 && eT != t && land == isLand(eT) && prio(eT) > prio(t) && Noise.rand01(gx, gy, 2) < (pxl - 12) / 4.0) eff = eT;
                        else if (py < 3 && nT != t && land == isLand(nT) && prio(nT) > prio(t) && Noise.rand01(gx, gy, 3) < (3 - py) / 4.0) eff = nT;
                        else if (py > 12 && sT != t && land == isLand(sT) && prio(sT) > prio(t) && Noise.rand01(gx, gy, 4) < (py - 12) / 4.0) eff = sT;
                        int col;
                        if (isLand(eff)) {
                            col = landColor(eff, gx, gy);
                            double k = shade;
                            // wet edge where land meets water
                            if ((pxl == 0 && isWater(wT)) || (pxl == 15 && isWater(eT)) || (py == 0 && isWater(nT)) || (py == 15 && isWater(sT))) k *= 0.86;
                            if (k != 1) col = Pix.shade(col, k);
                        } else {
                            col = waterColor(eff, gx, gy, elev);
                            // foam where water meets land
                            double fa = 0;
                            if (isLand(wT)) fa = Math.max(fa, foam(pxl));
                            if (isLand(eT)) fa = Math.max(fa, foam(15 - pxl));
                            if (isLand(nT)) fa = Math.max(fa, foam(py));
                            if (isLand(sT)) fa = Math.max(fa, foam(15 - py));
                            if (isLand(nwT) && isWater(nT) && isWater(wT)) fa = Math.max(fa, foam(Math.hypot(pxl + 0.5, py + 0.5) - 0.5));
                            if (isLand(neT) && isWater(nT) && isWater(eT)) fa = Math.max(fa, foam(Math.hypot(15.5 - pxl, py + 0.5) - 0.5));
                            if (isLand(swT) && isWater(sT) && isWater(wT)) fa = Math.max(fa, foam(Math.hypot(pxl + 0.5, 15.5 - py) - 0.5));
                            if (isLand(seT) && isWater(sT) && isWater(eT)) fa = Math.max(fa, foam(Math.hypot(15.5 - pxl, 15.5 - py) - 0.5));
                            if (fa > 0 && Noise.rand01(gx, gy, 8) < fa) col = fa > 0.7 ? 0xf4fbff : 0xbfe3f4;
                        }
                        px[(ty * TP + py) * CP + tx * TP + pxl] = 0xFF000000 | col;
                    }
                }
            }
        }

        // second pass: roads, bridges and plazas, then sprites row by row so lower tiles overlap upper ones
        for (int ty = 0; ty < S; ty++) {
            for (int tx = 0; tx < S; tx++) {
                int ti = ty * S + tx, bi = (ty + 1) * B + tx + 1;
                int f = c.feat[ti] & 0xff, aux = c.aux[ti], t = c.terrain[ti];
                if (f == 0) continue;
                int wtx = ox + tx, wty = oy + ty;
                int hash = th(wtx, wty);
                if (f == ROAD || f == BRIDGE) {
                    boolean nC = conn(fb[bi - B]), sC = conn(fb[bi + B]), wC = conn(fb[bi - 1]), eC = conn(fb[bi + 1]);
                    if (f == BRIDGE) drawBridge(px, tx, ty, wC || eC, hash);
                    else drawRoad(px, tx, ty, nC, sC, wC, eC, wtx, wty);
                } else if (f == CITY) {
                    boolean nC = conn(fb[bi - B]), sC = conn(fb[bi + B]), wC = conn(fb[bi - 1]), eC = conn(fb[bi + 1]);
                    drawPlaza(px, tx, ty, wtx, wty);
                }
            }
        }
        for (int ty = 0; ty < S; ty++) {
            for (int tx = 0; tx < S; tx++) {
                int ti = ty * S + tx;
                int f = c.feat[ti] & 0xff;
                if (f == 0 || f == ROAD || f == BRIDGE || f == CITY) continue;
                int t = c.terrain[ti];
                int aux = c.aux[ti];
                int wtx = ox + tx, wty = oy + ty;
                int hash = th(wtx, wty);
                if (f == DOCK) aux = dockDir(w, wtx, wty);
                int[] spr = Sprites.forFeature(f, aux, hash, t);
                if (spr == null) continue;
                int dx = 0, dy = 0;
                if (f >= TREE && f <= CACTUS || f == ROCKS) {
                    dx = ((hash >> 8) & 3) - 1;
                    dy = ((hash >> 12) & 3) - 2;
                    if (tx == 0 && dx < 0) dx = 0;
                    if (tx == S - 1 && dx > 0) dx = 0;
                    if (ty == 0 && dy < 0) dy = 0;
                    if (ty == S - 1 && dy > 0) dy = 0;
                }
                stamp(px, spr, tx * TP + dx, ty * TP + dy, (hash & 0x10000) != 0 && f != DOCK && f != HOUSE && f != TOWER);
            }
            // mountains are drawn from the terrain, in the same row pass
            for (int tx = 0; tx < S; tx++) {
                int ti = ty * S + tx;
                int t = c.terrain[ti];
                if (t != ROCK && t != PEAK) continue;
                int f = c.feat[ti] & 0xff;
                if (f == ORE || f == ROCKS) {
                    // ore and boulders sit on mountain tiles: stamped above already, skip the peak sprite
                    continue;
                }
                int wtx = ox + tx, wty = oy + ty;
                int hash = th(wtx, wty);
                int hh = hash >>> 4;
                if (t == ROCK && (hh & 7) == 0) continue;
                if (t == PEAK && (hh & 7) == 1) continue;
                int[] spr = t == PEAK ? Sprites.PEAK[hh & 3] : Sprites.MOUNTAIN[hh % Sprites.MOUNTAIN.length];
                int mdy = ((hash >>> 9) & 3) - 1;
                if (ty == 0 && mdy < 0) mdy = 0;
                if (ty == S - 1 && mdy > 0) mdy = 0;
                stamp(px, spr, tx * TP, ty * TP + mdy, (hash & 0x20000) != 0);
            }
        }
        return px;
    }

    private static double foam(double d) {
        return d < 0.5 ? 0.92 : d < 1.5 ? 0.6 : d < 2.5 ? 0.28 : 0;
    }

    private static boolean conn(int f) {
        return f == ROAD || f == BRIDGE || f == CITY || f == DOCK;
    }

    private static int dockDir(World w, int x, int y) {
        // sprite 0 expects water to the south, 1 west, 2 north, 3 east (rot90 clockwise steps)
        if (isWater(w.terrainAt(x, y + 1))) return 0;
        if (isWater(w.terrainAt(x - 1, y))) return 1;
        if (isWater(w.terrainAt(x, y - 1))) return 2;
        return 3;
    }

    private static void stamp(int[] px, int[] spr, int x0, int y0, boolean flip) {
        for (int y = 0; y < TP; y++) {
            int yy = y0 + y;
            if (yy < 0 || yy >= CP) continue;
            for (int x = 0; x < TP; x++) {
                int s = spr[y * TP + (flip ? TP - 1 - x : x)];
                if ((s >>> 24) == 0) continue;
                int xx = x0 + x;
                if (xx < 0 || xx >= CP) continue;
                int di = yy * CP + xx;
                px[di] = Pix.over(px[di], s);
            }
        }
    }

    private static void drawRoad(int[] px, int tx, int ty, boolean n, boolean s, boolean wC, boolean e, int wtx, int wty) {
        boolean[] m = new boolean[TP * TP];
        boolean any = n || s || wC || e;
        for (int y = 0; y < TP; y++)
            for (int x = 0; x < TP; x++) {
                boolean in = (x >= 6 && x <= 9 && y >= 6 && y <= 9);
                if (!any && x >= 5 && x <= 10 && y >= 5 && y <= 10) in = true;
                if (n && x >= 6 && x <= 9 && y < 6) in = true;
                if (s && x >= 6 && x <= 9 && y > 9) in = true;
                if (wC && y >= 6 && y <= 9 && x < 6) in = true;
                if (e && y >= 6 && y <= 9 && x > 9) in = true;
                m[y * TP + x] = in;
            }
        for (int y = 0; y < TP; y++)
            for (int x = 0; x < TP; x++) {
                if (!m[y * TP + x]) continue;
                boolean edge = (x > 0 && !m[y * TP + x - 1]) || (x < TP - 1 && !m[y * TP + x + 1])
                        || (y > 0 && !m[(y - 1) * TP + x]) || (y < TP - 1 && !m[(y + 1) * TP + x]);
                int gx = (wtx * TP + x), gy = (wty * TP + y);
                int col = edge ? 0x8a7244 : (Noise.rand01(gx, gy, 51) > 0.8 ? 0xc4a874 : 0xb59a68);
                if (edge && Noise.rand01(gx, gy, 52) > 0.5) col = 0x9a8250;
                px[(ty * TP + y) * CP + tx * TP + x] = 0xFF000000 | col;
            }
    }

    private static void drawBridge(int[] px, int tx, int ty, boolean horizontal, int hash) {
        for (int y = 0; y < TP; y++)
            for (int x = 0; x < TP; x++) {
                int a = horizontal ? y : x, b = horizontal ? x : y;
                int col;
                if (a < 3 || a > 12) continue;
                if (a == 3 || a == 12) col = 0x4a3220;
                else col = (b & 1) == 0 ? 0xa57a4c : 0x8c6038;
                if (a == 4 && ((b & 3) == 0)) col = 0x6a4a2c;
                px[(ty * TP + y) * CP + tx * TP + x] = 0xFF000000 | col;
            }
    }

    private static void drawPlaza(int[] px, int tx, int ty, int wtx, int wty) {
        for (int y = 1; y < TP - 1; y++)
            for (int x = 1; x < TP - 1; x++) {
                int gx = wtx * TP + x, gy = wty * TP + y;
                boolean line = (x % 5 == 0) || (y % 4 == 0 && (x / 5) % 2 == 0);
                int col = line ? 0x8e8676 : (Noise.rand01(gx, gy, 61) > 0.85 ? 0xc2baa8 : 0xb3ab99);
                px[(ty * TP + y) * CP + tx * TP + x] = 0xFF000000 | col;
            }
    }

    // ---------------- overview (1px per tile) ----------------

    public static int[] paintOverview(Chunk c) {
        int[] o = new int[Chunk.N];
        for (int i = 0; i < Chunk.N; i++) {
            int t = c.terrain[i];
            int col = Terrain.color(t);
            if (t == DEEP || t == SHALLOW) {
                double d = (c.elev[i] & 0xff) / 255.0;
                col = t == DEEP ? Pix.shade(0xFF000000 | col, 0.85 + d * 0.5) : Pix.shade(0xFF000000 | col, 0.95 + (d - 0.3) * 2);
            } else {
                col = Pix.shade(0xFF000000 | col, 1 + c.shade[i] / 230.0);
            }
            int f = c.feat[i] & 0xff;
            switch (f) {
                case TREE: col = Pix.mix(0xFF000000 | col, 0xFF2d6a2c, 0.55); break;
                case PINE: col = Pix.mix(0xFF000000 | col, 0xFF1f5a38, 0.55); break;
                case HOUSE: col = 0xFFc0603a; break;
                case FARM: col = 0xFFb7a050; break;
                case ROAD: case BRIDGE: col = 0xFFb59a68; break;
                case MINE: case LUMBER: col = 0xFF6a4a28; break;
                case CITY: col = 0xFFfff0c0; break;
                case TOWER: col = 0xFFa0a0a8; break;
                case DOCK: col = 0xFF8a5c36; break;
                default: break;
            }
            o[i] = 0xFF000000 | col;
        }
        return o;
    }
}
