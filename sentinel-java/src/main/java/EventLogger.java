import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class EventLogger {
    private static final Gson JSON = new GsonBuilder()
            .serializeNulls()
            .disableHtmlEscaping()
            .create();

    private static final DateTimeFormatter UTC_TIMESTAMP =
            DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSSSSSxxx");

    private static final Object WRITE_LOCK = new Object();

    private final Path eventFile;

    public EventLogger(Path projectRoot) {
        this.eventFile = projectRoot.resolve("data").resolve("events.jsonl");
    }

    public Map<String, Object> recordEvent(
            String ip,
            int port,
            String payload,
            Map<String, ?> analysis,
            Map<String, ?> behavior,
            Map<String, ?> anomaly,
            Map<String, ?> reputation,
            Map<String, ?> learning,
            Map<String, ?> fusion,
            Map<String, ?> context,
            Map<String, ?> response,
            Map<String, ?> deception,
            Map<String, ?> sandbox
    ) throws IOException {
        Map<String, Object> event = new LinkedHashMap<>();

        int length = Math.min(500, payload.codePointCount(0, payload.length()));
        int end = payload.offsetByCodePoints(0, length);

        event.put("timestamp", OffsetDateTime.now(ZoneOffset.UTC).format(UTC_TIMESTAMP));
        event.put("type", "HONEYPOT_EVENT");
        event.put("source_ip", ip);
        event.put("source_port", port);
        event.put("payload", payload.substring(0, end));

        copyFields(event, analysis, null, "severity");
        copyFields(event, analysis, 0, "score");
        copyFields(event, analysis, List.of(), "indicators");

        copyFields(event, behavior, null, "behavior_level", "behavior_type");
        copyFields(event, behavior, 0, "behavior_score", "connections_60s", "critical_60s");
        copyFields(event, behavior, List.of(), "unique_indicators");

        copyFields(event, anomaly, null, "anomaly_level");
        copyFields(event, anomaly, 0, "anomaly_score", "payload_length",
                "entropy", "length_zscore", "connections_30s");
        copyFields(event, anomaly, List.of(), "anomaly_reasons");

        copyFields(event, reputation, false, "known_source");
        copyFields(event, reputation, 0, "reputation_score", "historical_events",
                "historical_critical", "historical_containments");
        copyFields(event, reputation, null, "reputation_level");
        copyFields(event, reputation, List.of(), "reputation_reasons");

        copyFields(event, learning, 0, "ml_score", "ml_confidence",
                "ml_model_samples:model_samples", "ml_normal_samples:normal_samples",
                "ml_dangerous_samples:dangerous_samples");
        copyFields(event, learning, null, "ml_level", "ml_model_status:model_status",
                "ml_model_version:model_version");
        copyFields(event, learning, List.of(), "learning_reasons");

        copyFields(event, fusion, 0, "current_risk_score", "historical_bonus",
                "deterministic_score", "global_score", "confidence", "fusion_ml_weight:ml_weight");
        copyFields(event, fusion, null, "global_level", "fusion_decision:decision",
                "fusion_version", "fusion_mode");
        copyFields(event, fusion, false, "fusion_ml_active:ml_active");
        copyFields(event, fusion, List.of(), "fusion_reasons");

        copyFields(event, context, 0, "context_score");
        copyFields(event, context, null, "context_level",
                "context_recommended_action:recommended_action");
        copyFields(event, context, List.of(), "context_reasons", "context_summary");
        copyFields(event, context, false, "review_required");

        copyFields(event, response, null, "response_action:action", "monitoring_level");
        copyFields(event, response, false, "containment_requested");
        copyFields(event, response, List.of(), "response_reasons");

        copyFields(event, deception, false, "decoy_active", "decoy_reused");
        copyFields(event, deception, null, "decoy_session_id", "decoy_mode");

        copyFields(event, sandbox, false, "sandbox_active", "sandbox_reused", "sandbox_privileged");
        copyFields(event, sandbox, null, "sandbox_name", "sandbox_id", "sandbox_error");
        copyFields(event, sandbox, "NONE", "sandbox_network");
        copyFields(event, sandbox, true, "sandbox_read_only");

        event.put("payload_execution", false);
        event.put("status", "ANALYZED");

        String line = JSON.toJson(event) + "\n";

        synchronized (WRITE_LOCK) {
            Files.createDirectories(eventFile.getParent());
            Files.writeString(eventFile, line, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        }

        return event;
    }

    private static void copyFields(
            Map<String, Object> event,
            Map<String, ?> source,
            Object defaultValue,
            String... fields
    ) {
        for (String field : fields) {
            // Un alias suit la forme « clé JSON:clé du moteur ».
            String[] keys = field.split(":", 2);
            String sourceKey = keys.length == 2 ? keys[1] : keys[0];
            Object value = source.containsKey(sourceKey) ? source.get(sourceKey) : defaultValue;
            event.put(keys[0], value);
        }
    }
}