import java.util.List;
import java.util.Locale;

/** Storyboard selection, not a new threat detector. */
public final class SceneCatalog {
    public enum Kind {
        CONNECTION_TEST("Termux / test connection"),
        PORT_SCAN("Port scanning"),
        BRUTE_FORCE("Repeated login attempts"),
        SQL_INJECTION("SQL injection"),
        XSS("Cross-site scripting"),
        COMMAND_INJECTION("Command injection"),
        PATH_TRAVERSAL("Path traversal"),
        CONNECTION_FLOOD("Connection saturation"),
        TROJAN("Trojan mechanism"),
        RANSOMWARE("Ransomware mechanism"),
        UNKNOWN("Recorded connection / unclassified");
        private final String title;
        Kind(String title) { this.title = title; }
        public String title() { return title; }
        @Override public String toString() { return title; }
    }
    private SceneCatalog() {}
    public static Kind detect(String payload, String attackType, String behaviorType,
                              List<String> indicators) {
        Kind explicit = explicitLabel(attackType);
        if (explicit != Kind.UNKNOWN) return explicit;
        explicit = explicitLabel(behaviorType);
        if (explicit != Kind.UNKNOWN) return explicit;
        Kind selected = Kind.UNKNOWN;
        if (indicators != null) for (String indicator : indicators) {
            Kind candidate = explicitLabel(indicator);
            if (candidate != Kind.UNKNOWN) {
                if (selected != Kind.UNKNOWN && selected != candidate) return Kind.UNKNOWN;
                selected = candidate;
            }
        }
        if (selected == Kind.UNKNOWN
                && "SENTINEL_DEMO_TEST".equals(payload == null ? "" : payload.strip())) {
            return Kind.CONNECTION_TEST;
        }
        return selected;
    }
    private static Kind explicitLabel(String label) {
        String value = label == null ? "" : label.strip().toUpperCase(Locale.ROOT)
                .replace('-', '_').replace(' ', '_');
        return switch (value) {
            case "PORT_SCAN", "PORT_SCANNING" -> Kind.PORT_SCAN;
            case "BRUTE_FORCE", "LOGIN_BRUTE_FORCE" -> Kind.BRUTE_FORCE;
            case "SQL_INJECTION", "SQLI" -> Kind.SQL_INJECTION;
            case "XSS", "CROSS_SITE_SCRIPTING" -> Kind.XSS;
            case "COMMAND_INJECTION", "OS_COMMAND_INJECTION" -> Kind.COMMAND_INJECTION;
            case "PATH_TRAVERSAL", "DIRECTORY_TRAVERSAL" -> Kind.PATH_TRAVERSAL;
            case "CONNECTION_FLOOD", "DOS", "DDOS" -> Kind.CONNECTION_FLOOD;
            case "TROJAN" -> Kind.TROJAN;
            case "RANSOMWARE" -> Kind.RANSOMWARE;
            default -> Kind.UNKNOWN;
        };
    }
}
