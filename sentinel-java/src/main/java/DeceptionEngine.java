import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonParseException;
import com.google.gson.reflect.TypeToken;

import java.io.IOException;
import java.lang.reflect.Type;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;

public final class DeceptionEngine {
    private static final Gson JSON = new GsonBuilder()
            .serializeNulls()
            .disableHtmlEscaping()
            .create();

    private static final Gson PRETTY = JSON.newBuilder().setPrettyPrinting().create();
    private static final Type OBJECT_TYPE = new TypeToken<Map<String, Object>>() {}.getType();
    private static final SecureRandom RANDOM = new SecureRandom();

    private final Path directory;
    private final Path registryFile;

    public DeceptionEngine(Path root) {
        directory = root.resolve("data").resolve("decoys");
        registryFile = directory.resolve("registry.json");
    }

    public synchronized Map<String, Object> routeIfNeeded(
            String ip, int port, String payload,
            Map<String, Object> fusion, Map<String, Object> response
    ) throws IOException {
        Map<String, Object> registry = readObject(registryFile);
        String id = activeId(registry.get(ip));
        boolean reused = id != null;

        if (!reused && !Boolean.TRUE.equals(response.get("containment_requested"))) {
            return noDecoy();
        }
        if (!reused) {
            id = createDirectory();
        }

        Path sessionDir = directory.resolve(id);
        Path sessionFile = sessionDir.resolve("session.json");
        Map<String, Object> session = readObject(sessionFile);

        AdaptiveDeception.Interaction interaction;
        try {
            interaction = AdaptiveDeception.processInteraction(
                    sessionDir, id, ip, payload, fusion
            );
        } catch (IOException | RuntimeException error) {
            interaction = new AdaptiveDeception.Interaction(
                    truncate(payload, 512), "Temporary decoy service error.\n",
                    null, 1, 0, 0, false, null, error.toString()
            );
        }

        Instant now = Instant.now();
        session.put("session_id", id);
        session.put("source_ip", ip);
        session.put("source_port", port);
        if (!(session.get("created_at") instanceof Number)) {
            session.put("created_at", now.toEpochMilli() / 1000.0);
        }
        if (session.get("created_at_iso") == null || "".equals(session.get("created_at_iso"))) {
            session.put("created_at_iso", now.toString());
        }
        session.put("last_seen", now.toString());
        session.put("state", "ACTIVE");
        session.put("mode", "ADAPTIVE_DECEPTION");
        session.put("interactions", interaction.interactions());
        session.put("surface_profile", interaction.profileId());
        session.put("surface_generation", interaction.generation());
        session.put("surface_rotations", interaction.rotations());
        session.put("payload_execution", false);
        session.put("host_modified", false);
        writeObject(sessionFile, session);

        Map<String, Object> event = new LinkedHashMap<>();
        event.put("timestamp", now.toString());
        event.put("event", "DECOY_INTERACTION");
        event.put("source_ip", ip);
        event.put("source_port", port);
        event.put("command", truncate(interaction.command(), 512));
        event.put("response", truncate(interaction.response(), 4000));
        event.put("global_score", fusion.getOrDefault("global_score", 0));
        event.put("global_level", fusion.get("global_level"));
        event.put("policy_action", response.get("action"));
        event.put("surface_profile", interaction.profileId());
        event.put("surface_generation", interaction.generation());
        event.put("surface_rotated", interaction.rotated());
        event.put("surface_rotations", interaction.rotations());
        event.put("rotation_reason", interaction.rotationReason());
        event.put("executed", false);
        event.put("payload_execution", false);
        event.put("host_modified", false);

        if (interaction.error() != null) {
            event.put("deception_error", interaction.error());
        }

        Files.writeString(
                sessionDir.resolve("activity.jsonl"), JSON.toJson(event) + "\n",
                StandardOpenOption.CREATE, StandardOpenOption.APPEND
        );

        if (!reused) {
            registry.put(ip, id);
            writeObject(registryFile, registry);
        }

        Map<String, Object> result = noDecoy();
        result.put("decoy_active", true);
        result.put("decoy_session_id", id);
        result.put("decoy_path", sessionDir.toString());
        result.put("decoy_mode", "ADAPTIVE_TERMINAL");
        result.put("decoy_reused", reused);
        result.put("decoy_command", interaction.command());
        result.put("decoy_response", interaction.response());
        result.put("decoy_profile", interaction.profileId());
        result.put("surface_generation", interaction.generation());
        result.put("surface_rotated", interaction.rotated());
        result.put("surface_rotations", interaction.rotations());
        result.put("rotation_reason", interaction.rotationReason());
        return result;
    }

    public static Map<String, Object> noDecoy() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("decoy_active", false);
        result.put("decoy_session_id", null);
        result.put("decoy_path", null);
        result.put("decoy_mode", null);
        result.put("decoy_reused", false);
        result.put("decoy_command", null);
        result.put("decoy_response", null);
        result.put("decoy_profile", null);
        result.put("surface_generation", null);
        result.put("surface_rotated", false);
        result.put("surface_rotations", 0);
        result.put("rotation_reason", null);
        result.put("payload_execution", false);
        result.put("host_modified", false);
        return result;
    }

    private String activeId(Object value) throws IOException {
        if (!(value instanceof String id) || !id.matches("[0-9a-f]{16}")) {
            return null;
        }

        Path sessionDir = directory.resolve(id);
        if (!Files.isDirectory(sessionDir)) {
            return null;
        }

        String state = String.valueOf(
                readObject(sessionDir.resolve("session.json")).get("state")
        );
        if ("CLOSED".equalsIgnoreCase(state) || "DESTROYED".equalsIgnoreCase(state)) {
            return null;
        }
        return id;
    }

    private String createDirectory() throws IOException {
        Files.createDirectories(directory);
        byte[] randomBytes = new byte[8];

        while (true) {
            RANDOM.nextBytes(randomBytes);
            String id = HexFormat.of().formatHex(randomBytes);
            try {
                Files.createDirectory(directory.resolve(id));
                return id;
            } catch (FileAlreadyExistsException collision) {
                // Generate a new identifier.
            }
        }
    }

    static String truncate(String text, int maximum) {
        int length = Math.min(text.codePointCount(0, text.length()), maximum);
        return text.substring(0, text.offsetByCodePoints(0, length));
    }

    static Map<String, Object> readObject(Path path) throws IOException {
        if (!Files.isRegularFile(path)) {
            return new LinkedHashMap<>();
        }

        try {
            Map<String, Object> result = JSON.fromJson(Files.readString(path), OBJECT_TYPE);
            return result == null ? new LinkedHashMap<>() : result;
        } catch (JsonParseException error) {
            return new LinkedHashMap<>();
        }
    }

    static void writeObject(Path path, Map<String, Object> values) throws IOException {
        atomicWrite(path, PRETTY.toJson(values));
    }

    static void atomicWrite(Path path, String content) throws IOException {
        Path parent = path.getParent();
        Files.createDirectories(parent);
        Path temporary = Files.createTempFile(parent, ".decoy-", ".tmp");

        try {
            Files.writeString(temporary, content);
            try {
                Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException error) {
                Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}