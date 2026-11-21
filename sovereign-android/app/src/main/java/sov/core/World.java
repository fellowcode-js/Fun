package sov.core;

import java.util.*;
import java.util.concurrent.*;

/** The world: procedural terrain (bounded or infinite), plus all nations, cities and armies. */
public final class World {
    public static final class LogEntry {
        public final int turn, nation;
        public final String text;
        public final boolean important;

        LogEntry(int turn, int nation, String text, boolean important) {
            this.turn = turn;
            this.nation = nation;
            this.text = text;
            this.important = important;
        }
    }

    public final long seed;
    public final WorldSize size;
    public final boolean bounded;
    public final int N;
    private final int seedInt;
    private final Noise nElev, nDetail, nRidge, nMoist, nTemp, nRiver, nForest;
    private final double baseFreq, riverScale;

    private final ConcurrentHashMap<Long, Chunk> chunks = new ConcurrentHashMap<>();
    private final Set<Long> pending = ConcurrentHashMap.newKeySet();
    private final ExecutorService pool;

    // ---- game state ----
    public final LinkedHashMap<Integer, Nation> nations = new LinkedHashMap<>();
    public final HashMap<Integer, City> cities = new HashMap<>();
    public final ArrayList<Army> armies = new ArrayList<>();
    private final HashMap<Long, ArrayList<City>> grid = new HashMap<>();
    public int turn;
    public int nextCityId = 1, nextNationId = 1, nextArmyId = 1;
    public final Random rng;
    public final ArrayList<LogEntry> log = new ArrayList<>();
    public int playerNation;
    public boolean gameOver;
    /** Visual effect events for the renderer: x, y, type, color. Types: 0 battle, 1 captured, 2 founded, 3 disaster. */
    public final ArrayList<float[]> fx = new ArrayList<>();

    public World(long seed, WorldSize size) {
        this.seed = seed;
        this.size = size;
        this.bounded = !size.infinite();
        this.N = size.tiles;
        this.seedInt = (int) (seed ^ (seed >>> 32));
        nElev = new Noise(seed * 31 + 1);
        nDetail = new Noise(seed * 31 + 2);
        nRidge = new Noise(seed * 31 + 3);
        nMoist = new Noise(seed * 31 + 4);
        nTemp = new Noise(seed * 31 + 5);
        nRiver = new Noise(seed * 31 + 6);
        nForest = new Noise(seed * 31 + 7);
        baseFreq = bounded ? 0.0042 * Math.max(1.0, 700.0 / N) : 0.0036;
        riverScale = baseFreq / 0.0042;
        rng = new Random(seed ^ 0x5DEECE66DL);
        int threads = Math.max(1, Runtime.getRuntime().availableProcessors() - 1);
        pool = Executors.newFixedThreadPool(threads, r -> {
            Thread t = new Thread(r, "chunkgen");
            t.setDaemon(true);
            t.setPriority(Thread.NORM_PRIORITY - 1);
            return t;
        });
    }

    public void shutdown() {
        pool.shutdownNow();
    }

    // ================= terrain sampling =================

    private static double clamp01(double v) {
        return v < 0 ? 0 : v > 1 ? 1 : v;
    }

    public double elevation(int x, int y) {
        double f = baseFreq;
        double c = nElev.fbm(x * f, y * f, 6, 2.0, 0.5);
        double det = nDetail.fbm(x * 0.035, y * 0.035, 3, 2.0, 0.5) * 0.10;
        double e = 0.46 + c * 1.30 + det;
        double ridge = 1.0 - Math.abs(nRidge.fbm(x * f * 1.4 + 40, y * f * 1.4 - 20, 4, 2.0, 0.5) * 5.0);
        if (ridge > 0.55) e += (ridge - 0.55) * 0.55 * clamp01((e - 0.45) * 6);
        if (bounded) {
            int d = Math.min(Math.min(x, y), Math.min(N - 1 - x, N - 1 - y));
            double band = Math.max(10, N * 0.10);
            if (d < band) {
                double m = d < 0 ? 0 : d / band;
                m = m * m * (3 - 2 * m);
                e = e * m + 0.05 * (1 - m);
            }
        }
        return clamp01(e);
    }

    public double moisture(int x, int y) {
        return clamp01(0.5 + nMoist.fbm(x * 0.0055 + 300, y * 0.0055 - 120, 4, 2.0, 0.5) * 1.6);
    }

    public double temperature(int x, int y, double e) {
        double lat;
        if (bounded) lat = Math.sin(Math.PI * (y + 0.5) / N);
        else lat = 0.5 + 0.5 * Math.cos(y * 2 * Math.PI / 7000.0 + 1.6);
        double t = 0.12 + lat * 0.72 + nTemp.fbm(x * 0.004 + 9, y * 0.004 + 5, 3, 2.0, 0.5) * 0.40;
        t -= Math.max(0, e - 0.5) * 0.8;
        return clamp01(t);
    }

    private double riverVal(int x, int y) {
        return Math.abs(nRiver.fbm(x * 0.0075 * riverScale, y * 0.0075 * riverScale, 3, 2.0, 0.5));
    }

    private byte classify(int x, int y, double e, double m, double t) {
        if (e < 0.30) return Terrain.DEEP;
        if (e < 0.38) return Terrain.SHALLOW;
        if (e < 0.72 && e > 0.395) {
            double thr = 0.005 + 0.012 * (1 - (e - 0.395) / 0.325);
            if (riverVal(x, y) < thr) return Terrain.RIVER;
        }
        if (e < 0.41) return t < 0.2 ? Terrain.TUNDRA : Terrain.SAND;
        if (e > 0.93) return Terrain.PEAK;
        if (e > 0.79) return (t < 0.30 && e > 0.86) ? Terrain.PEAK : Terrain.ROCK;
        if (t < 0.15) return Terrain.SNOW;
        if (t < 0.30) return Terrain.TUNDRA;
        if (t > 0.68) {
            if (m < 0.30) return Terrain.DESERT;
            if (m < 0.55) return Terrain.SAVANNA;
            return Terrain.JUNGLE;
        }
        if (m < 0.20 && t > 0.5) return Terrain.DESERT;
        if (m > 0.80 && e < 0.47) return Terrain.SWAMP;
        return Terrain.GRASS;
    }

    /** Returns feature | aux<<8. */
    private int featureFor(int x, int y, byte ter, double forest, double t) {
        double r = Noise.rand01(x, y, seedInt + 11);
        double r2 = Noise.rand01(x, y, seedInt + 29);
        switch (ter) {
            case Terrain.GRASS:
                if (forest > 0.04 && r < 0.60) return Terrain.TREE | ((r2 < 0.10 ? 1 : 0) << 8);
                if (r < 0.015) return Terrain.TREE;
                if (r > 0.992) return Terrain.ROCKS;
                return 0;
            case Terrain.SWAMP:
                return r < 0.14 ? (Terrain.TREE | (3 << 8)) : 0;
            case Terrain.JUNGLE:
                return r < 0.68 ? (Terrain.TREE | (1 << 8)) : 0;
            case Terrain.SAVANNA:
                if (r < 0.05) return Terrain.TREE | (2 << 8);
                if (r > 0.99) return Terrain.ROCKS;
                return 0;
            case Terrain.TUNDRA:
                if (forest > 0.0 && r < 0.40) return Terrain.PINE;
                return r < 0.03 ? Terrain.PINE : 0;
            case Terrain.SNOW:
                if (r < 0.05) return Terrain.PINE | (1 << 8);
                return r > 0.99 ? Terrain.ROCKS : 0;
            case Terrain.DESERT:
                if (r < 0.013) return Terrain.CACTUS;
                return r > 0.988 ? Terrain.ROCKS : 0;
            case Terrain.SAND:
                return (r < 0.02 && t > 0.45) ? Terrain.PALM : 0;
            case Terrain.ROCK:
                if (r < 0.05) return Terrain.ORE | ((r2 < 0.3 ? 1 : 0) << 8);
                return r > 0.93 ? Terrain.ROCKS : 0;
            default:
                return 0;
        }
    }

    private boolean outside(int x, int y) {
        return bounded && (x < 0 || y < 0 || x >= N || y >= N);
    }

    private byte sampleTerrain(int x, int y) {
        if (outside(x, y)) return Terrain.DEEP;
        double e = elevation(x, y);
        if (e < 0.30) return Terrain.DEEP;
        if (e < 0.38) return Terrain.SHALLOW;
        return classify(x, y, e, moisture(x, y), temperature(x, y, e));
    }

    // ================= chunks =================

    private Chunk generate(int cx, int cy) {
        final int S = Chunk.S, B = S + 2;
        Chunk c = new Chunk(cx, cy);
        double[] el = new double[B * B];
        int ox = cx * S, oy = cy * S;
        for (int ty = -1; ty <= S; ty++)
            for (int tx = -1; tx <= S; tx++) el[(ty + 1) * B + tx + 1] = elevation(ox + tx, oy + ty);
        for (int ty = 0; ty < S; ty++) {
            for (int tx = 0; tx < S; tx++) {
                int x = ox + tx, y = oy + ty, i = ty * S + tx;
                double e = el[(ty + 1) * B + tx + 1];
                byte t;
                int fa = 0;
                if (outside(x, y)) {
                    t = Terrain.DEEP;
                } else if (e < 0.30) {
                    t = Terrain.DEEP;
                } else if (e < 0.38) {
                    t = Terrain.SHALLOW;
                } else {
                    double tm = temperature(x, y, e), m = moisture(x, y);
                    t = classify(x, y, e, m, tm);
                    if (Terrain.isLand(t)) {
                        double fo = nForest.fbm(x * 0.045, y * 0.045, 3, 2.0, 0.5);
                        fa = featureFor(x, y, t, fo, tm);
                    }
                }
                c.terrain[i] = t;
                c.feat[i] = (byte) (fa & 0xff);
                c.aux[i] = (byte) (fa >> 8);
                c.elev[i] = (byte) (int) (e * 255);
                if (Terrain.isLand(t)) {
                    double sh = (el[(ty + 1) * B + tx + 2] - el[(ty + 1) * B + tx]
                            + el[(ty + 2) * B + tx + 1] - el[ty * B + tx + 1]) * 260;
                    c.shade[i] = (byte) Math.max(-100, Math.min(100, sh));
                }
            }
        }
        return c;
    }

    /** Get a chunk, generating it on the calling thread if needed. */
    public Chunk chunk(int cx, int cy) {
        long k = Chunk.key(cx, cy);
        Chunk c = chunks.get(k);
        if (c != null) return c;
        c = generate(cx, cy);
        Chunk p = chunks.putIfAbsent(k, c);
        return p != null ? p : c;
    }

    public Chunk peek(int cx, int cy) {
        return chunks.get(Chunk.key(cx, cy));
    }

    /** Ask a worker thread to generate a chunk. */
    public void request(int cx, int cy) {
        long k = Chunk.key(cx, cy);
        if (chunks.containsKey(k) || pending.size() > 400 || !pending.add(k)) return;
        pool.submit(() -> {
            try {
                chunk(cx, cy);
            } finally {
                pending.remove(k);
            }
        });
    }

    public int loadedChunks() {
        return chunks.size();
    }

    /** Drop old chunks with no player-made state. */
    public void evict(int max) {
        if (chunks.size() <= max) return;
        ArrayList<Chunk> list = new ArrayList<>();
        for (Chunk c : chunks.values()) if (!c.hasClaims) list.add(c);
        list.sort(Comparator.comparingLong(a -> a.lastUse));
        int remove = chunks.size() - max;
        for (int i = 0; i < remove && i < list.size(); i++) chunks.remove(Chunk.key(list.get(i).cx, list.get(i).cy));
    }

    // ================= tile access =================

    public boolean inBounds(int x, int y) {
        return !outside(x, y);
    }

    public byte terrainAt(int x, int y) {
        if (outside(x, y)) return Terrain.DEEP;
        Chunk c = chunks.get(Chunk.key(x >> Chunk.SHIFT, y >> Chunk.SHIFT));
        if (c != null) return c.terrain[(y & 31) * 32 + (x & 31)];
        return sampleTerrain(x, y);
    }

    public byte featAt(int x, int y) {
        if (outside(x, y)) return 0;
        return chunk(x >> Chunk.SHIFT, y >> Chunk.SHIFT).feat[(y & 31) * 32 + (x & 31)];
    }

    public byte auxAt(int x, int y) {
        if (outside(x, y)) return 0;
        return chunk(x >> Chunk.SHIFT, y >> Chunk.SHIFT).aux[(y & 31) * 32 + (x & 31)];
    }

    public int elevAt(int x, int y) {
        if (outside(x, y)) return 0;
        return chunk(x >> Chunk.SHIFT, y >> Chunk.SHIFT).elev[(y & 31) * 32 + (x & 31)] & 0xff;
    }

    public int ownerAt(int x, int y) {
        if (outside(x, y)) return 0;
        Chunk c = chunks.get(Chunk.key(x >> Chunk.SHIFT, y >> Chunk.SHIFT));
        return c == null ? 0 : c.owner[(y & 31) * 32 + (x & 31)];
    }

    public int ownerCityAt(int x, int y) {
        if (outside(x, y)) return 0;
        Chunk c = chunks.get(Chunk.key(x >> Chunk.SHIFT, y >> Chunk.SHIFT));
        return c == null ? 0 : c.ownerCity[(y & 31) * 32 + (x & 31)];
    }

    public void setFeat(int x, int y, int feat, int aux) {
        if (outside(x, y)) return;
        Chunk c = chunk(x >> Chunk.SHIFT, y >> Chunk.SHIFT);
        int i = (y & 31) * 32 + (x & 31);
        c.feat[i] = (byte) feat;
        c.aux[i] = (byte) aux;
        if (feat >= Terrain.FARM) c.hasClaims = true;
        c.touch();
        int lx = x & 31, ly = y & 31;
        if (lx == 0) touchIf(c.cx - 1, c.cy);
        if (lx == 31) touchIf(c.cx + 1, c.cy);
        if (ly == 0) touchIf(c.cx, c.cy - 1);
        if (ly == 31) touchIf(c.cx, c.cy + 1);
    }

    private void touchIf(int cx, int cy) {
        Chunk c = peek(cx, cy);
        if (c != null) c.touch();
    }

    public boolean isCoastalTile(int x, int y) {
        return Terrain.isWater(terrainAt(x + 1, y)) || Terrain.isWater(terrainAt(x - 1, y))
                || Terrain.isWater(terrainAt(x, y + 1)) || Terrain.isWater(terrainAt(x, y - 1));
    }

    public boolean touchesSea(int x, int y) {
        int t;
        t = terrainAt(x + 1, y);
        if (t <= Terrain.SHALLOW) return true;
        t = terrainAt(x - 1, y);
        if (t <= Terrain.SHALLOW) return true;
        t = terrainAt(x, y + 1);
        if (t <= Terrain.SHALLOW) return true;
        t = terrainAt(x, y - 1);
        return t <= Terrain.SHALLOW;
    }

    // ================= cities & territory =================

    private static long gkey(int gx, int gy) {
        return ((long) gx << 32) ^ (gy & 0xffffffffL);
    }

    public ArrayList<City> citiesNear(int x, int y, int r) {
        ArrayList<City> out = new ArrayList<>();
        int g0x = (x - r) >> 5, g1x = (x + r) >> 5, g0y = (y - r) >> 5, g1y = (y + r) >> 5;
        long r2 = (long) r * r;
        for (int gy = g0y; gy <= g1y; gy++)
            for (int gx = g0x; gx <= g1x; gx++) {
                ArrayList<City> l = grid.get(gkey(gx, gy));
                if (l == null) continue;
                for (City c : l) {
                    long dx = c.x - x, dy = c.y - y;
                    if (dx * dx + dy * dy <= r2) out.add(c);
                }
            }
        return out;
    }

    public City cityAt(int x, int y) {
        ArrayList<City> l = grid.get(gkey(x >> 5, y >> 5));
        if (l == null) return null;
        for (City c : l) if (c.x == x && c.y == y) return c;
        return null;
    }

    public City addCity(Nation n, int x, int y, String name, boolean capital) {
        City c = new City();
        c.id = nextCityId++;
        c.nation = n.id;
        c.x = x;
        c.y = y;
        c.name = name;
        c.capital = capital;
        c.founded = turn;
        c.coastal = touchesSea(x, y);
        cities.put(c.id, c);
        grid.computeIfAbsent(gkey(x >> 5, y >> 5), k -> new ArrayList<>()).add(c);
        setFeat(x, y, Terrain.CITY, 0);
        claim(c);
        return c;
    }

    /** Insert an already-built city (used when loading a save). */
    public void registerCity(City c) {
        cities.put(c.id, c);
        grid.computeIfAbsent(gkey(c.x >> 5, c.y >> 5), k -> new ArrayList<>()).add(c);
        nextCityId = Math.max(nextCityId, c.id + 1);
        setFeat(c.x, c.y, Terrain.CITY, 0);
        claim(c);
    }

    /** A freshly generated copy of a chunk, for diffing against player changes. */
    public Chunk pristine(int cx, int cy) {
        return generate(cx, cy);
    }

    public ArrayList<Chunk> claimedChunks() {
        ArrayList<Chunk> l = new ArrayList<>();
        for (Chunk c : chunks.values()) if (c.hasClaims) l.add(c);
        return l;
    }

    public void removeCity(City c) {
        cities.remove(c.id);
        ArrayList<City> l = grid.get(gkey(c.x >> 5, c.y >> 5));
        if (l != null) l.remove(c);
        for (int[] b : c.blds) setFeat(b[0], b[1], Terrain.NONE, 0);
        setFeat(c.x, c.y, Terrain.NONE, 0);
        releaseTiles(c);
        for (City o : citiesNear(c.x, c.y, 45)) claim(o);
    }

    public void claim(City c) {
        int R = c.claimRadius();
        double fac = c.claimFactor();
        ArrayList<Chunk> touched = new ArrayList<>();
        Chunk last = null;
        for (int y = c.y - R; y <= c.y + R; y++) {
            for (int x = c.x - R; x <= c.x + R; x++) {
                double dx = x - c.x, dy = y - c.y;
                double d = Math.sqrt(dx * dx + dy * dy);
                if (d > R || outside(x, y)) continue;
                Chunk ch = (last != null && last.cx == (x >> 5) && last.cy == (y >> 5)) ? last : chunk(x >> 5, y >> 5);
                last = ch;
                int i = (y & 31) * 32 + (x & 31);
                byte t = ch.terrain[i];
                if (t == Terrain.DEEP && d > 3) continue;
                if (t == Terrain.SHALLOW && d > R * 0.65) continue;
                float s = (float) (d / fac);
                if (s < ch.score[i]) {
                    ch.score[i] = s;
                    ch.owner[i] = (short) c.nation;
                    ch.ownerCity[i] = c.id;
                    ch.hasClaims = true;
                    if (!touched.contains(ch)) touched.add(ch);
                }
            }
        }
        for (Chunk ch : touched) touchAround(ch);
    }

    private void touchAround(Chunk ch) {
        for (int dy = -1; dy <= 1; dy++)
            for (int dx = -1; dx <= 1; dx++) {
                Chunk n = peek(ch.cx + dx, ch.cy + dy);
                if (n != null) n.touch();
            }
    }

    private void releaseTiles(City c) {
        int R = c.claimRadius();
        for (int y = c.y - R; y <= c.y + R; y++)
            for (int x = c.x - R; x <= c.x + R; x++) {
                if (outside(x, y)) continue;
                Chunk ch = peek(x >> 5, y >> 5);
                if (ch == null) continue;
                int i = (y & 31) * 32 + (x & 31);
                if (ch.ownerCity[i] == c.id) {
                    ch.owner[i] = 0;
                    ch.ownerCity[i] = 0;
                    ch.score[i] = Float.MAX_VALUE;
                    ch.touch();
                }
            }
    }

    /** Hand a city (and its tiles) to another nation. */
    public void transferCity(City c, Nation to) {
        c.nation = to.id;
        int R = c.claimRadius();
        for (int y = c.y - R; y <= c.y + R; y++)
            for (int x = c.x - R; x <= c.x + R; x++) {
                if (outside(x, y)) continue;
                Chunk ch = peek(x >> 5, y >> 5);
                if (ch == null) continue;
                int i = (y & 31) * 32 + (x & 31);
                if (ch.ownerCity[i] == c.id) ch.owner[i] = (short) to.id;
            }
        for (int cy = (c.y - R) >> 5; cy <= (c.y + R) >> 5; cy++)
            for (int cx = (c.x - R) >> 5; cx <= (c.x + R) >> 5; cx++) {
                Chunk ch = peek(cx, cy);
                if (ch != null) touchAround(ch);
            }
    }

    /** Refresh a city's claim after it grew a level. */
    public void reclaim(City c) {
        claim(c);
    }

    public void log(String text, int nation, boolean important) {
        log.add(new LogEntry(turn, nation, text, important));
        if (log.size() > 400) log.subList(0, 100).clear();
    }

    public void fx(double x, double y, int type, int color) {
        if (fx.size() < 200) fx.add(new float[]{(float) x, (float) y, type, color});
    }

    public int year() {
        return 1 + turn / 12;
    }

    public Nation nation(int id) {
        return nations.get(id);
    }

    public static double dist(double ax, double ay, double bx, double by) {
        double dx = ax - bx, dy = ay - by;
        return Math.sqrt(dx * dx + dy * dy);
    }
}
