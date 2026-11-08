import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

// ============================================================
// SENTINEL PHOENIX
// EVIDENCE BRIDGE V1.0
//
// Discovers evidence every 10 seconds.
// Applies retention policies every 60 seconds.
//
// Does not modify the face recognition module.
// ============================================================

public final class EvidenceBridge implements AutoCloseable {

    public static final String VERSION = "1.0";

    private static final long SCAN_INTERVAL_SECONDS = 10;
    private static final long CLEANUP_INTERVAL_SECONDS = 60;

    private static final Gson JSON = new GsonBuilder()
            .serializeNulls()
            .setPrettyPrinting()
            .create();

    private final EvidenceLifecycle lifecycle;

    private ScheduledExecutorService executor;

    private boolean cleanupCompleted;
    private long lastCleanupNanos;

    public EvidenceBridge(Path root) throws IOException {
        lifecycle = new EvidenceLifecycle(root);
    }

    // ========================================================
    // DISCOVERY
    // ========================================================

    public synchronized JsonObject discoverNewEvidence() {

        JsonObject result = new JsonObject();

        JsonArray registered = new JsonArray();
        JsonArray alreadyRegistered = new JsonArray();
        JsonArray errors = new JsonArray();

        try {
            List<JsonObject> discoveries =
                    lifecycle.discoverEvidence();

            for (JsonObject discovery : discoveries) {

                String status = text(discovery, "status");

                switch (status) {
                    case "REGISTERED" ->
                            registered.add(
                                    text(discovery, "evidence_id")
                            );

                    case "ALREADY_REGISTERED" ->
                            alreadyRegistered.add(
                                    text(discovery, "evidence_id")
                            );

                    case "", "NOT_FOUND" -> {
                        // No actionable error.
                    }

                    default ->
                            errors.add(discovery.deepCopy());
                }
            }

            result.addProperty(
                    "status",
                    errors.isEmpty()
                            ? "DISCOVERY_COMPLETE"
                            : "DISCOVERY_PARTIAL"
            );

        } catch (Exception error) {

            result.addProperty("status", "ERROR");
            result.addProperty("stage", "DISCOVERY");
            result.addProperty("reason", error.toString());
        }

        result.add("registered", registered);
        result.add("already_registered", alreadyRegistered);
        result.add("errors", errors);

        return result;
    }

    // ========================================================
    // ONE MAINTENANCE CYCLE
    // ========================================================

    public synchronized JsonObject runOnce(boolean cleanup) {

        JsonObject discovery = discoverNewEvidence();
        JsonObject cleanupResult;
        JsonObject evidence;

        if (cleanup) {
            try {
                cleanupResult = lifecycle.cleanupEvidence();

            } catch (Exception error) {
                cleanupResult = errorResult(error);
            }

        } else {
            cleanupResult = new JsonObject();
            cleanupResult.addProperty("status", "SKIPPED");
        }

        try {
            evidence = lifecycle.evidenceStatus();

        } catch (Exception error) {
            evidence = errorResult(error);
        }

        boolean healthy =
                "DISCOVERY_COMPLETE".equals(
                        text(discovery, "status")
                )
                && (!cleanup
                    || "CLEANUP_COMPLETE".equals(
                            text(cleanupResult, "status")
                    ))
                && "ONLINE".equals(
                        text(evidence, "status")
                );

        JsonObject result = new JsonObject();

        result.addProperty(
                "status",
                healthy
                        ? "BRIDGE_CYCLE_COMPLETE"
                        : "BRIDGE_CYCLE_DEGRADED"
        );

        result.addProperty("version", VERSION);
        result.add("discovery", discovery);
        result.add("cleanup", cleanupResult);
        result.add("evidence", evidence);

        return result;
    }

    // ========================================================
    // BACKGROUND MAINTENANCE
    // ========================================================

    private void backgroundCycle() {

        try {
            long now = System.nanoTime();

            boolean cleanupDue =
                    !cleanupCompleted
                    || now - lastCleanupNanos
                    >= TimeUnit.SECONDS.toNanos(
                            CLEANUP_INTERVAL_SECONDS
                    );

            JsonObject result = runOnce(cleanupDue);

            JsonObject discovery =
                    result.getAsJsonObject("discovery");

            JsonArray registered =
                    discovery.getAsJsonArray("registered");

            if (!registered.isEmpty()) {

                System.out.println(
                        "[EVIDENCE] New evidence registered: "
                                + registered.size()
                );

                registered.forEach(id ->
                        System.out.println(
                                "[EVIDENCE] Registered: "
                                        + id.getAsString()
                        )
                );
            }

            if (cleanupDue) {

                JsonObject cleanup =
                        result.getAsJsonObject("cleanup");

                if ("CLEANUP_COMPLETE".equals(
                        text(cleanup, "status")
                )) {
                    cleanupCompleted = true;
                    lastCleanupNanos = System.nanoTime();

                    JsonArray deleted =
                            cleanup.getAsJsonArray("deleted");

                    if (deleted != null && !deleted.isEmpty()) {
                        System.out.println(
                                "[EVIDENCE] Retention cleanup: "
                                        + deleted.size()
                                        + " item(s) deleted."
                        );
                    }

                    boolean countExceeded =
                            cleanup.has("count_limit_exceeded")
                            && cleanup.get(
                                    "count_limit_exceeded"
                            ).getAsBoolean();

                    boolean storageExceeded =
                            cleanup.has("storage_limit_exceeded")
                            && cleanup.get(
                                    "storage_limit_exceeded"
                            ).getAsBoolean();

                    if (countExceeded || storageExceeded) {
                        System.out.println(
                                "[EVIDENCE] Storage policy limit "
                                        + "remains exceeded. "
                                        + "KEEP evidence is preserved."
                        );
                    }
                }
            }

            if (!"BRIDGE_CYCLE_COMPLETE".equals(
                    text(result, "status")
            )) {
                System.err.println(
                        "[EVIDENCE] Maintenance warning:\n"
                                + JSON.toJson(result)
                );
            }

        } catch (Exception error) {

            // A failed cycle must not stop future scans.
            System.err.println(
                    "[EVIDENCE] Background cycle failed: "
                            + error
            );
        }
    }

    // ========================================================
    // START
    // ========================================================

    public synchronized void start() {

        if (executor != null) {

            if (!executor.isShutdown()) {
                return;
            }

            if (!executor.isTerminated()) {
                throw new IllegalStateException(
                        "Previous evidence worker is still stopping."
                );
            }
        }

        cleanupCompleted = false;
        lastCleanupNanos = 0L;

        executor = Executors.newSingleThreadScheduledExecutor(
                task -> {
                    Thread thread = new Thread(
                            task,
                            "sentinel-evidence-lifecycle"
                    );

                    thread.setDaemon(true);
                    return thread;
                }
        );

        executor.scheduleWithFixedDelay(
                this::backgroundCycle,
                0,
                SCAN_INTERVAL_SECONDS,
                TimeUnit.SECONDS
        );

        System.out.println(
                "[EVIDENCE] Lifecycle bridge started."
        );

        System.out.println(
                "[EVIDENCE] Watching: "
                        + lifecycle.directory()
        );
    }

    // ========================================================
    // STATUS
    // ========================================================

    public synchronized JsonObject status() {

        JsonObject result = new JsonObject();

        result.addProperty("version", VERSION);

        result.addProperty(
                "running",
                executor != null && !executor.isShutdown()
        );

        result.addProperty(
                "evidence_directory",
                lifecycle.directory().toString()
        );

        result.addProperty(
                "scan_interval_seconds",
                SCAN_INTERVAL_SECONDS
        );

        result.addProperty(
                "cleanup_interval_seconds",
                CLEANUP_INTERVAL_SECONDS
        );

        return result;
    }

    // ========================================================
    // STOP
    // ========================================================

    @Override
    public void close() {

        ScheduledExecutorService worker;

        synchronized (this) {
            worker = executor;

            if (worker == null) {
                return;
            }

            worker.shutdownNow();
        }

        // Wait outside the monitor: a cycle may need it to finish.
        try {
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {

                System.err.println(
                        "[EVIDENCE] Worker is still stopping."
                );

                return;
            }

        } catch (InterruptedException error) {

            Thread.currentThread().interrupt();
            return;
        }

        synchronized (this) {
            if (executor == worker) {
                executor = null;
            }
        }

        System.out.println(
                "[EVIDENCE] Lifecycle bridge stopped."
        );
    }

    // ========================================================
    // HELPERS
    // ========================================================

    private static String text(
            JsonObject object,
            String key
    ) {
        if (object == null
                || !object.has(key)
                || object.get(key).isJsonNull()
                || !object.get(key).isJsonPrimitive()) {
            return "";
        }

        return object.get(key).getAsString();
    }

    private static JsonObject errorResult(Exception error) {

        JsonObject result = new JsonObject();

        result.addProperty("status", "ERROR");
        result.addProperty("reason", error.toString());

        return result;
    }

    // ========================================================
    // MANUAL CHECK
    //
    // Discovery and status only.
    // Does not run retention cleanup.
    // ========================================================

    public static void main(String[] args) throws IOException {

        try (EvidenceBridge bridge =
                     new EvidenceBridge(Path.of("."))) {

            System.out.println(
                    JSON.toJson(bridge.runOnce(false))
            );
        }
    }
}