# ============================================================
# SENTINEL PHOENIX
# PREMIUM ORB V2.1
#
# Lightweight Tkinter Orb
#
# Features:
# - Fade in / fade out
# - Smooth color/state transitions
# - Animated holographic rings
# - Lightweight VirtualBox-safe rendering
#
# Public API preserved:
#   SentinelOrb()
#   show()
#   hide()
#   set_state(...)
#   run()
# ============================================================

import math
import queue
import time
import tkinter as tk


ORB_VERSION = "2.1"

WINDOW_SIZE = 460
CENTER = WINDOW_SIZE // 2

FPS_MS = 40

FADE_STEP_MS = 20
FADE_SPEED = 0.085
MAX_ALPHA = 0.95

STATE_TRANSITION_SECONDS = 0.38


# ============================================================
# COLOR UTILITIES
# ============================================================

def hex_to_rgb(value):
    value = value.lstrip("#")

    return tuple(
        int(value[i:i + 2], 16)
        for i in (0, 2, 4)
    )


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(
        max(
            0,
            min(
                255,
                int(component),
            ),
        )
        for component in rgb
    )


def blend(color_a, color_b, ratio):
    ratio = max(
        0.0,
        min(
            1.0,
            float(ratio),
        ),
    )

    a = hex_to_rgb(color_a)
    b = hex_to_rgb(color_b)

    return rgb_to_hex(
        tuple(
            a[i]
            +
            (
                b[i]
                -
                a[i]
            )
            * ratio
            for i in range(3)
        )
    )


def lerp(a, b, ratio):
    return (
        float(a)
        +
        (
            float(b)
            -
            float(a)
        )
        * ratio
    )


# ============================================================
# STATE PROFILES
# ============================================================

STATE_PROFILES = {

    "IDLE": {
        "color": "#55dff8",
        "speed": 0.30,
        "pulse": 2.0,
        "frequency": 1.2,
        "label": "STANDBY",
    },

    "READY": {
        "color": "#68f4ff",
        "speed": 0.52,
        "pulse": 4.0,
        "frequency": 1.6,
        "label": "ONLINE",
    },

    "LISTENING": {
        "color": "#57f7e8",
        "speed": 0.72,
        "pulse": 12.0,
        "frequency": 2.0,
        "label": "LISTENING",
    },

    "THINKING": {
        "color": "#9d7cff",
        "speed": 1.90,
        "pulse": 7.0,
        "frequency": 2.8,
        "label": "PROCESSING",
    },

    "SPEAKING": {
        "color": "#4ec8ff",
        "speed": 1.10,
        "pulse": 15.0,
        "frequency": 3.6,
        "label": "SPEAKING",
    },

    "ALERT": {
        "color": "#ff506d",
        "speed": 2.25,
        "pulse": 12.0,
        "frequency": 4.0,
        "label": "SECURITY ALERT",
    },

    "SUCCESS": {
        "color": "#65ffad",
        "speed": 0.75,
        "pulse": 7.0,
        "frequency": 2.2,
        "label": "SECURE",
    },

    "ERROR": {
        "color": "#ff775c",
        "speed": 1.70,
        "pulse": 10.0,
        "frequency": 3.5,
        "label": "SYSTEM ERROR",
    },
}


STATE_ALIASES = {

    "PROCESSING":
        "THINKING",

    "THINK":
        "THINKING",

    "LISTEN":
        "LISTENING",

    "SPEAK":
        "SPEAKING",

    "WAITING":
        "IDLE",

    "WAKE":
        "READY",

    "ONLINE":
        "READY",
}


# ============================================================
# SENTINEL ORB
# ============================================================

class SentinelOrb:

    def __init__(self):

        self.state = "IDLE"

        self._commands = queue.Queue()

        self._running = False
        self._visible = False

        self.root = None
        self.canvas = None

        self._started_at = time.monotonic()

        # ----------------------------------------------------
        # Fade state
        # ----------------------------------------------------

        self._alpha = 0.0
        self._target_alpha = 0.0

        # ----------------------------------------------------
        # Smooth visual transition
        # ----------------------------------------------------

        self._visual_state = "IDLE"
        self._previous_state = "IDLE"

        self._transition_start = (
            time.monotonic()
        )


    # ========================================================
    # PUBLIC API
    # ========================================================

    def show(self):

        self._commands.put(
            (
                "SHOW",
                None,
            )
        )


    def hide(self):

        self._commands.put(
            (
                "HIDE",
                None,
            )
        )


    def set_state(
        self,
        state,
    ):

        normalized = str(
            state or "IDLE"
        ).strip().upper()

        normalized = (
            STATE_ALIASES.get(
                normalized,
                normalized,
            )
        )

        if normalized not in STATE_PROFILES:

            normalized = "READY"

        self.state = normalized

        self._commands.put(
            (
                "STATE",
                normalized,
            )
        )


    def close(self):

        self._commands.put(
            (
                "CLOSE",
                None,
            )
        )


    # ========================================================
    # WINDOW
    # ========================================================

    def _create_window(self):

        self.root = tk.Tk()

        self.root.title(
            "Sentinel Phoenix Orb"
        )

        self.root.overrideredirect(
            True
        )

        self.root.attributes(
            "-topmost",
            True
        )

        try:

            self.root.attributes(
                "-alpha",
                0.0,
            )

        except Exception:
            pass

        self.root.configure(
            bg="#05090f"
        )

        self.root.geometry(
            f"{WINDOW_SIZE}x{WINDOW_SIZE}"
            f"+{self._screen_x()}"
            f"+{self._screen_y()}"
        )

        self.canvas = tk.Canvas(
            self.root,
            width=WINDOW_SIZE,
            height=WINDOW_SIZE,
            bg="#05090f",
            highlightthickness=0,
            bd=0,
        )

        self.canvas.pack(
            fill="both",
            expand=True,
        )

        self.root.bind(
            "<Escape>",
            lambda event:
                self.close()
        )

        self.root.bind(
            "<Double-Button-1>",
            lambda event:
                self.close()
        )

        self.root.withdraw()

        self.root.after(
            20,
            self._poll_commands,
        )

        self.root.after(
            FPS_MS,
            self._animate,
        )

        self.root.after(
            FADE_STEP_MS,
            self._fade_tick,
        )


    def _screen_x(self):

        try:

            width = (
                self.root
                .winfo_screenwidth()
            )

            return max(
                0,
                int(
                    (
                        width
                        -
                        WINDOW_SIZE
                    )
                    / 2
                ),
            )

        except Exception:

            return 100


    def _screen_y(self):

        try:

            height = (
                self.root
                .winfo_screenheight()
            )

            return max(
                0,
                int(
                    (
                        height
                        -
                        WINDOW_SIZE
                    )
                    / 2
                ),
            )

        except Exception:

            return 100


    # ========================================================
    # COMMAND QUEUE
    # ========================================================

    def _poll_commands(self):

        if not self._running:
            return

        while True:

            try:

                command, value = (
                    self._commands
                    .get_nowait()
                )

            except queue.Empty:
                break

            if command == "SHOW":

                self._visible = True

                self._target_alpha = MAX_ALPHA

                try:

                    self.root.deiconify()
                    self.root.lift()

                except Exception:
                    pass


            elif command == "HIDE":

                self._visible = False

                self._target_alpha = 0.0


            elif command == "STATE":

                if value != self._visual_state:

                    self._previous_state = (
                        self._visual_state
                    )

                    self._visual_state = value

                    self._transition_start = (
                        time.monotonic()
                    )


            elif command == "CLOSE":

                self._running = False

                try:
                    self.root.destroy()
                except Exception:
                    pass

                return


        try:

            self.root.after(
                20,
                self._poll_commands,
            )

        except Exception:
            pass


    # ========================================================
    # FADE ENGINE
    # ========================================================

    def _fade_tick(self):

        if not self._running:
            return

        difference = (
            self._target_alpha
            -
            self._alpha
        )

        if abs(difference) < 0.01:

            self._alpha = (
                self._target_alpha
            )

        else:

            if difference > 0:

                self._alpha = min(
                    self._target_alpha,
                    self._alpha
                    +
                    FADE_SPEED,
                )

            else:

                self._alpha = max(
                    self._target_alpha,
                    self._alpha
                    -
                    FADE_SPEED,
                )


        try:

            self.root.attributes(
                "-alpha",
                self._alpha,
            )

        except Exception:
            pass


        if (
            self._alpha <= 0.01
            and
            self._target_alpha <= 0.0
            and
            not self._visible
        ):

            try:
                self.root.withdraw()
            except Exception:
                pass


        try:

            self.root.after(
                FADE_STEP_MS,
                self._fade_tick,
            )

        except Exception:
            pass


    # ========================================================
    # PROFILE TRANSITION
    # ========================================================

    def _current_profile(self):

        previous = STATE_PROFILES.get(
            self._previous_state,
            STATE_PROFILES[
                "IDLE"
            ],
        )

        current = STATE_PROFILES.get(
            self._visual_state,
            STATE_PROFILES[
                "READY"
            ],
        )

        elapsed = (
            time.monotonic()
            -
            self._transition_start
        )

        ratio = min(
            1.0,
            max(
                0.0,
                elapsed
                /
                STATE_TRANSITION_SECONDS,
            ),
        )

        # Smoothstep interpolation
        ratio = (
            ratio
            *
            ratio
            *
            (
                3
                -
                2
                *
                ratio
            )
        )

        return {

            "color":
                blend(
                    previous[
                        "color"
                    ],
                    current[
                        "color"
                    ],
                    ratio,
                ),

            "speed":
                lerp(
                    previous[
                        "speed"
                    ],
                    current[
                        "speed"
                    ],
                    ratio,
                ),

            "pulse":
                lerp(
                    previous[
                        "pulse"
                    ],
                    current[
                        "pulse"
                    ],
                    ratio,
                ),

            "frequency":
                lerp(
                    previous[
                        "frequency"
                    ],
                    current[
                        "frequency"
                    ],
                    ratio,
                ),

            "label":
                current[
                    "label"
                ],
        }


    # ========================================================
    # ANIMATION
    # ========================================================

    def _animate(self):

        if not self._running:
            return

        try:

            if (
                self._alpha > 0.01
            ):

                self._draw_frame()

            self.root.after(
                FPS_MS,
                self._animate,
            )

        except Exception:
            pass


    # ========================================================
    # FRAME
    # ========================================================

    def _draw_frame(self):

        canvas = self.canvas

        canvas.delete(
            "all"
        )

        profile = (
            self._current_profile()
        )

        color = profile[
            "color"
        ]

        elapsed = (
            time.monotonic()
            -
            self._started_at
        )

        frequency = profile[
            "frequency"
        ]

        pulse = math.sin(
            elapsed
            *
            frequency
            *
            math.pi
            *
            2
        )

        pulse_amount = (
            profile[
                "pulse"
            ]
            *
            (
                0.5
                +
                0.5
                *
                pulse
            )
        )

        rotation = (
            elapsed
            *
            70
            *
            profile[
                "speed"
            ]
        )


        # ====================================================
        # BACKGROUND AURA
        # ====================================================

        for index in range(
            7,
            0,
            -1,
        ):

            radius = (
                120
                +
                index
                *
                7
                +
                pulse_amount
                *
                0.4
            )

            aura_color = blend(
                "#05090f",
                color,
                0.035
                +
                index
                *
                0.012,
            )

            canvas.create_oval(
                CENTER - radius,
                CENTER - radius,
                CENTER + radius,
                CENTER + radius,
                outline=aura_color,
                width=2,
            )


        # ====================================================
        # ORBIT 1
        # ====================================================

        radius = (
            145
            +
            pulse_amount
            *
            0.25
        )

        canvas.create_arc(
            CENTER - radius,
            CENTER - radius * 0.58,
            CENTER + radius,
            CENTER + radius * 0.58,
            start=rotation,
            extent=118,
            style=tk.ARC,
            outline=blend(
                color,
                "#ffffff",
                0.10,
            ),
            width=3,
        )

        canvas.create_arc(
            CENTER - radius,
            CENTER - radius * 0.58,
            CENTER + radius,
            CENTER + radius * 0.58,
            start=rotation + 180,
            extent=75,
            style=tk.ARC,
            outline=blend(
                "#05090f",
                color,
                0.75,
            ),
            width=2,
        )


        # ====================================================
        # ORBIT 2
        # ====================================================

        radius_2 = (
            123
            +
            pulse_amount
            *
            0.18
        )

        canvas.create_arc(
            CENTER - radius_2 * 0.72,
            CENTER - radius_2,
            CENTER + radius_2 * 0.72,
            CENTER + radius_2,
            start=-rotation * 1.25,
            extent=110,
            style=tk.ARC,
            outline=blend(
                color,
                "#ffffff",
                0.22,
            ),
            width=3,
        )

        canvas.create_arc(
            CENTER - radius_2 * 0.72,
            CENTER - radius_2,
            CENTER + radius_2 * 0.72,
            CENTER + radius_2,
            start=-rotation * 1.25 + 180,
            extent=70,
            style=tk.ARC,
            outline=blend(
                "#05090f",
                color,
                0.80,
            ),
            width=2,
        )


        # ====================================================
        # EQUATOR
        # ====================================================

        equator = (
            105
            +
            pulse_amount
            *
            0.30
        )

        canvas.create_oval(
            CENTER - equator,
            CENTER - equator * 0.28,
            CENTER + equator,
            CENTER + equator * 0.28,
            outline=blend(
                color,
                "#ffffff",
                0.18,
            ),
            width=2,
        )


        # ====================================================
        # PARTICLES
        # ====================================================

        for index in range(8):

            angle = math.radians(
                rotation
                *
                (
                    1
                    if index % 2 == 0
                    else -1
                )
                +
                index
                *
                45
            )

            particle_radius = (
                128
                +
                7
                *
                math.sin(
                    elapsed
                    *
                    1.7
                    +
                    index
                )
            )

            x = (
                CENTER
                +
                math.cos(
                    angle
                )
                *
                particle_radius
            )

            y = (
                CENTER
                +
                math.sin(
                    angle
                )
                *
                particle_radius
                *
                0.65
            )

            dot = (
                2
                +
                index % 3
            )

            canvas.create_oval(
                x - dot,
                y - dot,
                x + dot,
                y + dot,
                fill=blend(
                    color,
                    "#ffffff",
                    0.35,
                ),
                outline="",
            )


        # ====================================================
        # ENERGY SHELL
        # ====================================================

        shell_radius = (
            82
            +
            pulse_amount
        )

        for index in range(
            9,
            0,
            -1,
        ):

            radius = (
                shell_radius
                +
                index
                *
                2.6
            )

            shell_color = blend(
                "#05090f",
                color,
                0.10
                +
                index
                *
                0.045,
            )

            canvas.create_oval(
                CENTER - radius,
                CENTER - radius,
                CENTER + radius,
                CENTER + radius,
                outline=shell_color,
                width=2,
            )


        # ====================================================
        # CORE
        # ====================================================

        core_radius = (
            63
            +
            pulse_amount
            *
            0.55
        )

        layers = 22

        for index in range(
            layers,
            0,
            -1,
        ):

            ratio = (
                index
                /
                layers
            )

            radius = (
                core_radius
                *
                ratio
            )

            core_color = blend(
                color,
                "#ffffff",
                (
                    1.0
                    -
                    ratio
                )
                *
                0.82,
            )

            canvas.create_oval(
                CENTER - radius,
                CENTER - radius,
                CENTER + radius,
                CENTER + radius,
                fill=core_color,
                outline="",
            )


        # ====================================================
        # INNER CORE
        # ====================================================

        inner = (
            20
            +
            pulse_amount
            *
            0.18
        )

        canvas.create_oval(
            CENTER - inner,
            CENTER - inner,
            CENTER + inner,
            CENTER + inner,
            fill="#f5feff",
            outline="",
        )

        canvas.create_oval(
            CENTER - 8,
            CENTER - 8,
            CENTER + 8,
            CENTER + 8,
            fill="#ffffff",
            outline="",
        )


        # ====================================================
        # TEXT
        # ====================================================

        canvas.create_text(
            CENTER,
            WINDOW_SIZE - 55,
            text=(
                "SENTINEL // "
                +
                profile[
                    "label"
                ]
            ),
            fill=blend(
                color,
                "#ffffff",
                0.25,
            ),
            font=(
                "DejaVu Sans Mono",
                11,
                "bold",
            ),
        )

        canvas.create_text(
            CENTER,
            WINDOW_SIZE - 32,
            text=(
                "PHOENIX CORE"
            ),
            fill=blend(
                "#05090f",
                color,
                0.65,
            ),
            font=(
                "DejaVu Sans Mono",
                8,
            ),
        )


    # ========================================================
    # EVENT LOOP
    # ========================================================

    def run(self):

        if self._running:
            return

        self._running = True

        self._create_window()

        try:

            self.root.mainloop()

        finally:

            self._running = False


# ============================================================
# STANDALONE TEST
# ============================================================

def run_test():

    orb = SentinelOrb()

    orb.show()

    orb.set_state(
        "LISTENING"
    )

    print(
        "SENTINEL ORB V2.1 PREMIUM TRANSITION TEST"
    )

    print(
        "ESC or double-click to close."
    )

    orb.run()


if __name__ == "__main__":

    run_test()
