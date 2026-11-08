import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.BufferedReader;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class DashboardServer {
    private static final Gson JSON = new Gson();

    private DashboardServer() {
    }

    public static void main(String[] args) throws IOException {
        start(Path.of("."));
    }

    public static HttpServer start(Path projectRoot) throws IOException {
        Path eventFile = projectRoot.resolve("data").resolve("events.jsonl");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(Config.DASHBOARD_HOST, Config.DASHBOARD_PORT), 0
        );

        server.createContext("/", exchange -> {
            try (exchange) {
                if (!"GET".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().set("Allow", "GET");
                    send(exchange, 405, "text/plain", "Method not allowed");
                    return;
                }

                switch (exchange.getRequestURI().getPath()) {
                    case "/" -> send(exchange, 200, "text/html", PAGE);
                    case "/api/events" -> send(exchange, 200, "application/json",
                            JSON.toJson(Map.of("events", loadEvents(eventFile))));
                    case "/api/stats" -> send(exchange, 200, "application/json",
                            JSON.toJson(Map.of(
                                    "status", "ACTIVE",
                                    "stats", calculateStats(loadEvents(eventFile))
                            )));
                    default -> send(exchange, 404, "text/plain", "Not found");
                }
            }
        });

        server.start();
        System.out.printf("[DASHBOARD] Listening on http://%s:%d/%n",
                Config.DASHBOARD_HOST, Config.DASHBOARD_PORT);
        return server;
    }

    private static List<JsonObject> loadEvents(Path eventFile) {
        Deque<JsonObject> recent = new ArrayDeque<>();

        try (BufferedReader reader = Files.newBufferedReader(eventFile, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }

                try {
                    JsonElement value = JsonParser.parseString(line);
                    if (value.isJsonObject()) {
                        recent.addFirst(value.getAsJsonObject());
                        if (recent.size() > Config.MAX_LOGS) {
                            recent.removeLast();
                        }
                    }
                } catch (JsonParseException ignored) {
                    // A line can be incomplete while the honeypot is appending it.
                }
            }
        } catch (java.nio.file.NoSuchFileException ignored) {
            return List.of();
        } catch (IOException error) {
            System.err.println("[DASHBOARD ERROR] " + error.getMessage());
            return List.of();
        }

        return new ArrayList<>(recent);
    }

    private static Map<String, Integer> calculateStats(List<JsonObject> events) {
        Map<String, Integer> stats = new LinkedHashMap<>();
        stats.put("total", events.size());

        for (String key : List.of(
                "payload_critical", "behavior_critical", "anomaly_medium",
                "anomaly_high", "anomaly_critical", "repeated_critical",
                "high_frequency", "high_entropy"
        )) {
            stats.put(key, 0);
        }

        for (JsonObject event : events) {
            if ("CRITICAL".equals(upper(event, "severity"))) {
                stats.merge("payload_critical", 1, Integer::sum);
            }
            if ("CRITICAL".equals(upper(event, "behavior_level"))) {
                stats.merge("behavior_critical", 1, Integer::sum);
            }
            switch (upper(event, "anomaly_level")) {
                case "MEDIUM" -> stats.merge("anomaly_medium", 1, Integer::sum);
                case "HIGH" -> stats.merge("anomaly_high", 1, Integer::sum);
                case "CRITICAL" -> stats.merge("anomaly_critical", 1, Integer::sum);
            }
            if ("REPEATED_CRITICAL_ACTIVITY".equals(upper(event, "behavior_type"))) {
                stats.merge("repeated_critical", 1, Integer::sum);
            }

            JsonElement value = event.get("anomaly_reasons");
            if (value instanceof JsonArray reasons) {
                if (reasons.contains(JSON.toJsonTree("HIGH_CONNECTION_FREQUENCY"))) {
                    stats.merge("high_frequency", 1, Integer::sum);
                }
                if (reasons.contains(JSON.toJsonTree("HIGH_ENTROPY"))) {
                    stats.merge("high_entropy", 1, Integer::sum);
                }
            }
        }
        return stats;
    }

    private static String upper(JsonObject event, String key) {
        JsonElement value = event.get(key);
        return value != null && value.isJsonPrimitive()
                ? value.getAsString().toUpperCase(Locale.ROOT)
                : "";
    }

    private static void send(HttpExchange exchange, int status, String contentType, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", contentType + "; charset=UTF-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }

    private static final String PAGE = """
            <!doctype html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Sentinel Phoenix</title>
                <style>
                    :root { color-scheme: dark; }
                    body {
                        margin: 0; padding: 24px; background: #050509;
                        color: #e6e7ef; font-family: "Courier New", monospace;
                    }
                    h1 { color: #ff5670; border-bottom: 2px solid; padding-bottom: 12px; }
                    .muted { color: #a0a4bb; }
                    #cards {
                        display: grid; gap: 12px;
                        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                        margin: 24px 0;
                    }
                    .card { padding: 14px; background: #0b0b16; border: 1px solid #244c49; }
                    .card strong { display: block; margin-top: 8px; color: #00ffcc; font-size: 25px; }
                    .table-wrap { overflow-x: auto; }
                    table { width: 100%; border-collapse: collapse; background: #080812; }
                    th, td { border: 1px solid #252540; padding: 8px; text-align: left; vertical-align: top; }
                    th { color: #ff7890; background: #101022; }
                    td { font-size: 12px; overflow-wrap: anywhere; }
                    .payload { min-width: 130px; max-width: 260px; }
                    .critical { color: #ff5670; }
                    .high { color: #ffab40; }
                    .medium { color: #f9dd65; }
                    .low { color: #00ffcc; }
                </style>
            </head>
            <body>
                <h1>Sentinel Phoenix</h1>
                <p class="muted">Adaptive Cyber Defense Laboratory</p>
                <div id="cards"></div>
                <h2>Live Threat Intelligence</h2>
                <p id="status" class="muted" role="status">Loading events…</p>
                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>Time (UTC)</th><th>Source</th><th>Payload Risk</th>
                                <th>Behavior Risk</th><th>Anomaly Risk</th><th>Global Risk</th>
                                <th>Policy</th><th>Decoy Session</th><th>Behavior Profile</th>
                                <th>Entropy</th><th>Z-Score</th><th>Connections (30s)</th>
                                <th>Payload</th><th>Anomaly Reasons</th>
                            </tr>
                        </thead>
                        <tbody id="events"></tbody>
                    </table>
                </div>
                <script>
                    const cards = document.getElementById('cards');
                    const events = document.getElementById('events');
                    const status = document.getElementById('status');
                    const labels = {
                        total: 'Recent events',
                        payload_critical: 'Critical payloads',
                        behavior_critical: 'Critical behavior',
                        anomaly_medium: 'Medium anomalies',
                        anomaly_high: 'High anomalies',
                        anomaly_critical: 'Critical anomalies',
                        repeated_critical: 'Repeated critical activity',
                        high_frequency: 'High frequency',
                        high_entropy: 'High entropy'
                    };

                    function cell(row, value, className = '') {
                        const entry = row.insertCell();
                        entry.textContent = value ?? '—';
                        entry.className = className;
                    }

                    function risk(row, level, score) {
                        const name = String(level || 'UNKNOWN').toUpperCase();
                        const color = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].includes(name)
                            ? name.toLowerCase() : '';
                        cell(row, name + ' / ' + (score ?? 0) + '/100', color);
                    }

                    async function readJson(url) {
                        const response = await fetch(url);
                        if (!response.ok) {
                            throw new Error('HTTP ' + response.status);
                        }
                        return response.json();
                    }

                    async function refresh() {
                        try {
                            const [summary, feed] = await Promise.all([
                                readJson('/api/stats'),
                                readJson('/api/events')
                            ]);

                            const cardList = document.createDocumentFragment();
                            for (const [key, label] of Object.entries(labels)) {
                                const card = document.createElement('div');
                                card.className = 'card';
                                card.textContent = label;
                                const count = document.createElement('strong');
                                count.textContent = summary.stats[key] ?? 0;
                                card.append(count);
                                cardList.append(card);
                            }
                            cards.replaceChildren(cardList);

                            const rows = document.createDocumentFragment();
                            for (const event of feed.events) {
                                const row = document.createElement('tr');
                                cell(row, event.timestamp);
                                cell(row, (event.source_ip ?? '—') + ':' + (event.source_port ?? '—'));
                                risk(row, event.severity, event.score);
                                risk(row, event.behavior_level, event.behavior_score);
                                risk(row, event.anomaly_level, event.anomaly_score);
                                risk(row, event.global_level, event.global_score);
                                cell(row, event.response_action);
                                cell(row, event.decoy_active
                                    ? (event.decoy_session_id ?? 'Active')
                                        + (event.decoy_reused ? ' (reused)' : '')
                                    : '—');
                                cell(row, event.behavior_type);
                                cell(row, event.entropy ?? 0);
                                cell(row, event.length_zscore ?? 0);
                                cell(row, event.connections_30s ?? 0);
                                cell(row, event.payload || '<empty>', 'payload');
                                cell(row, Array.isArray(event.anomaly_reasons)
                                    ? event.anomaly_reasons.join(', ') || '—' : '—');
                                rows.append(row);
                            }
                            events.replaceChildren(rows);
                            status.textContent = feed.events.length
                                ? 'Live feed · newest events first'
                                : 'No events recorded yet.';
                        } catch (error) {
                            status.textContent = 'Could not refresh the live feed. Retrying…';
                        } finally {
                            setTimeout(refresh, 1500);
                        }
                    }

                    refresh();
                </script>
            </body>
            </html>
            """;
}