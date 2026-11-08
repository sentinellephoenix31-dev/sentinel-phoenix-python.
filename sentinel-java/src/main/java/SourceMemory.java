import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class SourceMemory {
    private static final Gson JSON = new Gson();

    private static final DateTimeFormatter UTC_TIMESTAMP =
            DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSSSSSxxx");

    private final String databaseUrl;

    public SourceMemory(Path projectRoot) throws IOException, SQLException {
        Path dataDirectory = projectRoot.resolve("data").toAbsolutePath().normalize();
        Files.createDirectories(dataDirectory);
        databaseUrl = "jdbc:sqlite:" + dataDirectory.resolve("phoenix_memory.db");

        try (Connection connection = openConnection();
             Statement statement = connection.createStatement()) {
            statement.execute("PRAGMA journal_mode=WAL");

            statement.execute("""
                    CREATE TABLE IF NOT EXISTS source_profiles (
                        source_ip TEXT PRIMARY KEY,
                        first_seen TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        total_events INTEGER NOT NULL DEFAULT 0,
                        critical_events INTEGER NOT NULL DEFAULT 0,
                        containment_events INTEGER NOT NULL DEFAULT 0,
                        max_payload_score REAL NOT NULL DEFAULT 0,
                        max_behavior_score REAL NOT NULL DEFAULT 0,
                        max_anomaly_score REAL NOT NULL DEFAULT 0,
                        max_global_score REAL NOT NULL DEFAULT 0,
                        last_global_level TEXT,
                        last_policy_action TEXT,
                        last_decoy_session TEXT,
                        sandbox_seen INTEGER NOT NULL DEFAULT 0,
                        indicators_json TEXT NOT NULL DEFAULT '[]',
                        anomaly_reasons_json TEXT NOT NULL DEFAULT '[]'
                    )
                    """);

            statement.execute("""
                    CREATE TABLE IF NOT EXISTS observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        source_ip TEXT NOT NULL,
                        source_port INTEGER,
                        payload_hash TEXT,
                        payload_length INTEGER,
                        payload_score REAL,
                        behavior_score REAL,
                        anomaly_score REAL,
                        global_score REAL,
                        global_level TEXT,
                        policy_action TEXT,
                        containment_requested INTEGER,
                        decoy_session_id TEXT,
                        sandbox_active INTEGER,
                        indicators_json TEXT,
                        anomaly_reasons_json TEXT
                    )
                    """);

            statement.execute("""
                    CREATE INDEX IF NOT EXISTS idx_observations_source_ip
                    ON observations(source_ip)
                    """);

            statement.execute("""
                    CREATE INDEX IF NOT EXISTS idx_observations_timestamp
                    ON observations(timestamp)
                    """);
        }
    }

    public Map<String, Object> getSourceMemory(String sourceIp) throws SQLException {
        try (Connection connection = openConnection()) {
            return readProfile(connection, sourceIp);
        }
    }

    public void rememberEvent(
            String sourceIp,
            int sourcePort,
            String payload,
            Map<String, Object> analysis,
            Map<String, Object> behavior,
            Map<String, Object> anomaly,
            Map<String, Object> fusion,
            Map<String, Object> response,
            Map<String, Object> deception,
            Map<String, Object> sandbox
    ) throws SQLException {
        String timestamp = OffsetDateTime.now(ZoneOffset.UTC).format(UTC_TIMESTAMP);

        List<?> indicators = (List<?>) analysis.getOrDefault("indicators", List.of());
        List<?> anomalyReasons = (List<?>) anomaly.getOrDefault("anomaly_reasons", List.of());

        double payloadScore = readScore(analysis, "score");
        double behaviorScore = readScore(behavior, "behavior_score");
        double anomalyScore = readScore(anomaly, "anomaly_score");
        double globalScore = readScore(fusion, "global_score");

        String globalLevel = (String) fusion.getOrDefault("global_level", "LOW");
        String policyAction = (String) response.getOrDefault("action", "OBSERVE");
        String decoySession = (String) deception.get("decoy_session_id");

        int critical = "CRITICAL".equalsIgnoreCase(globalLevel) ? 1 : 0;
        int contained = Boolean.TRUE.equals(response.get("containment_requested")) ? 1 : 0;
        int sandboxActive = Boolean.TRUE.equals(sandbox.get("sandbox_active")) ? 1 : 0;

        try (Connection connection = openConnection()) {
            connection.setAutoCommit(false);

            try {
                executeUpdate(connection, """
                        INSERT INTO observations (
                            timestamp, source_ip, source_port, payload_hash, payload_length,
                            payload_score, behavior_score, anomaly_score, global_score,
                            global_level, policy_action, containment_requested,
                            decoy_session_id, sandbox_active, indicators_json, anomaly_reasons_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        timestamp, sourceIp, sourcePort, payloadHash(payload),
                        payload.codePointCount(0, payload.length()),
                        payloadScore, behaviorScore, anomalyScore, globalScore,
                        globalLevel, policyAction, contained, decoySession, sandboxActive,
                        JSON.toJson(indicators), JSON.toJson(anomalyReasons));

                Map<String, Object> previous = readProfile(connection, sourceIp);

                List<?> profileIndicators = indicators;
                List<?> profileAnomalies = anomalyReasons;
                if (previous != null) {
                    profileIndicators = mergeUnique(
                            (List<?>) previous.get("indicators"), indicators
                    );
                    profileAnomalies = mergeUnique(
                            (List<?>) previous.get("anomaly_reasons"), anomalyReasons
                    );
                }

                executeUpdate(connection, """
                        INSERT INTO source_profiles (
                            source_ip, first_seen, last_seen, total_events,
                            critical_events, containment_events,
                            max_payload_score, max_behavior_score, max_anomaly_score,
                            max_global_score, last_global_level, last_policy_action,
                            last_decoy_session, sandbox_seen, indicators_json, anomaly_reasons_json
                        )
                        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source_ip) DO UPDATE SET
                            last_seen = excluded.last_seen,
                            total_events = source_profiles.total_events + 1,
                            critical_events = source_profiles.critical_events + excluded.critical_events,
                            containment_events = source_profiles.containment_events
                                + excluded.containment_events,
                            max_payload_score = MAX(source_profiles.max_payload_score,
                                excluded.max_payload_score),
                            max_behavior_score = MAX(source_profiles.max_behavior_score,
                                excluded.max_behavior_score),
                            max_anomaly_score = MAX(source_profiles.max_anomaly_score,
                                excluded.max_anomaly_score),
                            max_global_score = MAX(source_profiles.max_global_score,
                                excluded.max_global_score),
                            last_global_level = excluded.last_global_level,
                            last_policy_action = excluded.last_policy_action,
                            last_decoy_session = COALESCE(excluded.last_decoy_session,
                                source_profiles.last_decoy_session),
                            sandbox_seen = MAX(source_profiles.sandbox_seen, excluded.sandbox_seen),
                            indicators_json = excluded.indicators_json,
                            anomaly_reasons_json = excluded.anomaly_reasons_json
                        """,
                        sourceIp, timestamp, timestamp, critical, contained,
                        payloadScore, behaviorScore, anomalyScore, globalScore,
                        globalLevel, policyAction, decoySession, sandboxActive,
                        JSON.toJson(profileIndicators), JSON.toJson(profileAnomalies));

                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }

    public Map<String, Long> getMemoryStats() throws SQLException {
        try (Connection connection = openConnection();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("""
                     SELECT
                         (SELECT COUNT(*) FROM source_profiles) AS known_sources,
                         (SELECT COUNT(*) FROM observations) AS observations,
                         (SELECT COUNT(*) FROM source_profiles
                             WHERE critical_events > 0) AS critical_sources,
                         (SELECT COUNT(*) FROM source_profiles
                             WHERE containment_events > 0) AS contained_sources
                     """)) {
            result.next();
            return Map.of(
                    "known_sources", result.getLong("known_sources"),
                    "observations", result.getLong("observations"),
                    "critical_sources", result.getLong("critical_sources"),
                    "contained_sources", result.getLong("contained_sources")
            );
        }
    }

    private Connection openConnection() throws SQLException {
        Connection connection = DriverManager.getConnection(databaseUrl);
        try {
            try (Statement statement = connection.createStatement()) {
                statement.execute("PRAGMA busy_timeout=10000");
                statement.execute("PRAGMA synchronous=NORMAL");
            }
            return connection;
        } catch (SQLException error) {
            try {
                connection.close();
            } catch (SQLException closeError) {
                error.addSuppressed(closeError);
            }
            throw error;
        }
    }

    private static Map<String, Object> readProfile(Connection connection, String sourceIp)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT * FROM source_profiles WHERE source_ip = ?"
        )) {
            statement.setString(1, sourceIp);

            try (ResultSet row = statement.executeQuery()) {
                if (!row.next()) {
                    return null;
                }

                Map<String, Object> profile = new LinkedHashMap<>();
                ResultSetMetaData columns = row.getMetaData();
                for (int index = 1; index <= columns.getColumnCount(); index++) {
                    profile.put(columns.getColumnLabel(index), row.getObject(index));
                }

                profile.put("indicators", readJsonList((String) profile.remove("indicators_json")));
                profile.put("anomaly_reasons",
                        readJsonList((String) profile.remove("anomaly_reasons_json")));
                profile.put("sandbox_seen", row.getInt("sandbox_seen") != 0);
                return profile;
            }
        }
    }

    private static void executeUpdate(Connection connection, String sql, Object... values)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            for (int index = 0; index < values.length; index++) {
                statement.setObject(index + 1, values[index]);
            }
            statement.executeUpdate();
        }
    }

    private static double readScore(Map<String, Object> engine, String key) {
        return ((Number) engine.getOrDefault(key, 0)).doubleValue();
    }

    private static String payloadHash(String payload) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(payload.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 indisponible", error);
        }
    }

    private static List<Object> readJsonList(String value) {
        if (value == null || value.isBlank()) {
            return List.of();
        }

        try {
            JsonElement parsed = JsonParser.parseString(value);
            if (parsed.isJsonArray()) {
                return JSON.fromJson(parsed, List.class);
            }
        } catch (JsonParseException ignored) {
            return List.of();
        }

        return List.of();
    }

    private static List<String> mergeUnique(List<?> previous, List<?> current) {
        Set<String> values = new LinkedHashSet<>();
        for (Object value : previous) {
            values.add(String.valueOf(value));
        }
        for (Object value : current) {
            values.add(String.valueOf(value));
        }
        return new ArrayList<>(values);
    }
}