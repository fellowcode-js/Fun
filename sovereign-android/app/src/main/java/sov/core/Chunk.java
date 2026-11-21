package sov.core;

/** A 32x32 block of tiles. Terrain is regenerable from the seed; claims and buildings are rebuilt from cities on load. */
public final class Chunk {
    public static final int S = 32;
    public static final int SHIFT = 5;
    public static final int N = S * S;

    public final int cx, cy;
    public final byte[] terrain = new byte[N];
    public final byte[] feat = new byte[N];
    public final byte[] aux = new byte[N];
    public final byte[] elev = new byte[N];
    public final byte[] shade = new byte[N];
    public final short[] owner = new short[N];
    public final int[] ownerCity = new int[N];
    public final float[] score = new float[N];
    /** Bumped whenever anything visible changes so views know to redraw. */
    public volatile int version = 1;
    public boolean hasClaims;
    public long lastUse;

    public Chunk(int cx, int cy) {
        this.cx = cx;
        this.cy = cy;
        java.util.Arrays.fill(score, Float.MAX_VALUE);
    }

    public static long key(int cx, int cy) {
        return ((long) cx << 32) ^ (cy & 0xffffffffL);
    }

    public static int idx(int lx, int ly) {
        return ly * S + lx;
    }

    public void touch() {
        version++;
    }
}
