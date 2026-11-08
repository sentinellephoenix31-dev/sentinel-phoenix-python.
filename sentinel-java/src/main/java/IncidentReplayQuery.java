import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class IncidentReplayQuery {

    private static final int MAX_EVENTS = 3000;
    private static final int DISPLAY_LIMIT = 120;
    private static final int LATEST_LIMIT = 100;

    private static final Gson JSON = new GsonBuilder()
            .serializeNulls()
            .setPrettyPrinting()
            .create();

    private static final String MONTHS =
            "january|february|march|april|may|june|july"
                    + "|august|september|october|november|december";

    private static final Pattern ISO_DATE = Pattern.compile(
            "\\b(\\d{4})-(\\d{2})-(\\d{2})\\b");

    private static final Pattern MONTH_DATE = Pattern.compile(
            "\\b(" + MONTHS + ")\\s+(\\d{1,2})"
                    + "(?:st|nd|rd|th)?"
                    + "(?:\\s*,?\\s+(\\d{4}))?\\b");

    private static final Pattern DAY_MONTH_DATE = Pattern.compile(
            "\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+("
                    + MONTHS + ")"
                    + "(?:\\s*,?\\s+(\\d{4}))?\\b");

    private static final String CLOCK =
            "(\\d{1,2})(?::(\\d{2}))?\\s*(am|pm)?";

    private static final Pattern BETWEEN = Pattern.compile(
            "\\bbetween\\s+" + CLOCK
                    + "\\s+(?:and|to)\\s+" + CLOCK + "\\b");

    private static final Pattern AFTER = Pattern.compile(
            "\\b(?:after|since)\\s+" + CLOCK + "\\b");

    private static final Pattern BEFORE = Pattern.compile(
            "\\b(?:before|until)\\s+" + CLOCK + "\\b");

    private final Path eventsFile;
    private final ZoneId zone;

    public IncidentReplayQuery(Path root, ZoneId zone) {
        this.eventsFile = root.resolve("data/events.jsonl");
        this.zone = Objects.requireNonNull(zone);
    }

    private record RecordedEvent(JsonObject event, Instant timestamp) {
    }

    private record Window(Instant start, Instant end) {
        boolean contains(Instant timestamp) {
            return (start == null || !timestamp.isBefore(start))
                    && timestamp.isBefore(end);
        }
    }

    private record Selection(String period, Window window) {
    }

    public JsonObject replayPayloadForQuery(String query)
            throws IOException {

        String question = query == null ? "" : query.strip();

        SemanticRouter.Route semantic =
                SemanticRouter.routeQuestion(question);

        if (semantic.presenceContext() != null) {
            throw new IllegalArgumentException(
                    "Presence-based replay is unavailable. "
                            + "Please specify a date or period.");
        }

        Instant now = Instant.now();

        Selection selection = resolveWindow(
                question, semantic, now);

        List<RecordedEvent> loaded = readEvents();
        List<RecordedEvent> matched = new ArrayList<>();

        for (RecordedEvent event : loaded) {
            if (selection.window().contains(event.timestamp())) {
                matched.add(event);
            }
        }

        matched.sort(
                Comparator.comparing(
                        RecordedEvent::timestamp).reversed());

        if ("LATEST".equals(selection.period())
                && matched.size() > LATEST_LIMIT) {
            matched = new ArrayList<>(
                    matched.subList(0, LATEST_LIMIT));
        }

        int matchingCount = matched.size();

        boolean mostDangerous =
                "MOST_DANGEROUS".equals(semantic.intent());

        if (mostDangerous && !matched.isEmpty()) {
            matched.sort(
                    Comparator.comparingDouble(
                                    (RecordedEvent event) ->
                                            severity(event.event()))
                            .thenComparing(RecordedEvent::timestamp)
                            .reversed());

            matched = new ArrayList<>(matched.subList(0, 1));
        }

        if (matched.size() > DISPLAY_LIMIT) {
            matched = new ArrayList<>(
                    matched.subList(0, DISPLAY_LIMIT));
        }

        JsonArray rawEvents = new JsonArray();
        JsonArray globeEvents = new JsonArray();

        for (int i = 0; i < matched.size(); i++) {
            RecordedEvent selected = matched.get(i);
            JsonObject event = selected.event().deepCopy();

            event.addProperty(
                    "timestamp", selected.timestamp().toString());

            rawEvents.add(event);
            globeEvents.add(
                    JSON.toJsonTree(GlobeEvent.from(event, i + 1)));
        }

        Window window = selection.window();

        JsonObject windowJson = new JsonObject();
        windowJson.addProperty(
                "start",
                window.start() == null
                        ? null : window.start().toString());
        windowJson.addProperty("end", window.end().toString());

        JsonObject result = new JsonObject();

        result.addProperty("status", "READY");
        result.addProperty("version", "1.1");
        result.addProperty("query", question);
        result.addProperty("period", selection.period());
        result.addProperty(
                "selection",
                mostDangerous ? "MOST_DANGEROUS" : "ALL");
        result.addProperty("generated_at", now.toString());
        result.addProperty("timezone", zone.getId());
        result.addProperty("source_file", "data/events.jsonl");
        result.addProperty(
                "source_file_exists", Files.isRegularFile(eventsFile));
        result.addProperty("retained_events", loaded.size());
        result.addProperty("retention_limit", MAX_EVENTS);
        result.addProperty("matched_events", matchingCount);
        result.addProperty("event_count", matched.size());
        result.addProperty(
                "display_truncated",
                !mostDangerous && matchingCount > matched.size());

        result.add("window", windowJson);
        result.add("incidents", rawEvents);
        result.add("events", globeEvents);

        return result;
    }

    private Selection resolveWindow(
            String question,
            SemanticRouter.Route semantic,
            Instant instant) {

        String text = question.toLowerCase(Locale.ROOT)
                .replaceAll("\\s+", " ")
                .trim();

        LocalDate explicitDate =
                extractDate(text, instant.atZone(zone).getYear());

        String period = explicitDate != null
                ? "DATE:" + explicitDate
                : semantic.timeExplicit()
                    ? semantic.timeRange() : "LATEST";

        Window base = explicitDate != null
                ? dayWindow(explicitDate, instant)
                : periodWindow(period, instant);

        Matcher between = BETWEEN.matcher(text);
        Matcher after = AFTER.matcher(text);
        Matcher before = BEFORE.matcher(text);

        boolean hasBetween = between.find();
        boolean hasAfter = after.find();
        boolean hasBefore = before.find();

        if (hasBetween && (hasAfter || hasBefore)) {
            throw new IllegalArgumentException(
                    "Use either between two times, "
                            + "or after/before a time.");
        }

        LocalTime startTime = null;
        LocalTime endTime = null;

        if (hasBetween) {
            startTime = parseClock(
                    between.group(1), between.group(2),
                    between.group(3));

            endTime = parseClock(
                    between.group(4), between.group(5),
                    between.group(6));

        } else {
            if (hasAfter) {
                startTime = parseClock(
                        after.group(1), after.group(2),
                        after.group(3));
            }

            if (hasBefore) {
                endTime = parseClock(
                        before.group(1), before.group(2),
                        before.group(3));
            }
        }

        // Preserve the existing French "entre 14h et 17h" support.
        if (!hasBetween && !hasAfter && !hasBefore
                && semantic.explicitClock() != null) {

            startTime = LocalTime.parse(
                    semantic.explicitClock().start());

            endTime = LocalTime.parse(
                    semantic.explicitClock().end());
        }

        boolean clockRequested =
                startTime != null || endTime != null;

        boolean clockWords = Pattern.compile(
                "\\b(after|before|until|between)\\b")
                .matcher(text).find();

        if (clockWords && !clockRequested) {
            throw new IllegalArgumentException(
                    "Specify a numeric time, such as after 3 PM.");
        }

        if (!clockRequested) {
            // Avoid silently interpreting unsupported dates as LATEST.
            boolean unresolvedDate = explicitDate == null
                    && (Pattern.compile(
                            "\\b(?:on|le)\\s+\\d")
                            .matcher(text).find()
                        || Pattern.compile(
                            "\\b\\d{1,2}/\\d{1,2}")
                            .matcher(text).find()
                        || Pattern.compile(
                            "\\b(?:" + MONTHS + ")\\b")
                            .matcher(text).find());

            if (unresolvedDate) {
                throw new IllegalArgumentException(
                        "Use a date such as November 5, 2026 "
                                + "or 2026-11-05.");
            }

            return new Selection(period, base);
        }

        LocalDate date;

        if (explicitDate != null) {
            date = explicitDate;

        } else if ("YESTERDAY".equals(period)) {
            date = instant.atZone(zone).toLocalDate().minusDays(1);

        } else if ("TODAY".equals(period)
                || "LATEST".equals(period)) {

            date = instant.atZone(zone).toLocalDate();

        } else {
            throw new IllegalArgumentException(
                    "For clock filtering, specify today, yesterday "
                            + "or an exact date.");
        }

        if (startTime != null && endTime != null
                && !endTime.isAfter(startTime)) {
            throw new IllegalArgumentException(
                    "The ending time must be after the starting time. "
                            + "Overnight clock ranges are not supported yet.");
        }

        Instant start = startTime == null
                ? date.atStartOfDay(zone).toInstant()
                : date.atTime(startTime).atZone(zone).toInstant();

        Instant end = endTime == null
                ? date.plusDays(1).atStartOfDay(zone).toInstant()
                : date.atTime(endTime).atZone(zone).toInstant();

        end = earlier(end, instant);

        return new Selection(
                "DATE:" + date + ":CLOCK",
                new Window(start, end));
    }

    private static LocalTime parseClock(
            String hourText,
            String minuteText,
            String meridiem) {

        int hour = Integer.parseInt(hourText);
        int minute = minuteText == null
                ? 0 : Integer.parseInt(minuteText);

        if (meridiem != null) {
            if (hour < 1 || hour > 12) {
                throw new IllegalArgumentException(
                        "AM/PM hours must be between 1 and 12.");
            }

            hour = hour % 12;
            if ("pm".equals(meridiem)) {
                hour += 12;
            }

        } else if (minuteText == null && hour >= 1 && hour <= 12) {
            throw new IllegalArgumentException(
                    "Specify AM or PM, for example 3 PM, "
                            + "or use 24-hour time such as 15:00.");
        }

        try {
            return LocalTime.of(hour, minute);
        } catch (DateTimeException error) {
            throw new IllegalArgumentException(
                    "Invalid clock time.", error);
        }
    }

    private static LocalDate extractDate(String text, int year) {
        Matcher iso = ISO_DATE.matcher(text);

        if (iso.find()) {
            return validDate(
                    Integer.parseInt(iso.group(1)),
                    Integer.parseInt(iso.group(2)),
                    Integer.parseInt(iso.group(3)));
        }

        Matcher monthFirst = MONTH_DATE.matcher(text);

        if (monthFirst.find()) {
            return validDate(
                    monthFirst.group(3) == null
                            ? year
                            : Integer.parseInt(monthFirst.group(3)),
                    monthNumber(monthFirst.group(1)),
                    Integer.parseInt(monthFirst.group(2)));
        }

        Matcher dayFirst = DAY_MONTH_DATE.matcher(text);

        if (dayFirst.find()) {
            return validDate(
                    dayFirst.group(3) == null
                            ? year
                            : Integer.parseInt(dayFirst.group(3)),
                    monthNumber(dayFirst.group(2)),
                    Integer.parseInt(dayFirst.group(1)));
        }

        return null;
    }

    private static int monthNumber(String name) {
        return List.of(MONTHS.split("\\|")).indexOf(name) + 1;
    }

    private static LocalDate validDate(int year, int month, int day) {
        try {
            return LocalDate.of(year, month, day);
        } catch (DateTimeException error) {
            throw new IllegalArgumentException(
                    "Invalid calendar date.", error);
        }
    }

    private Window dayWindow(LocalDate date, Instant now) {
        return new Window(
                date.atStartOfDay(zone).toInstant(),
                earlier(
                        date.plusDays(1).atStartOfDay(zone).toInstant(),
                        now));
    }

    private Window periodWindow(String period, Instant instant) {
        ZonedDateTime now = instant.atZone(zone);
        ZonedDateTime today =
                now.toLocalDate().atStartOfDay(zone);

        ZonedDateTime start;
        ZonedDateTime end = now;

        switch (period) {
            case "LATEST", "ALL_TIME" -> {
                return new Window(null, instant);
            }
            case "YESTERDAY" -> {
                start = today.minusDays(1);
                end = today;
            }
            case "LAST_NIGHT" -> {
                start = today.minusDays(1).withHour(18);
                end = now.isBefore(today.withHour(6))
                        ? now : today.withHour(6);
            }
            case "THIS_MORNING" -> {
                start = today.withHour(6);
                end = now.isBefore(today.withHour(12))
                        ? now : today.withHour(12);
            }
            case "THIS_AFTERNOON" -> {
                start = today.withHour(12);
                end = now.isBefore(today.withHour(18))
                        ? now : today.withHour(18);
            }
            case "THIS_EVENING" -> start = today.withHour(18);
            case "LAST_24_HOURS" -> {
                return new Window(
                        instant.minus(Duration.ofHours(24)), instant);
            }
            case "LAST_7_DAYS" -> {
                return new Window(
                        instant.minus(Duration.ofDays(7)), instant);
            }
            case "THIS_WEEK" -> start = today.with(
                    TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));

            case "THIS_WEEKEND" -> start = today.with(
                    TemporalAdjusters.previousOrSame(DayOfWeek.SATURDAY));

            default -> start = today;
        }

        return new Window(start.toInstant(), end.toInstant());
    }

    private static Instant earlier(Instant first, Instant second) {
        return first.isBefore(second) ? first : second;
    }

    private List<RecordedEvent> readEvents() throws IOException {
        PriorityQueue<RecordedEvent> newest = new PriorityQueue<>(
                Comparator.comparing(RecordedEvent::timestamp));

        if (!Files.exists(eventsFile)) {
            return new ArrayList<>();
        }

        try (BufferedReader reader = Files.newBufferedReader(
                eventsFile, StandardCharsets.UTF_8)) {

            String line;

            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }

                JsonObject event;

                try {
                    JsonElement parsed = JsonParser.parseString(line);

                    if (!parsed.isJsonObject()) {
                        continue;
                    }

                    event = parsed.getAsJsonObject();

                } catch (RuntimeException malformed) {
                    continue;
                }

                if (!isCyberEvent(event)) {
                    continue;
                }

                Instant timestamp = timestamp(event, zone);

                if (timestamp == null) {
                    continue;
                }

                newest.add(new RecordedEvent(event, timestamp));

                if (newest.size() > MAX_EVENTS) {
                    newest.poll();
                }
            }
        }

        return new ArrayList<>(newest);
    }

    private static boolean isCyberEvent(JsonObject event) {
        String type = text(event, "type");

        if (type.isEmpty()) {
            type = text(event, "event");
        }

        String upper = type.toUpperCase(Locale.ROOT);

        if (upper.startsWith("OWNER_")
                || upper.startsWith("GUEST_")
                || upper.startsWith("FACE_")
                || upper.contains("IDENTITY")
                || upper.contains("LIVENESS")
                || upper.contains("UNKNOWN_PERSON")) {
            return false;
        }

        return "HONEYPOT_EVENT".equals(upper)
                || !text(event, "source_ip").isEmpty()
                || !text(event, "remote_ip").isEmpty()
                || !text(event, "ip").isEmpty();
    }

    private static Instant timestamp(JsonObject event, ZoneId zone) {
        for (String key : List.of(
                "timestamp", "timestamp_iso", "time", "datetime",
                "created_at", "detected_at", "event_time",
                "occurred_at", "date")) {

            String value = text(event, key);

            if (value.isEmpty()) {
                continue;
            }

            try {
                double numeric = Double.parseDouble(value);

                if (!Double.isFinite(numeric)) {
                    continue;
                }

                double seconds = Math.abs(numeric) > 100_000_000_000L
                        ? numeric / 1000.0 : numeric;

                long whole = (long) Math.floor(seconds);
                long nanos = (long) (
                        (seconds - whole) * 1_000_000_000);

                return Instant.ofEpochSecond(whole, nanos);

            } catch (RuntimeException ignored) {
            }

            try {
                return Instant.parse(value);
            } catch (RuntimeException ignored) {
            }

            String iso = value.replace(' ', 'T');

            try {
                return OffsetDateTime.parse(iso).toInstant();
            } catch (RuntimeException ignored) {
            }

            try {
                return LocalDateTime.parse(iso)
                        .atZone(zone).toInstant();
            } catch (RuntimeException ignored) {
            }
        }

        return null;
    }

    private static double severity(JsonObject event) {
        for (String key : List.of(
                "global_score", "risk_score", "score", "threat_score")) {
            try {
                double value = Double.parseDouble(text(event, key));

                if (Double.isFinite(value)) {
                    return value;
                }
            } catch (NumberFormatException ignored) {
            }
        }

        String level = text(event, "global_level");

        if (level.isEmpty()) {
            level = text(event, "severity");
        }

        return switch (level.toUpperCase(Locale.ROOT)) {
            case "CRITICAL" -> 100;
            case "HIGH", "SEVERE" -> 80;
            case "MEDIUM", "MODERATE" -> 50;
            case "LOW" -> 20;
            case "INFO" -> 5;
            default -> 0;
        };
    }

    private static String text(JsonObject object, String key) {
        JsonElement value = object.get(key);

        return value != null && value.isJsonPrimitive()
                ? value.getAsString().strip() : "";
    }

    public static void main(String[] args) throws IOException {
        String query = args.length == 0
                ? "latest" : String.join(" ", args);

        IncidentReplayQuery engine = new IncidentReplayQuery(
                Path.of("."), ZoneId.of("Asia/Kolkata"));

        System.out.println(
                JSON.toJson(engine.replayPayloadForQuery(query)));
    }
}