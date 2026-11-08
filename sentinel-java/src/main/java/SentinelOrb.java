import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import javafx.animation.AnimationTimer;
import javafx.application.Application;
import javafx.application.ConditionalFeature;
import javafx.application.Platform;
import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.geometry.Rectangle2D;
import javafx.scene.*;
import javafx.scene.control.*;
import javafx.scene.layout.*;
import javafx.scene.paint.Color;
import javafx.scene.paint.PhongMaterial;
import javafx.scene.shape.Box;
import javafx.scene.shape.CullFace;
import javafx.scene.shape.Sphere;
import javafx.scene.transform.Rotate;
import javafx.stage.Screen;
import javafx.stage.Stage;
import javafx.stage.StageStyle;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Random;
import java.util.concurrent.*;

public final class SentinelOrb {

    private SentinelOrb() {
    }

    public static void main(String[] args) {
        Application.launch(OrbWindow.class, args);
    }

    public static final class OrbWindow extends Application {

        private record Pose(
                double x, double y, double z,
                double rx, double ry, double rz) {
        }

        private static final class Motion {
            double value;
            double velocity;

            Motion(double initial) {
                value = initial;
            }

            double step(double target, double dt) {
                int steps = Math.max(1, (int) Math.ceil(dt / 0.008));
                double h = dt / steps;

                for (int i = 0; i < steps; i++) {
                    velocity += ((target - value) * 110
                            - velocity * 17) * h;
                    value += velocity * h;
                }

                return value;
            }
        }

        private final Path stateFile = Path.of("data/voice-state.json");

        private final ScheduledExecutorService reader =
                Executors.newSingleThreadScheduledExecutor(task -> {
                    Thread thread = new Thread(task, "sentinel-orb-state");
                    thread.setDaemon(true);
                    return thread;
                });

        private final Random random = new Random();
        private final Group character = new Group();
        private final Group head = new Group();
        private final Group leftEye = new Group();
        private final Group rightEye = new Group();
        private final Group smile = new Group();

        private final Sphere[] smilePoints = new Sphere[21];
        private final Sphere mouth = new Sphere(6, 32);

        private final Box leftBrow = new Box(18, 2.7, 3);
        private final Box rightBrow = new Box(18, 2.7, 3);

        private final Rotate headYaw = new Rotate(0, Rotate.Y_AXIS);
        private final Rotate headPitch = new Rotate(0, Rotate.X_AXIS);
        private final Rotate headRoll = new Rotate(0, Rotate.Z_AXIS);

        private final Motion yaw = new Motion(0);
        private final Motion pitch = new Motion(0);
        private final Motion roll = new Motion(0);
        private final Motion depth = new Motion(0);
        private final Motion gaze = new Motion(0);

        private final PhongMaterial shell =
                material(Color.web("#31cdbd"), Color.WHITE, 110);

        private final PhongMaterial handMaterial =
                material(Color.web("#b3fff1"), Color.WHITE, 90);

        private final PhongMaterial dark =
                material(Color.web("#051522"), Color.web("#557889"), 55);

        private final Hand leftHand = new Hand(false);
        private final Hand rightHand = new Hand(true);

        private final Label stateLabel = new Label("STARTING");
        private final Label caption = new Label("Preparing Sentinel");

        private Stage window;
        private AnimationTimer animation;

        private String state = "STARTING";
        private String gesture = "NONE";
        private String gestureToken = "";
        private Color targetColor = Color.web("#31cdbd");

        private boolean dragging;
        private boolean roaming = true;
        private boolean greeted;
        private volatile boolean closing;

        private double time;
        private double gestureStart;
        private double gestureDuration = 1;
        private double nextGesture;
        private double nextBlink = 2;
        private double blinkStart = -10;
        private double nextLook;
        private double idleLook;

        private double dragX;
        private double dragY;
        private double destinationX;
        private double destinationY;
        private double nextDestination;

        private long previousFrame;

        private final class Hand {
            final Group node = new Group();

            final Rotate rx = new Rotate(0, Rotate.X_AXIS);
            final Rotate ry = new Rotate(0, Rotate.Y_AXIS);
            final Rotate rz = new Rotate(0, Rotate.Z_AXIS);

            final Rotate[] fingers = new Rotate[3];
            final Rotate[] tips = new Rotate[3];

            final Motion x;
            final Motion y = new Motion(35);
            final Motion z = new Motion(0);
            final Motion ax = new Motion(0);
            final Motion ay = new Motion(0);
            final Motion az = new Motion(0);
            final Motion curl = new Motion(10);

            Hand(boolean right) {
                x = new Motion(right ? 104 : -104);

                Sphere palm = sphere(12, 0, 0, 0, handMaterial);
                palm.setScaleY(1.25);
                palm.setScaleZ(0.65);
                node.getChildren().add(palm);

                for (int i = 0; i < 3; i++) {
                    Group finger = new Group();
                    finger.setTranslateX(-7 + i * 7);
                    finger.setTranslateY(-9);

                    fingers[i] = new Rotate(0, Rotate.X_AXIS);
                    finger.getTransforms().add(fingers[i]);

                    Sphere upper = sphere(
                            3.2, 0, -5, 0, handMaterial);
                    upper.setScaleY(1.65);

                    Group tipJoint = new Group();
                    tipJoint.setTranslateY(-10);

                    tips[i] = new Rotate(0, Rotate.X_AXIS);
                    tipJoint.getTransforms().add(tips[i]);

                    Sphere tip = sphere(
                            3.0, 0, -4, 0, handMaterial);
                    tip.setScaleY(1.45);

                    tipJoint.getChildren().add(tip);
                    finger.getChildren().addAll(upper, tipJoint);
                    node.getChildren().add(finger);
                }

                Sphere thumb = sphere(
                        4.5, right ? -12 : 12, 3, -3, handMaterial);
                thumb.setScaleY(1.5);
                node.getChildren().add(thumb);

                node.getTransforms().addAll(ry, rx, rz);
                node.setTranslateX(right ? 104 : -104);
                node.setTranslateY(35);
            }

            void apply(Pose pose, boolean pointing, double dt) {
                node.setTranslateX(x.step(pose.x(), dt));
                node.setTranslateY(y.step(pose.y(), dt));
                node.setTranslateZ(z.step(pose.z(), dt));

                rx.setAngle(ax.step(pose.rx(), dt));
                ry.setAngle(ay.step(pose.ry(), dt));
                rz.setAngle(az.step(pose.rz(), dt));

                double bend = curl.step(pointing ? 65 : 12, dt);

                for (int i = 0; i < fingers.length; i++) {
                    double angle = pointing && i == 0 ? 0 : bend;
                    fingers[i].setAngle(angle);
                    tips[i].setAngle(angle * 0.7);
                }
            }
        }

        @Override
        public void start(Stage stage) {
            window = stage;

            if (!Platform.isSupported(ConditionalFeature.SCENE3D)) {
                new Alert(Alert.AlertType.ERROR,
                        "JavaFX 3D is unavailable.").showAndWait();
                Platform.exit();
                return;
            }

            buildCharacter();

            AmbientLight ambient =
                    new AmbientLight(Color.web("#435469"));

            PointLight key = new PointLight(Color.web("#e7fff8"));
            key.setTranslateX(-145);
            key.setTranslateY(-150);
            key.setTranslateZ(-230);

            PointLight rim = new PointLight(Color.web("#897bff"));
            rim.setTranslateX(160);
            rim.setTranslateY(-20);
            rim.setTranslateZ(60);

            PointLight fill = new PointLight(Color.web("#399ca8"));
            fill.setTranslateX(0);
            fill.setTranslateY(180);
            fill.setTranslateZ(-100);

            SubScene space = new SubScene(
                    new Group(character, ambient, key, rim, fill),
                    340, 300, true, SceneAntialiasing.BALANCED);

            space.setFill(Color.TRANSPARENT);

            PerspectiveCamera camera = new PerspectiveCamera(true);
            camera.setFieldOfView(35);
            camera.setNearClip(0.1);
            camera.setFarClip(1500);
            camera.setTranslateZ(-440);
            space.setCamera(camera);

            stateLabel.setStyle(
                    "-fx-font-family:'Segoe UI';-fx-font-size:12px;"
                            + "-fx-font-weight:bold;-fx-text-fill:#85ffe1;");

            caption.setStyle(
                    "-fx-font-family:'Segoe UI';-fx-font-size:11px;"
                            + "-fx-text-fill:#d6edf2;");

            caption.setWrapText(true);
            caption.setMaxWidth(310);
            caption.setAlignment(Pos.CENTER);

            VBox text = new VBox(5, stateLabel, caption);
            text.setAlignment(Pos.CENTER);
            text.setPadding(new Insets(0, 12, 10, 12));
            text.setMouseTransparent(true);

            BorderPane root = new BorderPane();
            root.setStyle("-fx-background-color:transparent;");
            root.setCenter(space);
            root.setBottom(text);

            stage.initStyle(StageStyle.TRANSPARENT);
            stage.setTitle("Sentinel Phoenix | Spatial Orb");
            stage.setAlwaysOnTop(true);
            stage.setScene(new Scene(root, 340, 370, Color.TRANSPARENT));

            Rectangle2D screen = Screen.getPrimary().getVisualBounds();
            stage.setX(screen.getMinX() + 35);
            stage.setY(screen.getMinY() + 100);

            configureMovement(root);
            configureMenu(root);
            stage.show();

            destinationX = stage.getX();
            destinationY = stage.getY();

            animation = new AnimationTimer() {
                @Override
                public void handle(long now) {
                    double dt = previousFrame == 0 ? 0
                            : Math.min(0.05,
                                    (now - previousFrame) / 1_000_000_000.0);

                    previousFrame = now;
                    time += dt;

                    animateCharacter(dt);
                    moveWindow(dt);
                }
            };

            animation.start();

            reader.scheduleWithFixedDelay(
                    this::readState, 0, 200, TimeUnit.MILLISECONDS);
        }

        private void buildCharacter() {
            Sphere body = new Sphere(74, 96);
            body.setMaterial(shell);

            Sphere halo = new Sphere(76, 64);
            halo.setCullFace(CullFace.FRONT);
            halo.setMaterial(new PhongMaterial(
                    Color.color(0.20, 0.80, 0.90, 0.10)));

            buildEye(leftEye);
            buildEye(rightEye);

            leftEye.setTranslateX(-24);
            rightEye.setTranslateX(24);

            leftBrow.setMaterial(dark);
            rightBrow.setMaterial(dark);
            leftBrow.setTranslateX(-24);
            rightBrow.setTranslateX(24);
            leftBrow.setTranslateZ(-67);
            rightBrow.setTranslateZ(-67);

            for (int i = 0; i < smilePoints.length; i++) {
                smilePoints[i] = sphere(1.8, 0, 0, 0, dark);
                smile.getChildren().add(smilePoints[i]);
            }

            mouth.setMaterial(dark);
            mouth.setTranslateY(27);
            mouth.setTranslateZ(-72);
            mouth.setScaleX(1.7);
            mouth.setScaleZ(0.35);

            head.getChildren().addAll(
                    body, halo, leftEye, rightEye,
                    leftBrow, rightBrow, smile, mouth);

            head.getTransforms().addAll(
                    headYaw, headPitch, headRoll);

            character.getChildren().addAll(
                    head, leftHand.node, rightHand.node);
        }

        private void buildEye(Group eye) {
            Sphere pupil = sphere(7, 0, 0, 0, dark);
            pupil.setScaleY(1.65);
            pupil.setScaleZ(0.45);

            Sphere shine = sphere(
                    2, -2, -5, -4,
                    material(Color.WHITE, Color.WHITE, 100));

            eye.getChildren().addAll(pupil, shine);
            eye.setTranslateY(-12);
            eye.setTranslateZ(-72);
        }

        private static Sphere sphere(
                double radius, double x, double y, double z,
                PhongMaterial material) {

            Sphere sphere = new Sphere(radius, 32);
            sphere.setMaterial(material);
            sphere.setTranslateX(x);
            sphere.setTranslateY(y);
            sphere.setTranslateZ(z);
            return sphere;
        }

        private static PhongMaterial material(
                Color diffuse, Color specular, double power) {

            PhongMaterial result = new PhongMaterial(diffuse);
            result.setSpecularColor(specular);
            result.setSpecularPower(power);
            return result;
        }

        private void startGesture(String name, double duration) {
            gesture = name;
            gestureStart = time;
            gestureDuration = duration;
        }

        private void stateChanged(String nextState) {
            state = nextState;

            switch (state) {
                case "WAITING" -> {
                    if (!greeted) {
                        greeted = true;
                        startGesture("WAVE", 2.1);
                    }
                }
                case "LISTENING" -> startGesture("ATTENTIVE", 1.8);
                case "THINKING" -> startGesture("CONSIDER", 2.4);
                case "SPEAKING" -> {
                    startGesture("PRESENT", 2);
                    nextGesture = time + 2.6;
                }
                case "ERROR" -> startGesture("SHRUG", 1.8);
                default -> {
                }
            }
        }

        private static Pose blend(Pose first, Pose second, double amount) {
            return new Pose(
                    first.x() + (second.x() - first.x()) * amount,
                    first.y() + (second.y() - first.y()) * amount,
                    first.z() + (second.z() - first.z()) * amount,
                    first.rx() + (second.rx() - first.rx()) * amount,
                    first.ry() + (second.ry() - first.ry()) * amount,
                    first.rz() + (second.rz() - first.rz()) * amount);
        }

        private void animateCharacter(double dt) {
            boolean listening = "LISTENING".equals(state);
            boolean thinking = "THINKING".equals(state);
            boolean speaking = "SPEAKING".equals(state);

            if (time >= nextBlink) {
                blinkStart = time;
                nextBlink = time + 2.3 + random.nextDouble() * 4;
            }

            double blinkAge = time - blinkStart;
            double eyelid = blinkAge >= 0 && blinkAge < 0.18
                    ? 1 - 0.94 * Math.sin(Math.PI * blinkAge / 0.18)
                    : 1;

            if (time >= nextLook) {
                idleLook = -24 + random.nextDouble() * 48;
                nextLook = time + 2.2 + random.nextDouble() * 3;
            }

            double look = gaze.step(
                    listening ? 0 : thinking ? 24 : idleLook, dt);

            double targetYaw = look;
            double targetPitch = listening ? -7 : thinking ? -10 : 0;
            double targetRoll = thinking ? -7 : 0;
            double targetDepth = listening ? -12 : 0;

            Pose left = new Pose(-104, 35, 0, 0, 20, -12);
            Pose right = new Pose(104, 35, 0, 0, -20, 12);

            if (listening) {
                left = new Pose(-88, 23, -32, -15, 30, -18);
                right = new Pose(88, 23, -32, -15, -30, 18);
            }

            if (thinking) {
                right = new Pose(38, 27, -88, -35, -40, -32);
            }

            if (speaking && time >= nextGesture) {
                String[] choices = {
                        "PRESENT", "REACH", "TURN",
                        "BEAT_LEFT", "BEAT_RIGHT", "NOD"
                };

                startGesture(
                        choices[random.nextInt(choices.length)], 2.1);

                nextGesture = time + 2.8 + random.nextDouble() * 2;
            }

            boolean leftPoint = false;
            boolean rightPoint = false;

            double age = time - gestureStart;

            if (age >= 0 && age < gestureDuration) {
                double p = age / gestureDuration;
                double amount = Math.pow(Math.sin(Math.PI * p), 0.65);

                Pose leftTarget = left;
                Pose rightTarget = right;

                switch (gesture) {
                    case "WAVE" -> {
                        rightTarget = new Pose(
                                92, -48, -65,
                                -20,
                                Math.sin(p * Math.PI * 6) * 35,
                                25 + Math.sin(p * Math.PI * 6) * 20);
                        targetYaw += amount * -12;
                    }
                    case "ATTENTIVE" -> {
                        rightTarget = new Pose(83, 10, -48, -20, -35, 15);
                        targetPitch -= amount * 5;
                    }
                    case "CONSIDER" -> {
                        rightTarget = new Pose(34, 24, -94, -40, -35, -35);
                        targetYaw += amount * 15;
                    }
                    case "PRESENT" -> {
                        leftTarget = new Pose(-111, 12, -65, -25, 40, -38);
                        rightTarget = new Pose(108, 25, -30, -15, -25, 25);
                        targetYaw += amount * 15;
                    }
                    case "REACH" -> {
                        rightTarget = new Pose(35, 8, -140, -12, 10, 5);
                        targetDepth += amount * 10;
                        targetYaw -= amount * 12;
                        rightPoint = true;
                    }
                    case "TURN" -> {
                        targetYaw = look + amount * 52;
                        rightTarget = new Pose(75, 30, 35, 15, -65, 15);
                        leftTarget = new Pose(-105, 25, -40, -10, 50, -18);
                    }
                    case "POINT_LEFT" -> {
                        leftTarget = new Pose(-132, -8, -38, 5, 30, -85);
                        targetYaw = look + amount * 38;
                        leftPoint = true;
                    }
                    case "POINT_RIGHT" -> {
                        rightTarget = new Pose(132, -8, -38, 5, -30, 85);
                        targetYaw = look - amount * 38;
                        rightPoint = true;
                    }
                    case "BEAT_LEFT" ->
                            leftTarget = new Pose(-104, 0, -65, -25, 35, -35);
                    case "BEAT_RIGHT" ->
                            rightTarget = new Pose(104, 0, -65, -25, -35, 35);
                    case "SHRUG" -> {
                        leftTarget = new Pose(-111, 0, -30, -35, 50, -50);
                        rightTarget = new Pose(111, 0, -30, -35, -50, 50);
                        targetRoll += amount * 6;
                    }
                    case "NOD" ->
                            targetPitch += Math.sin(p * Math.PI * 2) * amount * 13;
                    default -> {
                    }
                }

                left = blend(left, leftTarget, amount);
                right = blend(right, rightTarget, amount);
            }

            headYaw.setAngle(yaw.step(targetYaw, dt));
            headPitch.setAngle(pitch.step(targetPitch, dt));
            headRoll.setAngle(roll.step(targetRoll, dt));
            head.setTranslateZ(depth.step(targetDepth, dt));

            character.setTranslateY(Math.sin(time * 1.5) * 2.5);

            leftHand.apply(left, leftPoint, dt);
            rightHand.apply(right, rightPoint, dt);

            leftEye.setScaleY(eyelid * (listening ? 1.1 : 1));
            rightEye.setScaleY(eyelid * (listening ? 1.1 : 1));

            leftBrow.setTranslateY(listening ? -38 : -34);
            rightBrow.setTranslateY(thinking ? -39 : listening ? -38 : -34);
            leftBrow.setRotate(thinking ? -12 : -4);
            rightBrow.setRotate(thinking ? -7 : 4);

            double curve = thinking ? 1.5 : listening ? 4 : 8;

            for (int i = 0; i < smilePoints.length; i++) {
                double x = -17 + i * 34.0 / (smilePoints.length - 1);
                double y = 24 + curve * (1 - x * x / 289);

                smilePoints[i].setTranslateX(x);
                smilePoints[i].setTranslateY(y);
                smilePoints[i].setTranslateZ(
                        -Math.sqrt(74 * 74 - x * x - y * y) - 2);
            }

            smile.setVisible(!speaking);
            mouth.setVisible(speaking);

            if (speaking) {
                double articulation = Math.abs(
                        Math.sin(time * 7.3) * Math.sin(time * 2.7));

                mouth.setScaleY(0.35 + articulation * 1.15);
                mouth.setScaleX(1.4 + articulation * 0.45);
            }

            shell.setDiffuseColor(
                    shell.getDiffuseColor().interpolate(
                            targetColor, 1 - Math.exp(-dt * 4)));
        }

        private void configureMovement(Node root) {
            root.setOnMousePressed(event -> {
                if (!event.isPrimaryButtonDown()) {
                    return;
                }

                dragging = true;
                dragX = event.getScreenX() - window.getX();
                dragY = event.getScreenY() - window.getY();
            });

            root.setOnMouseDragged(event -> {
                if (dragging) {
                    window.setX(event.getScreenX() - dragX);
                    window.setY(event.getScreenY() - dragY);
                }
            });

            root.setOnMouseReleased(event -> {
                dragging = false;
                destinationX = window.getX();
                destinationY = window.getY();
                nextDestination = time + 12;
            });
        }

        private MenuItem preview(String label, String name) {
            MenuItem item = new MenuItem(label);

            item.setOnAction(event -> {
                startGesture(name, 2.8);
                nextGesture = time + 3.2;
            });

            return item;
        }

        private void configureMenu(Node root) {
            CheckMenuItem roam = new CheckMenuItem("Autonomous movement");
            roam.setSelected(roaming);

            roam.setOnAction(event -> {
                roaming = roam.isSelected();
                nextDestination = 0;
            });

            CheckMenuItem onTop = new CheckMenuItem("Always on top");
            onTop.setSelected(true);
            onTop.setOnAction(event ->
                    window.setAlwaysOnTop(onTop.isSelected()));

            Menu previews = new Menu("3D gesture previews");
            previews.getItems().addAll(
                    preview("Turn three quarters", "TURN"),
                    preview("Reach toward you", "REACH"),
                    preview("Point left", "POINT_LEFT"),
                    preview("Point right", "POINT_RIGHT"),
                    preview("Wave in depth", "WAVE"),
                    preview("Shrug", "SHRUG"));

            MenuItem hide = new MenuItem("Hide orb");
            hide.setOnAction(event -> window.hide());

            ContextMenu menu = new ContextMenu(roam, onTop, previews, hide);

            root.setOnContextMenuRequested(event ->
                    menu.show(root, event.getScreenX(), event.getScreenY()));
        }

        private void moveWindow(double dt) {
            if (!roaming || dragging || !window.isShowing()
                    || !"WAITING".equals(state)) {
                return;
            }

            if (time >= nextDestination) {
                var screens = Screen.getScreens();

                Rectangle2D bounds = screens.get(
                        random.nextInt(screens.size())).getVisualBounds();

                destinationX = bounds.getMinX() + random.nextDouble()
                        * Math.max(0, bounds.getWidth() - window.getWidth());

                destinationY = bounds.getMinY() + random.nextDouble()
                        * Math.max(0, bounds.getHeight() - window.getHeight());

                nextDestination = time + 20 + random.nextDouble() * 10;
            }

            double dx = destinationX - window.getX();
            double dy = destinationY - window.getY();
            double distance = Math.hypot(dx, dy);

            if (distance > 1) {
                double step = Math.min(distance, dt * 35);
                window.setX(window.getX() + dx / distance * step);
                window.setY(window.getY() + dy / distance * step);
            }
        }

        private static String text(JsonObject data, String key) {
            return data.has(key) && data.get(key).isJsonPrimitive()
                    ? data.get(key).getAsString() : "";
        }

        private void readState() {
            if (closing) {
                return;
            }

            try {
                if (!Files.isRegularFile(stateFile)) {
                    return;
                }

                JsonObject data = JsonParser.parseString(
                        Files.readString(stateFile, StandardCharsets.UTF_8))
                        .getAsJsonObject();

                String nextState = text(data, "state");
                String nextCaption = text(data, "caption");
                String requestedGesture = text(data, "gesture");
                String token = text(data, "updated_at") + ":" + requestedGesture;

                Platform.runLater(() -> {
                    if (closing || nextState.isBlank()) {
                        return;
                    }

                    if (!nextState.equals(state)) {
                        stateChanged(nextState);
                    }

                    caption.setText(nextCaption);

                    if (!requestedGesture.isBlank()
                            && !token.equals(gestureToken)) {

                        gestureToken = token;
                        startGesture(requestedGesture, 2.2);
                        nextGesture = time + 2.8;
                    }

                    stateLabel.setText(
                            "LISTENING".equals(state)
                                    ? "LISTENING / TRANSCRIBING" : state);

                    targetColor = switch (state) {
                        case "LISTENING" -> Color.web("#48bfe9");
                        case "THINKING" -> Color.web("#9478df");
                        case "SPEAKING" -> Color.web("#48dfbf");
                        case "ERROR" -> Color.web("#e77d91");
                        case "STARTING", "PREPARING" -> Color.web("#d9b66d");
                        default -> Color.web("#31cdbd");
                    };

                    stateLabel.setTextFill(targetColor.brighter());
                });

            } catch (Exception ignored) {
                // Keep the previous valid state.
            }
        }

        @Override
        public void stop() {
            closing = true;

            if (animation != null) {
                animation.stop();
            }

            reader.shutdownNow();
        }
    }
}
// END SENTINEL ORB