import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.UUID;

public final class GlobeControl {
    private static final Path ROOT = Path.of(".").toAbsolutePath().normalize();
    private static final Path STATE = ROOT.resolve("data/globe-state.json");
    private static final Path COMMAND = ROOT.resolve("data/globe-command.json");
    private static final Path ACK = ROOT.resolve("data/globe-ack.json");
    private GlobeControl() {}
    public record Result(boolean confirmed, String status) {}
    private static boolean live(JsonObject state) {
        try {
            return state != null && "OPEN".equals(text(state, "status"))
                    && ProcessHandle.of(state.get("process_id").getAsLong())
                            .filter(ProcessHandle::isAlive).isPresent();
        } catch (Exception error) { return false; }
    }
    public static JsonObject findOpenState() {
        JsonObject state = read(STATE);
        try {
            if (!live(state) || text(state, "instance_id").isBlank()) return null;
            long age = java.time.Duration.between(
                    Instant.parse(text(state, "updated_at")), Instant.now()).toMillis();
            return age >= -1000 && age <= 5000 ? state : null;
        } catch (Exception error) { return null; }
    }
    public static Result send(String action) throws IOException, InterruptedException {
        if (!action.equals("CLOSE") && !action.equals("STOP_NARRATION")
                && !action.equals("RESUME_NARRATION")) return new Result(false, "UNSUPPORTED");
        JsonObject state = findOpenState();
        if (state == null) {
            return new Result(false, live(read(STATE)) ? "UNRESPONSIVE" : "NOT_RUNNING");
        }
        String instance = text(state, "instance_id");
        String id = UUID.randomUUID().toString();
        JsonObject request = new JsonObject();
        request.addProperty("id", id); request.addProperty("target_instance", instance);
        request.addProperty("action", action);
        request.addProperty("created_at", Instant.now().toString());
        publish(COMMAND, request);
        System.out.println("[GLOBE COMMAND] " + action);
        long deadline = System.nanoTime() + 5_000_000_000L;
        while (System.nanoTime() < deadline) {
            JsonObject ack = read(ACK);
            if (ack != null && id.equals(text(ack, "id"))
                    && instance.equals(text(ack, "instance_id"))
                    && action.equals(text(ack, "action"))) {
                String status = text(ack, "status");
                boolean confirmed = "COMPLETED".equals(status)
                        || ("RESUME_NARRATION".equals(action) && "ACCEPTED".equals(status));
                System.out.println("[GLOBE RESULT] " + action + ": " + status);
                return new Result(confirmed, status);
            }
            try { Thread.sleep(40); }
            catch (InterruptedException error) { Thread.currentThread().interrupt(); throw error; }
        }
        return new Result(false, "TIMEOUT");
    }
    private static JsonObject read(Path file) {
        try {
            return Files.isRegularFile(file) ? JsonParser.parseString(
                    Files.readString(file, StandardCharsets.UTF_8)).getAsJsonObject() : null;
        } catch (Exception error) { return null; }
    }
    private static String text(JsonObject object, String key) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString() : "";
    }
    private static void publish(Path destination, JsonObject data) throws IOException {
        Files.createDirectories(destination.getParent());
        Path temporary = Files.createTempFile(destination.getParent(), "globe-command-", ".tmp");
        try {
            Files.writeString(temporary, data.toString(), StandardCharsets.UTF_8);
            try { Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException error) {
                Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally { Files.deleteIfExists(temporary); }
    }
}
