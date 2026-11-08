import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.text.Normalizer;
import java.time.ZoneId;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class CommandDispatcher {

    public static final String VERSION = "2.1-GLOBE-CONTROL";

    private static Process replayProcess;

    private final BrainConversation brain;
    private final LocalBrain companion = new LocalBrain();

    private final Deque<LocalBrain.Message> companionHistory =
            new ArrayDeque<>();

    private final Deque<String> recentReplies =
            new ArrayDeque<>();

    private final Deque<String> recentFallbacks =
            new ArrayDeque<>();

    private String lastReplayQuery = "";
    private String previousDirection = "";

    private boolean playful = true;
    private long reactionRetryAfter;

    private static final Pattern MOVEMENT = Pattern.compile(
            "^(?:please )?"
                    + "(?:(?:can|could|would|will) you |try to |try and )?"
                    + "(?:please )?"
                    + "(?:move|go|float|slide|shift)"
                    + "(?: yourself)?"
                    + "(?: a little| a bit)?"
                    + "(?: to)?(?: the)? "
                    + "(left|right|up|down)"
                    + "(?: a little| a bit)?(?: please)?$");

    public CommandDispatcher(BrainConversation brain) {
        this.brain = Objects.requireNonNull(brain);
    }

    private static String normalize(String text) {
        return Normalizer.normalize(
                        text == null ? "" : text,
                        Normalizer.Form.NFKD)
                .replaceAll("\\p{M}+", "")
                .toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9\\s]", " ")
                .replaceAll("\\s+", " ")
                .strip();
    }

    private static String withoutName(String text) {
        return normalize(text).replaceFirst(
                "^(?:hey )?(?:sentinel|sentinelle)\\s+", "");
    }

    private static String requestText(String text) {
        return withoutName(text)
                .replaceFirst("^please\\s+", "")
                .replaceFirst(
                        "^(?:can|could|would|will) you\\s+", "")
                .replaceFirst("^please\\s+", "")
                .replaceFirst("\\s+please$", "")
                .strip();
    }

    private static String globeControlIntent(String question) {
        String request = requestText(question);

        if (request.matches(
                "(?:(?:close|hide|exit|shut down) "
                        + "(?:the )?(?:globe|incident globe|replay)"
                        + "|(?:ferme|cache) "
                        + "(?:le )?(?:globe|replay))")) {
            return "CLOSE";
        }

        if (request.matches(
                "(?:(?:stop|pause|mute) "
                        + "(?:the )?(?:(?:globe|replay) )?"
                        + "(?:narration|voice)"
                        + "|(?:stop|pause) "
                        + "(?:the )?(?:globe|replay) audio"
                        + "|(?:arrete|coupe|mets en pause) "
                        + "(?:la )?(?:narration|voix du globe))")) {
            return "STOP_NARRATION";
        }

        if (request.matches(
                "(?:(?:resume|restart|enable|start) "
                        + "(?:the )?(?:(?:globe|replay) )?narration"
                        + "|(?:reprends|relance|active) "
                        + "(?:la )?narration)")) {
            return "RESUME_NARRATION";
        }

        return "";
    }

    private static JsonObject baseResult(
            String route, String source) {

        JsonObject result = new JsonObject();

        result.addProperty("version", VERSION);
        result.addProperty("route", route);
        result.addProperty("language", "en");

        result.addProperty(
                "source",
                "voice".equalsIgnoreCase(source)
                        ? "voice" : "text");

        result.addProperty("continue", true);
        result.addProperty("handled", true);

        return result;
    }

    private static JsonObject companionAnswer(
            String response, String source) {

        JsonObject result = baseResult("ORB_COMPANION", source);
        result.addProperty("status", "ANSWERED");
        result.addProperty("response", response);

        return result;
    }

    private JsonObject controlGlobe(
            String action, String source) throws Exception {

        GlobeControl.Result control =
                GlobeControl.send(action);

        JsonObject result =
                baseResult("GLOBE_CONTROL", source);

        result.addProperty("globe_action", action);
        result.addProperty("globe_result", control.status());

        if (!control.confirmed()) {
            result.addProperty(
                    "status",
                    "NOT_RUNNING".equals(control.status())
                            ? "NOT_RUNNING" : "ERROR");

            result.addProperty(
                    "response",
                    "NOT_RUNNING".equals(control.status())
                            ? "I couldn't find an active globe."
                            : "The globe didn't confirm that command. "
                                + "You can use its on-screen controls.");

            return result;
        }

        if ("RESUME_NARRATION".equals(action)) {
            /*
             * Existing VoiceAssistant versions recognize this route/status
             * and leave speech to the globe instead of speaking over it.
             */
            result.addProperty(
                    "route", "VISUAL_INCIDENT_REPLAY");

            result.addProperty("status", "LAUNCHED");
            result.addProperty("operation", "RESUMED");
            result.addProperty("response", "");
            result.addProperty("audio_owner", "REPLAY");

            return result;
        }

        result.addProperty("status", "COMPLETED");

        result.addProperty(
                "response",
                "CLOSE".equals(action)
                        ? "The globe is closed."
                        : "Globe narration stopped. "
                            + "Automatic replay is paused.");

        return result;
    }

    private void rememberCompanion(
            String question, String response) {

        companionHistory.addLast(
                new LocalBrain.Message("user", question));

        companionHistory.addLast(
                new LocalBrain.Message("assistant", response));

        while (companionHistory.size() > 12) {
            companionHistory.removeFirst();
        }

        recentReplies.addLast(response);

        while (recentReplies.size() > 10) {
            recentReplies.removeFirst();
        }
    }

    private static Set<String> words(String text) {
        Set<String> words = new HashSet<>();

        for (String word : normalize(text).split(" ")) {
            if (!word.isBlank()) {
                words.add(word);
            }
        }

        return words;
    }

    private boolean tooSimilar(String candidate) {
        String normalized = normalize(candidate);
        Set<String> candidateWords = words(candidate);

        for (String previous : recentReplies) {
            if (normalized.equals(normalize(previous))) {
                return true;
            }

            Set<String> oldWords = words(previous);

            Set<String> intersection =
                    new HashSet<>(candidateWords);

            intersection.retainAll(oldWords);

            Set<String> union =
                    new HashSet<>(candidateWords);

            union.addAll(oldWords);

            if (candidateWords.size() >= 5
                    && oldWords.size() >= 5
                    && !union.isEmpty()
                    && intersection.size()
                        / (double) union.size() >= 0.65) {
                return true;
            }
        }

        return false;
    }

    private String chooseFallback(String... choices) {
        List<String> available = new ArrayList<>();

        for (String choice : choices) {
            if (!recentFallbacks.contains(choice)
                    && !tooSimilar(choice)) {
                available.add(choice);
            }
        }

        if (available.isEmpty()) {
            for (String choice : choices) {
                if (!recentFallbacks.contains(choice)) {
                    available.add(choice);
                }
            }
        }

        if (available.isEmpty()) {
            recentFallbacks.clear();
            available.addAll(List.of(choices));
        }

        String selected = available.get(
                ThreadLocalRandom.current()
                        .nextInt(available.size()));

        recentFallbacks.addLast(selected);

        while (recentFallbacks.size() > 6) {
            recentFallbacks.removeFirst();
        }

        return selected;
    }

    private static String cleanReaction(String text) {
        if (text == null) {
            return "";
        }

        String value = text.strip()
                .replaceFirst(
                        "(?i)^(?:sentinel(?: phoenix)?|assistant)\\s*:\\s*",
                        "")
                .replaceAll("\\s+", " ")
                .strip();

        if (value.length() >= 2
                && value.startsWith("\"")
                && value.endsWith("\"")) {
            value = value.substring(
                    1, value.length() - 1).strip();
        }

        if (value.isBlank()
                || value.length() > 240
                || value.split("\\s+").length > 40
                || value.contains("*")
                || value.contains("[")
                || value.contains("]")
                || value.contains("<")
                || value.contains(">")) {
            return "";
        }

        return value;
    }

    private JsonObject react(
            String question,
            String source,
            JsonObject event,
            boolean generate,
            String... fallbackChoices) {

        event.addProperty("playful", playful);

        String response = "";
        boolean generated = false;

        if (generate
                && System.nanoTime() >= reactionRetryAfter) {

            LocalBrain.Result answer =
                    companion.companionReaction(
                            question,
                            event,
                            new ArrayList<>(companionHistory),
                            new ArrayList<>(recentReplies));

            if (answer.ok()) {
                String candidate =
                        cleanReaction(answer.response());

                if (!candidate.isEmpty()
                        && !tooSimilar(candidate)) {
                    response = candidate;
                    generated = true;
                }

            } else {
                reactionRetryAfter =
                        System.nanoTime() + 30_000_000_000L;

                System.err.println(
                        "[COMPANION MODEL] " + answer.error());
            }
        }

        if (response.isEmpty()) {
            response = chooseFallback(fallbackChoices);
        }

        rememberCompanion(question, response);

        JsonObject result =
                companionAnswer(response, source);

        result.addProperty(
                "reaction_source",
                generated
                        ? "LOCAL_MODEL"
                        : "LOCAL_FALLBACK");

        return result;
    }

    private JsonObject companionRequest(
            String question, String source) throws Exception {

        String text = withoutName(question);

        if (text.matches(
                "(?:please )?(?:stop joking|be serious"
                        + "|no more jokes|seriously)(?: please)?")) {

            playful = false;

            JsonObject event = new JsonObject();
            event.addProperty("event", "STYLE_CHANGED");
            event.addProperty("style", "DIRECT");

            return react(
                    question, source, event, false,
                    "Understood. I'll keep it direct.",
                    "All right. No jokes.",
                    "Got it. Straight answers.",
                    "Okay. Let's keep it practical.");
        }

        if (text.matches(
                "(?:please )?(?:you can joke again|be playful"
                        + "|you can be playful again)(?: please)?")) {

            playful = true;

            JsonObject event = new JsonObject();
            event.addProperty("event", "STYLE_CHANGED");
            event.addProperty("style", "PLAYFUL");

            return react(
                    question, source, event, true,
                    "All right. A little mischief, then.",
                    "Noted. I'll leave room for a joke.",
                    "Okay, we can loosen up a little.",
                    "Good. Serious doesn't have to mean solemn.");
        }

        if (text.matches(
                "(?:no )*(?:you are|you re|you keep|you) "
                        + "(?:moving|move|floating)(?: around)?")) {

            JsonObject event = new JsonObject();

            event.addProperty("event", "MOVEMENT_COMMENT");
            event.addProperty(
                    "movement_observed_by_application", false);

            event.addProperty("action_executed", "NONE");

            return react(
                    question, source, event, true,
                    "I hear you. Which way would you like me to go?",
                    "Fair point. Where would you prefer me?",
                    "Tell me a direction and I'll try that.",
                    "We can choose a better spot. Left or right?");
        }

        String movementText = text.replaceFirst(
                "^(?:seriously|no really) ", "");

        Matcher movement = MOVEMENT.matcher(movementText);

        if (!movement.matches()) {
            return null;
        }

        boolean directThisTime =
                !movementText.equals(text);

        String direction = movement.group(1);
        String action =
                "MOVE_" + direction.toUpperCase(Locale.ROOT);

        String status = sendOrbAction(action);

        JsonObject event = new JsonObject();

        event.addProperty(
                "event",
                "COMPLETED".equals(status)
                        ? "MOVE_COMPLETED"
                        : "MOVE_NOT_COMPLETED");

        event.addProperty("action", action);
        event.addProperty("result", status);
        event.addProperty("direction", direction);
        event.addProperty(
                "previous_direction", previousDirection);

        JsonObject result;

        switch (status) {
            case "COMPLETED" -> {
                previousDirection = direction;

                if (!playful || directThisTime) {
                    result = react(
                            question, source, event, false,
                            "Moved " + direction + ".",
                            "Done - " + direction + ".",
                            "I've moved " + direction + ".",
                            "That move " + direction + " is complete.");

                } else {
                    result = react(
                            question, source, event, true,
                            "Moved " + direction + ".",
                            "A little " + direction + ", as requested.",
                            "Done. I've shifted " + direction + ".",
                            "I've moved " + direction + ".",
                            "That takes me a little further "
                                    + direction + ".");
                }
            }

            case "EDGE" -> result = react(
                    question, source, event, false,
                    "There's no room to move further " + direction + ".",
                    "I'm at the screen boundary in that direction.",
                    "That direction is limited by the screen edge.",
                    "I can't go further " + direction + " from here.");

            case "HIDDEN" -> result = react(
                    question, source, event, false,
                    "The orb is hidden. Say come back first.",
                    "Ask me to come back, then I can move.",
                    "I need to be visible before that movement.",
                    "Show the orb first, then try that direction.");

            case "CANCELLED" -> result = react(
                    question, source, event, false,
                    "That movement was cancelled.",
                    "The move didn't finish.",
                    "That move was interrupted.",
                    "I didn't complete that movement.");

            default -> {
                result = react(
                        question, source, event, false,
                        "I couldn't confirm that movement.",
                        "The orb didn't confirm the move.",
                        "I didn't receive a successful movement result.",
                        "That move hasn't been confirmed.");

                result.addProperty("status", "ERROR");
            }
        }

        result.addProperty("orb_action", action);
        result.addProperty("orb_result", status);

        return result;
    }

    private static void publish(
            Path destination,
            JsonObject data) throws Exception {

        Files.createDirectories(destination.getParent());

        Path temporary = Files.createTempFile(
                destination.getParent(),
                "sentinel-request-",
                ".tmp");

        try {
            Files.writeString(
                    temporary,
                    data.toString(),
                    StandardCharsets.UTF_8);

            try {
                Files.move(
                        temporary,
                        destination,
                        StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.ATOMIC_MOVE);

            } catch (AtomicMoveNotSupportedException error) {
                Files.move(
                        temporary,
                        destination,
                        StandardCopyOption.REPLACE_EXISTING);
            }

        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static String sendOrbAction(String action)
            throws Exception {

        Path directory = Path.of(".")
                .toAbsolutePath()
                .normalize()
                .resolve("data");

        String id = UUID.randomUUID().toString();

        JsonObject request = new JsonObject();
        request.addProperty("id", id);
        request.addProperty("action", action);

        publish(
                directory.resolve("orb-command.json"),
                request);

        Path acknowledgement =
                directory.resolve("orb-ack.json");

        long deadline = System.nanoTime() + 5_000_000_000L;

        while (System.nanoTime() < deadline) {
            try {
                if (Files.isRegularFile(acknowledgement)) {
                    JsonObject result = JsonParser.parseString(
                            Files.readString(
                                    acknowledgement,
                                    StandardCharsets.UTF_8))
                            .getAsJsonObject();

                    if (id.equals(jsonText(result, "id"))) {
                        return jsonText(result, "status");
                    }
                }

            } catch (java.io.IOException | RuntimeException ignored) {
            }

            try {
                Thread.sleep(40);

            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw error;
            }
        }

        return "TIMEOUT";
    }

    public static String classifyRoute(String command) {
        String text = normalize(command);

        if (text.isEmpty()) {
            return "NONE";
        }

        if (!globeControlIntent(command).isEmpty()) {
            return "GLOBE_CONTROL";
        }

        String request = requestText(command);

        // Explicit personal memory commands must not open a replay,
        // even if their saved note mentions incidents or dates.
        if (PersonalMemory.isCommand(request)) {
            return "BRAIN";
        }

        if (request.matches(
                ".*\\b(dont|don t|do not|never|not|ne|pas)\\b.*")) {
            return "BRAIN";
        }

        SemanticRouter.Route semantic =
                SemanticRouter.routeQuestion(command);

        if ("INCIDENT_SUMMARY".equals(semantic.intent())
                || "MOST_DANGEROUS".equals(semantic.intent())) {
            return "VISUAL_INCIDENT_REPLAY";
        }

        if (request.matches(
                "^(?:why|how|explain|pourquoi|comment|explique)\\b.*")) {
            return "BRAIN";
        }

        String action =
                "(?:open|opens|show|shows|display|launch|start"
                        + "|ouvre|ouvres|affiche|lance|montre)";

        String recipient = "(?:me |moi )?";
        String article = "(?:the |a |an |le |la |un |une )?";

        boolean globe = request.matches(
                action + " " + recipient + article
                        + "(?:incident |sentinel )?globe");

        boolean replay = request.matches(
                action + " " + recipient + article
                        + "(?:visual )?(?:incident )?replay(?:\\s+.*)?");

        boolean latest = request.matches(
                "(?:show|shows|display|montre|affiche) "
                        + recipient + article
                        + "(?:latest|last|dernier|derniere) "
                        + "(?:incident|attack|attaque)");

        boolean visualAction = request.matches(
                "^(?:replay|animate|visualize|visualise"
                        + "|rejoue|anime)\\b.*");

        boolean incident = request.matches(
                ".*\\b(attack|attacks|incident|incidents"
                        + "|attaque|attaques|scan"
                        + "|intrusion|network|reseau)\\b.*");

        boolean previous = request.matches(
                "(?:show|replay|visualize|visualise) "
                        + "(?:me )?(?:that|it|those events)");

        return globe || replay || latest || previous
                || (visualAction && incident)
                ? "VISUAL_INCIDENT_REPLAY"
                : "BRAIN";
    }

    private static boolean isPeriodFollowUp(String command) {
        return normalize(command).matches(
                "(?:(?:and|what about|how about|et|et pour) )?"
                        + "(?:today|yesterday|last night"
                        + "|this morning|this afternoon|this evening"
                        + "|this week|this weekend"
                        + "|aujourd hui|hier|cette nuit|ce matin"
                        + "|cet apres midi|ce soir|cette semaine)");
    }

    private String resolveQuery(String command) {
        String text = normalize(command);

        SemanticRouter.Route semantic =
                SemanticRouter.routeQuestion(command);

        boolean previous = text.matches(
                "(?:please )?"
                        + "(?:show|replay|visualize|visualise) "
                        + "(?:me )?(?:that|it|those events)"
                        + "(?: please)?")
                || text.matches(
                "(?:please )?show (?:me )?what happened(?: please)?");

        if (previous
                && !semantic.timeExplicit()
                && !lastReplayQuery.isBlank()) {
            return lastReplayQuery;
        }

        return isPeriodFollowUp(command)
                ? "What happened " + command
                : command;
    }

    private static synchronized String openOrUpdateReplay(
            String query) throws Exception {

        Path root =
                Path.of(".").toAbsolutePath().normalize();

        JsonObject request = new JsonObject();

        request.addProperty(
                "id", UUID.randomUUID().toString());

        request.addProperty("query", query);

        if (GlobeControl.findOpenState() != null) {
            publish(
                    root.resolve("data/replay-request.json"),
                    request);

            return "UPDATED";
        }

        if (replayProcess != null && replayProcess.isAlive()) {
            throw new IllegalStateException(
                    "The previous globe is starting or closing. "
                            + "Try again in a moment.");
        }

        Path classes = root.resolve("target/classes");

        Path dependencies =
                root.resolve("target/globe-classpath.txt");

        if (!Files.isRegularFile(
                classes.resolve("GlobeLauncher.class"))) {
            throw new IllegalStateException(
                    "GlobeLauncher is not compiled.");
        }

        String deps = Files.readString(
                dependencies,
                StandardCharsets.UTF_8).trim();

        if (!deps.contains("sherpa-onnx-native-lib-win-x64")) {
            throw new IllegalStateException(
                    "The Kokoro native library is missing.");
        }

        Path java = Path.of(
                System.getProperty("java.home"),
                "bin", "java.exe");

        if (!Files.isRegularFile(java)) {
            throw new IllegalStateException(
                    "Java executable not found: " + java);
        }

        Files.createDirectories(root.resolve("data"));

        publish(
                root.resolve("data/replay-request.json"),
                request);

        replayProcess = new ProcessBuilder(
                java.toString(),
                "--enable-native-access=ALL-UNNAMED",
                "-cp",
                classes + File.pathSeparator + deps,
                "GlobeLauncher",
                query)
                .directory(root.toFile())
                .redirectErrorStream(true)
                .redirectOutput(
                        ProcessBuilder.Redirect.appendTo(
                                root.resolve(
                                        "data/voice-replay.log").toFile()))
                .start();

        return "OPENED";
    }

    public synchronized JsonObject dispatch(
            String command, String source) {

        String question =
                command == null ? "" : command.trim();

        try {
            String globeAction = globeControlIntent(question);

            if (!globeAction.isEmpty()) {
                return controlGlobe(globeAction, source);
            }

            JsonObject companionResult =
                    companionRequest(question, source);

            if (companionResult != null) {
                return companionResult;
            }

        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();

            JsonObject result = baseResult("CONTROL", source);
            result.addProperty("status", "ERROR");
            result.addProperty(
                    "response",
                    "That request was interrupted.");

            return result;

        } catch (Exception error) {
            System.err.println("[CONTROL] " + error);

            JsonObject result = baseResult("CONTROL", source);
            result.addProperty("status", "ERROR");
            result.addProperty(
                    "response",
                    "I couldn't confirm that application action.");

            return result;
        }

        String route = classifyRoute(question);

        if (!lastReplayQuery.isBlank()
                && isPeriodFollowUp(question)) {
            route = "VISUAL_INCIDENT_REPLAY";
        }

        JsonObject result = baseResult(route, source);

        if ("NONE".equals(route)) {
            result.addProperty("handled", false);
            result.addProperty("status", "EMPTY_COMMAND");
            result.addProperty("response", "");

            return result;
        }

        try {
            if ("VISUAL_INCIDENT_REPLAY".equals(route)) {
                String query = resolveQuery(question);

                JsonObject payload = new IncidentReplayQuery(
                        Path.of("."),
                        ZoneId.of("Asia/Kolkata"))
                        .replayPayloadForQuery(query);

                String operation = openOrUpdateReplay(query);
                lastReplayQuery = query;

                result.addProperty("status", "LAUNCHED");
                result.addProperty("operation", operation);
                result.addProperty("response", "");
                result.addProperty("audio_owner", "REPLAY");
                result.addProperty("replay_query", query);

                result.addProperty(
                        "matched_events",
                        payload.get("matched_events").getAsInt());

                return result;
            }

            BrainConversation.Reply reply =
                    brain.answer(question);

            result.addProperty("status", reply.status());
            result.addProperty("response", reply.response());
            result.addProperty("brain_route", reply.route());

            result.addProperty(
                    "knowledge_source",
                    reply.knowledgeSource());

            result.addProperty(
                    "continue",
                    reply.continueConversation());

            if ("PERSONAL_MEMORY".equals(reply.knowledgeSource())) {
                // Do not retain deleted personal notes in this
                // controller's temporary conversational history.
                companionHistory.clear();
                recentReplies.clear();
                recentFallbacks.clear();

            } else if (reply.response() != null
                    && !reply.response().isBlank()) {
                rememberCompanion(
                        question, reply.response());
            }

        } catch (Exception error) {
            result.addProperty("status", "ERROR");

            result.addProperty(
                    "response",
                    "I couldn't complete that request.");

            System.err.println("[DISPATCHER] " + error);
        }

        return result;
    }

    public JsonObject dispatch(String command) {
        return dispatch(command, "text");
    }

    private static String jsonText(
            JsonObject object,
            String key) {

        return object.has(key)
                && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString() : "";
    }

    public static void main(String[] args) {
        JsonObject tests = new JsonObject();

        for (String text : List.of(
                "Open the globe",
                "What happened today?",
                "What happened yesterday?",
                "Replay the latest incident")) {

            tests.addProperty(
                    text,
                    "VISUAL_INCIDENT_REPLAY"
                            .equals(classifyRoute(text)));
        }

        for (String text : List.of(
                "Close the globe",
                "Stop narration",
                "Resume narration")) {

            tests.addProperty(
                    text,
                    "GLOBE_CONTROL"
                            .equals(classifyRoute(text)));
        }

        JsonObject result = new JsonObject();

        result.addProperty(
                "status",
                tests.entrySet().stream()
                        .allMatch(entry ->
                                entry.getValue().getAsBoolean())
                        ? "PASS" : "FAIL");

        result.add("tests", tests);

        System.out.println(
                new GsonBuilder()
                        .setPrettyPrinting()
                        .create()
                        .toJson(result));
    }
}
// END COMMAND DISPATCHER