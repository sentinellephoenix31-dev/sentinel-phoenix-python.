import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

import javax.swing.*;
import java.awt.*;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import java.awt.geom.Ellipse2D;
import java.nio.file.Path;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;

// ============================================================
// SENTINEL PHOENIX
// INCIDENT GLOBE — JAVA V1
//
// Native Java Swing rendering.
// Recorded incidents only.
// No face recognition.
// No geolocation request.
// ============================================================

public final class IncidentGlobe {

    private final List<GlobeEvent> events;
    private final JFrame frame;
    private final GlobeCanvas canvas;

    private final JTextArea details = new JTextArea();
    private final JLabel counter = new JLabel();
    private final JButton playButton = new JButton("PAUSE");

    private final Timer animation;
    private final Timer playback;

    private int currentIndex;
    private double rotation;
    private boolean playing = true;

    public IncidentGlobe(
            List<GlobeEvent> events,
            String query
    ) {
        this.events = List.copyOf(events);

        frame = new JFrame(
                "Sentinel Phoenix | Incident Intelligence"
        );

        frame.setDefaultCloseOperation(
                WindowConstants.DISPOSE_ON_CLOSE
        );

        frame.setSize(1250, 800);
        frame.setMinimumSize(new Dimension(900, 600));
        frame.setLocationRelativeTo(null);

        JPanel root = new JPanel(new BorderLayout(18, 18));

        root.setBackground(new Color(3, 12, 19));
        root.setBorder(
                BorderFactory.createEmptyBorder(22, 22, 22, 22)
        );

        JLabel title = new JLabel(
                "SENTINEL // INCIDENT INTELLIGENCE"
        );

        title.setForeground(new Color(160, 255, 225));
        title.setFont(
                new Font("SansSerif", Font.BOLD, 23)
        );

        JTextArea queryLabel = new JTextArea(query);

        queryLabel.setEditable(false);
        queryLabel.setLineWrap(true);
        queryLabel.setWrapStyleWord(true);
        queryLabel.setOpaque(false);
        queryLabel.setForeground(new Color(100, 180, 165));

        JPanel header = new JPanel(new BorderLayout(0, 8));
        header.setOpaque(false);
        header.add(title, BorderLayout.NORTH);
        header.add(queryLabel, BorderLayout.CENTER);

        root.add(header, BorderLayout.NORTH);

        canvas = new GlobeCanvas();
        root.add(canvas, BorderLayout.CENTER);

        details.setEditable(false);
        details.setLineWrap(true);
        details.setWrapStyleWord(true);

        details.setFont(
                new Font("SansSerif", Font.PLAIN, 15)
        );

        details.setForeground(new Color(210, 255, 240));
        details.setBackground(new Color(8, 25, 33));

        details.setBorder(
                BorderFactory.createEmptyBorder(20, 20, 20, 20)
        );

        JScrollPane scroll = new JScrollPane(details);
        scroll.setPreferredSize(new Dimension(330, 500));

        root.add(scroll, BorderLayout.EAST);

        JButton previous = new JButton("PREVIOUS");
        JButton next = new JButton("NEXT");

        previous.addActionListener(event -> select(currentIndex - 1));
        next.addActionListener(event -> select(currentIndex + 1));

        playButton.addActionListener(event -> {
            playing = !playing;
            playButton.setText(playing ? "PAUSE" : "PLAY");
        });

        counter.setForeground(new Color(160, 230, 210));

        JPanel controls = new JPanel(
                new FlowLayout(FlowLayout.LEFT, 12, 0)
        );

        controls.setOpaque(false);
        controls.add(previous);
        controls.add(playButton);
        controls.add(next);
        controls.add(counter);

        root.add(controls, BorderLayout.SOUTH);

        frame.setContentPane(root);

        animation = new Timer(33, event -> {
            GlobeEvent selected = current();

            if (selected != null && selected.hasGeo()) {

                double target = -selected.longitude();

                double delta =
                        ((target - rotation) % 360 + 540) % 360 - 180;

                rotation += delta * 0.05;

            } else {
                rotation = (rotation + 0.12) % 360;
            }

            canvas.repaint();
        });

        playback = new Timer(12000, event -> {
            if (playing && this.events.size() > 1) {
                select(currentIndex + 1);
            }
        });

        frame.addWindowListener(new WindowAdapter() {
            @Override
            public void windowClosed(WindowEvent event) {
                animation.stop();
                playback.stop();
            }
        });

        boolean hasEvents = !events.isEmpty();

        previous.setEnabled(hasEvents);
        next.setEnabled(hasEvents);
        playButton.setEnabled(hasEvents);

        select(0);
    }

    public void show() {
        frame.setVisible(true);
        animation.start();
        playback.start();
    }

    private GlobeEvent current() {
        return events.isEmpty() ? null : events.get(currentIndex);
    }

    private void select(int index) {

        if (events.isEmpty()) {
            details.setText(
                    "NO MATCHING SECURITY EVENTS\n\n"
                            + "No recorded event matches this query.\n\n"
                            + "Try the latest incidents or another period."
            );

            counter.setText("0 / 0");
            return;
        }

        currentIndex = Math.floorMod(index, events.size());

        GlobeEvent event = current();

        String location = event.local()
                ? "LOCAL / PRIVATE NETWORK"
                : event.hasGeo()
                    ? event.country()
                    : "GEOLOCATION UNAVAILABLE";

        details.setText(
                "RECORDED INCIDENT\n\n"
                        + "RISK LEVEL\n" + event.level() + "\n\n"
                        + "GLOBAL SCORE\n"
                        + (event.score() == null
                            ? "Not recorded"
                            : event.score() + " / 100")
                        + "\n\nSOURCE IP\n" + event.sourceIp()
                        + "\n\nLOCATION\n" + location
                        + "\n\nTIMESTAMP\n" + event.timestamp()
                        + "\n\nBEHAVIOR\n" + event.behavior()
                        + "\n\nANOMALY\n" + event.anomaly()
                        + "\n\nRECORDED POLICY ACTION\n" + event.action()
                        + "\n\nCONTAINMENT REQUESTED\n"
                        + event.containmentRequested()
                        + "\n\nDECOY ACTIVE\n" + state(event.decoyActive())
                        + "\n\nSANDBOX ACTIVE\n" + state(event.sandboxActive())
                        + "\n\n"
                        + (event.hasGeo()
                            ? "IP coordinates are approximate. "
                              + "They do not identify a person."
                            : "No geographic position is plotted.")
                        + "\n\nA containment request alone does not "
                        + "prove that traffic was blocked."
        );

        details.setCaretPosition(0);

        counter.setText(
                (currentIndex + 1) + " / " + events.size()
        );

        if (playback != null) {
            playback.restart();
        }

        canvas.repaint();
    }

    private static String state(Boolean value) {
        return value == null ? "Not recorded" : value.toString();
    }

    private final class GlobeCanvas extends JPanel {

        private double radius;
        private double centerX;
        private double centerY;

        GlobeCanvas() {
            setOpaque(false);
        }

        private double[] project(double latitude, double longitude) {

            double lat = Math.toRadians(latitude);
            double lon = Math.toRadians(longitude + rotation);

            return new double[] {
                    centerX + radius * Math.cos(lat) * Math.sin(lon),
                    centerY - radius * Math.sin(lat),
                    Math.cos(lat) * Math.cos(lon)
            };
        }

        @Override
        protected void paintComponent(Graphics graphics) {

            super.paintComponent(graphics);

            Graphics2D g = (Graphics2D) graphics.create();

            try {
                g.setRenderingHint(
                        RenderingHints.KEY_ANTIALIASING,
                        RenderingHints.VALUE_ANTIALIAS_ON
                );

                centerX = getWidth() / 2.0;
                centerY = getHeight() / 2.0;

                radius = Math.max(
                        1,
                        Math.min(getWidth(), getHeight()) * 0.37
                );

                Ellipse2D sphere = new Ellipse2D.Double(
                        centerX - radius,
                        centerY - radius,
                        radius * 2,
                        radius * 2
                );

                g.setPaint(
                        new GradientPaint(
                                (float) (centerX - radius),
                                (float) (centerY - radius),
                                new Color(25, 80, 90),
                                (float) (centerX + radius),
                                (float) (centerY + radius),
                                new Color(1, 7, 13)
                        )
                );

                g.fill(sphere);

                g.setColor(new Color(75, 245, 200, 160));
                g.setStroke(new BasicStroke(1.5f));
                g.draw(sphere);

                g.setStroke(new BasicStroke(1f));
                g.setColor(new Color(70, 190, 170, 95));

                for (int lat = -60; lat <= 60; lat += 30) {

                    double[] previous = null;

                    for (int lon = -180; lon <= 180; lon += 3) {
                        double[] point = project(lat, lon);
                        drawSegment(g, previous, point);
                        previous = point;
                    }
                }

                for (int lon = -180; lon < 180; lon += 30) {

                    double[] previous = null;

                    for (int lat = -90; lat <= 90; lat += 3) {
                        double[] point = project(lat, lon);
                        drawSegment(g, previous, point);
                        previous = point;
                    }
                }

                drawContinents(g);

                GlobeEvent event = current();

                if (event != null && event.hasGeo()) {

                    double[] point = project(
                            event.latitude(),
                            event.longitude()
                    );

                    if (point[2] > 0) {

                        double pulse = 10 + 3 * Math.sin(
                                System.nanoTime() / 300_000_000.0
                        );

                        g.setColor(new Color(120, 255, 210));

                        g.draw(new Ellipse2D.Double(
                                point[0] - pulse,
                                point[1] - pulse,
                                pulse * 2,
                                pulse * 2
                        ));

                        g.fill(new Ellipse2D.Double(
                                point[0] - 4,
                                point[1] - 4,
                                8,
                                8
                        ));
                    }
                }

                g.setColor(new Color(150, 220, 205));
                g.setFont(new Font("SansSerif", Font.PLAIN, 12));

                String notice = event == null
                        ? "NO MATCHING EVENTS"
                        : event.hasGeo()
                            ? "APPROXIMATE IP LOCATION"
                            : "NO GEOGRAPHIC POSITION AVAILABLE";

                int textWidth = g.getFontMetrics()
                        .stringWidth(notice);

                g.drawString(
                        notice,
                        (int) (centerX - textWidth / 2.0),
                        (int) (centerY + radius + 35)
                );

            } finally {
                g.dispose();
            }
        }

        private void drawSegment(
                Graphics2D g,
                double[] previous,
                double[] point
        ) {
            if (previous != null
                    && previous[2] > 0
                    && point[2] > 0) {

                g.drawLine(
                        (int) previous[0],
                        (int) previous[1],
                        (int) point[0],
                        (int) point[1]
                );
            }
        }

        private void drawContinents(Graphics2D g) {

            // Simplified outlines: longitude, latitude.
            double[][][] continents = {
                    {
                            {-168,66}, {-150,70}, {-130,56},
                            {-122,48}, {-105,50}, {-95,42},
                            {-82,27}, {-96,18}, {-108,23},
                            {-118,32}, {-135,52}, {-168,66}
                    },
                    {
                            {-81,12}, {-67,8}, {-52,-3},
                            {-47,-18}, {-56,-34}, {-68,-55},
                            {-75,-38}, {-73,-18}, {-81,12}
                    },
                    {
                            {-11,36}, {3,44}, {15,47},
                            {31,45}, {39,55}, {26,70},
                            {7,71}, {-8,58}, {-11,36}
                    },
                    {
                            {-17,35}, {10,37}, {32,30},
                            {44,10}, {38,-18}, {20,-35},
                            {5,-32}, {-8,-10}, {-16,14}, {-17,35}
                    },
                    {
                            {30,40}, {53,55}, {84,72},
                            {125,64}, {154,50}, {139,32},
                            {110,20}, {88,8}, {67,24},
                            {43,29}, {30,40}
                    },
                    {
                            {112,-12}, {134,-10}, {153,-27},
                            {142,-39}, {116,-35}, {112,-12}
                    }
            };

            g.setColor(new Color(100, 255, 200, 180));
            g.setStroke(new BasicStroke(2f));

            for (double[][] continent : continents) {

                for (int i = 1; i < continent.length; i++) {

                    double[] a = continent[i - 1];
                    double[] b = continent[i];

                    double[] previous = null;

                    for (int step = 0; step <= 20; step++) {

                        double fraction = step / 20.0;

                        double longitude =
                                a[0] + (b[0] - a[0]) * fraction;

                        double latitude =
                                a[1] + (b[1] - a[1]) * fraction;

                        double[] point = project(
                                latitude,
                                longitude
                        );

                        drawSegment(g, previous, point);
                        previous = point;
                    }
                }
            }
        }
    }

    // ========================================================
    // STANDALONE LAUNCH
    // ========================================================

    public static void main(String[] args) throws Exception {

        String query = args.length == 0
                ? "latest"
                : String.join(" ", args);

        IncidentReplayQuery engine = new IncidentReplayQuery(
                Path.of("."),
                ZoneId.of("Asia/Kolkata")
        );

        JsonObject payload =
                engine.replayPayloadForQuery(query);

        JsonArray items = payload.getAsJsonArray("events");

        Gson gson = new Gson();

        List<GlobeEvent> events = new ArrayList<>();

        for (var item : items) {
            events.add(
                    gson.fromJson(item, GlobeEvent.class)
            );
        }

        SwingUtilities.invokeLater(
                () -> new IncidentGlobe(events, query).show()
        );
    }
}