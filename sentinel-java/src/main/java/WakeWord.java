import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import org.vosk.Model;
import org.vosk.Recognizer;

import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.DataLine;
import javax.sound.sampled.TargetDataLine;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

// ============================================================
// SENTINEL PHOENIX
// WAKE WORD — MICROPHONE TEST
//
// Local Vosk recognition.
// No command dispatch.
// No audio file saved.
// ============================================================

public final class WakeWord {

    private static final float SAMPLE_RATE = 16000.0f;

    private static final Pattern WAKE = Pattern.compile(
            "\\bhey\\s+(?:sentinel|sentinelle)\\b"
    );

    private WakeWord() {
    }

    public static boolean containsWakeWord(String text) {

        String normalized = text == null
                ? ""
                : text.toLowerCase(Locale.ROOT)
                      .replaceAll("[^a-z\\s]", " ")
                      .replaceAll("\\s+", " ")
                      .strip();

        return WAKE.matcher(normalized).find();
    }

    private static String recognizedText(
            String json,
            String field
    ) {
        try {
            JsonObject object = JsonParser.parseString(json)
                    .getAsJsonObject();

            JsonElement value = object.get(field);

            if (value == null || !value.isJsonPrimitive()) {
                return "";
            }

            return value.getAsString().strip();

        } catch (RuntimeException error) {
            return "";
        }
    }

    public static void main(String[] args) throws Exception {

        Path modelDirectory = Path.of(
                "models",
                "wake",
                "vosk-model-small-en-us-0.15"
        ).toAbsolutePath().normalize();

        if (!Files.isRegularFile(
                modelDirectory.resolve("am/final.mdl")
        )) {
            throw new IllegalStateException(
                    "Wake model not found: " + modelDirectory
            );
        }

        AudioFormat format = new AudioFormat(
                SAMPLE_RATE,
                16,
                1,
                true,
                false
        );

        DataLine.Info microphoneInfo = new DataLine.Info(
                TargetDataLine.class,
                format
        );

        if (!AudioSystem.isLineSupported(microphoneInfo)) {
            throw new IllegalStateException(
                    "No compatible default microphone was found. "
                            + "This test requires 16 kHz, "
                            + "16-bit mono PCM input."
            );
        }

        System.out.println("[WAKE] Loading local English model...");

        try (
                Model model = new Model(modelDirectory.toString());

                // General recognition first, so we can inspect
                // what the microphone actually recognizes.
                Recognizer recognizer =
                        new Recognizer(model, SAMPLE_RATE)
        ) {
            TargetDataLine microphone =
                    (TargetDataLine) AudioSystem.getLine(
                            microphoneInfo
                    );

            Thread shutdownHook = new Thread(
                    microphone::close,
                    "sentinel-microphone-shutdown"
            );

            Runtime.getRuntime().addShutdownHook(shutdownHook);

            boolean detected = false;

            try {
                microphone.open(format);
                microphone.start();

                System.out.println();
                System.out.println("[WAKE] MICROPHONE ONLINE");
                System.out.println(
                        "[WAKE] Say: Hey Sentinel"
                );
                System.out.println(
                        "[WAKE] Listening for up to 60 seconds."
                );
                System.out.println(
                        "[WAKE] Press Ctrl+C to stop."
                );

                byte[] buffer = new byte[4000];

                String previousText = "";

                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(60);

                while (System.nanoTime() < deadline
                        && microphone.isOpen()) {

                    int bytes = microphone.read(
                            buffer,
                            0,
                            buffer.length
                    );

                    if (bytes <= 0) {
                        break;
                    }

                    boolean completed =
                            recognizer.acceptWaveForm(
                                    buffer,
                                    bytes
                            );

                    String text = completed
                            ? recognizedText(
                                    recognizer.getResult(),
                                    "text"
                            )
                            : recognizedText(
                                    recognizer.getPartialResult(),
                                    "partial"
                            );

                    if (!text.isEmpty()
                            && !text.equals(previousText)) {

                        System.out.println(
                                "[HEARD] " + text
                        );

                        previousText = text;
                    }

                    if (containsWakeWord(text)) {

                        detected = true;

                        System.out.println();
                        System.out.println(
                                "[WAKE] HEY SENTINEL DETECTED"
                        );

                        System.out.println(
                                "[WAKE] Test passed. "
                                        + "No command was executed."
                        );

                        break;
                    }
                }

                if (!detected) {
                    System.out.println(
                            "[WAKE] No wake phrase detected "
                                    + "during this test."
                    );
                }

            } finally {
                microphone.stop();
                microphone.close();

                try {
                    Runtime.getRuntime().removeShutdownHook(
                            shutdownHook
                    );
                } catch (IllegalStateException ignored) {
                    // JVM shutdown is already in progress.
                }

                System.out.println(
                        "[WAKE] MICROPHONE CLOSED"
                );
            }
        }
    }
}