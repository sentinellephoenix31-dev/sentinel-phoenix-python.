import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class PolicyEngine {
    private static final Map<String, Integer> ACTION_PRIORITY = Map.of(
            "OBSERVE", 0,
            "MONITOR", 1,
            "HEIGHTEN_MONITORING", 2,
            "CONTAIN_DECOY", 3
    );

    private final Map<String, SourceState> sourceStates = new HashMap<>();

    public synchronized Map<String, Object> applyPolicy(
            String sourceIp,
            Map<String, Object> fusion,
            Map<String, Object> behavior,
            Map<String, Object> anomaly,
            Map<String, Object> context
    ) {
        long now = System.currentTimeMillis();
        double globalScore = readNumber(fusion, "global_score");
        String globalLevel = String.valueOf(fusion.getOrDefault("global_level", "LOW"))
                .toUpperCase(Locale.ROOT);
        int confidence = (int) readNumber(fusion, "confidence");
        List<String> reasons = new ArrayList<>();

        String action;
        if ("CRITICAL".equals(globalLevel) && confidence >= 80) {
            action = "CONTAIN_DECOY";
            reasons.add("CRITICAL_GLOBAL_RISK");
        } else if ("HIGH".equals(globalLevel)) {
            action = "HEIGHTEN_MONITORING";
            reasons.add("HIGH_GLOBAL_RISK");
        } else if ("MEDIUM".equals(globalLevel)) {
            action = "MONITOR";
            reasons.add("MEDIUM_GLOBAL_RISK");
        } else {
            action = "OBSERVE";
            reasons.add("LOW_GLOBAL_RISK");
        }

        String contextAction = String.valueOf(
                context.getOrDefault("recommended_action", "OBSERVE")
        );
        String previousAction = action;
        action = strongestAction(action, contextAction);
        if (!action.equals(previousAction)) {
            reasons.add("CONTEXT_ESCALATION");
        }

        if ("REPEATED_CRITICAL_ACTIVITY".equals(behavior.get("behavior_type"))) {
            reasons.add("REPEATED_CRITICAL_ACTIVITY");
            action = strongestAction(action, "HEIGHTEN_MONITORING");
        }

        if (anomaly.get("anomaly_reasons") instanceof List<?> anomalyReasons
                && anomalyReasons.size() >= 3) {
            reasons.add("MULTIPLE_ANOMALY_SIGNALS");
        }

        boolean containmentRequested = "CONTAIN_DECOY".equals(action);
        String monitoringLevel = switch (action) {
            case "CONTAIN_DECOY" -> "MAXIMUM";
            case "HEIGHTEN_MONITORING" -> "HIGH";
            case "MONITOR" -> "MEDIUM";
            default -> "NORMAL";
        };

        SourceState state = sourceStates.computeIfAbsent(sourceIp, ip -> new SourceState());
        state.events++;
        if (containmentRequested) {
            state.containmentRequests++;
        }
        state.lastSeenMillis = now;
        state.lastAction = action;
        state.lastGlobalScore = globalScore;
        state.lastContextScore = readNumber(context, "context_score");

        return Map.of(
                "response_id", sourceIp + "-" + now,
                "action", action,
                "monitoring_level", monitoringLevel,
                "containment_requested", containmentRequested,
                "response_reasons", reasons,
                "source_events", state.events,
                "containment_count", state.containmentRequests,
                "policy_status", "DECISION_READY",
                "context_used", true
        );
    }

    private static String strongestAction(String first, String second) {
        int firstPriority = ACTION_PRIORITY.getOrDefault(first, 0);
        int secondPriority = ACTION_PRIORITY.getOrDefault(second, 0);
        return secondPriority > firstPriority ? second : first;
    }

    private static double readNumber(Map<String, Object> values, String key) {
        Object value = values.getOrDefault(key, 0);
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        return Double.parseDouble(String.valueOf(value));
    }

    private static final class SourceState {
        private long events;
        private long containmentRequests;
        private long lastSeenMillis;
        private String lastAction;
        private double lastGlobalScore;
        private double lastContextScore;
    }
}