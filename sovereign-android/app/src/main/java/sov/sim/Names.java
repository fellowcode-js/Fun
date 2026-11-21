package sov.sim;

import java.util.Random;

public final class Names {
    private Names() {}

    private static final String[] A = {"Va", "Ka", "Mor", "Eld", "Tha", "Bra", "Sol", "Dun", "Fen", "Gal", "Hal", "Ir", "Jor", "Lum",
            "Nor", "Os", "Pel", "Quin", "Ral", "Sev", "Tor", "Ul", "Ven", "Wyn", "Yar", "Zan", "Ash", "Bel", "Cor", "Dra", "Eri",
            "Fal", "Gor", "Hel", "Ith", "Kel", "Lor", "Mal", "Nar", "Or", "Pra", "Rho", "Sil", "Tar", "Ur", "Vor", "Xan", "Zer"};
    private static final String[] B = {"a", "e", "i", "o", "u", "an", "en", "in", "on", "ar", "er", "or", "al", "el", "il", "ol", "ad", "ed"};
    private static final String[] NATION_END = {"dor", "ia", "land", "mark", "heim", "vale", "tan", "dia", "ria", "nia", "gard", "mere", "stan", "ica", "ora", "ium"};
    private static final String[] CITY_END = {"ton", "burg", "wick", "ford", "stead", "haven", "port", "mouth", "bridge", "field", "dale", "holm", "grad",
            "polis", "ville", "keep", "crest", "wall", "mere", "gate", "ham", "by", "stad", "ia"};
    private static final String[] PEOPLE_A = {"Alden", "Brea", "Cael", "Dorn", "Eira", "Fenn", "Garr", "Hild", "Isen", "Jora", "Kael", "Lyra", "Marn", "Nyla",
            "Orin", "Pell", "Quor", "Rynn", "Sorn", "Tess", "Ulric", "Vera", "Wulf", "Xena", "Yorick", "Zora"};
    private static final String[] PEOPLE_B = {"Ashford", "Blackwood", "Crane", "Dunmore", "Evermoor", "Frost", "Greyson", "Hawthorne", "Ironside",
            "Kestrel", "Lockwood", "Marlow", "Northcott", "Oakheart", "Pryce", "Ravenscar", "Stormwind", "Thorne", "Underhill", "Valemont", "Wyndham"};
    public static final String[] GOVS = {"Kingdom", "Republic", "Empire", "Duchy", "Federation", "Khanate", "Sultanate", "Confederacy", "Principality", "Union"};

    public static final int[] COLORS = {
            0xd94141, 0x3b82d6, 0x3fae5a, 0xe0b230, 0x9a55c8, 0xe07a30, 0x30b8b0, 0xd9569a, 0x8a6a3c, 0x6fb030,
            0x4a54c8, 0xc8c8d0, 0x1f8a6a, 0xb03a3a, 0x7ab8e8, 0xe8d46a, 0x8a3a9a, 0xe89a6a, 0x5a8a30, 0x3a3a50,
            0xf08080, 0x40c0f0, 0xa0d060, 0xc070e0};

    private static String cap(String s) {
        return Character.toUpperCase(s.charAt(0)) + s.substring(1);
    }

    private static String stem(Random r) {
        String s = A[r.nextInt(A.length)];
        if (r.nextInt(3) == 0) s += B[r.nextInt(B.length)];
        return s;
    }

    public static String nation(Random r) {
        String s = stem(r);
        String e = NATION_END[r.nextInt(NATION_END.length)];
        if (s.length() > 0 && e.length() > 0 && isVowel(s.charAt(s.length() - 1)) && isVowel(e.charAt(0))) e = e.substring(1);
        return cap(s + e);
    }

    public static String city(Random r) {
        String s = stem(r);
        String e = CITY_END[r.nextInt(CITY_END.length)];
        if (isVowel(s.charAt(s.length() - 1)) && isVowel(e.charAt(0))) e = e.substring(1);
        return cap(s + e);
    }

    public static String person(Random r) {
        return PEOPLE_A[r.nextInt(PEOPLE_A.length)] + " " + PEOPLE_B[r.nextInt(PEOPLE_B.length)];
    }

    private static boolean isVowel(char c) {
        return "aeiou".indexOf(Character.toLowerCase(c)) >= 0;
    }

    public static String leaderTitle(String gov) {
        switch (gov) {
            case "Kingdom": return "King";
            case "Republic": return "President";
            case "Empire": return "Emperor";
            case "Duchy": return "Duke";
            case "Federation": return "Chancellor";
            case "Khanate": return "Khan";
            case "Sultanate": return "Sultan";
            case "Confederacy": return "Chairman";
            case "Principality": return "Prince";
            default: return "Premier";
        }
    }
}
