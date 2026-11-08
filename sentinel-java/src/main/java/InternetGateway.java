import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;

import javax.net.ssl.HttpsURLConnection;
import java.io.IOException;
import java.io.InputStream;
import java.net.Proxy;
import java.net.SocketTimeoutException;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class InternetGateway {
    private static final String ENDPOINT =
            "https://services.nvd.nist.gov/rest/json/cves/2.0";
    private static final String SOURCE = "NVD/NIST";
    private static final int TIMEOUT_MS = 10_000;
    private static final int MAX_RESPONSE_BYTES = 2 * 1024 * 1024;
    private static final int MAX_RESULTS = 5;

    private static final Pattern CVE_ID =
            Pattern.compile("\\bCVE-[0-9]{4}-[0-9]{4,}\\b", Pattern.CASE_INSENSITIVE);

    private static final Pattern SEARCH_MARKER = Pattern.compile(
            "\\b(?:search nvd|look up nvd|search vulnerabilit(?:ies|y)"
                    + "|find vulnerabilit(?:ies|y)|vulnerability database"
                    + "|cherche nvd|recherche nvd|cherche les vulnerabilites"
                    + "|recherche les vulnerabilites)\\b"
    );

    private static final List<String> CVSS_METRICS =
            List.of("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2");

    private InternetGateway() {
    }

    public static Route classify(String question) {
        String input = question == null ? "" : question.strip();
        Matcher cve = CVE_ID.matcher(input);
        if (cve.find()) {
            return new Route("CVE_LOOKUP", cve.group().toUpperCase(Locale.ROOT));
        }

        String normalized = Normalizer.normalize(input, Normalizer.Form.NFKD)
                .replaceAll("\\p{M}+", "")
                .toLowerCase(Locale.ROOT)
                .replaceAll("\\s+", " ");

        Matcher search = SEARCH_MARKER.matcher(normalized);
        if (search.find()) {
            String keywords = search.replaceFirst(" ")
                    .replaceAll("\\s+", " ")
                    .replaceAll("^[ ?.,:]+|[ ?.,:]+$", "");
            return new Route("VULNERABILITY_SEARCH", truncate(keywords, 200));
        }

        return new Route("LOCAL", "");
    }

    public static Reply answer(String question) {
        Route route = classify(question);
        if (!route.external()) {
            return new Reply(false, route.type(), null,
                    "That question does not request an NVD lookup.");
        }
        if (route.query().isBlank()) {
            return new Reply(false, route.type(), SOURCE,
                    "Tell me what product or vulnerability to search for.");
        }

        boolean singleCve = "CVE_LOOKUP".equals(route.type());
        String query = singleCve
                ? "cveId=" + encode(route.query())
                : "keywordSearch=" + encode(route.query()) + "&resultsPerPage=" + MAX_RESULTS;

        try {
            JsonObject data = fetch(query);
            if (!(data.get("vulnerabilities") instanceof JsonArray vulnerabilities)) {
                throw new IOException("INVALID_REMOTE_STRUCTURE");
            }

            List<String> descriptions = new ArrayList<>();
            for (JsonElement item : vulnerabilities) {
                JsonObject cve = object(object(item).get("cve"));
                String id = text(cve, "id");
                if (!CVE_ID.matcher(id).matches()
                        || (singleCve && !route.query().equalsIgnoreCase(id))) {
                    continue;
                }

                descriptions.add(describe(cve, id, singleCve));
                if (descriptions.size() == (singleCve ? 1 : MAX_RESULTS)) {
                    break;
                }
            }

            if (descriptions.isEmpty()) {
                return new Reply(!singleCve, route.type(), SOURCE, singleCve
                        ? "I could not find " + route.query() + " in NVD."
                        : "I found no matching vulnerabilities in NVD.");
            }

            String response = singleCve
                    ? descriptions.get(0)
                    : "NVD results for '" + route.query() + "':\n"
                            + String.join("\n", descriptions);
            return new Reply(true, route.type(), SOURCE, response);
        } catch (SocketTimeoutException error) {
            return new Reply(false, route.type(), SOURCE, "The NVD request timed out.");
        } catch (IOException error) {
            return new Reply(false, route.type(), SOURCE,
                    "I couldn't complete the NVD lookup. " + error.getMessage());
        }
    }

    private static JsonObject fetch(String query) throws IOException {
        URI uri = URI.create(ENDPOINT + "?" + query);
        HttpsURLConnection connection =
                (HttpsURLConnection) uri.toURL().openConnection(Proxy.NO_PROXY);

        try {
            connection.setInstanceFollowRedirects(false);
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(TIMEOUT_MS);
            connection.setReadTimeout(TIMEOUT_MS);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("User-Agent", "Sentinel-Phoenix/1.0");

            String apiKey = System.getenv("NVD_API_KEY");
            if (apiKey != null && !apiKey.isBlank()) {
                if (apiKey.indexOf('\r') >= 0 || apiKey.indexOf('\n') >= 0) {
                    throw new IOException("INVALID_API_KEY_FORMAT");
                }
                connection.setRequestProperty("apiKey", apiKey.strip());
            }

            int status = connection.getResponseCode();
            if (status == 429) {
                throw new IOException("REMOTE_RATE_LIMITED");
            }
            if (status != 200) {
                throw new IOException("REMOTE_HTTP_ERROR_" + status);
            }

            String contentType = connection.getContentType();
            if (contentType == null
                    || !contentType.toLowerCase(Locale.ROOT).contains("json")) {
                throw new IOException("NON_JSON_RESPONSE");
            }

            try (InputStream stream = connection.getInputStream()) {
                byte[] bytes = stream.readNBytes(MAX_RESPONSE_BYTES + 1);
                if (bytes.length > MAX_RESPONSE_BYTES) {
                    throw new IOException("RESPONSE_TOO_LARGE");
                }

                String body = StandardCharsets.UTF_8.newDecoder()
                        .decode(ByteBuffer.wrap(bytes)).toString();
                JsonElement parsed = JsonParser.parseString(body);
                if (parsed instanceof JsonObject json) {
                    return json;
                }
                throw new IOException("INVALID_REMOTE_STRUCTURE");
            } catch (JsonParseException | CharacterCodingException error) {
                throw new IOException("INVALID_REMOTE_JSON", error);
            }
        } finally {
            connection.disconnect();
        }
    }

    private static String describe(JsonObject cve, String id, boolean detailed) {
        JsonObject metrics = object(cve.get("metrics"));
        String severity = "";
        String score = "";

        for (String metricName : CVSS_METRICS) {
            if (metrics.get(metricName) instanceof JsonArray entries && !entries.isEmpty()) {
                JsonObject entry = object(entries.get(0));
                JsonObject cvss = object(entry.get("cvssData"));
                score = text(cvss, "baseScore");
                severity = text(cvss, "baseSeverity");
                if (severity.isBlank()) {
                    severity = text(entry, "baseSeverity");
                }
                break;
            }
        }

        String description = "No English description available.";
        if (cve.get("descriptions") instanceof JsonArray descriptions) {
            for (JsonElement item : descriptions) {
                JsonObject entry = object(item);
                String value = text(entry, "value");
                if ("en".equalsIgnoreCase(text(entry, "lang")) && !value.isBlank()) {
                    description = truncate(value, detailed ? 1500 : 220);
                    break;
                }
            }
        }

        StringBuilder answer = new StringBuilder(id)
                .append(" — severity ")
                .append(severity.isBlank() ? "UNKNOWN" : severity);
        if (!score.isBlank()) {
            answer.append(", CVSS ").append(score);
        }
        answer.append(". ").append(description);

        if (detailed) {
            if (!text(cve, "cisaExploitAdd").isBlank()) {
                answer.append(" The NVD record includes CISA known-exploitation information.");
            }
            String modified = text(cve, "lastModified");
            if (!modified.isBlank()) {
                answer.append(" NVD last modified: ").append(modified).append(".");
            }
            answer.append("\nNVD record: https://nvd.nist.gov/vuln/detail/").append(id);
        }

        return answer.toString();
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private static JsonObject object(JsonElement value) {
        return value instanceof JsonObject json ? json : new JsonObject();
    }

    private static String text(JsonObject object, String key) {
        JsonElement value = object.get(key);
        return value != null && value.isJsonPrimitive() ? value.getAsString() : "";
    }

    private static String truncate(String value, int maximum) {
        int length = Math.min(maximum, value.codePointCount(0, value.length()));
        return value.substring(0, value.offsetByCodePoints(0, length));
    }

    public static void main(String[] args) {
        if (args.length == 0) {
            Route cve = classify("Tell me about cve-2021-44228.");
            Route keywords = classify("Search NVD for OpenSSH.");
            Route local = classify("What happened yesterday?");

            if (!"CVE_LOOKUP".equals(cve.type())
                    || !"CVE-2021-44228".equals(cve.query())
                    || !"VULNERABILITY_SEARCH".equals(keywords.type())
                    || local.external()) {
                throw new IllegalStateException("Offline routing test failed.");
            }
            System.out.println("[NVD] Offline routing test: PASS");
            return;
        }

        Reply reply = answer(String.join(" ", args));
        System.out.println("SENTINEL > " + reply.response());
        if (reply.source() != null) {
            System.out.println("[SOURCE] " + reply.source());
        }
    }

    public record Route(String type, String query) {
        public boolean external() {
            return !"LOCAL".equals(type);
        }
    }

    public record Reply(boolean ok, String type, String source, String response) {
    }
}