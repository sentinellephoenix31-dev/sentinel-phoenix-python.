import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;
import com.google.gson.reflect.TypeToken;

import java.io.BufferedReader;
import java.io.IOException;
import java.lang.reflect.Type;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

public final class LatestIncident {
    private static final Gson JSON = new Gson();
    private static final Type EVENT_TYPE =
            new TypeToken<Map<String, Object>>() {}.getType();

    private final Path eventFile;

    public LatestIncident(Path projectRoot) {
        eventFile = projectRoot.resolve("data").resolve("events.jsonl");
    }

    public Optional<String> answer(String question) throws IOException {
        return loadReport().map(
                report -> IncidentReasoning.answerIncidentQuestion(question, report)
        );
    }

    public Optional<IncidentReasoning.Report> loadReport() throws IOException {
        Map<String, Object> event = readLatestEvent();
        if (event == null) {
            return Optional.empty();
        }

        Map<String, Object> learning = new LinkedHashMap<>(event);
        learning.put("model_status", event.get("ml_model_status"));

        Map<String, Object> fusion = new LinkedHashMap<>(event);
        fusion.put("decision", event.get("fusion_decision"));

        Map<String, Object> context = new LinkedHashMap<>();
        context.put("recommended_action", event.get("context_recommended_action"));

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("action", event.get("response_action"));
        response.put("containment_requested", event.get("containment_requested"));

        return Optional.of(IncidentReasoning.reasonAboutIncident(
                String.valueOf(event.getOrDefault("source_ip", "UNKNOWN")),
                event,      // Payload analysis
                event,      // Behavior
                event,      // Anomaly
                event,      // Reputation
                learning,
                fusion,
                context,
                response,
                event,      // Decoy
                event,      // Sandbox
                null        // No integrity assessment in the event log
        ));
    }

    private Map<String, Object> readLatestEvent() throws IOException {
        JsonElement latest = null;

        try (BufferedReader reader = Files.newBufferedReader(eventFile)) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }

                JsonElement parsed;
                try {
                    parsed = JsonParser.parseString(line);
                } catch (JsonParseException error) {
                    continue;
                }

                if (parsed.isJsonObject()) {
                    JsonElement type = parsed.getAsJsonObject().get("type");
                    if (type != null && type.isJsonPrimitive()
                            && "HONEYPOT_EVENT".equals(type.getAsString())) {
                        latest = parsed;
                    }
                }
            }
        } catch (NoSuchFileException ignored) {
            return null;
        }

        return latest == null ? null : JSON.fromJson(latest, EVENT_TYPE);
    }

    public static void main(String[] args) throws IOException {
        String question = args.length == 0
                ? "Why was the last incident dangerous?"
                : String.join(" ", args);

        LatestIncident incidents = new LatestIncident(Path.of("."));
        System.out.println("SENTINEL > " + incidents.answer(question)
                .orElse("I haven't recorded a honeypot connection yet."));
    }
}