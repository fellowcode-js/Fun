package sov.awt;

import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.RectF;
import android.graphics.Shader;

/** Minimal java.awt.Graphics2D on top of an Android Canvas. */
public class Graphics2D {
    public final Canvas c;
    final android.graphics.Paint p = new android.graphics.Paint();
    final RectF rf = new RectF();
    Color color = Color.BLACK;
    Font font = new Font(Font.SANS_SERIF, Font.PLAIN, 12);
    Stroke stroke = new BasicStroke(1f);
    Rectangle clip;
    final int baseSave;
    boolean aa, filter;

    public Graphics2D(Canvas c) {
        this.c = c;
        baseSave = c.save();
        p.setColor(color.v);
        setFont(font);
        applyStroke();
        p.setSubpixelText(true);
    }

    public void dispose() { c.restoreToCount(baseSave); }

    public void setColor(Color col) { if (col == null) return; color = col; p.setShader(null); p.setColor(col.v); }
    public Color getColor() { return color; }
    public void setPaint(Paint pt) {
        if (pt instanceof Color) setColor((Color) pt);
        else if (pt instanceof GradientPaint) {
            GradientPaint g = (GradientPaint) pt;
            p.setColor(0xff000000);
            p.setShader(new LinearGradient(g.x1, g.y1, g.x2 == g.x1 && g.y2 == g.y1 ? g.x2 + 0.01f : g.x2, g.y2, g.c1.v, g.c2.v, Shader.TileMode.CLAMP));
        }
    }
    public void setFont(Font f) { if (f == null) return; font = f; p.setTypeface(f.tf); p.setTextSize(f.size); }
    public Font getFont() { return font; }
    public FontMetrics getFontMetrics() { return new FontMetrics(font); }
    public FontMetrics getFontMetrics(Font f) { return new FontMetrics(f); }
    public void setStroke(Stroke s) { stroke = s; applyStroke(); }
    public Stroke getStroke() { return stroke; }
    void applyStroke() {
        BasicStroke b = (BasicStroke) stroke;
        p.setStrokeWidth(b.w);
        p.setStrokeCap(b.cap == BasicStroke.CAP_ROUND ? android.graphics.Paint.Cap.ROUND : b.cap == BasicStroke.CAP_BUTT ? android.graphics.Paint.Cap.BUTT : android.graphics.Paint.Cap.SQUARE);
        p.setStrokeJoin(b.join == BasicStroke.JOIN_ROUND ? android.graphics.Paint.Join.ROUND : b.join == BasicStroke.JOIN_BEVEL ? android.graphics.Paint.Join.BEVEL : android.graphics.Paint.Join.MITER);
        p.setPathEffect(b.dash != null ? new android.graphics.DashPathEffect(b.dash, 0) : null);
    }

    public void setRenderingHint(Object k, Object v) {
        if (k == RenderingHints.KEY_ANTIALIASING) { aa = v == RenderingHints.VALUE_ANTIALIAS_ON; p.setAntiAlias(aa); }
        else if (k == RenderingHints.KEY_INTERPOLATION) filter = v != RenderingHints.VALUE_INTERPOLATION_NEAREST_NEIGHBOR;
    }
    public Object getRenderingHint(Object k) {
        if (k == RenderingHints.KEY_ANTIALIASING) return aa ? RenderingHints.VALUE_ANTIALIAS_ON : RenderingHints.VALUE_ANTIALIAS_OFF;
        if (k == RenderingHints.KEY_INTERPOLATION) return filter ? RenderingHints.VALUE_INTERPOLATION_BILINEAR : RenderingHints.VALUE_INTERPOLATION_NEAREST_NEIGHBOR;
        return null;
    }

    android.graphics.Paint fill() { p.setStyle(android.graphics.Paint.Style.FILL); return p; }
    android.graphics.Paint line() { p.setStyle(android.graphics.Paint.Style.STROKE); return p; }

    public void fillRect(int x, int y, int w, int h) { if (w > 0 && h > 0) c.drawRect(x, y, x + w, y + h, fill()); }
    public void drawRect(int x, int y, int w, int h) { c.drawRect(x + .5f, y + .5f, x + w + .5f, y + h + .5f, line()); }
    public void clearRect(int x, int y, int w, int h) { fillRect(x, y, w, h); }
    public void drawLine(int x1, int y1, int x2, int y2) {
        if (x1 == x2 && y1 == y2) { c.drawRect(x1, y1, x1 + 1, y1 + 1, fill()); return; }
        c.drawLine(x1 + .5f, y1 + .5f, x2 + .5f, y2 + .5f, line());
    }
    public void fillOval(int x, int y, int w, int h) { rf.set(x, y, x + w, y + h); c.drawOval(rf, fill()); }
    public void drawOval(int x, int y, int w, int h) { rf.set(x + .5f, y + .5f, x + w + .5f, y + h + .5f); c.drawOval(rf, line()); }
    public void fillRoundRect(int x, int y, int w, int h, int aw, int ah) { rf.set(x, y, x + w, y + h); c.drawRoundRect(rf, aw / 2f, ah / 2f, fill()); }
    public void drawRoundRect(int x, int y, int w, int h, int aw, int ah) { rf.set(x + .5f, y + .5f, x + w + .5f, y + h + .5f); c.drawRoundRect(rf, aw / 2f, ah / 2f, line()); }
    public void drawArc(int x, int y, int w, int h, int start, int ext) { rf.set(x + .5f, y + .5f, x + w + .5f, y + h + .5f); c.drawArc(rf, -start, -ext, false, line()); }
    public void fillArc(int x, int y, int w, int h, int start, int ext) { rf.set(x, y, x + w, y + h); c.drawArc(rf, -start, -ext, true, fill()); }
    android.graphics.Path poly(int[] xs, int[] ys, int n, boolean close) {
        android.graphics.Path path = new android.graphics.Path();
        for (int i = 0; i < n; i++) { if (i == 0) path.moveTo(xs[i], ys[i]); else path.lineTo(xs[i], ys[i]); }
        if (close) path.close();
        return path;
    }
    public void fillPolygon(int[] xs, int[] ys, int n) { c.drawPath(poly(xs, ys, n, true), fill()); }
    public void drawPolygon(int[] xs, int[] ys, int n) { c.drawPath(poly(xs, ys, n, true), line()); }
    public void drawPolyline(int[] xs, int[] ys, int n) { c.drawPath(poly(xs, ys, n, false), line()); }
    public void fill(Shape s) { c.drawPath(s.toPath(), fill()); }
    public void draw(Shape s) { c.drawPath(s.toPath(), line()); }

    public void drawString(String s, int x, int y) { if (s != null) c.drawText(s, x, y, fill()); }
    public void drawString(String s, float x, float y) { if (s != null) c.drawText(s, x, y, fill()); }

    final android.graphics.Paint ip = new android.graphics.Paint();
    final android.graphics.Rect dst = new android.graphics.Rect();
    public boolean drawImage(Image im, int x, int y, Object obs) {
        if (im == null) return true;
        ip.setFilterBitmap(filter);
        c.drawBitmap(im.bitmap(), x, y, ip);
        return true;
    }
    public boolean drawImage(Image im, int x, int y, int w, int h, Object obs) {
        if (im == null) return true;
        ip.setFilterBitmap(filter);
        dst.set(x, y, x + w, y + h);
        c.drawBitmap(im.bitmap(), null, dst, ip);
        return true;
    }

    public Shape getClip() { return clip == null ? null : new Rectangle(clip.x, clip.y, clip.width, clip.height); }
    public void setClip(int x, int y, int w, int h) { setClip(new Rectangle(x, y, w, h)); }
    public void setClip(Shape s) {
        c.restoreToCount(baseSave);
        c.save();
        clip = null;
        if (s instanceof Rectangle) {
            Rectangle r = (Rectangle) s;
            clip = new Rectangle(r.x, r.y, r.width, r.height);
            c.clipRect(r.x, r.y, r.x + r.width, r.y + r.height);
        }
    }
    public void clipRect(int x, int y, int w, int h) { setClip(x, y, w, h); }
}
