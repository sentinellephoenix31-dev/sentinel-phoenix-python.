import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;

/** Audio arbitration between VoiceAssistant and the incident globe. */
public final class AudioOwnership {
    private AudioOwnership() {}

    public static synchronized void claim(Path root, String owner) throws IOException {
        if (!owner.equals("ASSISTANT") && !owner.equals("REPLAY") && !owner.equals("IDLE")) {
            throw new IllegalArgumentException("Unsupported audio owner.");
        }
        Path file = root.toAbsolutePath().normalize().resolve("data/audio-owner.json");
        Files.createDirectories(file.getParent());
        JsonObject data = new JsonObject();
        data.addProperty("owner", owner);
        data.addProperty("process_id", ProcessHandle.current().pid());
        data.addProperty("updated_at", Instant.now().toString());
        Path temporary = Files.createTempFile(file.getParent(), "audio-owner-", ".tmp");
        try {
            Files.writeString(temporary, data.toString(), StandardCharsets.UTF_8);
            try {
                Files.move(temporary, file, StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException error) {
                Files.move(temporary, file, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    public static boolean assistantOwns(Path root) {
        Path file = root.toAbsolutePath().normalize().resolve("data/audio-owner.json");
        try {
            if (!Files.isRegularFile(file)) return false;
            JsonObject data = JsonParser.parseString(
                    Files.readString(file, StandardCharsets.UTF_8)).getAsJsonObject();
            if (!"ASSISTANT".equals(data.get("owner").getAsString())) return false;
            long pid = data.get("process_id").getAsLong();
            return ProcessHandle.of(pid).filter(ProcessHandle::isAlive).isPresent();
        } catch (Exception error) {
            // A replacement may briefly be unreadable; retry on the next poll.
            return false;
        }
    }
}
