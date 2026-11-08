import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Map;

final class AdaptiveDeception {
    private record Profile(
            String hostname, String user, String cwd, String os,
            String network, String users, String listing,
            String database, String processes
    ) {}

    private static final List<String> IDS =
            List.of("analytics-db", "backup-node", "devops-runner", "web-gateway");

    private static final List<String> RECON = List.of(
            "whoami", "id", "pwd", "ls", "hostname", "uname",
            "cat /etc/os-release", "cat /etc/passwd", "ip ", "ifconfig", "ps "
    );

    private static final Map<String, Profile> PROFILES = Map.of(
        "backup-node", new Profile("phoenix-backup-01", "backup", "/srv/backup",
            "NAME=\"Ubuntu\"\nVERSION=\"22.04.5 LTS (Jammy Jellyfish)\"\nID=ubuntu\n",
            network("eth0", "10.44.8.21", "21"),
            "root:x:0:0:root:/root:/bin/bash\n"
                + "backup:x:1001:1001:Backup Service:/srv/backup:/bin/bash\n"
                + "monitor:x:1002:1002:Monitoring:/opt/monitor:/usr/sbin/nologin\n",
            "drwxr-xr-x  archives\ndrwxr-xr-x  database\ndrwxr-xr-x  logs\n"
                + "drwxr-xr-x  scripts\n-rw-r--r--  system-backup.tar.gz\n",
            "backup_catalog\narchive_index\nretention_jobs\n",
            "root       1  0.0  init\nbackup   318  0.1  backup-agent\n"
                + "monitor  472  0.0  metrics-agent\n"),
        "web-gateway", new Profile("edge-web-02", "app", "/opt/webapp",
            "PRETTY_NAME=\"Debian GNU/Linux 12 (bookworm)\"\n"
                + "NAME=\"Debian GNU/Linux\"\nVERSION_ID=\"12\"\n",
            network("ens18", "10.44.12.14", "14"),
            "root:x:0:0:root:/root:/bin/bash\n"
                + "app:x:1001:1001:Web Application:/opt/webapp:/bin/bash\n"
                + "www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin\n",
            "drwxr-xr-x  config\ndrwxr-xr-x  logs\ndrwxr-xr-x  public\n"
                + "drwxr-xr-x  releases\n-rw-r--r--  app.env.example\n",
            "sessions\nfrontend_cache\napplication_events\n",
            "root       1  0.0  init\nwww-data 221  0.2  nginx\napp      384  0.3  gunicorn\n"),
        "analytics-db", new Profile("analytics-db-03", "postgres", "/var/lib/postgresql",
            "PRETTY_NAME=\"Ubuntu 24.04.1 LTS\"\nNAME=\"Ubuntu\"\nVERSION_ID=\"24.04\"\n",
            network("eth0", "10.44.20.31", "31"),
            "root:x:0:0:root:/root:/bin/bash\n"
                + "postgres:x:113:118:PostgreSQL:/var/lib/postgresql:/bin/bash\n"
                + "analyst:x:1003:1003:Analytics:/home/analyst:/bin/bash\n",
            "drwx------  16\ndrwx------  backups\ndrwx------  data\n"
                + "drwx------  exports\n-rw-------  recovery.notes\n",
            "analytics\ntelemetry\nreporting\n",
            "root       1  0.0  init\npostgres 247  0.4  postgres\n"
                + "postgres 261  0.1  walwriter\n"),
        "devops-runner", new Profile("ci-runner-07", "runner", "/home/runner/work",
            "NAME=\"Alpine Linux\"\nID=alpine\nVERSION_ID=3.20.3\n",
            network("eth0", "10.44.30.17", "17"),
            "root:x:0:0:root:/root:/bin/ash\nrunner:x:1000:1000:CI Runner:/home/runner:/bin/ash\n",
            "drwxr-xr-x  artifacts\ndrwxr-xr-x  builds\ndrwxr-xr-x  cache\n"
                + "drwxr-xr-x  pipelines\n-rw-r--r--  runner-config.example\n",
            "pipeline_history\nartifact_index\nrunner_jobs\n",
            "root       1  0.0  init\nrunner   184  0.2  runner-agent\n"
                + "runner   211  0.1  job-worker\n")
    );

    record Interaction(
            String command, String response, String profileId, int generation,
            int interactions, int rotations, boolean rotated, String rotationReason,
            String error
    ) {}

    private AdaptiveDeception() {}

    static Interaction processInteraction(
            Path directory, String id, String ip, String payload,
            Map<String, Object> fusion
    ) throws IOException {
        String command = DeceptionEngine.truncate(payload, 512)
                .split("[\\r\\n\\u000b\\u000c\\u001c-\\u001e\\u0085\\u2028\\u2029]", 2)[0]
                .strip();
        String level = String.valueOf(fusion.getOrDefault("global_level", "LOW"))
                .toUpperCase(Locale.ROOT);
        Path surfaceFile = directory.resolve("surface.json");
        Map<String, Object> surface = DeceptionEngine.readObject(surfaceFile);
        String now = Instant.now().toString();

        if (surface.isEmpty()) {
            surface.put("version", "1.0");
            surface.put("profile_id", initialProfile(id + "|" + ip + "|" + level));
            surface.put("generation", 1);
            surface.put("interactions", 0);
            surface.put("rotations", 0);
            surface.put("created_at", now);
            surface.put("last_rotation_at", null);
            surface.put("last_rotation_reason", null);
        }

        int interactions = number(surface, "interactions", 0) + 1;
        int generation = number(surface, "generation", 1);
        int rotations = number(surface, "rotations", 0);
        String profileId = (String) surface.get("profile_id");
        int threshold = switch (level) {
            case "CRITICAL" -> 3;
            case "HIGH" -> 4;
            case "MEDIUM" -> 5;
            default -> 6;
        };

        String normalized = command.toLowerCase(Locale.ROOT);
        boolean rotated = interactions % threshold == 0
                && RECON.stream().anyMatch(normalized::startsWith);

        if (rotated) {
            profileId = IDS.get((IDS.indexOf(profileId) + 1) % IDS.size());
            generation++;
            rotations++;
            surface.put("last_rotation_at", now);
            surface.put("last_rotation_reason", "RECON_ACTIVITY");
        }

        Profile profile = PROFILES.get(profileId);
        if (profile == null) {
            throw new IOException("Unknown deception profile: " + profileId);
        }

        Path fakeSystem = directory.resolve("fake_system");
        Map<String, String> files = Map.of(
                "hostname.txt", profile.hostname() + "\n",
                "os-release.txt", profile.os(),
                "users.txt", profile.users(),
                "network.txt", profile.network(),
                "database.txt", profile.database()
        );
        for (var file : files.entrySet()) {
            DeceptionEngine.atomicWrite(fakeSystem.resolve(file.getKey()), file.getValue());
        }

        surface.put("profile_id", profileId);
        surface.put("interactions", interactions);
        surface.put("generation", generation);
        surface.put("rotations", rotations);
        surface.put("last_seen", now);
        DeceptionEngine.writeObject(surfaceFile, surface);

        return new Interaction(
                command, render(profile, command, normalized), profileId, generation,
                interactions, rotations, rotated, (String) surface.get("last_rotation_reason"),
                null
        );
    }

    private static String render(Profile profile, String command, String normalized) {
        return switch (normalized) {
            case "" -> profile.user() + "@" + profile.hostname() + ":" + profile.cwd() + "$ ";
            case "help" -> """
                    Available commands:
                    whoami
                    id
                    pwd
                    ls
                    ls -la
                    hostname
                    uname -a
                    cat /etc/os-release
                    cat /etc/passwd
                    ip a
                    ifconfig
                    ps aux
                    exit
                    """;
            case "whoami" -> profile.user() + "\n";
            case "id" -> "uid=1001(%1$s) gid=1001(%1$s) groups=1001(%1$s)\n"
                    .formatted(profile.user());
            case "pwd" -> profile.cwd() + "\n";
            case "hostname" -> profile.hostname() + "\n";
            case "uname -a" -> "Linux " + profile.hostname()
                    + " 6.8.0-phoenix #1 SMP x86_64 GNU/Linux\n";
            case "cat /etc/os-release" -> profile.os();
            case "cat /etc/passwd" -> profile.users();
            case "ip a", "ifconfig" -> profile.network();
            case "ps aux", "ps" -> profile.processes();
            case "exit" -> "Connection closed.\n";
            case "ls" -> profile.listing();
            default -> normalized.startsWith("ls ") ? profile.listing()
                    : "bash: " + command.split("(?U)\\s+", 2)[0] + ": command not found\n";
        };
    }

    private static String initialProfile(String seed) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(seed.getBytes(StandardCharsets.UTF_8));
            long prefix = ByteBuffer.wrap(digest).getLong();
            return IDS.get((int) Long.remainderUnsigned(prefix, IDS.size()));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static int number(Map<String, Object> values, String key, int fallback) {
        return ((Number) values.getOrDefault(key, fallback)).intValue();
    }

    private static String network(String adapter, String ip, String suffix) {
        return "2: " + adapter + ": <BROADCAST,MULTICAST,UP>\n"
                + "    inet " + ip + "/24\n    inet6 fe80::" + suffix + "/64\n";
    }
}