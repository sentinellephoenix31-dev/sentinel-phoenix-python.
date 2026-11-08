import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class RuntimeLock implements AutoCloseable {
    private static final Path LOCK_FILE = Path.of(
            System.getProperty("user.home"),
            ".cache",
            "sentinel-phoenix-java-runtime.lock"
    );

    private final FileChannel channel;
    private final FileLock lock;
    private boolean closed;

    private RuntimeLock(FileChannel channel, FileLock lock) {
        this.channel = channel;
        this.lock = lock;
    }

    public static RuntimeLock tryAcquire() throws IOException {
        Files.createDirectories(LOCK_FILE.getParent());

        FileChannel channel = FileChannel.open(
                LOCK_FILE,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE
        );

        try {
            FileLock lock;
            try {
                lock = channel.tryLock();
            } catch (OverlappingFileLockException alreadyLocked) {
                channel.close();
                return null;
            }

            if (lock == null) {
                channel.close();
                return null;
            }

            RuntimeLock runtimeLock = new RuntimeLock(channel, lock);

            try {
                byte[] pid = Long.toString(ProcessHandle.current().pid())
                        .getBytes(StandardCharsets.UTF_8);

                channel.truncate(0);
                channel.position(0);

                ByteBuffer buffer = ByteBuffer.wrap(pid);
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }

                channel.force(true);
                return runtimeLock;
            } catch (IOException | RuntimeException error) {
                try {
                    runtimeLock.close();
                } catch (IOException closeError) {
                    error.addSuppressed(closeError);
                }
                throw error;
            }
        } catch (IOException | RuntimeException error) {
            try {
                channel.close();
            } catch (IOException closeError) {
                error.addSuppressed(closeError);
            }
            throw error;
        }
    }

    @Override
    public synchronized void close() throws IOException {
        if (closed) {
            return;
        }

        closed = true;
        try {
            lock.release();
        } finally {
            channel.close();
        }
    }

    public static void main(String[] args) throws IOException {
        try (RuntimeLock runtimeLock = tryAcquire()) {
            if (runtimeLock == null) {
                System.out.println("[RUNTIME] Sentinel Java is already running.");
                System.out.println("[RUNTIME] Second instance blocked.");
                return;
            }

            System.out.println("[RUNTIME] Instance lock acquired.");
            System.out.println("[RUNTIME] Press Enter to release the lock.");

            new java.io.BufferedReader(
                    new java.io.InputStreamReader(System.in, StandardCharsets.UTF_8)
            ).readLine();
        }

        System.out.println("[RUNTIME] Instance lock released.");
    }
}