import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class RiskFusion {
    private RiskFusion() {
    }

    public static Map<String, Object> fuseRisk(
            Map<String, Object> analysis,
            Map<String, Object> behavior,
            Map<String, Object> anomaly,
            Map<String, Object> reputation,
            Map<String, Object> learning
    ) {
        double payloadScore = score(analysis, "score");
        double behaviorScore = score(behavior, "behavior_score");
        double anomalyScore = score(anomaly, "anomaly_score");
        double reputationScore = score(reputation, "reputation_score");
        double mlScore = score(learning, "ml_score");
        int mlConfidence = (int) score(learning, "ml_confidence");
        boolean knownSource = Boolean.TRUE.equals(reputation.get("known_source"));

        double currentScore = round(
                payloadScore * 0.40 + behaviorScore * 0.35 + anomalyScore * 0.25
        );
        double historicalBonus = round(Math.min(reputationScore * 0.15, 15));
        double deterministicScore = clamp(currentScore + historicalBonus, 100);

        boolean mlActive = "READY".equalsIgnoreCase(
                String.valueOf(learning.get("model_status"))
        ) && mlConfidence >= 60;

        double mlWeight = mlActive ? 0.20 : 0.0;
        double deterministicWeight = mlActive ? 0.80 : 1.0;
        double fusedScore = mlActive
                ? deterministicScore * deterministicWeight + mlScore * mlWeight
                : deterministicScore;

        List<String> reasons = new ArrayList<>();
        reasons.add(mlActive ? "LEARNING_MODEL_ACTIVE" : "DETERMINISTIC_FALLBACK");

        boolean agreement = mlActive && deterministicScore >= 60 && mlScore >= 60;
        if (agreement) {
            fusedScore += 5;
            reasons.add("ML_DETERMINISTIC_AGREEMENT");
        }

        boolean disagreement = mlActive && Math.abs(mlScore - deterministicScore) >= 35;
        if (disagreement) {
            reasons.add("MODEL_DISAGREEMENT");
        }

        if (knownSource) {
            reasons.add("KNOWN_SOURCE");
        }
        if (reputationScore >= 80) {
            reasons.add("HOSTILE_HISTORY");
        } else if (reputationScore >= 60) {
            reasons.add("HIGH_RISK_HISTORY");
        } else if (reputationScore >= 30) {
            reasons.add("SUSPICIOUS_HISTORY");
        } else if (reputationScore > 0) {
            reasons.add("KNOWN_RISK_HISTORY");
        }

        int criticalEngines = 0;
        if (isCritical(analysis, "severity")) {
            criticalEngines++;
            reasons.add("CRITICAL_PAYLOAD");
        }
        if (isCritical(behavior, "behavior_level")) {
            criticalEngines++;
            reasons.add("CRITICAL_BEHAVIOR");
        }
        if (isCritical(anomaly, "anomaly_level")) {
            criticalEngines++;
            reasons.add("CRITICAL_ANOMALY");
        }

        if (criticalEngines >= 2) {
            fusedScore += 15;
            reasons.add("MULTI_ENGINE_CRITICAL");
        }
        if (criticalEngines == 3) {
            fusedScore += 10;
            reasons.add("FULL_ENGINE_CONSENSUS");
        }
        if ("REPEATED_CRITICAL_ACTIVITY".equals(behavior.get("behavior_type"))) {
            fusedScore += 10;
            reasons.add("REPEATED_CRITICAL_ACTIVITY");
        }
        if (anomaly.get("anomaly_reasons") instanceof List<?> anomalies
                && anomalies.size() >= 2) {
            fusedScore += 5;
            reasons.add("MULTIPLE_ANOMALIES");
        }

        boolean currentDanger = payloadScore >= 60 || behaviorScore >= 60 || anomalyScore >= 60;
        if (reputationScore >= 60 && currentDanger) {
            fusedScore += 5;
            reasons.add("HISTORY_CURRENT_RISK_CORRELATION");
        }
        if (mlActive && mlScore >= 80 && mlConfidence >= 75 && currentDanger) {
            fusedScore += 5;
            reasons.add("STRONG_LEARNED_RISK");
        }

        double globalScore = round(clamp(fusedScore, 100));
        String globalLevel;
        String decision;

        if (globalScore >= 80) {
            globalLevel = "CRITICAL";
            decision = "ISOLATION_RECOMMENDED";
        } else if (globalScore >= 60) {
            globalLevel = "HIGH";
            decision = "ENHANCED_MONITORING";
        } else if (globalScore >= 30) {
            globalLevel = "MEDIUM";
            decision = "MONITOR";
        } else {
            globalLevel = "LOW";
            decision = "OBSERVE";
        }

        int activeEngines = 0;
        for (double engineScore : new double[] {payloadScore, behaviorScore, anomalyScore}) {
            if (engineScore >= 30) {
                activeEngines++;
            }
        }

        int confidence = switch (activeEngines) {
            case 3 -> 92;
            case 2 -> 82;
            case 1 -> 68;
            default -> 52;
        };

        if (knownSource && reputationScore >= 30) {
            confidence += 4;
        }
        if (mlActive) {
            confidence += Math.min((int) (mlConfidence * 0.08), 7);
        }
        if (agreement) {
            confidence += 4;
        }
        if (disagreement) {
            confidence -= 8;
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("global_score", globalScore);
        result.put("global_level", globalLevel);
        result.put("decision", decision);
        result.put("confidence", (int) clamp(confidence, 99));
        result.put("fusion_version", "3.0");
        result.put("fusion_mode", mlActive ? "HYBRID_ML" : "DETERMINISTIC");
        result.put("fusion_reasons", reasons);
        result.put("current_risk_score", currentScore);
        result.put("historical_bonus", historicalBonus);
        result.put("deterministic_score", round(deterministicScore));
        result.put("ml_active", mlActive);
        result.put("ml_weight", mlWeight);
        result.put("deterministic_weight", deterministicWeight);
        result.put("critical_engines", criticalEngines);
        result.put("engine_scores", Map.of(
                "payload", payloadScore,
                "behavior", behaviorScore,
                "anomaly", anomalyScore,
                "reputation", reputationScore,
                "learning", mlScore
        ));
        return result;
    }

    private static double score(Map<String, Object> engine, String key) {
        Object value = engine.getOrDefault(key, 0);
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        return Double.parseDouble(String.valueOf(value));
    }

    private static boolean isCritical(Map<String, Object> engine, String key) {
        return "CRITICAL".equalsIgnoreCase(String.valueOf(engine.get(key)));
    }

    private static double clamp(double value, int maximum) {
        return Math.max(0, Math.min(maximum, value));
    }

    private static double round(double value) {
        return new BigDecimal(value).setScale(2, RoundingMode.HALF_EVEN).doubleValue();
    }
}