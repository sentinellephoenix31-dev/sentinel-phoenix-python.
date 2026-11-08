import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.Map;

public final class HoneypotService implements AutoCloseable {
    private static final int READ_TIMEOUT_MS = 2_000;
    private static final String BANNER = "Sentinel Phoenix Honeypot\r\n";

    private final ServerSocket server;
    private final EventLogger logger;
    private final SourceMemory memory;
    private final LearningEngine learningEngine;
    private final PolicyEngine policyEngine = new PolicyEngine();
    private final DeceptionEngine deceptionEngine;
    private final SandboxEngine sandboxEngine = new SandboxEngine();
    private final Thread worker;

    private Socket activeClient;

    private HoneypotService(Path root, ServerSocket server, SourceMemory memory) {
        this.server = server;
        this.memory = memory;
        this.logger = new EventLogger(root);
        this.learningEngine = new LearningEngine(root);
        this.deceptionEngine = new DeceptionEngine(root);
        this.worker = new Thread(this::listen, "sentinel-honeypot");
        this.worker.setDaemon(true);
    }

    public static HoneypotService start(Path root) throws IOException, SQLException {
        SourceMemory memory = new SourceMemory(root);
        ServerSocket server = new ServerSocket();

        try {
            server.setReuseAddress(true);
            server.bind(new InetSocketAddress(
                    Config.HONEYPOT_HOST, Config.HONEYPOT_PORT
            ), 5);

            HoneypotService service = new HoneypotService(root, server, memory);
            service.worker.start();
            System.out.printf("[HONEYPOT] Listening on %s:%d%n",
                    Config.HONEYPOT_HOST, Config.HONEYPOT_PORT);
            return service;
        } catch (IOException | RuntimeException error) {
            try {
                server.close();
            } catch (IOException closeError) {
                error.addSuppressed(closeError);
            }
            throw error;
        }
    }

    public static void main(String[] args) {
        try (HoneypotService service = start(Path.of("."))) {
            service.worker.join();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        } catch (IOException | SQLException error) {
            System.err.println("[HONEYPOT ERROR] " + error.getMessage());
        }
    }

    private void listen() {
        while (!server.isClosed()) {
            try (Socket client = server.accept()) {
                synchronized (this) {
                    if (server.isClosed()) {
                        return;
                    }
                    activeClient = client;
                }

                try {
                    handleConnection(client);
                } catch (IOException | SQLException error) {
                    if (!server.isClosed()) {
                        System.err.println("[CONNECTION ERROR] " + error.getMessage());
                    }
                } finally {
                    synchronized (this) {
                        activeClient = null;
                    }
                }
            } catch (IOException error) {
                if (!server.isClosed()) {
                    System.err.println("[HONEYPOT ERROR] " + error.getMessage());
                }
                return;
            }
        }
    }

    @Override
    public synchronized void close() throws IOException {
        try {
            server.close();
        } finally {
            if (activeClient != null) {
                activeClient.close();
            }
        }
    }

    private void handleConnection(Socket client) throws IOException, SQLException {
        client.setSoTimeout(READ_TIMEOUT_MS);

        byte[] buffer = new byte[Config.MAX_PAYLOAD_SIZE];
        int bytesRead;
        try {
            bytesRead = client.getInputStream().read(buffer);
        } catch (SocketTimeoutException timeout) {
            bytesRead = 0;
        }

        String payload = new String(
                buffer, 0, Math.max(0, bytesRead), StandardCharsets.UTF_8
        ).strip();
        String ip = client.getInetAddress().getHostAddress();
        int port = client.getPort();

        Map<String, Object> analysis = PayloadAnalyser.analyzePayload(payload);
        Map<String, Object> behavior = BehaviorAnalyser.analyzeBehavior(ip, analysis);
        Map<String, Object> anomaly = AnomalyAnalyser.analyzeAnomaly(ip, payload);
        Map<String, Object> reputation =
                ReputationAnalyser.evaluateReputation(memory.getSourceMemory(ip));
        Map<String, Object> learning =
                learningEngine.evaluateLearning(analysis, behavior, anomaly, reputation);
        Map<String, Object> fusion =
                RiskFusion.fuseRisk(analysis, behavior, anomaly, reputation, learning);
        Map<String, Object> context =
                ContextEngine.buildContext(analysis, behavior, anomaly, reputation, fusion);
        Map<String, Object> response =
                policyEngine.applyPolicy(ip, fusion, behavior, anomaly, context);

        Map<String, Object> deception;
        String clientReply;
        try {
            deception = deceptionEngine.routeIfNeeded(ip, port, payload, fusion, response);
            clientReply = Boolean.TRUE.equals(deception.get("decoy_active"))
                    ? (String) deception.get("decoy_response")
                    : BANNER;
        } catch (IOException error) {
            System.err.println("[DECOY ERROR] " + error.getMessage());
            deception = DeceptionEngine.noDecoy();
            clientReply = "Temporary decoy service error.\n";
        }

        boolean decoyActive = Boolean.TRUE.equals(deception.get("decoy_active"));
        Map<String, Object> sandbox = SandboxEngine.emptySandbox();
        if (decoyActive) {
            try {
                sandbox = sandboxEngine.createSandbox((String) deception.get("decoy_session_id"));
            } catch (RuntimeException error) {
                sandbox.put("sandbox_error", error.toString());
            }
        }

        try {
            logger.recordEvent(ip, port, payload, analysis, behavior, anomaly,
                    reputation, learning, fusion, context, response, deception, sandbox);
        } catch (IOException error) {
            System.err.println("[EVENT LOG ERROR] " + error.getMessage());
        }

        try {
            memory.rememberEvent(ip, port, payload, analysis, behavior, anomaly,
                    fusion, response, deception, sandbox);
        } catch (SQLException error) {
            System.err.println("[MEMORY ERROR] " + error.getMessage());
        }

        try {
            Map<String, Object> update = learningEngine.maybeRetrainModel();
            if (Boolean.TRUE.equals(update.get("retrained"))) {
                System.out.println("[LEARNING UPDATE] " + update);
            }
        } catch (IOException | SQLException error) {
            System.err.println("[LEARNING UPDATE ERROR] " + error.getMessage());
        }

        System.out.printf(
                "[EVENT] %s:%d | Payload %s %s/100 | Behavior %s %s/100 "
                        + "(%s connections in 60 s) | Anomaly %s %s/100 "
                        + "(%s connections in 30 s) | Reputation %s %s/100 (%s previous events) "
                        + "| ML %s %s/100 (%s, %s samples)%n",
                ip, port, analysis.get("severity"), analysis.get("score"),
                behavior.get("behavior_level"), behavior.get("behavior_score"),
                behavior.get("connections_60s"), anomaly.get("anomaly_level"),
                anomaly.get("anomaly_score"), anomaly.get("connections_30s"),
                reputation.get("reputation_level"), reputation.get("reputation_score"),
                reputation.get("historical_events"), learning.get("ml_level"),
                learning.get("ml_score"), learning.get("model_status"),
                learning.get("model_samples")
        );

        System.out.printf("[FUSION] %s %s/100 | %s | Confidence %s%% | Decision %s%n",
                fusion.get("global_level"), fusion.get("global_score"),
                fusion.get("fusion_mode"), fusion.get("confidence"), fusion.get("decision"));

        System.out.printf(
                "[CONTEXT] %s %s/100 | Recommended action %s | Review required %s%n",
                context.get("context_level"), context.get("context_score"),
                context.get("recommended_action"), context.get("review_required")
        );

        System.out.printf(
                "[POLICY] Action %s | Monitoring %s | Containment requested %s%n",
                response.get("action"), response.get("monitoring_level"),
                response.get("containment_requested")
        );

        if (decoyActive) {
            System.out.printf(
                    "[DECOY] Session %s | Reused %s | Profile %s | Generation %s | Rotated %s%n",
                    deception.get("decoy_session_id"), deception.get("decoy_reused"),
                    deception.get("decoy_profile"), deception.get("surface_generation"),
                    deception.get("surface_rotated")
            );
            System.out.printf("[SANDBOX] Active %s | Reused %s | Name %s | Error %s%n",
                    sandbox.get("sandbox_active"), sandbox.get("sandbox_reused"),
                    sandbox.get("sandbox_name"), sandbox.get("sandbox_error"));
        }

        client.getOutputStream().write(clientReply.getBytes(StandardCharsets.UTF_8));
    }
}