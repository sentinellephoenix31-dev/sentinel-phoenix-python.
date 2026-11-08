import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import java.util.Locale;

// ============================================================
// SENTINEL PHOENIX
// GLOBE EVENT
//
// Normalizes one recorded incident for the visual replay.
// Does not request geolocation or invent coordinates.
// ============================================================

public record GlobeEvent(
        int index,
        String timestamp,
        String sourceIp,
        String type,
        String level,
        Double score,
        String behavior,
        String anomaly,
        String action,
        boolean containmentRequested,
        Boolean decoyActive,
        Boolean sandboxActive,
        String country,
        String region,
        String city,
        Double latitude,
        Double longitude,
        boolean hasGeo,
        boolean local
) {

    public static GlobeEvent from(
            JsonObject event,
            int index
    ) {
        JsonObject geo = object(
                event,
                "geo",
                "geolocation",
                "geo_result",
                "globe"
        );

        String ip = text(
                event,
                "UNKNOWN",
                "source_ip",
                "ip",
                "remote_ip",
                "client_ip"
        );

        boolean local = isLocalIpv4(ip);

        Double latitude = number(event, "latitude", "lat");
        Double longitude = number(event, "longitude", "lon", "lng");

        if (latitude == null) {
            latitude = number(geo, "latitude", "lat");
        }

        if (longitude == null) {
            longitude = number(geo, "longitude", "lon", "lng");
        }

        boolean validCoordinates =
                latitude != null
                && longitude != null
                && latitude >= -90
                && latitude <= 90
                && longitude >= -180
                && longitude <= 180;

        if (local || !validCoordinates) {
            latitude = null;
            longitude = null;
        }

        String country = text(
                event,
                text(geo, "UNKNOWN", "country"),
                "country"
        );

        String region = text(
                event,
                text(geo, "—", "region"),
                "region"
        );

        String city = text(
                event,
                text(geo, "—", "city"),
                "city"
        );

        if (local) {
            country = "LOCAL / PRIVATE NETWORK";
            region = "NO PUBLIC GEOLOCATION";
            city = "—";
        }

        return new GlobeEvent(
                index,

                text(
                        event, "UNKNOWN",
                        "timestamp", "time", "created_at"
                ),

                ip,

                text(
                        event, "SECURITY_EVENT",
                        "type", "event_type", "category"
                ),

                text(
                        event, "UNKNOWN",
                        "global_level", "risk_level",
                        "level", "severity", "behavior_level"
                ).toUpperCase(Locale.ROOT),

                number(
                        event,
                        "global_score", "risk_score",
                        "score", "behavior_score"
                ),

                text(
                        event, "—",
                        "behavior_type", "behavior", "intent"
                ),

                text(
                        event, "—",
                        "anomaly_level", "anomaly"
                ),

                text(
                        event, "NOT_RECORDED",
                        "response_action", "policy_action", "action"
                ),

                Boolean.TRUE.equals(
                        bool(event, "containment_requested")
                ),

                bool(event, "decoy_active"),
                bool(event, "sandbox_active"),

                country,
                region,
                city,

                latitude,
                longitude,

                latitude != null && longitude != null,
                local
        );
    }

    // ========================================================
    // PRIVATE / LOOPBACK IPv4
    //
    // Literal parsing only: no DNS lookup.
    // ========================================================

    private static boolean isLocalIpv4(String value) {

        String[] parts = value.split("\\.", -1);

        if (parts.length != 4) {
            return false;
        }

        int[] octets = new int[4];

        for (int i = 0; i < parts.length; i++) {

            if (!parts[i].matches("[0-9]{1,3}")) {
                return false;
            }

            octets[i] = Integer.parseInt(parts[i]);

            if (octets[i] > 255) {
                return false;
            }
        }

        return octets[0] == 0
                || octets[0] == 10
                || octets[0] == 127
                || (octets[0] == 169 && octets[1] == 254)
                || (octets[0] == 172
                    && octets[1] >= 16
                    && octets[1] <= 31)
                || (octets[0] == 192 && octets[1] == 168);
    }

    private static JsonObject object(
            JsonObject source,
            String... keys
    ) {
        for (String key : keys) {

            JsonElement value = source.get(key);

            if (value != null && value.isJsonObject()) {
                return value.getAsJsonObject();
            }
        }

        return new JsonObject();
    }

    private static String text(
            JsonObject source,
            String fallback,
            String... keys
    ) {
        for (String key : keys) {

            JsonElement value = source.get(key);

            if (value != null && value.isJsonPrimitive()) {

                String result = value.getAsString().strip();

                if (!result.isEmpty()) {
                    return result;
                }
            }
        }

        return fallback;
    }

    private static Double number(
            JsonObject source,
            String... keys
    ) {
        for (String key : keys) {

            JsonElement value = source.get(key);

            if (value == null || !value.isJsonPrimitive()) {
                continue;
            }

            try {
                double result = Double.parseDouble(
                        value.getAsString()
                );

                if (Double.isFinite(result)) {
                    return result;
                }

            } catch (NumberFormatException ignored) {
                // Try the next field.
            }
        }

        return null;
    }

    private static Boolean bool(
            JsonObject source,
            String key
    ) {
        JsonElement value = source.get(key);

        if (value == null || !value.isJsonPrimitive()) {
            return null;
        }

        return switch (
                value.getAsString().toLowerCase(Locale.ROOT)
        ) {
            case "true" -> true;
            case "false" -> false;
            default -> null;
        };
    }

    // ========================================================
    // OFFLINE CHECK WITH SYNTHETIC DATA
    // Does not write to the incident history.
    // ========================================================

    public static void main(String[] args) {

        JsonObject sample = new JsonObject();

        sample.addProperty("source_ip", "192.168.1.2");
        sample.addProperty("global_score", 85);
        sample.addProperty("score", 20);
        sample.addProperty("global_level", "CRITICAL");
        sample.addProperty("containment_requested", true);

        // Private addresses must not receive a globe marker.
        sample.addProperty("latitude", 28.6);
        sample.addProperty("longitude", 77.2);

        GlobeEvent event = from(sample, 1);

        boolean passed =
                event.local()
                && !event.hasGeo()
                && event.latitude() == null
                && event.longitude() == null
                && Double.valueOf(85).equals(event.score())
                && event.containmentRequested()
                && event.sandboxActive() == null;

        JsonObject result = new JsonObject();

        result.addProperty("status", passed ? "PASS" : "FAIL");
        result.addProperty("synthetic_test", true);

        result.add(
                "event",
                new GsonBuilder()
                        .serializeNulls()
                        .create()
                        .toJsonTree(event)
        );

        System.out.println(
                new GsonBuilder()
                        .setPrettyPrinting()
                        .create()
                        .toJson(result)
        );
    }
}