import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class ContextEngine {
    private ContextEngine() {
    }

    public static Map<String, Object> buildContext(
            Map<String, Object> analysis,
            Map<String, Object> behavior,
            Map<String, Object> anomaly,
            Map<String, Object> reputation,
            Map<String, Object> fusion
    ) {
        double payloadScore = score(analysis, "score");
        double behaviorScore = score(behavior, "behavior_score");
        double anomalyScore = score(anomaly, "anomaly_score");
        double reputationScore = score(reputation, "reputation_score");
        double contextScore = score(fusion, "global_score");
        int confidence = (int) score(fusion, "confidence");

        List<String> reasons = new ArrayList<>();
        List<String> summary = new ArrayList<>();

        if (Boolean.TRUE.equals(reputation.get("known_source"))) {
            reasons.add("SOURCE_ALREADY_KNOWN");
            if (reputationScore >= 30) {
                contextScore += Math.min(reputationScore * 0.10, 10);
                reasons.add("HISTORICAL_RISK_PRESENT");
            }
        }

        if ("REPEATED_CRITICAL_ACTIVITY".equals(behavior.get("behavior_type"))) {
            contextScore += 10;
            reasons.add("REPEATED_CRITICAL_PATTERN");
        }

        if (anomaly.get("anomaly_reasons") instanceof List<?> anomalyReasons
                && anomalyReasons.size() >= 2) {
            contextScore += 5;
            reasons.add("MULTIPLE_ANOMALIES");
        }

        int dangerousEngines = 0;
        if (payloadScore >= 60) {
            dangerousEngines++;
            summary.add("dangerous_payload");
        }
        if (behaviorScore >= 60) {
            dangerousEngines++;
            summary.add("dangerous_behavior");
        }
        if (anomalyScore >= 60) {
            dangerousEngines++;
            summary.add("strong_anomaly");
        }
        if (dangerousEngines >= 2) {
            contextScore += 8;
            reasons.add("MULTIPLE_DANGEROUS_ENGINES");
        }

        contextScore = Math.min(
                new BigDecimal(contextScore).setScale(2, RoundingMode.HALF_EVEN).doubleValue(),
                100
        );

        String level;
        String action;
        boolean reviewRequired = contextScore >= 60;

        if (contextScore >= 80) {
            level = "CRITICAL";
            action = confidence >= 80 ? "CONTAIN_DECOY" : "HEIGHTEN_MONITORING";
        } else if (contextScore >= 60) {
            level = "ELEVATED";
            action = "HEIGHTEN_MONITORING";
        } else if (contextScore >= 30) {
            level = "WATCH";
            action = "MONITOR";
        } else {
            level = "NORMAL";
            action = "OBSERVE";
        }

        if (reputationScore >= 30) {
            summary.add("historical_risk");
        }
        if (summary.isEmpty()) {
            summary.add("no_major_signal");
        }

        return Map.of(
                "context_score", contextScore,
                "context_level", level,
                "recommended_action", action,
                "review_required", reviewRequired,
                "context_reasons", reasons,
                "context_summary", summary,
                "dangerous_engines", dangerousEngines,
                "confidence", confidence
        );
    }

    private static double score(Map<String, Object> engine, String key) {
        Object value = engine.getOrDefault(key, 0);
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        return Double.parseDouble(String.valueOf(value));
    }
}