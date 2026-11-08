import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import javafx.animation.AnimationTimer;
import javafx.application.Application;
import javafx.application.ConditionalFeature;
import javafx.application.Platform;
import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.*;
import javafx.scene.control.*;
import javafx.scene.image.Image;
import javafx.scene.layout.*;
import javafx.scene.paint.Color;
import javafx.scene.paint.PhongMaterial;
import javafx.scene.shape.CullFace;
import javafx.scene.shape.Sphere;
import javafx.scene.transform.Rotate;
import javafx.stage.Stage;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.time.ZoneId;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class IncidentGlobeFX extends Application {
    public static final String VERSION = "4.0-INCIDENT-SCENES";
    private record Entry(GlobeEvent event, JsonObject raw) {}
    private record Cue(String text, String focus) {}
    private final Path root = Path.of(".").toAbsolutePath().normalize();
    private final String instanceId = UUID.randomUUID().toString();
    private final List<Entry> entries = new ArrayList<>();
    private final ExecutorService worker = Executors.newSingleThreadExecutor(task -> {
        Thread thread = new Thread(task, "sentinel-globe-analysis");
        thread.setDaemon(true); return thread;
    });
    private final ScheduledExecutorService requests =
            Executors.newSingleThreadScheduledExecutor(task -> {
                Thread thread = new Thread(task, "sentinel-globe-requests");
                thread.setDaemon(true); return thread;
            });
    private final KokoroVoice voice = new KokoroVoice(root);
    private final Label queryLabel = label("", 12, "#a9bbc9");
    private final Label counter = label("0 / 0", 14, "#a6e4d4");
    private final Label status = label("", 12, "#7faaa6");
    private final Label risk = label("—", 28, "#75e3bf");
    private final Label source = label("—", 14, "#e0fff5");
    private final Label analysisStatus = label("", 12, "#82caba");
    private final Label voiceStatus = label("Heart / Preparing", 12, "#a6d4c9");
    private final TextArea details = new TextArea();
    private final TextArea explanation = new TextArea();
    private final Button analyze = button("AI ANALYZE");
    private final Button readAnalysis = button("READ ANALYSIS");
    private final Button narration = button("NARRATION ON");
    private final Button play = button("PAUSE");
    private final Rotate rotation = new Rotate(0, Rotate.Y_AXIS);
    private final Rotate tilt = new Rotate(-12, Rotate.X_AXIS);
    private final Map<Node, String> focusStyles = new IdentityHashMap<>();
    private PerspectiveCamera camera;
    private AnimationTimer animation;
    private GlobePresenter presenter;
    private AttackAnimationPane sceneView;
    private TabPane sceneTabs;
    private TabPane tabs;
    private Stage window;
    private int index;
    private int targetIndex;
    private long queryRevision;
    private long selectionRevision;
    private long speechRevision;
    private boolean playing = true;
    private boolean narrationEnabled = true;
    private boolean loading;
    private boolean analysisPending;
    private boolean speaking;
    private boolean selectionPending;
    private boolean resumeWhenAllowed;
    private volatile boolean closing;
    private boolean resourcesStopped;
    private String currentAnalysis = "";
    private String lastRequestId = "";
    private String lastControlId = "";
    private long lastFrame;
    private long lastHeartbeat;
    private double elapsed;
    private double mouseX;
    private double mouseY;

    @Override public void start(Stage stage) {
        window = stage;
        if (!Platform.isSupported(ConditionalFeature.SCENE3D)) {
            new Alert(Alert.AlertType.ERROR, "JavaFX 3D is unavailable.").showAndWait();
            Platform.exit(); return;
        }
        String query = getParameters().getRaw().isEmpty() ? "latest"
                : String.join(" ", getParameters().getRaw());
        JsonObject oldReplay = readJson("replay-request.json");
        JsonObject oldControl = readJson("globe-command.json");
        if (oldReplay != null) lastRequestId = value(oldReplay, "id");
        if (oldControl != null) lastControlId = value(oldControl, "id");
        presenter = new GlobePresenter();
        BorderPane layout = new BorderPane();
        layout.setPadding(new Insets(24));
        layout.setStyle("-fx-background-color:linear-gradient(to bottom right,#081724,#02060d);");
        queryLabel.setWrapText(true);
        VBox header = new VBox(8,
                label("SENTINEL / INCIDENT INTELLIGENCE", 23, "#c8fff1"),
                label("ONE REPLAY VOICE / RECORDED EVIDENCE", 11, "#62a99f"), queryLabel);
        header.setPadding(new Insets(0, 0, 20, 0));
        layout.setTop(header);
        layout.setCenter(buildCenter());
        layout.setRight(buildPanel());
        Button previous = button("PREVIOUS");
        Button next = button("NEXT");
        Button stopVoice = button("STOP VOICE");
        Button close = button("CLOSE GLOBE");
        previous.setOnAction(event -> select(targetIndex - 1));
        next.setOnAction(event -> select(targetIndex + 1));
        play.setOnAction(event -> {
            playing = !playing; elapsed = 0; updateButtons(); publishState(true);
        });
        narration.setOnAction(event -> {
            if (narrationEnabled) stopNarration("Automatic narration disabled.");
            else enableNarration();
        });
        stopVoice.setOnAction(event -> stopNarration("Voice stopped. Replay paused."));
        close.setOnAction(event -> closeGlobe("", ""));
        FlowPane controls = new FlowPane(12, 10);
        controls.getChildren().addAll(previous, play, next, counter, narration, stopVoice, close);
        voiceStatus.setWrapText(true); status.setWrapText(true);
        VBox bottom = new VBox(10, controls, voiceStatus, status);
        bottom.setPadding(new Insets(18, 0, 0, 0));
        layout.setBottom(bottom);
        Scene scene = new Scene(layout, 1400, 900);
        scene.setOnKeyPressed(event -> {
            if (scene.getFocusOwner() instanceof TextInputControl) return;
            switch (event.getCode()) {
                case RIGHT -> select(targetIndex + 1);
                case LEFT -> select(targetIndex - 1);
                case ESCAPE -> stopNarration("Voice stopped. Replay paused.");
                default -> {}
            }
        });
        stage.setTitle("Sentinel Phoenix | Globe " + VERSION);
        stage.setMinWidth(1000); stage.setMinHeight(700); stage.setScene(scene);
        stage.setOnCloseRequest(event -> { event.consume(); closeGlobe("", ""); });
        stage.show();
        System.out.println("[GLOBE] " + VERSION);
        startAnimation(); publishState(true); loadQuery(query);
        requests.scheduleWithFixedDelay(this::pollRequests, 150, 150, TimeUnit.MILLISECONDS);
    }

    private JsonObject readJson(String name) {
        try {
            Path file = root.resolve("data").resolve(name);
            return Files.isRegularFile(file) ? JsonParser.parseString(
                    Files.readString(file, StandardCharsets.UTF_8)).getAsJsonObject() : null;
        } catch (Exception error) { return null; }
    }
    private void writeJson(String name, JsonObject data) {
        Path temporary = null;
        try {
            Path file = root.resolve("data").resolve(name);
            Files.createDirectories(file.getParent());
            temporary = Files.createTempFile(file.getParent(), "globe-update-", ".tmp");
            Files.writeString(temporary, data.toString(), StandardCharsets.UTF_8);
            try { Files.move(temporary, file, StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException error) {
                Files.move(temporary, file, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (Exception error) { System.err.println("[GLOBE FILE] " + error); }
        finally {
            if (temporary != null) try { Files.deleteIfExists(temporary); }
            catch (Exception ignored) {}
        }
    }
    private void pollRequests() {
        if (closing) return;
        JsonObject command = readJson("globe-command.json");
        JsonObject replay = readJson("replay-request.json");
        String cid = command == null ? "" : value(command, "id");
        String action = command == null ? "" : value(command, "action");
        boolean freshControl = command != null && !cid.isBlank()
                && !cid.equals(lastControlId)
                && instanceId.equals(value(command, "target_instance"));
        if (freshControl) lastControlId = cid;
        String rid = replay == null ? "" : value(replay, "id");
        String query = replay == null ? "" : value(replay, "query");
        boolean freshReplay = !rid.isBlank() && !query.isBlank() && !rid.equals(lastRequestId);
        if (freshReplay) lastRequestId = rid;
        Platform.runLater(() -> {
            if (closing) return;
            if (freshControl) handleControl(cid, action);
            if (closing) return;
            if (freshReplay) { window.toFront(); loadQuery(query); }
            boolean assistant = AudioOwnership.assistantOwns(root);
            if (assistant && !resumeWhenAllowed && (speaking || narrationEnabled)) {
                stopNarration("Paused for your conversation. Say Resume narration to continue.");
            } else if (!assistant && resumeWhenAllowed && !loading && !analysisPending) {
                resumeWhenAllowed = false; narrateCurrent();
            }
            publishState(false);
        });
    }
    private void handleControl(String id, String action) {
        switch (action) {
            case "STOP_NARRATION" -> {
                stopNarration("Voice stopped. Replay paused."); acknowledge(id, action, "COMPLETED");
            }
            case "RESUME_NARRATION" -> { enableNarration(); acknowledge(id, action, "ACCEPTED"); }
            case "CLOSE" -> closeGlobe(id, action);
            case "NEXT" -> { select(targetIndex + 1); acknowledge(id, action, "ACCEPTED"); }
            case "PREVIOUS" -> { select(targetIndex - 1); acknowledge(id, action, "ACCEPTED"); }
            default -> acknowledge(id, action, "UNSUPPORTED");
        }
    }
    private void acknowledge(String id, String action, String result) {
        if (id.isBlank()) return;
        JsonObject data = new JsonObject();
        data.addProperty("id", id); data.addProperty("instance_id", instanceId);
        data.addProperty("action", action); data.addProperty("status", result);
        data.addProperty("updated_at", Instant.now().toString());
        writeJson("globe-ack.json", data);
    }
    private void publishState(boolean force) {
        long now = System.nanoTime();
        if (!force && now - lastHeartbeat < 1_000_000_000L) return;
        lastHeartbeat = now;
        JsonObject data = new JsonObject();
        data.addProperty("version", VERSION); data.addProperty("instance_id", instanceId);
        data.addProperty("process_id", ProcessHandle.current().pid());
        data.addProperty("status", closing ? "CLOSED" : "OPEN");
        data.addProperty("narration_enabled", narrationEnabled);
        data.addProperty("playing", playing); data.addProperty("speaking", speaking);
        data.addProperty("loading", loading); data.addProperty("analysis_pending", analysisPending);
        data.addProperty("selected_index", index); data.addProperty("event_count", entries.size());
        data.addProperty("updated_at", Instant.now().toString());
        writeJson("globe-state.json", data);
    }
    private void updateButtons() {
        narration.setText(narrationEnabled ? "NARRATION ON" : "NARRATION OFF");
        play.setText(playing ? "PAUSE" : "PLAY");
    }
    private void cancelSpeech() {
        speechRevision++; speaking = false; voice.stopSpeech();
        if (presenter != null) presenter.rest();
        if (sceneView != null) sceneView.pause();
        clearFocus();
    }
    private void settleSelection() {
        if (selectionPending && !loading && targetIndex >= 0 && targetIndex < entries.size()) {
            applyEntry(targetIndex);
        }
    }
    private void stopNarration(String message) {
        narrationEnabled = false; playing = false; resumeWhenAllowed = false;
        cancelSpeech(); settleSelection(); elapsed = 0; updateButtons();
        voiceStatus.setText(message); publishState(true);
    }
    private void enableNarration() {
        if (closing) return;
        cancelSpeech(); settleSelection(); narrationEnabled = true; updateButtons();
        if (AudioOwnership.assistantOwns(root) || loading || analysisPending) {
            resumeWhenAllowed = true;
            voiceStatus.setText("Narration requested. Waiting for the audio channel.");
        } else { resumeWhenAllowed = false; narrateCurrent(); }
        publishState(true);
    }
    private void closeGlobe(String id, String action) {
        if (closing) return;
        stopNarration("Closing globe."); closing = true; window.hide();
        publishState(true); acknowledge(id, action, "COMPLETED"); Platform.exit();
    }

    private void loadQuery(String query) {
        long ticket = ++queryRevision;
        selectionRevision++; cancelSpeech(); loading = true;
        selectionPending = false; analysisPending = false;
        // A new explicit replay request is a new playback request. STOP still
        // remains effective for the current request until the user resumes.
        narrationEnabled = true; playing = true;
        resumeWhenAllowed = AudioOwnership.assistantOwns(root); updateButtons();
        entries.clear(); index = 0; targetIndex = 0; elapsed = 0; currentAnalysis = "";
        queryLabel.setText(query); counter.setText("0 / 0"); risk.setText("LOADING");
        source.setText("—"); details.setText("Loading the requested local history...");
        explanation.clear(); analysisStatus.setText(""); analyze.setText("AI ANALYZE");
        analyze.setDisable(true); readAnalysis.setDisable(true);
        status.setText("Loading local history...");
        worker.submit(() -> {
            try {
                JsonObject payload = new IncidentReplayQuery(root, ZoneId.of("Asia/Kolkata"))
                        .replayPayloadForQuery(query);
                var normalized = payload.getAsJsonArray("events");
                var raw = payload.getAsJsonArray("incidents");
                if (normalized == null || raw == null || normalized.size() != raw.size()) {
                    throw new IllegalStateException("Replay arrays are inconsistent.");
                }
                List<Entry> loaded = new ArrayList<>(); Gson gson = new Gson();
                for (int i = 0; i < normalized.size(); i++) {
                    loaded.add(new Entry(gson.fromJson(normalized.get(i), GlobeEvent.class),
                            raw.get(i).getAsJsonObject().deepCopy()));
                }
                Platform.runLater(() -> {
                    if (closing || ticket != queryRevision) return;
                    loading = false; entries.addAll(loaded);
                    status.setText(entries.size() + " displayed / "
                            + payload.get("matched_events").getAsInt()
                            + " matching event(s) / Asia/Kolkata / Drag to rotate / Scroll to zoom");
                    select(0);
                    if (entries.isEmpty() && narrationEnabled) {
                        if (AudioOwnership.assistantOwns(root)) resumeWhenAllowed = true;
                        else narrateCurrent();
                    }
                    publishState(true);
                });
            } catch (Exception error) {
                error.printStackTrace();
                Platform.runLater(() -> {
                    if (closing || ticket != queryRevision) return;
                    loading = false; risk.setText("UNAVAILABLE");
                    details.setText("The requested replay could not be loaded.");
                    status.setText("Check data/voice-replay.log."); publishState(true);
                });
            }
        });
    }
    private VBox buildPanel() {
        configureText(details); configureText(explanation);
        source.setWrapText(true); analysisStatus.setWrapText(true);
        analyze.setDisable(true); readAnalysis.setDisable(true);
        analyze.setOnAction(event -> analyzeSelected());
        readAnalysis.setOnAction(event -> {
            if (!currentAnalysis.isBlank() && !analysisPending) {
                playing = false; updateButtons(); playCues(analysisCues(currentAnalysis), null);
            }
        });
        VBox recordPanel = new VBox(12, risk, source, details);
        VBox.setVgrow(details, Priority.ALWAYS);
        FlowPane buttons = new FlowPane(10, 10); buttons.getChildren().addAll(analyze, readAnalysis);
        VBox aiPanel = new VBox(12, buttons, analysisStatus, explanation);
        VBox.setVgrow(explanation, Priority.ALWAYS);
        Tab recordTab = new Tab("INCIDENT", recordPanel);
        Tab aiTab = new Tab("AI EXPLANATION", aiPanel);
        recordTab.setClosable(false); aiTab.setClosable(false);
        tabs = new TabPane(recordTab, aiTab); VBox.setVgrow(tabs, Priority.ALWAYS);
        VBox panel = new VBox(16, label("INCIDENT INTELLIGENCE", 12, "#75cbb8"), tabs);
        panel.setPrefWidth(410); panel.setPadding(new Insets(18));
        panel.setStyle("-fx-background-color:#091521;-fx-background-radius:18;"
                + "-fx-border-color:#224b54;-fx-border-radius:18;");
        BorderPane.setMargin(panel, new Insets(0, 0, 0, 20)); return panel;
    }
    private static String field(Object value) {
        if (value == null) return "not recorded";
        String text = value.toString().replaceAll("\\p{Cntrl}", " ")
                .replaceAll("\\s+", " ").strip();
        if (text.isBlank()) return "not recorded";
        return text.length() > 240 ? text.substring(0, 240) + " ..." : text;
    }
    private List<Cue> eventCues(Entry entry) {
        return sceneCues(AttackAnimationPane.evidenceNarration(entry.raw()));
    }
    private static List<Cue> sceneCues(List<AttackAnimationPane.Phase> phases) {
        List<Cue> result = new ArrayList<>();
        for (int i = 0; i < phases.size(); i++) result.add(new Cue(phases.get(i).text(), "scene:" + i));
        return result;
    }
    private static List<Cue> analysisCues(String text) {
        List<Cue> result = new ArrayList<>();
        for (String sentence : text.strip().split("(?<=[.!?])\\s+")) {
            String remaining = sentence.strip();
            while (remaining.length() > 400) {
                int cut = remaining.lastIndexOf(' ', 400);
                if (cut < 100) cut = 400;
                result.add(new Cue(remaining.substring(0, cut), "analysis"));
                remaining = remaining.substring(cut).strip();
            }
            if (!remaining.isBlank()) result.add(new Cue(remaining, "analysis"));
        }
        return result;
    }
    private void narrateCurrent() {
        if (closing || loading || !narrationEnabled || analysisPending) return;
        if (entries.isEmpty()) {
            playCues(List.of(new Cue("No recorded incidents match the requested period.", "incident")), null);
        } else playCues(eventCues(entries.get(index)), null);
    }
    private void clearFocus() {
        for (var entry : focusStyles.entrySet()) entry.getKey().setStyle(entry.getValue());
        focusStyles.clear(); details.deselect();
    }
    private void highlight(String focus) {
        clearFocus(); Node target;
        if (focus.startsWith("scene:")) {
            int step = Integer.parseInt(focus.substring(6));
            sceneTabs.getSelectionModel().select(1); sceneView.setPhase(step);
            target = sceneView.phaseNode(step);
            focusStyles.put(target, target.getStyle());
            target.setStyle(target.getStyle() + "-fx-border-color:#74ffce;-fx-border-width:2;-fx-border-radius:6;");
            if (!sceneView.previewMode()) {
                tabs.getSelectionModel().select(0);
                Node fact = step == 0 ? source : step == 1 ? risk : details;
                focusStyles.put(fact, fact.getStyle());
                fact.setStyle(fact.getStyle() + "-fx-border-color:#74ffce;-fx-border-width:2;-fx-border-radius:6;");
                if (step >= 2) {
                    String heading = step == 2 ? "RECORDED POLICY ACTION" : "DECOY ACTIVE";
                    int start = details.getText().indexOf(heading);
                    if (start >= 0) details.selectRange(start, Math.min(details.getLength(), start + 160));
                }
            }
            presenter.aimAt(target); presenter.speak(sceneView.phases().get(step).title());
            return;
        } else if ("analysis".equals(focus)) {
            tabs.getSelectionModel().select(1); target = explanation;
        } else {
            tabs.getSelectionModel().select(0);
            target = switch (focus) { case "source" -> source; case "risk" -> risk; default -> details; };
            if ("behavior".equals(focus) || "action".equals(focus)) {
                String heading = "action".equals(focus) ? "RECORDED POLICY ACTION" : "BEHAVIOR";
                int start = details.getText().indexOf(heading);
                if (start >= 0) {
                    int end = details.getText().indexOf("\n\n", start);
                    details.selectRange(start, end < 0 ? details.getLength() : end);
                }
            }
        }
        focusStyles.put(target, target.getStyle());
        target.setStyle(target.getStyle()
                + "-fx-border-color:#74ffce;-fx-border-width:2;-fx-border-radius:6;");
        presenter.aimAt(target);
        presenter.speak(focus);
    }
    private void playCues(List<Cue> cues, Runnable showAtStart) {
        if (closing || cues.isEmpty()) {
            if (!closing && showAtStart != null) showAtStart.run(); return;
        }
        if (AudioOwnership.assistantOwns(root)) {
            if (showAtStart != null) showAtStart.run();
            stopNarration("Paused for your conversation. Say Resume narration to continue."); return;
        }
        cancelSpeech(); long ticket = ++speechRevision;
        sceneView.beginNarration();
        speaking = true; elapsed = 0; presenter.prepare();
        AtomicBoolean displayed = new AtomicBoolean();
        playCue(cues, 0, ticket, showAtStart, displayed);
    }
    private void playCue(List<Cue> cues, int position, long ticket,
                         Runnable showAtStart, AtomicBoolean displayed) {
        if (closing || ticket != speechRevision) return;
        if (AudioOwnership.assistantOwns(root)) {
            stopNarration("Paused for your conversation."); return;
        }
        if (position >= cues.size()) {
            speaking = false; elapsed = 0; presenter.rest(); sceneView.pause(); clearFocus();
            voiceStatus.setText("Heart / Playback completed"); publishState(true); return;
        }
        Cue cue = cues.get(position); presenter.prepare(); sceneView.pause();
        voiceStatus.setText("Heart / Preparing step " + (position + 1) + " / " + cues.size());
        voice.speak(cue.text(), () -> {
            CompletableFuture<Boolean> ready = new CompletableFuture<>();
            Platform.runLater(() -> {
                try {
                    if (closing || ticket != speechRevision || AudioOwnership.assistantOwns(root)) {
                        ready.complete(false); return;
                    }
                    if (displayed.compareAndSet(false, true) && showAtStart != null) showAtStart.run();
                    highlight(cue.focus());
                    voiceStatus.setText("Heart / Speaking step " + (position + 1) + " / " + cues.size());
                    ready.complete(true);
                } catch (Throwable error) { ready.completeExceptionally(error); }
            });
            try {
                if (!ready.get(5, TimeUnit.SECONDS)) throw new CancellationException("Audio ownership changed.");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt(); throw new CancellationException("Interrupted.");
            } catch (ExecutionException | TimeoutException error) {
                throw new IllegalStateException("The interface could not synchronize narration.", error);
            }
        }).whenComplete((result, error) -> Platform.runLater(() -> {
            if (closing || ticket != speechRevision) return;
            if (error != null || result == null || !result.spoken()) {
                speaking = false; presenter.rest(); sceneView.pause(); clearFocus();
                if (displayed.compareAndSet(false, true) && showAtStart != null) showAtStart.run();
                // Do not automatically retry an audio failure every twelve seconds.
                narrationEnabled = false; playing = false; updateButtons();
                voiceStatus.setText("Voice stopped or unavailable. Text remains available.");
                publishState(true); return;
            }
            playCue(cues, position + 1, ticket, showAtStart, displayed);
        }));
    }
    private void select(int requested) {
        if (loading || closing) return;
        selectionRevision++; cancelSpeech(); elapsed = 0; currentAnalysis = "";
        readAnalysis.setDisable(true);
        if (entries.isEmpty()) {
            selectionPending = false; counter.setText("0 / 0"); risk.setText("NO EVENTS");
            source.setText("—"); details.setText("No recorded incident matches this query.");
            explanation.clear(); analyze.setDisable(true); return;
        }
        targetIndex = Math.floorMod(requested, entries.size());
        int selected = targetIndex; long revision = selectionRevision;
        if (narrationEnabled && AudioOwnership.assistantOwns(root)) {
            applyEntry(selected); resumeWhenAllowed = true;
            voiceStatus.setText("Replay prepared. Waiting for the conversation audio channel.");
            return;
        }
        if (narrationEnabled && !analysisPending) {
            selectionPending = true; analyze.setDisable(true);
            counter.setText("Preparing " + (selected + 1) + " / " + entries.size());
            playCues(eventCues(entries.get(selected)), () -> {
                if (revision == selectionRevision && !loading) applyEntry(selected);
            });
        } else applyEntry(selected);
    }
    private void applyEntry(int selected) {
        if (selected < 0 || selected >= entries.size()) return;
        index = selected; targetIndex = selected; selectionPending = false;
        GlobeEvent event = entries.get(index).event();
        sceneView.setEvent(entries.get(index).raw());
        if (sceneView.recognizedScene()) sceneTabs.getSelectionModel().select(1);
        counter.setText((index + 1) + " / " + entries.size()); risk.setText(event.level());
        risk.setTextFill(switch (event.level()) {
            case "CRITICAL" -> Color.web("#ff657e"); case "HIGH" -> Color.web("#ffa76b");
            case "MEDIUM" -> Color.web("#edcf7a"); default -> Color.web("#75e3bf");
        });
        source.setText(event.sourceIp());
        details.setText("TIMESTAMP\n" + event.timestamp() + "\n\nGLOBAL SCORE\n"
                + (event.score() == null ? "Not recorded" : event.score() + " / 100")
                + "\n\nBEHAVIOR\n" + event.behavior() + "\n\nANOMALY\n" + event.anomaly()
                + "\n\nRECORDED POLICY ACTION\n" + event.action()
                + "\n\nCONTAINMENT REQUESTED\n" + event.containmentRequested()
                + "\n\nDECOY ACTIVE\n" + state(event.decoyActive())
                + "\n\nSANDBOX ACTIVE\n" + state(event.sandboxActive())
                + "\n\nLOCATION\n" + (event.local() ? "Local / private network"
                : event.hasGeo() ? event.country() : "Unknown")
                + "\n\nGeographic markers are not connected."
                + "\n\nA containment request does not confirm that network traffic was blocked.");
        details.positionCaret(0); explanation.setText("Select AI ANALYZE to explain this event.");
        analysisStatus.setText(analysisPending ? "A previous analysis is still running."
                : "Local analysis / No incident upload");
        analyze.setDisable(analysisPending); publishState(true);
    }
    private void analyzeSelected() {
        if (closing || loading || selectionPending || entries.isEmpty() || analysisPending) return;
        cancelSpeech(); long queryTicket = queryRevision;
        long selectionTicket = selectionRevision; long expectedSpeech = speechRevision;
        JsonObject snapshot = entries.get(index).raw().deepCopy();
        analysisPending = true; currentAnalysis = ""; analyze.setDisable(true);
        analyze.setText("ANALYZING..."); readAnalysis.setDisable(true); playing = false;
        updateButtons(); presenter.prepare();
        analysisStatus.setText("Local Qwen analysis in progress...");
        explanation.setText("Preparing the explanation...");
        worker.submit(() -> {
            try {
                GlobeAnalysis.Result answer = new GlobeAnalysis().analyze(snapshot);
                Platform.runLater(() -> {
                    if (closing || queryTicket != queryRevision) return;
                    analysisPending = false; analyze.setText("AI ANALYZE");
                    analyze.setDisable(entries.isEmpty() || selectionPending);
                    if (selectionTicket != selectionRevision) return;
                    String answerText = answer.response(); currentAnalysis = answerText;
                    Runnable show = () -> {
                        explanation.setText(answerText); explanation.positionCaret(0);
                        analysisStatus.setText("Source: " + answer.source());
                        readAnalysis.setDisable(answerText.isBlank());
                    };
                    if (narrationEnabled && speechRevision == expectedSpeech && !answerText.isBlank()) {
                        playCues(analysisCues(answerText), show);
                    } else {
                        show.run(); presenter.rest();
                        voiceStatus.setText("Analysis ready. Select READ ANALYSIS to hear it.");
                    }
                    publishState(true);
                });
            } catch (Exception error) {
                error.printStackTrace();
                Platform.runLater(() -> {
                    if (closing || queryTicket != queryRevision) return;
                    analysisPending = false; presenter.rest(); analyze.setText("AI ANALYZE");
                    analyze.setDisable(entries.isEmpty() || selectionPending);
                    if (selectionTicket == selectionRevision) {
                        analysisStatus.setText("Analysis failed.");
                        explanation.setText("The recorded event remains available in the INCIDENT tab.");
                    }
                });
            }
        });
    }
    private StackPane buildCenter() {
        sceneView = new AttackAnimationPane(
                () -> {
                    stopNarration("Scene selection changed. Select EXPLAIN SCENE to hear it.");
                    sceneView.refreshPhaseIndicator();
                    sceneTabs.getSelectionModel().select(1);
                },
                () -> {
                    playing = false; updateButtons(); sceneTabs.getSelectionModel().select(1);
                    playCues(sceneCues(sceneView.phases()), null);
                },
                () -> {
                    stopNarration("Silent animation / no traffic or payload execution.");
                    sceneTabs.getSelectionModel().select(1); sceneView.playSilently();
                });
        Tab earthTab = new Tab("EARTH", buildViewport()); earthTab.setClosable(false);
        Tab animationTab = new Tab("INCIDENT SCENE", sceneView); animationTab.setClosable(false);
        sceneTabs = new TabPane(earthTab, animationTab);
        StackPane center = new StackPane(sceneTabs, presenter.view());
        StackPane.setAlignment(presenter.view(), Pos.BOTTOM_RIGHT);
        StackPane.setMargin(presenter.view(), new Insets(0, 8, 100, 0));
        return center;
    }
    private StackPane buildViewport() {
        Sphere earth = new Sphere(185, 96);
        PhongMaterial material = new PhongMaterial(Color.web("#125b79"));
        material.setSpecularColor(Color.web("#679da9")); material.setSpecularPower(25);
        boolean textured = false;
        Path texture = root.resolve("src/main/resources/textures/earth-day.jpg");
        if (Files.isRegularFile(texture)) {
            Image image = new Image(texture.toUri().toString(), false);
            if (!image.isError()) {
                material.setDiffuseMap(image); material.setDiffuseColor(Color.WHITE); textured = true;
            }
        }
        earth.setMaterial(material);
        Sphere atmosphere = new Sphere(190, 64); atmosphere.setCullFace(CullFace.FRONT);
        atmosphere.setMaterial(new PhongMaterial(Color.color(0.15, 0.65, 1, 0.10)));
        Group planet = new Group(earth, atmosphere); planet.getTransforms().addAll(tilt, rotation);
        AmbientLight ambient = new AmbientLight(Color.web("#48546b"));
        PointLight light = new PointLight(Color.web("#e4f6ff"));
        light.setTranslateX(-350); light.setTranslateY(-220); light.setTranslateZ(-450);
        SubScene space = new SubScene(new Group(planet, ambient, light),
                700, 600, true, SceneAntialiasing.BALANCED);
        space.setFill(Color.TRANSPARENT);
        camera = new PerspectiveCamera(true); camera.setNearClip(0.1);
        camera.setFarClip(3000); camera.setTranslateZ(-720); space.setCamera(camera);
        Pane stars = new Pane(); stars.setMouseTransparent(true); Random random = new Random(42);
        for (int i = 0; i < 130; i++) {
            var star = new javafx.scene.shape.Circle(0.5 + random.nextDouble(),
                    Color.color(0.65, 0.85, 1, 0.15 + random.nextDouble() * 0.5));
            star.centerXProperty().bind(stars.widthProperty().multiply(random.nextDouble()));
            star.centerYProperty().bind(stars.heightProperty().multiply(random.nextDouble()));
            stars.getChildren().add(star);
        }
        Label note = label(textured ? "EARTH TEXTURE LOADED" : "EARTH TEXTURE NOT INSTALLED",
                11, "#76b7c6"); note.setMouseTransparent(true);
        StackPane view = new StackPane(stars, space, note);
        view.setMinSize(300, 300);
        StackPane.setAlignment(note, Pos.BOTTOM_LEFT);
        StackPane.setMargin(note, new Insets(0, 0, 18, 12));
        space.widthProperty().bind(view.widthProperty()); space.heightProperty().bind(view.heightProperty());
        space.setOnMousePressed(event -> { mouseX = event.getSceneX(); mouseY = event.getSceneY(); });
        space.setOnMouseDragged(event -> {
            rotation.setAngle(rotation.getAngle() + (event.getSceneX() - mouseX) * 0.4);
            tilt.setAngle(Math.max(-70, Math.min(70,
                    tilt.getAngle() - (event.getSceneY() - mouseY) * 0.3)));
            mouseX = event.getSceneX(); mouseY = event.getSceneY();
        });
        space.setOnScroll(event -> camera.setTranslateZ(Math.max(-1200,
                Math.min(-440, camera.getTranslateZ() + event.getDeltaY()))));
        return view;
    }
    private void startAnimation() {
        animation = new AnimationTimer() {
            @Override public void handle(long now) {
                if (lastFrame == 0) { lastFrame = now; return; }
                double seconds = Math.min(0.1, (now - lastFrame) / 1_000_000_000.0);
                lastFrame = now;
                if (!playing) return;
                rotation.setAngle((rotation.getAngle() + seconds * 4) % 360);
                if (loading || speaking || analysisPending || selectionPending) { elapsed = 0; return; }
                elapsed += seconds;
                if (elapsed >= 12 && entries.size() > 1) select(index + 1);
            }
        }; animation.start();
    }
    private static String value(JsonObject object, String key) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString() : "";
    }
    private static String state(Boolean value) { return value == null ? "Not recorded" : value.toString(); }
    private static void configureText(TextArea area) {
        area.setEditable(false); area.setWrapText(true);
        area.setStyle("-fx-control-inner-background:#091521;-fx-text-fill:#c4d6df;-fx-font-size:14px;");
    }
    private static Label label(String text, double size, String color) {
        Label result = new Label(text);
        result.setStyle("-fx-font-size:" + size + "px;-fx-text-fill:" + color + ";"); return result;
    }
    private static Button button(String text) {
        Button result = new Button(text);
        result.setStyle("-fx-background-color:#10313c;-fx-text-fill:#c5ffeb;"
                + "-fx-background-radius:9;-fx-padding:10 17;-fx-cursor:hand;"); return result;
    }
    @Override public void stop() {
        if (resourcesStopped) return;
        resourcesStopped = true; closing = true; speechRevision++;
        speaking = false; narrationEnabled = false; playing = false;
        if (animation != null) animation.stop();
        if (presenter != null) presenter.stop();
        if (sceneView != null) sceneView.stop();
        requests.shutdownNow(); voice.stopSpeech(); voice.close(); worker.shutdownNow();
        publishState(true);
    }
    public static void main(String[] args) { launch(args); }
}
