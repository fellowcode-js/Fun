package sov.game;

import sov.core.*;
import sov.core.Nation.Relation;
import sov.render.MapImage;
import sov.render.WorldView;
import sov.sim.Names;
import sov.sim.Sim;

import sov.awt.*;
import sov.awt.event.*;
import sov.awt.image.BufferedImage;
import java.io.File;
import java.util.*;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

/** The game window: menus, new-game screen and the president's HUD. */
public final class App {
    enum Screen {MENU, NEW, PLAY}

    enum Tool {SELECT, FOUND, FARM, LUMBER, MINE, DOCK, TOWER, ROAD}

    enum PanelKind {NONE, POLICY, DIPLO, PAUSE, SAVES}

    private static final String[] MONTHS = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
    private static final int[] SPEED_RATE = {0, 1, 3, 8, 24};

    final Ui ui = new Ui();
    Screen screen = Screen.MENU;
    PanelKind panel = PanelKind.NONE;
    int W = 1280, H = 720;
    double scale = 1, userScale = 1;
    int mouseX = -1, mouseY = -1;
    boolean mouseDown, panning, pressedMap;
    int pressX, pressY, lastX, lastY;
    double dragDist;
    Ui.Hit activeDrag;
    final ConcurrentLinkedQueue<Runnable> events = new ConcurrentLinkedQueue<>();
    final boolean[] keys = new boolean[512];
    double clock;
    volatile boolean running = true;
    public Runnable onQuit;

    // ---- menu world ----
    World mWorld;
    Sim mSim;
    WorldView mView;
    double mSimAcc, mTimer, mZoomTarget = 12;
    double mTx, mTy;

    // ---- new game ----
    WorldSize ngSize = WorldSize.INFINITE;
    long ngSeed = new Random().nextInt(900000) + 100000;
    String ngSeedText = String.valueOf(ngSeed);
    String ngName = Names.nation(new Random());
    int ngGovIdx = 1, ngColor = 0;
    int ngStartX, ngStartY;
    boolean ngHasStart;
    World ngWorld;
    MapImage ngMap;
    double ngCx, ngCy, ngTpp = 3.5;
    int ngMapPx;
    int ngFocus; // 0 none, 1 name, 2 seed
    Rectangle ngPreviewRect = new Rectangle();
    boolean ngDragging;
    long ngRequestedKey;

    // ---- play ----
    World world;
    Sim sim;
    WorldView view;
    Nation me;
    Tool tool = Tool.SELECT;
    int selCity;
    int speed = 1;
    double simAcc;
    MapImage mm;
    double mmTimer;
    int diploScroll;
    final ArrayList<Object[]> toasts = new ArrayList<>();
    double hoverAcc;

    public App() {
        initMenuWorld();
    }

    // ================= lifecycle =================
    /** Runs one frame: events, update, draw. Also used by the headless screenshot harness. */
    public void renderFrame(Graphics2D g, int w, int h, double dt) {
        W = w;
        H = h;
        clock += dt;
        scale = Math.max(0.7, Math.min(w / 1280.0, h / 720.0)) * userScale;
        Runnable r;
        while ((r = events.poll()) != null) r.run();
        ui.begin(g, scale, mouseX, mouseY, mouseDown);
        switch (screen) {
            case MENU: drawMenu(g, dt); break;
            case NEW: drawNew(g, dt); break;
            default: drawPlay(g, dt); break;
        }
        ui.tooltipDraw(w, h);
    }

    void quit() {
        running = false;
        if (onQuit != null) onQuit.run();
    }

    // ================= menu =================
    void initMenuWorld() {
        if (mWorld != null) {
            mWorld.shutdown();
            mView.shutdown();
        }
        long seed = new Random().nextInt(900000) + 100000;
        mWorld = new World(seed, WorldSize.INFINITE);
        mSim = new Sim(mWorld);
        mSim.setupNewWorld(0, 0, null, null, 0, false);
        for (int i = 0; i < 150; i++) mSim.step();
        mView = new WorldView(mWorld);
        mView.zoom = 12;
        pickMenuTarget();
        mView.camX = mTx;
        mView.camY = mTy;
    }

    void pickMenuTarget() {
        ArrayList<City> cs = new ArrayList<>(mWorld.cities.values());
        if (cs.isEmpty()) return;
        City c = cs.get(new Random().nextInt(cs.size()));
        mTx = c.x + 0.5;
        mTy = c.y + 0.5;
        mZoomTarget = 9 + new Random().nextDouble() * 8;
        mTimer = 0;
    }

    void stepWorld(Sim s, double dt, double rate, double[] acc) {
        acc[0] += dt * rate;
        long t0 = System.nanoTime();
        int n = 0;
        while (acc[0] >= 1 && n < 40) {
            s.step();
            acc[0] -= 1;
            n++;
            if ((System.nanoTime() - t0) > 12_000_000L) {
                acc[0] = Math.min(acc[0], 2);
                break;
            }
        }
    }

    final double[] mAccBox = new double[1];

    void drawMenu(Graphics2D g, double dt) {
        mTimer += dt;
        mAccBox[0] = mSimAcc;
        stepWorld(mSim, dt, 3, mAccBox);
        mSimAcc = mAccBox[0];
        mView.vw = W;
        mView.vh = H;
        mView.camX += (mTx - mView.camX) * Math.min(1, dt * 0.35);
        mView.camY += (mTy - mView.camY) * Math.min(1, dt * 0.35);
        mView.zoom += (mZoomTarget - mView.zoom) * Math.min(1, dt * 0.4);
        if (mTimer > 16) pickMenuTarget();
        mView.update(dt);
        mView.draw(g, 0);
        // vignette
        g.setPaint(new GradientPaint(0, 0, new Color(6, 10, 22, 225), W * 0.55f, 0, new Color(6, 10, 22, 0)));
        g.fillRect(0, 0, W, H);
        g.setPaint(new GradientPaint(0, H * 0.72f, new Color(0, 0, 0, 0), 0, H, new Color(0, 0, 0, 160)));
        g.fillRect(0, H * 7 / 10, W, H * 3 / 10);
        g.setPaint(null);

        int x = ui.px(56), y = ui.px(150);
        ui.textShadow("SOVEREIGN", x, y, ui.huge, new Color(0xffe9a8));
        ui.textShadow("Rule from a village. Rule the world.", x + ui.px(4), y + ui.px(34), ui.big, new Color(0xcfdcff));
        int bw = ui.px(250), bh = ui.px(46), by = y + ui.px(80), gap = ui.px(14);
        ui.button("New Game", x, by, bw, bh, false, true, () -> openNewGame(), null);
        ui.button("Load Game", x, by + (bh + gap), bw, bh, false, true, () -> {
            startSpectateKeepMenu();
            panel = PanelKind.SAVES;
        }, null);
        ui.button("Watch the World", x, by + 2 * (bh + gap), bw, bh, false, true, () -> spectate(), "Spectate this living world without a nation");
        ui.button("Quit", x, by + 3 * (bh + gap), bw, bh, false, true, () -> quit(), null);
        ui.textShadow("Infinite procedural worlds - AI nations grow, trade, ally and go to war.", x, H - ui.px(28), ui.norm, new Color(0xd8e2ff));
        if (panel == PanelKind.SAVES) drawSavesPanel(g, true);
    }

    void startSpectateKeepMenu() {
    }

    void spectate() {
        world = mWorld;
        sim = mSim;
        view = mView;
        me = null;
        mWorld = null;
        selCity = 0;
        speed = 1;
        view.zoom = 10;
        screen = Screen.PLAY;
        panel = PanelKind.NONE;
        resetPlayState();
        toast("Spectating. Press Esc for the menu.", false);
    }

    void resetPlayState() {
        tool = Tool.SELECT;
        simAcc = 0;
        if (mm != null) mm.shutdown();
        mm = new MapImage();
        mmTimer = 99;
        toasts.clear();
    }

    // ================= new game =================
    void openNewGame() {
        screen = Screen.NEW;
        panel = PanelKind.NONE;
        newPreview();
    }

    void newPreview() {
        if (ngWorld != null) ngWorld.shutdown();
        if (ngMap != null) ngMap.shutdown();
        ngWorld = new World(ngSeed, ngSize);
        ngMap = new MapImage();
        ngHasStart = false;
        ngCx = ngWorld.bounded ? ngWorld.N / 2.0 : 0;
        ngCy = ngCx;
        ngTpp = 3.5;
        ngMapPx = 0;
        ngRequestedKey = -1;
    }

    void requestPreview() {
        int px = ngPreviewRect.width;
        if (px < 50) return;
        double tpp = ngWorld.bounded ? ngWorld.N / (double) px : ngTpp;
        long key = Double.doubleToLongBits(ngCx) * 31 + Double.doubleToLongBits(ngCy) * 17 + Double.doubleToLongBits(tpp) + px * 1000003L;
        if (key == ngRequestedKey) return;
        ngRequestedKey = key;
        ngMapPx = px;
        ngMap.request(ngWorld, ngCx, ngCy, tpp, px, tpp <= 6, null);
    }

    void autoStart() {
        Sim tmp = new Sim(ngWorld);
        double cx = ngWorld.bounded ? ngWorld.N / 2.0 : ngCx, cy = cx;
        if (!ngWorld.bounded) cy = ngCy;
        for (int r = 20; r <= 1200; r *= 2) {
            int[] s = tmp.findSiteNear((int) cx, (int) cy, r, 120);
            if (s != null) {
                ngStartX = s[0];
                ngStartY = s[1];
                ngHasStart = true;
                return;
            }
        }
        ngStartX = (int) cx;
        ngStartY = (int) cy;
        ngHasStart = true;
    }

    void startGame() {
        if (!ngHasStart) autoStart();
        World w = ngWorld;
        ngWorld = null;
        if (ngMap != null) ngMap.shutdown();
        if (mWorld != null) {
            mWorld.shutdown();
            mView.shutdown();
            mWorld = null;
        }
        world = w;
        sim = new Sim(world);
        me = sim.setupNewWorld(ngStartX, ngStartY, ngName.trim().isEmpty() ? "Nova" : ngName.trim(), Names.GOVS[ngGovIdx], Names.COLORS[ngColor], true);
        view = new WorldView(world);
        City cap = sim.citiesOf(me).isEmpty() ? null : sim.citiesOf(me).get(0);
        if (cap == null) {
            for (City c : world.cities.values()) if (c.nation == me.id) cap = c;
        }
        view.zoom = 26;
        if (cap != null) view.centerOn(cap.x, cap.y);
        screen = Screen.PLAY;
        panel = PanelKind.NONE;
        selCity = 0;
        speed = 1;
        resetPlayState();
        for (Nation n : world.nations.values()) sim.rel(me, n);
        toast("Welcome, " + Names.leaderTitle(me.gov) + ". Found cities, build farms and mines, and grow your nation.", false);
    }

    final String[] SIZE_HINT = new String[WorldSize.values().length];

    void drawNew(Graphics2D g, double dt) {
        g.setPaint(new GradientPaint(0, 0, new Color(0x0d1730), 0, H, new Color(0x16294d)));
        g.fillRect(0, 0, W, H);
        g.setPaint(null);
        int m = ui.px(16);
        // left: size list
        int lw = ui.px(300);
        ui.panel(m, m, lw, H - 2 * m);
        ui.text("WORLD SIZE", m + ui.px(16), m + ui.px(30), ui.big, Ui.GOLD);
        int ry = m + ui.px(44), rh = ui.px(31);
        for (WorldSize s : WorldSize.values()) {
            final WorldSize fs = s;
            String right = s.infinite() ? "infinite" : s.tiles + "²";
            boolean on = s == ngSize;
            ui.button(s.label, m + ui.px(12), ry, lw - ui.px(24), rh, on, true, () -> {
                ngSize = fs;
                newPreview();
            }, s.infinite() ? "Endless procedural world. It keeps growing as nations spread." : s.label + ": " + s.tiles + " x " + s.tiles + " tiles, " + s.startNations + " nations");
            ui.textRight(right, m + lw - ui.px(24), ry + rh / 2 + ui.px(5), ui.small, on ? Ui.GOLD : Ui.DIM);
            ry += rh + ui.px(4);
        }
        ry += ui.px(8);
        ui.text("SEED", m + ui.px(16), ry + ui.px(14), ui.bold, Ui.DIM);
        int fy = ry + ui.px(22);
        textField(m + ui.px(12), fy, lw - ui.px(24) - ui.px(52), ui.px(32), ngSeedText, ngFocus == 2, () -> ngFocus = 2);
        ui.button("Roll", m + lw - ui.px(12) - ui.px(46), fy, ui.px(46), ui.px(32), false, true, () -> {
            ngSeed = new Random().nextInt(900000) + 100000;
            ngSeedText = String.valueOf(ngSeed);
            newPreview();
        }, "New random seed");
        ui.text("Nations at start: " + ngSize.startNations, m + ui.px(16), fy + ui.px(52), ui.norm, Ui.DIM);
        ui.button("Back", m + ui.px(12), H - m - ui.px(48), lw - ui.px(24), ui.px(36), false, true, () -> screen = Screen.MENU, null);

        // right: preview and setup
        int rx = m + lw + m;
        int availW = W - rx - m;
        int setupH = ui.px(118);
        int size = Math.min(availW, H - 2 * m - setupH - ui.px(10));
        ngPreviewRect.setBounds(rx + (availW - size) / 2, m, size, size);
        ui.panel(ngPreviewRect.x - ui.px(6), ngPreviewRect.y - ui.px(6), size + ui.px(12), size + ui.px(12));
        BufferedImage im = ngMap == null ? null : ngMap.img;
        requestPreview();
        if (im != null) g.drawImage(im, ngPreviewRect.x, ngPreviewRect.y, size, size, null);
        else {
            g.setColor(new Color(0x0a1830));
            g.fillRect(ngPreviewRect.x, ngPreviewRect.y, size, size);
        }
        if (ngMap != null && ngMap.busy) {
            ui.textShadow("Generating world...", ngPreviewRect.x + ui.px(12), ngPreviewRect.y + ui.px(24), ui.bold, Color.WHITE);
        }
        ui.block(ngPreviewRect.x, ngPreviewRect.y, 0, 0);
        if (ngHasStart && im != null) {
            double tpp = ngMap.tpp;
            double px = ngPreviewRect.x + (ngStartX - ngMap.cx) / tpp + ngMapPx / 2.0;
            double py = ngPreviewRect.y + (ngStartY - ngMap.cy) / tpp + ngMapPx / 2.0;
            if (px >= ngPreviewRect.x && py >= ngPreviewRect.y && px < ngPreviewRect.x + size && py < ngPreviewRect.y + size) {
                g.setColor(new Color(Names.COLORS[ngColor]));
                int fl = ui.px(26);
                g.setColor(new Color(0, 0, 0, 150));
                g.fillOval((int) px - ui.px(5), (int) py - ui.px(3), ui.px(10), ui.px(6));
                g.setColor(new Color(0x3a2414));
                g.fillRect((int) px - 1, (int) py - fl, ui.px(2), fl);
                g.setColor(new Color(Names.COLORS[ngColor]));
                g.fillRect((int) px + ui.px(1), (int) py - fl, ui.px(16), ui.px(10));
                g.setColor(Color.WHITE);
                g.drawRect((int) px + ui.px(1), (int) py - fl, ui.px(16), ui.px(10));
            }
        }
        if (!ngHasStart) ui.textShadow("Click the map to choose your starting point" + (ngSize.infinite() ? "  (drag to explore, wheel to zoom)" : ""),
                ngPreviewRect.x + ui.px(12), ngPreviewRect.y + size - ui.px(14), ui.bold, Color.WHITE);

        // setup row
        int sy = ngPreviewRect.y + size + ui.px(14);
        ui.panel(rx, sy, availW, setupH - ui.px(4));
        int px0 = rx + ui.px(14);
        ui.text("NATION", px0, sy + ui.px(24), ui.bold, Ui.DIM);
        textField(px0, sy + ui.px(32), ui.px(210), ui.px(32), ngName, ngFocus == 1, () -> ngFocus = 1);
        ui.button("Dice", px0 + ui.px(216), sy + ui.px(32), ui.px(48), ui.px(32), false, true, () -> ngName = Names.nation(new Random()), "Random name");
        ui.text("GOVERNMENT", px0 + ui.px(290), sy + ui.px(24), ui.bold, Ui.DIM);
        ui.button("<", px0 + ui.px(290), sy + ui.px(32), ui.px(32), ui.px(32), false, true, () -> ngGovIdx = (ngGovIdx + Names.GOVS.length - 1) % Names.GOVS.length, null);
        ui.textCenter(Names.GOVS[ngGovIdx], px0 + ui.px(290) + ui.px(32) + ui.px(55), sy + ui.px(53), ui.bold, Ui.TEXT);
        ui.button(">", px0 + ui.px(290) + ui.px(142), sy + ui.px(32), ui.px(32), ui.px(32), false, true, () -> ngGovIdx = (ngGovIdx + 1) % Names.GOVS.length, null);
        ui.text("COLOR", px0, sy + ui.px(84), ui.bold, Ui.DIM);
        int cs = ui.px(20);
        for (int i = 0; i < 12; i++) {
            final int fi = i;
            ui.swatch(px0 + ui.px(60) + i * (cs + ui.px(5)), sy + ui.px(68), cs, Names.COLORS[i], ngColor == i, () -> ngColor = fi);
        }
        int sbw = ui.px(210), sbh = ui.px(50);
        ui.button("FOUND NATION", rx + availW - sbw - ui.px(14), sy + ui.px(30), sbw, sbh, true, true, () -> startGame(),
                "Start with your capital at the flag (or the best nearby land)");
        if (ngHasStart) ui.text("Start: " + ngStartX + ", " + ngStartY, rx + availW - sbw - ui.px(14), sy + ui.px(96), ui.small, Ui.DIM);
    }

    void textField(int x, int y, int w, int h, String text, boolean focused, Runnable click) {
        Graphics2D g = ui.g;
        g.setColor(new Color(8, 12, 24, 230));
        g.fillRoundRect(x, y, w, h, ui.px(8), ui.px(8));
        g.setColor(focused ? Ui.GOLD : Ui.BORDER);
        g.drawRoundRect(x, y, w, h, ui.px(8), ui.px(8));
        g.setFont(ui.norm);
        FontMetrics fm = g.getFontMetrics();
        g.setColor(Ui.TEXT);
        String shown = text + (focused && ((int) (clock * 2) % 2 == 0) ? "|" : "");
        g.drawString(shown, x + ui.px(8), y + (h + fm.getAscent() - fm.getDescent()) / 2);
        ui.hotspot(x, y, w, h, click, null);
    }

    // ================= play =================
    boolean hasMe() {
        return me != null && me.alive;
    }

    void toast(String s, boolean err) {
        toasts.add(new Object[]{s, clock + 4.0, err});
        if (toasts.size() > 5) toasts.remove(0);
    }

    void drawPlay(Graphics2D g, double dt) {
        view.vw = W;
        view.vh = H;
        // camera keys
        double pan = 520 * dt / view.zoom * Math.max(1, view.zoom > 20 ? 1 : 1.4);
        if (panel != PanelKind.PAUSE && panel != PanelKind.SAVES && ngFocus == 0) {
            if (keys[KeyEvent.VK_W] || keys[KeyEvent.VK_UP]) view.camY -= pan;
            if (keys[KeyEvent.VK_S] || keys[KeyEvent.VK_DOWN]) view.camY += pan;
            if (keys[KeyEvent.VK_A] || keys[KeyEvent.VK_LEFT]) view.camX -= pan;
            if (keys[KeyEvent.VK_D] || keys[KeyEvent.VK_RIGHT]) view.camX += pan;
        }
        double[] acc = {simAcc};
        if (speed > 0 && panel != PanelKind.PAUSE) stepWorld(sim, dt, SPEED_RATE[speed], acc);
        simAcc = acc[0];
        view.update(dt);
        view.draw(g, me != null ? me.id : 0);

        City sel = world.cities.get(selCity);
        if (sel == null) selCity = 0;
        if (sel != null) drawSelection(g, sel);
        if (hasMe() && panel == PanelKind.NONE) drawToolPreview(g);

        drawHud(g, dt);
        if (world.gameOver && me != null) drawGameOver(g);
    }

    void drawSelection(Graphics2D g, City c) {
        double x = view.sx(c.x + 0.5), y = view.sy(c.y + 0.5);
        double r = Math.max(10, view.zoom * (0.9 + 0.1 * Math.sin(clock * 4)));
        g.setColor(new Color(255, 255, 255, 220));
        g.setStroke(new BasicStroke(2.5f));
        g.drawOval((int) (x - r), (int) (y - r), (int) (2 * r), (int) (2 * r));
        g.setStroke(new BasicStroke(1f));
    }

    void drawToolPreview(Graphics2D g) {
        if (tool == Tool.SELECT) return;
        if (ui.overUi(mouseX, mouseY)) return;
        int tx = view.tileX(mouseX), ty = view.tileY(mouseY);
        double x = view.sx(tx), y = view.sy(ty), z = view.zoom;
        if (tool == Tool.FOUND) {
            double sc = sim.siteScore(tx, ty, me.id);
            double[] cost = sim.foundCost(me);
            boolean ok = sc >= 0 && me.gold >= cost[0] && me.wood >= cost[1] && me.stone >= cost[2];
            Color c = ok ? new Color(80, 255, 120) : new Color(255, 90, 80);
            double r = 10 * z;
            g.setColor(new Color(c.getRed(), c.getGreen(), c.getBlue(), 40));
            g.fillOval((int) (x + z / 2 - r), (int) (y + z / 2 - r), (int) (2 * r), (int) (2 * r));
            g.setColor(c);
            g.setStroke(new BasicStroke(2f, BasicStroke.CAP_BUTT, BasicStroke.JOIN_MITER, 10f, new float[]{8f, 6f}, 0));
            g.drawOval((int) (x + z / 2 - r), (int) (y + z / 2 - r), (int) (2 * r), (int) (2 * r));
            g.setStroke(new BasicStroke(1f));
            g.drawRect((int) x, (int) y, (int) z, (int) z);
        } else {
            int type = toolType(tool);
            String err = sim.checkBuild(me, type, tx, ty);
            Color c = err == null ? new Color(80, 255, 120) : new Color(255, 90, 80);
            g.setColor(new Color(c.getRed(), c.getGreen(), c.getBlue(), 70));
            g.fillRect((int) x, (int) y, (int) z + 1, (int) z + 1);
            g.setColor(c);
            g.setStroke(new BasicStroke(2f));
            g.drawRect((int) x, (int) y, (int) z, (int) z);
            g.setStroke(new BasicStroke(1f));
        }
    }

    int toolType(Tool t) {
        switch (t) {
            case FARM: return Terrain.FARM;
            case LUMBER: return Terrain.LUMBER;
            case MINE: return Terrain.MINE;
            case DOCK: return Terrain.DOCK;
            case TOWER: return Terrain.TOWER;
            case ROAD: return Terrain.ROAD;
            default: return 0;
        }
    }

    static String fmt(double v) {
        double a = Math.abs(v);
        if (a >= 1e6) return String.format("%.1fM", v / 1e6);
        if (a >= 1e4) return String.format("%.1fk", v / 1e3);
        if (a >= 1000) return String.format("%.2fk", v / 1e3);
        return String.valueOf((long) v);
    }

    void drawHud(Graphics2D g, double dt) {
        int bh = ui.px(46);
        // ---- top bar ----
        ui.panel(-ui.px(12), -ui.px(12), W + ui.px(24), bh + ui.px(12));
        int x = ui.px(12);
        if (me != null) {
            g.setColor(new Color(me.color));
            g.fillRoundRect(x, ui.px(8), ui.px(26), ui.px(30), ui.px(6), ui.px(6));
            g.setColor(Color.WHITE);
            g.drawRoundRect(x, ui.px(8), ui.px(26), ui.px(30), ui.px(6), ui.px(6));
            ui.text(me.name, x + ui.px(36), ui.px(23), ui.big, Ui.TEXT);
            ui.text(Names.leaderTitle(me.gov) + " " + me.leader, x + ui.px(36), ui.px(38), ui.small, Ui.DIM);
            x += ui.px(236);
        } else {
            ui.text("Spectating", x, ui.px(30), ui.big, Ui.GOLD);
            x += ui.px(150);
        }
        int month = world.turn % 12;
        ui.text("Year " + world.year(), x, ui.px(22), ui.bold, Ui.TEXT);
        ui.text(MONTHS[month] + (me != null ? "  ·  " + me.eraName() + " Age" : ""), x, ui.px(38), ui.small, Ui.DIM);
        x += ui.px(150);
        BufferedImage[] sp = {Icons.speed0, Icons.speed1, Icons.speed2, Icons.speed3, Icons.speed4};
        String[] spTip = {"Pause (Space)", "Normal speed (1)", "Fast (2)", "Faster (3)", "Fastest (4)"};
        for (int i = 0; i < 5; i++) {
            final int fi = i;
            ui.iconButton(sp[i], x + i * ui.px(31), ui.px(8), ui.px(30), speed == i, true, () -> speed = fi, spTip[i]);
        }
        x += ui.px(168);
        if (me != null) {
            x = chip(Icons.gold, fmt(me.gold), (me.income >= 0 ? "+" : "") + fmt(me.income) + "/mo", me.income >= 0 ? Ui.GOOD : Ui.BAD, x, "Gold: " + (int) me.gold + "\nIncome per month: " + String.format("%+.1f", me.income));
            x = chip(Icons.wood, fmt(me.wood), null, null, x, "Wood: " + (int) me.wood + "\nBuilding material");
            x = chip(Icons.stone, fmt(me.stone), null, null, x, "Stone: " + (int) me.stone + "\nMines on mountain tiles produce stone and a little gold");
            x = chip(Icons.pop, fmt(me.pop), me.foodBalance >= 0 ? "fed" : "hungry", me.foodBalance >= 0 ? Ui.GOOD : Ui.BAD, x, "Population across " + me.cityCount + " cities");
            x = chip(Icons.sword, fmt(me.soldiers), null, null, x, "Soldiers at home\nPower: " + fmt(me.power));
            double nextCost = me.era < Nation.ERAS.length - 1 ? Nation.ERA_COST[me.era + 1] : me.science;
            x = chip(Icons.science, fmt(me.science), me.era < Nation.ERAS.length - 1 ? "/" + fmt(nextCost) : "max", Ui.DIM, x, "Research toward the next age");
        }
        ui.iconButton(Icons.menu, W - ui.px(42), ui.px(8), ui.px(30), false, true, () -> panel = panel == PanelKind.PAUSE ? PanelKind.NONE : PanelKind.PAUSE, "Menu (Esc)");

        // ---- toolbar ----
        if (hasMe()) {
            int tx = ui.px(8), ty = ui.px(58), ts = ui.px(46), tg = ui.px(6);
            Tool[] tools = Tool.values();
            BufferedImage[] ic = {Icons.select, Icons.found, Icons.farm, Icons.lumber, Icons.mine, Icons.dock, Icons.tower, Icons.road};
            double[] fc = sim.foundCost(me);
            String[] tip = {"Select (Esc)\nClick cities to inspect them",
                    String.format("Found City\n%d gold, %d wood, %d stone\nWithin 34 tiles of one of your cities", (int) fc[0], (int) fc[1], (int) fc[2]),
                    "Farm - 3 wood\nFeeds your people. Best on grassland by water",
                    "Lumber Camp - 4 wood\nHarvests nearby forest",
                    "Mine - 6 wood, 2 stone\nOn mountain tiles. Stone and gold",
                    "Dock - 8 wood\nOn the coast. Trade income, ships",
                    "Watch Tower - 5 gold, 6 wood, 10 stone\nStrengthens city defence",
                    "Road - 1 wood per tile\nConnect your cities"};
            ui.panel(tx - ui.px(4), ty - ui.px(4), ts + ui.px(8), tools.length * (ts + tg) + ui.px(4) + 2 * (ts + tg) + ui.px(8));
            for (int i = 0; i < tools.length; i++) {
                final Tool ft = tools[i];
                ui.iconButton(ic[i], tx, ty + i * (ts + tg), ts, tool == ft, true, () -> {
                    tool = ft;
                    if (ft != Tool.SELECT) panel = PanelKind.NONE;
                }, tip[i]);
            }
            int by = ty + tools.length * (ts + tg) + ui.px(6);
            ui.iconButton(Icons.policy, tx, by, ts, panel == PanelKind.POLICY, true, () -> {
                panel = panel == PanelKind.POLICY ? PanelKind.NONE : PanelKind.POLICY;
                tool = Tool.SELECT;
            }, "Government (G)\nTaxes, military, science, research");
            ui.iconButton(Icons.diplo, tx, by + ts + tg, ts, panel == PanelKind.DIPLO, true, () -> {
                panel = panel == PanelKind.DIPLO ? PanelKind.NONE : PanelKind.DIPLO;
                tool = Tool.SELECT;
            }, "Diplomacy (F)\nWar, peace, alliances");
        } else {
            ui.iconButton(Icons.diplo, ui.px(8), ui.px(58), ui.px(46), panel == PanelKind.DIPLO, true, () -> panel = panel == PanelKind.DIPLO ? PanelKind.NONE : PanelKind.DIPLO, "Nations");
        }

        // ---- panels ----
        if (panel == PanelKind.POLICY && hasMe()) drawPolicy(g);
        if (panel == PanelKind.DIPLO) drawDiplo(g);
        City sel = world.cities.get(selCity);
        if (sel != null && panel != PanelKind.PAUSE) drawCityPanel(g, sel);

        // ---- minimap ----
        drawMinimap(g, dt);

        // ---- log / offers / toasts / hover ----
        drawLog(g);
        drawOffers(g);
        drawToasts(g);
        drawHover(g);
        if (panel == PanelKind.PAUSE) drawPause(g);
        if (panel == PanelKind.SAVES) drawSavesPanel(g, false);
    }

    int chip(BufferedImage icon, String main, String sub, Color subColor, int x, String tip) {
        Graphics2D g = ui.g;
        int y = ui.px(8), h = ui.px(30);
        g.setFont(ui.bold);
        int w = ui.px(34) + g.getFontMetrics().stringWidth(main) + (sub != null ? ui.textWidth(sub, ui.small) + ui.px(6) : 0) + ui.px(10);
        g.setColor(new Color(255, 255, 255, 18));
        g.fillRoundRect(x, y, w, h, ui.px(8), ui.px(8));
        g.drawImage(icon, x + ui.px(6), y + ui.px(5), ui.px(20), ui.px(20), null);
        ui.text(main, x + ui.px(30), y + ui.px(20), ui.bold, Ui.TEXT);
        if (sub != null) ui.text(sub, x + ui.px(34) + ui.textWidth(main, ui.bold), y + ui.px(20), ui.small, subColor);
        if (ui.hover(x, y, w, h)) ui.tooltip = tip;
        return x + w + ui.px(6);
    }

    void drawLog(Graphics2D g) {
        int y = H - ui.px(34);
        int shown = 0;
        for (int i = world.log.size() - 1; i >= 0 && shown < 5; i--) {
            World.LogEntry e = world.log.get(i);
            int age = world.turn - e.turn;
            if (age > 30) break;
            if (!e.important && age > 12) continue;
            float a = (float) Math.max(0.0, Math.min(1.0, 1.0 - (age - 10) / 20.0));
            Nation n = world.nation(e.nation);
            int ly = y - shown * ui.px(19);
            g.setFont(ui.norm);
            String line = e.text;
            int tw = g.getFontMetrics().stringWidth(line);
            g.setColor(new Color(0, 0, 0, (int) (130 * a)));
            g.fillRoundRect(ui.px(10), ly - ui.px(14), tw + ui.px(30), ui.px(19), ui.px(6), ui.px(6));
            if (n != null) {
                g.setColor(new Color((n.color & 0xFFFFFF) | ((int) (255 * a) << 24), true));
                g.fillRect(ui.px(15), ly - ui.px(10), ui.px(6), ui.px(11));
            }
            g.setColor(new Color(1f, 1f, 1f, a));
            g.drawString(line, ui.px(26), ly);
            shown++;
        }
    }

    void drawToasts(Graphics2D g) {
        toasts.removeIf(t -> (Double) t[1] < clock);
        int y = ui.px(64);
        for (Object[] t : toasts) {
            String s = (String) t[0];
            boolean err = (Boolean) t[2];
            g.setFont(ui.bold);
            int w = g.getFontMetrics().stringWidth(s) + ui.px(28);
            int x = (W - w) / 2;
            double life = (Double) t[1] - clock;
            float a = (float) Math.min(1, life * 2);
            g.setColor(new Color(err ? 0x6a1c1c : 0x16304a, false));
            g.setColor(new Color(err ? 120 : 20, err ? 30 : 50, err ? 30 : 80, (int) (230 * a)));
            g.fillRoundRect(x, y, w, ui.px(30), ui.px(10), ui.px(10));
            g.setColor(new Color(err ? 255 : 120, err ? 130 : 200, err ? 120 : 255, (int) (255 * a)));
            g.drawRoundRect(x, y, w, ui.px(30), ui.px(10), ui.px(10));
            g.setColor(new Color(1f, 1f, 1f, a));
            g.drawString(s, x + ui.px(14), y + ui.px(20));
            y += ui.px(36);
        }
    }

    void drawOffers(Graphics2D g) {
        if (me == null) return;
        int y = ui.px(100) + toasts.size() * ui.px(36);
        for (Sim.Offer o : new ArrayList<>(sim.offers)) {
            if (o.to != me.id) continue;
            Nation from = world.nation(o.from);
            if (from == null || !from.alive) continue;
            String msg = from.name + (o.type == 0 ? " offers peace" : " proposes an alliance");
            int w = ui.px(430), h = ui.px(44);
            int x = (W - w) / 2;
            ui.panel(x, y, w, h);
            g.setColor(new Color(from.color));
            g.fillRect(x + ui.px(10), y + ui.px(10), ui.px(8), ui.px(24));
            ui.text(msg, x + ui.px(26), y + ui.px(27), ui.bold, Ui.TEXT);
            ui.button("Accept", x + w - ui.px(164), y + ui.px(7), ui.px(74), ui.px(30), true, true, () -> {
                String e = sim.acceptOffer(o);
                if (e != null) toast(e, true);
            }, null);
            ui.button("Decline", x + w - ui.px(84), y + ui.px(7), ui.px(74), ui.px(30), false, true, () -> sim.offers.remove(o), null);
            y += h + ui.px(6);
        }
    }

    void drawHover(Graphics2D g) {
        if (ui.overUi(mouseX, mouseY) || mouseX < 0) return;
        int tx = view.tileX(mouseX), ty = view.tileY(mouseY);
        if (!world.inBounds(tx, ty)) return;
        byte t = world.terrainAt(tx, ty);
        int own = world.ownerAt(tx, ty);
        Nation n = world.nation(own);
        String s = Terrain.name(t) + (n != null ? "  ·  " + n.name : "  ·  unclaimed") + "  ·  (" + tx + ", " + ty + ")";
        g.setFont(ui.small);
        int w = g.getFontMetrics().stringWidth(s) + ui.px(16);
        g.setColor(new Color(0, 0, 0, 130));
        g.fillRoundRect(ui.px(10), H - ui.px(22), w, ui.px(18), ui.px(6), ui.px(6));
        g.setColor(new Color(0xd8e2ff));
        g.drawString(s, ui.px(18), H - ui.px(9));
    }

    // ---- minimap ----
    int mmX, mmY, mmSize;

    void drawMinimap(Graphics2D g, double dt) {
        mmSize = ui.px(190);
        mmX = W - mmSize - ui.px(14);
        mmY = H - mmSize - ui.px(14);
        mmTimer += dt;
        int px = mmSize;
        boolean far = mm.img == null || (!world.bounded && (Math.abs(view.camX - mm.cx) > 350 || Math.abs(view.camY - mm.cy) > 350));
        if ((mmTimer > 6 || far) && !mm.busy) {
            mmTimer = 0;
            ArrayList<int[]> pts = new ArrayList<>();
            for (City c : world.cities.values()) {
                Nation n = world.nation(c.nation);
                pts.add(new int[]{c.x, c.y, n != null ? n.color : 0xffffff, c.capital ? 1 : 0});
            }
            double cx = world.bounded ? world.N / 2.0 : view.camX, cy = world.bounded ? world.N / 2.0 : view.camY;
            double tpp = world.bounded ? world.N / (double) px : 8;
            mm.request(world, cx, cy, tpp, px, tpp <= 6, pts);
        }
        ui.panel(mmX - ui.px(6), mmY - ui.px(6), mmSize + ui.px(12), mmSize + ui.px(12));
        BufferedImage im = mm.img;
        if (im != null) {
            g.drawImage(im, mmX, mmY, mmSize, mmSize, null);
            double tpp = mm.tpp;
            double vwT = view.vw / view.zoom, vhT = view.vh / view.zoom;
            double rx = (view.camX - vwT / 2 - mm.cx) / tpp + im.getWidth() / 2.0, ry = (view.camY - vhT / 2 - mm.cy) / tpp + im.getHeight() / 2.0;
            Shape old = g.getClip();
            g.setClip(mmX, mmY, mmSize, mmSize);
            g.setColor(Color.WHITE);
            g.setStroke(new BasicStroke(1.5f));
            g.drawRect((int) (mmX + rx), (int) (mmY + ry), (int) Math.max(3, vwT / tpp), (int) Math.max(3, vhT / tpp));
            g.setStroke(new BasicStroke(1f));
            g.setClip(old);
        }
        ui.hotspot(mmX, mmY, mmSize, mmSize, () -> minimapClick(mouseX, mouseY), "Minimap - click to jump");
    }

    void minimapClick(int x, int y) {
        if (mm == null || mm.img == null) return;
        double tpp = mm.tpp;
        double wx = mm.cx + (x - mmX - mm.img.getWidth() * (mmSize / (double) mm.img.getWidth()) / 2.0) * tpp * (mm.img.getWidth() / (double) mmSize);
        double wy = mm.cy + (y - mmY - mmSize / 2.0) * tpp * (mm.img.getWidth() / (double) mmSize);
        view.camX = wx;
        view.camY = wy;
        view.clampCamera();
    }

    // ---- city panel ----
    void drawCityPanel(Graphics2D g, City c) {
        Nation owner = world.nation(c.nation);
        boolean mine = me != null && c.nation == me.id;
        int w = ui.px(300), x = W - w - ui.px(10), y = ui.px(58);
        int h = ui.px(mine ? 276 : 232);
        ui.panel(x, y, w, h);
        int pad = ui.px(14);
        if (owner != null) {
            g.setColor(new Color(owner.color));
            g.fillRect(x + pad, y + ui.px(14), ui.px(8), ui.px(34));
        }
        ui.text(c.name + (c.capital ? "  ★" : ""), x + pad + ui.px(16), y + ui.px(30), ui.big, Ui.TEXT);
        ui.text(c.levelName() + " of " + (owner != null ? owner.name : "?"), x + pad + ui.px(16), y + ui.px(46), ui.small, Ui.DIM);
        ui.button("x", x + w - ui.px(36), y + ui.px(10), ui.px(26), ui.px(24), false, true, () -> selCity = 0, "Close");
        int ly = y + ui.px(70), lh = ui.px(22);
        ui.text("Population", x + pad, ly, ui.norm, Ui.DIM);
        ui.textRight(String.valueOf((int) c.pop) + (mine ? " / " + (int) c.housingCap() : ""), x + w - pad, ly, ui.bold, Ui.TEXT);
        ly += lh;
        if (mine) {
            ui.text("Food", x + pad, ly, ui.norm, Ui.DIM);
            ui.bar(x + pad + ui.px(90), ly - ui.px(10), w - 2 * pad - ui.px(90), ui.px(10), c.food / 2.0, c.food >= 1 ? Ui.GOOD : Ui.BAD);
            ly += lh;
            ui.text("Happiness", x + pad, ly, ui.norm, Ui.DIM);
            ui.bar(x + pad + ui.px(90), ly - ui.px(10), w - 2 * pad - ui.px(90), ui.px(10), c.happiness / 100.0, c.happiness > 50 ? Ui.GOOD : c.happiness > 30 ? Ui.GOLD : Ui.BAD);
            ly += lh;
            ui.text("Buildings", x + pad, ly, ui.norm, Ui.DIM);
            ui.textRight(c.houses + " houses  \u00B7  " + c.farms + " farms", x + w - pad, ly, ui.small, Ui.TEXT);
            ly += lh - ui.px(5);
            ui.textRight(c.lumbers + " lumber  \u00B7  " + c.mines + " mines  \u00B7  " + c.docks + " docks", x + w - pad, ly, ui.small, Ui.TEXT);
            ly += lh;
            ui.text("Defence", x + pad, ly, ui.norm, Ui.DIM);
            ui.textRight(String.valueOf((int) sim.cityDefense(c)) + (c.towers > 0 ? "  (" + c.towers + " towers)" : ""), x + w - pad, ly, ui.bold, Ui.TEXT);
            ly += lh;
            ui.text("Founded", x + pad, ly, ui.norm, Ui.DIM);
            ui.textRight("Year " + (1 + c.founded / 12), x + w - pad, ly, ui.norm, Ui.TEXT);
            ui.button("Zoom to city", x + pad, y + h - ui.px(44), w - 2 * pad, ui.px(32), false, true, () -> {
                view.centerOn(c.x, c.y);
                view.zoom = Math.max(view.zoom, 24);
            }, null);
        } else if (hasMe() && owner != null) {
            Relation rl = sim.rel(me, owner);
            boolean war = rl.state == Relation.WAR;
            ui.text("Relations", x + pad, ly, ui.norm, Ui.DIM);
            ui.textRight(war ? "At war" : rl.state == Relation.ALLY ? "Allied" : "At peace", x + w - pad, ly, ui.bold, war ? Ui.BAD : rl.state == Relation.ALLY ? Ui.GOOD : Ui.TEXT);
            ly += lh;
            double def = sim.cityDefense(c);
            ui.text("Est. defence", x + pad, ly, ui.norm, Ui.DIM);
            ui.textRight(String.valueOf((int) def), x + w - pad, ly, ui.bold, Ui.TEXT);
            ly += lh;
            ui.text("Your soldiers", x + pad, ly, ui.norm, Ui.DIM);
            ui.textRight(String.valueOf((int) me.soldiers), x + w - pad, ly, ui.bold, Ui.TEXT);
            ly += lh;
            if (war) {
                ui.button("Attack (60% of army)", x + pad, y + h - ui.px(84), w - 2 * pad, ui.px(32), true, true, () -> toastResult(sim.sendArmy(me, c, 0.6), "Army marching on " + c.name + "!"), "Sends soldiers overland. Wins if attack beats defence");
                ui.button("All-out attack", x + pad, y + h - ui.px(44), w - 2 * pad, ui.px(32), false, true, () -> toastResult(sim.sendArmy(me, c, 0.95), "All forces marching on " + c.name + "!"), null);
            } else {
                ui.button("Declare war on " + owner.name, x + pad, y + h - ui.px(44), w - 2 * pad, ui.px(32), false, true, () -> {
                    sim.declareWar(me, owner);
                    toast("You declared war on " + owner.name + "!", false);
                }, "Breaks any alliance. Their allies may join");
            }
        }
    }

    void toastResult(String err, String ok) {
        if (err != null) toast(err, true);
        else toast(ok, false);
    }

    // ---- policy panel ----
    void drawPolicy(Graphics2D g) {
        int w = ui.px(400), x = ui.px(68), y = ui.px(58), h = ui.px(556);
        ui.panel(x, y, w, h);
        int pad = ui.px(18);
        ui.text("Government of " + me.name, x + pad, y + ui.px(30), ui.big, Ui.GOLD);
        ui.text(me.fullName() + " · " + me.eraName() + " Age", x + pad, y + ui.px(48), ui.small, Ui.DIM);
        int ly = y + ui.px(78), sw = w - 2 * pad;
        ui.text("Taxes  " + (int) (me.tax * 100) + "%", x + pad, ly, ui.bold, Ui.TEXT);
        ui.text("more gold, less happiness", x + w - pad - ui.textWidth("more gold, less happiness", ui.small), ly, ui.small, Ui.DIM);
        ui.slider(x + pad, ly + ui.px(8), sw, me.tax, v -> me.tax = v, Ui.GOLD, "Taxes");
        ly += ui.px(58);
        ui.text("Military  " + (int) (me.military * 100) + "%", x + pad, ly, ui.bold, Ui.TEXT);
        ui.text("soldiers cost upkeep", x + w - pad - ui.textWidth("soldiers cost upkeep", ui.small), ly, ui.small, Ui.DIM);
        ui.slider(x + pad, ly + ui.px(8), sw, me.military, v -> me.military = v, Ui.BAD, "Military spending");
        ly += ui.px(58);
        ui.text("Science  " + (int) (me.sciencePolicy * 100) + "%", x + pad, ly, ui.bold, Ui.TEXT);
        ui.text("faster ages", x + w - pad - ui.textWidth("faster ages", ui.small), ly, ui.small, Ui.DIM);
        ui.slider(x + pad, ly + ui.px(8), sw, me.sciencePolicy, v -> me.sciencePolicy = v, new Color(0x60e0a0), "Research effort");
        ly += ui.px(50);
        ui.text("City building focus", x + pad, ly, ui.bold, Ui.TEXT);
        String[] fl = {"Balanced", "Farming", "Industry", "Trade"};
        int bw = (sw - ui.px(18)) / 4;
        for (int i = 0; i < 4; i++) {
            final int fi = i;
            ui.button(fl[i], x + pad + i * (bw + ui.px(6)), ly + ui.px(10), bw, ui.px(30), me.focus == i, true, () -> me.focus = fi, null);
        }
        ly += ui.px(64);
        ui.button(me.autoExpand ? "Auto-settle: ON" : "Auto-settle: OFF", x + pad, ly, sw, ui.px(32), me.autoExpand, true, () -> me.autoExpand = !me.autoExpand,
                "Let advisors found new cities automatically when you can afford them");
        ly += ui.px(44);
        ui.button("Hire soldiers (200 gold)", x + pad, ly, (sw - ui.px(8)) / 2, ui.px(32), false, me.gold >= 200, () -> toastResult(sim.recruit(me, 200), "Hired 100 soldiers"), "2 gold per soldier");
        ui.button("Fund research (200 gold)", x + pad + (sw + ui.px(8)) / 2, ly, (sw - ui.px(8)) / 2, ui.px(32), false, me.gold >= 200, () -> toastResult(sim.fundScience(me, 200), "Research funded"), "2 gold per research point");
        ly += ui.px(52);
        ui.text("Research", x + pad, ly, ui.bold, Ui.TEXT);
        double nextCost = me.era < Nation.ERAS.length - 1 ? Nation.ERA_COST[me.era + 1] : me.science;
        double prev = Nation.ERA_COST[me.era];
        ui.bar(x + pad + ui.px(80), ly - ui.px(10), sw - ui.px(80), ui.px(12), me.era < Nation.ERAS.length - 1 ? (me.science - prev) / (nextCost - prev) : 1, new Color(0x60e0a0));
        ly += ui.px(26);
        ui.text("Income " + String.format("%+.1f", me.income) + " gold/month  ·  food " + (me.foodBalance >= 0 ? "surplus" : "deficit"), x + pad, ly, ui.norm, me.income >= 0 ? Ui.GOOD : Ui.BAD);
        ly += ui.px(26);
        ui.text("Your cities", x + pad, ly, ui.bold, Ui.GOLD);
        ArrayList<City> mine = new ArrayList<>(sim.citiesOf(me));
        mine.sort((a, b) -> Double.compare(b.pop, a.pop));
        int row = 0;
        for (City c : mine) {
            if (row >= 4) break;
            final City fc = c;
            ui.button(c.name + (c.capital ? " ★" : "") + "  -  " + (int) c.pop, x + pad, ly + ui.px(8) + row * ui.px(30), sw, ui.px(26), false, true, () -> {
                view.centerOn(fc.x, fc.y);
                view.zoom = Math.max(view.zoom, 20);
                selCity = fc.id;
                panel = PanelKind.NONE;
            }, null);
            row++;
        }
        if (mine.size() > 4) ui.text("+" + (mine.size() - 4) + " more", x + pad, ly + ui.px(8) + row * ui.px(30) + ui.px(14), ui.small, Ui.DIM);
    }

    // ---- diplomacy ----
    void drawDiplo(Graphics2D g) {
        int w = ui.px(560), x = ui.px(68), y = ui.px(58), h = Math.min(H - ui.px(80), ui.px(600));
        ui.panel(x, y, w, h);
        int pad = ui.px(16);
        ui.text("Nations of the world", x + pad, y + ui.px(30), ui.big, Ui.GOLD);
        ArrayList<Nation> list = new ArrayList<>();
        for (Nation n : sim.aliveNations()) if (n != me) list.add(n);
        final Nation fme = me;
        list.sort((a, b) -> {
            if (fme == null) return Double.compare(b.power, a.power);
            int wa = sim.rel(fme, a).state == Relation.WAR ? 0 : fme.neighbors.contains(a.id) ? 1 : 2;
            int wb = sim.rel(fme, b).state == Relation.WAR ? 0 : fme.neighbors.contains(b.id) ? 1 : 2;
            if (wa != wb) return wa - wb;
            return Double.compare(b.power, a.power);
        });
        ui.text(list.size() + " other nations" + (me != null ? "  (at war / neighbours first)" : ""), x + pad, y + ui.px(48), ui.small, Ui.DIM);
        int rowH = ui.px(62), top = y + ui.px(60), visible = (h - ui.px(70)) / rowH;
        diploScroll = Math.max(0, Math.min(Math.max(0, list.size() - visible), diploScroll));
        Shape oldClip = g.getClip();
        g.setClip(x, top, w, visible * rowH);
        for (int i = 0; i < visible && i + diploScroll < list.size(); i++) {
            Nation n = list.get(i + diploScroll);
            int ry = top + i * rowH;
            g.setColor(new Color(255, 255, 255, i % 2 == 0 ? 14 : 6));
            g.fillRoundRect(x + ui.px(8), ry, w - ui.px(16), rowH - ui.px(4), ui.px(8), ui.px(8));
            g.setColor(new Color(n.color));
            g.fillRoundRect(x + ui.px(14), ry + ui.px(8), ui.px(14), ui.px(40), ui.px(4), ui.px(4));
            ui.text(n.name, x + ui.px(36), ry + ui.px(22), ui.bold, Ui.TEXT);
            ui.text(n.gov + " · " + n.cityCount + " cities · pop " + fmt(n.pop) + " · " + n.eraName(), x + ui.px(36), ry + ui.px(38), ui.small, Ui.DIM);
            if (me != null) {
                Relation rl = sim.rel(me, n);
                String st = rl.state == Relation.WAR ? "AT WAR" : rl.state == Relation.ALLY ? "ALLIED" : rl.opinion > 25 ? "Friendly" : rl.opinion < -25 ? "Hostile" : "Neutral";
                Color sc = rl.state == Relation.WAR ? Ui.BAD : rl.state == Relation.ALLY ? Ui.GOOD : Ui.DIM;
                ui.text(st, x + ui.px(36), ry + ui.px(53), ui.small, sc);
                ui.bar(x + ui.px(100), ry + ui.px(46), ui.px(90), ui.px(7), (rl.opinion + 100) / 200.0, rl.opinion >= 0 ? Ui.GOOD : Ui.BAD);
                int bx = x + w - ui.px(8) - ui.px(250);
                if (rl.state == Relation.WAR) {
                    ui.button("Peace", bx, ry + ui.px(10), ui.px(76), ui.px(28), true, true, () -> toastResult(sim.proposePeace(me, n), "Peace treaty signed with " + n.name), null);
                } else {
                    ui.button("War", bx, ry + ui.px(10), ui.px(76), ui.px(28), false, true, () -> {
                        sim.declareWar(me, n);
                        toast("You declared war on " + n.name, false);
                    }, null);
                }
                if (rl.state == Relation.ALLY) ui.button("Break", bx + ui.px(82), ry + ui.px(10), ui.px(76), ui.px(28), false, true, () -> sim.breakAlliance(me, n), null);
                else ui.button("Ally", bx + ui.px(82), ry + ui.px(10), ui.px(76), ui.px(28), false, rl.state != Relation.WAR, () -> toastResult(sim.proposeAlliance(me, n), "Alliance formed with " + n.name), "Needs good relations");
                ui.button("Gift 100", bx + ui.px(164), ry + ui.px(10), ui.px(78), ui.px(28), false, me.gold >= 100, () -> {
                    sim.giftGold(me, n, 100);
                    toast("Gift sent to " + n.name, false);
                }, "Improves relations");
            } else {
                ui.text("Power " + fmt(n.power), x + w - ui.px(120), ry + ui.px(30), ui.norm, Ui.TEXT);
            }
            final Nation fn = n;
            ui.button("Go", x + w - ui.px(8) - ui.px(250) + ui.px(164), ry + ui.px(10 + 31), ui.px(78), ui.px(18), false, true, () -> {
                for (City c : sim.citiesOf(fn)) if (c.capital) {
                    view.centerOn(c.x, c.y);
                    view.zoom = Math.max(8, Math.min(view.zoom, 14));
                }
            }, "Show capital");
        }
        g.setClip(oldClip);
        if (list.size() > visible) ui.text("scroll for more (" + (diploScroll + 1) + "-" + Math.min(list.size(), diploScroll + visible) + " of " + list.size() + ")", x + pad, y + h - ui.px(12), ui.small, Ui.DIM);
    }

    // ---- pause & saves ----
    void drawPause(Graphics2D g) {
        g.setColor(new Color(0, 0, 0, 120));
        g.fillRect(0, 0, W, H);
        ui.block(0, 0, W, H);
        int w = ui.px(320), h = ui.px(360), x = (W - w) / 2, y = (H - h) / 2;
        ui.panel(x, y, w, h);
        ui.textCenter("Paused", x + w / 2, y + ui.px(42), ui.title, Ui.GOLD);
        int bx = x + ui.px(30), bw = w - ui.px(60), bh = ui.px(40), by = y + ui.px(70), gap = ui.px(10);
        ui.button("Resume", bx, by, bw, bh, true, true, () -> panel = PanelKind.NONE, null);
        ui.button("Save Game", bx, by + (bh + gap), bw, bh, false, me != null, () -> saveNow(), me == null ? "Spectator worlds can't be saved" : null);
        ui.button("Load Game", bx, by + 2 * (bh + gap), bw, bh, false, true, () -> panel = PanelKind.SAVES, null);
        ui.button("UI size  -", bx, by + 3 * (bh + gap), (bw - gap) / 2, bh, false, true, () -> userScale = Math.max(0.6, userScale - 0.1), null);
        ui.button("UI size  +", bx + (bw + gap) / 2, by + 3 * (bh + gap), (bw - gap) / 2, bh, false, true, () -> userScale = Math.min(2.2, userScale + 0.1), null);
        ui.button("Main Menu", bx, by + 4 * (bh + gap), bw, bh, false, true, () -> toMenu(), null);
    }

    void saveNow() {
        try {
            String name = "save-" + new java.text.SimpleDateFormat("MMdd-HHmmss").format(new Date());
            SaveGame.save(world, SaveGame.slot(name));
            toast("Game saved", false);
            panel = PanelKind.NONE;
        } catch (Exception e) {
            e.printStackTrace();
            toast("Save failed: " + e.getMessage(), true);
        }
    }

    void quickSave() {
        if (me == null || screen != Screen.PLAY) return;
        try {
            SaveGame.save(world, SaveGame.slot("quicksave"));
            toast("Quick-saved", false);
        } catch (Exception e) {
            toast("Save failed", true);
        }
    }

    void toMenu() {
        if (world != null && world != mWorld) {
            world.shutdown();
            if (view != null) view.shutdown();
        }
        if (mm != null) mm.shutdown();
        world = null;
        sim = null;
        view = null;
        me = null;
        screen = Screen.MENU;
        panel = PanelKind.NONE;
        initMenuWorld();
    }

    void loadFile(File f) {
        try {
            World w = SaveGame.load(f);
            if (world != null && world != mWorld) {
                world.shutdown();
                if (view != null) view.shutdown();
            }
            if (mWorld != null) {
                mWorld.shutdown();
                mView.shutdown();
                mWorld = null;
            }
            world = w;
            sim = new Sim(w);
            me = w.nation(w.playerNation);
            view = new WorldView(w);
            City cap = null;
            for (City c : w.cities.values()) if (me != null && c.nation == me.id && (cap == null || c.capital)) cap = c;
            if (cap == null && !w.cities.isEmpty()) cap = w.cities.values().iterator().next();
            view.zoom = 24;
            if (cap != null) view.centerOn(cap.x, cap.y);
            screen = Screen.PLAY;
            panel = PanelKind.NONE;
            selCity = 0;
            speed = 1;
            resetPlayState();
            toast("Game loaded", false);
        } catch (Exception e) {
            e.printStackTrace();
            toast("Load failed: " + e.getMessage(), true);
        }
    }

    void drawSavesPanel(Graphics2D g, boolean fromMenu) {
        g.setColor(new Color(0, 0, 0, 140));
        g.fillRect(0, 0, W, H);
        ui.block(0, 0, W, H);
        int w = ui.px(560), h = ui.px(440), x = (W - w) / 2, y = (H - h) / 2;
        ui.panel(x, y, w, h);
        ui.text("Load Game", x + ui.px(20), y + ui.px(36), ui.title, Ui.GOLD);
        File[] files = SaveGame.dir().listFiles((d, n) -> n.endsWith(".sav"));
        ArrayList<SaveGame.Info> infos = new ArrayList<>();
        if (files != null) for (File f : files) {
            SaveGame.Info i = SaveGame.peek(f);
            if (i != null) infos.add(i);
        }
        infos.sort((a, b) -> Long.compare(b.time, a.time));
        int ry = y + ui.px(60);
        if (infos.isEmpty()) ui.text("No saved games yet.", x + ui.px(20), ry + ui.px(24), ui.norm, Ui.DIM);
        for (int i = 0; i < Math.min(7, infos.size()); i++) {
            SaveGame.Info inf = infos.get(i);
            ui.text(inf.nation.isEmpty() ? "Spectator" : inf.nation, x + ui.px(20), ry + ui.px(20), ui.bold, Ui.TEXT);
            ui.text(inf.name + " · Year " + inf.year + " · " + inf.size.label + " · " + new java.text.SimpleDateFormat("MMM d, HH:mm").format(new Date(inf.time)), x + ui.px(20), ry + ui.px(36), ui.small, Ui.DIM);
            ui.button("Load", x + w - ui.px(190), ry + ui.px(6), ui.px(80), ui.px(32), true, true, () -> loadFile(inf.file), null);
            ui.button("Delete", x + w - ui.px(100), ry + ui.px(6), ui.px(80), ui.px(32), false, true, () -> inf.file.delete(), null);
            ry += ui.px(46);
        }
        ui.button("Close", x + w - ui.px(120), y + h - ui.px(50), ui.px(100), ui.px(34), false, true, () -> panel = fromMenu ? PanelKind.NONE : PanelKind.PAUSE, null);
    }

    void drawGameOver(Graphics2D g) {
        if (panel == PanelKind.SAVES) return;
        g.setColor(new Color(0, 0, 0, 150));
        g.fillRect(0, 0, W, H);
        ui.block(0, 0, W, H);
        int w = ui.px(460), h = ui.px(240), x = (W - w) / 2, y = (H - h) / 2;
        ui.panel(x, y, w, h);
        ui.textCenter("Your nation has fallen", x + w / 2, y + ui.px(58), ui.title, Ui.BAD);
        ui.textCenter(me.fullName() + " lasted until year " + world.year() + ".", x + w / 2, y + ui.px(92), ui.norm, Ui.DIM);
        ui.button("Keep Watching", x + ui.px(40), y + ui.px(130), w - ui.px(80), ui.px(42), false, true, () -> {
            me = null;
            world.gameOver = false;
        }, null);
        ui.button("Main Menu", x + ui.px(40), y + ui.px(184), w - ui.px(80), ui.px(42), true, true, () -> toMenu(), null);
    }

    // ================= input =================
    // ---- Android entry points (called from the GL/render thread queue) ----
    public void post(Runnable r) { events.add(r); }
    public void touchDown(int x, int y) { mouseX = x; mouseY = y; events.add(() -> pressed(x, y, 1)); }
    public void touchMove(int x, int y) { mouseX = x; mouseY = y; events.add(() -> dragged(x, y)); }
    public void touchUp(int x, int y, boolean longPress) { events.add(() -> { released(x, y, longPress ? 3 : 1); mouseX = -1; mouseY = -1; }); }
    /** Cancels the current single-finger gesture (a second finger landed). */
    public void touchCancel() { events.add(() -> { mouseDown = false; activeDrag = null; ngDragging = false; pressedMap = false; dragDist = 1e9; mouseX = -1; mouseY = -1; }); }
    public void pinch(float cx, float cy, float factor, float dx, float dy) {
        events.add(() -> {
            if (screen == Screen.NEW) {
                if (ngSize.infinite()) { ngTpp = Math.max(1.5, Math.min(14, ngTpp / factor)); ngCx -= dx * ngTpp; ngCy -= dy * ngTpp; }
                return;
            }
            if (screen != Screen.PLAY || view == null) return;
            if (panel == PanelKind.PAUSE || panel == PanelKind.SAVES) return;
            view.camX -= dx / view.zoom;
            view.camY -= dy / view.zoom;
            view.zoomAt(cx, cy, factor);
            view.clampCamera();
        });
    }
    public void scroll(int x, int y, double rot) { events.add(() -> wheel(x, y, rot)); }
    public void key(int code) { events.add(() -> keyDown(code)); }
    public void type(char c) { events.add(() -> typed(c)); }
    public boolean wantsText() { return screen == Screen.NEW && ngFocus != 0; }

    void pressed(int x, int y, int button) {
        mouseX = x;
        mouseY = y;
        mouseDown = true;
        pressX = lastX = x;
        pressY = lastY = y;
        dragDist = 0;
        pressedMap = false;
        panning = false;
        activeDrag = null;
        Ui.Hit h = ui.hitAt(x, y);
        if (h != null && h.drag != null) {
            activeDrag = h;
            h.drag.accept((double) x);
            return;
        }
        if (h == null || !h.blocksMap) pressedMap = true;
        if (screen == Screen.NEW && ngPreviewRect.contains(x, y)) {
            ngDragging = true;
            pressedMap = true;
        }
        if (screen == Screen.NEW && !ngPreviewRect.contains(x, y)) ngFocus = ngFocus; // keep focus unless a field is clicked
    }

    Rectangle previewDragBase;

    void dragged(int x, int y) {
        if (!mouseDown) return;
        double dx = x - lastX, dy = y - lastY;
        dragDist += Math.abs(dx) + Math.abs(dy);
        lastX = x;
        lastY = y;
        if (activeDrag != null) {
            activeDrag.drag.accept((double) x);
            return;
        }
        if (!pressedMap) return;
        if (screen == Screen.NEW) {
            if (ngSize.infinite() && dragDist > 6) {
                ngCx -= dx * ngTpp;
                ngCy -= dy * ngTpp;
            }
            return;
        }
        if (screen == Screen.PLAY && dragDist > 5) {
            panning = true;
            view.camX -= dx / view.zoom;
            view.camY -= dy / view.zoom;
            view.clampCamera();
        }
    }

    void released(int x, int y, int button) {
        mouseDown = false;
        boolean wasDrag = dragDist > 6;
        activeDrag = null;
        ngDragging = false;
        Ui.Hit h = ui.hitAt(x, y);
        if (!wasDrag && h != null) {
            if (h.click != null) {
                h.click.run();
                return;
            }
        }
        if (!pressedMap || wasDrag) return;
        if (screen == Screen.NEW && ngPreviewRect.contains(x, y)) {
            ngFocus = 0;
            double tpp = ngWorld.bounded ? ngWorld.N / (double) ngPreviewRect.width : ngMap.tpp;
            if (ngMap.img == null) return;
            double wx = ngMap.cx + (x - ngPreviewRect.x - ngMapPx / 2.0) * tpp;
            double wy = ngMap.cy + (y - ngPreviewRect.y - ngMapPx / 2.0) * tpp;
            if (!ngWorld.inBounds((int) wx, (int) wy)) return;
            Sim tmp = new Sim(ngWorld);
            int[] s = tmp.findSiteNear((int) wx, (int) wy, (int) Math.max(6, tpp * 6), 120);
            if (s == null) {
                toast("No suitable land near there", true);
                return;
            }
            ngStartX = s[0];
            ngStartY = s[1];
            ngHasStart = true;
            return;
        }
        if (screen == Screen.PLAY && panel != PanelKind.PAUSE && panel != PanelKind.SAVES) {
            if (button == MouseEvent.BUTTON3) {
                tool = Tool.SELECT;
                return;
            }
            if (mm != null && x >= mmX && y >= mmY && x < mmX + mmSize && y < mmY + mmSize) return;
            mapClick(x, y);
        }
        if (screen == Screen.NEW) ngFocus = 0;
    }

    void mapClick(int x, int y) {
        int tx = view.tileX(x), ty = view.tileY(y);
        if (!hasMe() || tool == Tool.SELECT) {
            City best = null;
            double bd = 2.2;
            for (City c : world.citiesNear(tx, ty, 3)) {
                double d = World.dist(c.x + 0.5, c.y + 0.5, view.wx(x), view.wy(y));
                if (d < bd) {
                    bd = d;
                    best = c;
                }
            }
            selCity = best != null ? best.id : 0;
            if (best != null && panel != PanelKind.NONE && panel != PanelKind.PAUSE) panel = PanelKind.NONE;
            return;
        }
        String err;
        if (tool == Tool.FOUND) {
            err = sim.tryFoundCity(me, tx, ty);
            if (err == null) toast("City founded!", false);
        } else err = sim.tryBuild(me, toolType(tool), tx, ty);
        if (err != null) toast(err, true);
    }

    void wheel(int x, int y, double rot) {
        if (screen == Screen.NEW) {
            if (ngPreviewRect.contains(x, y) && ngSize.infinite()) {
                ngTpp = Math.max(1.5, Math.min(14, ngTpp * Math.pow(1.15, rot)));
            }
            return;
        }
        if (screen == Screen.PLAY) {
            if (panel == PanelKind.DIPLO && ui.overUi(x, y)) {
                diploScroll += rot > 0 ? 1 : -1;
                return;
            }
            if (panel == PanelKind.PAUSE || panel == PanelKind.SAVES) return;
            if (ui.overUi(x, y)) return;
            view.zoomAt(x, y, Math.pow(1.18, -rot));
        }
    }

    void keyDown(int code) {
        if (screen == Screen.NEW) {
            if (code == KeyEvent.VK_ESCAPE) {
                if (ngFocus != 0) ngFocus = 0;
                else screen = Screen.MENU;
            }
            if (code == KeyEvent.VK_ENTER) {
                if (ngFocus == 2) {
                    applySeedText();
                    ngFocus = 0;
                } else if (ngFocus == 1) ngFocus = 0;
                else startGame();
            }
            return;
        }
        if (screen != Screen.PLAY) return;
        switch (code) {
            case KeyEvent.VK_ESCAPE:
                if (panel == PanelKind.SAVES) panel = PanelKind.PAUSE;
                else if (panel != PanelKind.NONE) panel = panel == PanelKind.PAUSE ? PanelKind.NONE : PanelKind.NONE;
                else if (tool != Tool.SELECT) tool = Tool.SELECT;
                else if (selCity != 0) selCity = 0;
                else panel = PanelKind.PAUSE;
                break;
            case KeyEvent.VK_SPACE:
                speed = speed == 0 ? 1 : 0;
                break;
            case KeyEvent.VK_1: speed = 1; break;
            case KeyEvent.VK_2: speed = 2; break;
            case KeyEvent.VK_3: speed = 3; break;
            case KeyEvent.VK_4: speed = 4; break;
            case KeyEvent.VK_G:
                if (hasMe()) panel = panel == PanelKind.POLICY ? PanelKind.NONE : PanelKind.POLICY;
                break;
            case KeyEvent.VK_F:
                panel = panel == PanelKind.DIPLO ? PanelKind.NONE : PanelKind.DIPLO;
                break;
            case KeyEvent.VK_F5:
                quickSave();
                break;
            case KeyEvent.VK_F9: {
                File f = SaveGame.slot("quicksave");
                if (f.exists()) loadFile(f);
                break;
            }
            case KeyEvent.VK_EQUALS:
            case KeyEvent.VK_PLUS:
                view.zoomAt(W / 2.0, H / 2.0, 1.25);
                break;
            case KeyEvent.VK_MINUS:
                view.zoomAt(W / 2.0, H / 2.0, 0.8);
                break;
            default:
                break;
        }
    }

    void applySeedText() {
        try {
            long s = ngSeedText.isEmpty() ? 1 : Long.parseLong(ngSeedText);
            if (s != ngSeed) {
                ngSeed = s;
                newPreview();
            }
        } catch (NumberFormatException e) {
            ngSeedText = String.valueOf(ngSeed);
        }
    }

    void typed(char c) {
        if (screen != Screen.NEW) return;
        if (ngFocus == 1) {
            if (c == '\b') {
                if (!ngName.isEmpty()) ngName = ngName.substring(0, ngName.length() - 1);
            } else if (c >= 32 && c < 127 && ngName.length() < 20) ngName += c;
        } else if (ngFocus == 2) {
            if (c == '\b') {
                if (!ngSeedText.isEmpty()) ngSeedText = ngSeedText.substring(0, ngSeedText.length() - 1);
            } else if (Character.isDigit(c) && ngSeedText.length() < 12) ngSeedText += c;
        }
    }
}
