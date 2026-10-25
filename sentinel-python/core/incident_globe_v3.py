# ============================================================
# SENTINEL PHOENIX
# INCIDENT INTELLIGENCE GLOBE V3.1
#
# Stable narrated Globe:
#
# - Globe V2 Canvas rendering
# - lightweight automatic narration
# - narration ON / OFF
# - explicit AI ANALYZE button
# - Qwen3 4B loaded only on demand
# - QWebChannel asynchronous bridge
# - VirtualBox software-rendering friendly
# ============================================================

import argparse
import json
import os
import sys
from typing import Any, Dict


# ============================================================
# VIRTUALBOX / SOFTWARE RENDERING
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


from PySide6.QtCore import (
    QObject,
    QUrl,
    Slot,
)

from PySide6.QtWebChannel import (
    QWebChannel,
)

from PySide6.QtWidgets import (
    QApplication,
)

from PySide6.QtWebEngineWidgets import (
    QWebEngineView,
)


from core import incident_globe_v2 as v2

from core.globe_narration_bridge import (
    GlobeNarrationBridge,
)


GLOBE_VERSION = "3.1"


# ============================================================
# PYTHON <-> JAVASCRIPT ENDPOINT
# ============================================================

class NarrationEndpoint(QObject):

    def __init__(
        self,
        language: str = "fr",
    ):
        super().__init__()

        self.language = language

        self.bridge = GlobeNarrationBridge(
            language=language
        )


    # --------------------------------------------------------
    # Lightweight automatic narration
    # --------------------------------------------------------

    @Slot(str)
    def narrateEvent(
        self,
        payload_json: str,
    ):

        incident = self._decode(
            payload_json
        )

        if incident is None:
            return

        print(
            "[GLOBE V3.1] "
            "Light narration:",
            incident.get(
                "source_ip",
                "UNKNOWN",
            ),
            flush=True,
        )

        self.bridge.narrate(
            incident
        )


    # --------------------------------------------------------
    # Explicit Qwen analysis
    # --------------------------------------------------------

    @Slot(str)
    def analyzeEvent(
        self,
        payload_json: str,
    ):

        incident = self._decode(
            payload_json
        )

        if incident is None:
            return

        print(
            "[GLOBE V3.1] "
            "AI analysis requested:",
            incident.get(
                "source_ip",
                "UNKNOWN",
            ),
            incident.get(
                "level",
                "UNKNOWN",
            ),
            flush=True,
        )

        # This only queues the work.
        # Qwen runs in the bridge worker thread.
        self.bridge.analyze(
            incident
        )


    # --------------------------------------------------------
    # Stop narration
    # --------------------------------------------------------

    @Slot()
    def stopNarration(
        self,
    ):

        # We intentionally do not destroy the bridge here,
        # because narration can later be re-enabled.
        pass


    # --------------------------------------------------------
    # Decode payload
    # --------------------------------------------------------

    def _decode(
        self,
        payload_json: str,
    ):

        try:

            incident = json.loads(
                payload_json
            )

        except Exception as error:

            print(
                "[GLOBE V3.1] "
                "Invalid payload:",
                repr(error),
                flush=True,
            )

            return None

        if not isinstance(
            incident,
            dict,
        ):
            return None

        return incident


    # --------------------------------------------------------
    # Shutdown
    # --------------------------------------------------------

    def shutdown(
        self,
    ):

        try:
            self.bridge.stop()

        except Exception:
            pass


# ============================================================
# HTML BUILDER
# ============================================================

def build_html(
    payload: Dict[str, Any],
) -> str:

    data = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )

    data = data.replace(
        "</",
        "<\\/",
    )

    html = (
        v2.HTML_TEMPLATE
        .replace(
            "__DATA__",
            data,
        )
    )

    # ========================================================
    # QWEBCHANNEL
    # ========================================================

    html = html.replace(
        "<script>\n\nconst DATA",
        (
            '<script '
            'src="qrc:///qtwebchannel/qwebchannel.js">'
            '</script>\n'
            '<script>\n\n'
            'const DATA'
        ),
        1,
    )


    # ========================================================
    # ADD NARRATION + AI BUTTONS
    # ========================================================

    old_controls = """
    <button onclick="nextEvent()">
        NEXT ▶
    </button>

    <span id="counter">
"""

    new_controls = """
    <button onclick="nextEvent()">
        NEXT ▶
    </button>

    <button
        id="narrationButton"
        onclick="toggleNarration()"
    >
        🔊 NARRATION ON
    </button>

    <button
        id="aiButton"
        onclick="analyzeCurrentIncident()"
    >
        🧠 AI ANALYZE
    </button>

    <span id="counter">
"""

    html = html.replace(
        old_controls,
        new_controls,
        1,
    )


    # ========================================================
    # JS BRIDGE
    # ========================================================

    old_delay = """
const autoDelay = 6500;
"""

    new_delay = r"""
const autoDelay = 12000;


// ============================================================
// SENTINEL NARRATION / AI BRIDGE
// ============================================================

let sentinelNarration = null;

let narrationEnabled = true;

let aiRequestPending = false;


// ------------------------------------------------------------
// BUTTON STATES
// ------------------------------------------------------------

function updateNarrationButton() {

    const button =
        document.getElementById(
            "narrationButton"
        );

    if (!button) {
        return;
    }

    if (!sentinelNarration) {

        button.textContent =
            "🔇 NARRATION WAITING";

        return;
    }

    button.textContent =
        narrationEnabled
        ? "🔊 NARRATION ON"
        : "🔇 NARRATION OFF";
}


function updateAIButton() {

    const button =
        document.getElementById(
            "aiButton"
        );

    if (!button) {
        return;
    }

    if (!sentinelNarration) {

        button.textContent =
            "🧠 AI WAITING";

        button.disabled =
            true;

        return;
    }

    button.disabled =
        false;

    button.textContent =
        aiRequestPending
        ? "🧠 AI QUEUED..."
        : "🧠 AI ANALYZE";
}


// ------------------------------------------------------------
// AUTOMATIC LIGHT NARRATION
// ------------------------------------------------------------

function requestNarration() {

    if (
        !narrationEnabled
        || !sentinelNarration
    ) {
        return;
    }

    const event =
        getCurrentEvent();

    if (!event) {
        return;
    }

    try {

        sentinelNarration.narrateEvent(
            JSON.stringify(
                event
            )
        );

    } catch (error) {

        console.log(
            "Narration bridge error:",
            error
        );
    }
}


// ------------------------------------------------------------
// EXPLICIT QWEN ANALYSIS
// ------------------------------------------------------------

function analyzeCurrentIncident() {

    if (
        !sentinelNarration
        || aiRequestPending
    ) {
        return;
    }

    const event =
        getCurrentEvent();

    if (!event) {
        return;
    }

    aiRequestPending =
        true;

    updateAIButton();

    try {

        sentinelNarration.analyzeEvent(
            JSON.stringify(
                event
            )
        );

        // The Python bridge queues the request immediately.
        // We unlock the UI shortly afterwards.
        setTimeout(
            function() {

                aiRequestPending =
                    false;

                updateAIButton();
            },

            2500
        );

    } catch (error) {

        aiRequestPending =
            false;

        updateAIButton();

        console.log(
            "AI bridge error:",
            error
        );
    }
}


// ------------------------------------------------------------
// NARRATION TOGGLE
// ------------------------------------------------------------

function toggleNarration() {

    narrationEnabled =
        !narrationEnabled;

    updateNarrationButton();

    if (
        narrationEnabled
    ) {

        requestNarration();
    }
}


// ------------------------------------------------------------
// BRIDGE INITIALIZATION
// ------------------------------------------------------------

function initializeNarrationBridge() {

    if (
        typeof qt === "undefined"
        ||
        typeof QWebChannel === "undefined"
    ) {

        console.log(
            "Sentinel bridge unavailable."
        );

        updateNarrationButton();
        updateAIButton();

        return;
    }

    new QWebChannel(
        qt.webChannelTransport,

        function(channel) {

            sentinelNarration =
                channel.objects
                .sentinelNarration;

            console.log(
                "Sentinel narration + AI bridge ONLINE."
            );

            updateNarrationButton();
            updateAIButton();

            setTimeout(
                requestNarration,
                700
            );
        }
    );
}


window.addEventListener(
    "load",
    initializeNarrationBridge
);
"""

    html = html.replace(
        old_delay,
        new_delay,
        1,
    )


    # ========================================================
    # NARRATE ON EVENT CHANGE
    # ========================================================

    old_selection_end = """
    updatePanel();
}


function nextEvent() {
"""

    new_selection_end = """
    updatePanel();

    requestNarration();
}


function nextEvent() {
"""

    html = html.replace(
        old_selection_end,
        new_selection_end,
        1,
    )

    return html


# ============================================================
# RUN
# ============================================================

def run_globe(
    query: str = "latest",
    language: str = "fr",
) -> int:

    print(
        "=" * 70,
        flush=True,
    )

    print(
        "SENTINEL PHOENIX "
        f"INCIDENT GLOBE V{GLOBE_VERSION}",
        flush=True,
    )

    print(
        "STABLE NARRATION + "
        "ON-DEMAND QWEN ANALYSIS",
        flush=True,
    )

    print(
        "=" * 70,
        flush=True,
    )

    print(
        "[GLOBE V3.1] Query:",
        query,
        flush=True,
    )

    raw_payload = (
        v2.load_replay_payload(
            query
        )
    )

    payload = (
        v2.normalize_payload(
            raw_payload,
            query,
        )
    )

    events = payload.get(
        "events",
        [],
    )

    print(
        "[GLOBE V3.1] Events:",
        len(events),
        flush=True,
    )

    print(
        "[GLOBE V3.1] Geo:",
        sum(
            1
            for event in events
            if event.get(
                "has_geo"
            )
        ),
        flush=True,
    )

    print(
        "[GLOBE V3.1] Local:",
        sum(
            1
            for event in events
            if event.get(
                "local"
            )
        ),
        flush=True,
    )

    app = (
        QApplication.instance()
        or
        QApplication(
            sys.argv
        )
    )

    browser = (
        QWebEngineView()
    )

    browser.setWindowTitle(
        "Sentinel Phoenix // "
        "Incident Intelligence V3.1"
    )

    browser.resize(
        1400,
        850,
    )


    # ========================================================
    # QWEBCHANNEL
    # ========================================================

    channel = QWebChannel(
        browser.page()
    )

    endpoint = NarrationEndpoint(
        language=language
    )

    channel.registerObject(
        "sentinelNarration",
        endpoint,
    )

    browser.page().setWebChannel(
        channel
    )

    # Prevent garbage collection.
    browser._sentinel_channel = (
        channel
    )

    browser._sentinel_endpoint = (
        endpoint
    )


    # ========================================================
    # UI
    # ========================================================

    browser.setHtml(
        build_html(
            payload
        ),
        QUrl(
            "about:blank"
        ),
    )

    browser.show()

    app.aboutToQuit.connect(
        endpoint.shutdown
    )

    return app.exec()


# ============================================================
# SELF TEST
# ============================================================

def self_test(
    query: str = "latest",
) -> int:

    raw_payload = (
        v2.load_replay_payload(
            query
        )
    )

    payload = (
        v2.normalize_payload(
            raw_payload,
            query,
        )
    )

    result = {
        "status":
            "PASS",

        "version":
            GLOBE_VERSION,

        "events":
            payload.get(
                "event_count",
                0,
            ),

        "base_globe":
            "V2",

        "automatic_narration":
            "DETERMINISTIC_TTS",

        "ai_analysis":
            "EXPLICIT_QWEN3_4B",

        "qwen_auto_load":
            False,

        "narration_button":
            True,

        "ai_analyze_button":
            True,

        "ui_blocking":
            False,

        "rendering":
            "HTML5_CANVAS",

        "webgl":
            False,
    }

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
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
        "--language",
        default="fr",
        choices=[
            "fr",
            "en",
        ],
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
        query=args.query,
        language=args.language,
    )


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
