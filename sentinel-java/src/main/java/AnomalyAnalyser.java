import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public final class AnomalyAnalyser {
    private static final long WINDOW_NANOS = TimeUnit.SECONDS.toNanos(30);
    private static final int MAX_HISTORY = 50;
    private static final int MAX_GLOBAL_LENGTHS = 100;

    private static final Map<String, Deque<Long>> IP_HISTORY = new HashMap<>();
    private static final Deque<Integer> GLOBAL_LENGTHS = new ArrayDeque<>();

    private AnomalyAnalyser() {
    }

    public static synchronized Map<String, Object> analyzeAnomaly(
            String ip, String payload
    ) {
        long now = System.nanoTime();
        int[] characters = payload.codePoints().toArray();
        int payloadLength = characters.length;
        double entropy = calculateEntropy(characters);
        double nonPrintableRatio = calculateNonPrintableRatio(characters);

        Deque<Long> history = IP_HISTORY.computeIfAbsent(
                ip, key -> new ArrayDeque<>()
        );
        if (history.size() == MAX_HISTORY) {
            history.removeFirst();
        }
        history.addLast(now);

        while (now - history.getFirst() > WINDOW_NANOS) {
            history.removeFirst();
        }
        int connections30s = history.size();

        double lengthZscore = calculateLengthZscore(payloadLength);
        if (GLOBAL_LENGTHS.size() == MAX_GLOBAL_LENGTHS) {
            GLOBAL_LENGTHS.removeFirst();
        }
        GLOBAL_LENGTHS.addLast(payloadLength);

        List<String> reasons = new ArrayList<>();
        int score = 0;

        if (connections30s >= 5) {
            score += 20;
            reasons.add("HIGH_CONNECTION_FREQUENCY");
        }
        if (connections30s >= 10) {
            score += 20;
            reasons.add("CONNECTION_BURST");
        }
        if (payloadLength > 512) {
            score += 15;
            reasons.add("LARGE_PAYLOAD");
        }
        if (payloadLength > 1500) {
            score += 20;
            reasons.add("VERY_LARGE_PAYLOAD");
        }
        if (entropy >= 4.5) {
            score += 20;
            reasons.add("HIGH_ENTROPY");
        }
        if (nonPrintableRatio >= 0.15) {
            score += 25;
            reasons.add("NON_PRINTABLE_CONTENT");
        }
        if (lengthZscore >= 3.0) {
            score += 20;
            reasons.add("STATISTICAL_LENGTH_ANOMALY");
        }

        score = Math.min(score, 100);

        String level;
        if (score >= 80) {
            level = "CRITICAL";
        } else if (score >= 55) {
            level = "HIGH";
        } else if (score >= 25) {
            level = "MEDIUM";
        } else {
            level = "LOW";
        }

        return Map.of(
                "anomaly_score", score,
                "anomaly_level", level,
                "anomaly_reasons", reasons,
                "payload_length", payloadLength,
                "entropy", entropy,
                "non_printable_ratio", nonPrintableRatio,
                "length_zscore", lengthZscore,
                "connections_30s", connections30s
        );
    }

    private static double calculateEntropy(int[] characters) {
        if (characters.length == 0) {
            return 0.0;
        }

        Map<Integer, Integer> counts = new LinkedHashMap<>();
        for (int character : characters) {
            counts.merge(character, 1, Integer::sum);
        }

        double entropy = 0.0;
        for (int count : counts.values()) {
            double probability = (double) count / characters.length;
            entropy -= probability * (Math.log(probability) / Math.log(2));
        }
        return Math.rint(entropy * 100) / 100;
    }

    private static double calculateNonPrintableRatio(int[] characters) {
        if (characters.length == 0) {
            return 0.0;
        }

        int nonPrintable = 0;
        for (int character : characters) {
            if (!isPrintable(character)) {
                nonPrintable++;
            }
        }

        double ratio = (double) nonPrintable / characters.length;
        return Math.rint(ratio * 1000) / 1000;
    }

    private static boolean isPrintable(int character) {
        if (character == ' ') {
            return true;
        }

        return switch (Character.getType(character)) {
            case Character.CONTROL, Character.FORMAT, Character.SURROGATE,
                    Character.PRIVATE_USE, Character.UNASSIGNED,
                    Character.SPACE_SEPARATOR, Character.LINE_SEPARATOR,
                    Character.PARAGRAPH_SEPARATOR -> false;
            default -> true;
        };
    }

    private static double calculateLengthZscore(int length) {
        if (GLOBAL_LENGTHS.size() < 10) {
            return 0.0;
        }

        double sum = 0.0;
        for (int value : GLOBAL_LENGTHS) {
            sum += value;
        }
        double mean = sum / GLOBAL_LENGTHS.size();

        double squaredDifferences = 0.0;
        for (int value : GLOBAL_LENGTHS) {
            double difference = value - mean;
            squaredDifferences += difference * difference;
        }

        double deviation = Math.sqrt(squaredDifferences / GLOBAL_LENGTHS.size());
        if (deviation == 0.0) {
            return 0.0;
        }

        double zscore = Math.abs(length - mean) / deviation;
        return Math.rint(zscore * 100) / 100;
    }
}