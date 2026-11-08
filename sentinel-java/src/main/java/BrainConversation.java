import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;

public final class BrainConversation {

    public static final String VERSION = "3.0-PERSONAL-MEMORY";

    private static final Gson JSON =
            new GsonBuilder().serializeNulls().create();

    private static final Pattern LATEST_INCIDENT = Pattern.compile(
            "\\b(?:last|latest|most recent)\\s+"
                    + "(?:incident|event|connection|attack)\\b",
            Pattern.CASE_INSENSITIVE);

    private static final Pattern FOLLOW_UP = Pattern.compile(
            "^(?:explain (?:that|it|this).*"
                    + "|tell me more.*"
                    + "|why.*"
                    + "|how did you.*"
                    + "|what did you do.*"
                    + "|what (?:defen[cs]ive )?(?:measures|actions) did you.*"
                    + "|what about (?:the )?(?:decoy|sandbox).*"
                    + "|was (?:the )?(?:decoy|sandbox) active.*)$");

    private final String sessionId = "brain-" + UUID.randomUUID();

    private final Deque<LocalBrain.Message> modelHistory =
            new ArrayDeque<>();

    private final Path root;
    private final ZoneId zone;
    private final Path replayRequestFile;
    private final Path conversationLog;

    private final BrainMemory brainMemory;
    private final PersonalMemory personalMemory;
    private final IncidentDialogue incidentDialogue;
    private final LocalBrain localBrain = new LocalBrain();

    private boolean active = true;

    private String lastReplayRequestId = "";
    private String replayQuery = "";
    private JsonObject replayPayload;
    private JsonObject selectedReplayIncident;
    private boolean replayContextUnavailable;

    public BrainConversation(Path root, ZoneId zone) {
        this.root = root.toAbsolutePath().normalize();
        this.zone = zone;

        brainMemory = new BrainMemory(this.root, zone);
        personalMemory = new PersonalMemory(this.root);
        incidentDialogue = new IncidentDialogue(this.root);

        replayRequestFile =
                this.root.resolve("data/replay-request.json");

        conversationLog =
                this.root.resolve("data/brain_conversations.jsonl");

        JsonObject previous = readReplayRequest();

        if (previous != null) {
            lastReplayRequestId = jsonText(previous, "id");
        }

        System.out.println("[BRAIN] Version: " + VERSION);
    }

    public synchronized Reply answer(String input) {
        String question = input == null ? "" : input.strip();

        if (!active) {
            return new Reply(
                    "EXIT",
                    "This conversation has already closed.",
                    false,
                    "LOCAL",
                    "CONVERSATION_CONTROL");
        }

        if (question.isEmpty()) {
            return new Reply(
                    "EMPTY",
                    "I didn't receive a question.",
                    true,
                    null,
                    null);
        }

        // Explicit personal memory operations do not need a language model.
        PersonalMemory.Response memory = personalMemory.handle(question);

        if (memory.handled()) {
            // Avoid retaining a deleted note in this model's short history.
            // Other components may still hold their own session history.
            modelHistory.clear();

            // Do not duplicate these commands in this conversation log.
            return new Reply(
                    memory.ok() ? "ANSWERED" : "ERROR",
                    memory.text(),
                    true,
                    "LOCAL",
                    "PERSONAL_MEMORY");
        }

        refreshReplayContext();

        SemanticRouter.Route semantic =
                SemanticRouter.routeQuestion(question);

        Reply reply = route(semantic);

        active = reply.continueConversation();

        remember("USER", question, semantic, reply);
        remember("SENTINEL", reply.response(), semantic, reply);

        return reply;
    }

    private JsonObject readReplayRequest() {
        try {
            if (!Files.isRegularFile(replayRequestFile)) {
                return null;
            }

            return JsonParser.parseString(
                    Files.readString(
                            replayRequestFile,
                            StandardCharsets.UTF_8))
                    .getAsJsonObject();

        } catch (IOException | RuntimeException error) {
            return null;
        }
    }

    private void refreshReplayContext() {
        JsonObject request = readReplayRequest();

        if (request == null) {
            return;
        }

        String id = jsonText(request, "id");
        String query = jsonText(request, "query");

        if (id.isBlank() || query.isBlank()
                || id.equals(lastReplayRequestId)) {
            return;
        }

        lastReplayRequestId = id;
        replayQuery = query;
        replayPayload = null;
        selectedReplayIncident = null;
        replayContextUnavailable = false;

        incidentDialogue.clear();
        modelHistory.clear();

        try {
            replayPayload = new IncidentReplayQuery(root, zone)
                    .replayPayloadForQuery(query);

            System.out.println(
                    "[BRAIN CONTEXT] Requested replay: " + query);

        } catch (IOException | RuntimeException error) {
            replayContextUnavailable = true;

            System.err.println(
                    "[REPLAY CONTEXT ERROR] " + error.getMessage());
        }
    }

    private Reply route(SemanticRouter.Route semantic) {
        return switch (semantic.intent()) {
            case "EXIT" -> new Reply(
                    "EXIT",
                    "Sentinel conversation session closed.",
                    false,
                    "LOCAL",
                    "CONVERSATION_CONTROL");

            case "HELP" -> new Reply(
                    "ANSWERED",
                    """
                    Ask what happened today or yesterday.
                    After a replay, ask me to explain the latest event.
                    For personal memory, say:
                    Remember that I like basketball.
                    What do you remember about me?
                    Forget memory followed by its ID.
                    Forget all personal memories.
                    Say that's all to return to voice standby.
                    """,
                    true,
                    "LOCAL",
                    "CONVERSATION_CONTROL");

            case "SYSTEM_STATUS" -> systemStatus();

            default -> routeQuestion(semantic);
        };
    }

    private Reply routeQuestion(SemanticRouter.Route semantic) {
        String question = semantic.original();

        String normalized = question.toLowerCase(Locale.ROOT)
                .replaceAll("\\s+", " ")
                .replaceFirst("[?!.]+$", "")
                .strip();

        boolean noTimeFilter = !semantic.timeExplicit()
                && semantic.explicitClock() == null
                && semantic.presenceContext() == null;

        boolean latest =
                LATEST_INCIDENT.matcher(question).find();

        boolean followUp =
                FOLLOW_UP.matcher(normalized).matches()
                        || isDirectIncidentQuestion(normalized);

        boolean hasReplayContext =
                replayPayload != null || replayContextUnavailable;

        if (hasReplayContext && noTimeFilter
                && (latest || followUp || semantic.sourceIp() != null)) {
            return answerReplayFollowUp(semantic, latest);
        }

        boolean noFilter =
                noTimeFilter && semantic.sourceIp() == null;

        if (noFilter && latest) {
            return answerIncident(question, true);
        }

        if (noFilter
                && incidentDialogue.hasIncident()
                && FOLLOW_UP.matcher(normalized).matches()) {
            return answerIncident(question, false);
        }

        if (noFilter && isDirectIncidentQuestion(normalized)) {
            return answerIncident(question, true);
        }

        switch (semantic.intent()) {
            case "INCIDENT_SUMMARY", "SOURCE_LOOKUP",
                    "MOST_DANGEROUS", "CONTAINMENT_SUMMARY" -> {
                clearTopic();
                return answerMemory(semantic);
            }

            default -> {
            }
        }

        if (InternetGateway.classify(question).external()) {
            clearTopic();

            InternetGateway.Reply result =
                    InternetGateway.answer(question);

            return new Reply(
                    result.ok() ? "ANSWERED" : "ERROR",
                    result.response(),
                    true,
                    "INTERNET",
                    result.source());
        }

        if ("yesterday".equals(normalized)
                || "today".equals(normalized)
                || "hier".equals(normalized)
                || semantic.presenceContext() != null
                || semantic.explicitClock() != null) {
            clearTopic();
            return answerMemory(semantic);
        }

        incidentDialogue.clear();
        replayPayload = null;
        selectedReplayIncident = null;
        replayContextUnavailable = false;
        replayQuery = "";

        return answerGeneralQuestion(question);
    }

    private Reply answerReplayFollowUp(
            SemanticRouter.Route semantic,
            boolean latestRequested) {

        if (replayContextUnavailable || replayPayload == null) {
            return replayReply(
                    "ERROR",
                    "I couldn't read the history for that replay. "
                            + "Please request the period again.");
        }

        JsonArray incidents =
                replayPayload.getAsJsonArray("incidents");

        if (incidents == null || incidents.isEmpty()) {
            return replayReply(
                    "ANSWERED",
                    "No matching recorded incidents were found "
                            + "for that requested replay.");
        }

        if (semantic.sourceIp() != null) {
            List<JsonObject> matches = new ArrayList<>();

            for (JsonElement item : incidents) {
                JsonObject event = item.getAsJsonObject();

                if (semantic.sourceIp().equals(sourceIp(event))) {
                    matches.add(event);
                }
            }

            if (matches.isEmpty()) {
                return replayReply(
                        "CLARIFICATION_REQUIRED",
                        "That address is not in the event selection "
                                + "prepared for this replay. "
                                + "Please identify another event or "
                                + "request a different period.");
            }

            if (matches.size() > 1 && !latestRequested) {
                return replayReply(
                        "CLARIFICATION_REQUIRED",
                        "There are several recorded events from that "
                                + "address in this replay selection. "
                                + "Please say explain the latest event "
                                + "from that address, including its IP.");
            }

            JsonArray candidates = new JsonArray();

            for (JsonObject match : matches) {
                candidates.add(match);
            }

            selectedReplayIncident = latestRequested
                    ? latestEvent(candidates)
                    : matches.get(0).deepCopy();

        } else if (latestRequested) {
            selectedReplayIncident = latestEvent(incidents);

        } else if (selectedReplayIncident == null) {
            if (incidents.size() == 1) {
                selectedReplayIncident =
                        incidents.get(0).getAsJsonObject().deepCopy();

            } else {
                return replayReply(
                        "CLARIFICATION_REQUIRED",
                        "There are several events in that replay. "
                                + "Which one should I explain? "
                                + "You can give its source IP, "
                                + "or say explain the latest event.");
            }
        }

        JsonObject context = new JsonObject();

        context.addProperty(
                "scope",
                "Recorded event from the requested replay period. "
                        + "The current globe selection is not reported.");

        context.addProperty("replay_query", replayQuery);
        context.addProperty("timezone", zone.getId());

        context.addProperty(
                "selection_basis",
                "Explicit latest-event or source-IP selection, "
                        + "a previously identified event, "
                        + "or the only event returned.");

        context.add(
                "incident", selectedReplayIncident.deepCopy());

        if (replayPayload.has("window")) {
            context.add(
                    "window", replayPayload.get("window").deepCopy());
        }

        context.addProperty(
                "history_limit",
                "The query retains up to 3000 recent events "
                        + "and returns at most 120.");

        LocalBrain.Result result = localBrain.chat(
                semantic.original(),
                context,
                new ArrayList<>(modelHistory));

        if (!result.ok()) {
            return replayReply(
                    "ERROR",
                    "The recorded event is available, "
                            + "but my local language model "
                            + "couldn't explain it right now.");
        }

        addModelHistory(
                semantic.original(), result.response());

        return replayReply("ANSWERED", result.response());
    }

    private static JsonObject latestEvent(JsonArray incidents) {
        JsonObject selected = null;
        Instant latest = Instant.MIN;

        for (JsonElement item : incidents) {
            JsonObject event = item.getAsJsonObject();

            try {
                Instant timestamp =
                        Instant.parse(jsonText(event, "timestamp"));

                if (selected == null || timestamp.isAfter(latest)) {
                    selected = event;
                    latest = timestamp;
                }

            } catch (RuntimeException ignored) {
            }
        }

        return (selected == null
                ? incidents.get(0).getAsJsonObject()
                : selected).deepCopy();
    }

    private static String sourceIp(JsonObject event) {
        for (String key : List.of(
                "source_ip", "remote_ip", "ip")) {

            String address = jsonText(event, key);

            if (!address.isBlank()) {
                return address;
            }
        }

        return "";
    }

    private static Reply replayReply(
            String status, String response) {

        return new Reply(
                status, response, true,
                "LOCAL", "RECORDED_REPLAY_CONTEXT");
    }

    private static boolean isDirectIncidentQuestion(
            String question) {

        return switch (question) {
            case "what did you do",
                    "what about the sandbox",
                    "what about the decoy",
                    "was the sandbox active",
                    "was the decoy active",
                    "how did you neutralize the attack",
                    "how did you contain the attack",
                    "what defensive measures did you take" -> true;

            default -> false;
        };
    }

    private void clearTopic() {
        incidentDialogue.clear();
        modelHistory.clear();
        replayPayload = null;
        selectedReplayIncident = null;
        replayContextUnavailable = false;
        replayQuery = "";
    }

    private Reply answerIncident(
            String question, boolean selectLatest) {

        modelHistory.clear();

        try {
            IncidentDialogue.Result result = selectLatest
                    ? incidentDialogue.begin(question)
                    : incidentDialogue.followUp(question);

            return new Reply(
                    "ANSWERED",
                    result.response(),
                    true,
                    "LOCAL",
                    result.source());

        } catch (IOException error) {
            incidentDialogue.clear();

            System.err.println(
                    "[INCIDENT DIALOGUE ERROR] "
                            + error.getMessage());

            return new Reply(
                    "ERROR",
                    "I couldn't read the incident report right now.",
                    true,
                    "LOCAL",
                    "INCIDENT_REASONING");
        }
    }

    private Reply answerMemory(SemanticRouter.Route semantic) {
        try {
            return new Reply(
                    "ANSWERED",
                    brainMemory.answer(semantic),
                    true,
                    "LOCAL",
                    "SENTINEL_MEMORY");

        } catch (IOException error) {
            System.err.println(
                    "[HISTORY ERROR] " + error.getMessage());

            return new Reply(
                    "ERROR",
                    "I couldn't read my local history right now.",
                    true,
                    "LOCAL",
                    "SENTINEL_MEMORY");
        }
    }

    private void addModelHistory(
            String question, String response) {

        modelHistory.addLast(
                new LocalBrain.Message("user", question));

        modelHistory.addLast(
                new LocalBrain.Message("assistant", response));

        while (modelHistory.size() > 8) {
            modelHistory.removeFirst();
        }
    }

    private Reply answerGeneralQuestion(String question) {
        JsonObject context;

        try {
            context = personalMemory.context();

        } catch (IOException error) {
            // Do not let the model guess what is stored in an unreadable file.
            return new Reply(
                    "ERROR",
                    "I couldn't read personal memory right now. "
                            + "Please check the personal memory file.",
                    true,
                    "LOCAL",
                    "PERSONAL_MEMORY");
        }

        LocalBrain.Result result = localBrain.chat(
                question,
                context,
                new ArrayList<>(modelHistory));

        if (!result.ok()) {
            return new Reply(
                    "ERROR",
                    "My local language model is unavailable right now ("
                            + result.error()
                            + "). Recorded incident queries remain available.",
                    true,
                    "LOCAL",
                    "OLLAMA");
        }

        addModelHistory(question, result.response());

        return new Reply(
                "ANSWERED",
                result.response(),
                true,
                "LOCAL",
                LocalBrain.MODEL);
    }

    private Reply systemStatus() {
        LocalBrain.Status status = localBrain.status();

        return new Reply(
                "ANSWERED",
                "The conversation router supports recorded incident queries "
                        + "and replay follow-ups. "
                        + "Explicit personal notes are stored locally. "
                        + "Camera recognition is not connected. "
                        + "The local model is " + LocalBrain.MODEL
                        + ", with status " + status.reason() + ".",
                true,
                "LOCAL",
                "SENTINEL_INTERNAL");
    }

    private void remember(
            String role,
            String text,
            SemanticRouter.Route semantic,
            Reply reply) {

        String content = text == null ? "" : text;

        int length = Math.min(
                6000,
                content.codePointCount(0, content.length()));

        Map<String, Object> details = new LinkedHashMap<>();

        details.put("intent", semantic.intent());
        details.put("time_range", semantic.timeRange());
        details.put("presence_context", semantic.presenceContext());
        details.put("source_ip", semantic.sourceIp());
        details.put(
                "intent_confidence", semantic.intentConfidence());

        if (semantic.explicitClock() != null) {
            details.put(
                    "explicit_clock",
                    Map.of(
                            "start", semantic.explicitClock().start(),
                            "end", semantic.explicitClock().end()));
        }

        Map<String, Object> event = new LinkedHashMap<>();

        event.put("session_id", sessionId);
        event.put("timestamp", Instant.now().toString());
        event.put("role", role);

        event.put(
                "text",
                content.substring(
                        0, content.offsetByCodePoints(0, length)));

        event.put("route_mode", reply.route());
        event.put("knowledge_source", reply.knowledgeSource());
        event.put("semantic", details);

        try {
            Files.createDirectories(conversationLog.getParent());

            Files.writeString(
                    conversationLog,
                    JSON.toJson(event) + "\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);

        } catch (IOException error) {
            System.err.println(
                    "[CONVERSATION LOG ERROR] " + error.getMessage());
        }
    }

    public static void main(String[] args) throws IOException {
        ZoneId zone = ZoneId.of(
                args.length == 0 ? "Asia/Kolkata" : args[0]);

        BrainConversation conversation =
                new BrainConversation(Path.of("."), zone);

        CommandDispatcher dispatcher =
                new CommandDispatcher(conversation);

        System.out.println(
                "SENTINEL PHOENIX | CONTEXT-AWARE CONVERSATION");

        System.out.println("Brain version: " + VERSION);
        System.out.println("Local model: " + LocalBrain.MODEL);
        System.out.println(
                "Type help for examples or exit to close.");

        BufferedReader input = new BufferedReader(
                new InputStreamReader(
                        System.in, StandardCharsets.UTF_8));

        while (conversation.active) {
            System.out.print("\nYOU > ");
            System.out.flush();

            String question = input.readLine();

            if (question == null) {
                break;
            }

            JsonObject result =
                    dispatcher.dispatch(question, "text");

            System.out.println(
                    "SENTINEL > " + jsonText(result, "response"));

            System.out.println(
                    "[DISPATCH] " + jsonText(result, "route"));

            if (result.has("continue")
                    && !result.get("continue").isJsonNull()
                    && !result.get("continue").getAsBoolean()) {
                break;
            }
        }
    }

    private static String jsonText(
            JsonObject object, String key) {

        return object.has(key)
                && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString() : "";
    }

    public record Reply(
            String status,
            String response,
            boolean continueConversation,
            String route,
            String knowledgeSource) {
    }
}
// END BRAIN CONVERSATION