package sov.render;

import sov.core.*;

import sov.awt.*;
import sov.awt.geom.AffineTransform;
import sov.awt.geom.Path2D;
import sov.awt.image.BufferedImage;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/** Camera plus everything that draws the world itself (terrain, borders, cities, armies, effects). */
public final class WorldView {
    public final World world;
    public double camX, camY, zoom = 16;
    public int vw = 1280, vh = 720;
    public double time;
    public static final double MIN_ZOOM = 2.0, MAX_ZOOM = 64;
    /** Zoom at which chunks switch to the detailed 16px art. */
    private static final double DETAIL_ZOOM = 6.5;

    private static final class CV {
        volatile BufferedImage detail;
        volatile int detailVer = -1;
        volatile boolean painting;
        BufferedImage over, tint, border;
        int overVer = -1;
        long used;
    }

    private static final class Fx {
        double x, y, age;
        int type, color;
    }

    private final HashMap<Long, CV> views = new HashMap<>();
    private final ExecutorService paint;
    private final AtomicInteger queued = new AtomicInteger();
    private int frame;
    private final ArrayList<Fx> fxs = new ArrayList<>();
    public int detailImages;

    public WorldView(World world) {
        this.world = world;
        int threads = Math.max(1, Math.min(3, Runtime.getRuntime().availableProcessors() - 1));
        paint = Executors.newFixedThreadPool(threads, r -> {
            Thread t = new Thread(r, "chunkpaint");
            t.setDaemon(true);
            t.setPriority(Thread.NORM_PRIORITY - 1);
            return t;
        });
    }

    public void shutdown() {
        paint.shutdownNow();
    }

    public boolean idle() {
        return queued.get() == 0;
    }

    // ---------- coordinates ----------
    public double sx(double wx) {
        return (wx - camX) * zoom + vw / 2.0;
    }

    public double sy(double wy) {
        return (wy - camY) * zoom + vh / 2.0;
    }

    public double wx(double sx) {
        return (sx - vw / 2.0) / zoom + camX;
    }

    public double wy(double sy) {
        return (sy - vh / 2.0) / zoom + camY;
    }

    public void clampCamera() {
        zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom));
        if (world.bounded) {
            camX = Math.max(0, Math.min(world.N, camX));
            camY = Math.max(0, Math.min(world.N, camY));
        }
    }

    public void zoomAt(double mx, double my, double factor) {
        double bx = wx(mx), by = wy(my);
        zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom * factor));
        camX = bx - (mx - vw / 2.0) / zoom;
        camY = by - (my - vh / 2.0) / zoom;
        clampCamera();
    }

    // ---------- main draw ----------
    public void draw(Graphics2D g, int highlightNation) {
        frame++;
        clampCamera();
        g.setColor(new Color(0x0e2850));
        g.fillRect(0, 0, vw, vh);

        double wx0 = wx(0), wx1 = wx(vw), wy0 = wy(0), wy1 = wy(vh);
        int cx0 = (int) Math.floor(wx0 / 32), cx1 = (int) Math.floor(wx1 / 32);
        int cy0 = (int) Math.floor(wy0 / 32), cy1 = (int) Math.floor(wy1 / 32);
        if (world.bounded) {
            int maxC = (world.N - 1) >> 5;
            cx0 = Math.max(0, cx0);
            cy0 = Math.max(0, cy0);
            cx1 = Math.min(maxC, cx1);
            cy1 = Math.min(maxC, cy1);
        }

        ArrayList<int[]> order = new ArrayList<>();
        double ccx = camX / 32, ccy = camY / 32;
        for (int cy = cy0; cy <= cy1; cy++)
            for (int cx = cx0; cx <= cx1; cx++) order.add(new int[]{cx, cy});
        order.sort((a, b) -> Double.compare(Math.hypot(a[0] + .5 - ccx, a[1] + .5 - ccy), Math.hypot(b[0] + .5 - ccx, b[1] + .5 - ccy)));

        boolean detail = zoom >= DETAIL_ZOOM;
        int rebuilt = 0;
        ArrayList<Object[]> tints = new ArrayList<>();
        Object oldInterp = g.getRenderingHint(RenderingHints.KEY_INTERPOLATION);
        g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_NEAREST_NEIGHBOR);
        for (int[] cc : order) {
            int cx = cc[0], cy = cc[1];
            Chunk c = world.peek(cx, cy);
            int sx0 = (int) Math.floor(sx(cx * 32)), sy0 = (int) Math.floor(sy(cy * 32));
            int sx1 = (int) Math.floor(sx((cx + 1) * 32)), sy1 = (int) Math.floor(sy((cy + 1) * 32));
            if (c == null) {
                world.request(cx, cy);
                continue;
            }
            c.lastUse = frame;
            long key = Chunk.key(cx, cy);
            CV v = views.get(key);
            if (v == null) {
                v = new CV();
                views.put(key, v);
            }
            v.used = frame;
            if (v.overVer != c.version && rebuilt < 24) {
                rebuild(c, v);
                rebuilt++;
            }
            if (detail && v.detailVer != c.version && !v.painting && queued.get() < 10) requestDetail(c, v);
            BufferedImage di = detail ? v.detail : null;
            if (di != null) g.drawImage(di, sx0, sy0, sx1 - sx0, sy1 - sy0, null);
            else if (v.over != null) g.drawImage(v.over, sx0, sy0, sx1 - sx0, sy1 - sy0, null);
            if (v.tint != null) tints.add(new Object[]{v, sx0, sy0, sx1 - sx0, sy1 - sy0, c});
        }

        // territory tint (smoothed) and borders
        g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
        for (Object[] t : tints) {
            CV v = (CV) t[0];
            g.drawImage(v.tint, (Integer) t[1], (Integer) t[2], (Integer) t[3], (Integer) t[4], null);
        }
        g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_NEAREST_NEIGHBOR);
        if (zoom < 8) {
            for (Object[] t : tints) {
                CV v = (CV) t[0];
                if (v.border != null) g.drawImage(v.border, (Integer) t[1], (Integer) t[2], (Integer) t[3], (Integer) t[4], null);
            }
        } else {
            drawBorderLines(g, tints);
        }
        if (oldInterp != null) g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, oldInterp);

        if (zoom >= 9) drawWaterSparkle(g, wx0, wy0, wx1, wy1);

        drawCitiesAndUnits(g, highlightNation);
        drawFx(g);

        if (frame % 60 == 0) housekeeping();
    }

    private void rebuild(Chunk c, CV v) {
        int ver = c.version;
        BufferedImage o = new BufferedImage(32, 32, BufferedImage.TYPE_INT_RGB);
        o.setRGB(0, 0, 32, 32, ChunkPainter.paintOverview(c), 0, 32);
        v.over = o;
        if (c.hasClaims) {
            int[] tint = new int[Chunk.N], bord = new int[Chunk.N];
            boolean any = false;
            int ox = c.cx * 32, oy = c.cy * 32;
            for (int ty = 0; ty < 32; ty++)
                for (int tx = 0; tx < 32; tx++) {
                    int i = ty * 32 + tx;
                    int ow = c.owner[i];
                    if (ow == 0) continue;
                    Nation n = world.nation(ow);
                    int col = n != null ? n.color : 0x888888;
                    tint[i] = (0x2e << 24) | col;
                    any = true;
                    boolean edge = ownerDiffers(c, tx - 1, ty, ox, oy, ow) || ownerDiffers(c, tx + 1, ty, ox, oy, ow)
                            || ownerDiffers(c, tx, ty - 1, ox, oy, ow) || ownerDiffers(c, tx, ty + 1, ox, oy, ow);
                    if (edge) bord[i] = (0xE6 << 24) | Pix.shade(0xFF000000 | col, 0.85) & 0xFFFFFF;
                }
            if (any) {
                v.tint = new BufferedImage(32, 32, BufferedImage.TYPE_INT_ARGB);
                v.tint.setRGB(0, 0, 32, 32, tint, 0, 32);
                v.border = new BufferedImage(32, 32, BufferedImage.TYPE_INT_ARGB);
                v.border.setRGB(0, 0, 32, 32, bord, 0, 32);
            } else {
                v.tint = null;
                v.border = null;
            }
        } else {
            v.tint = null;
            v.border = null;
        }
        v.overVer = ver;
    }

    private boolean ownerDiffers(Chunk c, int tx, int ty, int ox, int oy, int ow) {
        if (tx >= 0 && ty >= 0 && tx < 32 && ty < 32) return c.owner[ty * 32 + tx] != ow;
        return world.ownerAt(ox + tx, oy + ty) != ow;
    }

    private void requestDetail(Chunk c, CV v) {
        final int ver = c.version;
        v.painting = true;
        queued.incrementAndGet();
        paint.submit(() -> {
            try {
                int[] px = ChunkPainter.paintDetail(world, c);
                BufferedImage im = new BufferedImage(ChunkPainter.CP, ChunkPainter.CP, BufferedImage.TYPE_INT_RGB);
                im.setRGB(0, 0, ChunkPainter.CP, ChunkPainter.CP, px, 0, ChunkPainter.CP);
                v.detail = im;
                v.detailVer = ver;
            } catch (Throwable t) {
                t.printStackTrace();
            } finally {
                v.painting = false;
                queued.decrementAndGet();
            }
        });
    }

    private void housekeeping() {
        int count = 0;
        for (CV v : views.values()) if (v.detail != null) count++;
        detailImages = count;
        int max = 150;
        if (count > max) {
            ArrayList<CV> list = new ArrayList<>();
            for (CV v : views.values()) if (v.detail != null) list.add(v);
            list.sort((a, b) -> Long.compare(a.used, b.used));
            for (int i = 0; i < count - max; i++) {
                list.get(i).detail = null;
                list.get(i).detailVer = -1;
            }
        }
        world.evict(1800);
        if (views.size() > 2600) {
            Iterator<java.util.Map.Entry<Long, CV>> it = views.entrySet().iterator();
            while (it.hasNext()) {
                java.util.Map.Entry<Long, CV> e = it.next();
                if (frame - e.getValue().used > 600) it.remove();
            }
        }
    }

    // ---------- borders at close zoom ----------
    private void drawBorderLines(Graphics2D g, ArrayList<Object[]> tints) {
        float w = (float) Math.max(2, zoom * 0.14);
        g.setStroke(new BasicStroke(w, BasicStroke.CAP_BUTT, BasicStroke.JOIN_MITER));
        for (Object[] t : tints) {
            Chunk c = (Chunk) t[5];
            int ox = c.cx * 32, oy = c.cy * 32;
            for (int ty = 0; ty < 32; ty++)
                for (int tx = 0; tx < 32; tx++) {
                    int ow = c.owner[ty * 32 + tx];
                    if (ow == 0) continue;
                    double x0 = sx(ox + tx), y0 = sy(oy + ty);
                    if (x0 < -zoom || y0 < -zoom || x0 > vw || y0 > vh) continue;
                    boolean l = ownerDiffers(c, tx - 1, ty, ox, oy, ow), r = ownerDiffers(c, tx + 1, ty, ox, oy, ow),
                            u = ownerDiffers(c, tx, ty - 1, ox, oy, ow), d = ownerDiffers(c, tx, ty + 1, ox, oy, ow);
                    if (!(l || r || u || d)) continue;
                    Nation n = world.nation(ow);
                    int col = n != null ? n.color : 0x888888;
                    double h = w / 2.0;
                    g.setColor(new Color(0xE0000000 | Pix.shade(0xFF000000 | col, 0.9) & 0xFFFFFF, true));
                    if (l) g.drawLine((int) (x0 + h), (int) y0, (int) (x0 + h), (int) (y0 + zoom));
                    if (r) g.drawLine((int) (x0 + zoom - h), (int) y0, (int) (x0 + zoom - h), (int) (y0 + zoom));
                    if (u) g.drawLine((int) x0, (int) (y0 + h), (int) (x0 + zoom), (int) (y0 + h));
                    if (d) g.drawLine((int) x0, (int) (y0 + zoom - h), (int) (x0 + zoom), (int) (y0 + zoom - h));
                }
        }
        g.setStroke(new BasicStroke(1f));
    }

    private void drawWaterSparkle(Graphics2D g, double wx0, double wy0, double wx1, double wy1) {
        int x0 = (int) Math.floor(wx0), x1 = (int) Math.ceil(wx1), y0 = (int) Math.floor(wy0), y1 = (int) Math.ceil(wy1);
        if ((x1 - x0) * (y1 - y0) > 9000) return;
        g.setColor(new Color(255, 255, 255, 150));
        int s = (int) Math.max(1, zoom / 8);
        for (int y = y0; y <= y1; y++)
            for (int x = x0; x <= x1; x++) {
                int h = Noise.randInt(x, y, 777);
                if ((h & 15) != 0) continue;
                double ph = ((h >>> 8) & 255) / 255.0 * 6.28 + time * 1.7;
                if (Math.sin(ph) < 0.82) continue;
                if (!Terrain.isWater(world.terrainAt(x, y))) continue;
                double px = sx(x) + ((h >>> 16) & 15) / 16.0 * zoom * 0.8, py = sy(y) + ((h >>> 20) & 15) / 16.0 * zoom * 0.8;
                g.fillRect((int) px, (int) py, s * 3, s);
            }
    }

    // ---------- cities, ships, armies ----------
    private int nationColor(int id) {
        Nation n = world.nation(id);
        return n != null ? n.color : 0x888888;
    }

    private void drawCitiesAndUnits(Graphics2D g, int highlightNation) {
        double radius = Math.hypot(vw, vh) / zoom / 2 + 12;
        ArrayList<City> cs = world.citiesNear((int) camX, (int) camY, (int) radius);
        Font nameFont = new Font("SansSerif", Font.BOLD, (int) Math.max(10, Math.min(15, zoom * 0.8)));
        for (City c : cs) {
            double cx = sx(c.x + 0.5), cyb = sy(c.y + 1);
            int col = nationColor(c.nation);
            if (zoom >= DETAIL_ZOOM) {
                BufferedImage im = Sprites.CITY[c.level];
                double s = zoom / 16.0;
                int w = (int) (im.getWidth() * s), h = (int) (im.getHeight() * s);
                int x = (int) (cx - w / 2.0), y = (int) (cyb - h + zoom * 0.18);
                g.drawImage(im, x, y, w, h, null);
                // nation banner
                double fx = x + w * 0.5 + s * 0.5, fy = y + s * 0.3;
                int fw = (int) Math.max(3, 5 * s), fh = (int) Math.max(2, 3 * s);
                g.setColor(new Color(col));
                g.fillRect((int) (x + w * 0.52), (int) (y - fh * 0.2), fw, fh);
                g.setColor(new Color(0, 0, 0, 120));
                g.drawRect((int) (x + w * 0.52), (int) (y - fh * 0.2), fw, fh);
                if (c.capital) {
                    g.setColor(new Color(0xffd23a));
                    int r = (int) Math.max(2, s * 1.6);
                    g.fillOval((int) (cx - r), (int) (y - r * 2.4), r * 2, r * 2);
                    g.setColor(new Color(60, 40, 0));
                    g.drawOval((int) (cx - r), (int) (y - r * 2.4), r * 2, r * 2);
                }
                if (zoom >= 12) {
                    String name = c.name;
                    g.setFont(nameFont);
                    FontMetrics fm = g.getFontMetrics();
                    int tw = fm.stringWidth(name);
                    int tx = (int) (cx - tw / 2.0), ty = (int) (y - (c.capital ? zoom * 0.55 : zoom * 0.12));
                    outlinedText(g, name, tx, ty, Color.WHITE, new Color(0, 0, 0, 200));
                }
            } else {
                double s = Math.max(3.5, zoom * (0.5 + c.level * 0.12));
                double x = sx(c.x + 0.5) - s / 2, y = sy(c.y + 0.5) - s / 2;
                g.setColor(new Color(0, 0, 0, 180));
                g.fillRect((int) x - 1, (int) y - 1, (int) s + 2, (int) s + 2);
                g.setColor(new Color(col));
                g.fillRect((int) x, (int) y, (int) s, (int) s);
                if (c.capital) {
                    g.setColor(new Color(0xffd23a));
                    g.fillRect((int) (x + s * 0.3), (int) (y + s * 0.3), (int) Math.max(2, s * 0.4), (int) Math.max(2, s * 0.4));
                }
            }
        }
        // nation names on capitals when zoomed out
        if (zoom < 12 && zoom >= 2.5) {
            for (City c : cs) {
                if (!c.capital) continue;
                Nation n = world.nation(c.nation);
                if (n == null) continue;
                int fs = (int) Math.max(11, Math.min(26, 8 + zoom * 1.5));
                g.setFont(new Font("SansSerif", Font.BOLD, fs));
                FontMetrics fm = g.getFontMetrics();
                String s = n.name.toUpperCase();
                int tw = fm.stringWidth(s);
                outlinedText(g, s, (int) (sx(c.x + 0.5) - tw / 2.0), (int) (sy(c.y) - Math.max(6, zoom * 0.9)), new Color(n.color).brighter(), new Color(0, 0, 0, 215));
            }
        }
        if (zoom >= 8) drawShips(g, cs);
        drawArmies(g);
    }

    public static void outlinedText(Graphics2D g, String s, int x, int y, Color fill, Color outline) {
        g.setColor(outline);
        for (int dx = -1; dx <= 1; dx++) for (int dy = -1; dy <= 1; dy++) if (dx != 0 || dy != 0) g.drawString(s, x + dx, y + dy);
        g.setColor(fill);
        g.drawString(s, x, y);
    }

    private void drawShips(Graphics2D g, ArrayList<City> cs) {
        double u = zoom / 16.0;
        for (City c : cs) {
            if (c.docks == 0) continue;
            int k = 0;
            for (int[] b : c.blds) {
                if (b[2] != Terrain.DOCK) continue;
                if (k++ > 3) break;
                int dir = dockDir(b[0], b[1]);
                int[] dv = {0, 0};
                switch (dir) {
                    case 0: dv = new int[]{0, 1}; break;
                    case 1: dv = new int[]{-1, 0}; break;
                    case 2: dv = new int[]{0, -1}; break;
                    default: dv = new int[]{1, 0}; break;
                }
                double ph = time * 0.35 + c.id * 1.3 + b[0] * 0.7;
                double dist = 2.2 + 2.2 * (0.5 + 0.5 * Math.sin(ph));
                double wob = 0.5 * Math.sin(time * 0.8 + b[1]);
                double wxp = b[0] + 0.5 + dv[0] * dist + dv[1] * wob, wyp = b[1] + 0.5 + dv[1] * dist + dv[0] * wob;
                if (!Terrain.isWater(world.terrainAt((int) Math.floor(wxp), (int) Math.floor(wyp)))) continue;
                double px = sx(wxp), py = sy(wyp);
                // hull
                Path2D hull = new Path2D.Double();
                hull.moveTo(px - 5 * u, py);
                hull.lineTo(px + 5 * u, py);
                hull.lineTo(px + 3.5 * u, py + 3 * u);
                hull.lineTo(px - 3.5 * u, py + 3 * u);
                hull.closePath();
                g.setColor(new Color(0x6a4429));
                g.fill(hull);
                g.setColor(new Color(0x3a2414));
                g.draw(hull);
                g.setColor(new Color(0x3a2414));
                g.fillRect((int) (px - 0.5 * u), (int) (py - 6 * u), (int) Math.max(1, u), (int) (6 * u));
                Path2D sail = new Path2D.Double();
                sail.moveTo(px + 0.5 * u, py - 6 * u);
                sail.lineTo(px + 4.5 * u, py - 1 * u);
                sail.lineTo(px + 0.5 * u, py - 1 * u);
                sail.closePath();
                g.setColor(new Color(0xf2f0e6));
                g.fill(sail);
                Path2D sail2 = new Path2D.Double();
                sail2.moveTo(px - 0.5 * u, py - 5 * u);
                sail2.lineTo(px - 3.5 * u, py - 1 * u);
                sail2.lineTo(px - 0.5 * u, py - 1 * u);
                sail2.closePath();
                g.setColor(new Color(nationColor(c.nation)));
                g.fill(sail2);
                g.setColor(new Color(255, 255, 255, 110));
                g.drawLine((int) (px - 6 * u), (int) (py + 3.5 * u), (int) (px + 6 * u), (int) (py + 3.5 * u));
            }
        }
    }

    private int dockDir(int x, int y) {
        if (Terrain.isWater(world.terrainAt(x, y + 1))) return 0;
        if (Terrain.isWater(world.terrainAt(x - 1, y))) return 1;
        if (Terrain.isWater(world.terrainAt(x, y - 1))) return 2;
        return 3;
    }

    private void drawArmies(Graphics2D g) {
        double u = zoom / 16.0;
        for (Army a : world.armies) {
            if (a.dead) continue;
            double px = sx(a.x + 0.5), py = sy(a.y + 0.5);
            if (px < -40 || py < -40 || px > vw + 40 || py > vh + 40) continue;
            int col = nationColor(a.nation);
            Color nc = new Color(col);
            Nation n = world.nation(a.nation);
            Color dark = new Color(Pix.shade(0xFF000000 | col, 0.55));
            City t = world.cities.get(a.targetCity);
            if (t != null && zoom >= 3) {
                g.setColor(new Color(col & 0xFFFFFF | 0x90000000, true));
                g.setStroke(new BasicStroke(Math.max(1.5f, (float) (zoom * 0.08)), BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND, 1f, new float[]{6f, 6f}, (float) (time * 12 % 12)));
                g.drawLine((int) px, (int) py, (int) sx(t.x + 0.5), (int) sy(t.y + 0.5));
                g.setStroke(new BasicStroke(1f));
            }
            if (zoom >= DETAIL_ZOOM) {
                int soldiers = a.strength > 400 ? 5 : a.strength > 120 ? 4 : 3;
                for (int i = 0; i < soldiers; i++) {
                    double ox = ((i % 3) - 1) * 4.2 * u + (i / 3) * 2 * u, oy = (i / 3) * 4 * u - (i % 2) * 1.5 * u + Math.sin(time * 8 + i) * 0.5 * u;
                    double x = px + ox, y = py + oy;
                    g.setColor(new Color(0, 0, 0, 70));
                    g.fillOval((int) (x - 2.5 * u), (int) (y + 3 * u), (int) (5 * u), (int) (2 * u));
                    g.setColor(new Color(0x5a3b22));
                    g.fillRect((int) (x + 2 * u), (int) (y - 6 * u), (int) Math.max(1, u), (int) (10 * u));
                    g.setColor(Color.WHITE);
                    g.fillRect((int) (x + 2 * u), (int) (y - 7 * u), (int) Math.max(1, u), (int) Math.max(1, 2 * u));
                    g.setColor(nc);
                    g.fillRect((int) (x - 2 * u), (int) (y - 1 * u), (int) (4 * u), (int) (5 * u));
                    g.setColor(dark);
                    g.drawRect((int) (x - 2 * u), (int) (y - 1 * u), (int) (4 * u), (int) (5 * u));
                    g.setColor(new Color(0xe8c49a));
                    g.fillRect((int) (x - 1.5 * u), (int) (y - 4 * u), (int) (3 * u), (int) (3 * u));
                    g.setColor(new Color(0x9aa0aa));
                    g.fillRect((int) (x - 2 * u), (int) (y - 5 * u), (int) (4 * u), (int) (2 * u));
                }
                // banner
                g.setColor(new Color(0x3a2414));
                g.fillRect((int) (px - 0.5 * u), (int) (py - 13 * u), (int) Math.max(1, u), (int) (10 * u));
                g.setColor(nc);
                g.fillRect((int) (px + 0.5 * u), (int) (py - 13 * u), (int) (6 * u), (int) (4 * u));
                g.setColor(dark);
                g.drawRect((int) (px + 0.5 * u), (int) (py - 13 * u), (int) (6 * u), (int) (4 * u));
            } else {
                double s = Math.max(5, zoom * 1.1);
                g.setColor(new Color(0, 0, 0, 200));
                g.fillOval((int) (px - s / 2 - 1), (int) (py - s / 2 - 1), (int) s + 2, (int) s + 2);
                g.setColor(nc);
                g.fillOval((int) (px - s / 2), (int) (py - s / 2), (int) s, (int) s);
                g.setColor(Color.WHITE);
                g.drawLine((int) (px - s * 0.25), (int) (py + s * 0.25), (int) (px + s * 0.25), (int) (py - s * 0.25));
            }
        }
    }

    // ---------- effects ----------
    public void update(double dt) {
        time += dt;
        for (float[] f : world.fx) {
            Fx e = new Fx();
            e.x = f[0];
            e.y = f[1];
            e.type = (int) f[2];
            e.color = (int) f[3];
            fxs.add(e);
        }
        world.fx.clear();
        for (Iterator<Fx> it = fxs.iterator(); it.hasNext(); ) {
            Fx e = it.next();
            e.age += dt;
            if (e.age > 1.8) it.remove();
        }
    }

    private void drawFx(Graphics2D g) {
        for (Fx e : fxs) {
            double px = sx(e.x + 0.5), py = sy(e.y + 0.5);
            if (px < -80 || py < -80 || px > vw + 80 || py > vh + 80) continue;
            double a = e.age / 1.8;
            double base = Math.max(10, zoom * 2.5);
            int alpha = (int) (230 * (1 - a));
            if (e.type == 0) {
                for (int i = 0; i < 9; i++) {
                    double ang = i * 0.7 + e.x;
                    double r = base * (0.25 + a * 1.1) * (0.6 + 0.4 * ((i * 37) % 10) / 10.0);
                    double x = px + Math.cos(ang) * r, y = py + Math.sin(ang) * r - a * base * 0.5;
                    g.setColor(new Color(i % 2 == 0 ? 255 : 255, i % 2 == 0 ? 120 : 200, 40, alpha));
                    g.fillOval((int) (x - 3), (int) (y - 3), 6, 6);
                }
                g.setColor(new Color(70, 70, 70, (int) (150 * (1 - a))));
                g.fillOval((int) (px - base * 0.5 * (0.5 + a)), (int) (py - base * (0.3 + a * 0.8)), (int) (base * (0.5 + a)), (int) (base * (0.5 + a)));
                g.setColor(new Color(255, 80, 30, alpha));
                g.setStroke(new BasicStroke(3f));
                g.drawOval((int) (px - base * a), (int) (py - base * a), (int) (base * 2 * a), (int) (base * 2 * a));
                g.setStroke(new BasicStroke(1f));
            } else {
                Color c = e.type == 3 ? new Color(0xa040ff) : e.type == 2 ? new Color(0x60ff80) : new Color(e.color);
                g.setColor(new Color(c.getRed(), c.getGreen(), c.getBlue(), alpha));
                g.setStroke(new BasicStroke(4f));
                g.drawOval((int) (px - base * 1.4 * a), (int) (py - base * 1.4 * a), (int) (base * 2.8 * a), (int) (base * 2.8 * a));
                g.setStroke(new BasicStroke(1f));
                if (e.type == 1) {
                    g.setColor(new Color(255, 255, 255, alpha));
                    g.fillRect((int) px - 1, (int) (py - base * 0.6 * a - 10), 3, 10);
                    g.setColor(new Color(c.getRed(), c.getGreen(), c.getBlue(), alpha));
                    g.fillRect((int) px + 2, (int) (py - base * 0.6 * a - 10), 12, 7);
                }
            }
        }
    }

    // ---------- helpers for UI ----------
    public int tileX(double sx) {
        return (int) Math.floor(wx(sx));
    }

    public int tileY(double sy) {
        return (int) Math.floor(wy(sy));
    }

    public void centerOn(double wx, double wy) {
        camX = wx + 0.5;
        camY = wy + 0.5;
        clampCamera();
    }
}
