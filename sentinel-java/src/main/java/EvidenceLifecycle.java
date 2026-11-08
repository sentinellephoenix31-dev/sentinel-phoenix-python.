import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class EvidenceLifecycle {
    public static final long TTL_SECONDS = 24 * 60 * 60;
    public static final int MAX_COUNT = 20;
    public static final long MAX_BYTES = 100L * 1024 * 1024;

    private static final Object LOCAL_LOCK = new Object();
    private static final Gson JSON = new GsonBuilder()
            .serializeNulls().setPrettyPrinting().create();

    private static final Set<String> EXTENSIONS =
            Set.of(".jpg", ".jpeg", ".png", ".webp");

    private final Path directory;
    private final Path indexFile;
    private final Path lockFile;

    public EvidenceLifecycle(Path projectRoot) throws IOException {
        Path requested = projectRoot.resolve("data/identity/evidence")
                .toAbsolutePath().normalize();
        Files.createDirectories(requested);
        directory = requested.toRealPath();
        indexFile = directory.resolve("evidence_index.json");
        lockFile = directory.resolve("evidence-java.lock");
    }

    public Path directory() {
        return directory;
    }

    public JsonObject registerEvidence(Path image) throws IOException {
        return registerEvidence(image, "UNKNOWN_PERSON", new JsonObject());
    }

    public JsonObject registerEvidence(
            Path image, String source, JsonObject metadata
    ) throws IOException {
        return withIndex(records -> register(records, image, source, metadata));
    }

    public List<JsonObject> discoverEvidence() throws IOException {
        return withIndex(this::discover);
    }

    public List<JsonObject> listEvidence() throws IOException {
        return withIndex(records -> {
            discover(records);
            return sortedRecords(records, true);
        });
    }

    public JsonObject getEvidence(String id) throws IOException {
        return withIndex(records -> {
            JsonObject record = record(records, id);
            if (record == null) {
                return result("NOT_FOUND");
            }

            Path image = imagePath(text(record, "filename"));
            if (image == null) {
                return result("DENIED", "reason", "UNSAFE_PATH");
            }

            JsonObject response = result("FOUND");
            response.add("record", record.deepCopy());
            response.addProperty("path", image.toString());
            response.addProperty("exists", isImageFile(image));
            return response;
        });
    }

    public JsonObject markPresented(String id) throws IOException {
        return withIndex(records -> {
            JsonObject record = record(records, id);
            if (record == null) {
                return result("NOT_FOUND");
            }
            record.addProperty("presented", true);
            record.addProperty("presented_at", nowSeconds());
            record.addProperty("state", flag(record, "kept") ? "KEPT" : "PRESENTED");
            return result("PRESENTED", "evidence_id", id);
        });
    }

    public JsonObject keepEvidence(String id) throws IOException {
        return withIndex(records -> {
            JsonObject record = record(records, id);
            if (record == null) {
                return result("NOT_FOUND");
            }
            record.addProperty("kept", true);
            record.addProperty("state", "KEPT");
            return result("KEPT", "evidence_id", id);
        });
    }

    public JsonObject releaseEvidence(String id) throws IOException {
        return withIndex(records -> {
            JsonObject record = record(records, id);
            if (record == null) {
                return result("NOT_FOUND");
            }
            record.addProperty("kept", false);
            record.addProperty("state", "TEMPORARY");
            return result("RELEASED", "evidence_id", id);
        });
    }

    public JsonObject deleteEvidence(String id) throws IOException {
        return withIndex(records -> delete(records, id, "OWNER_DELETE"));
    }

    public JsonObject acknowledgeEvidence(String id) throws IOException {
        return withIndex(records -> {
            JsonObject record = record(records, id);
            if (record == null) {
                return result("NOT_FOUND");
            }
            record.addProperty("acknowledged", true);
            record.addProperty("acknowledged_at", nowSeconds());
            record.addProperty("state", "ACKNOWLEDGED");

            if (!flag(record, "kept")) {
                return delete(records, id, "OWNER_ACKNOWLEDGED");
            }
            return result("ACKNOWLEDGED", "evidence_id", id);
        });
    }

    public JsonObject cleanupEvidence() throws IOException {
        return cleanupEvidence(TTL_SECONDS);
    }

    public JsonObject cleanupEvidence(long ttlSeconds) throws IOException {
        if (ttlSeconds < 0) {
            throw new IllegalArgumentException("TTL must be non-negative.");
        }

        return withIndex(records -> {
            discover(records);
            List<String> deleted = new ArrayList<>();
            List<String> expired = new ArrayList<>();
            double now = nowSeconds();

            for (JsonObject record : sortedRecords(records, false)) {
                if (!flag(record, "kept")
                        && now - number(record, "created_at", now) >= ttlSeconds) {
                    String id = text(record, "id");
                    if ("DELETED".equals(text(delete(records, id, "TTL_EXPIRED"), "status"))) {
                        expired.add(id);
                        deleted.add(id);
                    }
                }
            }

            for (JsonObject record : sortedRecords(records, false)) {
                if (records.size() <= MAX_COUNT) {
                    break;
                }
                if (!flag(record, "kept")) {
                    String id = text(record, "id");
                    if ("DELETED".equals(text(delete(records, id, "COUNT_LIMIT"), "status"))) {
                        deleted.add(id);
                    }
                }
            }

            for (JsonObject record : sortedRecords(records, false)) {
                if (storageBytes(records) <= MAX_BYTES) {
                    break;
                }
                if (!flag(record, "kept")) {
                    String id = text(record, "id");
                    if ("DELETED".equals(text(delete(records, id, "STORAGE_LIMIT"), "status"))) {
                        deleted.add(id);
                    }
                }
            }

            JsonObject response = result("CLEANUP_COMPLETE");
            response.add("expired", JSON.toJsonTree(expired));
            response.add("deleted", JSON.toJsonTree(deleted));
            response.addProperty("remaining", records.size());
            response.addProperty("storage_mb", megabytes(storageBytes(records)));
            response.addProperty("count_limit_exceeded", records.size() > MAX_COUNT);
            response.addProperty("storage_limit_exceeded", storageBytes(records) > MAX_BYTES);
            return response;
        });
    }

    public JsonObject evidenceStatus() throws IOException {
        return withIndex(records -> {
            discover(records);
            int kept = 0;
            for (JsonElement value : records.asMap().values()) {
                if (value.isJsonObject() && flag(value.getAsJsonObject(), "kept")) {
                    kept++;
                }
            }

            JsonObject response = result("ONLINE");
            response.addProperty("version", "1.0");
            response.addProperty("total", records.size());
            response.addProperty("temporary", records.size() - kept);
            response.addProperty("kept", kept);
            response.addProperty("storage_mb", megabytes(storageBytes(records)));

            JsonObject policy = new JsonObject();
            policy.addProperty("ttl_hours", 24);
            policy.addProperty("max_count", MAX_COUNT);
            policy.addProperty("max_storage_mb", 100);
            policy.addProperty("delete_on_acknowledge", true);
            response.add("policy", policy);
            return response;
        });
    }

    private List<JsonObject> discover(JsonObject records) throws IOException {
        List<JsonObject> results = new ArrayList<>();
        try (var files = Files.list(directory)) {
            for (Path path : files.sorted().toList()) {
                if (isImageFile(path) && supported(path.getFileName().toString())) {
                    results.add(register(records, path, "UNKNOWN_PERSON", new JsonObject()));
                }
            }
        }
        return results;
    }

    private JsonObject register(
            JsonObject records, Path image, String source, JsonObject metadata
    ) throws IOException {
        if (image == null) {
            return result("DENIED", "reason", "INVALID_EVIDENCE_PATH");
        }

        Path candidate = image.toAbsolutePath().normalize();
        if (!directory.equals(candidate.getParent())
                || imagePath(candidate.getFileName().toString()) == null) {
            return result("DENIED", "reason", "INVALID_EVIDENCE_PATH");
        }
        if (!isImageFile(candidate)) {
            return result("NOT_FOUND", "reason", "EVIDENCE_FILE_NOT_FOUND");
        }

        String filename = candidate.getFileName().toString();
        String id = evidenceId(filename);
        JsonObject existing = record(records, id);
        if (existing != null) {
            JsonObject response = result("ALREADY_REGISTERED", "evidence_id", id);
            response.add("record", existing.deepCopy());
            return response;
        }

        JsonObject record = new JsonObject();
        record.addProperty("id", id);
        record.addProperty("filename", filename);
        record.addProperty("created_at", nowSeconds());
        record.addProperty("created_at_iso", Instant.now().toString());
        record.addProperty("source", source);
        record.addProperty("state", "TEMPORARY");
        record.addProperty("kept", false);
        record.addProperty("presented", false);
        record.add("presented_at", null);
        record.addProperty("acknowledged", false);
        record.add("acknowledged_at", null);
        record.add("metadata", metadata == null ? new JsonObject() : metadata.deepCopy());
        records.add(id, record);

        JsonObject response = result("REGISTERED", "evidence_id", id);
        response.add("record", record.deepCopy());
        return response;
    }

    private JsonObject delete(JsonObject records, String id, String reason) throws IOException {
        JsonObject record = record(records, id);
        if (record == null) {
            return result("NOT_FOUND");
        }

        Path image = imagePath(text(record, "filename"));
        if (image == null) {
            return result("DENIED", "reason", "UNSAFE_PATH");
        }

        try {
            Files.deleteIfExists(image);
        } catch (IOException error) {
            return result("ERROR", "reason", error.getMessage());
        }

        records.remove(id);
        JsonObject response = result("DELETED", "evidence_id", id);
        response.addProperty("reason", reason);
        return response;
    }

    private Path imagePath(String filename) {
        if (filename.isBlank() || filename.contains("/") || filename.contains("\\")
                || filename.contains(":") || !supported(filename)) {
            return null;
        }

        Path path = directory.resolve(filename).normalize();
        if (!directory.equals(path.getParent()) || Files.isSymbolicLink(path)) {
            return null;
        }
        return path;
    }

    private static boolean isImageFile(Path path) {
        return Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS);
    }

    private static boolean supported(String filename) {
        int dot = filename.lastIndexOf('.');
        return dot >= 0 && EXTENSIONS.contains(filename.substring(dot).toLowerCase(Locale.ROOT));
    }

    private long storageBytes(JsonObject records) throws IOException {
        long total = 0;
        for (JsonObject record : sortedRecords(records, false)) {
            Path image = imagePath(text(record, "filename"));
            if (image != null && isImageFile(image)) {
                total += Files.size(image);
            }
        }
        return total;
    }

    private static List<JsonObject> sortedRecords(JsonObject records, boolean newestFirst) {
        List<JsonObject> result = new ArrayList<>();
        for (JsonElement value : records.asMap().values()) {
            if (value.isJsonObject()) {
                result.add(value.getAsJsonObject().deepCopy());
            }
        }

        Comparator<JsonObject> order =
                Comparator.comparingDouble(record -> number(record, "created_at", 0));
        result.sort(newestFirst ? order.reversed() : order);
        return result;
    }

    private <T> T withIndex(IndexAction<T> action) throws IOException {
        synchronized (LOCAL_LOCK) {
            try (FileChannel channel = FileChannel.open(
                    lockFile, StandardOpenOption.CREATE, StandardOpenOption.WRITE
            ); FileLock lock = channel.lock()) {
                JsonObject index = loadIndex();
                JsonObject records = index.getAsJsonObject("evidence");

                try {
                    return action.apply(records);
                } finally {
                    saveIndex(index);
                }
            }
        }
    }

    private JsonObject loadIndex() throws IOException {
        if (!Files.exists(indexFile)) {
            JsonObject index = new JsonObject();
            index.addProperty("version", "1.0");
            index.add("evidence", new JsonObject());
            return index;
        }

        try {
            JsonElement parsed = JsonParser.parseString(Files.readString(indexFile));
            if (parsed instanceof JsonObject index
                    && index.get("evidence") instanceof JsonObject) {
                return index;
            }
        } catch (JsonParseException error) {
            throw new IOException("Evidence index contains invalid JSON.", error);
        }
        throw new IOException("Evidence index has an invalid structure.");
    }

    private void saveIndex(JsonObject index) throws IOException {
        Path temporary = Files.createTempFile(directory, "evidence-index-", ".tmp");
        try {
            Files.writeString(temporary, JSON.toJson(index), StandardCharsets.UTF_8);
            try {
                Files.move(temporary, indexFile, StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException error) {
                Files.move(temporary, indexFile, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static JsonObject record(JsonObject records, String id) {
        if (id == null) {
            return null;
        }
        return records.get(id) instanceof JsonObject value ? value : null;
    }

    private static String evidenceId(String filename) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(filename.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest).substring(0, 16);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable.", error);
        }
    }

    private static JsonObject result(String status) {
        JsonObject result = new JsonObject();
        result.addProperty("status", status);
        return result;
    }

    private static JsonObject result(String status, String key, String value) {
        JsonObject result = result(status);
        result.addProperty(key, value);
        return result;
    }

    private static String text(JsonObject object, String key) {
        JsonElement value = object.get(key);
        return value != null && value.isJsonPrimitive() ? value.getAsString() : "";
    }

    private static boolean flag(JsonObject object, String key) {
        JsonElement value = object.get(key);
        return value != null && value.isJsonPrimitive() && value.getAsBoolean();
    }

    private static double number(JsonObject object, String key, double fallback) {
        try {
            JsonElement value = object.get(key);
            double number = value == null ? fallback : value.getAsDouble();
            return Double.isFinite(number) ? number : fallback;
        } catch (NumberFormatException | UnsupportedOperationException error) {
            return fallback;
        }
    }

    private static double nowSeconds() {
        return System.currentTimeMillis() / 1000.0;
    }

    private static double megabytes(long bytes) {
        return Math.round(bytes / (1024.0 * 1024) * 1000) / 1000.0;
    }

    @FunctionalInterface
    private interface IndexAction<T> {
        T apply(JsonObject records) throws IOException;
    }

    public static void main(String[] args) throws IOException {
        EvidenceLifecycle lifecycle = new EvidenceLifecycle(Path.of("."));
        System.out.println(JSON.toJson(lifecycle.evidenceStatus()));
    }
}