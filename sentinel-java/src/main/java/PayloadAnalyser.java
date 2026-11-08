import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class PayloadAnalyser {
    private static final List<Rule> RULES = List.of(
            new Rule("powershell", 30),
            new Rule("cmd", 20),
            new Rule("bash", 20),
            new Rule("exec", 25),
            new Rule("exploit", 40),
            new Rule("nc ", 30),
            new Rule("wget", 15),
            new Rule("curl", 15)
    );

    private PayloadAnalyser() {
    }

    public static Map<String, Object> analyzePayload(String payload) {
        String text = payload.toLowerCase(Locale.ROOT);
        List<String> indicators = new ArrayList<>();
        int score = 0;

        for (Rule rule : RULES) {
            if (text.contains(rule.keyword())) {
                score += rule.weight();
                indicators.add(rule.keyword().trim());
            }
        }

        score = Math.min(score, 100);

        String severity;
        if (score >= 70) {
            severity = "CRITICAL";
        } else if (score >= 40) {
            severity = "HIGH";
        } else if (score >= 20) {
            severity = "MEDIUM";
        } else {
            severity = "LOW";
        }

        return Map.of(
                "score", score,
                "severity", severity,
                "indicators", indicators
        );
    }

    private record Rule(String keyword, int weight) {
    }
}