import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.TimeUnit;

public final class BehaviorAnalyser {
    private static final long WINDOW_NANOS = TimeUnit.SECONDS.toNanos(60);
    private static final int MAX_HISTORY_PER_IP = 30;

    private static final Map<String, Deque<Observation>> HISTORY = new HashMap<>();

    private BehaviorAnalyser() {
    }

    public static synchronized Map<String, Object> analyzeBehavior(
            String ip, Map<String, Object> payloadAnalysis
    ) {
        long now = System.nanoTime();
        String severity = (String) payloadAnalysis.get("severity");
        List<?> indicators = (List<?>) payloadAnalysis.get("indicators");
        int score = ((Number) payloadAnalysis.get("score")).intValue();

        Deque<Observation> history = HISTORY.computeIfAbsent(
                ip, key -> new ArrayDeque<>()
        );

        if (history.size() == MAX_HISTORY_PER_IP) {
            history.removeFirst();
        }
        history.addLast(new Observation(now, severity, List.copyOf(indicators)));

        while (now - history.getFirst().timeNanos() > WINDOW_NANOS) {
            history.removeFirst();
        }

        int connectionCount = history.size();
        int criticalCount = 0;
        Set<String> uniqueIndicators = new TreeSet<>();

        for (Observation event : history) {
            if ("CRITICAL".equals(event.severity())) {
                criticalCount++;
            }
            for (Object indicator : event.indicators()) {
                uniqueIndicators.add((String) indicator);
            }
        }

        if (connectionCount >= 3) {
            score += 10;
        }
        if (connectionCount >= 5) {
            score += 15;
        }
        if (criticalCount >= 2) {
            score += 20;
        }
        if (uniqueIndicators.size() >= 3) {
            score += 10;
        }
        score = Math.min(score, 100);

        String level;
        if (score >= 80) {
            level = "CRITICAL";
        } else if (score >= 60) {
            level = "HIGH";
        } else if (score >= 30) {
            level = "MEDIUM";
        } else {
            level = "LOW";
        }

        String behaviorType;
        if (criticalCount >= 2) {
            behaviorType = "REPEATED_CRITICAL_ACTIVITY";
        } else if (connectionCount >= 3) {
            behaviorType = "REPEATED_CONNECTIONS";
        } else {
            behaviorType = "SINGLE_ACTIVITY";
        }

        return Map.of(
                "behavior_score", score,
                "behavior_level", level,
                "behavior_type", behaviorType,
                "connections_60s", connectionCount,
                "critical_60s", criticalCount,
                "unique_indicators", new ArrayList<>(uniqueIndicators)
        );
    }

    private record Observation(long timeNanos, String severity, List<?> indicators) {
    }
}