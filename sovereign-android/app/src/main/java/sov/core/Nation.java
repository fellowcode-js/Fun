package sov.core;

import java.util.HashMap;
import java.util.HashSet;

public final class Nation {
    public static final String[] ERAS = {"Tribal", "Bronze", "Iron", "Medieval", "Gunpowder", "Industrial"};
    public static final double[] ERA_COST = {0, 150, 700, 2500, 9000, 30000};

    public int id;
    public String name, gov, leader;
    public int color;
    public boolean player, alive = true;
    /** Personality, 0..1. */
    public double aggression, expansion, builder, diplomat, trader;
    public double gold = 160, wood = 120, stone = 40, science;
    public int era;
    /** Policies, 0..1. */
    public double tax = 0.5, military = 0.3, sciencePolicy = 0.4;
    /** 0 balanced, 1 agriculture, 2 industry, 3 trade. */
    public int focus;
    public double soldiers = 10;
    public int founded;
    public int startX, startY;
    public int roofStyle;

    // Derived each turn
    public double pop, income, foodBalance;
    public int cityCount;
    public double power;
    public int droughtUntil, boomUntil;
    public final HashSet<Integer> neighbors = new HashSet<>();
    public final HashMap<Integer, Relation> rel = new HashMap<>();
    public final java.util.ArrayDeque<int[]> roadQueue = new java.util.ArrayDeque<>();
    public int lastCityTurn;
    public boolean autoExpand;

    public String eraName() {
        return ERAS[era];
    }

    public String fullName() {
        return gov + " of " + name;
    }

    public double techMult() {
        return 1 + era * 0.25;
    }

    public double warMult() {
        return 1 + era * 0.4;
    }

    public static final class Relation {
        public static final int PEACE = 0, WAR = 1, ALLY = 2;
        public int a, b;
        public double opinion;
        public int state;
        public int since, truceUntil;

        public Relation(int a, int b) {
            this.a = a;
            this.b = b;
        }
    }
}
