import json
import os

from flask import Flask, jsonify, render_template_string

from core.config import (
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    MAX_LOGS
)


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

EVENT_FILE = os.path.join(
    DATA_DIR,
    "events.jsonl"
)


app = Flask(__name__)


# ============================================================
# EVENTS
# ============================================================

def load_events():

    events = []

    if not os.path.exists(EVENT_FILE):
        return events

    try:

        with open(
            EVENT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            for line in file:

                line = line.strip()

                if not line:
                    continue

                try:

                    event = json.loads(line)
                    events.append(event)

                except json.JSONDecodeError:
                    continue

    except OSError:

        return []

    events.reverse()

    return events[:MAX_LOGS]


# ============================================================
# STATISTICS
# ============================================================

def calculate_stats(events):

    stats = {
        "total": len(events),

        "payload_critical": 0,

        "behavior_critical": 0,

        "anomaly_medium": 0,
        "anomaly_high": 0,
        "anomaly_critical": 0,

        "repeated_critical": 0,

        "high_frequency": 0,

        "high_entropy": 0
    }

    for event in events:

        severity = str(
            event.get(
                "severity",
                ""
            )
        ).upper()

        behavior_level = str(
            event.get(
                "behavior_level",
                ""
            )
        ).upper()

        anomaly_level = str(
            event.get(
                "anomaly_level",
                ""
            )
        ).upper()

        behavior_type = str(
            event.get(
                "behavior_type",
                ""
            )
        ).upper()

        anomaly_reasons = event.get(
            "anomaly_reasons",
            []
        )

        if severity == "CRITICAL":

            stats[
                "payload_critical"
            ] += 1

        if behavior_level == "CRITICAL":

            stats[
                "behavior_critical"
            ] += 1

        if anomaly_level == "MEDIUM":

            stats[
                "anomaly_medium"
            ] += 1

        elif anomaly_level == "HIGH":

            stats[
                "anomaly_high"
            ] += 1

        elif anomaly_level == "CRITICAL":

            stats[
                "anomaly_critical"
            ] += 1

        if (
            behavior_type
            ==
            "REPEATED_CRITICAL_ACTIVITY"
        ):

            stats[
                "repeated_critical"
            ] += 1

        if (
            "HIGH_CONNECTION_FREQUENCY"
            in anomaly_reasons
        ):

            stats[
                "high_frequency"
            ] += 1

        if (
            "HIGH_ENTROPY"
            in anomaly_reasons
        ):

            stats[
                "high_entropy"
            ] += 1

    return stats


# ============================================================
# API
# ============================================================

@app.route(
    "/api/events"
)
def api_events():

    events = load_events()

    return jsonify({
        "events": events
    })


@app.route(
    "/api/stats"
)
def api_stats():

    events = load_events()

    return jsonify({
        "status": "ACTIVE",
        "stats": calculate_stats(
            events
        )
    })


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def dashboard():

    return render_template_string(
r"""
<!DOCTYPE html>

<html lang="fr">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
Sentinel Phoenix
</title>


<style>

body {

    margin: 0;

    padding: 24px;

    background: #050509;

    color: #00ffcc;

    font-family:
        "Courier New",
        monospace;
}


h1 {

    color: #ff445f;

    border-bottom:
        2px solid #ff445f;

    padding-bottom: 12px;

    text-shadow:
        0 0 10px
        rgba(255, 68, 95, 0.5);
}


h2 {

    margin-top: 35px;
}


.subtitle {

    color: #9999aa;
}


.live {

    display: inline-block;

    width: 10px;
    height: 10px;

    border-radius: 50%;

    background: #00ffcc;

    box-shadow:
        0 0 12px #00ffcc;

    margin-left: 10px;
}


.grid {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px, 1fr)
        );

    gap: 14px;

    margin-top: 25px;
}


.card {

    background: #0b0b16;

    border:
        1px solid #00ffcc;

    padding: 16px;

    box-shadow:
        0 0 8px
        rgba(0,255,204,0.15);
}


.card h3 {

    margin-top: 0;

    color: #9999aa;

    font-size: 13px;
}


.number {

    font-size: 29px;

    font-weight: bold;
}


.green {

    color: #00ffcc;
}


.yellow {

    color: #ffff00;
}


.orange {

    color: #ff9900;
}


.red {

    color: #ff445f;
}


.purple {

    color: #cc66ff;
}


table {

    width: 100%;

    border-collapse: collapse;

    margin-top: 20px;

    background: #080812;
}


th,
td {

    border:
        1px solid #202040;

    padding: 8px;

    text-align: left;

    vertical-align: top;

    font-size: 12px;
}


th {

    background: #101022;

    color: #ff445f;
}


tr:hover {

    background: #121225;
}


.payload {

    max-width: 260px;

    word-break:
        break-word;
}


.profile {

    color: #cc66ff;

    font-weight: bold;
}


.score {

    font-weight: bold;
}


</style>

</head>


<body>


<h1>

🔥 SENTINEL PHOENIX

<span class="live"></span>

</h1>


<p class="subtitle">

Adaptive Cyber Defense Laboratory

</p>



<div class="grid">


<div class="card">

<h3>
TOTAL EVENTS
</h3>

<div
    id="total"
    class="number green"
>
0
</div>

</div>



<div class="card">

<h3>
PAYLOAD CRITICAL
</h3>

<div
    id="payload-critical"
    class="number red"
>
0
</div>

</div>



<div class="card">

<h3>
BEHAVIOR CRITICAL
</h3>

<div
    id="behavior-critical"
    class="number purple"
>
0
</div>

</div>



<div class="card">

<h3>
ANOMALY MEDIUM
</h3>

<div
    id="anomaly-medium"
    class="number yellow"
>
0
</div>

</div>



<div class="card">

<h3>
ANOMALY HIGH
</h3>

<div
    id="anomaly-high"
    class="number orange"
>
0
</div>

</div>



<div class="card">

<h3>
ANOMALY CRITICAL
</h3>

<div
    id="anomaly-critical"
    class="number red"
>
0
</div>

</div>



<div class="card">

<h3>
HIGH FREQUENCY
</h3>

<div
    id="high-frequency"
    class="number orange"
>
0
</div>

</div>



<div class="card">

<h3>
HIGH ENTROPY
</h3>

<div
    id="high-entropy"
    class="number purple"
>
0
</div>

</div>


</div>



<h2>
Live Threat Intelligence
</h2>


<table>


<thead>


<tr>

<th>
Time
</th>

<th>
Source
</th>

<th>
Payload Risk
</th>

<th>
Behavior Risk
</th>

<th>
Anomaly Risk
</th>

<th>
Profile
</th>

<th>
Entropy
</th>

<th>
Z-Score
</th>

<th>
Conn. 30s
</th>

<th>
Payload
</th>

<th>
Anomaly Reasons
</th>

</tr>


</thead>



<tbody id="events">


<tr>

<td colspan="11">

En attente d'événements...

</td>

</tr>


</tbody>


</table>



<script>


function riskClass(level) {

    const value =
        String(
            level || ""
        ).toUpperCase();


    if (
        value === "CRITICAL"
    ) {

        return "red";

    }


    if (
        value === "HIGH"
    ) {

        return "orange";

    }


    if (
        value === "MEDIUM"
    ) {

        return "yellow";

    }


    return "green";
}



async function refreshDashboard() {


    try {


        // ========================================
        // STATS
        // ========================================

        const statsResponse =
            await fetch(
                "/api/stats"
            );


        const statsData =
            await statsResponse.json();


        const stats =
            statsData.stats;


        document.getElementById(
            "total"
        ).innerText =
            stats.total;


        document.getElementById(
            "payload-critical"
        ).innerText =
            stats.payload_critical;


        document.getElementById(
            "behavior-critical"
        ).innerText =
            stats.behavior_critical;


        document.getElementById(
            "anomaly-medium"
        ).innerText =
            stats.anomaly_medium;


        document.getElementById(
            "anomaly-high"
        ).innerText =
            stats.anomaly_high;


        document.getElementById(
            "anomaly-critical"
        ).innerText =
            stats.anomaly_critical;


        document.getElementById(
            "high-frequency"
        ).innerText =
            stats.high_frequency;


        document.getElementById(
            "high-entropy"
        ).innerText =
            stats.high_entropy;



        // ========================================
        // EVENTS
        // ========================================

        const eventsResponse =
            await fetch(
                "/api/events"
            );


        const eventsData =
            await eventsResponse.json();


        const tbody =
            document.getElementById(
                "events"
            );


        tbody.innerHTML = "";


        if (
            eventsData.events.length
            ===
            0
        ) {


            tbody.innerHTML = `

                <tr>

                    <td colspan="11">

                    Aucun événement enregistré.

                    </td>

                </tr>

            `;


            return;

        }



        eventsData.events.forEach(

            event => {


                const row =
                    document.createElement(
                        "tr"
                    );


                const payloadLevel =
                    event.severity
                    ||
                    "UNKNOWN";


                const behaviorLevel =
                    event.behavior_level
                    ||
                    "UNKNOWN";


                const anomalyLevel =
                    event.anomaly_level
                    ||
                    "UNKNOWN";


                const anomalyReasons =
                    Array.isArray(
                        event.anomaly_reasons
                    )
                    ?
                    event.anomaly_reasons.join(
                        ", "
                    )
                    :
                    "";


                row.innerHTML = `

<td></td>

<td></td>


<td
class="${
    riskClass(
        payloadLevel
    )
} score"
>

${payloadLevel}

<br>

${event.score ?? 0}/100

</td>


<td
class="${
    riskClass(
        behaviorLevel
    )
} score"
>

${behaviorLevel}

<br>

${event.behavior_score ?? 0}/100

</td>


<td
class="${
    riskClass(
        anomalyLevel
    )
} score"
>

${anomalyLevel}

<br>

${event.anomaly_score ?? 0}/100

</td>


<td class="profile">
</td>


<td>
</td>


<td>
</td>


<td>
</td>


<td class="payload">
</td>


<td>
</td>

                `;


                row.children[0].textContent =
                    event.timestamp
                    ||
                    "";


                row.children[1].textContent =
                    (
                        event.source_ip
                        ||
                        ""
                    )
                    +
                    ":"
                    +
                    (
                        event.source_port
                        ||
                        ""
                    );


                row.children[5].textContent =
                    event.behavior_type
                    ||
                    "UNKNOWN";


                row.children[6].textContent =
                    event.entropy
                    ??
                    0;


                row.children[7].textContent =
                    event.length_zscore
                    ??
                    0;


                row.children[8].textContent =
                    event.connections_30s
                    ??
                    0;


                row.children[9].textContent =
                    event.payload
                    ||
                    "<vide>";


                row.children[10].textContent =
                    anomalyReasons
                    ||
                    "-";


                tbody.appendChild(
                    row
                );

            }

        );


    }

    catch (error) {


        console.log(
            "Dashboard error:",
            error
        );


    }

}



refreshDashboard();


setInterval(
    refreshDashboard,
    1500
);


</script>


</body>

</html>
"""
    )


# ============================================================
# START DASHBOARD
# ============================================================

def run_dashboard():

    print(
        f"[+] Dashboard actif : "
        f"http://{DASHBOARD_HOST}:"
        f"{DASHBOARD_PORT}"
    )

    app.run(
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        debug=False,
        use_reloader=False
    )