import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.vosk.Model;
import javax.sound.sampled.*;
import java.io.*;
import java.net.ConnectException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.Locale;
import java.util.UUID;

public final class VoiceInput implements AutoCloseable {
    public static final String VERSION = "5.1-TWO-PASS-COMMANDS";
    public enum Outcome { NO_SPEECH, UNUSABLE_TRANSCRIPTION, CONFIRM_COMMAND, TEXT }
    private static final int SAMPLE_RATE = 16000;
    private static final int FRAME_BYTES = 640;
    private static final AudioFormat FORMAT = new AudioFormat(SAMPLE_RATE, 16, 1, true, false);
    private static final URI INFERENCE = URI.create("http://127.0.0.1:8178/inference");
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3)).followRedirects(HttpClient.Redirect.NEVER).build();
    private final String language;
    private final LocalCommandDecoder commandDecoder;
    private final WhisperCommandServer commandServer;
    private volatile Outcome lastOutcome = Outcome.NO_SPEECH;
    private String suggestedCommand = "";

    public VoiceInput(Path root) { this(root, null); }
    public VoiceInput(Path root, Model commandModel) {
        commandServer = new WhisperCommandServer(root);
        language = System.getProperty("sentinel.stt.language",
                System.getenv().getOrDefault("SENTINEL_STT_LANGUAGE", "en"))
                .strip().toLowerCase(Locale.ROOT);
        if (!language.equals("en") && !language.equals("fr") && !language.equals("auto")) {
            throw new IllegalArgumentException("STT language must be en, fr or auto.");
        }
        commandDecoder = commandModel != null && language.equals("en")
                ? new LocalCommandDecoder(commandModel) : null;
        System.out.println("[VOICE INPUT] Version: " + VERSION);
        System.out.println("[VOICE INPUT] Language: " + language);
        System.out.println("[VOICE INPUT] Local command check: " + (commandDecoder != null));
    }
    public Outcome lastOutcome() { return lastOutcome; }
    public String suggestedCommand() { return suggestedCommand; }
    private void resetResult() { lastOutcome = Outcome.NO_SPEECH; suggestedCommand = ""; }

    public String listen(int maximumSpeechSeconds) throws Exception {
        resetResult();
        byte[] wav = record(maximumSpeechSeconds);
        if (wav == null) return "";
        LocalCommandDecoder.Candidate local = commandDecoder == null
                ? new LocalCommandDecoder.Candidate("", 0) : commandDecoder.decode(wav);
        String raw = transcribe(wav);
        String canonical = language.equals("en") ? CommandPhrases.canonical(raw) : "";
        boolean unusable = !isUsable(raw);
        // Questions, negations and quoted instructions cannot be converted by
        // a constrained decoder into an executable imperative.
        if (language.equals("en") && canonical.isBlank()
                && CommandPhrases.protectedSpeech(raw)) {
            return plainText(raw);
        }
        if (!canonical.isBlank() && (!local.available() || canonical.equals(local.canonical()))) {
            return commandText(canonical);
        }
        boolean commandAttempt = language.equals("en") && CommandPhrases.looksLikeCommandAttempt(raw);
        boolean retry = language.equals("en")
                && (commandAttempt || unusable || local.available() || !canonical.isBlank());
        if (retry && commandServer.ensureReady()) {
            try {
                String alternative = transcribe(wav, WhisperCommandServer.INFERENCE, "SMALL");
                String secondCommand = CommandPhrases.canonical(alternative);
                if (secondCommand.isBlank() && CommandPhrases.protectedSpeech(alternative)) {
                    return plainText(alternative);
                }
                if (!secondCommand.isBlank()) {
                    if (secondCommand.equals(canonical)) return commandText(secondCommand);
                    if (canonical.isBlank() && commandAttempt && local.available()
                            && secondCommand.equals(local.canonical())) {
                        return commandText(secondCommand);
                    }
                    return propose(secondCommand, "Whisper Small proposes this command; confirmation required.");
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt(); throw error;
            } catch (IOException error) {
                System.err.println("[COMMAND RETRY] " + error.getMessage());
            }
        }
        if (!canonical.isBlank()) return propose(canonical, "Recognizers disagree.");
        if (local.available() && (unusable || commandAttempt)) {
            return propose(local.canonical(), "Local command differs from the Whisper text.");
        }
        if (unusable || commandAttempt) {
            lastOutcome = Outcome.UNUSABLE_TRANSCRIPTION;
            System.out.println("[STT REJECTED] Unusable or unresolved short command.");
            return "";
        }
        return plainText(raw);
    }
    private String commandText(String command) {
        lastOutcome = Outcome.TEXT;
        System.out.println("[COMMAND NORMALIZED] " + command);
        return command;
    }
    private String plainText(String text) {
        lastOutcome = isUsable(text) ? Outcome.TEXT : Outcome.UNUSABLE_TRANSCRIPTION;
        return lastOutcome == Outcome.TEXT ? text : "";
    }
    private String propose(String command, String reason) {
        suggestedCommand = command;
        lastOutcome = Outcome.CONFIRM_COMMAND;
        System.out.println("[COMMAND PROPOSAL] " + command + " / " + reason);
        return "";
    }
    /** Confirmation is transcribed without command substitution or proposals. */
    public String listenConfirmation(int maximumSpeechSeconds) throws Exception {
        resetResult();
        byte[] wav = record(maximumSpeechSeconds);
        if (wav == null) return "";
        String text = transcribe(wav);
        lastOutcome = isUsable(text) ? Outcome.TEXT : Outcome.UNUSABLE_TRANSCRIPTION;
        return lastOutcome == Outcome.TEXT ? text : "";
    }
    private String transcribe(byte[] wav) throws Exception {
        return transcribe(wav, INFERENCE, "BASE");
    }
    private String transcribe(byte[] wav, URI endpoint, String modelLabel) throws IOException, InterruptedException {
        String boundary = "SentinelBoundary" + UUID.randomUUID().toString().replace("-", "");
        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds("SMALL".equals(modelLabel) ? 45 : 180))
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(multipart(wav, boundary))).build();
        System.out.println("[VOICE] Transcribing with Whisper " + modelLabel + "; language=" + language);
        long started = System.nanoTime(); HttpResponse<String> response;
        try { response = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)); }
        catch (ConnectException error) {
            throw new IOException("Whisper server is unavailable at " + endpoint, error);
        } catch (InterruptedException error) { Thread.currentThread().interrupt(); throw error; }
        if (response.statusCode() != 200) {
            String diagnostic = response.body();
            if (diagnostic.length() > 1000) diagnostic = diagnostic.substring(0, 1000);
            throw new IOException("Whisper returned HTTP " + response.statusCode() + ": " + diagnostic);
        }
        JsonObject result;
        try { result = JsonParser.parseString(response.body()).getAsJsonObject(); }
        catch (RuntimeException error) { throw new IOException("Unexpected Whisper response format.", error); }
        JsonElement value = result.get("text");
        if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString()) {
            throw new IOException("Whisper response does not contain a text field.");
        }
        String text = value.getAsString().replace("\uFEFF", "")
                .replaceAll("[\\p{Cc}&&[^\\r\\n\\t]]", " ").replaceAll("\\s+", " ").strip();
        System.out.printf(Locale.ROOT, "[VOICE] Transcription time: %.2f seconds%n",
                (System.nanoTime() - started) / 1_000_000_000.0);
        System.out.println("[STT " + modelLabel + " TEXT] " + text);
        return text;
    }
    private static boolean isUsable(String text) {
        if (text == null || text.isBlank() || text.length() > 2000 || text.indexOf('\uFFFD') >= 0) return false;
        if (text.codePoints().noneMatch(Character::isLetterOrDigit)) return false;
        return !text.toLowerCase(Locale.ROOT).matches(
                "(?:\\[(?:blank_audio|blank audio|silence|music|inaudible|unintelligible|noise)\\]"
                + "|\\((?:silence|music|inaudible|unintelligible|noise)\\))");
    }
    private byte[] multipart(byte[] wav, String boundary) throws IOException {
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        writeField(body, boundary, "response_format", "json");
        writeField(body, boundary, "language", language);
        writeField(body, boundary, "temperature", "0.0");
        writeUtf8(body, "--" + boundary + "\r\nContent-Disposition: form-data; "
                + "name=\"file\"; filename=\"question.wav\"\r\nContent-Type: audio/wav\r\n\r\n");
        body.write(wav); writeUtf8(body, "\r\n--" + boundary + "--\r\n");
        return body.toByteArray();
    }
    private static void writeField(ByteArrayOutputStream body, String boundary,
                                   String name, String value) throws IOException {
        writeUtf8(body, "--" + boundary + "\r\nContent-Disposition: form-data; name=\""
                + name + "\"\r\n\r\n" + value + "\r\n");
    }
    private static void writeUtf8(ByteArrayOutputStream body, String text) throws IOException {
        body.write(text.getBytes(StandardCharsets.UTF_8));
    }
    private byte[] record(int maximumSpeechSeconds) throws Exception {
        if (maximumSpeechSeconds < 1 || maximumSpeechSeconds > 30) {
            throw new IllegalArgumentException("Maximum speech duration must be between 1 and 30 seconds.");
        }
        DataLine.Info info = new DataLine.Info(TargetDataLine.class, FORMAT);
        if (!AudioSystem.isLineSupported(info)) {
            throw new LineUnavailableException("The default microphone does not support 16 kHz mono.");
        }
        TargetDataLine microphone = (TargetDataLine) AudioSystem.getLine(info);
        ByteArrayOutputStream recording = new ByteArrayOutputStream();
        Deque<byte[]> preRoll = new ArrayDeque<>();
        boolean started = false;
        int waiting = 0, captured = 0, activeFrames = 0, silent = 0;
        double noiseFloor = 0.0002;
        try {
            microphone.open(FORMAT); microphone.start();
            System.out.println("[VOICE] LISTENING: speak now. Recording stops after a short pause.");
            while (true) {
                if (Thread.currentThread().isInterrupted()) throw new InterruptedException("Capture interrupted.");
                byte[] frame = new byte[FRAME_BYTES]; int received = 0;
                while (received < frame.length) {
                    int count = microphone.read(frame, received, frame.length - received);
                    if (count <= 0) throw new IOException("The microphone stopped providing audio.");
                    received += count;
                }
                double level = rms(frame);
                boolean active = level >= Math.max(0.0008, Math.min(0.01, noiseFloor * 3));
                if (!started) {
                    waiting++;
                    if (!active) {
                        noiseFloor = noiseFloor * 0.95 + level * 0.05;
                        preRoll.addLast(frame);
                        if (preRoll.size() > 10) preRoll.removeFirst();
                        if (waiting >= 150) { System.out.println("[VOICE] No speech detected."); return null; }
                        continue;
                    }
                    started = true;
                    for (byte[] previous : preRoll) recording.write(previous);
                    preRoll.clear(); System.out.println("[VOICE] Speech detected.");
                }
                recording.write(frame); captured++;
                if (active) { activeFrames++; silent = 0; } else silent++;
                if (silent >= 35) { System.out.println("[VOICE] End of speech detected."); break; }
                if (captured >= maximumSpeechSeconds * 50) {
                    System.out.println("[VOICE] Maximum recording duration reached."); break;
                }
            }
        } finally {
            if (microphone.isOpen()) { microphone.stop(); microphone.close(); }
        }
        if (activeFrames < 8) { System.out.println("[VOICE] Recording too short or unclear."); return null; }
        byte[] audio = recording.toByteArray();
        int useful = audio.length - Math.max(0, silent - 10) * FRAME_BYTES;
        if (useful < audio.length) audio = Arrays.copyOf(audio, Math.max(0, useful));
        double level = rms(audio); int peak = peak(audio);
        System.out.printf(Locale.ROOT, "[MIC] Duration: %.2f seconds | RMS: %.5f | Peak: %.3f%n",
                audio.length / 32000.0, level, peak / 32768.0);
        if (audio.length == 0 || level < 0.0005) return null;
        double gain = Math.min(12, 0.055 / level);
        if (peak > 0) gain = Math.min(gain, 28000.0 / peak);
        for (int i = 0; i + 1 < audio.length; i += 2) {
            int sample = (short) ((audio[i] & 255) | (audio[i + 1] << 8));
            int adjusted = Math.max(-32768, Math.min(32767, (int) Math.round(sample * gain)));
            audio[i] = (byte) adjusted; audio[i + 1] = (byte) (adjusted >> 8);
        }
        ByteArrayOutputStream wav = new ByteArrayOutputStream();
        try (AudioInputStream stream = new AudioInputStream(new ByteArrayInputStream(audio),
                FORMAT, audio.length / FORMAT.getFrameSize())) {
            AudioSystem.write(stream, AudioFileFormat.Type.WAVE, wav);
        }
        return wav.toByteArray();
    }
    private static double rms(byte[] audio) {
        if (audio.length < 2) return 0;
        double sum = 0;
        for (int i = 0; i + 1 < audio.length; i += 2) {
            int sample = (short) ((audio[i] & 255) | (audio[i + 1] << 8));
            sum += sample * (double) sample;
        }
        return Math.sqrt(sum / (audio.length / 2.0)) / 32768.0;
    }
    private static int peak(byte[] audio) {
        int peak = 0;
        for (int i = 0; i + 1 < audio.length; i += 2) {
            int sample = (short) ((audio[i] & 255) | (audio[i + 1] << 8));
            peak = Math.max(peak, Math.abs(sample));
        }
        return peak;
    }
    public static void main(String[] args) {
        int code = 0;
        try {
            try (VoiceInput input = new VoiceInput(Path.of("."))) {
                String text = input.listen(5);
                System.out.println(text.isBlank() ? "[VOICE] No usable speech." : "[YOU] " + text);
            }
        } catch (Exception error) { code = 1; System.err.println("[VOICE ERROR] " + error); }
        System.exit(code);
    }
    @Override public void close() { commandServer.close(); }
}
