import argparse
import html
import json
import math
import mimetypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from pathlib import Path
from urllib.parse import (
    unquote,
    urlparse,
)


# ============================================================
# SENTINEL PHOENIX
# VISUAL INCIDENT REPLAY QT V5.2
#
# Query
#   ↓
# Incident Replay Query Engine
#   ↓
# Real Replay Payload
#   ↓
# Local-only HTTP bridge
#   ↓
# Qt WebEngine
#   ↓
# Canvas Globe
#
# VirtualBox:
# 2D Canvas is preferred.
# WebGL is NOT required.
#
# No attacker payload is executed.
# ============================================================


REPLAY_QT_VERSION = "5.2"

HOST = "127.0.0.1"

DEFAULT_WIDTH = 1180
DEFAULT_HEIGHT = 760


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

UI_DIR = os.path.join(
    BASE_DIR,
    "ui",
    "incident_replay"
)

INDEX_FILE = os.path.join(
    UI_DIR,
    "index.html"
)


# ============================================================
# VIRTUALBOX / SOFTWARE RENDERING
# ============================================================

os.environ.setdefault(
    "QT_OPENGL",
    "software"
)

os.environ.setdefault(
    "QT_QUICK_BACKEND",
    "software"
)

_existing_flags = os.environ.get(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    ""
).strip()

_required_flags = (
    "--disable-gpu "
    "--disable-gpu-compositing"
)

if _required_flags not in _existing_flags:

    os.environ[
        "QTWEBENGINE_CHROMIUM_FLAGS"
    ] = (
        _existing_flags
        +
        " "
        +
        _required_flags
    ).strip()


# ============================================================
# QUERY ENGINE
# ============================================================

def get_replay_payload(
    query
):

    from core.incident_replay_query import (
        replay_payload_for_query
    )

    return replay_payload_for_query(
        query
    )


# ============================================================
# GENERIC PAYLOAD HELPERS
# ============================================================

def _first(
    mapping,
    keys,
    default=None
):

    if not isinstance(
        mapping,
        dict
    ):

        return default

    for key in keys:

        if key in mapping:

            value = mapping.get(
                key
            )

            if value not in (
                None,
                "",
            ):

                return value

    return default


def _nested_first(
    mapping,
    containers,
    keys,
    default=None
):

    direct = _first(
        mapping,
        keys,
        None
    )

    if direct not in (
        None,
        "",
    ):

        return direct

    if not isinstance(
        mapping,
        dict
    ):

        return default

    for container_name in containers:

        container = mapping.get(
            container_name
        )

        if isinstance(
            container,
            dict
        ):

            value = _first(
                container,
                keys,
                None
            )

            if value not in (
                None,
                "",
            ):

                return value

    return default


def _to_float(
    value
):

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError
    ):

        return None


# ============================================================
# INCIDENT EXTRACTION
#
# Flexible because Replay payload formats can evolve.
# ============================================================

def extract_incidents(
    payload
):

    incidents = []

    seen = set()


    def inspect(
        value
    ):

        if isinstance(
            value,
            list
        ):

            for item in value:

                inspect(
                    item
                )

            return


        if not isinstance(
            value,
            dict
        ):

            return


        latitude = _nested_first(
            value,
            (
                "geo",
                "location",
                "geolocation",
                "source_geo",
                "origin",
            ),
            (
                "lat",
                "latitude",
            ),
            None
        )


        longitude = _nested_first(
            value,
            (
                "geo",
                "location",
                "geolocation",
                "source_geo",
                "origin",
            ),
            (
                "lon",
                "lng",
                "longitude",
            ),
            None
        )


        latitude = _to_float(
            latitude
        )

        longitude = _to_float(
            longitude
        )


        ip = _nested_first(
            value,
            (
                "source",
                "origin",
                "network",
            ),
            (
                "ip",
                "source_ip",
                "src_ip",
                "remote_ip",
                "attacker_ip",
            ),
            ""
        )


        country = _nested_first(
            value,
            (
                "geo",
                "location",
                "geolocation",
                "source_geo",
                "origin",
            ),
            (
                "country",
                "country_name",
            ),
            ""
        )


        region = _nested_first(
            value,
            (
                "geo",
                "location",
                "geolocation",
                "source_geo",
                "origin",
            ),
            (
                "region",
                "region_name",
                "state",
                "city",
            ),
            ""
        )


        attack_type = _first(
            value,
            (
                "attack_type",
                "type",
                "category",
                "event_type",
                "threat",
                "classification",
                "label",
            ),
            ""
        )


        timestamp = _first(
            value,
            (
                "timestamp",
                "time",
                "datetime",
                "created_at",
                "detected_at",
            ),
            ""
        )


        severity = _first(
            value,
            (
                "severity",
                "risk",
                "level",
                "priority",
            ),
            ""
        )


        looks_like_incident = any(
            (
                latitude is not None,
                longitude is not None,
                bool(ip),
                bool(attack_type),
                bool(timestamp),
            )
        )


        if looks_like_incident:

            signature = (
                str(ip),
                str(timestamp),
                str(attack_type),
                str(latitude),
                str(longitude),
            )


            if signature not in seen:

                seen.add(
                    signature
                )


                incidents.append(
                    {
                        "latitude":
                            latitude,

                        "longitude":
                            longitude,

                        "ip":
                            str(
                                ip or ""
                            ),

                        "country":
                            str(
                                country or ""
                            ),

                        "region":
                            str(
                                region or ""
                            ),

                        "type":
                            str(
                                attack_type or "INCIDENT"
                            ),

                        "timestamp":
                            str(
                                timestamp or ""
                            ),

                        "severity":
                            str(
                                severity or ""
                            ),

                        "raw":
                            value,
                    }
                )


        for nested_value in value.values():

            if isinstance(
                nested_value,
                (
                    dict,
                    list,
                )
            ):

                inspect(
                    nested_value
                )


    inspect(
        payload
    )

    return incidents


# ============================================================
# LANGUAGE
# ============================================================

def detect_language(
    query
):

    value = str(
        query or ""
    ).lower()

    french_markers = (
        "hier",
        "nuit",
        "attaque",
        "attaques",
        "montre",
        "incident",
        "incidents",
        "aujourd",
        "passé",
        "passe",
        "dernière",
    )

    if any(
        marker in value
        for marker in french_markers
    ):

        return "fr"

    return "en"


# ============================================================
# LOCAL NARRATION
# ============================================================

def build_narration(
    query,
    payload
):

    incidents = extract_incidents(
        payload
    )

    language = detect_language(
        query
    )


    if not incidents:

        if language == "fr":

            return (
                "Visual Incident Replay ouvert. "
                "Aucun incident géolocalisé correspondant "
                "n'a été trouvé."
            )

        return (
            "Visual Incident Replay opened. "
            "No matching geolocated incident was found."
        )


    incident = incidents[
        0
    ]


    country = (
        incident.get(
            "country"
        )
        or
        "unknown region"
    )

    region = incident.get(
        "region"
    )

    attack_type = (
        incident.get(
            "type"
        )
        or
        "incident"
    )

    ip = incident.get(
        "ip"
    )

    timestamp = incident.get(
        "timestamp"
    )


    if language == "fr":

        parts = [
            "Visual Incident Replay activé.",
            (
                f"Incident principal: "
                f"{attack_type}."
            ),
        ]


        if country:

            if region:

                parts.append(
                    (
                        f"Origine approximative: "
                        f"{region}, {country}."
                    )
                )

            else:

                parts.append(
                    (
                        f"Origine approximative: "
                        f"{country}."
                    )
                )


        if ip:

            parts.append(
                f"Adresse source: {ip}."
            )


        if timestamp:

            parts.append(
                f"Détection: {timestamp}."
            )


        return " ".join(
            parts
        )


    parts = [
        "Visual Incident Replay activated.",
        (
            f"Primary incident: "
            f"{attack_type}."
        ),
    ]


    if country:

        if region:

            parts.append(
                (
                    f"Approximate origin: "
                    f"{region}, {country}."
                )
            )

        else:

            parts.append(
                (
                    f"Approximate origin: "
                    f"{country}."
                )
            )


    if ip:

        parts.append(
            f"Source address: {ip}."
        )


    if timestamp:

        parts.append(
            f"Detected at {timestamp}."
        )


    return " ".join(
        parts
    )


def speak_local(
    text,
    language
):

    executable = (
        shutil.which(
            "espeak-ng"
        )
        or
        shutil.which(
            "espeak"
        )
    )


    if executable is None:

        return False


    voice = (
        "fr+f3"
        if language == "fr"
        else
        "en-us+f3"
    )


    try:

        subprocess.Popen(
            [
                executable,
                "-v",
                voice,
                "-s",
                "165",
                str(
                    text
                ),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=True
        )

        return True

    except Exception:

        return False


# ============================================================
# LOCAL HTTP SERVER
# ============================================================

class ReplayHTTPServer(
    ThreadingHTTPServer
):

    daemon_threads = True

    allow_reuse_address = True


def create_handler(
    payload
):

    payload_bytes = json.dumps(
        payload,
        ensure_ascii=False
    ).encode(
        "utf-8"
    )


    class ReplayHandler(
        BaseHTTPRequestHandler
    ):

        def log_message(
            self,
            format_string,
            *args
        ):

            # Quiet local bridge.
            return


        def _headers(
            self,
            status=200,
            content_type="application/json; charset=utf-8",
            content_length=None
        ):

            self.send_response(
                status
            )

            self.send_header(
                "Content-Type",
                content_type
            )

            self.send_header(
                "Cache-Control",
                "no-store, no-cache, must-revalidate"
            )

            self.send_header(
                "Access-Control-Allow-Origin",
                "*"
            )

            if content_length is not None:

                self.send_header(
                    "Content-Length",
                    str(
                        content_length
                    )
                )

            self.end_headers()


        def do_OPTIONS(
            self
        ):

            self.send_response(
                204
            )

            self.send_header(
                "Access-Control-Allow-Origin",
                "*"
            )

            self.send_header(
                "Access-Control-Allow-Headers",
                "*"
            )

            self.send_header(
                "Access-Control-Allow-Methods",
                "GET, OPTIONS"
            )

            self.end_headers()


        def do_GET(
            self
        ):

            parsed = urlparse(
                self.path
            )

            request_path = unquote(
                parsed.path
            )


            # =================================================
            # PAYLOAD API
            #
            # Several aliases are intentionally provided so
            # older versions of index.html remain compatible.
            # =================================================

            if request_path in (
                "/api/replay",
                "/api/payload",
                "/api/incidents",
                "/api/replay/payload",
                "/payload.json",
                "/replay.json",
                "/incident_replay.json",
            ):

                self._headers(
                    200,
                    "application/json; charset=utf-8",
                    len(
                        payload_bytes
                    )
                )

                self.wfile.write(
                    payload_bytes
                )

                return


            # =================================================
            # ROOT
            # =================================================

            if request_path in (
                "",
                "/",
                "/index.html",
            ):

                if os.path.isfile(
                    INDEX_FILE
                ):

                    try:

                        with open(
                            INDEX_FILE,
                            "rb"
                        ) as handle:

                            body = handle.read()


                        self._headers(
                            200,
                            "text/html; charset=utf-8",
                            len(
                                body
                            )
                        )

                        self.wfile.write(
                            body
                        )

                        return

                    except OSError:

                        pass


                body = build_fallback_html(
                    payload
                ).encode(
                    "utf-8"
                )


                self._headers(
                    200,
                    "text/html; charset=utf-8",
                    len(
                        body
                    )
                )

                self.wfile.write(
                    body
                )

                return


            # =================================================
            # STATIC FILES
            # =================================================

            relative = request_path.lstrip(
                "/"
            )

            candidate = os.path.realpath(
                os.path.join(
                    UI_DIR,
                    relative
                )
            )

            real_ui_dir = os.path.realpath(
                UI_DIR
            )


            if not candidate.startswith(
                real_ui_dir
                +
                os.sep
            ):

                self._headers(
                    403,
                    "text/plain; charset=utf-8"
                )

                return


            if not os.path.isfile(
                candidate
            ):

                self._headers(
                    404,
                    "text/plain; charset=utf-8"
                )

                return


            try:

                with open(
                    candidate,
                    "rb"
                ) as handle:

                    body = handle.read()


                content_type = (
                    mimetypes.guess_type(
                        candidate
                    )[
                        0
                    ]
                    or
                    "application/octet-stream"
                )


                self._headers(
                    200,
                    content_type,
                    len(
                        body
                    )
                )

                self.wfile.write(
                    body
                )


            except OSError:

                self._headers(
                    500,
                    "text/plain; charset=utf-8"
                )


    return ReplayHandler


def start_local_server(
    payload
):

    handler = create_handler(
        payload
    )


    server = ReplayHTTPServer(
        (
            HOST,
            0,
        ),
        handler
    )


    port = server.server_address[
        1
    ]


    thread = threading.Thread(
        target=server.serve_forever,
        name="sentinel-replay-http",
        daemon=True
    )


    thread.start()


    return (
        server,
        thread,
        port
    )


# ============================================================
# FALLBACK CANVAS GLOBE
#
# Used only if the existing index.html is missing.
# ============================================================

def build_fallback_html(
    payload
):

    incidents = extract_incidents(
        payload
    )


    clean_incidents = []

    for incident in incidents:

        clean_incidents.append(
            {
                "latitude":
                    incident.get(
                        "latitude"
                    ),

                "longitude":
                    incident.get(
                        "longitude"
                    ),

                "ip":
                    incident.get(
                        "ip",
                        ""
                    ),

                "country":
                    incident.get(
                        "country",
                        ""
                    ),

                "region":
                    incident.get(
                        "region",
                        ""
                    ),

                "type":
                    incident.get(
                        "type",
                        "INCIDENT"
                    ),

                "timestamp":
                    incident.get(
                        "timestamp",
                        ""
                    ),

                "severity":
                    incident.get(
                        "severity",
                        ""
                    ),
            }
        )


    incidents_json = json.dumps(
        clean_incidents,
        ensure_ascii=False
    )


    return f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Sentinel Phoenix - Visual Incident Replay</title>

<style>
html, body {{
    margin: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background:
        radial-gradient(circle at center, #071525 0%, #02060d 65%, #000 100%);
    color: #dff9ff;
    font-family: Arial, Helvetica, sans-serif;
}}

#canvas {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
}}

#hud {{
    position: absolute;
    top: 28px;
    left: 32px;
    width: 420px;
    pointer-events: none;
}}

.title {{
    font-size: 25px;
    letter-spacing: 4px;
    font-weight: 700;
}}

.subtitle {{
    color: #67dbff;
    margin-top: 7px;
    font-size: 12px;
    letter-spacing: 2px;
}}

.panel {{
    margin-top: 25px;
    padding: 17px;
    border: 1px solid rgba(89,220,255,.55);
    background: rgba(3,12,22,.72);
    border-radius: 9px;
    box-shadow: 0 0 22px rgba(40,200,255,.14);
}}

.label {{
    color: #6edfff;
    font-size: 10px;
    letter-spacing: 2px;
    margin-top: 9px;
}}

.value {{
    margin-top: 3px;
    font-size: 14px;
}}

#status {{
    position: absolute;
    bottom: 26px;
    left: 32px;
    color: #70e4ff;
    font-size: 11px;
    letter-spacing: 2px;
}}

.scan {{
    animation: pulse 1.4s infinite;
}}

@keyframes pulse {{
    0% {{ opacity: .35; }}
    50% {{ opacity: 1; }}
    100% {{ opacity: .35; }}
}}
</style>
</head>

<body>

<canvas id="canvas"></canvas>

<div id="hud">
    <div class="title">SENTINEL PHOENIX</div>
    <div class="subtitle">
        VISUAL INCIDENT REPLAY // GEO INTELLIGENCE
    </div>

    <div class="panel">
        <div class="label">INCIDENT</div>
        <div class="value" id="type">ANALYZING...</div>

        <div class="label">APPROXIMATE ORIGIN</div>
        <div class="value" id="origin">UNKNOWN</div>

        <div class="label">SOURCE IP</div>
        <div class="value" id="ip">UNKNOWN</div>

        <div class="label">TIME</div>
        <div class="value" id="timestamp">UNKNOWN</div>
    </div>
</div>

<div id="status" class="scan">
    INCIDENT REPLAY ACTIVE // LOCAL ANALYSIS
</div>

<script>

const incidents = {incidents_json};

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

let W = 0;
let H = 0;

let rotation = 0;
let activeIndex = 0;
let lastChange = performance.now();


function resize() {{
    const ratio = window.devicePixelRatio || 1;

    W = window.innerWidth;
    H = window.innerHeight;

    canvas.width = W * ratio;
    canvas.height = H * ratio;

    canvas.style.width = W + "px";
    canvas.style.height = H + "px";

    ctx.setTransform(
        ratio,
        0,
        0,
        ratio,
        0,
        0
    );
}}

window.addEventListener(
    "resize",
    resize
);

resize();


function project(lat, lon, cx, cy, radius) {{

    const phi =
        lat * Math.PI / 180;

    const lambda =
        lon * Math.PI / 180
        +
        rotation;

    const x =
        Math.cos(phi)
        *
        Math.sin(lambda);

    const y =
        Math.sin(phi);

    const z =
        Math.cos(phi)
        *
        Math.cos(lambda);

    return {{
        x: cx + x * radius,
        y: cy - y * radius,
        z: z
    }};
}}


function drawStars() {{

    ctx.save();

    for (
        let i = 0;
        i < 100;
        i++
    ) {{

        const x =
            (i * 193) % W;

        const y =
            (i * 97) % H;

        const alpha =
            0.15
            +
            ((i % 7) / 12);

        ctx.fillStyle =
            `rgba(180,230,255,${{alpha}})`;

        ctx.fillRect(
            x,
            y,
            1.2,
            1.2
        );
    }}

    ctx.restore();
}}


function drawGlobe() {{

    const cx =
        W * 0.68;

    const cy =
        H * 0.51;

    const radius =
        Math.min(
            W,
            H
        ) * 0.32;


    const glow = ctx.createRadialGradient(
        cx,
        cy,
        radius * 0.1,
        cx,
        cy,
        radius
    );

    glow.addColorStop(
        0,
        "rgba(20,125,170,.30)"
    );

    glow.addColorStop(
        0.7,
        "rgba(5,50,80,.24)"
    );

    glow.addColorStop(
        1,
        "rgba(0,15,28,.05)"
    );


    ctx.beginPath();

    ctx.arc(
        cx,
        cy,
        radius,
        0,
        Math.PI * 2
    );

    ctx.fillStyle = glow;
    ctx.fill();


    ctx.strokeStyle =
        "rgba(70,220,255,.75)";

    ctx.lineWidth = 1.4;

    ctx.stroke();


    // latitude rings

    for (
        let lat = -60;
        lat <= 60;
        lat += 30
    ) {{

        const y =
            cy
            -
            Math.sin(
                lat * Math.PI / 180
            )
            *
            radius;

        const ringRadius =
            Math.cos(
                lat * Math.PI / 180
            )
            *
            radius;

        ctx.beginPath();

        ctx.ellipse(
            cx,
            y,
            ringRadius,
            ringRadius * 0.16,
            0,
            0,
            Math.PI * 2
        );

        ctx.strokeStyle =
            "rgba(60,185,225,.20)";

        ctx.lineWidth = 1;

        ctx.stroke();
    }}


    // longitude curves

    for (
        let lon = 0;
        lon < 180;
        lon += 30
    ) {{

        ctx.beginPath();

        for (
            let lat = -90;
            lat <= 90;
            lat += 3
        ) {{

            const p = project(
                lat,
                lon,
                cx,
                cy,
                radius
            );

            if (lat === -90) {{
                ctx.moveTo(
                    p.x,
                    p.y
                );
            }}
            else {{
                ctx.lineTo(
                    p.x,
                    p.y
                );
            }}
        }}

        ctx.strokeStyle =
            "rgba(60,185,225,.16)";

        ctx.stroke();
    }}


    incidents.forEach(
        (incident, index) => {{

            if (
                incident.latitude === null
                ||
                incident.longitude === null
            ) {{
                return;
            }}


            const p = project(
                incident.latitude,
                incident.longitude,
                cx,
                cy,
                radius
            );


            // hidden side of globe

            if (p.z < -0.08) {{
                return;
            }}


            const active =
                index === activeIndex;


            const size =
                active
                ? 7
                : 3.5;


            const alpha =
                .35
                +
                Math.max(
                    0,
                    p.z
                ) * .65;


            if (active) {{

                const pulse =
                    15
                    +
                    Math.sin(
                        performance.now() / 180
                    ) * 5;

                ctx.beginPath();

                ctx.arc(
                    p.x,
                    p.y,
                    pulse,
                    0,
                    Math.PI * 2
                );

                ctx.strokeStyle =
                    "rgba(255,90,90,.45)";

                ctx.lineWidth = 2;

                ctx.stroke();
            }}


            ctx.beginPath();

            ctx.arc(
                p.x,
                p.y,
                size,
                0,
                Math.PI * 2
            );

            ctx.fillStyle =
                active
                ? "rgba(255,95,95,.95)"
                : `rgba(80,220,255,${{alpha}})`;

            ctx.fill();


            if (active) {{

                ctx.beginPath();

                ctx.moveTo(
                    p.x,
                    p.y
                );

                ctx.lineTo(
                    cx,
                    cy
                );

                ctx.strokeStyle =
                    "rgba(255,90,90,.18)";

                ctx.lineWidth = 1;

                ctx.stroke();
            }}
        }}
    );
}}


function updateHUD() {{

    if (!incidents.length) {{

        document.getElementById(
            "type"
        ).textContent =
            "NO MATCHING GEOLOCATED INCIDENT";

        return;
    }}


    const incident =
        incidents[
            activeIndex
        ];


    document.getElementById(
        "type"
    ).textContent =
        incident.type
        ||
        "INCIDENT";


    const originParts = [];

    if (incident.region) {{
        originParts.push(
            incident.region
        );
    }}

    if (incident.country) {{
        originParts.push(
            incident.country
        );
    }}


    document.getElementById(
        "origin"
    ).textContent =
        originParts.join(
            ", "
        )
        ||
        "UNKNOWN";


    document.getElementById(
        "ip"
    ).textContent =
        incident.ip
        ||
        "UNKNOWN";


    document.getElementById(
        "timestamp"
    ).textContent =
        incident.timestamp
        ||
        "UNKNOWN";
}}


function animate(now) {{

    ctx.clearRect(
        0,
        0,
        W,
        H
    );

    drawStars();

    rotation += 0.0017;

    drawGlobe();


    if (
        incidents.length > 1
        &&
        now - lastChange > 4200
    ) {{

        activeIndex =
            (
                activeIndex + 1
            )
            %
            incidents.length;

        lastChange = now;

        updateHUD();
    }}


    requestAnimationFrame(
        animate
    );
}}


updateHUD();

requestAnimationFrame(
    animate
);

</script>

</body>
</html>
"""


# ============================================================
# PAYLOAD JAVASCRIPT INJECTION
#
# Keeps older versions of index.html compatible.
# ============================================================

def build_payload_injection(
    payload
):

    serialized = json.dumps(
        payload,
        ensure_ascii=False
    )


    return f"""
(function() {{

    const payload = {serialized};

    window.SENTINEL_REPLAY_PAYLOAD =
        payload;

    window.replayPayload =
        payload;

    window.incidentReplayPayload =
        payload;


    const functionNames = [
        "setReplayPayload",
        "loadReplay",
        "renderReplay",
        "startReplay",
        "updateReplay",
        "renderIncidentReplay"
    ];


    for (
        const name of functionNames
    ) {{

        try {{

            if (
                typeof window[name]
                ===
                "function"
            ) {{

                window[name](
                    payload
                );
            }}

        }}
        catch (error) {{

            console.warn(
                "Sentinel Replay bridge:",
                name,
                error
            );
        }}
    }}


    window.dispatchEvent(
        new CustomEvent(
            "sentinel-replay-payload",
            {{
                detail: payload
            }}
        )
    );


    return true;

}})();
"""


# ============================================================
# QT APPLICATION
# ============================================================

def run(
    payload=None,
    query=None
):

    if payload is None:

        payload = get_replay_payload(
            query or "latest"
        )


    if payload is None:

        payload = {
            "status":
                "EMPTY",

            "query":
                query or "latest",

            "incidents":
                [],
        }


    try:

        from PySide6.QtCore import (
            QTimer,
            QUrl
        )

        from PySide6.QtWidgets import (
            QApplication,
            QMainWindow
        )

        from PySide6.QtWebEngineWidgets import (
            QWebEngineView
        )


    except Exception as error:

        print(
            "[REPLAY QT] Qt WebEngine unavailable:",
            str(error),
            flush=True
        )

        return 2


    server = None

    server_thread = None


    try:

        (
            server,
            server_thread,
            port
        ) = start_local_server(
            payload
        )


        application = (
            QApplication.instance()
        )


        owns_application = (
            application is None
        )


        if application is None:

            application = QApplication(
                sys.argv
            )


        window = QMainWindow()

        window.setWindowTitle(
            "Sentinel Phoenix - Visual Incident Replay"
        )

        window.resize(
            DEFAULT_WIDTH,
            DEFAULT_HEIGHT
        )


        browser = QWebEngineView()

        window.setCentralWidget(
            browser
        )


        target_url = (
            f"http://{HOST}:{port}/"
        )


        injection = (
            build_payload_injection(
                payload
            )
        )


        def inject_payload(
            ok=True
        ):

            if not ok:

                print(
                    "[REPLAY QT] Page load warning.",
                    flush=True
                )


            def execute():

                try:

                    browser.page().runJavaScript(
                        injection
                    )

                except Exception:

                    pass


            # Multiple injections make this compatible
            # with pages whose own scripts initialize later.

            QTimer.singleShot(
                100,
                execute
            )

            QTimer.singleShot(
                600,
                execute
            )

            QTimer.singleShot(
                1500,
                execute
            )


        browser.loadFinished.connect(
            inject_payload
        )


        browser.setUrl(
            QUrl(
                target_url
            )
        )


        window.show()


        # ====================================================
        # LOCAL NARRATION
        # ====================================================

        narration = build_narration(
            query,
            payload
        )


        language = detect_language(
            query
        )


        def narrate():

            time.sleep(
                0.9
            )

            speak_local(
                narration,
                language
            )


        threading.Thread(
            target=narrate,
            name="sentinel-replay-narration",
            daemon=True
        ).start()


        print(
            "[REPLAY QT] Visual Incident Replay: ONLINE",
            flush=True
        )

        print(
            "[REPLAY QT] Version:",
            REPLAY_QT_VERSION,
            flush=True
        )

        print(
            "[REPLAY QT] Query:",
            query or "latest",
            flush=True
        )

        print(
            "[REPLAY QT] Incidents:",
            len(
                extract_incidents(
                    payload
                )
            ),
            flush=True
        )


        if owns_application:

            result = application.exec()

        else:

            result = 0


        return int(
            result
        )


    finally:

        if server is not None:

            try:

                server.shutdown()

            except Exception:

                pass


            try:

                server.server_close()

            except Exception:

                pass


# ============================================================
# QUERY ENTRY
# ============================================================

def run_query(
    query
):

    query = str(
        query or ""
    ).strip()


    if not query:

        query = "latest"


    payload = get_replay_payload(
        query
    )


    return run(
        payload=payload,
        query=query
    )


# ============================================================
# SELF TEST
#
# Does not open GUI.
# ============================================================

def self_test():

    query_available = False

    qt_available = False

    webengine_available = False


    try:

        from core.incident_replay_query import (
            replay_payload_for_query
        )

        query_available = callable(
            replay_payload_for_query
        )

    except Exception:

        query_available = False


    try:

        import PySide6

        qt_available = True

    except Exception:

        qt_available = False


    try:

        from PySide6.QtWebEngineWidgets import (
            QWebEngineView
        )

        webengine_available = True

    except Exception:

        webengine_available = False


    passed = all(
        (
            query_available,
            qt_available,
            webengine_available,
        )
    )


    return {
        "status":
            (
                "PASS"
                if passed
                else
                "FAIL"
            ),

        "version":
            REPLAY_QT_VERSION,

        "query_engine":
            query_available,

        "pyside6":
            qt_available,

        "qt_webengine":
            webengine_available,

        "existing_canvas_ui":
            os.path.isfile(
                INDEX_FILE
            ),

        "fallback_canvas":
            True,

        "renderer":
            "CANVAS_2D",

        "webgl_required":
            False,

        "local_http_bridge":
            True,

        "host":
            HOST,

        "api_aliases": [
            "/api/replay",
            "/api/payload",
            "/api/incidents",
            "/payload.json",
            "/replay.json",
        ],

        "entry_points": {
            "run":
                callable(
                    run
                ),

            "run_query":
                callable(
                    run_query
                ),
        },

        "security": {
            "localhost_only":
                True,

            "attacker_payload_execution":
                False,

            "shell_execution":
                False,

            "webgl_required":
                False,
        }
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Sentinel Phoenix "
            "Visual Incident Replay"
        )
    )


    parser.add_argument(
        "--query",
        default=None,
        help=(
            "Natural-language Replay query."
        )
    )


    parser.add_argument(
        "--self-test",
        action="store_true"
    )


    args = parser.parse_args()


    if args.self_test:

        import pprint

        pprint.pp(
            self_test()
        )

        raise SystemExit(
            0
        )


    raise SystemExit(
        run_query(
            args.query
            or
            "latest"
        )
    )