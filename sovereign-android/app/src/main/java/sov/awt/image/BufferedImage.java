package sov.awt.image;
import android.graphics.Bitmap;
public class BufferedImage extends sov.awt.Image {
    public static final int TYPE_INT_RGB = 1, TYPE_INT_ARGB = 2;
    final Bitmap b; final boolean opaque; final int w, h;
    public BufferedImage(int w, int h, int type) {
        this.w = w; this.h = h; opaque = type == TYPE_INT_RGB;
        b = Bitmap.createBitmap(Math.max(1, w), Math.max(1, h), Bitmap.Config.ARGB_8888);
        if (opaque) b.eraseColor(0xff000000);
    }
    public int getWidth() { return w; }
    public int getHeight() { return h; }
    public int getWidth(Object o) { return w; }
    public int getHeight(Object o) { return h; }
    public Bitmap bitmap() { return b; }
    public void setRGB(int x, int y, int rgb) { if (x >= 0 && y >= 0 && x < w && y < h) b.setPixel(x, y, opaque ? rgb | 0xff000000 : rgb); }
    public int getRGB(int x, int y) { return b.getPixel(x, y); }
    public void setRGB(int x, int y, int ww, int hh, int[] a, int off, int scan) {
        if (opaque) { int[] c = new int[ww * hh]; for (int j = 0; j < hh; j++) for (int i = 0; i < ww; i++) c[j * ww + i] = a[off + j * scan + i] | 0xff000000; b.setPixels(c, 0, ww, x, y, ww, hh); }
        else b.setPixels(a, off, scan, x, y, ww, hh);
    }
    public sov.awt.Graphics2D createGraphics() { return new sov.awt.Graphics2D(new android.graphics.Canvas(b)); }
    public sov.awt.Graphics2D getGraphics() { return createGraphics(); }
}
