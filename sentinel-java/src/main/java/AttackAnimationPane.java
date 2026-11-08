import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import javafx.animation.AnimationTimer;
import javafx.geometry.Insets;
import javafx.geometry.Point3D;
import javafx.scene.*;
import javafx.scene.canvas.Canvas;
import javafx.scene.canvas.GraphicsContext;
import javafx.scene.control.*;
import javafx.scene.layout.*;
import javafx.scene.paint.Color;
import javafx.scene.paint.PhongMaterial;
import javafx.scene.shape.*;
import javafx.scene.text.Font;
import javafx.scene.text.Text;
import javafx.scene.transform.Rotate;
import java.util.ArrayList;
import java.util.List;

/** Inert 3D storyboards. They never send packets, execute payloads or alter files. */
public final class AttackAnimationPane extends VBox {
    public record Phase(String text, String title) {}
    private final Label badge = new Label();
    private final Label title = new Label();
    private final Label facts = new Label();
    private final ComboBox<String> mode = new ComboBox<>();
    private final Label[] phaseLabels = new Label[4];
    private final Group world = new Group();
    private final Group model = new Group();
    private final Canvas reconstruction = new Canvas(760, 350);
    private boolean compatible = true;
    private final Rotate yaw = new Rotate(-10, Rotate.Y_AXIS);
    private final Rotate tilt = new Rotate(-5, Rotate.X_AXIS);
    private final List<Box> packets = new ArrayList<>();
    private final List<Sphere> ports = new ArrayList<>();
    private final List<Box> pages = new ArrayList<>();
    private final List<Node> fileLocks = new ArrayList<>();
    private final PhongMaterial cyan = material("#3ce4ca");
    private final PhongMaterial dark = material("#102c43");
    private final PhongMaterial metal = material("#54839c");
    private final PhongMaterial orange = material("#ffaf68");
    private final PhongMaterial red = material("#f16c8d");
    private final PhongMaterial paper = material("#bce6ec");
    private final PhongMaterial dim = material("#234152");
    private final Runnable changed;
    private final Runnable explain;
    private final Runnable animate;
    private final AnimationTimer timer;
    private JsonObject event = new JsonObject();
    private SceneCatalog.Kind recordedKind = SceneCatalog.Kind.UNKNOWN;
    private SceneCatalog.Kind kind = SceneCatalog.Kind.UNKNOWN;
    private List<Phase> phases = List.of();
    private Group sourceDevice;
    private Group targetDevice;
    private Box packageLid;
    private Node hiddenCore;
    private Node shield;
    private Text attemptLabel;
    private boolean preview;
    private boolean changing;
    private boolean running;
    private boolean automatic;
    private int phase;
    private long lastFrame;
    private double seconds;
    private double mouseX;
    private double mouseY;

    public AttackAnimationPane(Runnable changed, Runnable explain, Runnable animate) {
        this.changed = changed; this.explain = explain; this.animate = animate;
        setSpacing(10); setPadding(new Insets(8, 4, 4, 4));
        title.setStyle("-fx-font-size:21px;-fx-text-fill:#d6fff3;-fx-font-weight:bold;");
        title.setWrapText(true);
        badge.setStyle("-fx-font-size:11px;-fx-text-fill:#80e3d0;"); badge.setWrapText(true);
        facts.setStyle("-fx-text-fill:#a8c5d2;-fx-font-size:11px;"); facts.setWrapText(true);
        mode.getItems().add("RECORDED EVENT / AUTO");
        for (SceneCatalog.Kind item : SceneCatalog.Kind.values()) {
            if (item != SceneCatalog.Kind.UNKNOWN) mode.getItems().add("DEMO / " + item.title());
        }
        mode.getSelectionModel().select(0); mode.setPrefWidth(245);
        Button explainButton = button("EXPLAIN SCENE");
        Button animateButton = button("ANIMATE SILENTLY");
        explainButton.setOnAction(e -> this.explain.run());
        animateButton.setOnAction(e -> this.animate.run());
        mode.setOnAction(e -> {
            if (changing) return;
            int selected = mode.getSelectionModel().getSelectedIndex();
            preview = selected > 0;
            kind = preview ? SceneCatalog.Kind.values()[selected - 1] : recordedKind;
            rebuild(); this.changed.run();
        });
        Button renderer = button("VIEW: COMPATIBLE / SWITCH TO 3D");
        FlowPane controls = new FlowPane(8, 8, mode, explainButton, animateButton, renderer);
        AmbientLight ambient = new AmbientLight(Color.web("#61798d"));
        PointLight light = new PointLight(Color.web("#e1fff8"));
        light.setTranslateX(-300); light.setTranslateY(-350); light.setTranslateZ(-550);
        PointLight rim = new PointLight(Color.web("#586cdb"));
        rim.setTranslateX(350); rim.setTranslateY(70); rim.setTranslateZ(100);
        model.getTransforms().addAll(yaw, tilt); world.getChildren().addAll(model, ambient, light, rim);
        SubScene scene = new SubScene(world, 760, 350, true, SceneAntialiasing.BALANCED);
        scene.setFill(Color.TRANSPARENT);
        PerspectiveCamera camera = new PerspectiveCamera(true);
        camera.setFieldOfView(35); camera.setNearClip(0.1); camera.setFarClip(3000);
        camera.setTranslateX(55); camera.setTranslateY(25);
        camera.setTranslateZ(-650); scene.setCamera(camera);
        scene.setManaged(false); reconstruction.setManaged(false);
        scene.setVisible(false);
        Pane viewport = new Pane(scene, reconstruction) {
            @Override protected void layoutChildren() {
                double w = Math.max(1, getWidth()), h = Math.max(1, getHeight());
                scene.setWidth(w); scene.setHeight(h); scene.relocate(0, 0);
                reconstruction.setWidth(w); reconstruction.setHeight(h);
                reconstruction.relocate(0, 0);
                double vertical = 330, horizontal = 820;
                camera.setTranslateZ(-Math.max(vertical, horizontal * h / w)
                        / (2 * Math.tan(Math.toRadians(17.5))) - 100);
                drawReconstruction();
            }
        };
        viewport.setPrefSize(760, 350);
        viewport.setMinHeight(200); VBox.setVgrow(viewport, Priority.ALWAYS);
        viewport.setStyle("-fx-background-color:linear-gradient(to bottom,#071725,#04101c);"
                + "-fx-background-radius:16;-fx-border-color:#183b4c;-fx-border-radius:16;");
        renderer.setOnAction(e -> {
            compatible = !compatible;
            scene.setVisible(!compatible); reconstruction.setVisible(compatible);
            renderer.setText(compatible ? "VIEW: COMPATIBLE / SWITCH TO 3D"
                    : "VIEW: 3D / SWITCH TO COMPATIBLE");
            viewport.requestLayout(); drawReconstruction();
        });
        scene.setOnMousePressed(e -> { mouseX = e.getSceneX(); mouseY = e.getSceneY(); });
        scene.setOnMouseDragged(e -> {
            yaw.setAngle(Math.max(-35, Math.min(35, yaw.getAngle() + (e.getSceneX() - mouseX) * .2)));
            tilt.setAngle(Math.max(-25, Math.min(20, tilt.getAngle() - (e.getSceneY() - mouseY) * .15)));
            mouseX = e.getSceneX(); mouseY = e.getSceneY();
        });
        HBox steps = new HBox(6);
        for (int i = 0; i < 4; i++) {
            phaseLabels[i] = new Label(); phaseLabels[i].setWrapText(true);
            phaseLabels[i].setPrefWidth(0); phaseLabels[i].setMaxWidth(Double.MAX_VALUE);
            phaseLabels[i].setMinHeight(45); HBox.setHgrow(phaseLabels[i], Priority.ALWAYS);
            steps.getChildren().add(phaseLabels[i]);
        }
        getChildren().addAll(title, badge, controls, viewport, steps, facts);
        setMinSize(300, 300); rebuild();
        timer = new AnimationTimer() {
            @Override public void handle(long now) {
                double dt = lastFrame == 0 ? 0 : Math.min(.05, (now - lastFrame) / 1e9);
                lastFrame = now;
                if (running) {
                    seconds += dt;
                    if (automatic && seconds >= 3.5) {
                        if (phase < 3) { phase++; seconds = 0; updatePhaseLabels(); }
                        else { running = false; automatic = false; }
                    }
                }
                render();
            }
        }; timer.start();
    }
    public void setEvent(JsonObject raw) {
        event = raw.deepCopy(); List<String> indicators = new ArrayList<>();
        if (event.get("indicators") instanceof com.google.gson.JsonArray list) {
            for (JsonElement item : list) if (item.isJsonPrimitive()) indicators.add(item.getAsString());
        }
        recordedKind = SceneCatalog.detect(text(event, "payload"), text(event, "attack_type"),
                text(event, "behavior_type"), indicators);
        preview = false; kind = recordedKind;
        changing = true; mode.getSelectionModel().select(0); changing = false;
        rebuild();
    }
    public boolean recognizedScene() { return recordedKind != SceneCatalog.Kind.UNKNOWN; }
    public boolean previewMode() { return preview; }
    public List<Phase> phases() { return phases; }
    public Label phaseNode(int selected) { return phaseLabels[Math.max(0, Math.min(3, selected))]; }
    public void beginNarration() { running = false; automatic = false; }
    public void setPhase(int selected) {
        phase = Math.max(0, Math.min(3, selected)); seconds = 0;
        running = true; automatic = false; updatePhaseLabels();
    }
    public void playSilently() {
        phase = 0; seconds = 0; running = true; automatic = true; updatePhaseLabels();
    }
    public void pause() { running = false; automatic = false; }
    public void refreshPhaseIndicator() { updatePhaseLabels(); }
    public void stop() { timer.stop(); pause(); }

    private static String text(JsonObject object, String name) {
        JsonElement value = object.get(name);
        if (value == null || !value.isJsonPrimitive()) return "";
        String result = value.getAsString().replaceAll("\\p{Cntrl}", " ").replaceAll("\\s+", " ").strip();
        return result.length() > 220 ? result.substring(0, 220) + " ..." : result;
    }
    private static String recorded(JsonObject object, String name) {
        String value = text(object, name); return value.isBlank() ? "not recorded" : value;
    }
    private static Boolean flag(JsonObject object, String name) {
        JsonElement value = object.get(name);
        return value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isBoolean()
                ? value.getAsBoolean() : null;
    }
    private boolean active(String key) { return Boolean.TRUE.equals(flag(event, key)); }
    private static String flagDescription(JsonObject event, String key, String subject) {
        Boolean value = flag(event, key);
        return value == null ? subject + " was not recorded."
                : subject + (value ? " is recorded as active." : " is recorded as inactive.");
    }
    private List<Phase> recordedPhases() { return evidenceNarration(event); }
    public static List<Phase> evidenceNarration(JsonObject event) {
        String score = recorded(event, "global_score");
        String action = recorded(event, "response_action");
        Boolean containment = flag(event, "containment_requested");
        String containmentText = containment == null ? "Containment request status was not recorded."
                : containment ? "Containment was requested." : "Containment was not requested.";
        Boolean blocked = flag(event, "network_blocked");
        if (blocked == null) blocked = flag(event, "blocking_confirmed");
        String blockingText = blocked == null ? "This event does not confirm network blocking."
                : blocked ? "The log explicitly records network blocking."
                : "The log records network blocking as false.";
        String sandboxError = text(event, "sandbox_error");
        Boolean execution = flag(event, "payload_execution");
        String executionText = execution == null ? "Payload execution was not recorded."
                : execution ? "The payload execution flag is recorded as true."
                : "Payload execution is recorded as false.";
        boolean test = "SENTINEL_DEMO_TEST".equals(text(event, "payload"));
        return List.of(
                new Phase((test ? "This is the Sentinel demonstration connection, not a confirmed attack. " :
                        "This scene illustrates the selected recorded event. ")
                        + "Its recorded source address is " + recorded(event, "source_ip") + ".", "1 / ARRIVAL"),
                new Phase("The current event has global risk " + recorded(event, "global_level")
                        + ". Its recorded global score is " + score
                        + ". Historical source reputation is separate from this current event.", "2 / RISK"),
                new Phase("The recorded response is " + action + ". " + containmentText + " " + blockingText,
                        "3 / RESPONSE"),
                new Phase(flagDescription(event, "decoy_active", "The decoy") + " "
                        + flagDescription(event, "sandbox_active", "The sandbox")
                        + (sandboxError.isBlank() ? " " : " The recorded sandbox status is "
                        + sandboxError.replace('_', ' ') + ". ") + executionText,
                        "4 / DECOY / SANDBOX"));
    }
    private List<Phase> demonstrationPhases() {
        String mechanism;
        String impact;
        String control;
        switch (kind) {
            case CONNECTION_TEST -> {
                mechanism = "A harmless demonstration packet travels from a client to a listening service.";
                impact = "A connection alone does not prove malicious intent.";
                control = "A monitor can record the connection. A decoy is shown as an illustrative destination.";
            }
            case PORT_SCAN -> {
                mechanism = "The client contacts several numbered service ports to discover which services respond.";
                impact = "The moving lights represent probes, not a measured count from the selected incident.";
                control = "Rate controls and service exposure review are possible responses, not confirmed actions here.";
            }
            case BRUTE_FORCE -> {
                mechanism = "Repeated authentication attempts approach the same login gate.";
                impact = "The attempt counter is an illustration. It is not a recorded login history.";
                control = "Possible controls include rate limits and stronger authentication. No account is changed here.";
            }
            case SQL_INJECTION -> {
                mechanism = "User input approaches a database query boundary. Injection occurs when input is treated as query syntax.";
                impact = "The orange data tiles illustrate a boundary failure. No database query is executed.";
                control = "Parameterized queries keep values separate from query structure. This scene does not apply a patch.";
            }
            case XSS -> {
                mechanism = "Untrusted content reaches a browser page and may be interpreted as script.";
                impact = "The script tile is only a label. This demonstration executes no script.";
                control = "Context appropriate output encoding and other browser defenses can reduce risk. No site is modified.";
            }
            case COMMAND_INJECTION -> {
                mechanism = "Input crosses from an application into a system command boundary.";
                impact = "The branching tiles illustrate unintended command interpretation. No system command runs.";
                control = "Avoiding shell interpretation and strictly separating arguments are possible controls, not actions applied here.";
            }
            case PATH_TRAVERSAL -> {
                mechanism = "A file request moves through parent directories beyond the intended public folder.";
                impact = "The stairs represent path components. The demonstration reads no private files.";
                control = "Canonical path checks and directory confinement can enforce a boundary. No filesystem policy changes here.";
            }
            case CONNECTION_FLOOD -> {
                mechanism = "Many illustrated clients send connections toward a service with limited capacity.";
                impact = "The queue fills in the animation. These are not real packets or measured network load.";
                control = "Rate controls and upstream traffic handling are possible defenses. This is not a denial of service test.";
            }
            case TROJAN -> {
                mechanism = "A seemingly ordinary package reveals a concealed mechanism.";
                impact = "The red core is a visual metaphor. There is no executable or malware in this demonstration.";
                control = "Trusted software sources, analysis and isolation can help assess packages. No Trojan removal is claimed.";
            }
            case RANSOMWARE -> {
                mechanism = "An illustrated process reaches document tiles and changes them into locked symbols.";
                impact = "Only shapes change color. No files are opened, encrypted or deleted.";
                control = "Isolation and tested recovery copies are possible safeguards. The blue copy is an illustration, not a restored backup.";
            }
            default -> {
                mechanism = "A connection reaches a monitored service.";
                impact = "No attack family is identified by this generic illustration.";
                control = "The recorded evidence must be examined before claiming a specific defensive action.";
            }
        }
        return List.of(new Phase("Pedagogical preview. This is not a claim about the selected incident. "
                + mechanism, "1 / MECHANISM"), new Phase(impact, "2 / ILLUSTRATION"),
                new Phase(control, "3 / POSSIBLE CONTROL"),
                new Phase("This preview is complete. It did not send traffic, run payloads or apply patches.",
                        "4 / LIMITS"));
    }
    private void rebuild() {
        running = false; automatic = false; seconds = 0; phase = 0;
        model.getChildren().clear(); packets.clear(); ports.clear(); pages.clear(); fileLocks.clear();
        packageLid = null; hiddenCore = null; shield = null; attemptLabel = null;
        phases = preview ? demonstrationPhases() : recordedPhases();
        title.setText(kind.title());
        badge.setText(preview ? "PEDAGOGICAL PREVIEW / NOT A RECORDED DETECTION"
                : kind == SceneCatalog.Kind.CONNECTION_TEST
                    ? "RECORDED DEMO MARKER / TEST CONNECTION"
                    : kind == SceneCatalog.Kind.UNKNOWN
                        ? "RECORDED EVENT / NO SPECIFIC ATTACK FAMILY RECORDED"
                        : "RECORDED CLASSIFICATION / MECHANISM ILLUSTRATION");
        badge.setTextFill(preview ? Color.web("#ffcb86") : Color.web("#80e3d0"));
        facts.setText(preview ? "Illustration only. Counters, packets and defenses in this preview are simulated."
                : "SOURCE " + recorded(event, "source_ip") + "  /  GLOBAL "
                    + recorded(event, "global_level") + " " + recorded(event, "global_score")
                    + "  /  RESPONSE " + recorded(event, "response_action")
                    + "  /  DECOY " + recorded(event, "decoy_active")
                    + "  /  SANDBOX " + recorded(event, "sandbox_active"));
        model.getChildren().add(box(680, 3, 160, 0, 100, 25, dim));
        sourceDevice = kind == SceneCatalog.Kind.CONNECTION_TEST ? phone() : laptop();
        sourceDevice.setTranslateX(-250); sourceDevice.setTranslateY(0);
        sourceDevice.setRotationAxis(Rotate.Y_AXIS); sourceDevice.setRotate(15);
        model.getChildren().add(sourceDevice);
        label3D(kind == SceneCatalog.Kind.CONNECTION_TEST ? "DEMO CLIENT / TERMUX" : "INPUT / CLIENT",
                -250, 85, -40, "#91d4df");
        tube(new Point3D(-205, 5, 0), new Point3D(-80, 5, 0), 2, dim);
        tube(new Point3D(45, 5, 0), new Point3D(200, 5, 0), 2, dim);
        switch (kind) {
            case PORT_SCAN -> buildScan();
            case BRUTE_FORCE -> buildLogin();
            case SQL_INJECTION -> buildSql();
            case XSS -> buildXss();
            case COMMAND_INJECTION -> buildCommand();
            case PATH_TRAVERSAL -> buildPaths();
            case CONNECTION_FLOOD -> buildFlood();
            case TROJAN -> buildTrojan();
            case RANSOMWARE -> buildRansomware();
            default -> buildConnection();
        }
        int count = kind == SceneCatalog.Kind.CONNECTION_FLOOD ? 54 :
                kind == SceneCatalog.Kind.PORT_SCAN ? 18 : 9;
        for (int i = 0; i < count; i++) {
            Box packet = box(7, 7, 7, -220, 0, 0,
                    kind == SceneCatalog.Kind.CONNECTION_TEST || kind == SceneCatalog.Kind.UNKNOWN ? cyan : orange);
            packets.add(packet); model.getChildren().add(packet);
        }
        shield = box(7, 112, 82, 132, -5, 0, cyan);
        model.getChildren().add(shield);
        updatePhaseLabels(); render();
    }
    private void updatePhaseLabels() {
        for (int i = 0; i < phaseLabels.length; i++) {
            phaseLabels[i].setText(phases.get(i).title());
            phaseLabels[i].setStyle("-fx-font-size:10px;-fx-padding:7;-fx-background-radius:8;"
                    + (i == phase ? "-fx-background-color:#174a50;-fx-text-fill:#c9ffeb;"
                    : "-fx-background-color:#0a2030;-fx-text-fill:#7395a7;"));
        }
    }
    private void buildConnection() {
        model.getChildren().add(sphere(35, -35, 0, 0, cyan));
        label3D("SENTINEL / ANALYSIS", -35, 65, -40, "#afffe2");
        Group monitor = server(metal); monitor.setTranslateX(235); model.getChildren().add(monitor);
        label3D("MONITORED SERVICE", 235, 85, -40, "#b7d9e7");
        Group decoy = laptop(); decoy.setTranslateX(245); decoy.setTranslateY(145);
        decoy.setScaleX(.65); decoy.setScaleY(.65); decoy.setScaleZ(.65);
        model.getChildren().add(decoy);
        tube(new Point3D(50, 40, 0), new Point3D(225, 145, 0), 1.5, dim);
        label3D(preview ? "DECOY / ILLUSTRATION" : "DECOY: " + recorded(event, "decoy_active"),
                210, 192, -40, "#6fe3c7");
        label3D(preview ? "SANDBOX / ILLUSTRATION" : "SANDBOX: " + recorded(event, "sandbox_active"),
                -75, 168, -30, "#8b9dac");
        model.getChildren().add(box(60, 32, 35, -75, 130, 5, dim));
    }
    private void buildScan() {
        Group target = server(metal); target.setTranslateX(100); model.getChildren().add(target);
        int[] numbers = {22, 80, 443, 8080, 2222, 8178};
        for (int i = 0; i < numbers.length; i++) {
            double y = -85 + i * 29;
            Sphere light = sphere(5, 180, y, -20, dim); ports.add(light); model.getChildren().add(light);
            label3D("PORT " + numbers[i], 245, y + 5, -30, "#b1d7e7");
            tube(new Point3D(-170, 0, 0), new Point3D(180, y, 0), .9, dim);
        }
        label3D("SERVICE DISCOVERY", 80, -115, -30, "#ffcf9d");
    }
    private void buildLogin() {
        model.getChildren().add(box(70, 105, 20, 15, -5, 0, metal));
        model.getChildren().add(sphere(5, 38, 0, -17, cyan));
        attemptLabel = label3D("ILLUSTRATED ATTEMPT 1", 45, -95, -35, "#ffcd9e");
        label3D("LOGIN GATE", 15, 80, -30, "#bce3ee");
        for (int i = 0; i < 5; i++) model.getChildren().add(box(14, 22, 5, -135 + i * 27, 65, -10, orange));
        targetDevice = server(metal); targetDevice.setTranslateX(240); model.getChildren().add(targetDevice);
    }
    private void buildSql() {
        Group browser = browser("USER INPUT"); browser.setTranslateX(-45); model.getChildren().add(browser);
        Group db = database(); db.setTranslateX(225); model.getChildren().add(db);
        label3D("QUERY / VALUE BOUNDARY", 110, -95, -30, "#ffcf9d");
        label3D("DATABASE", 225, 80, -30, "#a5e7ed");
        model.getChildren().add(box(5, 100, 65, 100, 0, 5, dim));
    }
    private void buildXss() {
        Group page = browser("BROWSER PAGE"); page.setTranslateX(100); page.setScaleX(1.6);
        page.setScaleY(1.6); model.getChildren().add(page);
        label3D("UNTRUSTED CONTENT", -90, -85, -30, "#ffcf9d");
        model.getChildren().add(box(45, 34, 14, -80, 0, -25, orange));
        label3D("SCRIPT", -80, 5, -36, "#112237");
        label3D("DISPLAY ONLY / NO SCRIPT RUNS", 110, 115, -35, "#91bfd0");
    }
    private void buildCommand() {
        Group terminal = browser("APPLICATION"); terminal.setTranslateX(-20); model.getChildren().add(terminal);
        targetDevice = server(metal); targetDevice.setTranslateX(245); model.getChildren().add(targetDevice);
        label3D("INPUT / PROCESS BOUNDARY", 80, -95, -30, "#ffcf9d");
        for (int i = 0; i < 3; i++) {
            model.getChildren().add(box(22, 22, 22, 170 + i * 35, -85, 15, orange));
            tube(new Point3D(45, 0, 0), new Point3D(170 + i * 35, -85, 15), 1, dim);
        }
    }
    private void buildPaths() {
        String[] names = {"PUBLIC", "PARENT", "ROOT", "PRIVATE"};
        for (int i = 0; i < 4; i++) {
            Group folder = folder(); folder.setTranslateX(-90 + i * 100);
            folder.setTranslateY(65 - i * 40); model.getChildren().add(folder);
            label3D(names[i], -90 + i * 100, 105 - i * 40, -30, "#b9deeb");
            if (i < 3) tube(new Point3D(-60 + i * 100, 65 - i * 40, 0),
                    new Point3D(-20 + i * 100, 25 - i * 40, 0), 1.5, dim);
        }
        label3D("DIRECTORY BOUNDARY", 65, -125, -30, "#ffcf9d");
    }
    private void buildFlood() {
        for (int i = 0; i < 5; i++) {
            Group client = phone(); client.setScaleX(.45); client.setScaleY(.45); client.setScaleZ(.45);
            client.setTranslateX(-160 + (i % 2) * 45); client.setTranslateY(-90 + i * 43);
            client.setTranslateZ(40); model.getChildren().add(client);
        }
        targetDevice = server(metal); targetDevice.setTranslateX(235); model.getChildren().add(targetDevice);
        label3D("ILLUSTRATED QUEUE / LIMITED CAPACITY", 95, -115, -30, "#ffcf9d");
        for (int i = 0; i < 6; i++) model.getChildren().add(box(12, 12, 12, 85 + i * 19, 80, 0, dim));
    }
    private void buildTrojan() {
        model.getChildren().add(box(90, 70, 70, 5, 5, 0, metal));
        packageLid = box(98, 9, 78, 5, -35, 0, cyan); model.getChildren().add(packageLid);
        hiddenCore = sphere(21, 5, -12, -35, red); model.getChildren().add(hiddenCore);
        label3D("APPARENT PACKAGE", 5, 95, -45, "#b9deeb");
        label3D("CONCEALED MECHANISM", 155, -90, -40, "#ffa2b6");
        targetDevice = server(metal); targetDevice.setTranslateX(245); model.getChildren().add(targetDevice);
    }
    private void buildRansomware() {
        model.getChildren().add(sphere(30, -30, -5, 0, orange));
        label3D("ILLUSTRATED PROCESS", -30, -80, -30, "#ffcf9d");
        for (int i = 0; i < 6; i++) {
            double x = 135 + (i % 3) * 49; double y = -45 + (i / 3) * 70;
            Box page = box(33, 46, 5, x, y, 0, paper); pages.add(page); model.getChildren().add(page);
            Box lock = box(12, 12, 6, x, y, -7, dark); fileLocks.add(lock); model.getChildren().add(lock);
        }
        Group copy = folder(); copy.setTranslateX(205); copy.setTranslateY(140);
        copy.setScaleX(.7); copy.setScaleY(.7); model.getChildren().add(copy);
        label3D("RECOVERY COPY / ILLUSTRATION", 180, 190, -30, "#82d6ec");
    }
    private void render() {
        drawReconstruction();
        double t = seconds;
        if (sourceDevice != null) sourceDevice.setTranslateZ(Math.sin(t * 1.4) * 2);
        if (packageLid != null) packageLid.setTranslateY(phase >= 1 ? -85 : -35);
        if (hiddenCore != null) {
            hiddenCore.setVisible(phase >= 1); double scale = 1 + Math.sin(t * 3) * .08;
            hiddenCore.setScaleX(scale); hiddenCore.setScaleY(scale);
        }
        for (int i = 0; i < ports.size(); i++) {
            ports.get(i).setMaterial(((int) (t * 2) % ports.size()) == i ? orange : dim);
        }
        for (Box page : pages) page.setMaterial(phase >= 1 ? red : paper);
        for (Node lock : fileLocks) lock.setVisible(phase >= 1);
        if (attemptLabel != null) attemptLabel.setText("ILLUSTRATED ATTEMPT " + (1 + ((int) (t * 2) % 6)));
        boolean confirmedBlock = active("network_blocked") || active("blocking_confirmed");
        if (shield != null) shield.setVisible(preview ? phase == 2 : phase == 2 && confirmedBlock);
        for (int i = 0; i < packets.size(); i++) {
            Box packet = packets.get(i);
            double p = (t * .45 + i / (double) packets.size()) % 1;
            double x = -215 + p * 420; double y = -Math.sin(p * Math.PI) * 25;
            double z = Math.sin(p * Math.PI) * -25;
            if (kind == SceneCatalog.Kind.PORT_SCAN) {
                int port = i % 6; x = -195 + p * 375; y = p * (-85 + port * 29);
            } else if (kind == SceneCatalog.Kind.BRUTE_FORCE) {
                x = -205 + p * 195; y = Math.sin(p * Math.PI) * -25;
            } else if (kind == SceneCatalog.Kind.CONNECTION_FLOOD) {
                x = -190 + p * (phase >= 1 ? 310 : 420);
                y = Math.sin(i * 2.4) * 65 * (1 - p); z = Math.cos(i * 1.7) * 45;
            } else if (kind == SceneCatalog.Kind.PATH_TRAVERSAL) {
                x = -130 + p * 360; y = 70 - Math.floor(p * 4) * 40;
            } else if (kind == SceneCatalog.Kind.XSS) {
                x = phase >= 1 ? 100 + Math.cos(p * Math.PI * 2) * 57 : -190 + p * 270;
                y = phase >= 1 ? Math.sin(p * Math.PI * 2) * 35 : 0; z = -25;
            } else if (kind == SceneCatalog.Kind.COMMAND_INJECTION && phase >= 1) {
                x = 20 + p * 240; y = -p * 85; z = -15;
            } else if (kind == SceneCatalog.Kind.CONNECTION_TEST || kind == SceneCatalog.Kind.UNKNOWN) {
                if (phase == 0) { x = -215 + p * 180; }
                else if (phase == 1) { x = -35 + Math.cos(p * Math.PI * 2) * 55; y = Math.sin(p * Math.PI * 2) * 45; }
                else if (phase == 2) { x = -35 + p * 270; y = 0; }
                else { x = -35 + p * 270; y = (preview || active("decoy_active")) ? p * 145 : 0; }
            }
            if (!preview && confirmedBlock && phase == 2 && x > 122) packet.setVisible(false);
            else packet.setVisible(true);
            packet.setTranslateX(x); packet.setTranslateY(y); packet.setTranslateZ(z);
            packet.setRotationAxis(Rotate.Y_AXIS); packet.setRotate(p * 180);
        }
    }
    /* A separate Canvas renderer keeps reconstructions visible when a native
       SubScene fails to paint. Both renderers share the same evidence and clock. */
    private void drawReconstruction() {
        if (!compatible || reconstruction.getWidth() < 2) return;
        GraphicsContext g = reconstruction.getGraphicsContext2D();
        double w = reconstruction.getWidth(), h = reconstruction.getHeight();
        g.setFill(Color.web("#061321")); g.fillRect(0, 0, w, h);
        double scale = Math.min(w / 820, h / 360);
        g.save(); g.translate((w - 820 * scale) / 2, (h - 360 * scale) / 2); g.scale(scale, scale);
        g.setStroke(Color.web("#123247")); g.setLineWidth(1);
        for (int i = -5; i < 15; i++) {
            g.strokeLine(i * 80, 310, i * 80 + 200, 100);
            g.strokeLine(0, 110 + i * 28, 820, 110 + i * 28);
        }
        g.setFill(Color.web("#0d283c"));
        g.fillPolygon(new double[]{40, 650, 760, 150}, new double[]{250, 250, 320, 320}, 4);
        g.setStroke(Color.web("#3ac8c3")); g.setLineWidth(3);
        g.strokePolyline(new double[]{145, 295, 450, 600}, new double[]{205, 205, 205, 205}, 4);
        drawDevice(g, 100, 115, kind == SceneCatalog.Kind.CONNECTION_TEST,
                kind == SceneCatalog.Kind.CONNECTION_TEST ? "TERMUX / PHONE" : "SOURCE CLIENT");
        drawServer(g, 590, 112, "SENTINEL / SERVICE", "#40d7ca");
        double pulse = .5 + .5 * Math.sin(seconds * 4);
        g.setFill(Color.web("#1a495d")); g.fillOval(307, 126, 90, 90);
        g.setStroke(Color.web("#6df7df")); g.setLineWidth(2 + pulse * 2);
        g.strokeOval(307 - pulse * 6, 126 - pulse * 6, 90 + pulse * 12, 90 + pulse * 12);
        canvasText(g, "INSPECT", 352, 169, "#dcfff6", 14);
        canvasText(g, "EVENT EVIDENCE", 352, 190, "#9cc4d8", 10);
        boolean confirmed = active("network_blocked") || active("blocking_confirmed");
        if (kind == SceneCatalog.Kind.CONNECTION_TEST || kind == SceneCatalog.Kind.UNKNOWN) {
            canvasText(g, phase == 0 ? "CONNECTION ARRIVES" : phase == 1 ? "CURRENT RISK ASSESSED"
                    : phase == 2 ? "RESPONSE: " + (preview ? "ILLUSTRATION" : recorded(event, "response_action"))
                    : "RECORDED COMPONENT STATES", 350, 90, "#baffed", 16);
            drawDevice(g, 445, 260, false, "DECOY: " + (preview ? "DEMO" : recorded(event, "decoy_active")));
            canvasText(g, "SANDBOX: " + (preview ? "DEMO" : recorded(event, "sandbox_active")), 625, 324, "#9cb6c8", 11);
            if (phase == 3) {
                g.setStroke(Color.web("#5a8eaa")); g.setLineDashes(5, 6);
                g.strokeLine(398, 223, 477, 259); g.setLineDashes();
                canvasText(g, "STATE RECORDED / ROUTING NOT CONFIRMED", 350, 346, "#8fb1c3", 10);
            }
        } else if (kind == SceneCatalog.Kind.PORT_SCAN) {
            for (int i = 0; i < 6; i++) {
                g.setFill(i == (int)(seconds * 2) % 6 ? Color.web("#ffb56a") : Color.web("#1c5165"));
                g.fillRoundRect(480, 115 + i * 21, 65, 15, 6, 6);
                canvasText(g, "PORT " + (i + 1), 512, 126 + i * 21, "#d6f5ff", 9);
            }
        } else if (kind == SceneCatalog.Kind.BRUTE_FORCE) {
            for (int i = 0; i < 5; i++) {
                double x = 180 + ((seconds * 65 + i * 65) % 320);
                canvasCard(g, x, 240, "LOGIN", phase >= 1 ? "RETRY" : "ATTEMPT", "#b57748");
            }
            canvasText(g, "ILLUSTRATED ATTEMPTS: " + (1 + (int)(seconds * 2)), 360, 105, "#ffd49d", 15);
        } else if (kind == SceneCatalog.Kind.SQL_INJECTION) {
            canvasCard(g, 410, 125, "INPUT", "SQL TEXT", "#a66a46");
            g.setFill(Color.web("#2c7389")); g.fillRect(490, 170, 65, 65);
            g.fillOval(490, 157, 65, 25); g.setStroke(Color.web("#8fe9f3")); g.strokeOval(490, 157, 65, 25);
            canvasText(g, "DATABASE", 522, 253, "#c8f2ff", 11);
        } else if (kind == SceneCatalog.Kind.XSS || kind == SceneCatalog.Kind.COMMAND_INJECTION) {
            canvasCard(g, 420, 115, kind == SceneCatalog.Kind.XSS ? "BROWSER" : "APPLICATION",
                    kind == SceneCatalog.Kind.XSS ? "SCRIPT INPUT" : "COMMAND INPUT", "#a66a46");
            for (int i = 0; i < 3; i++) {
                double x = 485 + Math.cos(seconds + i * 2) * 35;
                double y = 230 + Math.sin(seconds + i * 2) * 20;
                canvasCard(g, x, y, kind == SceneCatalog.Kind.XSS ? "SCRIPT" : "PROCESS", "DEMO", "#805578");
            }
        } else if (kind == SceneCatalog.Kind.PATH_TRAVERSAL) {
            for (int i = 0; i < 4; i++) canvasCard(g, 390 + i * 45, 250 - i * 40,
                    "FOLDER", i == 0 ? "ROOT" : "LEVEL " + i, "#8a7342");
        } else if (kind == SceneCatalog.Kind.CONNECTION_FLOOD) {
            for (int i = 0; i < 4; i++) drawDevice(g, 180 + i * 55, 245, true, "CLIENT");
            for (int i = 0; i < 24; i++) {
                g.setFill(Color.web("#ffab68"));
                g.fillRect(470 + i % 6 * 12, 135 + i / 6 * 14, 8, 8);
            }
            canvasText(g, "CONNECTION QUEUE / DEMO", 470, 103, "#ffd09c", 13);
        } else if (kind == SceneCatalog.Kind.TROJAN) {
            canvasCard(g, 440, phase >= 1 ? 110 : 155, "PACKAGE", "APPARENT FILE", "#397f91");
            if (phase >= 1) canvasCard(g, 440, 200, "HIDDEN", "COMPONENT", "#b64c6d");
        } else if (kind == SceneCatalog.Kind.RANSOMWARE) {
            for (int i = 0; i < 6; i++) canvasCard(g, 410 + i % 3 * 64, 110 + i / 3 * 86,
                    "FILE", phase >= 1 ? "LOCKED" : "DOCUMENT", phase >= 1 ? "#b64c6d" : "#397f91");
        }
        int count = kind == SceneCatalog.Kind.CONNECTION_FLOOD ? 35 : 9;
        for (int i = 0; i < count; i++) {
            double progress = (seconds * .30 + i / (double) count) % 1;
            double x = phase == 0 ? 155 + progress * 155 : phase == 1 ? 312 + progress * 80 : 397 + progress * 195;
            double y = phase == 1 ? 170 + Math.sin(progress * Math.PI * 2) * 35 : 205;
            if (confirmed && phase == 2 && x > 528) continue;
            g.setFill(Color.web("#72ffe0")); g.fillOval(x - 4, y - 4, 9, 9);
        }
        if (phase == 2 && (confirmed || preview)) {
            g.setFill(Color.web("#297b80")); g.fillPolygon(new double[]{530, 561, 557, 545, 533},
                    new double[]{142, 151, 198, 218, 198}, 5);
            canvasText(g, confirmed ? "BLOCK CONFIRMED" : "POSSIBLE CONTROL / DEMO", 540, 246, "#9bffe1", 10);
        }
        canvasText(g, "RECONSTRUCTION 1.1 / " + (running ? "PLAYING" : "PAUSED"), 166, 29, "#67c9c4", 11);
        g.restore();
    }
    private static void canvasText(GraphicsContext g, String text, double x, double y, String color, int size) {
        g.setFill(Color.web(color)); g.setFont(Font.font("Segoe UI", size));
        g.setTextAlign(javafx.scene.text.TextAlignment.CENTER); g.fillText(text, x, y);
    }
    private static void drawDevice(GraphicsContext g, double x, double y, boolean phone, String label) {
        double w = phone ? 54 : 82, h = phone ? 94 : 57;
        g.setFill(Color.web("#07101d")); g.fillRoundRect(x + 7, y + 7, w, h, 12, 12);
        g.setFill(Color.web("#3c6a80")); g.fillRoundRect(x, y, w, h, 12, 12);
        g.setFill(Color.web("#0b2535")); g.fillRoundRect(x + 5, y + 8, w - 10, h - 17, 5, 5);
        g.setStroke(Color.web("#5af2d2")); g.setLineWidth(2);
        for (int i = 0; i < 3; i++) g.strokeLine(x + 12, y + 22 + i * 12, x + w - 12 - i * 4, y + 22 + i * 12);
        if (!phone) { g.setFill(Color.web("#7fabb8"));
            g.fillPolygon(new double[]{x, x + w, x + w + 15, x - 15}, new double[]{y + h, y + h, y + h + 16, y + h + 16}, 4); }
        canvasText(g, label, x + w / 2, y + h + (phone ? 20 : 31), "#aadce8", 10);
    }
    private static void drawServer(GraphicsContext g, double x, double y, String label, String color) {
        g.setFill(Color.web("#16394c")); g.fillRoundRect(x, y, 80, 125, 10, 10);
        g.setFill(Color.web("#244f66"));
        g.fillPolygon(new double[]{x + 80, x + 100, x + 100, x + 80}, new double[]{y, y - 12, y + 113, y + 125}, 4);
        g.setFill(Color.web("#527f92"));
        g.fillPolygon(new double[]{x, x + 20, x + 100, x + 80}, new double[]{y, y - 12, y - 12, y}, 4);
        for (int i = 0; i < 4; i++) {
            g.setFill(Color.web("#0b2436")); g.fillRoundRect(x + 9, y + 12 + i * 26, 62, 19, 4, 4);
            g.setFill(Color.web(color)); g.fillOval(x + 15, y + 18 + i * 26, 6, 6);
        }
        canvasText(g, label, x + 44, y + 150, "#a5dfeb", 10);
    }
    private static void canvasCard(GraphicsContext g, double x, double y, String heading, String detail, String color) {
        g.setFill(Color.web("#07101d")); g.fillRoundRect(x + 4, y + 5, 59, 49, 7, 7);
        g.setFill(Color.web(color)); g.fillRoundRect(x, y, 59, 49, 7, 7);
        canvasText(g, heading, x + 29, y + 19, "#ffffff", 9);
        canvasText(g, detail, x + 29, y + 35, "#e2f4ff", 8);
    }
    private static PhongMaterial material(String color) {
        PhongMaterial result = new PhongMaterial(Color.web(color));
        result.setSpecularColor(Color.web("#c4e8fa")); result.setSpecularPower(65); return result;
    }
    private static Box box(double w, double h, double d, double x, double y, double z, PhongMaterial m) {
        Box result = new Box(w, h, d); result.setMaterial(m);
        result.setTranslateX(x); result.setTranslateY(y); result.setTranslateZ(z); return result;
    }
    private static Sphere sphere(double r, double x, double y, double z, PhongMaterial m) {
        Sphere result = new Sphere(r, 32); result.setMaterial(m);
        result.setTranslateX(x); result.setTranslateY(y); result.setTranslateZ(z); return result;
    }
    private Text label3D(String content, double x, double y, double z, String color) {
        Text text = new Text(content); text.setFont(Font.font("Segoe UI", 13)); text.setFill(Color.web(color));
        text.setTranslateX(x - text.getLayoutBounds().getWidth() / 2);
        text.setTranslateY(y); text.setTranslateZ(z); model.getChildren().add(text); return text;
    }
    private void tube(Point3D start, Point3D end, double radius, PhongMaterial m) {
        Point3D delta = end.subtract(start); double length = delta.magnitude();
        if (length < .001) return;
        Cylinder cylinder = new Cylinder(radius, length, 12); cylinder.setMaterial(m);
        Point3D midpoint = start.midpoint(end);
        cylinder.setTranslateX(midpoint.getX()); cylinder.setTranslateY(midpoint.getY());
        cylinder.setTranslateZ(midpoint.getZ());
        Point3D axis = Rotate.Y_AXIS.crossProduct(delta);
        double angle = Math.toDegrees(Math.acos(Math.max(-1, Math.min(1, delta.getY() / length))));
        cylinder.getTransforms().add(new Rotate(angle, axis.magnitude() < .0001 ? Rotate.X_AXIS : axis));
        model.getChildren().add(cylinder);
    }
    private Group phone() {
        return new Group(box(45, 80, 11, 0, 0, 0, metal),
                box(36, 62, 3, 0, -1, -7, dark), sphere(3, 0, 34, -8, cyan));
    }
    private Group laptop() {
        return new Group(box(75, 48, 8, 0, -5, 0, metal),
                box(64, 35, 3, 0, -5, -6, dark), box(86, 5, 40, 0, 23, 10, metal));
    }
    private Group server(PhongMaterial color) {
        Group result = new Group(box(62, 96, 48, 0, 0, 0, color));
        for (int i = 0; i < 4; i++) result.getChildren().addAll(
                box(47, 12, 3, 0, -32 + i * 21, -26, dark),
                sphere(2.4, 19, -32 + i * 21, -29, cyan));
        return result;
    }
    private Group database() {
        Cylinder body = new Cylinder(40, 72, 48); body.setMaterial(metal);
        Group result = new Group(body);
        for (int i = 0; i < 4; i++) {
            Cylinder rim = new Cylinder(42, 3, 48); rim.setMaterial(cyan);
            rim.setTranslateY(-36 + i * 24); result.getChildren().add(rim);
        }
        return result;
    }
    private Group browser(String label) {
        Group group = new Group(box(116, 78, 10, 0, 0, 0, metal),
                box(105, 60, 3, 0, 5, -7, dark), box(115, 8, 12, 0, -34, 0, cyan));
        Text text = new Text(label); text.setFont(Font.font("Segoe UI", 11));
        text.setFill(Color.web("#a5dbe7")); text.setTranslateX(-text.getLayoutBounds().getWidth() / 2);
        text.setTranslateZ(-10); group.getChildren().add(text); return group;
    }
    private Group folder() {
        return new Group(box(65, 42, 10, 0, 0, 0, metal), box(25, 9, 10, -17, -24, 0, cyan));
    }
    private static Button button(String text) {
        Button button = new Button(text);
        button.setStyle("-fx-background-color:#143745;-fx-text-fill:#c9ffeb;"
                + "-fx-background-radius:8;-fx-padding:8 10;"); return button;
    }
}
