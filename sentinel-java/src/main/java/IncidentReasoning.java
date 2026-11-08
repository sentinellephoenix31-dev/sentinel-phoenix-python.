import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public final class IncidentReasoning {
    private static final String BRAIN_VERSION = "1.0";

    private static final Set<String> HOSTILE_SIGNALS = Set.of(
            "STRONG_MALICIOUS_PAYLOAD_SIGNAL",
            "AGGRESSIVE_BEHAVIOR_PATTERN",
            "REPEATED_CRITICAL_ACTIVITY",
            "HIGH_RISK_HISTORY",
            "LEARNING_MODEL_HIGH_RISK"
    );

    private IncidentReasoning() {
    }

    public record Assessment(
            String riskLevel,
            double riskScore,
            String intent,
            int intentConfidence,
            double reasoningConfidence,
            String posture
    ) {
    }

    public record Report(
            String timestamp,
            String sourceIp,
            Assessment assessment,
            List<String> signals,
            int corroboratingEngines,
            String explanation,
            Map<String, Object> decision,
            Map<String, Object> deception,
            Map<String, Object> sandbox
    ) {
        public Map<String, Object> toMap() {
            return Map.of(
                    "brain_version", BRAIN_VERSION,
                    "timestamp", timestamp,
                    "source_ip", sourceIp,
                    "assessment", Map.of(
                            "risk_level", assessment.riskLevel(),
                            "risk_score", assessment.riskScore(),
                            "intent", assessment.intent(),
                            "intent_confidence", assessment.intentConfidence(),
                            "reasoning_confidence", assessment.reasoningConfidence(),
                            "posture", assessment.posture()
                    ),
                    "signals", signals,
                    "corroborating_engines", corroboratingEngines,
                    "explanation", explanation,
                    "decision", decision,
                    "deception", deception,
                    "sandbox", sandbox
            );
        }

        public Map<String, Object> toFullMap() {
            Map<String, Object> result = new LinkedHashMap<>(toMap());
            result.put("safety", Map.of(
                    "payload_execution", false,
                    "shell_execution", false,
                    "brain_host_modification", false
            ));
            return result;
        }
    }

    public static Report reasonAboutIncident(
            String sourceIp,
            Map<String, ?> analysis,
            Map<String, ?> behavior,
            Map<String, ?> anomaly,
            Map<String, ?> reputation,
            Map<String, ?> learning,
            Map<String, ?> fusion,
            Map<String, ?> context,
            Map<String, ?> response,
            Map<String, ?> deception,
            Map<String, ?> sandbox,
            Map<String, ?> integrity
    ) {
        double payloadScore = number(analysis, "score", 0);
        double behaviorScore = number(behavior, "behavior_score", 0);
        double anomalyScore = number(anomaly, "anomaly_score", 0);
        double reputationScore = number(reputation, "reputation_score", 0);
        double mlScore = number(learning, "ml_score", 0);
        double globalScore = number(fusion, "global_score", 0);
        String globalLevel = text(fusion, "global_level", "LOW");

        boolean containmentRequested = flag(response, "containment_requested");
        boolean decoyActive = flag(deception, "decoy_active");
        boolean decoyRotated = flag(deception, "surface_rotated");
        boolean sandboxActive = flag(sandbox, "sandbox_active");
        boolean integrityFailure = integrity != null && Boolean.FALSE.equals(integrity.get("clean"));

        List<String> signals = new ArrayList<>();
        List<String> reasons = new ArrayList<>();

        if (payloadScore >= 70) {
            signals.add("STRONG_MALICIOUS_PAYLOAD_SIGNAL");
        } else if (payloadScore >= 40) {
            signals.add("SUSPICIOUS_PAYLOAD_SIGNAL");
        }
        if (!list(analysis, "indicators").isEmpty()) {
            signals.add("KNOWN_THREAT_INDICATORS_PRESENT");
            reasons.add("known payload indicators were detected");
        }

        if (behaviorScore >= 80) {
            signals.add("AGGRESSIVE_BEHAVIOR_PATTERN");
        } else if (behaviorScore >= 50) {
            signals.add("SUSPICIOUS_BEHAVIOR_PATTERN");
        }
        if ("REPEATED_CRITICAL_ACTIVITY".equals(behavior.get("behavior_type"))) {
            signals.add("REPEATED_CRITICAL_ACTIVITY");
        }
        if (behaviorScore >= 60) {
            reasons.add("the source displayed suspicious repeated behavior");
        }

        if (anomalyScore >= 70) {
            signals.add("STRONG_ANOMALY");
        }
        if (list(anomaly, "anomaly_reasons").size() >= 2) {
            signals.add("MULTIPLE_ANOMALIES");
        }
        if (anomalyScore >= 60) {
            reasons.add("the activity differed significantly from the observed baseline");
        }

        if (flag(reputation, "known_source")) {
            signals.add("KNOWN_SOURCE");
        }
        if (reputationScore >= 60) {
            signals.add("HIGH_RISK_HISTORY");
            reasons.add("the source already has a high-risk historical profile");
        }

        if ("READY".equals(learning.get("model_status"))) {
            signals.add("LEARNING_MODEL_AVAILABLE");
        }
        if (mlScore >= 70) {
            signals.add("LEARNING_MODEL_HIGH_RISK");
            reasons.add("the learned model placed the pattern near its dangerous profile");
        }

        boolean disagreement = list(fusion, "fusion_reasons").contains("MODEL_DISAGREEMENT");
        if (disagreement) {
            signals.add("MODEL_DISAGREEMENT");
        }

        if (globalScore >= 80) {
            signals.add("CRITICAL_GLOBAL_RISK");
        } else if (globalScore >= 60) {
            signals.add("HIGH_GLOBAL_RISK");
        } else if (globalScore >= 30) {
            signals.add("ELEVATED_GLOBAL_RISK");
        }

        if (containmentRequested) {
            signals.add("CONTAINMENT_REQUESTED");
        }
        if (decoyActive) {
            signals.add("DECEPTION_ACTIVE");
        }
        if (decoyRotated) {
            signals.add("DECEPTION_SURFACE_ROTATED");
        }
        if (sandboxActive) {
            signals.add("SANDBOX_ACTIVE");
        }
        if (integrityFailure) {
            signals.add("CORE_INTEGRITY_FAILURE");
        }

        long hostileCount = signals.stream().filter(HOSTILE_SIGNALS::contains).count();
        String intent;
        int intentConfidence;

        if (globalScore >= 80 && hostileCount >= 2) {
            intent = "PROBABLE_HOSTILE_ACTIVITY";
            intentConfidence = 90;
        } else if (globalScore >= 60 || hostileCount >= 2) {
            intent = "SUSPICIOUS_ACTIVITY";
            intentConfidence = 75;
        } else if (globalScore >= 30) {
            intent = "UNCERTAIN_ACTIVITY";
            intentConfidence = 55;
        } else {
            intent = "LOW_RISK_ACTIVITY";
            intentConfidence = 40;
        }

        int corroboration = 0;
        for (double score : new double[] {
                payloadScore, behaviorScore, anomalyScore, reputationScore, mlScore
        }) {
            if (score >= 50) {
                corroboration++;
            }
        }

        double confidence = number(fusion, "confidence", 50) + Math.min(corroboration * 3, 15);
        if (disagreement) {
            confidence -= 10;
        }

        String posture;
        if (integrityFailure) {
            posture = "RECOVERY";
        } else if (containmentRequested) {
            posture = "CONTAIN";
        } else {
            posture = switch (globalLevel.toUpperCase(Locale.ROOT)) {
                case "CRITICAL" -> "CONTAIN";
                case "HIGH" -> "HEIGHTEN_MONITORING";
                case "MEDIUM" -> "MONITOR";
                default -> "OBSERVE";
            };
        }

        Assessment assessment = new Assessment(
                globalLevel, round(globalScore), intent, intentConfidence,
                round(Math.max(20, Math.min(98, confidence))), posture
        );

        if (reasons.isEmpty()) {
            reasons.add("no strong correlated threat evidence was observed");
        }

        String explanation = "Source " + sourceIp + " was assessed as "
                + globalLevel + " risk with a score of " + assessment.riskScore()
                + "/100. Signals: " + String.join(", ", reasons) + ".";

        if (decoyActive) {
            explanation += " Sentinel routed the interaction to its decoy.";
        }
        if (decoyRotated) {
            explanation += " The decoy profile rotated after reconnaissance activity was detected.";
        }
        if (containmentRequested) {
            explanation += " The policy engine requested containment.";
        }

        Map<String, Object> decision = new LinkedHashMap<>();
        decision.put("fusion_decision", fusion.get("decision"));
        decision.put("context_recommendation", context.get("recommended_action"));
        decision.put("policy_action", response.get("action"));
        decision.put("containment_requested", containmentRequested);

        Map<String, Object> decoyDetails = new LinkedHashMap<>();
        decoyDetails.put("active", decoyActive);
        decoyDetails.put("profile", deception.get("decoy_profile"));
        decoyDetails.put("generation", deception.get("surface_generation"));
        decoyDetails.put("rotated", decoyRotated);

        Map<String, Object> sandboxDetails = new LinkedHashMap<>();
        sandboxDetails.put("active", sandboxActive);
        sandboxDetails.put("network", text(sandbox, "sandbox_network", "NONE"));
        sandboxDetails.put("privileged", flag(sandbox, "sandbox_privileged"));

        return new Report(
                Instant.now().toString(), sourceIp, assessment, List.copyOf(signals),
                corroboration, explanation, decision, decoyDetails, sandboxDetails
        );
    }

    public static String answerIncidentQuestion(String question, Report report) {
        String text = question.strip().toLowerCase(Locale.ROOT);
        Assessment assessment = report.assessment();

        if (text.contains("why") || text.contains("pourquoi")) {
            return report.explanation();
        }
        if (text.contains("risk") || text.contains("danger") || text.contains("risque")) {
            return "Current risk is " + assessment.riskLevel() + " at "
                    + assessment.riskScore() + "/100. My reasoning confidence is "
                    + assessment.reasoningConfidence() + "%.";
        }
        if (text.contains("intent")) {
            return "I classify this as " + assessment.intent() + " with "
                    + assessment.intentConfidence() + "% confidence.";
        }
        if (text.contains("what did you do") || text.contains("qu'est-ce que tu as fait")
                || text.contains("action")) {
            return "My current defensive posture is " + assessment.posture()
                    + ". The policy action is "
                    + text(report.decision(), "policy_action", "UNKNOWN") + ".";
        }
        if (text.contains("deception") || text.contains("decoy") || text.contains("leurre")) {
            if (flag(report.deception(), "active")) {
                return "The decoy is active using profile "
                        + text(report.deception(), "profile", "UNKNOWN") + " at generation "
                        + text(report.deception(), "generation", "UNKNOWN") + ".";
            }
            return "No decoy is active for this incident.";
        }
        return report.explanation();
    }

    private static double number(Map<String, ?> values, String key, double fallback) {
        Object value = values.get(key);
        try {
            double number = value instanceof Number n ? n.doubleValue()
                    : value == null ? fallback : Double.parseDouble(value.toString());
            return Double.isFinite(number) ? number : fallback;
        } catch (NumberFormatException error) {
            return fallback;
        }
    }

    private static String text(Map<String, ?> values, String key, String fallback) {
        Object value = values.get(key);
        return value == null ? fallback : value.toString();
    }

    private static boolean flag(Map<String, ?> values, String key) {
        return Boolean.TRUE.equals(values.get(key));
    }

    private static Collection<?> list(Map<String, ?> values, String key) {
        return values.get(key) instanceof Collection<?> items ? items : List.of();
    }

    private static double round(double value) {
        return new BigDecimal(value).setScale(2, RoundingMode.HALF_EVEN).doubleValue();
    }
}