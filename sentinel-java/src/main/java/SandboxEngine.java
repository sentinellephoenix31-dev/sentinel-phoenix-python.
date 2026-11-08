import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

public final class SandboxEngine {
    private static final Path HELPER = Path.of("/usr/local/sbin/phoenix-sandbox-helper");
    private static final Pattern SESSION_ID = Pattern.compile("[a-f0-9]{8,32}");

    private static final boolean LINUX = System.getProperty("os.name", "")
            .toLowerCase(Locale.ROOT)
            .startsWith("linux");

    public synchronized Map<String, Object> createSandbox(String sessionId) {
        validateSessionId(sessionId);

        Map<String, Object> result = emptySandbox();
        result.put("sandbox_name", "phoenix-" + sessionId);

        if (!LINUX) {
            result.put("sandbox_error", "UNSUPPORTED_PLATFORM");
            return result;
        }

        if (runHelper(Action.CHECK, sessionId).success()) {
            result.put("sandbox_active", true);
            result.put("sandbox_reused", true);
            return result;
        }

        if (Thread.currentThread().isInterrupted()) {
            result.put("sandbox_error", "INTERRUPTED");
            return result;
        }

        HelperResult created = runHelper(Action.CREATE, sessionId);
        if (!created.success()) {
            result.put("sandbox_error", created.error());
            return result;
        }

        String containerId = created.output();
        result.put("sandbox_active", true);
        result.put("sandbox_id", containerId.substring(0, Math.min(12, containerId.length())));
        return result;
    }

    public synchronized boolean sandboxExists(String sessionId) {
        validateSessionId(sessionId);
        return runHelper(Action.CHECK, sessionId).success();
    }

    public synchronized boolean destroySandbox(String sessionId) {
        validateSessionId(sessionId);
        return runHelper(Action.DESTROY, sessionId).success();
    }

    public static Map<String, Object> emptySandbox() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("sandbox_active", false);
        result.put("sandbox_name", null);
        result.put("sandbox_id", null);
        result.put("sandbox_reused", false);
        result.put("sandbox_network", "NONE");
        result.put("sandbox_read_only", true);
        result.put("sandbox_privileged", false);
        result.put("payload_execution", false);
        result.put("sandbox_error", null);
        return result;
    }

    private static HelperResult runHelper(Action action, String sessionId) {
        if (!LINUX) {
            return HelperResult.failure("UNSUPPORTED_PLATFORM");
        }
        if (!Files.isRegularFile(HELPER)) {
            return HelperResult.failure("HELPER_NOT_FOUND");
        }

        Path stdout = null;
        Path stderr = null;
        Process process = null;

        try {
            stdout = Files.createTempFile("phoenix-sandbox-", ".out");
            stderr = Files.createTempFile("phoenix-sandbox-", ".err");

            process = new ProcessBuilder(
                    "sudo", "-n", HELPER.toString(), action.command, sessionId
            )
                    .redirectOutput(stdout.toFile())
                    .redirectError(stderr.toFile())
                    .start();

            if (!process.waitFor(action.timeoutSeconds, TimeUnit.SECONDS)) {
                return HelperResult.failure("TIMEOUT");
            }

            if (process.exitValue() == 0) {
                return new HelperResult(true, Files.readString(stdout).strip(), null);
            }

            String error = Files.readString(stderr).strip();
            return HelperResult.failure(error.isEmpty()
                    ? "HELPER_EXIT_" + process.exitValue()
                    : error);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return HelperResult.failure("INTERRUPTED");
        } catch (IOException error) {
            return HelperResult.failure("HELPER_IO_ERROR: " + error.getMessage());
        } finally {
            if (process != null && process.isAlive()) {
                process.destroyForcibly();
            }
            deleteTemporaryFile(stdout);
            deleteTemporaryFile(stderr);
        }
    }

    private static void validateSessionId(String sessionId) {
        if (sessionId == null || !SESSION_ID.matcher(sessionId).matches()) {
            throw new IllegalArgumentException("Invalid sandbox session ID");
        }
    }

    private static void deleteTemporaryFile(Path path) {
        if (path != null) {
            try {
                Files.deleteIfExists(path);
            } catch (IOException ignored) {
                path.toFile().deleteOnExit();
            }
        }
    }

    private enum Action {
        CREATE("create", 20),
        CHECK("check", 10),
        DESTROY("destroy", 15);

        private final String command;
        private final int timeoutSeconds;

        Action(String command, int timeoutSeconds) {
            this.command = command;
            this.timeoutSeconds = timeoutSeconds;
        }
    }

    private record HelperResult(boolean success, String output, String error) {
        static HelperResult failure(String error) {
            return new HelperResult(false, "", error);
        }
    }
}