import nu.pattern.OpenCV;

import org.opencv.core.Mat;
import org.opencv.imgproc.Imgproc;
import org.opencv.videoio.VideoCapture;
import org.opencv.videoio.Videoio;

import javax.swing.*;
import java.awt.*;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import java.awt.image.BufferedImage;
import java.awt.image.DataBufferByte;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class CameraPreview {

    private final JFrame window =
            new JFrame("Sentinel Phoenix | Camera test");

    private final JLabel status =
            new JLabel("CAMERA OFF", SwingConstants.CENTER);

    private final JButton start =
            new JButton("Start camera");

    private final JButton stop =
            new JButton("Stop camera");

    private final JSpinner cameraIndex =
            new JSpinner(new SpinnerNumberModel(0, 0, 9, 1));

    private final AtomicBoolean capturing =
            new AtomicBoolean(false);

    private final AtomicBoolean closing =
            new AtomicBoolean(false);

    private final AtomicReference<BufferedImage> latestImage =
            new AtomicReference<>();

    private final ExecutorService worker =
            Executors.newSingleThreadExecutor(task -> {
                Thread thread =
                        new Thread(task, "sentinel-camera-preview");

                thread.setDaemon(true);
                return thread;
            });

    private final JPanel preview = new JPanel() {
        @Override
        protected void paintComponent(Graphics graphics) {
            super.paintComponent(graphics);

            BufferedImage image = latestImage.get();

            if (image == null) {
                graphics.setColor(new Color(190, 210, 220));
                graphics.drawString(
                        "Camera preview appears here",
                        25,
                        35);
                return;
            }

            double scale = Math.min(
                    getWidth() / (double) image.getWidth(),
                    getHeight() / (double) image.getHeight());

            int width =
                    Math.max(1, (int) (image.getWidth() * scale));

            int height =
                    Math.max(1, (int) (image.getHeight() * scale));

            int x = (getWidth() - width) / 2;
            int y = (getHeight() - height) / 2;

            graphics.drawImage(
                    image,
                    x, y, width, height,
                    null);
        }
    };

    private final Timer repaintTimer =
            new Timer(80, event -> preview.repaint());

    private void show() {
        window.setDefaultCloseOperation(
                WindowConstants.DO_NOTHING_ON_CLOSE);

        preview.setBackground(new Color(12, 20, 28));
        preview.setPreferredSize(new Dimension(720, 480));

        status.setForeground(new Color(0, 130, 100));
        status.setBorder(
                BorderFactory.createEmptyBorder(10, 10, 10, 10));

        JPanel controls = new JPanel();

        controls.add(new JLabel("Camera index:"));
        controls.add(cameraIndex);
        controls.add(start);
        controls.add(stop);

        JLabel notice = new JLabel(
                "Local preview only. No images are saved.",
                SwingConstants.CENTER);

        notice.setBorder(
                BorderFactory.createEmptyBorder(8, 8, 8, 8));

        JPanel bottom = new JPanel(new BorderLayout());
        bottom.add(controls, BorderLayout.CENTER);
        bottom.add(notice, BorderLayout.SOUTH);

        window.add(status, BorderLayout.NORTH);
        window.add(preview, BorderLayout.CENTER);
        window.add(bottom, BorderLayout.SOUTH);

        stop.setEnabled(false);

        start.addActionListener(event -> startCamera());

        stop.addActionListener(event -> {
            if (capturing.get()) {
                capturing.set(false);
                status.setText("Stopping camera...");
                stop.setEnabled(false);
            }
        });

        window.addWindowListener(new WindowAdapter() {
            @Override
            public void windowClosing(WindowEvent event) {
                closing.set(true);
                capturing.set(false);

                repaintTimer.stop();
                latestImage.set(null);

                worker.shutdown();
                window.dispose();
            }
        });

        window.pack();
        window.setLocationRelativeTo(null);
        window.setVisible(true);

        repaintTimer.start();
    }

    private void startCamera() {
        if (closing.get()
                || !capturing.compareAndSet(false, true)) {
            return;
        }

        int index = ((Number) cameraIndex.getValue()).intValue();

        start.setEnabled(false);
        stop.setEnabled(true);
        cameraIndex.setEnabled(false);

        status.setText("Opening camera " + index + "...");

        worker.execute(() -> capture(index));
    }

    private void updateStatus(String message) {
        SwingUtilities.invokeLater(() -> {
            if (!closing.get()) {
                status.setText(message);
            }
        });
    }

    private void capture(int index) {
        VideoCapture camera = null;
        Mat frame = null;
        Mat converted = null;

        String finalStatus = "CAMERA OFF";

        try {
            OpenCV.loadLocally();

            if (!capturing.get() || closing.get()) {
                return;
            }

            camera = new VideoCapture();

            boolean windows = System.getProperty("os.name", "")
                    .toLowerCase(java.util.Locale.ROOT)
                    .contains("win");

            boolean opened = camera.open(
                    index,
                    windows
                            ? Videoio.CAP_DSHOW
                            : Videoio.CAP_ANY);

            if (!opened) {
                throw new IllegalStateException(
                        "Cannot open camera " + index
                                + ". Check camera permissions "
                                + "or try another index.");
            }

            if (!capturing.get() || closing.get()) {
                return;
            }

            camera.set(Videoio.CAP_PROP_FRAME_WIDTH, 640);
            camera.set(Videoio.CAP_PROP_FRAME_HEIGHT, 480);

            frame = new Mat();
            converted = new Mat();

            updateStatus("CAMERA ON — local preview");

            int failedFrames = 0;

            while (capturing.get() && !closing.get()) {
                if (!camera.read(frame) || frame.empty()) {
                    failedFrames++;

                    if (failedFrames >= 20) {
                        throw new IllegalStateException(
                                "The camera stopped returning images.");
                    }

                    Thread.sleep(50);
                    continue;
                }

                failedFrames = 0;

                Mat image;

                if (frame.channels() == 4) {
                    Imgproc.cvtColor(
                            frame,
                            converted,
                            Imgproc.COLOR_BGRA2BGR);

                    image = converted;

                } else if (frame.channels() == 1) {
                    Imgproc.cvtColor(
                            frame,
                            converted,
                            Imgproc.COLOR_GRAY2BGR);

                    image = converted;

                } else if (frame.channels() == 3) {
                    image = frame;

                } else {
                    throw new IllegalStateException(
                            "Unsupported camera image format.");
                }

                BufferedImage buffered = new BufferedImage(
                        image.cols(),
                        image.rows(),
                        BufferedImage.TYPE_3BYTE_BGR);

                byte[] pixels = ((DataBufferByte)
                        buffered.getRaster().getDataBuffer())
                        .getData();

                if (image.isContinuous()) {
                    image.get(0, 0, pixels);

                } else {
                    int rowSize = image.cols() * 3;
                    byte[] row = new byte[rowSize];

                    for (int y = 0; y < image.rows(); y++) {
                        image.get(y, 0, row);

                        System.arraycopy(
                                row, 0,
                                pixels, y * rowSize,
                                rowSize);
                    }
                }

                latestImage.set(buffered);

                Thread.sleep(40);
            }

        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            finalStatus = "Camera interrupted.";

        } catch (Exception | LinkageError error) {
            finalStatus = "CAMERA ERROR: " + error.getMessage();

            System.err.println("[CAMERA] " + error);
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

            capturing.set(false);
            latestImage.set(null);

            String message = finalStatus;

            SwingUtilities.invokeLater(() -> {
                if (!closing.get()) {
                    status.setText(message);
                    start.setEnabled(true);
                    stop.setEnabled(false);
                    cameraIndex.setEnabled(true);
                    preview.repaint();
                }
            });
        }
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(
                () -> new CameraPreview().show());
    }
}
// END CAMERA PREVIEW