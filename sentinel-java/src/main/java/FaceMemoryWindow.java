import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

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
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class FaceMemoryWindow {

    private static final Gson JSON =
            new GsonBuilder().setPrettyPrinting().create();

    private static final int REQUIRED_SAMPLES = 8;

    // Starting values for this demonstration, not calibrated guarantees.
    private static final double MATCH_THRESHOLD = 0.50;
    private static final double ENROLLMENT_CONSISTENCY = 0.45;
    private static final int REQUIRED_MATCHES = 3;

    private final Path root =
            Path.of(".").toAbsolutePath().normalize();

    private final Path profileFile =
            root.resolve("data/face-profile.json");

    private final JFrame window =
            new JFrame("Sentinel Phoenix | Face memory");

    private final JLabel statusLabel =
            new JLabel("Loading face models...", SwingConstants.CENTER);

    private final JTextField nameField =
            new JTextField("David", 12);

    private final JSpinner cameraIndex =
            new JSpinner(new SpinnerNumberModel(0, 0, 9, 1));

    private final JCheckBox consent =
            new JCheckBox("I agree to save my face template locally");

    private final JButton start = new JButton("Start camera");
    private final JButton stop = new JButton("Stop camera");
    private final JButton enroll = new JButton("Remember my face");
    private final JButton forget = new JButton("Forget saved face");

    private final AtomicBoolean closing = new AtomicBoolean();
    private final AtomicBoolean cameraRequested = new AtomicBoolean();
    private final AtomicBoolean cameraBusy = new AtomicBoolean();
    private final AtomicBoolean ready = new AtomicBoolean();
    private final AtomicBoolean deleteRequested = new AtomicBoolean();

    private final AtomicReference<String> enrollmentRequest =
            new AtomicReference<>();

    private final AtomicReference<String> status =
            new AtomicReference<>("Loading face models...");

    private final AtomicReference<BufferedImage> image =
            new AtomicReference<>();

    private final AtomicReference<Profile> savedProfile =
            new AtomicReference<>();

    private volatile int requestedCameraIndex;

    // The following fields are used only by the camera worker.
    private FaceDetectorYN detector;
    private FaceRecognizerSF recognizer;

    private String enrollmentName = "";
    private final List<float[]> samples = new ArrayList<>();
    private long enrollmentDeadline;
    private long nextSample;

    private int stableMatches;
    private int failedFrames;

    private record Profile(
            int version,
            String name,
            float[][] templates) {
    }

    private final JPanel preview = new JPanel() {
        @Override
        protected void paintComponent(Graphics graphics) {
            super.paintComponent(graphics);

            BufferedImage current = image.get();

            if (current == null) {
                graphics.setColor(new Color(190, 210, 220));
                graphics.drawString(
                        "Camera off — no images are being saved",
                        25, 35);
                return;
            }

            double scale = Math.min(
                    getWidth() / (double) current.getWidth(),
                    getHeight() / (double) current.getHeight());

            int width = Math.max(
                    1, (int) (current.getWidth() * scale));

            int height = Math.max(
                    1, (int) (current.getHeight() * scale));

            graphics.drawImage(
                    current,
                    (getWidth() - width) / 2,
                    (getHeight() - height) / 2,
                    width, height,
                    null);
        }
    };

    private final Timer timer = new Timer(100, event -> updateUi());

    private void show() {
        window.setDefaultCloseOperation(
                WindowConstants.DO_NOTHING_ON_CLOSE);

        preview.setPreferredSize(new Dimension(720, 480));
        preview.setBackground(new Color(12, 20, 28));

        statusLabel.setBorder(
                BorderFactory.createEmptyBorder(10, 10, 10, 10));

        JPanel cameraControls = new JPanel();
        cameraControls.add(new JLabel("Camera:"));
        cameraControls.add(cameraIndex);
        cameraControls.add(start);
        cameraControls.add(stop);

        JPanel profileControls = new JPanel();
        profileControls.add(new JLabel("Profile name:"));
        profileControls.add(nameField);
        profileControls.add(enroll);
        profileControls.add(forget);

        JPanel bottom = new JPanel();
        bottom.setLayout(new BoxLayout(bottom, BoxLayout.Y_AXIS));

        cameraControls.setAlignmentX(Component.CENTER_ALIGNMENT);
        profileControls.setAlignmentX(Component.CENTER_ALIGNMENT);
        consent.setAlignmentX(Component.CENTER_ALIGNMENT);

        JLabel notice = new JLabel(
                "Local face templates only. No photos or video are saved.");

        notice.setAlignmentX(Component.CENTER_ALIGNMENT);

        bottom.add(cameraControls);
        bottom.add(profileControls);
        bottom.add(consent);
        bottom.add(Box.createVerticalStrut(6));
        bottom.add(notice);
        bottom.add(Box.createVerticalStrut(10));

        window.add(statusLabel, BorderLayout.NORTH);
        window.add(preview, BorderLayout.CENTER);
        window.add(bottom, BorderLayout.SOUTH);

        start.addActionListener(event -> {
            requestedCameraIndex =
                    ((Number) cameraIndex.getValue()).intValue();

            cameraRequested.set(true);
            status.set("Opening camera...");
        });

        stop.addActionListener(event -> {
            cameraRequested.set(false);
            status.set("Stopping camera...");
        });

        enroll.addActionListener(event -> {
            String name = nameField.getText().strip();

            if (name.isBlank()
                    || name.length() > 40
                    || !name.matches("[\\p{L}\\p{N} .'-]+")) {
                status.set("Enter a name using 1 to 40 normal characters.");
                return;
            }

            if (!consent.isSelected()) {
                status.set("Select the consent checkbox before enrollment.");
                return;
            }

            enrollmentRequest.set(name);
        });

        forget.addActionListener(event -> {
            deleteRequested.set(true);
            status.set("Deleting saved face template...");
        });

        window.addWindowListener(new WindowAdapter() {
            @Override
            public void windowClosing(WindowEvent event) {
                closing.set(true);
                cameraRequested.set(false);
                image.set(null);
                timer.stop();
                window.dispose();
            }
        });

        updateUi();

        window.pack();
        window.setLocationRelativeTo(null);
        window.setVisible(true);
        timer.start();

        Thread worker = new Thread(
                this::runWorker, "sentinel-face-memory");

        worker.setDaemon(true);
        worker.start();
    }

    private void updateUi() {
        statusLabel.setText(status.get());

        boolean available = ready.get();
        boolean active = cameraRequested.get();
        boolean busy = cameraBusy.get();
        boolean hasProfile = savedProfile.get() != null;

        start.setEnabled(available && !active && !busy);
        stop.setEnabled(available && active);
        cameraIndex.setEnabled(available && !active && !busy);

        enroll.setEnabled(
                available && active && busy
                        && consent.isSelected() && !hasProfile);

        forget.setEnabled(available && hasProfile);

        preview.repaint();
    }

    private void runWorker() {
        try {
            Files.createDirectories(root.resolve("data"));

            Path lockPath = root.resolve("data/face-memory.lock");

            try (FileChannel channel = FileChannel.open(
                    lockPath,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE);
                 FileLock lock = channel.tryLock()) {

                if (lock == null) {
                    throw new IllegalStateException(
                            "Another face memory window is already open.");
                }

                OpenCV.loadLocally();

                Path detectionModel = root.resolve(
                        "models/face/face_detection_yunet_2023mar.onnx");

                Path recognitionModel = root.resolve(
                        "models/face/face_recognition_sface_2021dec.onnx");

                checkModel(detectionModel, 100_000);
                checkModel(recognitionModel, 30_000_000);

                detector = FaceDetectorYN.create(
                        detectionModel.toString(),
                        "",
                        new Size(640, 480),
                        0.9f,
                        0.3f,
                        5000);

                recognizer = FaceRecognizerSF.create(
                        recognitionModel.toString(), "");

                savedProfile.set(loadProfile());

                ready.set(true);

                status.set(
                        savedProfile.get() == null
                                ? "CAMERA OFF — no face profile saved"
                                : "CAMERA OFF — saved face profile loaded");

                cameraLoop();
            }

        } catch (Exception | LinkageError error) {
            ready.set(false);
            status.set("FACE MEMORY ERROR: " + error.getMessage());

            System.err.println("[FACE MEMORY] " + error);
            error.printStackTrace();
        }
    }

    private static void checkModel(Path path, long minimum)
            throws Exception {

        if (!Files.isRegularFile(path)
                || Files.size(path) < minimum) {
            throw new IllegalStateException(
                    "Missing or incomplete model: " + path);
        }
    }

    private void cameraLoop() throws Exception {
        VideoCapture camera = null;
        Mat frame = new Mat();
        Mat converted = new Mat();
        Mat faces = new Mat();

        try {
            while (!closing.get()) {
                processDeletion();

                if (!cameraRequested.get()) {
                    enrollmentRequest.set(null);
                    cancelEnrollment();
                    stableMatches = 0;

                    if (camera != null) {
                        camera.release();
                        camera = null;

                        image.set(null);
                        status.set("CAMERA OFF");
                    }

                    cameraBusy.set(false);
                    Thread.sleep(80);
                    continue;
                }

                if (camera == null) {
                    cameraBusy.set(true);
                    camera = new VideoCapture();

                    boolean windows = System.getProperty("os.name", "")
                            .toLowerCase(java.util.Locale.ROOT)
                            .contains("win");

                    boolean opened = camera.open(
                            requestedCameraIndex,
                            windows
                                    ? Videoio.CAP_DSHOW
                                    : Videoio.CAP_ANY);

                    if (!opened) {
                        camera.release();
                        camera = null;
                        cameraRequested.set(false);
                        cameraBusy.set(false);

                        status.set(
                                "Cannot open camera. Try index 1 "
                                        + "or check Windows permissions.");

                        continue;
                    }

                    camera.set(Videoio.CAP_PROP_FRAME_WIDTH, 640);
                    camera.set(Videoio.CAP_PROP_FRAME_HEIGHT, 480);

                    failedFrames = 0;
                    status.set("CAMERA ON — looking for one face");
                }

                if (!camera.read(frame) || frame.empty()) {
                    failedFrames++;

                    if (failedFrames >= 20) {
                        cameraRequested.set(false);
                        status.set("Camera stopped returning images.");
                    }

                    Thread.sleep(50);
                    continue;
                }

                failedFrames = 0;

                if (!cameraRequested.get() || closing.get()) {
                    continue;
                }

                Mat current;

                if (frame.channels() == 4) {
                    Imgproc.cvtColor(
                            frame, converted,
                            Imgproc.COLOR_BGRA2BGR);

                    current = converted;

                } else if (frame.channels() == 1) {
                    Imgproc.cvtColor(
                            frame, converted,
                            Imgproc.COLOR_GRAY2BGR);

                    current = converted;

                } else if (frame.channels() == 3) {
                    current = frame;

                } else {
                    throw new IllegalStateException(
                            "Unsupported camera image format.");
                }

                String requestedName =
                        enrollmentRequest.getAndSet(null);

                if (requestedName != null) {
                    if (savedProfile.get() != null) {
                        status.set(
                                "A profile already exists. "
                                        + "Delete it before enrolling again.");
                    } else {
                        samples.clear();
                        enrollmentName = requestedName;

                        enrollmentDeadline = System.nanoTime()
                                + 30_000_000_000L;

                        nextSample = 0;
                        stableMatches = 0;
                    }
                }

                detector.setInputSize(current.size());
                detector.detect(current, faces);

                processFaces(current, faces);

                image.set(toImage(current));

                Thread.sleep(80);
            }

        } finally {
            if (camera != null) {
                camera.release();
            }

            frame.release();
            converted.release();
            faces.release();

            cameraBusy.set(false);
            cameraRequested.set(false);
            image.set(null);
            cancelEnrollment();
        }
    }

    private void processDeletion() throws Exception {
        if (!deleteRequested.getAndSet(false)) {
            return;
        }

        Files.deleteIfExists(profileFile);

        savedProfile.set(null);
        enrollmentRequest.set(null);
        cancelEnrollment();
        stableMatches = 0;

        status.set("Saved face profile deleted.");

        // The status may subsequently change when new camera frames arrive.
        // No raw camera frames are stored on disk.
    }

    private void cancelEnrollment() {
        enrollmentName = "";
        samples.clear();
        enrollmentDeadline = 0;
        nextSample = 0;
    }

    private void processFaces(Mat frame, Mat faces)
            throws Exception {

        long now = System.nanoTime();

        if (!enrollmentName.isBlank()
                && now >= enrollmentDeadline) {
            cancelEnrollment();
            status.set("Enrollment timed out. No profile was saved.");
            return;
        }

        if (faces.rows() != 1) {
            stableMatches = 0;

            if (!enrollmentName.isBlank()) {
                samples.clear();
                status.set(
                        "Enrollment: keep exactly one face in view.");
            } else {
                status.set(
                        faces.rows() == 0
                                ? "CAMERA ON — no face detected"
                                : "Multiple faces — identification paused");
            }

            return;
        }

        double width = faces.get(0, 2)[0];
        double height = faces.get(0, 3)[0];

        if (width < 90 || height < 90) {
            stableMatches = 0;

            if (!enrollmentName.isBlank()) {
                samples.clear();
            }

            status.set("Move closer to the camera.");
            return;
        }

        Mat face = faces.row(0);
        Mat aligned = new Mat();
        Mat feature = new Mat();

        float[] vector;

        try {
            recognizer.alignCrop(frame, face, aligned);
            recognizer.feature(aligned, feature);

            if (feature.total() != 128 || feature.channels() != 1) {
                throw new IllegalStateException(
                        "Unexpected face feature format.");
            }

            vector = new float[128];
            feature.get(0, 0, vector);
            normalize(vector);

        } finally {
            face.release();
            aligned.release();
            feature.release();
        }

        boolean recognized = false;

        if (!enrollmentName.isBlank()) {
            if (now >= nextSample) {
                if (!samples.isEmpty()
                        && cosine(samples.get(0), vector)
                                < ENROLLMENT_CONSISTENCY) {

                    samples.clear();

                    status.set(
                            "Enrollment restarted: keep the same "
                                    + "person facing the camera.");
                } else {
                    samples.add(vector.clone());
                }

                nextSample = now + 450_000_000L;

                if (samples.size() >= REQUIRED_SAMPLES) {
                    String name = enrollmentName;

                    Profile profile = new Profile(
                            1,
                            name,
                            samples.toArray(new float[0][]));

                    saveProfile(profile);
                    savedProfile.set(profile);
                    cancelEnrollment();

                    status.set(
                            "Face profile saved. Look away, "
                                    + "then look back to test it.");

                } else {
                    status.set(
                            "Saving face samples: "
                                    + samples.size() + "/"
                                    + REQUIRED_SAMPLES
                                    + " — move your head only slightly");
                }
            }

        } else {
            Profile profile = savedProfile.get();

            if (profile == null) {
                stableMatches = 0;
                status.set("Face detected — no saved profile");

            } else {
                double score = similarity(profile, vector);

                if (score >= MATCH_THRESHOLD) {
                    stableMatches++;

                    if (stableMatches >= REQUIRED_MATCHES) {
                        recognized = true;

                        status.set(
                                "Recognized: " + profile.name()
                                        + " — local visual match");
                    } else {
                        status.set("Checking face...");
                    }

                } else {
                    stableMatches = 0;
                    status.set(
                            "Unknown — no confident match "
                                    + "to the saved profile");
                }
            }
        }

        double x = faces.get(0, 0)[0];
        double y = faces.get(0, 1)[0];

        Imgproc.rectangle(
                frame,
                new Point(x, y),
                new Point(x + width, y + height),
                recognized
                        ? new Scalar(80, 220, 100)
                        : new Scalar(0, 190, 255),
                2);
    }

    private static double similarity(
            Profile profile, float[] candidate) {

        double[] scores = new double[profile.templates().length];

        for (int i = 0; i < scores.length; i++) {
            scores[i] = cosine(
                    profile.templates()[i], candidate);
        }

        Arrays.sort(scores);

        int count = Math.min(3, scores.length);
        double total = 0;

        for (int i = 0; i < count; i++) {
            total += scores[scores.length - 1 - i];
        }

        return total / count;
    }

    private static void normalize(float[] vector) {
        double sum = 0;

        for (float value : vector) {
            if (!Float.isFinite(value)) {
                throw new IllegalArgumentException(
                        "Invalid face feature value.");
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

    private static double cosine(float[] first, float[] second) {
        double result = 0;

        for (int i = 0; i < first.length; i++) {
            result += first[i] * (double) second[i];
        }

        return result;
    }

    private Profile loadProfile() throws Exception {
        if (!Files.exists(profileFile)) {
            return null;
        }

        if (!Files.isRegularFile(profileFile)
                || Files.size(profileFile) > 200_000) {
            throw new IllegalStateException(
                    "Invalid face profile file.");
        }

        Profile profile = JSON.fromJson(
                Files.readString(
                        profileFile, StandardCharsets.UTF_8),
                Profile.class);

        if (profile == null
                || profile.version() != 1
                || profile.name() == null
                || profile.name().isBlank()
                || profile.name().length() > 40
                || profile.templates() == null
                || profile.templates().length != REQUIRED_SAMPLES) {
            throw new IllegalStateException(
                    "The saved face profile is invalid.");
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

    private void saveProfile(Profile profile) throws Exception {
        Files.createDirectories(profileFile.getParent());

        Path temporary = Files.createTempFile(
                profileFile.getParent(), "face-profile-", ".tmp");

        try {
            Files.writeString(
                    temporary,
                    JSON.toJson(profile),
                    StandardCharsets.UTF_8);

            try {
                Files.move(
                        temporary,
                        profileFile,
                        StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.ATOMIC_MOVE);

            } catch (AtomicMoveNotSupportedException error) {
                Files.move(
                        temporary,
                        profileFile,
                        StandardCopyOption.REPLACE_EXISTING);
            }

        } finally {
            Files.deleteIfExists(temporary);
        }
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

    public static void main(String[] args) {
        SwingUtilities.invokeLater(
                () -> new FaceMemoryWindow().show());
    }
}
// END FACE MEMORY WINDOW