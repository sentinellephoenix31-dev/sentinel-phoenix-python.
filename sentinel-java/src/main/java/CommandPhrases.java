import java.text.Normalizer;
import java.util.*;

/** Exact command aliases only. This class never executes an action. */
public final class CommandPhrases {
    private static final Map<String, String> ALIASES = new LinkedHashMap<>();
    static {
        add("Close yourself.", "close yourself", "close your self", "hide yourself",
                "hide the orb", "close the orb", "go away", "clothes yourself");
        add("Come back.", "come back", "show yourself", "show the orb", "open the orb",
                "open yourself", "open your self", "open myself", "open my self", "show myself");
        add("Open the camera.", "open the camera", "open camera", "start the camera",
                "start camera", "turn on the camera", "open the webcam");
        add("Close the camera.", "close the camera", "close camera", "stop the camera",
                "turn off the camera", "close the webcam");
        add("Close the globe.", "close the globe", "close globe", "close the glove",
                "close glove", "close the incident globe", "close the replay");
        add("Open the globe.", "open the globe", "open globe", "open the glove", "open glove");
        add("Stop narration.", "stop narration", "stop the narration", "pause narration",
                "stop the globe narration", "stop the replay audio");
        add("Resume narration.", "resume narration", "resume the narration", "restart narration");
        add("Do you recognize me?", "do you recognize me", "do you recognise me", "recognize me",
                "who do you see", "see my face");
        add("Remember my face.", "remember my face", "save my face");
        add("Forget my face.", "forget my face", "delete my face", "delete my face profile");
        add("That's all.", "that s all", "thats all", "that is all", "stop listening", "end conversation");
        add("Close the microphone.", "close the microphone", "turn off the microphone");
        for (String direction : List.of("left", "right", "up", "down")) {
            add("Move " + direction + ".", "move " + direction, "move to the " + direction,
                    "move a little " + direction);
        }
    }
    private CommandPhrases() {}
    private static void add(String canonical, String... aliases) {
        for (String alias : aliases) ALIASES.put(normalize(alias), canonical);
    }
    public static String normalize(String text) {
        return Normalizer.normalize(text == null ? "" : text, Normalizer.Form.NFKD)
                .replaceAll("\\p{M}+", "").toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9\\s]", " ").replaceAll("\\s+", " ").strip();
    }
    public static String canonical(String text) {
        String value = normalize(text)
                .replaceFirst("^(?:hey )?sentinel\\s+", "")
                .replaceFirst("^please\\s+", "")
                .replaceFirst("^(?:can|could|would|will) you\\s+", "")
                .replaceFirst("^please\\s+", "")
                .replaceFirst("\\s+please$", "").strip();
        return ALIASES.getOrDefault(value, "");
    }
    public static List<String> grammar() {
        LinkedHashSet<String> phrases = new LinkedHashSet<>();
        for (String alias : ALIASES.keySet()) {
            phrases.add(alias);
            phrases.add("please " + alias);
            phrases.add(alias + " please");
            phrases.add("can you " + alias);
            phrases.add("could you " + alias);
        }
        phrases.add("[unk]");
        return List.copyOf(phrases);
    }
    public static boolean looksLikeCommandAttempt(String text) {
        String value = normalize(text).replaceFirst("^please\\s+", "")
                .replaceFirst("^(?:can|could|would|will) you\\s+", "")
                .replaceFirst("^please\\s+", "");
        if (value.isBlank()) return true;
        if (value.split(" ").length > 7) return false;
        if (protectedSpeech(value)) return false;
        if (value.matches("^(?:i|we|they|he|she)\\b.*")) return false;
        return value.matches("^(?:please )?(?:close|closed|clothes|closing|open|opening|hide|show"
                + "|stop|start|turn|shut|resume|restart|move|come)\\b.*")
                || value.matches(".*\\b(?:yourself|your self|ourselves|our selves|camera|webcam|glove|globe|my face)$");
    }
    public static boolean protectedSpeech(String text) {
        String value = normalize(text).replaceFirst("^please\\s+", "")
                .replaceFirst("^(?:can|could|would|will) you\\s+", "")
                .replaceFirst("^please\\s+", "");
        return value.matches(".*\\b(?:don t|dont|do not|never|not|no|ne|pas)\\b.*")
                || value.matches("^(?:remember that|remember this|forget memory|delete memory"
                    + "|forget all personal memories|delete all personal memories)\\b.*")
                || value.matches("^(?:why|how|what|when|where|who|explain|tell|do|does|did|is|are|was|were|should"
                    + "|if|suppose|imagine|say|repeat|translate|spell|describe|whether|unless|because)\\b.*");
    }
}
