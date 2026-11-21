package sov.render;

import sov.core.*;

import sov.awt.image.BufferedImage;
import java.util.ArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/** Async sampled overview map used for the minimap and the new-game preview. */
public final class MapImage {
    public volatile BufferedImage img;
    public volatile double cx, cy, tpp;
    public volatile boolean busy;
    private final AtomicInteger gen = new AtomicInteger();
    private final ExecutorService ex = Executors.newFixedThreadPool(2, r -> {
        Thread t = new Thread(r, "mapimage");
        t.setDaemon(true);
        return t;
    });

    public void shutdown() {
        ex.shutdownNow();
    }

    /** points: x, y, rgb, capital(0/1) snapshots taken on the game thread. */
    public void request(World w, double cx, double cy, double tpp, int px, boolean shade, ArrayList<int[]> points) {
        final int g = gen.incrementAndGet();
        busy = true;
        ex.submit(() -> {
            try {
                BufferedImage im = new BufferedImage(px, px, BufferedImage.TYPE_INT_RGB);
                int[] row = new int[px];
                for (int j = 0; j < px; j++) {
                    if (gen.get() != g) return;
                    double y = cy + (j - px / 2.0 + 0.5) * tpp;
                    for (int i = 0; i < px; i++) {
                        double x = cx + (i - px / 2.0 + 0.5) * tpp;
                        int xi = (int) Math.floor(x), yi = (int) Math.floor(y);
                        if (!w.inBounds(xi, yi)) {
                            row[i] = 0x0a1830;
                            continue;
                        }
                        int t = w.terrainAt(xi, yi);
                        int col = Terrain.color(t);
                        if (shade && Terrain.isLand(t)) {
                            double d = Math.max(1, tpp * 0.7);
                            double diff = w.elevation((int) (x + d), (int) (y + d)) - w.elevation((int) (x - d), (int) (y - d));
                            double k = 1 + Math.max(-0.3, Math.min(0.3, diff / (2 * d) * 2.2));
                            col = Pix.shade(0xFF000000 | col, k) & 0xFFFFFF;
                        } else if (t == Terrain.DEEP) {
                            col = Pix.shade(0xFF000000 | col, 0.92) & 0xFFFFFF;
                        }
                        int o = w.ownerAt(xi, yi);
                        if (o != 0) {
                            Nation n = w.nation(o);
                            if (n != null) col = Pix.mix(0xFF000000 | col, 0xFF000000 | n.color, 0.55) & 0xFFFFFF;
                        }
                        row[i] = col;
                    }
                    im.setRGB(0, j, px, 1, row, 0, px);
                }
                if (gen.get() != g) return;
                if (points != null) {
                    for (int[] p : points) {
                        int sx = (int) Math.floor((p[0] - cx) / tpp + px / 2.0), sy = (int) Math.floor((p[1] - cy) / tpp + px / 2.0);
                        int r = p[3] == 1 ? 2 : 1;
                        for (int dy = -r; dy <= r; dy++)
                            for (int dx = -r; dx <= r; dx++) {
                                int xx = sx + dx, yy = sy + dy;
                                if (xx >= 0 && yy >= 0 && xx < px && yy < px) im.setRGB(xx, yy, (dx == -r || dy == -r || dx == r || dy == r) ? 0x101010 : p[2]);
                            }
                    }
                }
                this.cx = cx;
                this.cy = cy;
                this.tpp = tpp;
                this.img = im;
            } finally {
                if (gen.get() == g) busy = false;
            }
        });
    }
}
