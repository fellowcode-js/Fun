package sov.game;

import sov.awt.*;
import sov.awt.geom.RoundRectangle2D;
import sov.awt.image.BufferedImage;
import java.util.ArrayList;
import java.util.function.Consumer;

/** Minimal immediate-mode UI: widgets are drawn and hit-tested each frame. */
public final class Ui {
    public static final class Hit {
        public Rectangle r;
        public Runnable click;
        public Consumer<Double> drag;
        public String tip;
        public boolean blocksMap = true;
    }

    public Graphics2D g;
    public double s = 1;
    public int mx, my;
    public boolean mouseDown;
    private ArrayList<Hit> hits = new ArrayList<>();
    private ArrayList<Hit> prev = new ArrayList<>();
    public String tooltip;
    public Font small, norm, bold, big, title, huge;

    public static final Color PANEL_TOP = new Color(0x1b2745), PANEL_BOT = new Color(0x111a30), BORDER = new Color(0x4d6291),
            TEXT = new Color(0xeef3ff), DIM = new Color(0x9fb0d0), GOLD = new Color(0xf5c842), GOOD = new Color(0x6fdc7a),
            BAD = new Color(0xff6a5a), BTN = new Color(0x2b3d66), BTN_HOVER = new Color(0x3d5488), BTN_ON = new Color(0x4f72b8),
            DISABLED = new Color(0x242b3d);

    public void begin(Graphics2D g, double s, int mx, int my, boolean down) {
        this.g = g;
        this.s = s;
        this.mx = mx;
        this.my = my;
        this.mouseDown = down;
        prev = hits;
        hits = new ArrayList<>();
        tooltip = null;
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
        small = new Font(Font.SANS_SERIF, Font.PLAIN, (int) Math.round(11 * s));
        norm = new Font(Font.SANS_SERIF, Font.PLAIN, (int) Math.round(13 * s));
        bold = new Font(Font.SANS_SERIF, Font.BOLD, (int) Math.round(13 * s));
        big = new Font(Font.SANS_SERIF, Font.BOLD, (int) Math.round(17 * s));
        title = new Font(Font.SANS_SERIF, Font.BOLD, (int) Math.round(26 * s));
        huge = new Font(Font.SANS_SERIF, Font.BOLD, (int) Math.round(64 * s));
    }

    public int px(double v) {
        return (int) Math.round(v * s);
    }

    public boolean hover(int x, int y, int w, int h) {
        return mx >= x && my >= y && mx < x + w && my < y + h;
    }

    /** Topmost widget from the previous frame at a point, or null. */
    public Hit hitAt(int x, int y) {
        for (int i = prev.size() - 1; i >= 0; i--) if (prev.get(i).r.contains(x, y)) return prev.get(i);
        return null;
    }

    public boolean overUi(int x, int y) {
        Hit h = hitAt(x, y);
        return h != null && h.blocksMap;
    }

    private Hit add(int x, int y, int w, int h, Runnable click, String tip) {
        Hit hit = new Hit();
        hit.r = new Rectangle(x, y, w, h);
        hit.click = click;
        hit.tip = tip;
        hits.add(hit);
        if (tip != null && hover(x, y, w, h)) tooltip = tip;
        return hit;
    }

    /** Clickable area with no drawing. */
    public void hotspot(int x, int y, int w, int h, Runnable click, String tip) {
        add(x, y, w, h, click, tip);
    }

    /** Invisible blocker so clicks on a panel don't reach the map. */
    public void block(int x, int y, int w, int h) {
        add(x, y, w, h, null, null);
    }

    public void panel(int x, int y, int w, int h) {
        RoundRectangle2D rr = new RoundRectangle2D.Double(x, y, w, h, 12 * s, 12 * s);
        g.setColor(new Color(0, 0, 0, 70));
        g.fill(new RoundRectangle2D.Double(x + 2 * s, y + 3 * s, w, h, 12 * s, 12 * s));
        g.setPaint(new GradientPaint(0, y, new Color(PANEL_TOP.getRed(), PANEL_TOP.getGreen(), PANEL_TOP.getBlue(), 238), 0, y + h,
                new Color(PANEL_BOT.getRed(), PANEL_BOT.getGreen(), PANEL_BOT.getBlue(), 238)));
        g.fill(rr);
        g.setPaint(null);
        g.setColor(BORDER);
        g.setStroke(new BasicStroke(Math.max(1f, (float) s)));
        g.draw(rr);
        g.setColor(new Color(255, 255, 255, 22));
        g.drawLine((int) (x + 10 * s), y + 1, (int) (x + w - 10 * s), y + 1);
        g.setStroke(new BasicStroke(1f));
        block(x, y, w, h);
    }

    public boolean button(String label, int x, int y, int w, int h, boolean on, boolean enabled, Runnable click, String tip) {
        boolean hov = enabled && hover(x, y, w, h);
        RoundRectangle2D rr = new RoundRectangle2D.Double(x, y, w, h, 8 * s, 8 * s);
        g.setColor(!enabled ? DISABLED : on ? BTN_ON : hov ? (mouseDown ? BTN : BTN_HOVER) : BTN);
        g.fill(rr);
        g.setColor(on ? GOLD : new Color(255, 255, 255, hov ? 70 : 34));
        g.setStroke(new BasicStroke(on ? Math.max(1.5f, (float) (1.5 * s)) : 1f));
        g.draw(rr);
        g.setStroke(new BasicStroke(1f));
        if (label != null) {
            g.setFont(bold);
            FontMetrics fm = g.getFontMetrics();
            g.setColor(enabled ? TEXT : new Color(0x6a7390));
            g.drawString(label, x + (w - fm.stringWidth(label)) / 2, y + (h + fm.getAscent() - fm.getDescent()) / 2);
        }
        add(x, y, w, h, enabled ? click : null, tip);
        return hov;
    }

    public void iconButton(BufferedImage icon, int x, int y, int size, boolean on, boolean enabled, Runnable click, String tip) {
        button(null, x, y, size, size, on, enabled, click, tip);
        if (icon != null) {
            int is = (int) (size * 0.72);
            g.drawImage(icon, x + (size - is) / 2, y + (size - is) / 2, is, is, null);
        }
    }

    public void text(String t, int x, int y, Font f, Color c) {
        g.setFont(f);
        g.setColor(c);
        g.drawString(t, x, y);
    }

    public void textShadow(String t, int x, int y, Font f, Color c) {
        g.setFont(f);
        g.setColor(new Color(0, 0, 0, 170));
        g.drawString(t, x + 1, y + 1);
        g.setColor(c);
        g.drawString(t, x, y);
    }

    public void textCenter(String t, int cx, int y, Font f, Color c) {
        g.setFont(f);
        int w = g.getFontMetrics().stringWidth(t);
        g.setColor(c);
        g.drawString(t, cx - w / 2, y);
    }

    public void textRight(String t, int rx, int y, Font f, Color c) {
        g.setFont(f);
        int w = g.getFontMetrics().stringWidth(t);
        g.setColor(c);
        g.drawString(t, rx - w, y);
    }

    public int textWidth(String t, Font f) {
        return g.getFontMetrics(f).stringWidth(t);
    }

    public void bar(int x, int y, int w, int h, double frac, Color c) {
        frac = Math.max(0, Math.min(1, frac));
        g.setColor(new Color(0, 0, 0, 120));
        g.fillRoundRect(x, y, w, h, h, h);
        if (frac > 0) {
            g.setColor(c);
            g.fillRoundRect(x, y, Math.max(h, (int) (w * frac)), h, h, h);
            g.setColor(new Color(255, 255, 255, 50));
            g.fillRoundRect(x + 1, y + 1, Math.max(h - 2, (int) (w * frac) - 2), Math.max(1, h / 2 - 1), h, h);
        }
        g.setColor(new Color(255, 255, 255, 40));
        g.drawRoundRect(x, y, w, h, h, h);
    }

    public void slider(int x, int y, int w, double val, Consumer<Double> set, Color c, String tip) {
        int h = px(10);
        bar(x, y + px(3), w, h, val, c);
        int kx = x + (int) (w * Math.max(0, Math.min(1, val)));
        g.setColor(Color.WHITE);
        g.fillOval(kx - px(8), y + px(3) + h / 2 - px(8), px(16), px(16));
        g.setColor(new Color(0x24365e));
        g.drawOval(kx - px(8), y + px(3) + h / 2 - px(8), px(16), px(16));
        Hit hit = add(x - px(8), y - px(4), w + px(16), px(28), null, tip);
        final int fx = x, fw = w;
        hit.drag = v -> set.accept(Math.max(0, Math.min(1, (v - fx) / fw)));
    }

    public void swatch(int x, int y, int size, int rgb, boolean selected, Runnable click) {
        g.setColor(new Color(rgb));
        g.fillRoundRect(x, y, size, size, size / 4, size / 4);
        g.setColor(selected ? Color.WHITE : new Color(0, 0, 0, 120));
        g.setStroke(new BasicStroke(selected ? (float) (2.5 * s) : 1f));
        g.drawRoundRect(x, y, size, size, size / 4, size / 4);
        g.setStroke(new BasicStroke(1f));
        add(x, y, size, size, click, null);
    }

    public void tooltipDraw(int w, int h) {
        if (tooltip == null) return;
        g.setFont(norm);
        FontMetrics fm = g.getFontMetrics();
        String[] lines = tooltip.split("\n");
        int tw = 0;
        for (String l : lines) tw = Math.max(tw, fm.stringWidth(l));
        int bw = tw + px(16), bh = lines.length * (fm.getHeight()) + px(10);
        int x = Math.min(w - bw - 6, mx + px(16)), y = Math.min(h - bh - 6, my + px(18));
        g.setColor(new Color(10, 14, 26, 235));
        g.fillRoundRect(x, y, bw, bh, px(8), px(8));
        g.setColor(BORDER);
        g.drawRoundRect(x, y, bw, bh, px(8), px(8));
        g.setColor(TEXT);
        for (int i = 0; i < lines.length; i++) g.drawString(lines[i], x + px(8), y + px(5) + fm.getAscent() + i * fm.getHeight());
    }
}
