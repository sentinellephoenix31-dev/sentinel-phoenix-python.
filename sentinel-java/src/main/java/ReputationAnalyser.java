import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class ReputationAnalyser {
    private ReputationAnalyser() {
    }

    public static Map<String, Object> evaluateReputation(Map<String, ?> memory) {
        if (memory == null) {
            return Map.of(
                    "known_source", false,
                    "reputation_score", 0,
                    "reputation_level", "UNKNOWN",
                    "historical_risk", "NONE",
                    "reputation_reasons", List.of(),
                    "historical_events", 0,
                    "historical_critical", 0,
                    "historical_containments", 0
            );
        }

        int totalEvents = readInt(memory, "total_events");
        int criticalEvents = readInt(memory, "critical_events");
        int containmentEvents = readInt(memory, "containment_events");
        double maxGlobal = Double.parseDouble(
                String.valueOf(readField(memory, "max_global_score", 0))
        );

        List<?> indicators = (List<?>) readField(memory, "indicators", List.of());
        List<?> anomalies = (List<?>) readField(memory, "anomaly_reasons", List.of());
        boolean sandboxSeen = Boolean.TRUE.equals(memory.get("sandbox_seen"));

        int score = 0;
        List<String> reasons = new ArrayList<>();

        if (maxGlobal >= 80) {
            score += 30;
            reasons.add("PAST_CRITICAL_RISK");
        } else if (maxGlobal >= 60) {
            score += 20;
            reasons.add("PAST_HIGH_RISK");
        } else if (maxGlobal >= 30) {
            score += 10;
            reasons.add("PAST_MEDIUM_RISK");
        }

        if (criticalEvents > 0) {
            score += (int) Math.min(criticalEvents * 8L, 30);
            reasons.add("HISTORICAL_CRITICAL_EVENTS");
        }
        if (containmentEvents > 0) {
            score += (int) Math.min(containmentEvents * 10L, 30);
            reasons.add("PAST_CONTAINMENT");
        }
        if (sandboxSeen) {
            score += 10;
            reasons.add("PREVIOUS_SANDBOX_ACTIVITY");
        }

        if (totalEvents >= 25) {
            score += 15;
            reasons.add("HIGH_HISTORICAL_ACTIVITY");
        } else if (totalEvents >= 10) {
            score += 10;
            reasons.add("REPEATED_HISTORICAL_ACTIVITY");
        } else if (totalEvents >= 5) {
            score += 5;
            reasons.add("KNOWN_REPEAT_SOURCE");
        }

        if (indicators != null && !indicators.isEmpty()) {
            score += (int) Math.min(indicators.size() * 2L, 10);
            reasons.add("KNOWN_THREAT_INDICATORS");
        }
        if (anomalies != null && !anomalies.isEmpty()) {
            score += (int) Math.min(anomalies.size() * 2L, 10);
            reasons.add("KNOWN_ANOMALY_HISTORY");
        }

        score = Math.min(score, 100);
        String level;
        String historicalRisk;

        if (score >= 80) {
            level = "HOSTILE_HISTORY";
            historicalRisk = "CRITICAL";
        } else if (score >= 60) {
            level = "HIGH_RISK_HISTORY";
            historicalRisk = "HIGH";
        } else if (score >= 30) {
            level = "SUSPICIOUS_HISTORY";
            historicalRisk = "MEDIUM";
        } else {
            level = score > 0 ? "KNOWN_HISTORY" : "KNOWN_CLEAN";
            historicalRisk = "LOW";
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("known_source", true);
        result.put("reputation_score", score);
        result.put("reputation_level", level);
        result.put("historical_risk", historicalRisk);
        result.put("reputation_reasons", reasons);
        result.put("historical_events", totalEvents);
        result.put("historical_critical", criticalEvents);
        result.put("historical_containments", containmentEvents);
        result.put("max_historical_risk", maxGlobal);
        result.put("historical_indicators", indicators);
        result.put("historical_anomalies", anomalies);
        return result;
    }

    private static int readInt(Map<String, ?> memory, String key) {
        Object value = readField(memory, key, 0);
        if (value instanceof Number number) {
            return number.intValue();
        }
        return Integer.parseInt(String.valueOf(value).strip());
    }

    private static Object readField(Map<String, ?> memory, String key, Object fallback) {
        return memory.containsKey(key) ? memory.get(key) : fallback;
    }
}