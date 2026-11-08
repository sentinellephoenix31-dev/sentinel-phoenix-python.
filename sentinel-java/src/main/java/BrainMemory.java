import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.function.Consumer;

public final class BrainMemory {
    private static final int MAX_EVENTS = 10_000;
    private static final DateTimeFormatter DISPLAY_TIME =
            DateTimeFormatter.ofPattern("MMM d, uuuu HH:mm:ss z", Locale.ENGLISH);

    private final Path dataDirectory;
    private final ZoneId zone;

    public BrainMemory(Path projectRoot, ZoneId zone) {
        dataDirectory = projectRoot.resolve("data");
        this.zone = zone;
    }

    public String answer(SemanticRouter.Route route) throws IOException {
        ZonedDateTime now = ZonedDateTime.now(zone);
        Window window = timeWindow(route.timeRange(), now);

        if (route.explicitClock() != null) {
            window = applyClock(window, route.explicitClock(), now.toLocalDate());
        }

        if (route.presenceContext() != null) {
            Window presence = presenceWindow(route.presenceContext(), now.toInstant());
            if (presence == null) {
                return "I don't have a recorded owner departure for that request.";
            }
            window = window.intersect(presence);
        }

        if ("SOURCE_LOOKUP".equals(route.intent())
                && route.sourceIp() != null
                && !route.timeExplicit()
                && route.explicitClock() == null
                && route.presenceContext() == null) {
            return describeSource(route.sourceIp(), sourceHistory(route.sourceIp(), now.toInstant()));
        }

        Summary summary = summarize(window, route.sourceIp());

        return switch (route.intent()) {
            case "SOURCE_LOOKUP" -> describeSource(route.sourceIp(), summary.sourceStats());
            case "MOST_DANGEROUS" -> describeHighestRisk(summary.highest);
            case "CONTAINMENT_SUMMARY" -> "I recorded "
                    + counted(summary.containments, "containment decision") + " in that period.";
            default -> describeSummary(summary);
        };
    }

    private Window timeWindow(String range, ZonedDateTime now) {
        LocalDate day = now.toLocalDate();
        Instant current = now.toInstant();

        return switch (range) {
            case "ALL_TIME" -> new Window(null, current);
            case "YESTERDAY" -> new Window(at(day.minusDays(1), 0), at(day, 0));
            case "LAST_NIGHT" -> new Window(at(day.minusDays(1), 18), earlier(current, at(day, 6)));
            case "THIS_MORNING" -> new Window(at(day, 6), earlier(current, at(day, 12)));
            case "THIS_AFTERNOON" -> new Window(at(day, 12), earlier(current, at(day, 18)));
            case "THIS_EVENING" -> new Window(at(day, 18), current);
            case "LAST_24_HOURS" -> new Window(current.minus(Duration.ofHours(24)), current);
            case "LAST_7_DAYS" -> new Window(now.minusDays(7).toInstant(), current);
            case "THIS_WEEK" -> new Window(
                    at(day.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY)), 0), current);
            case "THIS_WEEKEND" -> new Window(
                    at(day.with(TemporalAdjusters.previousOrSame(DayOfWeek.SATURDAY)), 0), current);
            default -> new Window(at(day, 0), current);
        };
    }

    private Instant at(LocalDate day, int hour) {
        return day.atTime(hour, 0).atZone(zone).toInstant();
    }

    private Window applyClock(Window base, SemanticRouter.ClockWindow clock, LocalDate today) {
        LocalDate day = base.start() == null ? today : base.start().atZone(zone).toLocalDate();
        LocalTime start = LocalTime.parse(clock.start());
        LocalTime end = LocalTime.parse(clock.end());
        LocalDate endDay = end.isBefore(start) ? day.plusDays(1) : day;

        return base.intersect(new Window(
                day.atTime(start).atZone(zone).toInstant(),
                endDay.atTime(end).atZone(zone).toInstant()
        ));
    }

    private Window presenceWindow(String context, Instant now) throws IOException {
        Deque<Presence> events = new ArrayDeque<>();
        readJsonLines(dataDirectory.resolve("presence_events.jsonl"), json -> {
            Instant timestamp = timestamp(first(json.get("timestamp"), json.get("created_at")));
            String type = text(first(json.get("event"), json.get("type")), "")
                    .toUpperCase(Locale.ROOT);

            if (timestamp != null && !timestamp.isAfter(now) && !type.isBlank()) {
                events.addLast(new Presence(timestamp, type));
            }
        });

        Instant departure = null;
        for (Presence event : events) {
            if ("OWNER_LEFT".equals(event.type())
                    && (departure == null || event.time().isAfter(departure))) {
                departure = event.time();
            }
        }
        if (departure == null) {
            return null;
        }

        Instant end = now;
        if ("OWNER_ABSENCE".equals(context)) {
            for (Presence event : events) {
                if (event.time().isAfter(departure)
                        && ("OWNER_RETURNED".equals(event.type())
                            || "OWNER_PRESENT".equals(event.type()))) {
                    end = earlier(end, event.time());
                }
            }
        }
        return new Window(departure, end);
    }

    private Summary summarize(Window window, String sourceIp) throws IOException {
        Deque<JsonObject> events = new ArrayDeque<>();

        readJsonLines(dataDirectory.resolve("events.jsonl"), json -> {
            events.addLast(json);
            if (events.size() > MAX_EVENTS) {
                events.removeFirst();
            }
        });

        Summary summary = new Summary();
        for (JsonObject json : events) {
            Incident event = normalize(json);
            if (event.time() != null && window.contains(event.time())
                    && (sourceIp == null || sourceIp.equals(event.sourceIp()))) {
                summary.add(event);
            }
        }
        return summary;
    }

    private SourceStats sourceHistory(String sourceIp, Instant now) throws IOException {
        Path database = dataDirectory.resolve("phoenix_memory.db")
                .toAbsolutePath().normalize();

        if (Files.isRegularFile(database)) {
            String url = "jdbc:sqlite:" + database.toUri() + "?mode=ro";
            try (var connection = DriverManager.getConnection(url);
                 var statement = connection.prepareStatement("""
                         SELECT total_events, critical_events, containment_events, max_global_score
                         FROM source_profiles
                         WHERE source_ip = ?
                         """)) {
                statement.setString(1, sourceIp);
                try (var row = statement.executeQuery()) {
                    if (row.next()) {
                        return new SourceStats(
                                row.getLong(1), row.getLong(2), row.getLong(3), row.getDouble(4)
                        );
                    }
                }
            } catch (SQLException error) {
                System.err.println("[BRAIN MEMORY] Source database unavailable. Using the event log.");
            }
        }

        return summarize(new Window(null, now), sourceIp).sourceStats();
    }

    private static Incident normalize(JsonObject json) {
        JsonObject fusion = object(json.get("fusion"));
        JsonObject response = object(json.get("response"));
        JsonObject deception = object(json.get("deception"));

        String action = text(first(json.get("response_action"), response.get("action")), "");
        boolean containment = flag(first(json.get("containment_requested"),
                response.get("containment_requested")))
                || action.toUpperCase(Locale.ROOT).contains("CONTAIN");

        return new Incident(
                timestamp(first(json.get("timestamp"), json.get("created_at"))),
                text(first(json.get("source_ip"), json.get("ip")), "UNKNOWN"),
                number(first(json.get("global_score"), fusion.get("global_score"))),
                text(first(json.get("global_level"), fusion.get("global_level")), "LOW")
                        .toUpperCase(Locale.ROOT),
                containment,
                flag(first(json.get("decoy_active"), deception.get("decoy_active"))),
                flag(first(json.get("surface_rotated"), deception.get("surface_rotated")))
        );
    }

    private static void readJsonLines(Path path, Consumer<JsonObject> handler) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }

                JsonElement value;
                try {
                    value = JsonParser.parseString(line);
                } catch (JsonParseException error) {
                    continue;
                }

                if (value.isJsonObject()) {
                    handler.accept(value.getAsJsonObject());
                }
            }
        } catch (NoSuchFileException ignored) {
            // The journal is created when its first event is recorded.
        }
    }

    private static Instant timestamp(JsonElement value) {
        if (value == null || !value.isJsonPrimitive()) {
            return null;
        }

        try {
            if (value.getAsJsonPrimitive().isNumber()) {
                double seconds = value.getAsDouble();
                if (!Double.isFinite(seconds)) {
                    return null;
                }
                long whole = (long) Math.floor(seconds);
                return Instant.ofEpochSecond(whole, Math.round((seconds - whole) * 1_000_000_000));
            }

            String input = value.getAsString().strip().replace(' ', 'T');
            try {
                return OffsetDateTime.parse(input).toInstant();
            } catch (java.time.format.DateTimeParseException error) {
                return LocalDateTime.parse(input).toInstant(ZoneOffset.UTC);
            }
        } catch (java.time.DateTimeException | NumberFormatException error) {
            return null;
        }
    }

    private static String describeSource(String sourceIp, SourceStats stats) {
        return "Source " + sourceIp + " has " + counted(stats.total(), "recorded event")
                + ", including " + counted(stats.critical(), "critical event") + ". "
                + "I recorded " + counted(stats.containments(), "containment decision")
                + ". The maximum risk was " + score(stats.maximum()) + "/100.";
    }

    private String describeHighestRisk(Incident event) {
        if (event == null) {
            return "I found no security events in that period.";
        }
        return "The highest-risk event came from " + event.sourceIp() + " at "
                + DISPLAY_TIME.format(event.time().atZone(zone)) + ". Its global risk was "
                + event.level() + " at " + score(event.score()) + "/100.";
    }

    private static String describeSummary(Summary summary) {
        if (summary.total == 0) {
            return "I found no security events in that period.";
        }

        String result = "I found " + counted(summary.total, "security event") + " from "
                + counted(summary.sources.size(), "source") + ". "
                + "High or critical risk: " + summary.highRisk
                + ", including " + summary.critical + " critical. "
                + "Maximum risk: " + score(summary.highest.score()) + "/100. "
                + "I recorded " + counted(summary.containments, "containment decision")
                + " and " + counted(summary.decoys, "decoy interaction") + ".";

        if (summary.rotations > 0) {
            result += " The decoy surface rotated " + counted(summary.rotations, "time") + ".";
        }
        return result;
    }

    private static JsonElement first(JsonElement primary, JsonElement fallback) {
        return primary == null || primary.isJsonNull() ? fallback : primary;
    }

    private static JsonObject object(JsonElement value) {
        return value instanceof JsonObject json ? json : new JsonObject();
    }

    private static String text(JsonElement value, String fallback) {
        return value != null && value.isJsonPrimitive() ? value.getAsString() : fallback;
    }

    private static boolean flag(JsonElement value) {
        return value != null && value.isJsonPrimitive() && value.getAsBoolean();
    }

    private static double number(JsonElement value) {
        try {
            double parsed = Double.parseDouble(text(value, "0"));
            return Double.isFinite(parsed) ? parsed : 0;
        } catch (NumberFormatException error) {
            return 0;
        }
    }

    private static String score(double value) {
        return String.format(Locale.ENGLISH, "%.2f", value);
    }

    private static String counted(long count, String singular) {
        return count + " " + singular + (count == 1 ? "" : "s");
    }

    private static Instant earlier(Instant first, Instant second) {
        return first.isBefore(second) ? first : second;
    }

    private record Window(Instant start, Instant end) {
        boolean contains(Instant time) {
            return (start == null || !time.isBefore(start)) && time.isBefore(end);
        }

        Window intersect(Window other) {
            Instant latestStart = start;
            if (latestStart == null
                    || (other.start != null && other.start.isAfter(latestStart))) {
                latestStart = other.start;
            }
            return new Window(latestStart, earlier(end, other.end));
        }
    }

    private record Presence(Instant time, String type) {
    }

    private record Incident(
            Instant time, String sourceIp, double score, String level,
            boolean containment, boolean decoy, boolean rotated
    ) {
    }

    private record SourceStats(long total, long critical, long containments, double maximum) {
    }

    private static final class Summary {
        private final Set<String> sources = new HashSet<>();
        private int total;
        private int highRisk;
        private int critical;
        private int containments;
        private int decoys;
        private int rotations;
        private Incident highest;

        void add(Incident event) {
            total++;
            sources.add(event.sourceIp());

            boolean isCritical = event.score() >= 80 || "CRITICAL".equals(event.level());
            if (isCritical || event.score() >= 60 || "HIGH".equals(event.level())) {
                highRisk++;
            }
            if (isCritical) {
                critical++;
            }
            if (event.containment()) {
                containments++;
            }
            if (event.decoy()) {
                decoys++;
            }
            if (event.rotated()) {
                rotations++;
            }
            if (highest == null || event.score() > highest.score()) {
                highest = event;
            }
        }

        SourceStats sourceStats() {
            return new SourceStats(total, critical, containments,
                    highest == null ? 0 : highest.score());
        }
    }

    public static void main(String[] args) throws IOException {
        String question = args.length == 0 ? "What happened today?" : String.join(" ", args);
        BrainMemory memory = new BrainMemory(Path.of("."), ZoneId.of("Asia/Kolkata"));
        System.out.println("SENTINEL > " + memory.answer(SemanticRouter.routeQuestion(question)));
    }
}