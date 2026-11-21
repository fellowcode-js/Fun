package sov.render;

/** Tiny ARGB pixel canvas used to draw procedural pixel art. */
public final class Pix {
    public final int w, h;
    public final int[] p;

    public Pix(int w, int h) {
        this.w = w;
        this.h = h;
        this.p = new int[w * h];
    }

    public static int argb(int a, int r, int g, int b) {
        return (a << 24) | (r << 16) | (g << 8) | b;
    }

    public static int rgb(int hex) {
        return 0xFF000000 | hex;
    }

    public static int mix(int a, int b, double t) {
        int aa = a >>> 24, ar = a >> 16 & 255, ag = a >> 8 & 255, ab = a & 255;
        int ba = b >>> 24, br = b >> 16 & 255, bg = b >> 8 & 255, bb = b & 255;
        return ((int) (aa + (ba - aa) * t) << 24) | ((int) (ar + (br - ar) * t) << 16)
                | ((int) (ag + (bg - ag) * t) << 8) | (int) (ab + (bb - ab) * t);
    }

    public static int shade(int c, double f) {
        int a = c >>> 24, r = (int) Math.min(255, (c >> 16 & 255) * f), g = (int) Math.min(255, (c >> 8 & 255) * f),
                b = (int) Math.min(255, (c & 255) * f);
        return (a << 24) | (r << 16) | (g << 8) | b;
    }

    /** Alpha-composite src over an opaque or translucent dst. */
    public static int over(int dst, int src) {
        int sa = src >>> 24;
        if (sa == 0) return dst;
        if (sa == 255) return src;
        int da = dst >>> 24;
        int inv = 255 - sa;
        int r = ((src >> 16 & 255) * sa + (dst >> 16 & 255) * inv) / 255;
        int g = ((src >> 8 & 255) * sa + (dst >> 8 & 255) * inv) / 255;
        int b = ((src & 255) * sa + (dst & 255) * inv) / 255;
        int a = Math.min(255, sa + da * inv / 255);
        return (a << 24) | (r << 16) | (g << 8) | b;
    }

    public void set(int x, int y, int c) {
        if (x >= 0 && y >= 0 && x < w && y < h) p[y * w + x] = c;
    }

    public int get(int x, int y) {
        return (x >= 0 && y >= 0 && x < w && y < h) ? p[y * w + x] : 0;
    }

    public void blend(int x, int y, int c) {
        if (x >= 0 && y >= 0 && x < w && y < h) p[y * w + x] = over(p[y * w + x], c);
    }

    public void rect(int x, int y, int rw, int rh, int c) {
        for (int j = y; j < y + rh; j++) for (int i = x; i < x + rw; i++) set(i, j, c);
    }

    public void disc(double cx, double cy, double r, int c) {
        for (int y = (int) Math.floor(cy - r); y <= (int) Math.ceil(cy + r); y++)
            for (int x = (int) Math.floor(cx - r); x <= (int) Math.ceil(cx + r); x++) {
                double dx = x + 0.5 - cx, dy = y + 0.5 - cy;
                if (dx * dx + dy * dy <= r * r) set(x, y, c);
            }
    }

    public void ellipse(double cx, double cy, double rx, double ry, int c) {
        for (int y = (int) Math.floor(cy - ry); y <= (int) Math.ceil(cy + ry); y++)
            for (int x = (int) Math.floor(cx - rx); x <= (int) Math.ceil(cx + rx); x++) {
                double dx = (x + 0.5 - cx) / rx, dy = (y + 0.5 - cy) / ry;
                if (dx * dx + dy * dy <= 1) blend(x, y, c);
            }
    }

    public void line(int x0, int y0, int x1, int y1, int c) {
        int dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0);
        int sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
        int err = dx + dy;
        while (true) {
            set(x0, y0, c);
            if (x0 == x1 && y0 == y1) break;
            int e2 = 2 * err;
            if (e2 >= dy) {
                err += dy;
                x0 += sx;
            }
            if (e2 <= dx) {
                err += dx;
                y0 += sy;
            }
        }
    }

    public void tri(double x0, double y0, double x1, double y1, double x2, double y2, int c) {
        int minX = (int) Math.floor(Math.min(x0, Math.min(x1, x2))), maxX = (int) Math.ceil(Math.max(x0, Math.max(x1, x2)));
        int minY = (int) Math.floor(Math.min(y0, Math.min(y1, y2))), maxY = (int) Math.ceil(Math.max(y0, Math.max(y1, y2)));
        double d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2);
        if (d == 0) return;
        for (int y = minY; y <= maxY; y++)
            for (int x = minX; x <= maxX; x++) {
                double px = x + 0.5, py = y + 0.5;
                double a = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / d;
                double b = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / d;
                double g = 1 - a - b;
                if (a >= -0.001 && b >= -0.001 && g >= -0.001) set(x, y, c);
            }
    }

    /** Add a 1px outline around opaque pixels (4-neighbourhood). */
    public void outline(int c) {
        int[] q = p.clone();
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++) {
                if ((q[y * w + x] >>> 24) != 0) continue;
                boolean n = (x > 0 && (q[y * w + x - 1] >>> 24) > 128) || (x < w - 1 && (q[y * w + x + 1] >>> 24) > 128)
                        || (y > 0 && (q[(y - 1) * w + x] >>> 24) > 128) || (y < h - 1 && (q[(y + 1) * w + x] >>> 24) > 128);
                if (n) p[y * w + x] = c;
            }
    }

    public Pix rot90() {
        Pix r = new Pix(h, w);
        for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) r.p[x * h + (h - 1 - y)] = p[y * w + x];
        return r;
    }

    public Pix flipX() {
        Pix r = new Pix(w, h);
        for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) r.p[y * w + (w - 1 - x)] = p[y * w + x];
        return r;
    }

    public sov.awt.image.BufferedImage toImage() {
        sov.awt.image.BufferedImage im = new sov.awt.image.BufferedImage(w, h, sov.awt.image.BufferedImage.TYPE_INT_ARGB);
        im.setRGB(0, 0, w, h, p, 0, w);
        return im;
    }
}
