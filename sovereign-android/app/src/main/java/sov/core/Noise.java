package sov.core;

/** Hash-based gradient noise. Non-periodic, so it works for an infinite world. */
public final class Noise {
    private final int seed;

    public Noise(long seed) {
        this.seed = (int) (seed ^ (seed >>> 32)) * 0x9E3779B1;
    }

    private int hash(int x, int y) {
        int h = x * 374761393 + y * 668265263 + seed;
        h = (h ^ (h >>> 13)) * 1274126177;
        return h ^ (h >>> 16);
    }

    private static double fade(double t) {
        return t * t * t * (t * (t * 6 - 15) + 10);
    }

    private static double grad(int h, double x, double y) {
        switch ((h >>> 3) & 7) {
            case 0: return x + y;
            case 1: return -x + y;
            case 2: return x - y;
            case 3: return -x - y;
            case 4: return x * 1.4;
            case 5: return -x * 1.4;
            case 6: return y * 1.4;
            default: return -y * 1.4;
        }
    }

    public double noise(double x, double y) {
        int xi = (int) Math.floor(x), yi = (int) Math.floor(y);
        double xf = x - xi, yf = y - yi;
        double u = fade(xf), v = fade(yf);
        double a = grad(hash(xi, yi), xf, yf);
        double b = grad(hash(xi + 1, yi), xf - 1, yf);
        double c = grad(hash(xi, yi + 1), xf, yf - 1);
        double d = grad(hash(xi + 1, yi + 1), xf - 1, yf - 1);
        double x1 = a + (b - a) * u;
        double x2 = c + (d - c) * u;
        return x1 + (x2 - x1) * v;
    }

    /** Fractal noise, roughly in [-1, 1] (typically +-0.5). */
    public double fbm(double x, double y, int oct, double lac, double gain) {
        double s = 0, a = 1, f = 1, n = 0;
        for (int i = 0; i < oct; i++) {
            s += a * noise(x * f + i * 17.3, y * f + i * 91.7);
            n += a;
            a *= gain;
            f *= lac;
        }
        return s / n;
    }

    /** Cheap deterministic per-tile random in [0,1). */
    public static double rand01(int x, int y, int salt) {
        int h = x * 73856093 ^ y * 19349663 ^ salt * 83492791;
        h = (h ^ (h >>> 15)) * 0x2C1B3C6D;
        h = (h ^ (h >>> 12)) * 0x297A2D39;
        h ^= h >>> 15;
        return (h & 0xFFFFFF) / (double) 0x1000000;
    }

    public static int randInt(int x, int y, int salt) {
        int h = x * 73856093 ^ y * 19349663 ^ salt * 83492791;
        h = (h ^ (h >>> 15)) * 0x2C1B3C6D;
        h = (h ^ (h >>> 12)) * 0x297A2D39;
        return h ^ (h >>> 15);
    }
}
