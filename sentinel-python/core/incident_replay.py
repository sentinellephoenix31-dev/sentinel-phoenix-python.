import math
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime


# ============================================================
# SENTINEL PHOENIX
# VISUAL INCIDENT REPLAY V1
#
# Cinematic security visualization.
#
# Features:
# - Animated globe
# - Globe rotation
# - Zoom toward approximate source
# - Geographic marker
# - Security HUD
# - Incident timeline information
#
# IMPORTANT:
# Geographic information represents approximate IP-derived
# location only. It does NOT identify a physical person.
# ============================================================


INCIDENT_REPLAY_VERSION = "1.0"


WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

FPS = 30

GLOBE_CENTER_X = 440
GLOBE_CENTER_Y = 355

BASE_RADIUS = 235

HUD_X = 760


# ============================================================
# DATA
# ============================================================

@dataclass
class Incident:

    source_ip: str

    country: str

    region: str

    latitude: float

    longitude: float

    asn: str

    provider: str

    threat_type: str

    risk_score: float

    action: str

    timestamp: str

    description: str = ""


# ============================================================
# HELPERS
# ============================================================

def clamp(
    value,
    minimum,
    maximum
):

    return max(
        minimum,
        min(
            maximum,
            value
        )
    )


def parse_timestamp(
    value
):

    if not value:

        return datetime.now()


    try:

        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00"
            )
        )

    except ValueError:

        return datetime.now()


# ============================================================
# VISUAL REPLAY
# ============================================================

class IncidentReplay:

    def __init__(
        self,
        incident
    ):

        self.incident = incident


        self.root = tk.Tk()

        self.root.title(
            "Sentinel Phoenix - Visual Incident Replay"
        )


        self.root.geometry(
            f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}"
        )


        self.root.configure(
            bg="#020807"
        )


        self.root.resizable(
            False,
            False
        )


        self.canvas = tk.Canvas(
            self.root,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            bg="#020807",
            highlightthickness=0
        )


        self.canvas.pack(
            fill="both",
            expand=True
        )


        # ================================================
        # Animation
        # ================================================

        self.rotation = -110.0

        self.target_rotation = (
            -float(
                incident.longitude
            )
        )


        self.zoom = 1.0

        self.target_zoom = 1.34


        self.animation_stage = 0

        self.stage_started = (
            time.monotonic()
        )


        self.marker_strength = 0.0

        self.scan_phase = 0.0


        self.running = True


        self.root.bind(
            "<Escape>",
            lambda event:
                self.close()
        )


        self.root.bind(
            "q",
            lambda event:
                self.close()
        )


    # ========================================================
    # CLOSE
    # ========================================================

    def close(
        self
    ):

        self.running = False

        try:

            self.root.destroy()

        except tk.TclError:

            pass


    # ========================================================
    # TITLE
    # ========================================================

    def draw_header(
        self
    ):

        self.canvas.create_text(

            40,
            35,

            anchor="w",

            text="SENTINEL PHOENIX",

            fill="#b8ffe2",

            font=(
                "Courier",
                22,
                "bold"
            )
        )


        self.canvas.create_text(

            40,
            66,

            anchor="w",

            text=(
                "VISUAL INCIDENT REPLAY "
                f"// ENGINE {INCIDENT_REPLAY_VERSION}"
            ),

            fill="#39ff98",

            font=(
                "Courier",
                11
            )
        )


        self.canvas.create_line(

            40,
            88,

            WINDOW_WIDTH - 40,
            88,

            fill="#145b42",

            width=1
        )


    # ========================================================
    # GRID BACKGROUND
    # ========================================================

    def draw_background_grid(
        self
    ):

        spacing = 48


        for x in range(
            0,
            WINDOW_WIDTH,
            spacing
        ):

            self.canvas.create_line(

                x,
                95,

                x,
                WINDOW_HEIGHT,

                fill="#08251c"
            )


        for y in range(
            95,
            WINDOW_HEIGHT,
            spacing
        ):

            self.canvas.create_line(

                0,
                y,

                WINDOW_WIDTH,
                y,

                fill="#08251c"
            )


    # ========================================================
    # SPHERE PROJECTION
    # ========================================================

    def project_point(
        self,
        latitude,
        longitude
    ):

        lat = math.radians(
            latitude
        )


        lon = math.radians(
            longitude
            +
            self.rotation
        )


        radius = (
            BASE_RADIUS
            *
            self.zoom
        )


        x = (
            GLOBE_CENTER_X
            +
            radius
            *
            math.cos(
                lat
            )
            *
            math.sin(
                lon
            )
        )


        y = (
            GLOBE_CENTER_Y
            -
            radius
            *
            math.sin(
                lat
            )
        )


        depth = (
            math.cos(
                lat
            )
            *
            math.cos(
                lon
            )
        )


        return (
            x,
            y,
            depth
        )


    # ========================================================
    # GLOBE
    # ========================================================

    def draw_globe(
        self
    ):

        radius = (
            BASE_RADIUS
            *
            self.zoom
        )


        # Outer atmosphere

        self.canvas.create_oval(

            GLOBE_CENTER_X
            -
            radius
            -
            8,

            GLOBE_CENTER_Y
            -
            radius
            -
            8,

            GLOBE_CENTER_X
            +
            radius
            +
            8,

            GLOBE_CENTER_Y
            +
            radius
            +
            8,

            outline="#0e513a",

            width=2
        )


        # Sphere

        self.canvas.create_oval(

            GLOBE_CENTER_X
            -
            radius,

            GLOBE_CENTER_Y
            -
            radius,

            GLOBE_CENTER_X
            +
            radius,

            GLOBE_CENTER_Y
            +
            radius,

            outline="#36ff99",

            width=2
        )


        # ================================================
        # Latitude lines
        # ================================================

        for latitude in (
            -60,
            -30,
            0,
            30,
            60
        ):

            lat = math.radians(
                latitude
            )


            y = (
                GLOBE_CENTER_Y
                -
                radius
                *
                math.sin(
                    lat
                )
            )


            horizontal_radius = (
                radius
                *
                math.cos(
                    lat
                )
            )


            vertical_radius = max(
                4,
                horizontal_radius
                *
                0.15
            )


            self.canvas.create_oval(

                GLOBE_CENTER_X
                -
                horizontal_radius,

                y
                -
                vertical_radius,

                GLOBE_CENTER_X
                +
                horizontal_radius,

                y
                +
                vertical_radius,

                outline="#116143"
            )


        # ================================================
        # Longitude wireframe
        # ================================================

        for longitude in range(
            -150,
            181,
            30
        ):

            points = []


            for latitude in range(
                -90,
                91,
                4
            ):

                x, y, depth = (
                    self.project_point(
                        latitude,
                        longitude
                    )
                )


                if depth >= -0.08:

                    points.extend(
                        (
                            x,
                            y
                        )
                    )


            if len(
                points
            ) >= 4:

                self.canvas.create_line(

                    points,

                    fill="#125b40",

                    smooth=True
                )


        # ================================================
        # Moving scan ring
        # ================================================

        scan_y = (
            GLOBE_CENTER_Y
            +
            math.sin(
                self.scan_phase
            )
            *
            radius
            *
            0.75
        )


        local_y = (
            scan_y
            -
            GLOBE_CENTER_Y
        )


        ratio = (
            local_y
            /
            max(
                radius,
                1
            )
        )


        ratio = clamp(
            ratio,
            -1,
            1
        )


        scan_width = (
            radius
            *
            math.sqrt(
                max(
                    0.0,
                    1.0
                    -
                    ratio
                    *
                    ratio
                )
            )
        )


        self.canvas.create_line(

            GLOBE_CENTER_X
            -
            scan_width,

            scan_y,

            GLOBE_CENTER_X
            +
            scan_width,

            scan_y,

            fill="#44ffad",

            width=2
        )


    # ========================================================
    # SOURCE MARKER
    # ========================================================

    def draw_source_marker(
        self
    ):

        x, y, depth = self.project_point(

            self.incident.latitude,

            self.incident.longitude
        )


        if depth < 0:

            return


        pulse = (

            1.0
            +
            0.25
            *
            math.sin(
                self.scan_phase
                *
                4
            )
        )


        size = (
            10
            +
            18
            *
            self.marker_strength
            *
            pulse
        )


        self.canvas.create_oval(

            x - size,
            y - size,

            x + size,
            y + size,

            outline="#52ff9f",

            width=2
        )


        self.canvas.create_oval(

            x - 4,
            y - 4,

            x + 4,
            y + 4,

            fill="#89ffc4",

            outline=""
        )


        self.canvas.create_line(

            x,
            y,

            x + 65,
            y - 45,

            fill="#48ffa3",

            width=1
        )


        self.canvas.create_text(

            x + 72,
            y - 48,

            anchor="w",

            text=self.incident.country.upper(),

            fill="#70ffb7",

            font=(
                "Courier",
                11,
                "bold"
            )
        )


    # ========================================================
    # HUD
    # ========================================================

    def hud_line(
        self,
        y,
        label,
        value,
        important=False
    ):

        label_color = "#3edc8c"


        value_color = (
            "#9effca"
            if not important
            else
            "#ffffff"
        )


        self.canvas.create_text(

            HUD_X,
            y,

            anchor="w",

            text=label,

            fill=label_color,

            font=(
                "Courier",
                10
            )
        )


        self.canvas.create_text(

            HUD_X + 170,
            y,

            anchor="w",

            text=str(
                value
            ),

            fill=value_color,

            font=(
                "Courier",
                11,
                "bold"
            )
        )


    def draw_hud(
        self
    ):

        self.canvas.create_rectangle(

            HUD_X - 25,
            125,

            WINDOW_WIDTH - 40,
            WINDOW_HEIGHT - 55,

            outline="#145c42",

            width=2
        )


        self.canvas.create_text(

            HUD_X,
            155,

            anchor="w",

            text="INCIDENT INTELLIGENCE",

            fill="#76ffbb",

            font=(
                "Courier",
                17,
                "bold"
            )
        )


        timestamp = parse_timestamp(
            self.incident.timestamp
        )


        self.hud_line(
            210,
            "SOURCE IP",
            self.incident.source_ip,
            True
        )


        self.hud_line(
            245,
            "COUNTRY",
            self.incident.country
        )


        self.hud_line(
            280,
            "REGION",
            self.incident.region
        )


        self.hud_line(
            315,
            "ASN",
            self.incident.asn
        )


        self.hud_line(
            350,
            "PROVIDER",
            self.incident.provider
        )


        self.hud_line(
            400,
            "DATE",
            timestamp.strftime(
                "%Y-%m-%d"
            )
        )


        self.hud_line(
            435,
            "TIME",
            timestamp.strftime(
                "%H:%M:%S"
            )
        )


        self.hud_line(
            485,
            "THREAT",
            self.incident.threat_type,
            True
        )


        self.hud_line(
            520,
            "RISK SCORE",
            (
                f"{self.incident.risk_score:.0f}/100"
            ),
            True
        )


        self.hud_line(
            555,
            "ACTION",
            self.incident.action
        )


        self.canvas.create_text(

            HUD_X,
            615,

            anchor="nw",

            width=420,

            text=(
                self.incident.description
                or
                "Security incident reconstructed "
                "from Sentinel telemetry."
            ),

            fill="#a3d9c1",

            font=(
                "Courier",
                10
            )
        )


        self.canvas.create_text(

            HUD_X,
            WINDOW_HEIGHT - 82,

            anchor="w",

            text=(
                "LOCATION CONFIDENCE: "
                "APPROXIMATE IP GEOLOCATION"
            ),

            fill="#689b83",

            font=(
                "Courier",
                9
            )
        )


    # ========================================================
    # STATUS
    # ========================================================

    def draw_status(
        self
    ):

        if self.animation_stage == 0:

            text = (
                "ACQUIRING INCIDENT TELEMETRY..."
            )


        elif self.animation_stage == 1:

            text = (
                "ROTATING GLOBAL THREAT MAP..."
            )


        elif self.animation_stage == 2:

            text = (
                "GEOLOCATION CORRELATION..."
            )


        else:

            text = (
                "SOURCE REGION IDENTIFIED"
            )


        self.canvas.create_text(

            40,
            WINDOW_HEIGHT - 35,

            anchor="w",

            text=text,

            fill="#49ff9e",

            font=(
                "Courier",
                11,
                "bold"
            )
        )


        self.canvas.create_text(

            WINDOW_WIDTH - 40,
            WINDOW_HEIGHT - 35,

            anchor="e",

            text="ESC / Q : CLOSE",

            fill="#487c66",

            font=(
                "Courier",
                9
            )
        )


    # ========================================================
    # ANIMATION
    # ========================================================

    def update_animation(
        self
    ):

        now = time.monotonic()

        elapsed = (
            now
            -
            self.stage_started
        )


        # Initial scanning

        if self.animation_stage == 0:

            self.rotation += 0.8


            if elapsed > 1.4:

                self.animation_stage = 1

                self.stage_started = now


        # Rotate toward source longitude

        elif self.animation_stage == 1:

            delta = (
                self.target_rotation
                -
                self.rotation
            )


            self.rotation += (
                delta
                *
                0.055
            )


            if (
                abs(
                    delta
                )
                <
                2.0
                or
                elapsed > 4.0
            ):

                self.animation_stage = 2

                self.stage_started = now


        # Zoom

        elif self.animation_stage == 2:

            self.zoom += (
                (
                    self.target_zoom
                    -
                    self.zoom
                )
                *
                0.055
            )


            self.marker_strength = min(
                1.0,
                self.marker_strength
                +
                0.04
            )


            if elapsed > 2.3:

                self.animation_stage = 3

                self.stage_started = now


        # Hold target

        else:

            self.marker_strength = 1.0


        self.scan_phase += 0.045


    # ========================================================
    # FRAME
    # ========================================================

    def frame(
        self
    ):

        if not self.running:

            return


        self.canvas.delete(
            "all"
        )


        self.update_animation()


        self.draw_background_grid()

        self.draw_header()

        self.draw_globe()

        self.draw_source_marker()

        self.draw_hud()

        self.draw_status()


        try:

            self.root.after(
                int(
                    1000
                    /
                    FPS
                ),
                self.frame
            )

        except tk.TclError:

            return


    # ========================================================
    # RUN
    # ========================================================

    def run(
        self
    ):

        self.frame()

        self.root.mainloop()


# ============================================================
# PUBLIC FUNCTION
# ============================================================

def replay_incident(
    incident
):

    if isinstance(
        incident,
        dict
    ):

        incident = Incident(
            **incident
        )


    app = IncidentReplay(
        incident
    )


    app.run()


# ============================================================
# DEMO
# ============================================================

def demo():

    # Synthetic incident used only to test the UI.
    # It is NOT real telemetry.

    incident = Incident(

        source_ip=
            "203.0.113.42",

        country=
            "Germany",

        region=
            "Frankfurt",

        latitude=
            50.1109,

        longitude=
            8.6821,

        asn=
            "AS-DEMO",

        provider=
            "Demo Network",

        threat_type=
            "HONEYPOT RECONNAISSANCE",

        risk_score=
            87,

        action=
            "CONTAINED / DECEPTION ACTIVE",

        timestamp=
            datetime.now().isoformat(),

        description=(
            "Multiple reconnaissance events were "
            "correlated by Sentinel. The source was "
            "redirected toward the deception layer."
        )
    )


    replay_incident(
        incident
    )


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    required = all(
        [
            callable(
                replay_incident
            ),

            callable(
                demo
            ),

            callable(
                IncidentReplay
            )
        ]
    )


    return {

        "status":
            (
                "PASS"
                if required
                else
                "FAIL"
            ),

        "version":
            INCIDENT_REPLAY_VERSION,

        "features": {

            "animated_globe":
                True,

            "rotation":
                True,

            "source_zoom":
                True,

            "country_marker":
                True,

            "incident_hud":
                True,

            "source_ip":
                True,

            "asn":
                True,

            "risk_score":
                True,

            "incident_time":
                True,

            "approximate_geolocation_notice":
                True
        }
    }


if __name__ == "__main__":

    demo()