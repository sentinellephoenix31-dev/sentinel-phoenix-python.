import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.vosk.Model;
import org.vosk.Recognizer;
import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.TargetDataLine;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.text.Normalizer;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Locale;
import java.util.UUID;

public final class VoiceAssistant {
    public static final String VERSION = "4.6-INCIDENT-SCENES";
    private static final AudioFormat FORMAT = new AudioFormat(16000, 16, 1, true, false);
    private static final String WAKE_GRAMMAR = "[\"hey sentinel\", \"[unk]\"]";
    private static final int MAX_SPEECH_SECONDS = 10;
    private enum SessionResult { STANDBY, REPLAY, SHUTDOWN }
    private final Path root;
    private final LocalFaceCamera faceCamera;
    private volatile boolean running = true;
    private volatile TargetDataLine activeMicrophone;
    private volatile Process orbProcess;
    private boolean faceGreetingDelivered;
    private boolean cameraTopic;

    public VoiceAssistant(Path root) {
        this.root = root.toAbsolutePath().normalize();
        faceCamera = new LocalFaceCamera(this.root);
    }
    private synchronized boolean writeJson(String filename, JsonObject data) {
        Path temporary = null;
        try {
            Path directory = root.resolve("data"); Files.createDirectories(directory);
            temporary = Files.createTempFile(directory, "sentinel-update-", ".tmp");
            Files.writeString(temporary, data.toString(), StandardCharsets.UTF_8);
            Path destination = directory.resolve(filename);
            try { Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException error) {
                Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING);
            }
            return true;
        } catch (Exception error) { System.err.println("[ORB UPDATE] " + error); return false; }
        finally {
            if (temporary != null) try { Files.deleteIfExists(temporary); }
            catch (Exception ignored) {}
        }
    }
    private void setState(String state, String caption) { setState(state, caption, ""); }
    private void setState(String state, String caption, String gesture) {
        JsonObject data = new JsonObject();
        data.addProperty("state", state); data.addProperty("caption", caption);
        data.addProperty("updated_at", Instant.now().toString());
        if (!gesture.isBlank()) data.addProperty("gesture", gesture);
        writeJson("voice-state.json", data);
    }
    private String sendOrbCommand(String action) throws InterruptedException {
        String id = UUID.randomUUID().toString(); JsonObject request = new JsonObject();
        request.addProperty("id", id); request.addProperty("action", action);
        if (!writeJson("orb-command.json", request)) return "WRITE_FAILED";
        System.out.println("[ORB COMMAND] " + action);
        long deadline = System.nanoTime() + 3_000_000_000L;
        Path file = root.resolve("data/orb-ack.json");
        while (running && System.nanoTime() < deadline) {
            try {
                if (Files.isRegularFile(file)) {
                    JsonObject result = JsonParser.parseString(
                            Files.readString(file, StandardCharsets.UTF_8)).getAsJsonObject();
                    if (id.equals(value(result, "id"))) return value(result, "status");
                }
            } catch (IOException | RuntimeException ignored) {}
            Thread.sleep(40);
        }
        return "TIMEOUT";
    }
    private void animateTask(String action) throws InterruptedException {
        if (!"COMPLETED".equals(sendOrbCommand(action))) sendOrbCommand("RESET_PROPS");
    }
    private boolean launchOrb() {
        if (orbProcess != null && orbProcess.isAlive()) return true;
        try {
            Path java = Path.of(System.getProperty("java.home"), "bin", "java.exe");
            Files.createDirectories(root.resolve("data"));
            orbProcess = new ProcessBuilder(java.toString(), "--enable-native-access=ALL-UNNAMED",
                    "-cp", System.getProperty("java.class.path"), "OrbLauncher")
                    .directory(root.toFile()).redirectErrorStream(true)
                    .redirectOutput(ProcessBuilder.Redirect.appendTo(
                            root.resolve("data/orb.log").toFile())).start();
            return true;
        } catch (Exception error) { System.err.println("[ORB] " + error); return false; }
    }
    private String showOrb() throws InterruptedException {
        if (orbProcess == null || !orbProcess.isAlive()) {
            if (!launchOrb()) return "START_FAILED";
            Thread.sleep(1500);
        }
        return sendOrbCommand("SHOW");
    }

    /* No spoken reply or command capture until the globe has stopped. */
    private void acquireConversationAudio() throws Exception {
        AudioOwnership.claim(root, "ASSISTANT");
        GlobeControl.Result result = GlobeControl.send("STOP_NARRATION");
        if (!result.confirmed() && !"NOT_RUNNING".equals(result.status())) {
            throw new IOException("The globe did not confirm audio suspension ("
                    + result.status() + "). Use STOP VOICE in the globe, then call me again.");
        }
    }
    private void releaseAudio(String owner) throws IOException {
        AudioOwnership.claim(root, owner);
        System.out.println("[AUDIO OWNER] " + owner);
    }
    private static String normalize(String text) {
        return Normalizer.normalize(text == null ? "" : text, Normalizer.Form.NFKD)
                .replaceAll("\\p{M}+", "").toLowerCase(Locale.ROOT)
                .replaceAll("[^\\p{L}\\p{N}\\s]", " ").replaceAll("\\s+", " ").strip();
    }
    private static String commandText(String question) {
        return normalize(question).replaceFirst("^(?:hey )?(?:sentinel|sentinelle)\\s+", "")
                .replaceFirst("^please\\s+", "")
                .replaceFirst("^(?:can|could|would|will) you\\s+", "")
                .replaceFirst("^please\\s+", "").replaceFirst("\\s+please$", "").strip();
    }
    private String cameraIntent(String question) {
        String text = commandText(question);
        if (text.matches("(?:(?:open|start|enable|turn on) (?:the |my |your )?(?:camera|webcam)"
                + "|(?:ouvre|active) (?:la |ta )?(?:camera|webcam))")) return "OPEN";
        if (text.matches("(?:(?:close|stop|disable|turn off|shut down) (?:the |my |your )?(?:camera|webcam)"
                + "|(?:ferme|coupe|desactive|arrete) (?:la |ta )?(?:camera|webcam))")) return "CLOSE";
        if (text.matches("(?:do you recognize me|do you recognise me|recognize me|recognise me"
                + "|who do you see|see my face|can you see my face|tu me reconnais"
                + "|est ce que tu me reconnais|qui vois tu)")) return "IDENTIFY";
        if (text.matches("(?:forget my face|delete my face|delete my face profile"
                + "|oublie mon visage|supprime mon profil facial)")) return "FORGET";
        if (text.matches("(?:remember my face|save my face|retiens mon visage|memorise mon visage)")) {
            return "ENROLL";
        }
        if (cameraTopic && text.matches("(?:open|open it|ouvre|ouvre la)")) return "OPEN";
        if (cameraTopic && text.matches("(?:close|close it|ferme|ferme la)")) return "CLOSE";
        return "";
    }
    private boolean handleCameraCommand(String question, KokoroVoice voice) throws Exception {
        String intent = cameraIntent(question); if (intent.isEmpty()) return false;
        cameraTopic = true; System.out.println("[CAMERA COMMAND] " + intent);
        switch (intent) {
            case "OPEN" -> {
                String state = faceCamera.observation().state();
                if ("OFF".equals(state) || "ERROR".equals(state)) {
                    setState("PREPARING", "Preparing the camera"); animateTask("CAMERA_OPEN");
                }
                String result = faceCamera.open();
                System.out.println("[CAMERA RESULT] OPEN: " + result);
                if ("STARTING".equals(result)) {
                    faceGreetingDelivered = false; say(voice, "Opening the camera.");
                } else if ("ALREADY_OPEN".equals(result)) say(voice, "The camera window is already open.");
                else if ("STOPPING".equals(result)) say(voice, "The camera is still closing. Try again in a moment.");
                else say(voice, "The camera service is unavailable.");
            }
            case "CLOSE" -> {
                if (!"OFF".equals(faceCamera.observation().state())) {
                    setState("PREPARING", "Closing the camera"); animateTask("CAMERA_CLOSE");
                }
                boolean stopped = faceCamera.stopCamera(); faceGreetingDelivered = false;
                System.out.println("[CAMERA RESULT] CLOSE: " + (stopped ? "COMPLETED" : "STOPPING"));
                say(voice, stopped ? "Camera closed." : "The camera is still stopping. "
                        + "The current face observation has been cleared.");
            }
            case "FORGET" -> {
                String result = faceCamera.forgetFace(); faceGreetingDelivered = false;
                System.out.println("[CAMERA RESULT] FORGET: " + result);
                say(voice, switch (result) {
                    case "DELETED" -> "Your saved face profile has been deleted. Your personal notes are separate.";
                    case "NO_PROFILE" -> "There is no saved face profile to delete.";
                    case "PROFILE_BUSY" -> "Close the separate enrollment window, then ask me again.";
                    default -> "The camera is still stopping. The face profile has not been deleted.";
                });
            }
            case "IDENTIFY" -> identify(voice);
            case "ENROLL" -> say(voice, "Face enrollment still uses FaceMemoryWindow. "
                    + "Close this camera, open that window, and choose Remember my face.");
            default -> {}
        }
        return true;
    }
    private void identify(KokoroVoice voice) throws Exception {
        LocalFaceCamera.Observation observed = faceCamera.observation();
        System.out.println("[CAMERA RESULT] IDENTIFY: " + observed.state());
        if (observed.recognized()) {
            faceGreetingDelivered = true;
            say(voice, "Your face matches the saved profile for " + observed.name() + ".", "NOD"); return;
        }
        say(voice, switch (observed.state()) {
            case "OFF" -> "The camera is off. Say open the camera first.";
            case "STARTING" -> "The camera is still starting.";
            case "STOPPING" -> "The camera is stopping.";
            case "NO_PROFILE" -> "No face profile is saved yet.";
            case "NO_FACE" -> "I don't currently detect a face.";
            case "MULTIPLE_FACES" -> "There is more than one face. Please stay alone in view.";
            case "TOO_SMALL" -> "Move a little closer to the camera.";
            case "CHECKING" -> "I'm still checking. Look toward the camera.";
            case "ERROR" -> "The camera encountered an error. Please check the voice log.";
            case "STALE", "NO_FRAME" -> "I don't have a recent usable camera result.";
            default -> "I can't confidently match your face to the saved profile.";
        });
    }
    private void greetRecognizedPerson(KokoroVoice voice) throws Exception {
        if (faceGreetingDelivered) return;
        LocalFaceCamera.Observation observed = faceCamera.observation();
        if (observed.recognized()) {
            faceGreetingDelivered = true; say(voice, "Hello, " + observed.name() + ".", "WAVE");
        }
    }
    private static boolean isTechnicalQuestion(String question) {
        return normalize(question).matches(".*\\b(?:cybersecurity|security|honeypot|sandbox|malware"
                + "|ransomware|trojan|phishing|injection|firewall|encryption|cryptography|algorithm"
                + "|database|network|protocol|vulnerability|vulnerabilities|exploit|cpu|gpu|java|python"
                + "|sql|tcp|udp|securite|reseau|chiffrement|algorithme|vulnerabilite|pare feu)\\b.*");
    }
    private static String orbIntent(String question) {
        String text = commandText(question);
        if (text.matches("(?:close yourself|hide yourself|hide the orb|close the orb|go away|cache toi|ferme toi)")) return "HIDE";
        if (text.matches("(?:come back|show yourself|show the orb|open the orb|reviens|montre toi)")) return "SHOW";
        return "";
    }
    private static boolean isStandbyCommand(String question) {
        return commandText(question).matches("(?:that s all|thats all|that is all|we re done|we are done"
                + "|go to sleep|stop listening|end conversation|end the conversation|c est tout"
                + "|retourne en veille|mets toi en veille|arrete d ecouter|fin de conversation)");
    }
    private static boolean isMicrophoneCloseCommand(String question) {
        return commandText(question).matches("(?:(?:close|stop|disable|turn off) (?:the |my )?microphone"
                + "|(?:ferme|coupe|desactive|arrete) (?:le |mon )?(?:micro|microphone))");
    }
    private static void amplify(byte[] audio, int count) {
        if (count < 2) return;
        double sum = 0; int peak = 0;
        for (int i = 0; i + 1 < count; i += 2) {
            int sample = (short) ((audio[i] & 255) | (audio[i + 1] << 8));
            sum += sample * (double) sample; peak = Math.max(peak, Math.abs(sample));
        }
        double rms = Math.sqrt(sum / (count / 2.0)) / 32768.0;
        double gain = 1;
        if (rms >= 0.0005 && peak > 0) gain = Math.min(Math.min(12, 0.055 / rms), 28000.0 / peak);
        for (int i = 0; i + 1 < count; i += 2) {
            int sample = (short) ((audio[i] & 255) | (audio[i + 1] << 8));
            int adjusted = Math.max(-32768, Math.min(32767, (int) Math.round(sample * gain)));
            audio[i] = (byte) adjusted; audio[i + 1] = (byte) (adjusted >> 8);
        }
    }
    private boolean waitForWakeWord(Model model) throws Exception {
        TargetDataLine microphone = AudioSystem.getTargetDataLine(FORMAT);
        try (Recognizer recognizer = new Recognizer(model, 16000, WAKE_GRAMMAR)) {
            activeMicrophone = microphone; microphone.open(FORMAT); microphone.start();
            setState("WAITING", "Say Hey Sentinel, then pause");
            System.out.println("[WAKE] STRICT: say Hey Sentinel, then pause.");
            byte[] buffer = new byte[4000];
            while (running) {
                int count = microphone.read(buffer, 0, buffer.length);
                if (count <= 0) continue;
                amplify(buffer, count);
                if (!recognizer.acceptWaveForm(buffer, count)) continue;
                JsonObject result = JsonParser.parseString(recognizer.getResult()).getAsJsonObject();
                String text = value(result, "text").toLowerCase(Locale.ROOT).replaceAll("\\s+", " ").strip();
                if (text.equals("hey sentinel")) {
                    System.out.println("[WAKE ACCEPTED] Final exact phrase."); return true;
                }
                if (!text.isBlank()) System.out.println("[WAKE REJECTED] Final phrase did not match.");
            }
            return false;
        } finally {
            if (microphone.isOpen()) { microphone.stop(); microphone.close(); }
            activeMicrophone = null;
        }
    }
    private void say(KokoroVoice voice, String text) throws Exception { say(voice, text, ""); }
    private void say(KokoroVoice voice, String text, String gesture) throws Exception {
        acquireConversationAudio();
        System.out.println("[SENTINEL] " + text);
        setState("PREPARING", "Preparing Heart voice");
        KokoroVoice.Result result = voice.speak(text,
                () -> setState("SPEAKING", "Heart is speaking", gesture)).join();
        System.out.println("[VOICE RESULT] " + result);
        if (!result.spoken()) setState("ERROR", "Voice unavailable; read the log");
    }
    private SessionResult answerRequest(String question, CommandDispatcher dispatcher,
                                        KokoroVoice voice) throws Exception {
        boolean technical = isTechnicalQuestion(question);
        setState("THINKING", "Processing your request");
        // Release before starting the globe so its initial narration is not blocked.
        boolean visual = "VISUAL_INCIDENT_REPLAY".equals(CommandDispatcher.classifyRoute(question));
        if (visual) releaseAudio("REPLAY");
        try {
            if (technical) animateTask("EXPLAIN_BEGIN");
            JsonObject result = dispatcher.dispatch(question, "voice");
            System.out.println("[DISPATCH] " + result);
            String route = value(result, "route"); String status = value(result, "status");
            if ("VISUAL_INCIDENT_REPLAY".equals(route)
                    && ("LAUNCHED".equals(status) || "ALREADY_RUNNING".equals(status))) {
                releaseAudio("REPLAY"); faceCamera.stopCamera(); faceGreetingDelivered = false;
                // The replay now contains its own visual presenter. Keep only
                // that representation visible while the globe owns narration.
                sendOrbCommand("HIDE");
                setState("REPLAY", "Sentinel explains the selected incident in the globe");
                return SessionResult.REPLAY;
            }
            acquireConversationAudio();
            if ("EMPTY_COMMAND".equals(status)) {
                say(voice, "I couldn't understand the command. Please say it again."); return null;
            }
            String response = value(result, "response");
            say(voice, response.isBlank() ? "I couldn't complete that request." : response);
            if (result.has("continue") && !result.get("continue").isJsonNull()
                    && !result.get("continue").getAsBoolean()) {
                running = false; return SessionResult.SHUTDOWN;
            }
            return null;
        } finally {
            if (technical && running) animateTask("EXPLAIN_END");
        }
    }
    private SessionResult conversation(VoiceInput input, CommandDispatcher dispatcher,
                                        KokoroVoice voice) throws Exception {
        System.out.println("[CONVERSATION] Session opened."); cameraTopic = false;
        int empty = 0; int unclear = 0;
        while (running) {
            acquireConversationAudio(); greetRecognizedPerson(voice); Thread.sleep(350);
            setState("LISTENING", "Your turn - say That's all to finish");
            String captured = input.listen(MAX_SPEECH_SECONDS);
            String question = captured == null ? "" : captured.strip();
            if (input.lastOutcome() == VoiceInput.Outcome.CONFIRM_COMMAND) {
                String proposed = input.suggestedCommand();
                String spoken = proposed.replaceFirst("[.!?]+$", "");
                say(voice, "Did you mean " + spoken + "? Say yes or no.");
                acquireConversationAudio();
                Thread.sleep(350);
                setState("LISTENING", "Confirm the proposed command: yes or no");
                String confirmation = input.listenConfirmation(4);
                boolean accepted = normalize(confirmation).matches(
                        "(?:yes|yes please|yes do it|yes that s right|yeah|yep|correct|that s right|oui)");
                if (!accepted) {
                    System.out.println("[COMMAND CANCELLED] " + proposed);
                    say(voice, "Cancelled. Please repeat your request if needed.");
                    continue;
                }
                question = proposed;
                System.out.println("[COMMAND CONFIRMED] " + question);
            }
            if (question.isBlank()) {
                if (input.lastOutcome() == VoiceInput.Outcome.UNUSABLE_TRANSCRIPTION) {
                    empty = 0;
                    if (++unclear >= 2) {
                        say(voice, "I still couldn't understand. Call me again when you're ready.");
                        return SessionResult.STANDBY;
                    }
                    say(voice, "I couldn't understand that. Please repeat the command."); continue;
                }
                greetRecognizedPerson(voice);
                if (++empty >= 2) return SessionResult.STANDBY;
                continue;
            }
            empty = 0; unclear = 0; System.out.println("[YOU] " + question);
            if (normalize(question).equals("hey sentinel")) { say(voice, "I'm here."); continue; }
            if (isMicrophoneCloseCommand(question)) {
                boolean stopped = faceCamera.stopCamera();
                say(voice, stopped ? "Microphone and camera closed. Restart the voice assistant when you need me."
                        : "Stopping the voice assistant and camera.");
                running = false; return SessionResult.SHUTDOWN;
            }
            if (isStandbyCommand(question)) {
                boolean stopped = faceCamera.stopCamera(); faceGreetingDelivered = false;
                say(voice, stopped ? "Okay. Call me when you need me."
                        : "Returning to standby. The camera is still stopping.");
                return SessionResult.STANDBY;
            }
            String orbAction = orbIntent(question);
            if ("HIDE".equals(orbAction)) {
                boolean stopped = faceCamera.stopCamera(); faceGreetingDelivered = false;
                say(voice, stopped ? "See you soon." : "See you soon. The camera is still stopping.");
                sendOrbCommand("HIDE"); return SessionResult.STANDBY;
            }
            if ("SHOW".equals(orbAction)) {
                cameraTopic = false;
                say(voice, "COMPLETED".equals(showOrb()) ? "Here I am."
                        : "I couldn't confirm the orb is visible."); continue;
            }
            if (handleCameraCommand(question, voice)) continue;
            cameraTopic = false;
            SessionResult result = answerRequest(question, dispatcher, voice);
            if (result != null) return result;
        }
        return SessionResult.SHUTDOWN;
    }
    private static String value(JsonObject object, String key) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString() : "";
    }
    public void run() throws Exception {
        Path wakeModel = root.resolve("models/wake/vosk-model-small-en-us-0.15");
        if (!Files.isRegularFile(wakeModel.resolve("am/final.mdl"))) {
            throw new IllegalStateException("Wake model missing: " + wakeModel);
        }
        releaseAudio("IDLE"); setState("STARTING", "Loading local voice services"); launchOrb();
        Thread shutdown = new Thread(() -> {
            running = false;
            TargetDataLine microphone = activeMicrophone;
            if (microphone != null) microphone.close();
            faceCamera.close();
            try { AudioOwnership.claim(root, "IDLE"); } catch (IOException ignored) {}
            if (orbProcess != null && orbProcess.isAlive()) orbProcess.destroy();
        }, "sentinel-voice-shutdown");
        Runtime.getRuntime().addShutdownHook(shutdown);
        try {
            BrainConversation brain = new BrainConversation(root, ZoneId.of("Asia/Kolkata"));
            CommandDispatcher dispatcher = new CommandDispatcher(brain);
            try (Model model = new Model(wakeModel.toString());
                 KokoroVoice voice = new KokoroVoice(root);
                 VoiceInput input = new VoiceInput(root, model)) {
                // Reuse the wake model; do not load a second native model.
                setState("PREPARING", "Loading Heart voice");
                if (!voice.warmUp().join()) System.err.println("[VOICE] Heart warm-up failed.");
                System.out.println("[SENTINEL] Voice version: " + VERSION);
                System.out.println("[SENTINEL] Camera starts OFF.");
                while (running) {
                    try {
                        if (!waitForWakeWord(model)) break;
                        // Pause and acknowledge the replay BEFORE I'm listening.
                        acquireConversationAudio();
                        String showStatus = showOrb();
                        if (!"COMPLETED".equals(showStatus)) System.err.println("[ORB] SHOW: " + showStatus);
                        say(voice, "I'm listening.");
                        SessionResult result = conversation(input, dispatcher, voice);
                        System.out.println("[CONVERSATION] Session result: " + result);
                        if (result == SessionResult.SHUTDOWN) break;
                        faceCamera.stopCamera(); faceGreetingDelivered = false; cameraTopic = false;
                        sendOrbCommand("RESET_PROPS");
                        if (result == SessionResult.STANDBY) releaseAudio("IDLE");
                        Thread.sleep(600);
                    } catch (InterruptedException error) {
                        Thread.currentThread().interrupt(); running = false; break;
                    } catch (Exception error) {
                        if (!running) break;
                        faceCamera.stopCamera(); faceGreetingDelivered = false; cameraTopic = false;
                        sendOrbCommand("RESET_PROPS");
                        setState("ERROR", "Request interrupted. Check the voice log or the globe STOP button.");
                        System.err.println("[VOICE ERROR] " + error); error.printStackTrace();
                        releaseAudio("IDLE"); Thread.sleep(1000);
                    }
                }
            }
        } finally {
            running = false; faceCamera.close();
            try { releaseAudio("IDLE"); } catch (IOException error) { System.err.println(error); }
            setState("OFFLINE", "Voice assistant stopped");
            if (orbProcess != null && orbProcess.isAlive()) orbProcess.destroy();
            try { Runtime.getRuntime().removeShutdownHook(shutdown); }
            catch (IllegalStateException ignored) {}
        }
    }
    public static void main(String[] args) {
        System.setOut(new PrintStream(System.out, true, StandardCharsets.UTF_8));
        System.setErr(new PrintStream(System.err, true, StandardCharsets.UTF_8));
        int code = 0;
        try { new VoiceAssistant(Path.of(".")).run(); }
        catch (Exception error) {
            code = 1; System.err.println("[SENTINEL ERROR] " + error); error.printStackTrace();
        }
        System.exit(code);
    }
}
