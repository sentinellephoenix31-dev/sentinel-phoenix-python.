import com.google.gson.Gson;

import nu.pattern.OpenCV;

import org.opencv.core.Mat;
import org.opencv.core.Point;
import org.opencv.core.Scalar;
import org.opencv.core.Size;
import org.opencv.imgproc.Imgproc;
import org.opencv.objdetect.FaceDetectorYN;
import org.opencv.objdetect.FaceRecognizerSF;
import org.opencv.videoio.VideoCapture;
import org.opencv.videoio.Videoio;

import javax.swing.*;
import java.awt.*;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import java.awt.image.BufferedImage;
import java.awt.image.DataBufferByte;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class LocalFaceCamera implements AutoCloseable {

    private static final Gson JSON = new Gson();

    private static final double MATCH_THRESHOLD = 0.50;
    private static final int REQUIRED_MATCHES = 3;
    private static final long FRESHNESS_NANOS = 3_000_000_000L;

    public record Observation(
            String state,
            String name,
            long observedAt) {

        public boolean recognized() {
            long age = System.nanoTime() - observedAt;

            return "RECOGNIZED".equals(state)
                    && !name.isBlank()
                    && age >= 0
                    && age < FRESHNESS_NANOS;
        }
    }

    private record Profile(
            int version,
            String name,
            float[][] templates) {
    }

    private static final class Session {
        final AtomicBoolean stop = new AtomicBoolean();

        final AtomicReference<BufferedImage> image =
                new AtomicReference<>();

        final AtomicReference<String> label =
                new AtomicReference<>("Opening camera...");

        Future<?> task;
        JFrame window;
        Timer timer;
    }

    private final Path root;

    private final ExecutorService worker =
            Executors.newSingleThreadExecutor(task -> {
                Thread thread =
                        new Thread(task, "sentinel-face-camera");

                thread.setDaemon(true);
                return thread;
            });

    private final AtomicReference<Observation> observation =
            new AtomicReference<>(
                    new Observation("OFF", "", System.nanoTime()));

    private volatile Session current;
    private boolean closed;

    // Accessed only by the camera worker.
    private FaceDetectorYN detector;
    private FaceRecognizerSF recognizer;

    public LocalFaceCamera(Path root) {
        this.root = root.toAbsolutePath().normalize();
    }

    public synchronized String open() {
        if (closed) {
            return "CLOSED";
        }

        if (current != null && !current.task.isDone()) {
            return current.stop.get()
                    ? "STOPPING" : "ALREADY_OPEN";
        }

        Session session = new Session();
        current = session;

        observation.set(
                new Observation("STARTING", "", System.nanoTime()));

        session.task = worker.submit(() -> runCamera(session));

        return "STARTING";
    }

    public Observation observation() {
        Observation value = observation.get();

        if ("RECOGNIZED".equals(value.state())
                && !value.recognized()) {
            return new Observation(
                    "STALE", "", value.observedAt());
        }

        return value;
    }

    private void publish(
            Session session,
            String state,
            String name,
            String label) {

        if (current != session || session.stop.get()) {
            return;
        }

        observation.set(
                new Observation(state, name, System.nanoTime()));

        session.label.set(label);
    }

    private void requestStop(Session session) {
        session.stop.set(true);
        session.image.set(null);
        session.label.set("Stopping camera...");

        if (current == session) {
            observation.set(
                    new Observation(
                            "STOPPING", "", System.nanoTime()));
        }
    }

    public boolean stopCamera() throws InterruptedException {
        Session session = current;

        if (session == null) {
            observation.set(
                    new Observation("OFF", "", System.nanoTime()));

            return true;
        }

        requestStop(session);

        try {
            session.task.get(5, TimeUnit.SECONDS);

            observation.set(
                    new Observation("OFF", "", System.nanoTime()));

            return true;

        } catch (TimeoutException error) {
            // The native camera driver may still be returning from read/open.
            return false;

        } catch (ExecutionException error) {
            // runCamera releases its camera in finally.
            observation.set(
                    new Observation("OFF", "", System.nanoTime()));

            return true;
        }
    }

    public String forgetFace() throws Exception {
        if (!stopCamera()) {
            return "CAMERA_BUSY";
        }

        Path directory = root.resolve("data");
        Files.createDirectories(directory);

        Path lockPath = directory.resolve("face-memory.lock");

        try (FileChannel channel = FileChannel.open(
                lockPath,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE);
             FileLock lock = channel.tryLock()) {

            if (lock == null) {
                return "PROFILE_BUSY";
            }

            boolean deleted = Files.deleteIfExists(
                    directory.resolve("face-profile.json"));

            observation.set(
                    new Observation("OFF", "", System.nanoTime()));

            return deleted ? "DELETED" : "NO_PROFILE";
        }
    }

    private void ensureModels() throws Exception {
        if (detector != null && recognizer != null) {
            return;
        }

        OpenCV.loadLocally();

        Path detection = root.resolve(
                "models/face/face_detection_yunet_2023mar.onnx");

        Path recognition = root.resolve(
                "models/face/face_recognition_sface_2021dec.onnx");

        if (!Files.isRegularFile(detection)
                || Files.size(detection) < 100_000
                || !Files.isRegularFile(recognition)
                || Files.size(recognition) < 30_000_000) {

            throw new IllegalStateException(
                    "Face models are missing or incomplete.");
        }

        detector = FaceDetectorYN.create(
                detection.toString(),
                "",
                new Size(640, 480),
                0.9f,
                0.3f,
                5000);

        recognizer = FaceRecognizerSF.create(
                recognition.toString(), "");
    }

    private void createWindow(Session session) throws Exception {
        SwingUtilities.invokeAndWait(() -> {
            JFrame frame = new JFrame(
                    "Sentinel Phoenix | Camera ON");

            session.window = frame;

            JPanel preview = new JPanel() {
                @Override
                protected void paintComponent(Graphics graphics) {
                    super.paintComponent(graphics);

                    BufferedImage image = session.image.get();

                    if (image == null) {
                        graphics.setColor(Color.LIGHT_GRAY);
                        graphics.drawString(
                                "Waiting for camera...", 25, 35);
                        return;
                    }

                    double scale = Math.min(
                            getWidth() / (double) image.getWidth(),
                            getHeight() / (double) image.getHeight());

                    int width =
                            Math.max(1, (int) (image.getWidth() * scale));

                    int height =
                            Math.max(1, (int) (image.getHeight() * scale));

                    graphics.drawImage(
                            image,
                            (getWidth() - width) / 2,
                            (getHeight() - height) / 2,
                            width, height,
                            null);
                }
            };

            preview.setBackground(new Color(12, 20, 28));
            preview.setPreferredSize(new Dimension(640, 480));

            JLabel label = new JLabel(
                    "Opening camera...",
                    SwingConstants.CENTER);

            label.setBorder(
                    BorderFactory.createEmptyBorder(10, 10, 10, 10));

            JButton close = new JButton("Close camera");
            close.addActionListener(event -> requestStop(session));

            JPanel bottom = new JPanel(new BorderLayout());
            bottom.add(close, BorderLayout.NORTH);

            bottom.add(
                    new JLabel(
                            "Local matching only. No photos or video saved.",
                            SwingConstants.CENTER),
                    BorderLayout.SOUTH);

            frame.add(label, BorderLayout.NORTH);
            frame.add(preview, BorderLayout.CENTER);
            frame.add(bottom, BorderLayout.SOUTH);

            frame.setDefaultCloseOperation(
                    WindowConstants.DO_NOTHING_ON_CLOSE);

            frame.addWindowListener(new WindowAdapter() {
                @Override
                public void windowClosing(WindowEvent event) {
                    requestStop(session);
                }
            });

            session.timer = new Timer(100, event -> {
                label.setText(session.label.get());
                preview.repaint();
            });

            frame.pack();
            frame.setLocationRelativeTo(null);

            if (!session.stop.get()) {
                frame.setVisible(true);
                session.timer.start();
            }
        });
    }

    private void runCamera(Session session) {
        VideoCapture camera = null;

        Mat frame = null;
        Mat converted = null;
        Mat faces = null;

        String terminalState = "OFF";

        try {
            // Preview appears before opening the camera.
            createWindow(session);

            if (session.stop.get()) {
                return;
            }

            ensureModels();

            Path directory = root.resolve("data");
            Files.createDirectories(directory);

            try (FileChannel channel = FileChannel.open(
                    directory.resolve("face-memory.lock"),
                    StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE);
                 FileLock lock = channel.tryLock()) {

                if (lock == null) {
                    throw new IllegalStateException(
                            "Close FaceMemoryWindow before opening "
                                    + "the voice-controlled camera.");
                }

                Profile profile = loadProfile();

                if (session.stop.get()) {
                    return;
                }

                camera = new VideoCapture();

                boolean windows =
                        System.getProperty("os.name", "")
                                .toLowerCase(java.util.Locale.ROOT)
                                .contains("win");

                if (!camera.open(
                        0,
                        windows
                                ? Videoio.CAP_DSHOW
                                : Videoio.CAP_ANY)) {
                    throw new IllegalStateException(
                            "Cannot open camera index 0.");
                }

                camera.set(Videoio.CAP_PROP_FRAME_WIDTH, 640);
                camera.set(Videoio.CAP_PROP_FRAME_HEIGHT, 480);

                frame = new Mat();
                converted = new Mat();
                faces = new Mat();

                int stableMatches = 0;
                int failedFrames = 0;

                while (!session.stop.get()) {
                    if (!camera.read(frame) || frame.empty()) {
                        stableMatches = 0;

                        publish(
                                session,
                                "NO_FRAME", "",
                                "Waiting for a camera frame...");

                        if (++failedFrames >= 20) {
                            throw new IllegalStateException(
                                    "Camera stopped returning images.");
                        }

                        Thread.sleep(80);
                        continue;
                    }

                    if (session.stop.get()) {
                        break;
                    }

                    failedFrames = 0;

                    Mat currentFrame;

                    if (frame.channels() == 4) {
                        Imgproc.cvtColor(
                                frame, converted,
                                Imgproc.COLOR_BGRA2BGR);

                        currentFrame = converted;

                    } else if (frame.channels() == 1) {
                        Imgproc.cvtColor(
                                frame, converted,
                                Imgproc.COLOR_GRAY2BGR);

                        currentFrame = converted;

                    } else if (frame.channels() == 3) {
                        currentFrame = frame;

                    } else {
                        throw new IllegalStateException(
                                "Unsupported camera image format.");
                    }

                    detector.setInputSize(currentFrame.size());
                    detector.detect(currentFrame, faces);

                    boolean matched = false;

                    if (faces.rows() != 1) {
                        stableMatches = 0;

                        publish(
                                session,
                                faces.rows() == 0
                                        ? "NO_FACE" : "MULTIPLE_FACES",
                                "",
                                faces.rows() == 0
                                        ? "No face detected"
                                        : "Multiple faces — matching paused");

                    } else if (profile == null) {
                        stableMatches = 0;

                        publish(
                                session,
                                "NO_PROFILE", "",
                                "No saved face profile. "
                                        + "Enroll using FaceMemoryWindow.");

                    } else if (faces.get(0, 2)[0] < 90
                            || faces.get(0, 3)[0] < 90) {
                        stableMatches = 0;

                        publish(
                                session,
                                "TOO_SMALL", "",
                                "Move closer to the camera");

                    } else {
                        float[] vector =
                                extractFeature(currentFrame, faces);

                        double score = similarity(profile, vector);

                        if (score >= MATCH_THRESHOLD) {
                            stableMatches++;

                            if (stableMatches >= REQUIRED_MATCHES) {
                                matched = true;

                                publish(
                                        session,
                                        "RECOGNIZED",
                                        profile.name(),
                                        "Recognized: " + profile.name());
                            } else {
                                publish(
                                        session,
                                        "CHECKING", "",
                                        "Checking face...");
                            }

                        } else {
                            stableMatches = 0;

                            publish(
                                    session,
                                    "UNKNOWN", "",
                                    "Unknown — no confident match");
                        }
                    }

                    if (faces.rows() == 1) {
                        double x = faces.get(0, 0)[0];
                        double y = faces.get(0, 1)[0];

                        Imgproc.rectangle(
                                currentFrame,
                                new Point(x, y),
                                new Point(
                                        x + faces.get(0, 2)[0],
                                        y + faces.get(0, 3)[0]),
                                matched
                                        ? new Scalar(80, 220, 100)
                                        : new Scalar(0, 190, 255),
                                2);
                    }

                    session.image.set(toImage(currentFrame));

                    Thread.sleep(150);
                }
            }

        } catch (Exception | LinkageError error) {
            terminalState = "ERROR";

            System.err.println(
                    "[FACE CAMERA] " + error.getMessage());

            error.printStackTrace();

        } finally {
            if (camera != null) {
                camera.release();
            }

            if (frame != null) {
                frame.release();
            }

            if (converted != null) {
                converted.release();
            }

            if (faces != null) {
                faces.release();
            }

            session.image.set(null);

            if (current == session) {
                observation.set(
                        new Observation(
                                terminalState, "", System.nanoTime()));
            }

            SwingUtilities.invokeLater(() -> {
                if (session.timer != null) {
                    session.timer.stop();
                }

                if (session.window != null) {
                    session.window.dispose();
                }
            });
        }
    }

    private float[] extractFeature(Mat frame, Mat faces) {
        Mat face = faces.row(0);
        Mat aligned = new Mat();
        Mat feature = new Mat();

        try {
            recognizer.alignCrop(frame, face, aligned);
            recognizer.feature(aligned, feature);

            if (feature.total() != 128 || feature.channels() != 1) {
                throw new IllegalStateException(
                        "Unexpected face feature format.");
            }

            float[] result = new float[128];
            feature.get(0, 0, result);
            normalize(result);

            return result;

        } finally {
            face.release();
            aligned.release();
            feature.release();
        }
    }

    private Profile loadProfile() throws Exception {
        Path file = root.resolve("data/face-profile.json");

        if (!Files.exists(file)) {
            return null;
        }

        if (!Files.isRegularFile(file)
                || Files.size(file) > 200_000) {
            throw new IllegalStateException(
                    "Invalid face profile file.");
        }

        Profile profile = JSON.fromJson(
                Files.readString(file, StandardCharsets.UTF_8),
                Profile.class);

        if (profile == null
                || profile.version() != 1
                || profile.name() == null
                || !profile.name().matches("[\\p{L}\\p{N} .'-]{1,40}")
                || profile.templates() == null
                || profile.templates().length != 8) {
            throw new IllegalStateException(
                    "Invalid saved face profile.");
        }

        for (float[] vector : profile.templates()) {
            if (vector == null || vector.length != 128) {
                throw new IllegalStateException(
                        "Invalid saved face template.");
            }

            normalize(vector);
        }

        return profile;
    }

    private static void normalize(float[] vector) {
        double sum = 0;

        for (float value : vector) {
            if (!Float.isFinite(value)) {
                throw new IllegalArgumentException(
                        "Invalid face feature.");
            }

            sum += value * (double) value;
        }

        double length = Math.sqrt(sum);

        if (length < 0.000001) {
            throw new IllegalArgumentException(
                    "Empty face feature.");
        }

        for (int i = 0; i < vector.length; i++) {
            vector[i] /= (float) length;
        }
    }

    private static double similarity(
            Profile profile, float[] candidate) {

        double[] scores =
                new double[profile.templates().length];

        for (int i = 0; i < scores.length; i++) {
            float[] reference = profile.templates()[i];

            double score = 0;

            for (int j = 0; j < reference.length; j++) {
                score += reference[j] * (double) candidate[j];
            }

            scores[i] = score;
        }

        Arrays.sort(scores);

        return (
                scores[scores.length - 1]
                        + scores[scores.length - 2]
                        + scores[scores.length - 3]
        ) / 3.0;
    }

    private static BufferedImage toImage(Mat frame) {
        BufferedImage result = new BufferedImage(
                frame.cols(),
                frame.rows(),
                BufferedImage.TYPE_3BYTE_BGR);

        byte[] pixels = ((DataBufferByte)
                result.getRaster().getDataBuffer()).getData();

        if (frame.isContinuous()) {
            frame.get(0, 0, pixels);

        } else {
            int rowLength = frame.cols() * 3;
            byte[] row = new byte[rowLength];

            for (int y = 0; y < frame.rows(); y++) {
                frame.get(y, 0, row);

                System.arraycopy(
                        row, 0,
                        pixels, y * rowLength,
                        rowLength);
            }
        }

        return result;
    }

    @Override
    public void close() {
        synchronized (this) {
            closed = true;
        }

        try {
            stopCamera();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }

        worker.shutdown();
    }
}
// END LOCAL FACE CAMERA