package sov.android;

import android.app.Activity;
import android.content.Context;
import android.graphics.Canvas;
import android.os.Build;
import android.os.Bundle;
import android.view.*;
import android.view.inputmethod.BaseInputConnection;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputMethodManager;
import sov.awt.Graphics2D;
import sov.awt.event.KeyEvent;
import sov.game.App;

public class MainActivity extends Activity {
    App app;
    GameView view;
    volatile boolean active;
    Thread loop;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        System.setProperty("user.home", getFilesDir().getAbsolutePath());
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (Build.VERSION.SDK_INT >= 28)
            getWindow().getAttributes().layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
        app = new App();
        app.onQuit = this::finish;
        view = new GameView(this);
        setContentView(view);
        hideBars();
    }

    void hideBars() {
        view.setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
    }

    @Override public void onWindowFocusChanged(boolean f) { super.onWindowFocusChanged(f); if (f) hideBars(); }

    @Override protected void onResume() { super.onResume(); active = true; startLoop(); }
    @Override protected void onPause() { active = false; super.onPause(); }

    @Override public void onBackPressed() { app.key(KeyEvent.VK_ESCAPE); }

    void startLoop() {
        if (loop != null && loop.isAlive()) return;
        loop = new Thread(() -> {
            long last = System.nanoTime();
            boolean kb = false;
            while (active) {
                long now = System.nanoTime();
                double dt = Math.min(0.1, (now - last) / 1e9);
                last = now;
                SurfaceHolder h = view.getHolder();
                if (!view.ready) { sleep(30); continue; }
                Canvas c = null;
                try {
                    c = Build.VERSION.SDK_INT >= 26 ? h.lockHardwareCanvas() : h.lockCanvas();
                    if (c != null) {
                        Graphics2D g = new Graphics2D(c);
                        app.renderFrame(g, c.getWidth(), c.getHeight(), dt);
                        g.dispose();
                    }
                } catch (Throwable e) {
                    e.printStackTrace();
                } finally {
                    if (c != null) try { h.unlockCanvasAndPost(c); } catch (Throwable ignored) {}
                }
                boolean want = app.wantsText();
                if (want != kb) { kb = want; final boolean show = want; view.post(() -> view.keyboard(show)); }
                long spent = (System.nanoTime() - now) / 1000000;
                sleep(Math.max(1, 16 - spent));
            }
        }, "game-loop");
        loop.start();
    }

    static void sleep(long ms) { try { Thread.sleep(ms); } catch (InterruptedException ignored) {} }

    class GameView extends SurfaceView implements SurfaceHolder.Callback {
        volatile boolean ready;
        int pid = -1;
        boolean multi, moved;
        long downAt;
        float downX, downY, lastCx, lastCy, lastDist;
        final float slop;

        GameView(Context ctx) {
            super(ctx);
            getHolder().addCallback(this);
            setFocusable(true);
            setFocusableInTouchMode(true);
            slop = ViewConfiguration.get(ctx).getScaledTouchSlop();
        }

        public void surfaceCreated(SurfaceHolder h) { ready = true; }
        public void surfaceChanged(SurfaceHolder h, int f, int w, int hh) { ready = true; }
        public void surfaceDestroyed(SurfaceHolder h) { ready = false; }

        void keyboard(boolean show) {
            InputMethodManager im = (InputMethodManager) getContext().getSystemService(Context.INPUT_METHOD_SERVICE);
            if (show) { requestFocus(); im.showSoftInput(this, InputMethodManager.SHOW_IMPLICIT); }
            else { im.hideSoftInputFromWindow(getWindowToken(), 0); hideBars(); }
        }

        @Override public boolean onCheckIsTextEditor() { return true; }

        @Override
        public InputConnection onCreateInputConnection(EditorInfo out) {
            out.inputType = android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS;
            out.imeOptions = EditorInfo.IME_ACTION_DONE | EditorInfo.IME_FLAG_NO_EXTRACT_UI | EditorInfo.IME_FLAG_NO_FULLSCREEN;
            return new BaseInputConnection(this, false) {
                @Override public boolean commitText(CharSequence t, int pos) { for (int i = 0; i < t.length(); i++) app.type(t.charAt(i)); return true; }
                @Override public boolean deleteSurroundingText(int before, int after) { for (int i = 0; i < Math.max(1, before); i++) app.type('\b'); return true; }
                @Override public boolean performEditorAction(int a) { app.key(KeyEvent.VK_ENTER); return true; }
            };
        }

        @Override
        public boolean onKeyDown(int code, android.view.KeyEvent e) {
            switch (code) {
                case android.view.KeyEvent.KEYCODE_DEL: app.type('\b'); return true;
                case android.view.KeyEvent.KEYCODE_ENTER: app.key(KeyEvent.VK_ENTER); return true;
                case android.view.KeyEvent.KEYCODE_BACK: return super.onKeyDown(code, e);
                case android.view.KeyEvent.KEYCODE_ESCAPE: app.key(KeyEvent.VK_ESCAPE); return true;
                case android.view.KeyEvent.KEYCODE_SPACE: app.key(KeyEvent.VK_SPACE); app.type(' '); return true;
            }
            int u = e.getUnicodeChar();
            if (u != 0) {
                char c = (char) u;
                app.type(c);
                if (c >= 'a' && c <= 'z') app.key(c - 32);
                else if (c >= '0' && c <= '9') app.key(c);
                else if (c == '-') app.key(KeyEvent.VK_MINUS);
                else if (c == '=' || c == '+') app.key(KeyEvent.VK_EQUALS);
                return true;
            }
            return super.onKeyDown(code, e);
        }

        @Override
        public boolean onGenericMotionEvent(MotionEvent e) {
            if (e.getAction() == MotionEvent.ACTION_SCROLL) {
                app.scroll((int) e.getX(), (int) e.getY(), -e.getAxisValue(MotionEvent.AXIS_VSCROLL));
                return true;
            }
            return super.onGenericMotionEvent(e);
        }

        @Override
        public boolean onTouchEvent(MotionEvent e) {
            int a = e.getActionMasked();
            switch (a) {
                case MotionEvent.ACTION_DOWN:
                    multi = false; moved = false;
                    pid = e.getPointerId(0);
                    downX = e.getX(); downY = e.getY(); downAt = e.getEventTime();
                    app.touchDown((int) downX, (int) downY);
                    break;
                case MotionEvent.ACTION_POINTER_DOWN:
                    if (!multi) { multi = true; app.touchCancel(); }
                    pinchStart(e);
                    break;
                case MotionEvent.ACTION_MOVE:
                    if (multi) {
                        if (e.getPointerCount() >= 2) {
                            float cx = (e.getX(0) + e.getX(1)) / 2, cy = (e.getY(0) + e.getY(1)) / 2;
                            float d = dist(e);
                            float f = lastDist > 0 ? d / lastDist : 1;
                            app.pinch(cx, cy, f, cx - lastCx, cy - lastCy);
                            lastCx = cx; lastCy = cy; lastDist = d;
                        }
                    } else {
                        int i = e.findPointerIndex(pid);
                        if (i < 0) break;
                        if (Math.abs(e.getX(i) - downX) > slop || Math.abs(e.getY(i) - downY) > slop) moved = true;
                        app.touchMove((int) e.getX(i), (int) e.getY(i));
                    }
                    break;
                case MotionEvent.ACTION_POINTER_UP:
                    if (multi && e.getPointerCount() > 2) pinchStart(e);
                    break;
                case MotionEvent.ACTION_UP:
                    if (!multi) {
                        boolean lp = !moved && e.getEventTime() - downAt > 550;
                        app.touchUp((int) e.getX(), (int) e.getY(), lp);
                    }
                    multi = false;
                    break;
                case MotionEvent.ACTION_CANCEL:
                    app.touchCancel();
                    multi = false;
                    break;
            }
            return true;
        }

        void pinchStart(MotionEvent e) {
            int up = e.getActionMasked() == MotionEvent.ACTION_POINTER_UP ? e.getActionIndex() : -1;
            int i0 = -1, i1 = -1;
            for (int i = 0; i < e.getPointerCount(); i++) { if (i == up) continue; if (i0 < 0) i0 = i; else if (i1 < 0) i1 = i; }
            if (i1 < 0) { lastDist = 0; return; }
            lastCx = (e.getX(i0) + e.getX(i1)) / 2; lastCy = (e.getY(i0) + e.getY(i1)) / 2;
            lastDist = (float) Math.hypot(e.getX(i0) - e.getX(i1), e.getY(i0) - e.getY(i1));
        }

        float dist(MotionEvent e) { return (float) Math.hypot(e.getX(0) - e.getX(1), e.getY(0) - e.getY(1)); }
    }
}
