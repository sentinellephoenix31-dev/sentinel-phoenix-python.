import com.k2fsa.sherpa.onnx.GeneratedAudio;
import com.k2fsa.sherpa.onnx.OfflineTts;
import com.k2fsa.sherpa.onnx.OfflineTtsConfig;
import com.k2fsa.sherpa.onnx.OfflineTtsKokoroModelConfig;
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig;

import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.DataLine;
import javax.sound.sampled.SourceDataLine;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class KokoroVoice implements AutoCloseable {

    public record Result(boolean spoken, String reason) {
    }

    private record Clip(float[] samples, int sampleRate) {
    }

    private record Packet(Clip clip, String error, boolean end) {
    }

    private static final int CHUNK_LIMIT = 180;
    private static final int TEXT_LIMIT = 1400;

    private final Path directory;
    private final Object stateLock = new Object();

    // Native model access stays on this single thread.
    private final ExecutorService synthesis =
            Executors.newSingleThreadExecutor(task -> {
                Thread thread = new Thread(
                        task, "sentinel-heart-synthesis");
                thread.setDaemon(true);
                return thread;
            });

    // Playback runs separately so synthesis can prepare the next chunk.
    private final ExecutorService playback =
            Executors.newSingleThreadExecutor(task -> {
                Thread thread = new Thread(
                        task, "sentinel-heart-playback");
                thread.setDaemon(true);
                return thread;
            });

    // Accessed only by the synthesis thread.
    private OfflineTts engine;

    // Small bounded cache for short, frequently repeated phrases.
    private final Map<String, Clip> cache =
            new LinkedHashMap<>(16, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(
                        Map.Entry<String, Clip> eldest) {
                    return size() > 12;
                }
            };

    private SourceDataLine currentLine;
    private long generation;
    private boolean closed;

    private final CompletableFuture<Boolean> ready =
            new CompletableFuture<>();

    private static final class Job {
        final long ticket;
        final BlockingQueue<Packet> queue =
                new ArrayBlockingQueue<>(2);
        final AtomicBoolean aborted = new AtomicBoolean();
        final CompletableFuture<Result> result =
                new CompletableFuture<>();

        Job(long ticket) {
            this.ticket = ticket;
        }
    }

    public KokoroVoice(Path root) {
        directory = root.resolve(
                "models/tts/kokoro-multi-lang-v1_0"
        ).toAbsolutePath().normalize();

        // Load once and prepare the wake acknowledgement in advance.
        synthesis.execute(() -> {
            try {
                ensureEngine();
                generateClip("I'm listening.");
                ready.complete(true);

            } catch (Exception | LinkageError error) {
                System.err.println(
                        "[KOKORO] Warm-up failed: " + error);
                ready.complete(false);
            }
        });
    }

    public CompletableFuture<Boolean> warmUp() {
        return ready;
    }

    public CompletableFuture<Result> speak(String text) {
        return speak(text, null);
    }

    /*
     * beforePlayback runs on the playback thread, once, immediately
     * before the first audio chunk is written.
     *
     * JavaFX callers must marshal UI work to Platform.runLater.
     * This callback marks playback submission, not sample-accurate
     * output from the physical speaker.
     */
    public CompletableFuture<Result> speak(
            String text, Runnable beforePlayback) {

        String message = clean(text);

        if (message.isEmpty()) {
            return CompletableFuture.completedFuture(
                    new Result(false, "EMPTY_TEXT"));
        }

        synchronized (stateLock) {
            if (closed) {
                return CompletableFuture.completedFuture(
                        new Result(false, "CLOSED"));
            }

            long ticket = ++generation;
            stopAudioLocked();

            Job job = new Job(ticket);
            List<String> chunks = split(message);

            synthesis.execute(() -> produce(job, chunks));
            playback.execute(() -> consume(job, beforePlayback));

            return job.result;
        }
    }

    private static String clean(String text) {
        String value = text == null ? ""
                : text.replaceAll("\\p{Cntrl}", " ")
                        .replaceAll("\\s+", " ")
                        .strip();

        int points = value.codePointCount(0, value.length());

        if (points > TEXT_LIMIT) {
            value = value.substring(
                    0, value.offsetByCodePoints(0, TEXT_LIMIT));
        }

        return value;
    }

    private static List<String> split(String message) {
        List<String> chunks = new ArrayList<>();

        // Keep sentence boundaries where practical.
        for (String sentence :
                message.split("(?<=[.!?])\\s+")) {

            String remaining = sentence.strip();

            while (remaining.codePointCount(
                    0, remaining.length()) > CHUNK_LIMIT) {

                int limit = remaining.offsetByCodePoints(
                        0, CHUNK_LIMIT);

                int cut = remaining.lastIndexOf(' ', limit);

                if (cut < limit / 2) {
                    cut = limit;
                }

                String part = remaining.substring(0, cut).strip();

                if (!part.isEmpty()) {
                    chunks.add(part);
                }

                remaining = remaining.substring(cut).strip();
            }

            if (!remaining.isEmpty()) {
                chunks.add(remaining);
            }
        }

        return chunks;
    }

    private boolean cancelled(Job job) {
        if (job.aborted.get()) {
            return true;
        }

        synchronized (stateLock) {
            return closed || job.ticket != generation;
        }
    }

    private void send(Job job, Packet packet)
            throws InterruptedException {

        while (!cancelled(job)) {
            if (job.queue.offer(packet, 100, TimeUnit.MILLISECONDS)) {
                return;
            }
        }
    }

    private void produce(Job job, List<String> chunks) {
        try {
            if (cancelled(job)) {
                return;
            }

            ensureEngine();

            for (String chunk : chunks) {
                if (cancelled(job)) {
                    return;
                }

                Clip clip = generateClip(chunk);

                if (cancelled(job)) {
                    return;
                }

                send(job, new Packet(clip, null, false));
            }

            send(job, new Packet(null, null, true));

        } catch (Exception | LinkageError error) {
            if (!cancelled(job)) {
                System.err.println("[KOKORO] " + error);

                try {
                    send(job, new Packet(
                            null, "VOICE_ERROR", false));

                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    job.aborted.set(true);
                    job.result.complete(
                            new Result(false, "INTERRUPTED"));
                }
            }
        }
    }

    private void consume(Job job, Runnable beforePlayback) {
        boolean started = false;

        try {
            while (!cancelled(job)) {
                Packet packet =
                        job.queue.poll(100, TimeUnit.MILLISECONDS);

                if (packet == null) {
                    continue;
                }

                if (packet.error() != null) {
                    job.result.complete(
                            new Result(false, packet.error()));
                    return;
                }

                if (packet.end()) {
                    job.result.complete(
                            new Result(started,
                                    started ? "OK" : "EMPTY_AUDIO"));
                    return;
                }

                Clip clip = packet.clip();

                if (clip == null || clip.samples().length == 0) {
                    continue;
                }

                Runnable callback =
                        started ? null : beforePlayback;

                if (!playClip(job, clip, callback)) {
                    job.result.complete(
                            new Result(false, "CANCELLED"));
                    return;
                }

                started = true;
            }

            job.result.complete(
                    new Result(false, "CANCELLED"));

        } catch (Exception | LinkageError error) {
            boolean wasCancelled = cancelled(job);

            if (!wasCancelled) {
                System.err.println(
                        "[KOKORO PLAYBACK] " + error);
            }

            job.result.complete(new Result(
                    false,
                    wasCancelled ? "CANCELLED" : "PLAYBACK_ERROR"));

        } finally {
            job.aborted.set(true);
        }
    }

    private Clip generateClip(String text) {
        Clip cached = cache.get(text);

        if (cached != null) {
            return cached;
        }

        long started = System.nanoTime();

        GeneratedAudio audio = engine.generate(
                text, 3, 1.0f);

        float[] samples = audio.getSamples();

        Clip clip = new Clip(
                samples == null ? new float[0] : samples,
                audio.getSampleRate());

        System.out.printf(
                java.util.Locale.ROOT,
                "[KOKORO] Prepared %d characters in %.2f seconds%n",
                text.length(),
                (System.nanoTime() - started) / 1_000_000_000.0);

        // Keep memory bounded: cache only short utterances.
        if (text.length() <= 80
                && clip.samples().length > 0
                && clip.samples().length <= 250_000) {

            cache.put(text, clip);
        }

        return clip;
    }

    private boolean playClip(
            Job job, Clip clip, Runnable beforePlayback)
            throws Exception {

        if (cancelled(job)) {
            return false;
        }

        AudioFormat format = new AudioFormat(
                clip.sampleRate(), 16, 1, true, false);

        SourceDataLine line = (SourceDataLine)
                AudioSystem.getLine(
                        new DataLine.Info(
                                SourceDataLine.class, format));

        try {
            synchronized (stateLock) {
                if (closed || job.ticket != generation) {
                    return false;
                }

                line.open(format);
                currentLine = line;
                line.start();
            }

            if (cancelled(job)) {
                return false;
            }

            if (beforePlayback != null) {
                beforePlayback.run();
            }

            float[] samples = clip.samples();
            byte[] buffer = new byte[4096];

            for (int offset = 0; offset < samples.length;) {
                if (cancelled(job)) {
                    return false;
                }

                int count = Math.min(
                        buffer.length / 2,
                        samples.length - offset);

                for (int i = 0; i < count; i++) {
                    float sample = Math.max(
                            -1.0f,
                            Math.min(1.0f, samples[offset + i]));

                    int pcm = Math.round(sample * 32767);

                    buffer[i * 2] = (byte) pcm;
                    buffer[i * 2 + 1] = (byte) (pcm >> 8);
                }

                int bytes = count * 2;
                int written = 0;

                while (written < bytes) {
                    if (cancelled(job)) {
                        return false;
                    }

                    int amount = line.write(
                            buffer, written, bytes - written);

                    if (amount <= 0) {
                        throw new IllegalStateException(
                                "Audio output stopped accepting data.");
                    }

                    written += amount;
                }

                offset += count;
            }

            line.drain();
            return !cancelled(job);

        } finally {
            synchronized (stateLock) {
                if (currentLine == line) {
                    currentLine = null;
                }
            }

            line.close();
        }
    }

    private void ensureEngine() throws Exception {
        if (engine != null) {
            return;
        }

        for (String name : new String[]{
                "model.onnx",
                "voices.bin",
                "tokens.txt",
                "lexicon-us-en.txt"
        }) {
            Path file = directory.resolve(name);

            if (!Files.isRegularFile(file)
                    || Files.size(file) == 0) {
                throw new IllegalStateException(
                        "Missing or empty model file: " + file);
            }
        }

        Path phonemes = directory.resolve("espeak-ng-data");

        if (!Files.isDirectory(phonemes)) {
            throw new IllegalStateException(
                    "Missing phoneme data: " + phonemes);
        }

        System.out.println("[KOKORO] Loading Heart...");

        OfflineTtsKokoroModelConfig kokoro =
                OfflineTtsKokoroModelConfig.builder()
                        .setModel(directory.resolve(
                                "model.onnx").toString())
                        .setVoices(directory.resolve(
                                "voices.bin").toString())
                        .setTokens(directory.resolve(
                                "tokens.txt").toString())
                        .setLexicon(directory.resolve(
                                "lexicon-us-en.txt").toString())
                        .setDataDir(phonemes.toString())
                        .build();

        OfflineTtsModelConfig model =
                OfflineTtsModelConfig.builder()
                        .setKokoro(kokoro)
                        .setNumThreads(2)
                        .setProvider("cpu")
                        .setDebug(false)
                        .build();

        engine = new OfflineTts(
                OfflineTtsConfig.builder()
                        .setModel(model)
                        .build());

        System.out.println("[KOKORO] Heart ready.");
    }

    public void stopSpeech() {
        synchronized (stateLock) {
            generation++;
            stopAudioLocked();
        }
    }

    private void stopAudioLocked() {
        if (currentLine != null) {
            currentLine.stop();
            currentLine.flush();
            currentLine.close();
            currentLine = null;
        }
    }

    @Override
    public void close() {
        synchronized (stateLock) {
            if (closed) {
                return;
            }

            closed = true;
            generation++;
            stopAudioLocked();

            // Release only after pending native synthesis returns.
            synthesis.execute(() -> {
                cache.clear();

                if (engine != null) {
                    engine.release();
                    engine = null;
                }
            });

            synthesis.shutdown();
            playback.shutdown();
        }
    }

    public static void main(String[] args) {
        try (KokoroVoice voice = new KokoroVoice(Path.of("."))) {
            System.out.println(
                    "[TEST] Warm-up: " + voice.warmUp().join());

            System.out.println(
                    voice.speak("I'm listening.").join());

            System.out.println(
                    voice.speak(
                            "Hello, I am Sentinel Phoenix. "
                                    + "I can explain recorded incidents "
                                    + "while preparing the next part "
                                    + "of my response."
                    ).join());
        }
    }
}