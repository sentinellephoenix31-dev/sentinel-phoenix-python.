# ============================================================
# SENTINEL PHOENIX
# INCIDENT INTELLIGENCE GLOBE V2.0
#
# VirtualBox-safe edition:
# - HTML5 Canvas
# - NO WebGL
# - software rendering friendly
# - animated pseudo-3D globe
# - incident timeline
# - geo target / marker
# - local/loopback protection
#
# Existing Incident Replay remains untouched.
# ============================================================

import argparse
import ipaddress
import json
import os
import sys
from typing import Any, Dict, List, Optional


# ============================================================
# SOFTWARE-FIRST RENDERING FOR VIRTUALBOX
# ============================================================

os.environ.setdefault(
    "QT_QUICK_BACKEND",
    "software",
)

os.environ.setdefault(
    "LIBGL_ALWAYS_SOFTWARE",
    "1",
)

os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-gpu --disable-gpu-compositing",
)


from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView


GLOBE_VERSION = "2.0"

MAX_EVENTS = 120


# ============================================================
# HELPERS
# ============================================================

def safe_text(
    value: Any,
    default: str = "",
) -> str:

    if value is None:
        return default

    text = str(value).strip()

    return text or default


def safe_float(
    value: Any,
) -> Optional[float]:

    try:
        return float(value)

    except Exception:
        return None


def first_value(
    *values,
):

    for value in values:

        if value is not None:

            if isinstance(
                value,
                str,
            ):

                if value.strip():
                    return value

            else:
                return value

    return None


def is_local_ip(
    value: Any,
) -> bool:

    try:

        ip = ipaddress.ip_address(
            safe_text(value)
        )

        return bool(
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_unspecified
        )

    except Exception:
        return False


# ============================================================
# LOAD EXISTING REPLAY
# ============================================================

def load_replay_payload(
    query: str,
) -> Any:

    # First choice:
    # preserve current working replay pipeline.
    try:

        from core import (
            incident_replay_qt
        )

        loader = getattr(
            incident_replay_qt,
            "get_replay_payload",
            None,
        )

        if callable(loader):

            return loader(
                query
            )

    except Exception as error:

        print(
            "[GLOBE V2] Existing replay "
            "loader warning:",
            repr(error),
            flush=True,
        )

    # Secondary path.
    from core.incident_replay_query import (
        replay_payload_for_query,
    )

    return replay_payload_for_query(
        query
    )


# ============================================================
# EVENT EXTRACTION
# ============================================================

def find_event_list(
    obj: Any,
) -> List[Dict[str, Any]]:

    if isinstance(
        obj,
        dict,
    ):

        for key in (
            "events",
            "incidents",
            "results",
            "items",
            "timeline",
        ):

            value = obj.get(
                key
            )

            if (
                isinstance(
                    value,
                    list,
                )
                and value
            ):

                dictionaries = [
                    item
                    for item in value
                    if isinstance(
                        item,
                        dict,
                    )
                ]

                if dictionaries:
                    return dictionaries

        for value in obj.values():

            result = find_event_list(
                value
            )

            if result:
                return result

    elif isinstance(
        obj,
        list,
    ):

        dictionaries = [
            item
            for item in obj
            if isinstance(
                item,
                dict,
            )
        ]

        if dictionaries:
            return dictionaries

    return []


# ============================================================
# GEO EXTRACTION
# ============================================================

def collect_geo_records(
    obj: Any,
    records: List[Dict[str, Any]],
):

    if isinstance(
        obj,
        dict,
    ):

        latitude = first_value(
            obj.get("latitude"),
            obj.get("lat"),
        )

        longitude = first_value(
            obj.get("longitude"),
            obj.get("lon"),
            obj.get("lng"),
        )

        if (
            safe_float(latitude)
            is not None
            and
            safe_float(longitude)
            is not None
        ):

            records.append(
                obj
            )

        for value in obj.values():

            collect_geo_records(
                value,
                records,
            )

    elif isinstance(
        obj,
        list,
    ):

        for value in obj:

            collect_geo_records(
                value,
                records,
            )


def build_geo_index(
    payload: Any,
) -> Dict[str, Dict[str, Any]]:

    records: List[
        Dict[str, Any]
    ] = []

    collect_geo_records(
        payload,
        records,
    )

    index: Dict[
        str,
        Dict[str, Any]
    ] = {}

    for record in records:

        ip = safe_text(
            first_value(
                record.get(
                    "source_ip"
                ),
                record.get("ip"),
                record.get(
                    "address"
                ),
            )
        )

        if ip:
            index[ip] = record

    return index


# ============================================================
# NORMALIZE EVENT
# ============================================================

def normalize_event(
    event: Dict[str, Any],
    geo_index: Dict[
        str,
        Dict[str, Any]
    ],
    number: int,
) -> Dict[str, Any]:

    source_ip = safe_text(
        first_value(
            event.get(
                "source_ip"
            ),
            event.get("ip"),
            event.get(
                "remote_ip"
            ),
            event.get(
                "client_ip"
            ),
        ),
        "UNKNOWN",
    )

    nested_geo = first_value(
        event.get("geo"),
        event.get(
            "geolocation"
        ),
        event.get(
            "geo_result"
        ),
        event.get(
            "globe"
        ),
    )

    if not isinstance(
        nested_geo,
        dict,
    ):
        nested_geo = {}

    indexed_geo = geo_index.get(
        source_ip,
        {},
    )

    latitude = safe_float(
        first_value(
            event.get("latitude"),
            event.get("lat"),
            nested_geo.get(
                "latitude"
            ),
            nested_geo.get("lat"),
            indexed_geo.get(
                "latitude"
            ),
            indexed_geo.get("lat"),
        )
    )

    longitude = safe_float(
        first_value(
            event.get(
                "longitude"
            ),
            event.get("lon"),
            event.get("lng"),
            nested_geo.get(
                "longitude"
            ),
            nested_geo.get("lon"),
            nested_geo.get("lng"),
            indexed_geo.get(
                "longitude"
            ),
            indexed_geo.get("lon"),
            indexed_geo.get("lng"),
        )
    )

    local = is_local_ip(
        source_ip
    )

    country = safe_text(
        first_value(
            event.get("country"),
            nested_geo.get(
                "country"
            ),
            indexed_geo.get(
                "country"
            ),
        ),
        (
            "LOCAL / LOOPBACK"
            if local
            else
            "UNKNOWN"
        ),
    )

    region = safe_text(
        first_value(
            event.get("region"),
            nested_geo.get(
                "region"
            ),
            indexed_geo.get(
                "region"
            ),
        ),
        "—",
    )

    city = safe_text(
        first_value(
            event.get("city"),
            nested_geo.get(
                "city"
            ),
            indexed_geo.get(
                "city"
            ),
        ),
        "—",
    )

    level = safe_text(
        first_value(
            event.get("level"),
            event.get(
                "risk_level"
            ),
            event.get(
                "severity"
            ),
            event.get(
                "global_level"
            ),
            event.get(
                "behavior_level"
            ),
        ),
        "UNKNOWN",
    ).upper()

    event_type = safe_text(
        first_value(
            event.get("type"),
            event.get(
                "event_type"
            ),
            event.get(
                "category"
            ),
        ),
        "SECURITY_EVENT",
    )

    behavior = safe_text(
        first_value(
            event.get(
                "behavior_type"
            ),
            event.get(
                "behavior"
            ),
            event.get(
                "intent"
            ),
        ),
        "—",
    )

    anomaly = safe_text(
        first_value(
            event.get(
                "anomaly_level"
            ),
            event.get(
                "anomaly"
            ),
        ),
        "—",
    )

    action = safe_text(
        first_value(
            event.get(
                "response_action"
            ),
            event.get(
                "policy_action"
            ),
            event.get(
                "context_recommended_action"
            ),
            event.get(
                "action"
            ),
        ),
        "MONITOR",
    )

    timestamp = safe_text(
        first_value(
            event.get(
                "timestamp"
            ),
            event.get("time"),
            event.get(
                "created_at"
            ),
        ),
        "UNKNOWN",
    )

    score = first_value(
        event.get("score"),
        event.get(
            "risk_score"
        ),
        event.get(
            "global_score"
        ),
        event.get(
            "behavior_score"
        ),
    )

    if score is None:
        score = "—"

    containment = bool(
        first_value(
            event.get(
                "containment_requested"
            ),
            event.get(
                "containment"
            ),
            False,
        )
    )

    has_geo = bool(
        latitude is not None
        and
        longitude is not None
        and
        not local
    )

    if local:

        latitude = None
        longitude = None
        region = "LOCAL SYSTEM"
        city = "LOCALHOST"

    return {
        "index": number,
        "timestamp": timestamp,
        "source_ip": source_ip,
        "type": event_type,
        "level": level,
        "score": score,
        "behavior": behavior,
        "anomaly": anomaly,
        "action": action,
        "containment": containment,
        "country": country,
        "region": region,
        "city": city,
        "latitude": latitude,
        "longitude": longitude,
        "has_geo": has_geo,
        "local": local,
    }


def normalize_payload(
    raw_payload: Any,
    query: str,
) -> Dict[str, Any]:

    events = find_event_list(
        raw_payload
    )

    geo_index = build_geo_index(
        raw_payload
    )

    normalized = []

    for number, event in enumerate(
        events[:MAX_EVENTS],
        start=1,
    ):

        normalized.append(
            normalize_event(
                event,
                geo_index,
                number,
            )
        )

    return {
        "version":
            GLOBE_VERSION,

        "query":
            query,

        "event_count":
            len(normalized),

        "events":
            normalized,
    }


# ============================================================
# HTML / CANVAS UI
# ============================================================

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">

<title>Sentinel Phoenix // Incident Intelligence</title>

<style>

html, body {
    width: 100%;
    height: 100%;
    margin: 0;
    overflow: hidden;
    background:
        radial-gradient(
            circle at 32% 40%,
            #071a24 0%,
            #02080d 48%,
            #000306 100%
        );
    color: #d8fff5;
    font-family:
        Inter,
        Segoe UI,
        Arial,
        sans-serif;
}

#canvas {
    position: absolute;
    left: 0;
    top: 0;
}

#header {
    position: absolute;
    left: 32px;
    top: 24px;
    z-index: 5;
}

#title {
    font-size: 22px;
    letter-spacing: 3px;
    font-weight: 700;
    color: #afffeb;
}

#subtitle {
    margin-top: 7px;
    font-size: 11px;
    letter-spacing: 2px;
    color: #58aa9c;
}

#panel {
    position: absolute;
    right: 26px;
    top: 28px;
    bottom: 88px;
    width: 350px;
    padding: 22px;

    background:
        linear-gradient(
            145deg,
            rgba(7,24,30,.94),
            rgba(4,12,18,.91)
        );

    border:
        1px solid rgba(
            73,255,205,.28
        );

    border-radius: 18px;

    box-shadow:
        0 0 45px rgba(
            0,255,190,.08
        );

    backdrop-filter:
        blur(8px);

    z-index: 6;
}

.panel-title {
    font-size: 12px;
    letter-spacing: 3px;
    color: #5ceecb;
    margin-bottom: 20px;
}

.row {
    margin-bottom: 13px;
}

.label {
    display: block;
    color: #588d86;
    font-size: 9px;
    letter-spacing: 2px;
    margin-bottom: 4px;
}

.value {
    display: block;
    color: #d7fff6;
    font-size: 14px;
    word-break: break-word;
}

#risk {
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 2px;
}

#location {
    color: #7fffdc;
}

#geoNotice {
    margin-top: 16px;
    padding: 11px;
    border-radius: 9px;
    background:
        rgba(255,190,70,.07);
    border:
        1px solid
        rgba(255,190,70,.18);

    color: #eecf88;
    font-size: 10px;
    letter-spacing: 1px;
    line-height: 1.5;
}

#controls {
    position: absolute;
    left: 34px;
    right: 404px;
    bottom: 27px;
    height: 43px;

    display: flex;
    align-items: center;
    gap: 12px;

    z-index: 7;
}

button {
    border:
        1px solid
        rgba(79,255,212,.32);

    background:
        rgba(6,27,31,.85);

    color:
        #bffff0;

    border-radius:
        10px;

    padding:
        8px 15px;

    cursor:
        pointer;

    letter-spacing:
        1px;
}

button:hover {
    background:
        rgba(20,70,66,.9);
}

#counter {
    margin-left: 10px;
    font-size: 11px;
    letter-spacing: 2px;
    color: #64b8a8;
}

#timeline {
    flex: 1;
    height: 3px;
    background:
        rgba(80,170,155,.18);

    border-radius:
        3px;

    overflow: hidden;
}

#timelineFill {
    height: 100%;
    width: 0%;
    background:
        linear-gradient(
            90deg,
            #35bfa4,
            #7fffd8
        );

    box-shadow:
        0 0 12px #64ffd5;
}

#empty {
    position: absolute;
    left: 28%;
    top: 48%;

    transform:
        translate(-50%,-50%);

    color: #6faaa0;
    font-size: 15px;
    letter-spacing: 3px;

    display: none;
}

</style>
</head>

<body>

<canvas id="canvas"></canvas>

<div id="header">
    <div id="title">
        SENTINEL // INCIDENT INTELLIGENCE
    </div>

    <div id="subtitle">
        INCIDENT REPLAY • GEO ANALYSIS • DEFENSIVE TELEMETRY
    </div>
</div>

<div id="panel">

    <div class="panel-title">
        INCIDENT INTELLIGENCE
    </div>

    <div class="row">
        <span class="label">RISK LEVEL</span>
        <span class="value" id="risk">—</span>
    </div>

    <div class="row">
        <span class="label">EVENT</span>
        <span class="value" id="eventType">—</span>
    </div>

    <div class="row">
        <span class="label">SOURCE IP</span>
        <span class="value" id="sourceIp">—</span>
    </div>

    <div class="row">
        <span class="label">LOCATION</span>
        <span class="value" id="location">—</span>
    </div>

    <div class="row">
        <span class="label">TIMESTAMP</span>
        <span class="value" id="timestamp">—</span>
    </div>

    <div class="row">
        <span class="label">SCORE</span>
        <span class="value" id="score">—</span>
    </div>

    <div class="row">
        <span class="label">BEHAVIOR</span>
        <span class="value" id="behavior">—</span>
    </div>

    <div class="row">
        <span class="label">ANOMALY</span>
        <span class="value" id="anomaly">—</span>
    </div>

    <div class="row">
        <span class="label">DEFENSIVE ACTION</span>
        <span class="value" id="action">—</span>
    </div>

    <div id="geoNotice"></div>
</div>

<div id="controls">

    <button onclick="previousEvent()">
        ◀ PREV
    </button>

    <button id="playButton" onclick="togglePlay()">
        ❚❚ PAUSE
    </button>

    <button onclick="nextEvent()">
        NEXT ▶
    </button>

    <span id="counter">
        0 / 0
    </span>

    <div id="timeline">
        <div id="timelineFill"></div>
    </div>
</div>

<div id="empty">
    NO SECURITY EVENTS AVAILABLE
</div>


<script>

const DATA = __DATA__;

const events = Array.isArray(DATA.events)
    ? DATA.events
    : [];

const canvas = document.getElementById(
    "canvas"
);

const ctx = canvas.getContext(
    "2d"
);

let width = 0;
let height = 0;

let currentIndex = 0;

let playing = true;

let rotation = 0;
let rotationTarget = 0;

let viewLatitude = 0;
let viewLatitudeTarget = 0;

let zoom = 1;
let zoomTarget = 1;

let pulse = 0;

let lastAutoChange = performance.now();

const autoDelay = 6500;


// ============================================================
// STARS
// ============================================================

const stars = [];

for (let i = 0; i < 170; i++) {

    stars.push({
        x: Math.random(),
        y: Math.random(),
        size:
            0.4
            + Math.random() * 1.4,
        alpha:
            0.15
            + Math.random() * 0.45
    });
}


// ============================================================
// SIMPLIFIED CONTINENT SHAPES
// lon, lat
// ============================================================

const lands = [

    // North America
    [
        [-168,66],[-150,70],[-130,56],
        [-122,48],[-105,50],[-95,42],
        [-82,27],[-96,18],[-108,23],
        [-118,32],[-135,52]
    ],

    // South America
    [
        [-81,12],[-67,8],[-52,-3],
        [-47,-18],[-56,-34],[-68,-55],
        [-75,-38],[-73,-18]
    ],

    // Europe
    [
        [-11,36],[3,44],[15,47],
        [31,45],[39,55],[26,70],
        [7,71],[-8,58]
    ],

    // Africa
    [
        [-17,35],[10,37],[32,30],
        [44,10],[38,-18],[20,-35],
        [5,-32],[-8,-10],[-16,14]
    ],

    // Asia
    [
        [30,40],[53,55],[84,72],
        [125,64],[154,50],[139,32],
        [110,20],[88,8],[67,24],
        [43,29]
    ],

    // Australia
    [
        [112,-12],[134,-10],[153,-27],
        [142,-39],[116,-35]
    ]
];


const continentLabels = [

    ["NORTH AMERICA",-105,43],
    ["SOUTH AMERICA",-60,-20],
    ["EUROPE",14,54],
    ["AFRICA",20,3],
    ["ASIA",91,43],
    ["AUSTRALIA",135,-25]
];


// ============================================================
// RESIZE
// ============================================================

function resize() {

    width =
        window.innerWidth;

    height =
        window.innerHeight;

    canvas.width =
        width * devicePixelRatio;

    canvas.height =
        height * devicePixelRatio;

    canvas.style.width =
        width + "px";

    canvas.style.height =
        height + "px";

    ctx.setTransform(
        devicePixelRatio,
        0,
        0,
        devicePixelRatio,
        0,
        0
    );
}

window.addEventListener(
    "resize",
    resize
);

resize();


// ============================================================
// GLOBE GEOMETRY
// ============================================================

function globeGeometry() {

    const usableWidth =
        width - 400;

    const radius =
        Math.max(
            130,
            Math.min(
                usableWidth * 0.31,
                height * 0.36
            )
        ) * zoom;

    return {
        cx:
            Math.max(
                210,
                usableWidth * 0.44
            ),

        cy:
            height * 0.51,

        radius
    };
}


function radians(value) {

    return (
        value
        * Math.PI
        / 180
    );
}


function project(
    lat,
    lon
) {

    const globe =
        globeGeometry();

    const phi =
        radians(lat);

    const theta =
        radians(
            lon + rotation
        );

    let x =
        Math.cos(phi)
        * Math.sin(theta);

    let y =
        -Math.sin(phi);

    let z =
        Math.cos(phi)
        * Math.cos(theta);

    // Camera latitude adjustment.
    const camera =
        radians(
            viewLatitude
        );

    const y2 =
        y * Math.cos(camera)
        - z * Math.sin(camera);

    const z2 =
        y * Math.sin(camera)
        + z * Math.cos(camera);

    y = y2;
    z = z2;

    return {
        x:
            globe.cx
            + x * globe.radius,

        y:
            globe.cy
            + y * globe.radius,

        z,

        visible:
            z > 0
    };
}


// ============================================================
// BACKGROUND
// ============================================================

function drawStars() {

    for (
        const star
        of stars
    ) {

        ctx.beginPath();

        ctx.fillStyle =
            `rgba(
                130,
                220,
                205,
                ${star.alpha}
            )`;

        ctx.arc(
            star.x * width,
            star.y * height,
            star.size,
            0,
            Math.PI * 2
        );

        ctx.fill();
    }
}


// ============================================================
// GLOBE
// ============================================================

function drawSphere() {

    const g =
        globeGeometry();

    // Outer glow.
    const glow =
        ctx.createRadialGradient(
            g.cx,
            g.cy,
            g.radius * 0.65,
            g.cx,
            g.cy,
            g.radius * 1.25
        );

    glow.addColorStop(
        0,
        "rgba(0,255,205,0.06)"
    );

    glow.addColorStop(
        0.75,
        "rgba(0,180,160,0.03)"
    );

    glow.addColorStop(
        1,
        "rgba(0,150,140,0)"
    );

    ctx.fillStyle =
        glow;

    ctx.beginPath();

    ctx.arc(
        g.cx,
        g.cy,
        g.radius * 1.28,
        0,
        Math.PI * 2
    );

    ctx.fill();

    // Main sphere.
    const sphere =
        ctx.createRadialGradient(
            g.cx - g.radius * .30,
            g.cy - g.radius * .35,
            g.radius * .12,
            g.cx,
            g.cy,
            g.radius
        );

    sphere.addColorStop(
        0,
        "#163b43"
    );

    sphere.addColorStop(
        .38,
        "#0a252d"
    );

    sphere.addColorStop(
        .78,
        "#04131a"
    );

    sphere.addColorStop(
        1,
        "#010509"
    );

    ctx.fillStyle =
        sphere;

    ctx.beginPath();

    ctx.arc(
        g.cx,
        g.cy,
        g.radius,
        0,
        Math.PI * 2
    );

    ctx.fill();

    // Rim.
    ctx.strokeStyle =
        "rgba(75,255,215,.42)";

    ctx.lineWidth =
        1.4;

    ctx.stroke();

    // Atmosphere.
    ctx.strokeStyle =
        "rgba(70,255,220,.12)";

    ctx.lineWidth =
        9;

    ctx.beginPath();

    ctx.arc(
        g.cx,
        g.cy,
        g.radius + 5,
        0,
        Math.PI * 2
    );

    ctx.stroke();
}


// ============================================================
// GRID
// ============================================================

function drawGeoLine(
    points,
    color,
    widthValue
) {

    let started = false;

    ctx.beginPath();

    for (
        const point
        of points
    ) {

        const p =
            project(
                point[0],
                point[1]
            );

        if (
            p.z <= 0.01
        ) {

            started = false;
            continue;
        }

        if (!started) {

            ctx.moveTo(
                p.x,
                p.y
            );

            started = true;

        } else {

            ctx.lineTo(
                p.x,
                p.y
            );
        }
    }

    ctx.strokeStyle =
        color;

    ctx.lineWidth =
        widthValue;

    ctx.stroke();
}


function drawGrid() {

    // Latitude lines.
    for (
        let lat = -60;
        lat <= 60;
        lat += 30
    ) {

        const points = [];

        for (
            let lon = -180;
            lon <= 180;
            lon += 4
        ) {

            points.push(
                [lat, lon]
            );
        }

        drawGeoLine(
            points,
            "rgba(60,180,170,.13)",
            0.8
        );
    }

    // Longitude lines.
    for (
        let lon = -180;
        lon < 180;
        lon += 30
    ) {

        const points = [];

        for (
            let lat = -85;
            lat <= 85;
            lat += 3
        ) {

            points.push(
                [lat, lon]
            );
        }

        drawGeoLine(
            points,
            "rgba(60,180,170,.11)",
            0.8
        );
    }
}


// ============================================================
// LAND
// ============================================================

function drawLands() {

    for (
        const polygon
        of lands
    ) {

        const visiblePoints = [];

        for (
            const coord
            of polygon
        ) {

            const p =
                project(
                    coord[1],
                    coord[0]
                );

            if (
                p.z > 0.02
            ) {
                visiblePoints.push(
                    p
                );
            }
        }

        if (
            visiblePoints.length < 3
        ) {
            continue;
        }

        ctx.beginPath();

        ctx.moveTo(
            visiblePoints[0].x,
            visiblePoints[0].y
        );

        for (
            let i = 1;
            i < visiblePoints.length;
            i++
        ) {

            ctx.lineTo(
                visiblePoints[i].x,
                visiblePoints[i].y
            );
        }

        ctx.closePath();

        ctx.fillStyle =
            "rgba(24,128,108,.34)";

        ctx.fill();

        ctx.strokeStyle =
            "rgba(98,255,215,.26)";

        ctx.lineWidth =
            1;

        ctx.stroke();
    }
}


// ============================================================
// CONTINENT LABELS
// ============================================================

function drawLabels() {

    ctx.font =
        "10px sans-serif";

    ctx.textAlign =
        "center";

    for (
        const item
        of continentLabels
    ) {

        const p =
            project(
                item[2],
                item[1]
            );

        if (
            p.z < .25
        ) {
            continue;
        }

        ctx.fillStyle =
            `rgba(
                130,
                230,
                210,
                ${0.15 + p.z * .35}
            )`;

        ctx.fillText(
            item[0],
            p.x,
            p.y
        );
    }
}


// ============================================================
// CURRENT INCIDENT
// ============================================================

function getCurrentEvent() {

    if (
        events.length === 0
    ) {
        return null;
    }

    return events[
        currentIndex
    ];
}


function updatePanel() {

    const event =
        getCurrentEvent();

    if (!event) {

        document.getElementById(
            "empty"
        ).style.display =
            "block";

        return;
    }

    document.getElementById(
        "empty"
    ).style.display =
        "none";

    document.getElementById(
        "risk"
    ).textContent =
        event.level || "UNKNOWN";

    document.getElementById(
        "eventType"
    ).textContent =
        event.type || "—";

    document.getElementById(
        "sourceIp"
    ).textContent =
        event.source_ip || "—";

    document.getElementById(
        "timestamp"
    ).textContent =
        event.timestamp || "—";

    document.getElementById(
        "score"
    ).textContent =
        String(
            event.score ?? "—"
        );

    document.getElementById(
        "behavior"
    ).textContent =
        event.behavior || "—";

    document.getElementById(
        "anomaly"
    ).textContent =
        event.anomaly || "—";

    document.getElementById(
        "action"
    ).textContent =
        event.action || "—";

    const location =
        event.local
        ? "LOCAL / LOOPBACK"
        : [
            event.city,
            event.region,
            event.country
          ]
          .filter(
              x =>
                  x
                  && x !== "—"
                  && x !== "UNKNOWN"
          )
          .join(", ")
          || "GEOLOCATION UNKNOWN";

    document.getElementById(
        "location"
    ).textContent =
        location;

    const notice =
        document.getElementById(
            "geoNotice"
        );

    if (event.local) {

        notice.textContent =
            "LOCAL / LOOPBACK • NO PUBLIC GEOLOCATION";

    } else if (
        !event.has_geo
    ) {

        notice.textContent =
            "PUBLIC SOURCE • PRECISE GEO COORDINATES UNAVAILABLE";

    } else {

        notice.textContent =
            "APPROXIMATE IP GEOLOCATION • NOT PERSON IDENTIFICATION";
    }

    document.getElementById(
        "counter"
    ).textContent =
        `${currentIndex + 1} / ${events.length}`;

    document.getElementById(
        "timelineFill"
    ).style.width =
        (
            (
                currentIndex + 1
            )
            / events.length
            * 100
        ) + "%";
}


function selectEvent(
    index
) {

    if (
        events.length === 0
    ) {
        return;
    }

    currentIndex =
        (
            index
            + events.length
        )
        % events.length;

    const event =
        events[
            currentIndex
        ];

    if (
        event.has_geo
    ) {

        rotationTarget =
            -Number(
                event.longitude
            );

        viewLatitudeTarget =
            Math.max(
                -45,
                Math.min(
                    45,
                    Number(
                        event.latitude
                    ) * .58
                )
            );

        zoomTarget =
            1.12;

    } else {

        zoomTarget =
            1.0;

        viewLatitudeTarget =
            0;
    }

    lastAutoChange =
        performance.now();

    updatePanel();
}


function nextEvent() {

    selectEvent(
        currentIndex + 1
    );
}


function previousEvent() {

    selectEvent(
        currentIndex - 1
    );
}


function togglePlay() {

    playing =
        !playing;

    document.getElementById(
        "playButton"
    ).textContent =
        playing
        ? "❚❚ PAUSE"
        : "▶ PLAY";

    lastAutoChange =
        performance.now();
}


// ============================================================
// MARKER
// ============================================================

function drawMarker() {

    const event =
        getCurrentEvent();

    if (!event) {
        return;
    }

    const g =
        globeGeometry();

    // Local/loopback marker:
    // do NOT fabricate geography.
    if (
        event.local
        || !event.has_geo
    ) {

        const radius =
            9
            + Math.sin(
                pulse
            ) * 3;

        ctx.beginPath();

        ctx.arc(
            g.cx,
            g.cy,
            radius,
            0,
            Math.PI * 2
        );

        ctx.strokeStyle =
            event.local
            ? "rgba(255,200,95,.8)"
            : "rgba(130,190,180,.65)";

        ctx.lineWidth =
            2;

        ctx.stroke();

        return;
    }

    const p =
        project(
            Number(
                event.latitude
            ),
            Number(
                event.longitude
            )
        );

    if (
        p.z <= .03
    ) {
        return;
    }

    const pulseSize =
        12
        + Math.sin(
            pulse
        ) * 4;

    // Glow.
    ctx.beginPath();

    ctx.arc(
        p.x,
        p.y,
        pulseSize * 2.1,
        0,
        Math.PI * 2
    );

    ctx.fillStyle =
        "rgba(70,255,205,.07)";

    ctx.fill();

    // Pulse ring.
    ctx.beginPath();

    ctx.arc(
        p.x,
        p.y,
        pulseSize,
        0,
        Math.PI * 2
    );

    ctx.strokeStyle =
        "rgba(90,255,215,.85)";

    ctx.lineWidth =
        2;

    ctx.stroke();

    // Center.
    ctx.beginPath();

    ctx.arc(
        p.x,
        p.y,
        4,
        0,
        Math.PI * 2
    );

    ctx.fillStyle =
        "#8affdc";

    ctx.fill();

    // Detection stem.
    const topY =
        Math.max(
            100,
            p.y - 88
        );

    ctx.beginPath();

    ctx.moveTo(
        p.x,
        p.y - 5
    );

    ctx.lineTo(
        p.x,
        topY
    );

    ctx.strokeStyle =
        "rgba(100,255,220,.65)";

    ctx.lineWidth =
        1.2;

    ctx.stroke();

    // Label.
    const country =
        event.country
        || "UNKNOWN";

    const label =
        `${country} • ${event.level}`;

    ctx.font =
        "11px sans-serif";

    ctx.textAlign =
        "center";

    const textWidth =
        ctx.measureText(
            label
        ).width;

    ctx.fillStyle =
        "rgba(4,17,20,.88)";

    ctx.fillRect(
        p.x
            - textWidth / 2
            - 10,

        topY - 25,

        textWidth + 20,

        21
    );

    ctx.strokeStyle =
        "rgba(90,255,215,.32)";

    ctx.strokeRect(
        p.x
            - textWidth / 2
            - 10,

        topY - 25,

        textWidth + 20,

        21
    );

    ctx.fillStyle =
        "#baffed";

    ctx.fillText(
        label,
        p.x,
        topY - 11
    );
}


// ============================================================
// ANIMATION
// ============================================================

function angleDelta(
    target,
    current
) {

    let delta =
        (
            target
            - current
            + 540
        ) % 360
        - 180;

    return delta;
}


function animate(
    now
) {

    pulse += .055;

    const event =
        getCurrentEvent();

    if (
        event
        && event.has_geo
    ) {

        rotation +=
            angleDelta(
                rotationTarget,
                rotation
            )
            * .035;

    } else {

        // Normal idle rotation.
        rotation += .045;
    }

    viewLatitude +=
        (
            viewLatitudeTarget
            - viewLatitude
        )
        * .035;

    zoom +=
        (
            zoomTarget
            - zoom
        )
        * .035;

    if (
        playing
        && events.length > 1
        && now - lastAutoChange
            > autoDelay
    ) {

        nextEvent();
    }

    ctx.clearRect(
        0,
        0,
        width,
        height
    );

    drawStars();
    drawSphere();
    drawGrid();
    drawLands();
    drawLabels();
    drawMarker();

    requestAnimationFrame(
        animate
    );
}


// ============================================================
// KEYBOARD
// ============================================================

document.addEventListener(
    "keydown",
    event => {

        if (
            event.key ===
            "ArrowRight"
        ) {
            nextEvent();
        }

        if (
            event.key ===
            "ArrowLeft"
        ) {
            previousEvent();
        }

        if (
            event.key === " "
        ) {
            togglePlay();
        }
    }
);


// ============================================================
// START
// ============================================================

if (
    events.length > 0
) {

    selectEvent(0);

} else {

    updatePanel();
}

requestAnimationFrame(
    animate
);

</script>

</body>
</html>
"""


# ============================================================
# BUILD HTML
# ============================================================

def build_html(
    payload: Dict[str, Any],
) -> str:

    data = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )

    # Avoid accidental script termination from log text.
    data = data.replace(
        "</",
        "<\\/",
    )

    return HTML_TEMPLATE.replace(
        "__DATA__",
        data,
    )


# ============================================================
# RUN UI
# ============================================================

def run_globe(
    query: str = "latest",
) -> int:

    print(
        "=" * 66,
        flush=True,
    )

    print(
        f"SENTINEL PHOENIX "
        f"INCIDENT GLOBE V{GLOBE_VERSION}",
        flush=True,
    )

    print(
        "=" * 66,
        flush=True,
    )

    print(
        f"[GLOBE] Query: {query}",
        flush=True,
    )

    raw_payload = load_replay_payload(
        query
    )

    payload = normalize_payload(
        raw_payload,
        query,
    )

    print(
        "[GLOBE] Events loaded:",
        payload[
            "event_count"
        ],
        flush=True,
    )

    geo_count = sum(
        1
        for event
        in payload[
            "events"
        ]
        if event.get(
            "has_geo"
        )
    )

    local_count = sum(
        1
        for event
        in payload[
            "events"
        ]
        if event.get(
            "local"
        )
    )

    print(
        "[GLOBE] Geo incidents:",
        geo_count,
        flush=True,
    )

    print(
        "[GLOBE] Local/loopback:",
        local_count,
        flush=True,
    )

    app = QApplication(
        sys.argv
    )

    browser = QWebEngineView()

    browser.setWindowTitle(
        (
            "Sentinel Phoenix // "
            "Incident Intelligence"
        )
    )

    browser.resize(
        1400,
        850,
    )

    browser.setHtml(
        build_html(
            payload
        ),
        QUrl(
            "about:blank"
        ),
    )

    browser.show()

    return app.exec()


# ============================================================
# SELF TEST
# ============================================================

def self_test(
    query: str = "latest",
) -> int:

    raw_payload = load_replay_payload(
        query
    )

    payload = normalize_payload(
        raw_payload,
        query,
    )

    print(
        json.dumps(
            {
                "status": "PASS",
                "version":
                    GLOBE_VERSION,

                "query":
                    query,

                "events":
                    payload[
                        "event_count"
                    ],

                "geo_events":
                    sum(
                        1
                        for event
                        in payload[
                            "events"
                        ]
                        if event.get(
                            "has_geo"
                        )
                    ),

                "local_events":
                    sum(
                        1
                        for event
                        in payload[
                            "events"
                        ]
                        if event.get(
                            "local"
                        )
                    ),

                "rendering":
                    "HTML5_CANVAS",

                "webgl":
                    False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    return 0


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--query",
        default="latest",
    )

    parser.add_argument(
        "--self-test",
        action="store_true",
    )

    args = parser.parse_args()

    if args.self_test:

        return self_test(
            args.query
        )

    return run_globe(
        args.query
    )


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
