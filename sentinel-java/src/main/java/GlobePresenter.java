import javafx.animation.AnimationTimer;
import javafx.geometry.Pos;
import javafx.scene.*;
import javafx.scene.control.Label;
import javafx.scene.layout.StackPane;
import javafx.scene.paint.Color;
import javafx.scene.paint.PhongMaterial;
import javafx.scene.shape.Box;
import javafx.scene.shape.Sphere;
import javafx.scene.transform.Rotate;

/** A miniature 3D presenter inside the replay, using the replay's sole TTS. */
public final class GlobePresenter {
    private final Group character = new Group();
    private final Group head = new Group();
    private final Group leftHand = new Group();
    private final Group rightHand = new Group();
    private final Group glasses = new Group();
    private final Sphere mouth = new Sphere(5, 24);
    private final Sphere leftEye = new Sphere(5, 24);
    private final Sphere rightEye = new Sphere(5, 24);
    private final Rotate turn = new Rotate(0, Rotate.Y_AXIS);
    private final Rotate lean = new Rotate(0, Rotate.Z_AXIS);
    private final Label caption = new Label("SENTINEL / RECORDED EVIDENCE");
    private final StackPane view;
    private final AnimationTimer timer;
    private boolean speaking;
    private boolean explaining;
    private String focus = "";
    private long lastFrame;
    private double time;
    private double handX = 80;
    private double handY = 28;
    private double handZ;
    private double yaw;
    private double leftX = -79;
    private double leftY = 30;
    private double leftZ;
    private double targetSide = 1;
    private double targetHeight;

    public GlobePresenter() {
        PhongMaterial shell = material("#31cdbd");
        PhongMaterial dark = material("#061723");
        PhongMaterial hands = material("#b3fff1");
        head.getChildren().add(sphere(55, 0, 0, 0, shell));
        configureEye(leftEye, -18, dark);
        configureEye(rightEye, 18, dark);
        head.getChildren().addAll(leftEye, rightEye);
        mouth.setMaterial(dark);
        mouth.setTranslateY(20);
        mouth.setTranslateZ(-53);
        mouth.setScaleX(1.8);
        mouth.setScaleZ(0.3);
        head.getChildren().add(mouth);
        for (double center : new double[] {-18, 18}) {
            for (int i = 0; i < 32; i++) {
                double a = i * Math.PI * 2 / 32;
                glasses.getChildren().add(sphere(1.3,
                        center + Math.cos(a) * 11,
                        -9 + Math.sin(a) * 10, -60, dark));
            }
        }
        Box bridge = new Box(14, 2.5, 3);
        bridge.setMaterial(dark);
        bridge.setTranslateY(-10);
        bridge.setTranslateZ(-60);
        glasses.getChildren().add(bridge);
        head.getChildren().add(glasses);
        head.getTransforms().addAll(turn, lean);
        buildHand(leftHand, hands);
        buildHand(rightHand, hands);
        leftHand.setTranslateX(-79);
        leftHand.setTranslateY(30);
        character.getChildren().addAll(head, leftHand, rightHand);
        AmbientLight ambient = new AmbientLight(Color.web("#758b9b"));
        PointLight key = new PointLight(Color.web("#effff8"));
        key.setTranslateX(-120);
        key.setTranslateY(-130);
        key.setTranslateZ(-190);
        SubScene scene = new SubScene(new Group(character, ambient, key),
                270, 240, true, SceneAntialiasing.BALANCED);
        scene.setFill(Color.TRANSPARENT);
        PerspectiveCamera camera = new PerspectiveCamera(true);
        camera.setFieldOfView(36);
        camera.setNearClip(0.1);
        camera.setFarClip(1500);
        camera.setTranslateZ(-390);
        scene.setCamera(camera);
        caption.setStyle("-fx-text-fill:#bbffeb;-fx-font-size:10px;"
                + "-fx-background-color:#09232b;-fx-padding:5 8;"
                + "-fx-background-radius:8;");
        view = new StackPane(scene, caption);
        view.setPrefSize(270, 240);
        view.setMaxSize(270, 240);
        view.setMouseTransparent(true);
        StackPane.setAlignment(caption, Pos.BOTTOM_CENTER);
        glasses.setVisible(false);
        timer = new AnimationTimer() {
            @Override public void handle(long now) {
                double dt = lastFrame == 0 ? 0 : Math.min(0.05,
                        (now - lastFrame) / 1_000_000_000.0);
                lastFrame = now;
                time += dt;
                double amount = 1 - Math.exp(-dt * 7);
                boolean pointing = speaking && !focus.isBlank();
                boolean pointRight = pointing && targetSide >= 0;
                boolean pointLeft = pointing && targetSide < 0;
                double tx = pointRight ? 108 : 80;
                double ty = pointRight ? -9 + targetHeight * 45 : 28;
                double tz = pointRight ? -40 : -5;
                handX += (tx - handX) * amount;
                handY += (ty - handY) * amount;
                handZ += (tz - handZ) * amount;
                rightHand.setTranslateX(handX);
                rightHand.setTranslateY(handY);
                rightHand.setTranslateZ(handZ);
                rightHand.setRotationAxis(Rotate.Z_AXIS);
                rightHand.setRotate(pointRight ? 65 : 12);
                leftX += ((pointLeft ? -108 : -79) - leftX) * amount;
                leftY += ((pointLeft ? -9 + targetHeight * 45 : 30) - leftY) * amount;
                leftZ += ((pointLeft ? -40 : -5) - leftZ) * amount;
                leftHand.setTranslateX(leftX); leftHand.setTranslateY(leftY); leftHand.setTranslateZ(leftZ);
                leftHand.setRotationAxis(Rotate.Z_AXIS); leftHand.setRotate(pointLeft ? -65 : -12);
                yaw += ((pointing ? -23 * targetSide : 0) - yaw) * amount;
                turn.setAngle(yaw);
                lean.setAngle(explaining ? -3 : 0);
                character.setTranslateY(Math.sin(time * 1.4) * 1.5);
                double blink = Math.sin(time * 0.82) > 0.995 ? 0.12 : 1;
                leftEye.setScaleY(blink * 1.5);
                rightEye.setScaleY(blink * 1.5);
                // Speaking activity, not phoneme or amplitude based lip sync.
                mouth.setScaleY(speaking ? 0.35 + Math.abs(
                        Math.sin(time * 7.1) * Math.sin(time * 2.9)) : 0.23);
                glasses.setVisible(explaining);
            }
        };
        timer.start();
    }

    private static PhongMaterial material(String color) {
        PhongMaterial result = new PhongMaterial(Color.web(color));
        result.setSpecularColor(Color.WHITE);
        result.setSpecularPower(90);
        return result;
    }
    private static Sphere sphere(double radius, double x, double y, double z,
                                 PhongMaterial material) {
        Sphere result = new Sphere(radius, 24);
        result.setMaterial(material);
        result.setTranslateX(x);
        result.setTranslateY(y);
        result.setTranslateZ(z);
        return result;
    }
    private static void configureEye(Sphere eye, double x, PhongMaterial material) {
        eye.setMaterial(material);
        eye.setTranslateX(x);
        eye.setTranslateY(-9);
        eye.setTranslateZ(-53);
        eye.setScaleZ(0.4);
    }
    private static void buildHand(Group group, PhongMaterial material) {
        Sphere palm = sphere(9, 0, 0, 0, material);
        palm.setScaleY(1.2);
        group.getChildren().add(palm);
        for (int i = 0; i < 3; i++) {
            Sphere finger = sphere(2.8, -5 + i * 5, -10, -2, material);
            finger.setScaleY(i == 0 ? 2 : 1.3);
            group.getChildren().add(finger);
        }
    }
    public StackPane view() { return view; }
    public void aimAt(Node target) {
        var destination = target.localToScene(target.getBoundsInLocal());
        var origin = view.localToScene(view.getBoundsInLocal());
        if (destination == null || origin == null) return;
        double dx = destination.getMinX() + destination.getWidth() / 2
                - origin.getMinX() - origin.getWidth() / 2;
        double dy = destination.getMinY() + destination.getHeight() / 2
                - origin.getMinY() - origin.getHeight() / 2;
        targetSide = dx < 0 ? -1 : 1;
        targetHeight = Math.max(-1, Math.min(1, dy / 160));
    }
    public void prepare() {
        explaining = true;
        speaking = false;
        caption.setText("SENTINEL / PREPARING EXPLANATION");
    }
    public void speak(String target) {
        explaining = true;
        speaking = true;
        focus = target;
        caption.setText("SENTINEL / " + target.toUpperCase(java.util.Locale.ROOT));
    }
    public void rest() {
        explaining = false;
        speaking = false;
        focus = "";
        caption.setText("SENTINEL / RECORDED EVIDENCE");
    }
    public void stop() { timer.stop(); rest(); }
}
