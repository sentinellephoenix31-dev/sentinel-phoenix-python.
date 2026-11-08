import com.sun.net.httpserver.HttpServer;

import java.nio.file.Path;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        boolean servicesOnly =
                Arrays.asList(args).contains("--services");

        try (RuntimeLock lock = RuntimeLock.tryAcquire()) {
            if (lock == null) {
                System.out.println(
                        "[SENTINEL] Services are already running.");
                return;
            }

            runSentinel(args, servicesOnly);

        } catch (Exception error) {
            System.err.println(
                    "[SENTINEL ERROR] " + error.getMessage());
            error.printStackTrace();
            System.exit(1);
        }
    }

    private static void runSentinel(
            String[] args, boolean servicesOnly) throws Exception {

        Path root = Path.of(".").toAbsolutePath().normalize();

        HoneypotService honeypot = HoneypotService.start(root);

        HttpServer dashboard;

        try {
            dashboard = DashboardServer.start(root);

        } catch (Exception error) {
            try {
                honeypot.close();
            } catch (Exception closeError) {
                error.addSuppressed(closeError);
            }

            throw error;
        }

        CountDownLatch stopped = new CountDownLatch(1);
        AtomicBoolean cleaned = new AtomicBoolean(false);

        Runnable cleanup = () -> {
            if (!cleaned.compareAndSet(false, true)) {
                return;
            }

            try {
                dashboard.stop(0);
            } catch (Exception error) {
                System.err.println(
                        "[DASHBOARD STOP] " + error.getMessage());
            }

            try {
                honeypot.close();
            } catch (Exception error) {
                System.err.println(
                        "[HONEYPOT STOP] " + error.getMessage());
            }

            stopped.countDown();
            System.out.println("[SENTINEL] Services stopped.");
        };

        Thread shutdownHook = new Thread(
                cleanup, "sentinel-services-shutdown");

        try {
            Runtime.getRuntime().addShutdownHook(shutdownHook);

            System.out.println(
                    "[SENTINEL] Runtime version: SERVICES-2");
            System.out.println(
                    "[SENTINEL] Single-instance protection: ACTIVE");
            System.out.println(
                    "[SENTINEL] Dashboard: http://127.0.0.1:8080/");
            System.out.println(
                    "[SENTINEL] Mode: "
                            + (servicesOnly
                                ? "BACKGROUND SERVICES"
                                : "TEXT CONVERSATION"));

            if (servicesOnly) {
                // Never pass --services to BrainConversation.
                // Keep the honeypot and dashboard alive.
                stopped.await();

            } else {
                BrainConversation.main(args);
            }

        } finally {
            cleanup.run();

            try {
                Runtime.getRuntime().removeShutdownHook(shutdownHook);
            } catch (IllegalStateException ignored) {
                // JVM shutdown is already in progress.
            }
        }
    }
}