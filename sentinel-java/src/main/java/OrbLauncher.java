import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import javafx.animation.*;
import javafx.application.Application;
import javafx.application.Platform;
import javafx.beans.property.DoubleProperty;
import javafx.beans.property.SimpleDoubleProperty;
import javafx.geometry.Rectangle2D;
import javafx.scene.*;
import javafx.scene.layout.BorderPane;
import javafx.scene.paint.Color;
import javafx.scene.paint.PhongMaterial;
import javafx.scene.shape.Box;
import javafx.scene.shape.Cylinder;
import javafx.scene.shape.Sphere;
import javafx.scene.transform.Rotate;
import javafx.scene.transform.Translate;
import javafx.stage.Screen;
import javafx.stage.Stage;
import javafx.util.Duration;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public final class OrbLauncher {

    private OrbLauncher() {
    }

    public static void main(String[] args) {
        Application.launch(ControlledOrb.class, args);
    }

    /*
     * Adds accessories to the scene structure of the SentinelOrb.java
     * supplied with this version.
     *
     * All methods run on the JavaFX application thread.
     */
    private static final class Accessories {

        private final Group camera = new Group();
        private final Group glasses = new Group();

        private final Group leftHand;
        private final Group rightHand;

        private final Translate leftOffset = new Translate();
        private final Translate rightOffset = new Translate();

        private final Rotate cameraTurn =
                new Rotate(0, Rotate.Y_AXIS);

        private final Rotate cameraTilt =
                new Rotate(0, Rotate.Z_AXIS);

        private final PointLight flash =
                new PointLight(Color.WHITE);

        private final AnimationTimer timer;

        private String action = "";
        private long started;
        private double duration;
        private Runnable completed;

        private boolean glassesWanted;
        private double glassesAmount;
        private long previousFrame;

        Accessories(Stage window) {
            if (!(window.getScene().getRoot()
                    instanceof BorderPane pane)
                    || !(pane.getCenter() instanceof SubScene scene)
                    || !(scene.getRoot() instanceof Group world)
                    || world.getChildren().isEmpty()
                    || !(world.getChildren().get(0)
                         instanceof Group character)
                    || character.getChildren().size() < 3
                    || !(character.getChildren().get(0)
                         instanceof Group head)
                    || !(character.getChildren().get(1)
                         instanceof Group left)
                    || !(character.getChildren().get(2)
                         instanceof Group right)) {

                throw new IllegalStateException(
                        "Unexpected SentinelOrb scene structure.");
            }

            leftHand = left;
            rightHand = right;

            leftHand.getTransforms().add(0, leftOffset);
            rightHand.getTransforms().add(0, rightOffset);

            buildCamera();
            buildGlasses();

            character.getChildren().add(camera);
            head.getChildren().add(glasses);

            camera.setVisible(false);
            glasses.setVisible(false);

            timer = new AnimationTimer() {
                @Override
                public void handle(long now) {
                    double dt = previousFrame == 0
                            ? 0
                            : Math.min(
                                    0.05,
                                    (now - previousFrame)
                                            / 1_000_000_000.0);

                    previousFrame = now;
                    animate(now, dt);
                }
            };

            timer.start();
        }

        private static PhongMaterial material(
                String diffuse, String specular) {

            PhongMaterial material =
                    new PhongMaterial(Color.web(diffuse));

            material.setSpecularColor(Color.web(specular));
            material.setSpecularPower(90);

            return material;
        }

        private static Box box(
                double width, double height, double depth,
                double x, double y, double z,
                PhongMaterial material) {

            Box box = new Box(width, height, depth);
            box.setMaterial(material);

            box.setTranslateX(x);
            box.setTranslateY(y);
            box.setTranslateZ(z);

            return box;
        }

        private static Sphere sphere(
                double radius,
                double x, double y, double z,
                PhongMaterial material) {

            Sphere sphere = new Sphere(radius, 16);
            sphere.setMaterial(material);

            sphere.setTranslateX(x);
            sphere.setTranslateY(y);
            sphere.setTranslateZ(z);

            return sphere;
        }

        private void buildCamera() {
            PhongMaterial body =
                    material("#203346", "#b4d9ed");

            PhongMaterial metal =
                    material("#83a9bf", "#ffffff");

            PhongMaterial lens =
                    material("#071b33", "#74d5ff");

            Box housing = box(
                    48, 30, 19,
                    0, 0, 0, body);

            Box grip = box(
                    8, 28, 22,
                    22, 1, -1, body);

            Box top = box(
                    17, 7, 15,
                    -4, -18, 0, metal);

            Cylinder lensRing = new Cylinder(12, 12, 40);
            lensRing.setMaterial(metal);
            lensRing.setRotationAxis(Rotate.X_AXIS);
            lensRing.setRotate(90);
            lensRing.setTranslateZ(-14);

            Sphere glass = sphere(
                    10, 0, 0, -21, lens);

            glass.setScaleZ(0.25);

            Box shutter = box(
                    7, 3, 6,
                    15, -17, 0, metal);

            Box flashPanel = box(
                    10, 5, 2,
                    -16, -9, -11,
                    material("#e9f9ff", "#ffffff"));

            flash.setTranslateX(-16);
            flash.setTranslateY(-9);
            flash.setTranslateZ(-35);
            flash.setLightOn(false);

            camera.getChildren().addAll(
                    housing, grip, top,
                    lensRing, glass,
                    shutter, flashPanel, flash);

            camera.getTransforms().addAll(
                    cameraTurn, cameraTilt);
        }

        private void buildGlasses() {
            PhongMaterial frame =
                    material("#18283d", "#b4d6ed");

            for (double center : new double[] {-24, 24}) {
                for (int i = 0; i < 40; i++) {
                    double angle = i * Math.PI * 2 / 40;

                    glasses.getChildren().add(
                            sphere(
                                    1.55,
                                    center + Math.cos(angle) * 15,
                                    -12 + Math.sin(angle) * 13,
                                    -81,
                                    frame));
                }
            }

            glasses.getChildren().addAll(
                    box(18, 2.8, 3, 0, -13, -81, frame),
                    box(3, 3, 35, -40, -12, -64, frame),
                    box(3, 3, 35, 40, -12, -64, frame));
        }

        boolean play(String nextAction, Runnable onCompleted) {
            switch (nextAction) {
                case "CAMERA_OPEN", "CAMERA_CLOSE",
                        "EXPLAIN_BEGIN", "EXPLAIN_END" -> {
                }

                default -> {
                    return false;
                }
            }

            cancelAnimation();

            action = nextAction;
            completed = onCompleted;
            started = System.nanoTime();

            duration = switch (action) {
                case "CAMERA_OPEN" -> 2.1;
                case "CAMERA_CLOSE" -> 1.6;
                case "EXPLAIN_BEGIN" -> 0.85;
                default -> 0.75;
            };

            if ("EXPLAIN_BEGIN".equals(action)) {
                glassesWanted = true;
            }

            if ("EXPLAIN_END".equals(action)
                    || action.startsWith("CAMERA_")) {
                glassesWanted = false;
            }

            return true;
        }

        void cancelAnimation() {
            action = "";
            completed = null;

            camera.setVisible(false);
            flash.setLightOn(false);

            resetHandOffsets();
        }

        void reset() {
            cancelAnimation();

            glassesWanted = false;
            glassesAmount = 0;
            glasses.setVisible(false);
        }

        private void resetHandOffsets() {
            leftOffset.setX(0);
            leftOffset.setY(0);
            leftOffset.setZ(0);

            rightOffset.setX(0);
            rightOffset.setY(0);
            rightOffset.setZ(0);
        }

        private static double ease(double value) {
            double p = Math.max(0, Math.min(1, value));
            return p * p * (3 - 2 * p);
        }

        private void handTarget(
                boolean right,
                double x, double y, double z,
                double amount) {

            Group hand = right ? rightHand : leftHand;
            Translate offset = right ? rightOffset : leftOffset;

            offset.setX((x - hand.getTranslateX()) * amount);
            offset.setY((y - hand.getTranslateY()) * amount);
            offset.setZ((z - hand.getTranslateZ()) * amount);
        }

        private void animate(long now, double dt) {
            resetHandOffsets();

            double target = glassesWanted ? 1 : 0;

            glassesAmount +=
                    (target - glassesAmount)
                            * (1 - Math.exp(-dt * 9));

            glasses.setVisible(glassesAmount > 0.02);
            glasses.setScaleX(Math.max(0.01, glassesAmount));
            glasses.setScaleY(Math.max(0.01, glassesAmount));
            glasses.setScaleZ(Math.max(0.01, glassesAmount));
            glasses.setTranslateY(-35 * (1 - glassesAmount));

            if (action.isBlank()) {
                return;
            }

            double p = Math.min(
                    1,
                    (now - started) / 1_000_000_000.0 / duration);

            if (action.startsWith("CAMERA_")) {
                animateCamera(p);

            } else {
                double reach =
                        Math.sin(Math.PI * p);

                handTarget(
                        true,
                        43, -15, -97,
                        reach * 0.9);
            }

            if (p >= 1) {
                String finishedAction = action;
                Runnable callback = completed;

                action = "";
                completed = null;

                camera.setVisible(false);
                flash.setLightOn(false);
                resetHandOffsets();

                if ("EXPLAIN_END".equals(finishedAction)) {
                    glassesAmount = 0;
                    glasses.setVisible(false);
                }

                if (callback != null) {
                    callback.run();
                }
            }
        }

        private void animateCamera(double p) {
            boolean opening = "CAMERA_OPEN".equals(action);

            double raise = ease(p / 0.30);
            double lower = ease((p - 0.66) / 0.34);

            double held = raise * (1 - lower);

            camera.setVisible(p < 0.995);

            double size = 0.12 + held * 0.88;

            camera.setScaleX(size);
            camera.setScaleY(size);
            camera.setScaleZ(size);

            camera.setTranslateX(92 * (1 - held));
            camera.setTranslateY(65 * (1 - held) - 8 * held);
            camera.setTranslateZ(-25 - 91 * held);

            cameraTurn.setAngle((1 - held) * -40);
            cameraTilt.setAngle((1 - held) * 25);

            handTarget(
                    true,
                    31, 6, -112,
                    held);

            handTarget(
                    false,
                    -30, 10, -106,
                    held);

            // Small local flash, not a full-screen effect.
            flash.setLightOn(
                    opening && p >= 0.46 && p < 0.49);
        }

        void stop() {
            timer.stop();
            reset();

            leftHand.getTransforms().remove(leftOffset);
            rightHand.getTransforms().remove(rightOffset);
        }
    }

    public static final class ControlledOrb extends Application {

        private final Path commandFile =
                Path.of("data/orb-command.json");

        private final Path acknowledgementFile =
                Path.of("data/orb-ack.json");

        private final ScheduledExecutorService reader =
                Executors.newSingleThreadScheduledExecutor(task -> {
                    Thread thread =
                            new Thread(task, "sentinel-orb-commands");

                    thread.setDaemon(true);
                    return thread;
                });

        private SentinelOrb.OrbWindow visual;
        private Accessories accessories;

        private Stage window;
        private Node surface;
        private Animation transition;

        private String previousCommandId = "";
        private String pendingId = "";
        private String pendingAction = "";

        private volatile boolean closing;

        @Override
        public void start(Stage stage) {
            Platform.setImplicitExit(false);
            window = stage;

            JsonObject existing = readCommand();

            if (existing != null) {
                previousCommandId = text(existing, "id");
            }

            visual = new SentinelOrb.OrbWindow();
            visual.start(stage);

            if (stage.getScene() == null) {
                Platform.exit();
                return;
            }

            surface = stage.getScene().getRoot();
            accessories = new Accessories(stage);

            stage.setOnCloseRequest(event -> Platform.exit());

            reader.scheduleWithFixedDelay(
                    this::pollCommands,
                    100, 100, TimeUnit.MILLISECONDS);
        }

        private JsonObject readCommand() {
            try {
                if (!Files.isRegularFile(commandFile)) {
                    return null;
                }

                return JsonParser.parseString(
                        Files.readString(
                                commandFile,
                                StandardCharsets.UTF_8))
                        .getAsJsonObject();

            } catch (Exception ignored) {
                return null;
            }
        }

        private static String text(
                JsonObject object, String key) {

            return object.has(key)
                    && object.get(key).isJsonPrimitive()
                    ? object.get(key).getAsString() : "";
        }

        private void pollCommands() {
            if (closing) {
                return;
            }

            JsonObject command = readCommand();

            if (command == null) {
                return;
            }

            String id = text(command, "id");
            String action = text(command, "action");

            if (id.isBlank() || id.equals(previousCommandId)) {
                return;
            }

            previousCommandId = id;

            Platform.runLater(() -> {
                if (!closing) {
                    execute(id, action);
                }
            });
        }

        private void execute(String id, String action) {
            interruptTransition();

            pendingId = id;
            pendingAction = action;

            switch (action) {
                case "HIDE" -> {
                    accessories.reset();
                    hideAnimated();
                }

                case "SHOW" -> showAnimated();

                case "MOVE_LEFT" -> move(-180, 0);
                case "MOVE_RIGHT" -> move(180, 0);
                case "MOVE_UP" -> move(0, -140);
                case "MOVE_DOWN" -> move(0, 140);

                case "RESET_PROPS" -> {
                    accessories.reset();
                    finish("COMPLETED");
                }

                case "CAMERA_OPEN", "CAMERA_CLOSE",
                        "EXPLAIN_BEGIN", "EXPLAIN_END" -> {

                    if (!window.isShowing()) {
                        finish("HIDDEN");
                        return;
                    }

                    boolean accepted = accessories.play(
                            action,
                            () -> finish("COMPLETED"));

                    if (!accepted) {
                        finish("UNSUPPORTED");
                    }
                }

                default -> finish("UNSUPPORTED");
            }
        }

        private void acknowledge(
                String id,
                String action,
                String status) {

            if (id.isBlank()) {
                return;
            }

            Path temporary = null;

            try {
                Files.createDirectories(
                        acknowledgementFile.getParent());

                JsonObject result = new JsonObject();

                result.addProperty("id", id);
                result.addProperty("action", action);
                result.addProperty("status", status);
                result.addProperty("x", window.getX());
                result.addProperty("y", window.getY());

                temporary = Files.createTempFile(
                        acknowledgementFile.getParent(),
                        "orb-ack-", ".tmp");

                Files.writeString(
                        temporary,
                        result.toString(),
                        StandardCharsets.UTF_8);

                try {
                    Files.move(
                            temporary,
                            acknowledgementFile,
                            StandardCopyOption.REPLACE_EXISTING,
                            StandardCopyOption.ATOMIC_MOVE);

                } catch (AtomicMoveNotSupportedException error) {
                    Files.move(
                            temporary,
                            acknowledgementFile,
                            StandardCopyOption.REPLACE_EXISTING);
                }

            } catch (Exception error) {
                System.err.println(
                        "[ORB ACK] " + error.getMessage());

            } finally {
                if (temporary != null) {
                    try {
                        Files.deleteIfExists(temporary);
                    } catch (Exception ignored) {
                    }
                }
            }
        }

        private void finish(String status) {
            acknowledge(pendingId, pendingAction, status);

            pendingId = "";
            pendingAction = "";
            transition = null;
        }

        private void resetSurface() {
            surface.setOpacity(1);
            surface.setScaleX(1);
            surface.setScaleY(1);
            surface.setRotate(0);
        }

        private void interruptTransition() {
            if (transition != null) {
                transition.stop();
                transition = null;
            }

            if (accessories != null) {
                accessories.cancelAnimation();
            }

            if (!pendingId.isBlank()) {
                finish("CANCELLED");
            }

            if (surface != null) {
                resetSurface();
            }
        }

        private void hideAnimated() {
            if (!window.isShowing()) {
                finish("COMPLETED");
                return;
            }

            RotateTransition sway = new RotateTransition(
                    Duration.millis(130), surface);

            sway.setFromAngle(-5);
            sway.setToAngle(5);
            sway.setCycleCount(4);
            sway.setAutoReverse(true);
            sway.setInterpolator(Interpolator.EASE_BOTH);

            RotateTransition straighten = new RotateTransition(
                    Duration.millis(100), surface);

            straighten.setToAngle(0);

            ScaleTransition shrink = new ScaleTransition(
                    Duration.millis(420), surface);

            shrink.setToX(0.05);
            shrink.setToY(0.05);
            shrink.setInterpolator(Interpolator.EASE_IN);

            FadeTransition fade = new FadeTransition(
                    Duration.millis(420), surface);

            fade.setToValue(0);

            SequentialTransition sequence =
                    new SequentialTransition(
                            sway,
                            straighten,
                            new ParallelTransition(shrink, fade));

            transition = sequence;

            sequence.setOnFinished(event -> {
                window.hide();
                resetSurface();
                finish("COMPLETED");
            });

            sequence.play();
        }

        private void showAnimated() {
            if (window.isShowing()) {
                window.toFront();
                finish("COMPLETED");
                return;
            }

            surface.setOpacity(0);
            surface.setScaleX(0.08);
            surface.setScaleY(0.08);

            window.show();
            window.toFront();

            ScaleTransition expand = new ScaleTransition(
                    Duration.millis(450), surface);

            expand.setToX(1);
            expand.setToY(1);
            expand.setInterpolator(Interpolator.EASE_OUT);

            FadeTransition fade = new FadeTransition(
                    Duration.millis(350), surface);

            fade.setToValue(1);

            ParallelTransition appearance =
                    new ParallelTransition(expand, fade);

            transition = appearance;

            appearance.setOnFinished(event -> {
                resetSurface();
                finish("COMPLETED");
            });

            appearance.play();
        }

        private void move(double dx, double dy) {
            if (!window.isShowing()) {
                finish("HIDDEN");
                return;
            }

            var screens = Screen.getScreensForRectangle(
                    window.getX(), window.getY(),
                    window.getWidth(), window.getHeight());

            Screen screen = screens.isEmpty()
                    ? Screen.getPrimary() : screens.get(0);

            Rectangle2D bounds = screen.getVisualBounds();

            double maximumX = Math.max(
                    bounds.getMinX(),
                    bounds.getMaxX() - window.getWidth());

            double maximumY = Math.max(
                    bounds.getMinY(),
                    bounds.getMaxY() - window.getHeight());

            double startX = window.getX();
            double startY = window.getY();

            double targetX = Math.max(
                    bounds.getMinX(),
                    Math.min(maximumX, startX + dx));

            double targetY = Math.max(
                    bounds.getMinY(),
                    Math.min(maximumY, startY + dy));

            if (Math.hypot(
                    targetX - startX,
                    targetY - startY) < 2) {

                finish("EDGE");
                return;
            }

            DoubleProperty progress =
                    new SimpleDoubleProperty(0);

            progress.addListener((observable, oldValue, newValue) -> {
                double fraction = newValue.doubleValue();

                window.setX(
                        startX + (targetX - startX) * fraction);

                window.setY(
                        startY + (targetY - startY) * fraction);
            });

            Timeline movement = new Timeline(
                    new KeyFrame(
                            Duration.ZERO,
                            new KeyValue(progress, 0.0)),
                    new KeyFrame(
                            Duration.millis(750),
                            new KeyValue(
                                    progress, 1.0,
                                    Interpolator.EASE_BOTH)));

            transition = movement;

            movement.setOnFinished(event -> {
                window.setX(targetX);
                window.setY(targetY);
                finish("COMPLETED");
            });

            movement.play();
        }

        @Override
        public void stop() {
            closing = true;
            reader.shutdownNow();

            interruptTransition();

            if (accessories != null) {
                accessories.stop();
            }

            if (visual != null) {
                visual.stop();
            }
        }
    }
}
// END ORB LAUNCHER