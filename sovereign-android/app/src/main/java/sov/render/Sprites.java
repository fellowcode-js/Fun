package sov.render;

import java.util.Random;

import static sov.render.Pix.*;

/** All pixel art is generated in code, so there are no asset files to ship. */
public final class Sprites {
    private Sprites() {}

    public static final int T = 16;
    public static final int[][] OAK = new int[8][];
    public static final int[][] JUNGLE = new int[4][];
    public static final int[][] ACACIA = new int[3][];
    public static final int[][] SWAMPTREE = new int[2][];
    public static final int[][] PINE = new int[4][];
    public static final int[][] SNOWPINE = new int[3][];
    public static final int[][] PALM = new int[3][];
    public static final int[][] CACTUS = new int[3][];
    public static final int[][] ROCKS = new int[4][];
    public static final int[][] ORE = new int[2][];
    public static final int[][] MOUNTAIN = new int[6][];
    public static final int[][] PEAK = new int[4][];
    /** [style 0..2][roof 0..5] */
    public static final int[][][] HOUSE = new int[3][6][];
    public static final int[][] FARM = new int[3][];
    public static int[] MINE, LUMBER, TOWER;
    /** Dock sprites for water on S, W, N, E. */
    public static final int[][] DOCK = new int[4][];
    public static final int[] ROOFS = {0xb5483a, 0x3f6fb5, 0x8a5a36, 0x4a8a58, 0x7a4aa0, 0xc9902e};
    public static sov.awt.image.BufferedImage[] CITY = new sov.awt.image.BufferedImage[6];

    static {
        for (int i = 0; i < 6; i++) OAK[i] = oak(i % 2 == 0 ? 0 : 3, i, false);
        OAK[6] = oak(2, 61, false);
        OAK[7] = oak(3, 62, false);
        for (int i = 0; i < JUNGLE.length; i++) JUNGLE[i] = oak(1, 100 + i, true);
        for (int i = 0; i < ACACIA.length; i++) ACACIA[i] = acacia(i);
        for (int i = 0; i < SWAMPTREE.length; i++) SWAMPTREE[i] = swampTree(i);
        for (int i = 0; i < PINE.length; i++) PINE[i] = pine(i, false);
        for (int i = 0; i < SNOWPINE.length; i++) SNOWPINE[i] = pine(i + 7, true);
        for (int i = 0; i < PALM.length; i++) PALM[i] = palm(i);
        for (int i = 0; i < CACTUS.length; i++) CACTUS[i] = cactus(i);
        for (int i = 0; i < ROCKS.length; i++) ROCKS[i] = rocks(i);
        ORE[0] = ore(false);
        ORE[1] = ore(true);
        for (int i = 0; i < MOUNTAIN.length; i++) MOUNTAIN[i] = mountain(i, false);
        for (int i = 0; i < PEAK.length; i++) PEAK[i] = mountain(i, true);
        for (int s = 0; s < 3; s++) for (int r = 0; r < 6; r++) HOUSE[s][r] = house(s, ROOFS[r]);
        for (int i = 0; i < FARM.length; i++) FARM[i] = farm(i);
        MINE = mine();
        LUMBER = lumber();
        TOWER = tower();
        Pix d = dockBase();
        DOCK[0] = d.p;
        d = d.rot90();
        DOCK[1] = d.p;
        d = d.rot90();
        DOCK[2] = d.p;
        d = d.rot90();
        DOCK[3] = d.p;
        for (int l = 1; l <= 5; l++) CITY[l] = city(l).toImage();
    }

    private static final int SHADOW = argb(64, 0, 0, 20);

    private static int[] oak(int pal, int seed, boolean big) {
        int[][] P = {
                {0x2f6e2c, 0x3f8a35, 0x5fae43, 0x8ad45c},
                {0x1f5e34, 0x2d7d44, 0x45a05a, 0x72cc80},
                {0x8a3d1f, 0xb5592a, 0xd9803a, 0xf0b052},
                {0x2a5e2e, 0x377c3b, 0x52a04c, 0x7cc86a}};
        int[] c = P[pal];
        Random r = new Random(seed * 7919L + 13);
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 14, 5.5, 2, SHADOW);
        t.rect(7, 10, 2, 5, rgb(0x5a3b22));
        t.rect(8, 11, 1, 4, rgb(0x46301c));
        double[][] blobs = big
                ? new double[][]{{8, 6, 5.8}, {4.5, 8.5, 3.9}, {11.5, 8.5, 3.9}, {8, 9.5, 4}}
                : new double[][]{{8, 6, 5}, {4.8, 8.3, 3.5}, {11.2, 8.3, 3.5}, {8, 9, 3.4}};
        for (double[] b : blobs) t.disc(b[0], b[1], b[2], rgb(c[0]));
        for (double[] b : blobs) t.disc(b[0] - 0.8, b[1] - 0.9, b[2] - 1.1, rgb(c[1]));
        for (double[] b : blobs) t.disc(b[0] - 1.6, b[1] - 1.9, b[2] - 2.4, rgb(c[2]));
        t.disc(6.4, 4.3, 1.7, rgb(c[3]));
        for (int i = 0; i < 14; i++) {
            int x = 3 + r.nextInt(10), y = 2 + r.nextInt(9);
            if ((t.get(x, y) >>> 24) == 255 && y < 12)
                t.set(x, y, r.nextBoolean() ? rgb(c[0]) : rgb(c[2]));
        }
        t.outline(rgb(Pix.shade(rgb(c[0]), 0.55)));
        return t.p;
    }

    private static int[] acacia(int seed) {
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 14, 5, 1.6, SHADOW);
        int tr = rgb(0x6b4a2a);
        t.line(8, 14, 8, 9, tr);
        t.line(8, 10, 4, 7, tr);
        t.line(8, 10, 12, 7, tr);
        t.ellipse(8, 6.2, 7, 2.7, rgb(0x5d7a2a));
        t.ellipse(7.2, 5.6, 5.8, 2.0, rgb(0x7f9b36));
        t.ellipse(6.2, 5.0, 3.5, 1.2, rgb(0xa3bd4a));
        t.outline(rgb(0x34461a));
        return t.p;
    }

    private static int[] swampTree(int seed) {
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 14, 5.5, 1.8, argb(70, 0, 20, 10));
        t.rect(7, 9, 2, 6, rgb(0x4a3a24));
        t.disc(8, 6, 5, rgb(0x2f4f2a));
        t.disc(5, 8, 3, rgb(0x2f4f2a));
        t.disc(11, 8, 3, rgb(0x2f4f2a));
        t.disc(7, 5, 3.5, rgb(0x3d6535));
        t.disc(6, 4, 1.8, rgb(0x55823f));
        Random r = new Random(seed + 5);
        for (int i = 0; i < 6; i++) {
            int x = 3 + r.nextInt(10), y0 = 9 + r.nextInt(2);
            t.line(x, y0, x, y0 + 2 + r.nextInt(2), rgb(0x7b9a64));
        }
        t.outline(rgb(0x1c3218));
        return t.p;
    }

    private static int[] pine(int seed, boolean snow) {
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 14.2, 5, 1.6, SHADOW);
        t.rect(7, 12, 2, 3, rgb(0x5a3b22));
        int dk = snow ? 0x2d5a46 : 0x24602f, md = snow ? 0x3b7258 : 0x2f7a3a, lt = snow ? 0x55957a : 0x45a04a;
        int[][] tiers = {{8, 1, 6, 3}, {8, 4, 10, 4}, {8, 7, 13, 5}};
        for (int[] ti : tiers) {
            int ax = ti[0], ay = ti[1], by = ti[2], hw = ti[3];
            for (int y = ay; y <= by; y++) {
                double half = (y - ay + 1) * (double) hw / (by - ay + 1);
                for (int x = (int) Math.round(ax - half); x <= (int) Math.round(ax + half); x++) {
                    int col = x < ax - half * 0.25 ? lt : (x > ax + half * 0.35 ? dk : md);
                    t.set(x, y, rgb(col));
                }
            }
        }
        if (snow) {
            for (int[] ti : tiers) {
                int ax = ti[0], ay = ti[1];
                t.set(ax, ay, rgb(0xf4f8ff));
                t.set(ax - 1, ay + 1, rgb(0xf4f8ff));
                t.set(ax, ay + 1, rgb(0xdfe9f4));
                t.set(ax + 1, ay + 1, rgb(0xdfe9f4));
                t.set(ax - 2, ay + 2, rgb(0xeef4fb));
            }
        }
        t.outline(rgb(0x163a1e));
        return t.p;
    }

    private static int[] palm(int seed) {
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 14.3, 4.5, 1.5, SHADOW);
        Random r = new Random(seed + 77);
        int lean = r.nextBoolean() ? 1 : -1;
        int tx = 8 + lean;
        t.line(8, 14, 8, 11, rgb(0x7a5a30));
        t.line(8, 11, tx, 7, rgb(0x8a6a38));
        t.line(8, 11, tx, 8, rgb(0x6a4a28));
        int[] g = {rgb(0x2f8a3a), rgb(0x48ad4a)};
        int[][] fr = {{-5, 1}, {5, 1}, {-4, 4}, {4, 4}, {0, -4}, {-2, -3}, {2, -3}};
        for (int[] f : fr) {
            t.line(tx, 7, tx + f[0], 7 + f[1] - 1, g[0]);
            t.line(tx, 6, tx + f[0] / 2, 6 + (f[1] - 1) / 2 - 1, g[1]);
        }
        t.set(tx, 8, rgb(0x5a3a1c));
        t.set(tx + 1, 8, rgb(0x5a3a1c));
        t.outline(rgb(0x1a4a22));
        return t.p;
    }

    private static int[] cactus(int seed) {
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 14, 4, 1.4, SHADOW);
        int a = rgb(0x3f8f3a), b = rgb(0x5fb050), d = rgb(0x2a6a2a);
        t.rect(7, 4, 3, 10, a);
        t.rect(7, 4, 1, 10, b);
        t.rect(9, 4, 1, 10, d);
        t.rect(4, 7, 2, 4, a);
        t.rect(4, 9, 4, 2, a);
        t.rect(11, 5, 2, 4, a);
        t.rect(9, 7, 4, 2, a);
        t.set(8, 3, rgb(0xe65a8a));
        t.outline(rgb(0x1c4a1e));
        return t.p;
    }

    private static int[] rocks(int seed) {
        Pix t = new Pix(16, 16);
        Random r = new Random(seed * 31 + 3);
        t.ellipse(8.5, 13.5, 6, 2, SHADOW);
        int n = 1 + r.nextInt(3);
        for (int i = 0; i < n; i++) {
            double cx = 5 + r.nextInt(7), cy = 10 + r.nextInt(3), rr = 2 + r.nextDouble() * 2;
            t.disc(cx, cy, rr, rgb(0x6f6a64));
            t.disc(cx - 0.6, cy - 0.7, rr - 0.8, rgb(0x938d84));
            t.disc(cx - 1, cy - 1.2, rr - 1.8, rgb(0xb4aea4));
        }
        t.outline(rgb(0x3a3631));
        return t.p;
    }

    private static int[] ore(boolean gold) {
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 13.5, 6, 2, SHADOW);
        t.disc(8, 10, 4.2, rgb(0x5f5a54));
        t.disc(7.4, 9.4, 3.4, rgb(0x827c72));
        int s = gold ? 0xffd23a : 0xd9783a, s2 = gold ? 0xfff0a0 : 0xf0a064;
        int[][] sp = {{6, 8}, {9, 9}, {7, 11}, {10, 11}, {8, 7}};
        for (int i = 0; i < sp.length; i++) {
            t.set(sp[i][0], sp[i][1], rgb(i % 2 == 0 ? s : s2));
        }
        t.set(6, 9, rgb(s2));
        t.outline(rgb(0x2f2c28));
        return t.p;
    }

    private static int[] mountain(int v, boolean snow) {
        Random r = new Random(v * 977L + (snow ? 31 : 0));
        Pix t = new Pix(16, 16);
        t.ellipse(8, 14, 7.5, 2.2, argb(70, 10, 10, 30));
        int light = 0xb2aa9a, mid = 0x8d857a, dark = 0x625c54;
        int ax = 7 + r.nextInt(3), ay = 1 + r.nextInt(3), by = 14;
        double hw = 6.6 + r.nextInt(2) * 0.6;
        if (v % 2 == 1) {
            // secondary shoulder peak
            int bx = ax < 8 ? 12 : 3, bay = ay + 5;
            for (int y = bay; y <= by; y++) {
                double half = (y - bay + 0.5) * 4.0 / (by - bay + 1);
                for (int x = (int) Math.round(bx - half); x <= (int) Math.round(bx + half); x++)
                    t.set(x, y, rgb(x < bx ? mid : dark));
            }
        }
        for (int y = ay; y <= by; y++) {
            double f = (y - ay) / (double) (by - ay);
            double half = f * hw + 0.6;
            int ridge = ax + (int) Math.round(Math.sin(y * 1.1 + v) * 1.1);
            for (int x = (int) Math.round(ax - half); x <= (int) Math.round(ax + half); x++) {
                int c = x < ridge ? light : (x == ridge ? mid : dark);
                if (x > ridge && r.nextInt(6) == 0) c = mid;
                if (x < ridge && r.nextInt(7) == 0) c = mid;
                t.set(x, y, rgb(c));
            }
        }
        for (int i = 0; i < 4; i++) {
            int x = ax - 3 + r.nextInt(7), y = ay + 4 + r.nextInt(8);
            t.line(x, y, x + (r.nextBoolean() ? 1 : -1), y + 2, rgb(0x4a453e));
        }
        if (snow) {
            int capH = 5 + r.nextInt(2);
            for (int y = ay; y < ay + capH; y++) {
                double half = (y - ay) / (double) (by - ay) * hw + 0.6;
                int ridge = ax + (int) Math.round(Math.sin(y * 1.1 + v) * 1.1);
                int jag = y == ay + capH - 1 ? 2 : (y == ay + capH - 2 ? 1 : 0);
                for (int x = (int) Math.round(ax - half); x <= (int) Math.round(ax + half); x++) {
                    if (jag > 0 && ((x + y * 3 + v) % (jag + 1) == 0)) continue;
                    t.set(x, y, rgb(x < ridge ? 0xffffff : (x == ridge ? 0xe6eef8 : 0xbccbe0)));
                }
            }
        }
        t.outline(rgb(0x37332d));
        return t.p;
    }

    private static int[] house(int style, int roof) {
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 13.8, 6, 2, SHADOW);
        int wall = rgb(0xe8dcc0), wallS = rgb(0xc8b894), door = rgb(0x4a3020), win = rgb(0x6fa8d8);
        int rl = rgb(Pix.shade(rgb(roof), 1.25)), rm = rgb(roof), rd = rgb(Pix.shade(rgb(roof), 0.7));
        if (style == 0) { // hut
            t.rect(4, 9, 8, 5, wall);
            t.rect(10, 9, 2, 5, wallS);
            t.rect(7, 11, 2, 3, door);
            int thatch = 0xcfae5a;
            t.tri(8, 3, 2, 10, 14, 10, rgb(thatch));
            t.tri(8, 3, 8, 10, 14, 10, rgb(Pix.shade(rgb(thatch), 0.78)));
            for (int i = 0; i < 6; i++) t.set(4 + i * 2, 9, rgb(0xa88a40));
            t.outline(rgb(0x3a2a18));
        } else if (style == 1) { // house
            t.rect(3, 8, 10, 6, wall);
            t.rect(10, 8, 3, 6, wallS);
            t.rect(7, 10, 2, 4, door);
            t.rect(4, 10, 2, 2, win);
            t.rect(10, 10, 2, 2, win);
            t.tri(8, 2, 1, 9, 15, 9, rm);
            t.tri(8, 2, 8, 9, 15, 9, rd);
            t.line(8, 2, 1, 9, rl);
            t.rect(11, 2, 2, 3, rgb(0x8a8a90));
            t.outline(rgb(0x2f2218));
        } else { // tall
            t.rect(4, 6, 9, 8, wall);
            t.rect(10, 6, 3, 8, wallS);
            t.rect(7, 11, 2, 3, door);
            t.rect(5, 8, 2, 2, win);
            t.rect(10, 8, 2, 2, win);
            t.rect(5, 11, 1, 2, win);
            t.tri(8.5, 0, 2, 7, 15, 7, rm);
            t.tri(8.5, 0, 8.5, 7, 15, 7, rd);
            t.line(8, 0, 2, 7, rl);
            t.rect(12, 1, 2, 3, rgb(0x8a8a90));
            t.outline(rgb(0x2f2218));
        }
        return t.p;
    }

    private static int[] farm(int v) {
        Pix t = new Pix(16, 16);
        int soil = 0x8c6a3c, soil2 = 0x735430;
        int[][] crops = {{0x86c43c, 0x5f9a2a}, {0xe3c04a, 0xc29a30}, {0x6fb04a, 0x4a8a34}};
        t.rect(0, 0, 16, 16, rgb(soil));
        for (int x = 1; x < 15; x += 3) {
            t.rect(x, 1, 2, 14, rgb(crops[v][0]));
            t.rect(x + 1, 1, 1, 14, rgb(crops[v][1]));
            for (int y = 2; y < 15; y += 3) t.set(x, y, rgb(Pix.shade(rgb(crops[v][0]), 1.2)));
        }
        for (int x = 0; x < 16; x++) {
            t.set(x, 0, rgb(soil2));
            t.set(x, 15, rgb(soil2));
        }
        for (int y = 0; y < 16; y++) {
            t.set(0, y, rgb(soil2));
            t.set(15, y, rgb(soil2));
        }
        int post = rgb(0x5a3b22);
        for (int[] c : new int[][]{{0, 0}, {15, 0}, {0, 15}, {15, 15}, {7, 0}, {7, 15}}) t.set(c[0], c[1], post);
        return t.p;
    }

    private static int[] mine() {
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 13.5, 7, 2.4, SHADOW);
        t.disc(8, 11, 6, rgb(0x5f5a54));
        t.disc(7.3, 10.3, 5, rgb(0x827c72));
        t.disc(6.5, 9, 3, rgb(0x9a948a));
        t.rect(5, 8, 6, 6, rgb(0x2a2420));
        t.rect(5, 8, 1, 6, rgb(0x6a4a28));
        t.rect(10, 8, 1, 6, rgb(0x6a4a28));
        t.rect(5, 7, 6, 1, rgb(0x7a5a30));
        t.rect(7, 12, 2, 2, rgb(0x6b6258));
        t.set(13, 12, rgb(0xd9783a));
        t.set(14, 13, rgb(0xffd23a));
        t.set(3, 13, rgb(0xd9783a));
        t.outline(rgb(0x2a2622));
        return t.p;
    }

    private static int[] lumber() {
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 13.8, 7, 2, SHADOW);
        t.rect(2, 7, 9, 7, rgb(0x9a6a3a));
        for (int y = 8; y < 14; y += 2) t.rect(2, y, 9, 1, rgb(0x7a4f2a));
        t.tri(6.5, 2, 0.5, 8, 12.5, 8, rgb(0x5f4a2a));
        t.tri(6.5, 2, 6.5, 8, 12.5, 8, rgb(0x493820));
        t.rect(5, 10, 2, 4, rgb(0x3a2818));
        for (int i = 0; i < 3; i++) {
            t.rect(11, 11 + i * 1, 4, 1, rgb(0xb98a52));
            t.set(14, 11 + i, rgb(0xe0c08a));
        }
        t.outline(rgb(0x2f2014));
        return t.p;
    }

    private static int[] tower() {
        Pix t = new Pix(16, 16);
        t.ellipse(8.5, 14, 6, 2, SHADOW);
        t.rect(4, 4, 8, 10, rgb(0x9a9a9a));
        t.rect(10, 4, 2, 10, rgb(0x76767a));
        t.rect(4, 4, 8, 1, rgb(0xc4c4c4));
        for (int x = 4; x < 12; x += 3) t.rect(x, 2, 2, 2, rgb(0x9a9a9a));
        t.rect(7, 7, 2, 3, rgb(0x2a2a30));
        t.rect(7, 11, 2, 3, rgb(0x4a3a2a));
        for (int y = 5; y < 14; y += 3) for (int x = 4; x < 12; x += 3) t.set(x, y, rgb(0x6a6a70));
        t.line(8, 0, 8, 2, rgb(0x4a3a2a));
        t.rect(9, 0, 3, 2, rgb(0xd04030));
        t.outline(rgb(0x2a2a2e));
        return t.p;
    }

    private static Pix dockBase() {
        Pix t = new Pix(16, 16);
        // water is to the south: pier running south from the shore
        for (int y = 6; y < 16; y++) {
            for (int x = 6; x < 10; x++) t.set(x, y, rgb(((y + (x & 1)) & 1) == 0 ? 0xa8764a : 0x8a5c36));
            t.set(5, y, rgb(0x5a3b22));
            t.set(10, y, rgb(0x5a3b22));
        }
        for (int y = 7; y < 16; y += 4) {
            t.set(5, y, rgb(0x3a2814));
            t.set(10, y, rgb(0x3a2814));
        }
        t.rect(2, 3, 5, 4, rgb(0x8a5c36));
        t.tri(4.5, 0.5, 1, 4, 8, 4, rgb(0x6a4a30));
        t.rect(4, 5, 1, 2, rgb(0x2a1a10));
        t.rect(12, 5, 2, 3, rgb(0x8a5c36));
        t.rect(12, 4, 2, 1, rgb(0xc8a870));
        return t;
    }

    private static Pix city(int level) {
        Pix t = new Pix(24, 26);
        t.ellipse(12.5, 23, 10.5, 3, SHADOW);
        int stone = 0xa8a8ac, stoneS = 0x7c7c84, stoneL = 0xd0d0d4, wood = 0x8a5c36, woodD = 0x5f3d22;
        int roofR = 0xb5483a, roofB = 0x3f6fb5, gold = 0xf0c030;
        switch (level) {
            case 1: { // tents
                t.tri(8, 11, 2, 22, 14, 22, rgb(0xe8dcc0));
                t.tri(8, 11, 8, 22, 14, 22, rgb(0xc8b894));
                t.rect(7, 18, 2, 4, rgb(0x4a3020));
                t.tri(17, 14, 12, 22, 22, 22, rgb(0xd8c8a0));
                t.tri(17, 14, 17, 22, 22, 22, rgb(0xb8a880));
                t.line(8, 11, 8, 8, rgb(woodD));
                t.rect(9, 7, 3, 2, rgb(0xd04030));
                break;
            }
            case 2: { // wooden hall
                t.rect(4, 13, 16, 9, rgb(wood));
                for (int y = 14; y < 22; y += 2) t.rect(4, y, 16, 1, rgb(woodD));
                t.tri(12, 5, 1, 14, 23, 14, rgb(0x5f4a2a));
                t.tri(12, 5, 12, 14, 23, 14, rgb(0x493820));
                t.rect(10, 17, 4, 5, rgb(0x2f2014));
                t.rect(5, 16, 2, 2, rgb(0x6fa8d8));
                t.rect(17, 16, 2, 2, rgb(0x6fa8d8));
                t.line(12, 5, 12, 2, rgb(woodD));
                t.rect(13, 1, 4, 3, rgb(0xd04030));
                break;
            }
            case 3: { // stone keep
                t.rect(3, 13, 18, 9, rgb(stone));
                t.rect(15, 13, 6, 9, rgb(stoneS));
                t.rect(8, 7, 9, 7, rgb(stone));
                t.rect(13, 7, 4, 7, rgb(stoneS));
                for (int x = 3; x < 21; x += 4) t.rect(x, 11, 2, 2, rgb(stone));
                for (int x = 8; x < 17; x += 3) t.rect(x, 5, 2, 2, rgb(stone));
                t.rect(10, 17, 4, 5, rgb(0x3a2a1c));
                t.rect(11, 9, 2, 3, rgb(0x2a2a30));
                t.line(12, 5, 12, 1, rgb(woodD));
                t.rect(13, 0, 5, 3, rgb(0xd04030));
                break;
            }
            case 4: { // castle
                t.rect(2, 12, 20, 10, rgb(stone));
                t.rect(15, 12, 7, 10, rgb(stoneS));
                t.rect(2, 12, 20, 1, rgb(stoneL));
                for (int x : new int[]{1, 18}) {
                    t.rect(x, 6, 5, 16, rgb(stone));
                    t.rect(x + 3, 6, 2, 16, rgb(stoneS));
                    t.tri(x + 2.5, 1, x - 0.5, 7, x + 5.5, 7, rgb(roofB));
                }
                t.rect(8, 5, 8, 9, rgb(stoneL));
                t.rect(13, 5, 3, 9, rgb(stone));
                t.tri(12, 0, 7, 6, 17, 6, rgb(roofR));
                t.tri(12, 0, 12, 6, 17, 6, rgb(Pix.shade(rgb(roofR), 0.7)));
                t.rect(10, 16, 4, 6, rgb(0x2f2014));
                t.rect(11, 8, 2, 3, rgb(0x2a2a30));
                t.set(12, 0, rgb(gold));
                break;
            }
            default: { // grand palace
                t.rect(1, 13, 22, 9, rgb(stoneL));
                t.rect(16, 13, 7, 9, rgb(stone));
                for (int x : new int[]{0, 19}) {
                    t.rect(x, 5, 5, 17, rgb(stone));
                    t.rect(x + 3, 5, 2, 17, rgb(stoneS));
                    t.tri(x + 2.5, -1, x - 0.5, 6, x + 5.5, 6, rgb(roofB));
                    t.set(x + 2, 4, rgb(gold));
                }
                t.rect(6, 7, 12, 7, rgb(stoneL));
                t.rect(14, 7, 4, 7, rgb(stone));
                t.disc(12, 7, 5, rgb(gold));
                t.disc(11, 6, 3.5, rgb(0xffe27a));
                t.rect(12, 0, 1, 3, rgb(woodD));
                t.rect(13, 0, 4, 2, rgb(0xd04030));
                t.rect(10, 16, 4, 6, rgb(0x2f2014));
                t.rect(8, 9, 1, 3, rgb(0x2a2a30));
                t.rect(15, 9, 1, 3, rgb(0x2a2a30));
                for (int x = 3; x < 22; x += 3) t.set(x, 15, rgb(0x6fa8d8));
                break;
            }
        }
        t.outline(rgb(0x26221e));
        return t;
    }

    /** Select the sprite for a natural/built feature on a tile. Returns null for none. */
    public static int[] forFeature(int feat, int aux, int hash, int terrain) {
        int h = hash & 0x7fffffff;
        switch (feat) {
            case sov.core.Terrain.TREE:
                if (aux == 1 && terrain == sov.core.Terrain.JUNGLE) return JUNGLE[h % JUNGLE.length];
                if (aux == 1) return OAK[6 + (h & 1)];
                if (aux == 2) return ACACIA[h % ACACIA.length];
                if (aux == 3) return SWAMPTREE[h % SWAMPTREE.length];
                return OAK[h % 6];
            case sov.core.Terrain.PINE: return aux == 1 || terrain == sov.core.Terrain.SNOW ? SNOWPINE[h % SNOWPINE.length] : PINE[h % PINE.length];
            case sov.core.Terrain.PALM: return PALM[h % PALM.length];
            case sov.core.Terrain.CACTUS: return CACTUS[h % CACTUS.length];
            case sov.core.Terrain.ROCKS: return ROCKS[h % ROCKS.length];
            case sov.core.Terrain.ORE: return ORE[aux == 1 ? 1 : 0];
            case sov.core.Terrain.FARM: return FARM[aux % 3];
            case sov.core.Terrain.HOUSE: return HOUSE[Math.min(2, aux >> 3)][(aux & 7) % 6];
            case sov.core.Terrain.MINE: return MINE;
            case sov.core.Terrain.LUMBER: return LUMBER;
            case sov.core.Terrain.TOWER: return TOWER;
            case sov.core.Terrain.DOCK: return DOCK[aux & 3];
            default: return null;
        }
    }
}
