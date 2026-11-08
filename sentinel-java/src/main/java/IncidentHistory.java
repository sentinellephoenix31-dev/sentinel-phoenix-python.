import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public final class IncidentHistory {
    private static final DateTimeFormatter ENGLISH_DATE =
            DateTimeFormatter.ofPattern("MMMM d, uuuu", Locale.ENGLISH);

    private final Path eventFile;
    private final ZoneId zone;

    public IncidentHistory(Path projectRoot, ZoneId zone) {
        this.eventFile = projectRoot.resolve("data").resolve("events.jsonl");
        this.zone = zone;
    }

    public String summarizeYesterday() throws IOException {
        LocalDate today = LocalDate.now(zone);
        LocalDate yesterday = today.minusDays(1);

        Instant start = yesterday.atStartOfDay(zone).toInstant();
        Instant end = today.atStartOfDay(zone).toInstant();
        String date = yesterday.format(ENGLISH_DATE);

        int connections = 0;
        int critical = 0;
        int decoyInteractions = 0;

        try (BufferedReader reader = Files.newBufferedReader(
                eventFile, StandardCharsets.UTF_8
        )) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }

                try {
                    JsonElement parsed = JsonParser.parseString(line);
                    if (!parsed.isJsonObject()) {
                        continue;
                    }

                    JsonObject event = parsed.getAsJsonObject();
                    if (!"HONEYPOT_EVENT".equals(text(event, "type"))) {
                        continue;
                    }

                    Instant timestamp = OffsetDateTime.parse(
                            text(event, "timestamp")
                    ).toInstant();
                    if (timestamp.isBefore(start) || !timestamp.isBefore(end)) {
                        continue;
                    }

                    connections++;
                    if ("CRITICAL".equalsIgnoreCase(text(event, "global_level"))) {
                        critical++;
                    }

                    JsonElement decoy = event.get("decoy_active");
                    if (decoy != null && decoy.isJsonPrimitive()
                            && decoy.getAsJsonPrimitive().isBoolean()
                            && decoy.getAsBoolean()) {
                        decoyInteractions++;
                    }
                } catch (JsonParseException | DateTimeParseException ignored) {
                    // Skip malformed records and partially written lines.
                }
            }
        } catch (NoSuchFileException ignored) {
            return "My event log has not been created yet.";
        }

        if (connections == 0) {
            return "I found no recorded honeypot connections for yesterday, "
                    + date + ".";
        }

        return "Yesterday, " + date + ", I recorded "
                + counted(connections, "honeypot connection") + ". "
                + counted(critical, "connection") + " reached critical global risk, and "
                + counted(decoyInteractions, "connection") + " went to the decoy.";
    }

    private static String text(JsonObject event, String key) {
        JsonElement value = event.get(key);
        return value != null && value.isJsonPrimitive() ? value.getAsString() : "";
    }

    private static String counted(int count, String singular) {
        return count + " " + singular + (count == 1 ? "" : "s");
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of(args.length == 0 ? "Asia/Kolkata" : args[0]);
        IncidentHistory history = new IncidentHistory(Path.of("."), zone);

        try {
            System.out.println(history.summarizeYesterday());
        } catch (IOException error) {
            System.err.println("[HISTORY ERROR] Could not read the event log: "
                    + error.getMessage());
        }
    }
}