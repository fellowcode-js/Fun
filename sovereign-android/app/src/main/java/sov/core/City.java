package sov.core;

import java.util.ArrayList;

public final class City {
    public int id, nation, x, y;
    public String name;
    public double pop = 60;
    public int level = 1;
    public boolean capital;
    public double food = 1, happiness = 70, buildPoints, garrison;
    public int founded;
    public int unrest;
    public int houses, farms, lumbers, mines, docks, towers;
    public double farmYield, lumberYield;
    public boolean coastal;
    /** Built tiles: x, y, type. */
    public final ArrayList<int[]> blds = new ArrayList<>();

    public static final String[] LEVEL_NAMES = {"", "Hamlet", "Village", "Town", "City", "Metropolis"};
    public static final int[] LEVEL_POP = {0, 0, 150, 600, 2000, 6000};

    public String levelName() {
        return LEVEL_NAMES[level];
    }

    public int claimRadius() {
        return 7 + level * 3 + (capital ? 3 : 0);
    }

    public double claimFactor() {
        return 1 + level * 0.12 + (capital ? 0.25 : 0);
    }

    public int buildRadius() {
        return 3 + level * 2;
    }

    public void updateLevel() {
        int l = 1;
        for (int i = 2; i <= 5; i++) if (pop >= LEVEL_POP[i]) l = i;
        level = l;
    }

    public double housingCap() {
        return 80 + houses * 30 + level * 70 + (capital ? 120 : 0);
    }
}
