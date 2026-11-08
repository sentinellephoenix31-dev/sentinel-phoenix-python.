import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonParseException;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class LearningEngine {
    private static final String MODEL_VERSION = "2.0";
    private static final int MINIMUM_SAMPLES = 5;
    private static final int MINIMUM_CLASS_SAMPLES = 2;
    private static final int AUTO_RETRAIN_NEW_SAMPLES = 10;
    private static final int AUTO_RETRAIN_MIN_INTERVAL_SECONDS = 300;

    private static final Gson JSON = new GsonBuilder()
            .disableHtmlEscaping()
            .create();

    private static final Gson PRETTY_JSON = new GsonBuilder()
            .disableHtmlEscaping()
            .setPrettyPrinting()
            .create();

    private final Path dataDirectory;
    private final Path databaseFile;
    private final Path modelFile;
    private final Path historyFile;

    public LearningEngine(Path projectRoot) {
        dataDirectory = projectRoot.resolve("data").toAbsolutePath().normalize();
        databaseFile = dataDirectory.resolve("phoenix_memory.db");
        modelFile = dataDirectory.resolve("phoenix_learning.json");
        historyFile = dataDirectory.resolve("learning_history.jsonl");
    }

    public synchronized Map<String, Object> evaluateLearning(
            Map<String, Object> analysis,
            Map<String, Object> behavior,
            Map<String, Object> anomaly,
            Map<String, Object> reputation
    ) throws IOException, SQLException {
        Model model = loadOrTrain();
        Vector vector = new Vector(
                safeDouble(analysis.get("score"), 0),
                safeDouble(behavior.get("behavior_score"), 0),
                safeDouble(anomaly.get("anomaly_score"), 0)
        );
        double reputationScore = safeDouble(reputation.get("reputation_score"), 0);
        double fallback = clamp(vector.payload() * 0.40 + vector.behavior() * 0.35
                + vector.anomaly() * 0.25 + reputationScore * 0.10);

        List<String> reasons = new ArrayList<>();
        double score;
        double confidence;

        if ("READY".equals(model.status())) {
            if (hasSamples(model.normal_profile()) && hasSamples(model.dangerous_profile())) {
                double normal = distance(vector, model.normal_profile().centroid(),
                        model.global_scales());
                double dangerous = distance(vector, model.dangerous_profile().centroid(),
                        model.global_scales());
                double total = normal + dangerous;

                score = total <= 0 ? 50.0 : normal / total * 100;
                reasons.add("LEARNED_CLASS_PROXIMITY");
            } else {
                score = fallback;
                reasons.add("MODEL_PROFILE_FALLBACK");
            }

            score = clamp(score + Math.min(reputationScore * 0.10, 10));
            double sampleConfidence = Math.min(model.total_samples() * 2.0, 25);
            double balanceConfidence = qualityOf(model).class_balance() * 10;
            confidence = Math.min(60 + sampleConfidence + balanceConfidence, 95);
            reasons.add("TRAINED_MODEL_ACTIVE");
        } else {
            score = fallback;
            confidence = Math.min(35 + model.total_samples() * 4.0, 55);
            reasons.add("COLD_START_FALLBACK");
        }

        score = round(clamp(score), 100);
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

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("ml_score", score);
        result.put("ml_level", level);
        result.put("ml_confidence", (int) clamp(confidence));
        result.put("model_status", model.status());
        result.put("model_samples", model.total_samples());
        result.put("normal_samples", model.normal_samples());
        result.put("dangerous_samples", model.dangerous_samples());
        result.put("model_version", MODEL_VERSION);
        result.put("model_quality", qualityOf(model).asMap());
        result.put("learning_reasons", reasons);
        result.put("payload_execution", false);
        return result;
    }

    public synchronized Map<String, Object> getLearningStatus()
            throws IOException, SQLException {
        Model model = loadOrTrain();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", model.status());
        result.put("version", model.model_version());
        result.put("total_samples", model.total_samples());
        result.put("normal_samples", model.normal_samples());
        result.put("dangerous_samples", model.dangerous_samples());
        result.put("trained_at", model.trained_at());
        result.put("quality", qualityOf(model).asMap());
        return result;
    }

    public synchronized Map<String, Object> trainLearningModel(boolean save)
            throws IOException, SQLException {
        return asMap(train(save));
    }

    public synchronized Map<String, Object> maybeRetrainModel()
            throws IOException, SQLException {
        return maybeRetrainModel(false, AUTO_RETRAIN_NEW_SAMPLES,
                AUTO_RETRAIN_MIN_INTERVAL_SECONDS);
    }

    public synchronized Map<String, Object> maybeRetrainModel(
            boolean force, int minNewSamples, long minIntervalSeconds
    ) throws IOException, SQLException {
        List<TrainingRow> rows = loadTrainingRows();
        Model current = loadModel();

        if (current == null) {
            Model candidate = buildCandidate(rows);
            saveModel(candidate);
            logLearningEvent("MODEL_ACCEPTED", Map.of(
                    "reason", "NO_CURRENT_V2_MODEL",
                    "samples", rows.size(),
                    "status", candidate.status(),
                    "quality", candidate.quality()
            ));
            return updateResult(true, true, "NO_CURRENT_V2_MODEL",
                    0, rows.size(), candidate.status());
        }

        int oldSamples = current.total_samples();
        int newSamples = rows.size() - oldSamples;

        if (!force && newSamples < minNewSamples) {
            return updateResult(false, false, "NOT_ENOUGH_NEW_SAMPLES",
                    oldSamples, newSamples, current.status());
        }
        if (!force && retrainIntervalActive(current.trained_at(), minIntervalSeconds)) {
            return updateResult(false, false, "RETRAIN_INTERVAL_ACTIVE",
                    oldSamples, newSamples, current.status());
        }

        Model candidate = buildCandidate(rows);
        String rejection = rejectionReason(current, candidate);
        if (rejection != null) {
            logLearningEvent("MODEL_REJECTED", Map.of(
                    "reason", rejection,
                    "previous_samples", oldSamples,
                    "candidate_samples", rows.size(),
                    "candidate_quality", candidate.quality()
            ));
            return updateResult(true, false, rejection,
                    oldSamples, newSamples, current.status());
        }

        saveModel(candidate);
        logLearningEvent("MODEL_ACCEPTED", Map.of(
                "reason", "QUALITY_CHECK_PASSED",
                "previous_samples", oldSamples,
                "new_total", rows.size(),
                "quality", candidate.quality()
        ));
        return updateResult(true, true, "QUALITY_CHECK_PASSED",
                oldSamples, newSamples, candidate.status());
    }

    private Model loadOrTrain() throws IOException, SQLException {
        Model model = loadModel();
        return model == null ? train(true) : model;
    }

    private Model train(boolean save) throws IOException, SQLException {
        Model candidate = buildCandidate(loadTrainingRows());
        if (save) {
            saveModel(candidate);
            logLearningEvent("MODEL_TRAINED", Map.of(
                    "samples", candidate.total_samples(),
                    "normal", candidate.normal_samples(),
                    "dangerous", candidate.dangerous_samples(),
                    "status", candidate.status(),
                    "quality", candidate.quality()
            ));
        }
        return candidate;
    }

    private List<TrainingRow> loadTrainingRows() throws SQLException {
        List<TrainingRow> rows = new ArrayList<>();
        if (!Files.exists(databaseFile)) {
            return rows;
        }

        try (Connection connection = DriverManager.getConnection("jdbc:sqlite:" + databaseFile);
             Statement statement = connection.createStatement()) {
            statement.execute("PRAGMA busy_timeout=10000");

            try (ResultSet result = statement.executeQuery("""
                    SELECT payload_score, behavior_score, anomaly_score,
                           global_score, containment_requested
                    FROM observations
                    WHERE payload_score IS NOT NULL
                      AND behavior_score IS NOT NULL
                      AND anomaly_score IS NOT NULL
                      AND global_score IS NOT NULL
                    ORDER BY id ASC
                    """)) {
                while (result.next()) {
                    Vector vector = new Vector(
                            safeDouble(result.getObject(1), 0),
                            safeDouble(result.getObject(2), 0),
                            safeDouble(result.getObject(3), 0)
                    );
                    double globalScore = safeDouble(result.getObject(4), 0);

                    if (validScore(vector.payload()) && validScore(vector.behavior())
                            && validScore(vector.anomaly()) && validScore(globalScore)) {
                        rows.add(new TrainingRow(vector, globalScore, result.getInt(5) != 0));
                    }
                }
            }
        }
        return rows;
    }

    private static Model buildCandidate(List<TrainingRow> rows) {
        List<Vector> all = new ArrayList<>();
        List<Vector> normal = new ArrayList<>();
        List<Vector> dangerous = new ArrayList<>();

        for (TrainingRow row : rows) {
            all.add(row.vector());
            if (isDangerous(row)) {
                dangerous.add(row.vector());
            } else {
                normal.add(row.vector());
            }
        }

        Profile normalProfile = buildProfile(normal);
        Profile dangerousProfile = buildProfile(dangerous);
        Vector scales = spread(all, mean(all));
        boolean ready = rows.size() >= MINIMUM_SAMPLES
                && normal.size() >= MINIMUM_CLASS_SAMPLES
                && dangerous.size() >= MINIMUM_CLASS_SAMPLES;

        return new Model(
                MODEL_VERSION, utcNow(), ready ? "READY" : "COLD_START",
                rows.size(), normal.size(), dangerous.size(),
                MINIMUM_SAMPLES, MINIMUM_CLASS_SAMPLES, fingerprint(rows),
                normalProfile, dangerousProfile, rounded(scales),
                calculateQuality(normalProfile, dangerousProfile, scales)
        );
    }

    private static boolean isDangerous(TrainingRow row) {
        Vector vector = row.vector();
        return row.containment()
                || (vector.payload() >= 60 && vector.behavior() >= 60)
                || vector.anomaly() >= 70
                || (vector.payload() >= 70 && vector.behavior() >= 50);
    }

    private static Profile buildProfile(List<Vector> rows) {
        Vector center = mean(rows);
        return new Profile(rows.size(), rounded(center), rounded(spread(rows, center)));
    }

    private static Vector mean(List<Vector> rows) {
        if (rows.isEmpty()) {
            return new Vector(0, 0, 0);
        }

        double payload = 0;
        double behavior = 0;
        double anomaly = 0;
        for (Vector row : rows) {
            payload += row.payload();
            behavior += row.behavior();
            anomaly += row.anomaly();
        }
        return new Vector(payload / rows.size(), behavior / rows.size(), anomaly / rows.size());
    }

    private static Vector spread(List<Vector> rows, Vector mean) {
        if (rows.size() < 2) {
            return new Vector(1, 1, 1);
        }

        double payload = 0;
        double behavior = 0;
        double anomaly = 0;
        for (Vector row : rows) {
            payload += square(row.payload() - mean.payload());
            behavior += square(row.behavior() - mean.behavior());
            anomaly += square(row.anomaly() - mean.anomaly());
        }
        return new Vector(
                Math.max(Math.sqrt(payload / rows.size()), 1),
                Math.max(Math.sqrt(behavior / rows.size()), 1),
                Math.max(Math.sqrt(anomaly / rows.size()), 1)
        );
    }

    private static Quality calculateQuality(Profile normal, Profile dangerous, Vector scales) {
        if (!hasSamples(normal) || !hasSamples(dangerous)) {
            return new Quality(0, 0, 0);
        }

        double separation = distance(normal.centroid(), dangerous.centroid(), scales);
        double balance = (double) Math.min(normal.samples(), dangerous.samples())
                / Math.max(normal.samples(), dangerous.samples());
        return new Quality(round(separation, 10_000), round(balance, 10_000),
                round(Math.min(separation * 25 + balance * 25, 100), 100));
    }

    private static double distance(Vector vector, Vector center, Vector scales) {
        Vector scale = scales == null ? new Vector(1, 1, 1) : scales;
        return Math.sqrt(
                square((vector.payload() - center.payload()) / Math.max(scale.payload(), 1))
                + square((vector.behavior() - center.behavior()) / Math.max(scale.behavior(), 1))
                + square((vector.anomaly() - center.anomaly()) / Math.max(scale.anomaly(), 1))
        );
    }

    private static String rejectionReason(Model current, Model candidate) {
        if (!"READY".equals(current.status())) {
            return null;
        }
        if (!"READY".equals(candidate.status())) {
            return "READY_MODEL_WOULD_DEGRADE";
        }

        double previousSeparation = qualityOf(current).separation();
        if (previousSeparation > 0
                && candidate.quality().separation() < previousSeparation * 0.70) {
            return "MODEL_SEPARATION_DEGRADED";
        }
        return null;
    }

    private Model loadModel() {
        if (!Files.exists(modelFile)) {
            return null;
        }

        try {
            Model model = JSON.fromJson(Files.readString(modelFile), Model.class);
            if (model != null && MODEL_VERSION.equals(model.model_version())
                    && model.status() != null) {
                return model;
            }
        } catch (IOException | JsonParseException ignored) {
            // A fresh model can be built from the observations.
        }
        return null;
    }

    private void saveModel(Model model) throws IOException {
        Files.createDirectories(dataDirectory);
        Path temporary = Files.createTempFile(dataDirectory, "phoenix-learning-", ".tmp");
        try {
            Files.writeString(temporary, PRETTY_JSON.toJson(model), StandardCharsets.UTF_8);
            Files.move(temporary, modelFile, StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private void logLearningEvent(String event, Map<String, ?> details) throws IOException {
        Files.createDirectories(dataDirectory);
        String line = JSON.toJson(Map.of(
                "timestamp", utcNow(), "event", event, "details", details
        ));
        Files.writeString(historyFile, line + "\n", StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }

    private static String fingerprint(List<TrainingRow> rows) {
        List<List<Number>> values = new ArrayList<>();
        for (TrainingRow row : rows) {
            Vector vector = row.vector();
            values.add(List.of(vector.payload(), vector.behavior(), vector.anomaly(),
                    row.globalScore(), row.containment() ? 1 : 0));
        }

        try {
            byte[] bytes = JSON.toJson(values).getBytes(StandardCharsets.UTF_8);
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 indisponible", error);
        }
    }

    private static boolean retrainIntervalActive(String trainedAt, long minIntervalSeconds) {
        if (trainedAt == null || trainedAt.isBlank()) {
            return false;
        }
        try {
            Duration age = Duration.between(OffsetDateTime.parse(trainedAt),
                    OffsetDateTime.now(ZoneOffset.UTC));
            return age.compareTo(Duration.ofSeconds(minIntervalSeconds)) < 0;
        } catch (DateTimeParseException ignored) {
            return false;
        }
    }

    private static Map<String, Object> updateResult(
            boolean retrained, boolean accepted, String reason,
            int oldSamples, int newSamples, String status
    ) {
        return Map.of(
                "retrained", retrained, "accepted", accepted, "reason", reason,
                "old_samples", oldSamples, "new_samples", newSamples, "status", status
        );
    }

    private static Map<String, Object> asMap(Model model) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("model_version", model.model_version());
        result.put("trained_at", model.trained_at());
        result.put("status", model.status());
        result.put("total_samples", model.total_samples());
        result.put("normal_samples", model.normal_samples());
        result.put("dangerous_samples", model.dangerous_samples());
        result.put("minimum_samples", model.minimum_samples());
        result.put("minimum_class_samples", model.minimum_class_samples());
        result.put("dataset_fingerprint", model.dataset_fingerprint());
        result.put("normal_profile", model.normal_profile().asMap());
        result.put("dangerous_profile", model.dangerous_profile().asMap());
        result.put("global_scales", model.global_scales().asMap());
        result.put("quality", model.quality().asMap());
        return result;
    }

    private static boolean hasSamples(Profile profile) {
        return profile != null && profile.samples() > 0 && profile.centroid() != null;
    }

    private static Quality qualityOf(Model model) {
        return model.quality() == null ? new Quality(0, 0, 0) : model.quality();
    }

    private static Vector rounded(Vector vector) {
        return new Vector(round(vector.payload(), 10_000), round(vector.behavior(), 10_000),
                round(vector.anomaly(), 10_000));
    }

    private static double safeDouble(Object value, double fallback) {
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        if (value instanceof String text) {
            try {
                return Double.parseDouble(text);
            } catch (NumberFormatException ignored) {
                return fallback;
            }
        }
        return fallback;
    }

    private static boolean validScore(double score) {
        return score >= 0 && score <= 100;
    }

    private static double square(double value) {
        return value * value;
    }

    private static double clamp(double value) {
        return Math.max(0, Math.min(100, value));
    }

    private static double round(double value, int scale) {
        return Math.rint(value * scale) / scale;
    }

    private static String utcNow() {
        return OffsetDateTime.now(ZoneOffset.UTC).toString();
    }

    private record Vector(double payload, double behavior, double anomaly) {
        Map<String, Object> asMap() {
            return Map.of("payload", payload, "behavior", behavior, "anomaly", anomaly);
        }
    }

    private record TrainingRow(Vector vector, double globalScore, boolean containment) {
    }

    private record Profile(int samples, Vector centroid, Vector spread) {
        Map<String, Object> asMap() {
            return Map.of("samples", samples, "centroid", centroid.asMap(), "spread", spread.asMap());
        }
    }

    private record Quality(double separation, double class_balance, double quality_score) {
        Map<String, Object> asMap() {
            return Map.of("separation", separation, "class_balance", class_balance,
                    "quality_score", quality_score);
        }
    }

    private record Model(
            String model_version, String trained_at, String status,
            int total_samples, int normal_samples, int dangerous_samples,
            int minimum_samples, int minimum_class_samples, String dataset_fingerprint,
            Profile normal_profile, Profile dangerous_profile, Vector global_scales,
            Quality quality
    ) {
    }
}