import java.io.File;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

// ============================================================
// SENTINEL PHOENIX
// LOCAL REPLAY NARRATION V1
//
// Fixed eSpeak NG executable and options.
// Text passed through standard input.
// No shell interpreter.
// ============================================================

public final class ReplayNarration implements AutoCloseable {

    private static final int MAX_TEXT_LENGTH = 1400;

    private final Object stateLock = new Object();
    private final Object speechLock = new Object();

    private Process currentProcess;
    private long generation;
    private boolean closed;

    public record Result(
            boolean spoken,
            String reason,
            String voice
    ) {
    }

    public static Path findExecutable() {

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT)
                .contains("win");

        String filename = windows
                ? "espeak-ng.exe"
                : "espeak-ng";

        List<Path> candidates = new ArrayList<>();

        String configured = System.getenv("SENTINEL_ESPEAK_PATH");

        if (configured != null && !configured.isBlank()) {
            candidates.add(Path.of(configured));
        }

        if (windows) {

            for (String variable : List.of(
                    "ProgramFiles",
                    "ProgramFiles(x86)",
                    "LOCALAPPDATA"
            )) {
                String folder = System.getenv(variable);

                if (folder == null || folder.isBlank()) {
                    continue;
                }

                candidates.add(
                        Path.of(folder, "eSpeak NG", filename)
                );

                candidates.add(
                        Path.of(folder, "eSpeak NG", "bin", filename)
                );

                candidates.add(
                        Path.of(
                                folder,
                                "Programs",
                                "eSpeak NG",
                                filename
                        )
                );
            }
        }

        String searchPath = System.getenv("PATH");

        if (searchPath != null) {
            for (String folder : searchPath.split(
                    java.util.regex.Pattern.quote(File.pathSeparator)
            )) {
                if (!folder.isBlank()) {
                    try {
                        candidates.add(Path.of(folder, filename));
                    } catch (RuntimeException ignored) {
                    }
                }
            }
        }

        for (Path candidate : candidates) {
            if (Files.isRegularFile(candidate)) {
                return candidate.toAbsolutePath().normalize();
            }
        }

        return null;
    }

    // Blocking method: call from a worker, not the JavaFX thread.
    public Result speakText(String text) {

        String cleaned = text == null
                ? ""
                : text.replaceAll("\\p{Cntrl}", " ")
                      .replaceAll("\\s+", " ")
                      .strip();

        if (cleaned.isEmpty()) {
            return new Result(false, "EMPTY_TEXT", "en-us+f3");
        }

        int count = cleaned.codePointCount(0, cleaned.length());

        if (count > MAX_TEXT_LENGTH) {
            cleaned = cleaned.substring(
                    0,
                    cleaned.offsetByCodePoints(0, MAX_TEXT_LENGTH)
            );
        }

        Path executable = findExecutable();

        if (executable == null) {
            return new Result(
                    false,
                    "ESPEAK_NG_NOT_FOUND",
                    "en-us+f3"
            );
        }

        long ticket;

        synchronized (stateLock) {
            if (closed) {
                return new Result(false, "CLOSED", "en-us+f3");
            }

            ticket = generation;
        }

        // Serialize speech: this instance never overlaps voices.
        synchronized (speechLock) {

            Process process = null;

            try {
                synchronized (stateLock) {

                    if (closed || ticket != generation) {
                        return new Result(
                                false, "CANCELLED", "en-us+f3"
                        );
                    }

                    process = new ProcessBuilder(
                            executable.toString(),
                            "-v", "en-us+f3",
                            "-s", "155",
                            "-p", "48",
                            "-a", "100",
                            "-b", "1",
                            "--stdin"
                    )
                            .redirectOutput(
                                    ProcessBuilder.Redirect.DISCARD
                            )
                            .redirectError(
                                    ProcessBuilder.Redirect.DISCARD
                            )
                            .start();

                    currentProcess = process;
                }

                try (OutputStream input = process.getOutputStream()) {
                    input.write(
                            cleaned.getBytes(StandardCharsets.UTF_8)
                    );
                }

                if (!process.waitFor(120, TimeUnit.SECONDS)) {
                    process.destroyForcibly();

                    return new Result(
                            false, "TTS_TIMEOUT", "en-us+f3"
                    );
                }

                synchronized (stateLock) {
                    if (closed || ticket != generation) {
                        return new Result(
                                false, "CANCELLED", "en-us+f3"
                        );
                    }
                }

                return new Result(
                        process.exitValue() == 0,
                        process.exitValue() == 0
                                ? "OK"
                                : "TTS_FAILED",
                        "en-us+f3"
                );

            } catch (InterruptedException error) {

                Thread.currentThread().interrupt();

                return new Result(
                        false, "INTERRUPTED", "en-us+f3"
                );

            } catch (Exception error) {

                System.err.println(
                        "[NARRATION] " + error.getMessage()
                );

                return new Result(
                        false, "TTS_FAILED", "en-us+f3"
                );

            } finally {

                if (process != null && process.isAlive()) {
                    process.destroyForcibly();
                }

                synchronized (stateLock) {
                    if (currentProcess == process) {
                        currentProcess = null;
                    }
                }
            }
        }
    }

    public void stopSpeech() {

        synchronized (stateLock) {
            generation++;

            if (currentProcess != null) {
                currentProcess.destroyForcibly();
            }
        }
    }

    public static String buildNarration(GlobeEvent event) {

        if (event == null) {
            return "No recorded incident is selected.";
        }

        String ip = event.sourceIp().replace(".", " dot ");

        String score = event.score() == null
                ? "The global risk score was not recorded. "
                : "The global risk score is "
                    + event.score() + " out of 100. ";

        return "Recorded security event. "
                + "Source I P address " + ip + ". "
                + "Risk level " + event.level() + ". "
                + score
                + (event.local()
                    ? "The source is on a local or private network. "
                    : "Physical attribution is not established. ")
                + "The recorded policy action is "
                + event.action().replace('_', ' ') + ". "
                + "A policy decision alone does not confirm "
                + "that network traffic was blocked.";
    }

    @Override
    public void close() {
        synchronized (stateLock) {
            closed = true;
        }

        stopSpeech();
    }

    public static void main(String[] args) {

        Path executable = findExecutable();

        System.out.println(
                "[NARRATION] Executable: "
                        + (executable == null
                            ? "NOT FOUND"
                            : executable)
        );

        if (executable == null) {
            System.out.println(
                    "[NARRATION] Install eSpeak NG, "
                            + "then run this test again."
            );
            return;
        }

        try (ReplayNarration narration = new ReplayNarration()) {

            Result result = narration.speakText(
                    "Sentinel Phoenix narration is online. "
                            + "I can explain recorded security incidents."
            );

            System.out.println("[NARRATION] " + result.reason());
            System.out.println("[VOICE] " + result.voice());
        }
    }
}