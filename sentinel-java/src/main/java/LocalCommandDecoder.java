import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.vosk.Model;
import org.vosk.Recognizer;
import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import java.io.ByteArrayInputStream;
import java.util.ArrayList;
import java.util.List;

/** Uses the already-loaded Vosk model, on the same recording as Whisper. */
public final class LocalCommandDecoder {
    public record Candidate(String canonical, double score) {
        public boolean available() { return !canonical.isBlank(); }
    }
    private final Model model;
    private final String grammar = new Gson().toJson(CommandPhrases.grammar());
    public LocalCommandDecoder(Model model) { this.model = model; }

    public Candidate decode(byte[] wav) {
        if (model == null) return new Candidate("", 0);
        try (AudioInputStream stream = AudioSystem.getAudioInputStream(new ByteArrayInputStream(wav))) {
            if (stream.getFormat().getSampleRate() != 16000
                    || stream.getFormat().getChannels() != 1
                    || stream.getFormat().getSampleSizeInBits() != 16
                    || stream.getFormat().isBigEndian()) return new Candidate("", 0);
            byte[] pcm = stream.readAllBytes();
            double seconds = pcm.length / 32000.0;
            if (seconds < 0.35 || seconds > 5.0) return new Candidate("", 0);
            List<JsonObject> segments = new ArrayList<>();
            try (Recognizer recognizer = new Recognizer(model, 16000, grammar)) {
                recognizer.setWords(true);
                for (int offset = 0; offset < pcm.length; offset += 4000) {
                    int length = Math.min(4000, pcm.length - offset);
                    byte[] part = java.util.Arrays.copyOfRange(pcm, offset, offset + length);
                    if (recognizer.acceptWaveForm(part, part.length)) {
                        segments.add(JsonParser.parseString(recognizer.getResult()).getAsJsonObject());
                    }
                }
                segments.add(JsonParser.parseString(recognizer.getFinalResult()).getAsJsonObject());
            }
            StringBuilder transcript = new StringBuilder();
            int words = 0; double sum = 0; double minimum = 1;
            for (JsonObject segment : segments) {
                if (segment.has("text")) transcript.append(segment.get("text").getAsString()).append(' ');
                JsonArray results = segment.getAsJsonArray("result");
                if (results == null) continue;
                for (JsonElement item : results) {
                    JsonObject word = item.getAsJsonObject();
                    if (!word.has("conf")) return new Candidate("", 0);
                    double confidence = word.get("conf").getAsDouble();
                    if (!Double.isFinite(confidence)) return new Candidate("", 0);
                    sum += confidence; minimum = Math.min(minimum, confidence); words++;
                }
            }
            String raw = transcript.toString().strip();
            if (raw.contains("[unk]") || words < 2) return new Candidate("", 0);
            String canonical = CommandPhrases.canonical(raw);
            double average = sum / words;
            // Heuristics, not calibrated probabilities of a correct command.
            if (canonical.isBlank() || minimum < 0.80 || average < 0.88) {
                return new Candidate("", 0);
            }
            return new Candidate(canonical, average);
        } catch (Exception | LinkageError error) {
            System.err.println("[COMMAND DECODER] " + error.getMessage());
            return new Candidate("", 0);
        }
    }
}
