import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/** Lazy, local-only Small server for a second pass over uncertain commands. */
public final class WhisperCommandServer implements AutoCloseable {
    public static final URI INFERENCE = URI.create("http://127.0.0.1:8179/inference");
    private final Path root;
    private final Path executable;
    private final Path model;
    private final Path state;
    private Process ownedProcess;
    private long retryAfter;

    public WhisperCommandServer(Path root) {
        this.root = root.toAbsolutePath().normalize();
        executable = this.root.resolve("tools/whisper-server.exe");
        model = this.root.resolve("models/stt/ggml-small.bin");
        state = this.root.resolve("data/whisper-command-server.json");
    }
    private static boolean portReady() {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress("127.0.0.1", 8179), 200); return true;
        } catch (IOException error) { return false; }
    }
    private boolean matchingServer() {
        try {
            if (!Files.isRegularFile(state)) return false;
            JsonObject data = JsonParser.parseString(
                    Files.readString(state, StandardCharsets.UTF_8)).getAsJsonObject();
            if (!model.toString().equals(data.get("model").getAsString())
                    || !executable.toString().equals(data.get("executable").getAsString())) return false;
            long pid = data.get("process_id").getAsLong();
            ProcessHandle process = ProcessHandle.of(pid).filter(ProcessHandle::isAlive).orElse(null);
            if (process == null) return false;
            String command = process.info().commandLine().orElse("").toLowerCase(Locale.ROOT);
            return command.contains("whisper-server") && command.contains("8179")
                    && command.contains(model.toString().toLowerCase(Locale.ROOT));
        } catch (Exception error) { return false; }
    }
    public synchronized boolean ensureReady() throws InterruptedException {
        if (System.nanoTime() < retryAfter) return false;
        try {
            if (ownedProcess != null && ownedProcess.isAlive() && portReady()) return true;
            if (portReady()) {
                if (matchingServer()) return true;
                throw new IOException("Port 8179 is occupied by an unverified service.");
            }
            if (!Files.isRegularFile(executable) || !Files.isRegularFile(model)
                    || Files.size(model) < 100_000_000) {
                throw new IOException("Whisper Small model or server executable is missing.");
            }
            Files.createDirectories(root.resolve("data"));
            System.out.println("[COMMAND RETRY] Loading Whisper Small on 127.0.0.1:8179...");
            ownedProcess = new ProcessBuilder(executable.toString(), "-m", model.toString(),
                    "--host", "127.0.0.1", "--port", "8179", "-l", "en", "-ng", "-t", "4")
                    .directory(root.toFile()).redirectErrorStream(true)
                    .redirectOutput(ProcessBuilder.Redirect.appendTo(
                            root.resolve("data/whisper-command-server.log").toFile())).start();
            JsonObject data = new JsonObject();
            data.addProperty("process_id", ownedProcess.pid());
            data.addProperty("model", model.toString());
            data.addProperty("executable", executable.toString());
            Path temporary = Files.createTempFile(state.getParent(), "command-server-", ".tmp");
            try {
                Files.writeString(temporary, data.toString(), StandardCharsets.UTF_8);
                try { Files.move(temporary, state, StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.ATOMIC_MOVE); }
                catch (AtomicMoveNotSupportedException error) {
                    Files.move(temporary, state, StandardCopyOption.REPLACE_EXISTING);
                }
            } finally { Files.deleteIfExists(temporary); }
            long deadline = System.nanoTime() + 30_000_000_000L;
            while (System.nanoTime() < deadline) {
                if (!ownedProcess.isAlive()) throw new IOException("Whisper Small exited during startup.");
                if (portReady()) return true;
                Thread.sleep(200);
            }
            throw new IOException("Whisper Small did not become ready in time.");
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt(); throw error;
        } catch (IOException | RuntimeException error) {
            System.err.println("[COMMAND RETRY] " + error.getMessage());
            retryAfter = System.nanoTime() + 60_000_000_000L;
            stopOwnedProcess(); return false;
        }
    }
    private void stopOwnedProcess() {
        Process process = ownedProcess; ownedProcess = null;
        if (process == null || !process.isAlive()) return;
        process.destroy();
        try {
            if (!process.waitFor(2, TimeUnit.SECONDS)) process.destroyForcibly();
        } catch (InterruptedException error) {
            process.destroyForcibly(); Thread.currentThread().interrupt();
        }
    }
    @Override public synchronized void close() { stopOwnedProcess(); }
}
