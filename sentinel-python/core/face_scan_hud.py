# ============================================================
# SENTINEL PHOENIX
# FACE SCAN HUD V2.0
#
# Visual biometric scanner.
# Does NOT perform face recognition itself.
#
# Communication:
# data/hud/face_scan_<session>.json
# ============================================================

import argparse
import json
import math
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QTimer,
    QRectF,
    QPointF,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QBrush,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
)


HUD_VERSION = "2.0"

PROJECT_DIR = Path(__file__).resolve().parent.parent
HUD_DIR = PROJECT_DIR / "data" / "hud"

WINDOW_WIDTH = 620
WINDOW_HEIGHT = 560

POLL_MS = 100
STALE_SECONDS = 15


# ============================================================
# HELPERS
# ============================================================

def clamp(value, minimum, maximum):
    return max(
        minimum,
        min(maximum, value),
    )


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def normalize_similarity(value):
    value = safe_float(value, 0.0)

    if value <= 1.0:
        value *= 100.0

    return clamp(
        value,
        0.0,
        100.0,
    )


def normalize_state(data):
    if not isinstance(data, dict):
        data = {}

    similarity = (
        data.get("similarity")
        if data.get("similarity") is not None
        else data.get("average_similarity")
    )

    match_percent = normalize_similarity(
        similarity
    )

    role = str(
        data.get(
            "role",
            "UNKNOWN",
        )
    ).upper()

    status = str(
        data.get(
            "status",
            "SCANNING",
        )
    ).upper()

    guidance = (
        data.get("guidance")
        or data.get("message")
        or data.get("instruction")
        or ""
    )

    votes = safe_int(
        data.get("votes", 0),
        0,
    )

    required_votes = safe_int(
        data.get(
            "required_votes",
            data.get(
                "votes_required",
                3,
            ),
        ),
        3,
    )

    quality = safe_float(
        data.get(
            "quality",
            data.get(
                "quality_score",
                0.0,
            ),
        ),
        0.0,
    )

    if quality <= 1.0:
        quality *= 100.0

    verified = bool(
        data.get("verified", False)
    )

    authorized = bool(
        data.get(
            "authorized",
            data.get(
                "granted",
                False,
            ),
        )
    )

    access = str(
        data.get(
            "access",
            "",
        )
    ).upper()

    if access == "GRANTED":
        authorized = True

    if status in {
        "VERIFIED",
        "GRANTED",
        "ACCESS_GRANTED",
    }:
        verified = True

    if not guidance:
        if verified and role == "OWNER":
            guidance = "OWNER VERIFIED"
        elif verified:
            guidance = f"{role} VERIFIED"
        elif status in {
            "NO_FACE",
            "FACE_NOT_FOUND",
        }:
            guidance = "CENTER YOUR FACE"
        elif status in {
            "TOO_FAR",
            "FACE_TOO_SMALL",
        }:
            guidance = "MOVE CLOSER"
        elif status in {
            "TOO_CLOSE",
            "FACE_TOO_LARGE",
        }:
            guidance = "MOVE BACK"
        elif status in {
            "LOW_QUALITY",
            "BLURRY",
        }:
            guidance = "HOLD STILL"
        elif status in {
            "LOW_LIGHT",
            "TOO_DARK",
        }:
            guidance = "MORE LIGHT NEEDED"
        elif status in {
            "DENIED",
            "ACCESS_DENIED",
        }:
            guidance = "ACCESS DENIED"
        else:
            guidance = "LOOK AT THE CAMERA"

    return {
        "status": status,
        "role": role,
        "guidance": str(guidance),
        "match_percent": match_percent,
        "votes": votes,
        "required_votes": max(
            1,
            required_votes,
        ),
        "quality": clamp(
            quality,
            0.0,
            100.0,
        ),
        "verified": verified,
        "authorized": authorized,
        "face_box": data.get(
            "face_box",
            data.get("box"),
        ),
        "timestamp": data.get(
            "timestamp",
            time.time(),
        ),
    }


# ============================================================
# HUD WINDOW
# ============================================================

class FaceScanHUD(QWidget):

    def __init__(
        self,
        session_id=None,
        demo=False,
    ):
        super().__init__()

        self.session_id = session_id
        self.demo = demo

        HUD_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.state_file = None

        if session_id:
            self.state_file = (
                HUD_DIR
                / f"face_scan_{session_id}.json"
            )

        self.state = normalize_state({})

        self.scan_position = 0.0
        self.scan_direction = 1

        self.pulse = 0.0

        self.demo_step = 0
        self.demo_started = time.time()

        self.setWindowTitle(
            "Sentinel Phoenix // Face Scan"
        )

        self.setFixedSize(
            WINDOW_WIDTH,
            WINDOW_HEIGHT,
        )

        self.setWindowFlags(
            Qt.Window
            | Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
        )

        self.setAttribute(
            Qt.WA_TranslucentBackground,
            True,
        )

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(
            self.animate
        )
        self.animation_timer.start(30)

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(
            self.read_state
        )
        self.poll_timer.start(POLL_MS)

        if self.demo:
            self.demo_timer = QTimer(self)
            self.demo_timer.timeout.connect(
                self.update_demo
            )
            self.demo_timer.start(1200)

    # ========================================================
    # STATE
    # ========================================================

    def read_state(self):

        if self.demo:
            return

        if self.state_file is None:
            return

        if not self.state_file.exists():
            return

        try:
            data = json.loads(
                self.state_file.read_text(
                    encoding="utf-8"
                )
            )

            self.state = normalize_state(
                data
            )

            self.update()

        except Exception:
            pass

    def update_demo(self):

        sequence = [
            {
                "status": "NO_FACE",
                "guidance": "CENTER YOUR FACE",
                "similarity": 0.0,
                "votes": 0,
            },
            {
                "status": "FACE_TOO_SMALL",
                "guidance": "MOVE CLOSER",
                "similarity": 0.21,
                "votes": 0,
            },
            {
                "status": "SCANNING",
                "guidance": "HOLD STILL",
                "similarity": 0.48,
                "votes": 1,
            },
            {
                "status": "SCANNING",
                "guidance": "MATCHING...",
                "similarity": 0.67,
                "votes": 2,
            },
            {
                "status": "VERIFIED",
                "guidance": "OWNER VERIFIED",
                "similarity": 0.83,
                "votes": 3,
                "role": "OWNER",
                "verified": True,
                "authorized": True,
                "access": "GRANTED",
            },
        ]

        self.state = normalize_state(
            sequence[
                self.demo_step
                % len(sequence)
            ]
        )

        self.demo_step += 1

        self.update()

    # ========================================================
    # ANIMATION
    # ========================================================

    def animate(self):

        self.scan_position += (
            0.018
            * self.scan_direction
        )

        if self.scan_position >= 1.0:
            self.scan_position = 1.0
            self.scan_direction = -1

        elif self.scan_position <= 0.0:
            self.scan_position = 0.0
            self.scan_direction = 1

        self.pulse += 0.08

        self.update()

    # ========================================================
    # PAINT
    # ========================================================

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        # ----------------------------------------------
        # BACKGROUND
        # ----------------------------------------------

        background = QColor(
            5,
            12,
            18,
            235,
        )

        painter.setBrush(
            background
        )

        painter.setPen(
            Qt.NoPen
        )

        painter.drawRoundedRect(
            self.rect(),
            28,
            28,
        )

        # ----------------------------------------------
        # OUTER GLOW
        # ----------------------------------------------

        pulse_alpha = int(
            70
            + 30
            * (
                0.5
                + 0.5
                * math.sin(
                    self.pulse
                )
            )
        )

        painter.setBrush(
            Qt.NoBrush
        )

        painter.setPen(
            QPen(
                QColor(
                    30,
                    255,
                    190,
                    pulse_alpha,
                ),
                2,
            )
        )

        painter.drawRoundedRect(
            QRectF(
                4,
                4,
                WINDOW_WIDTH - 8,
                WINDOW_HEIGHT - 8,
            ),
            26,
            26,
        )

        # ----------------------------------------------
        # TITLE
        # ----------------------------------------------

        painter.setPen(
            QColor(
                155,
                255,
                225,
            )
        )

        painter.setFont(
            QFont(
                "DejaVu Sans",
                15,
                QFont.Bold,
            )
        )

        painter.drawText(
            QRectF(
                30,
                22,
                WINDOW_WIDTH - 60,
                32,
            ),
            Qt.AlignCenter,
            "SENTINEL // BIOMETRIC ACCESS",
        )

        painter.setPen(
            QColor(
                90,
                160,
                150,
            )
        )

        painter.setFont(
            QFont(
                "DejaVu Sans",
                9,
            )
        )

        painter.drawText(
            QRectF(
                30,
                55,
                WINDOW_WIDTH - 60,
                22,
            ),
            Qt.AlignCenter,
            f"FACE SCAN HUD V{HUD_VERSION}",
        )

        # ----------------------------------------------
        # FACE SCANNER FRAME
        # ----------------------------------------------

        scan_rect = QRectF(
            150,
            100,
            320,
            285,
        )

        frame_color = QColor(
            50,
            255,
            190,
            210,
        )

        if self.state["verified"]:
            frame_color = QColor(
                100,
                255,
                150,
                240,
            )

        elif self.state["status"] in {
            "DENIED",
            "ACCESS_DENIED",
        }:
            frame_color = QColor(
                255,
                80,
                80,
                230,
            )

        painter.setBrush(
            QColor(
                5,
                25,
                28,
                120,
            )
        )

        painter.setPen(
            QPen(
                QColor(
                    40,
                    120,
                    115,
                    120,
                ),
                1,
            )
        )

        painter.drawRoundedRect(
            scan_rect,
            24,
            24,
        )

        # corner brackets

        painter.setPen(
            QPen(
                frame_color,
                4,
            )
        )

        corner = 42

        x = scan_rect.x()
        y = scan_rect.y()
        w = scan_rect.width()
        h = scan_rect.height()

        lines = [
            (
                QPointF(x, y + corner),
                QPointF(x, y),
            ),
            (
                QPointF(x, y),
                QPointF(x + corner, y),
            ),

            (
                QPointF(x + w - corner, y),
                QPointF(x + w, y),
            ),
            (
                QPointF(x + w, y),
                QPointF(x + w, y + corner),
            ),

            (
                QPointF(x, y + h - corner),
                QPointF(x, y + h),
            ),
            (
                QPointF(x, y + h),
                QPointF(x + corner, y + h),
            ),

            (
                QPointF(x + w - corner, y + h),
                QPointF(x + w, y + h),
            ),
            (
                QPointF(x + w, y + h),
                QPointF(x + w, y + h - corner),
            ),
        ]

        for p1, p2 in lines:
            painter.drawLine(
                p1,
                p2,
            )

        # ----------------------------------------------
        # FACE OVAL
        # ----------------------------------------------

        oval_rect = QRectF(
            scan_rect.center().x() - 82,
            scan_rect.center().y() - 108,
            164,
            216,
        )

        painter.setPen(
            QPen(
                QColor(
                    80,
                    235,
                    190,
                    105,
                ),
                2,
                Qt.DashLine,
            )
        )

        painter.drawEllipse(
            oval_rect
        )

        # ----------------------------------------------
        # SCAN LINE
        # ----------------------------------------------

        scan_y = (
            scan_rect.top()
            + 18
            + self.scan_position
            * (
                scan_rect.height()
                - 36
            )
        )

        gradient = QLinearGradient(
            scan_rect.left(),
            scan_y,
            scan_rect.right(),
            scan_y,
        )

        gradient.setColorAt(
            0.0,
            QColor(
                40,
                255,
                190,
                0,
            ),
        )

        gradient.setColorAt(
            0.5,
            QColor(
                80,
                255,
                210,
                255,
            ),
        )

        gradient.setColorAt(
            1.0,
            QColor(
                40,
                255,
                190,
                0,
            ),
        )

        painter.setPen(
            QPen(
                QBrush(
                    gradient
                ),
                3,
            )
        )

        painter.drawLine(
            QPointF(
                scan_rect.left() + 10,
                scan_y,
            ),
            QPointF(
                scan_rect.right() - 10,
                scan_y,
            ),
        )

        # ----------------------------------------------
        # GUIDANCE
        # ----------------------------------------------

        painter.setFont(
            QFont(
                "DejaVu Sans",
                16,
                QFont.Bold,
            )
        )

        painter.setPen(
            frame_color
        )

        painter.drawText(
            QRectF(
                40,
                400,
                WINDOW_WIDTH - 80,
                35,
            ),
            Qt.AlignCenter,
            self.state["guidance"],
        )

        # ----------------------------------------------
        # MATCH
        # ----------------------------------------------

        match = self.state[
            "match_percent"
        ]

        painter.setFont(
            QFont(
                "DejaVu Sans",
                12,
                QFont.Bold,
            )
        )

        painter.setPen(
            QColor(
                210,
                255,
                245,
            )
        )

        match_text = (
            f"MATCH {match:.1f}%"
        )

        vote_text = (
            f"VOTES "
            f"{self.state['votes']}"
            f"/"
            f"{self.state['required_votes']}"
        )

        painter.drawText(
            QRectF(
                70,
                447,
                220,
                30,
            ),
            Qt.AlignCenter,
            match_text,
        )

        painter.drawText(
            QRectF(
                330,
                447,
                220,
                30,
            ),
            Qt.AlignCenter,
            vote_text,
        )

        # ----------------------------------------------
        # QUALITY BAR
        # ----------------------------------------------

        bar_rect = QRectF(
            100,
            493,
            420,
            8,
        )

        painter.setBrush(
            QColor(
                35,
                60,
                65,
                180,
            )
        )

        painter.setPen(
            Qt.NoPen
        )

        painter.drawRoundedRect(
            bar_rect,
            4,
            4,
        )

        quality_width = (
            bar_rect.width()
            * self.state["quality"]
            / 100.0
        )

        quality_gradient = (
            QLinearGradient(
                bar_rect.left(),
                bar_rect.top(),
                bar_rect.right(),
                bar_rect.top(),
            )
        )

        quality_gradient.setColorAt(
            0.0,
            QColor(
                30,
                190,
                180,
            ),
        )

        quality_gradient.setColorAt(
            1.0,
            QColor(
                80,
                255,
                190,
            ),
        )

        painter.setBrush(
            quality_gradient
        )

        painter.drawRoundedRect(
            QRectF(
                bar_rect.left(),
                bar_rect.top(),
                quality_width,
                bar_rect.height(),
            ),
            4,
            4,
        )

        painter.setFont(
            QFont(
                "DejaVu Sans",
                8,
            )
        )

        painter.setPen(
            QColor(
                110,
                170,
                165,
            )
        )

        painter.drawText(
            QRectF(
                100,
                507,
                420,
                20,
            ),
            Qt.AlignCenter,
            (
                "SIGNAL QUALITY "
                f"{self.state['quality']:.0f}%"
            ),
        )

        # ----------------------------------------------
        # VERIFIED ACCESS
        # ----------------------------------------------

        if (
            self.state["verified"]
            and
            self.state["authorized"]
        ):

            painter.setFont(
                QFont(
                    "DejaVu Sans",
                    10,
                    QFont.Bold,
                )
            )

            painter.setPen(
                QColor(
                    100,
                    255,
                    160,
                )
            )

            painter.drawText(
                QRectF(
                    30,
                    530,
                    WINDOW_WIDTH - 60,
                    20,
                ),
                Qt.AlignCenter,
                "ACCESS GRANTED // OWNER",
            )

        elif self.state["status"] in {
            "DENIED",
            "ACCESS_DENIED",
        }:

            painter.setFont(
                QFont(
                    "DejaVu Sans",
                    10,
                    QFont.Bold,
                )
            )

            painter.setPen(
                QColor(
                    255,
                    100,
                    100,
                )
            )

            painter.drawText(
                QRectF(
                    30,
                    530,
                    WINDOW_WIDTH - 60,
                    20,
                ),
                Qt.AlignCenter,
                "ACCESS DENIED",
            )

        painter.end()


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--session",
        type=str,
        default=None,
    )

    parser.add_argument(
        "--demo",
        action="store_true",
    )

    parser.add_argument(
        "--self-test",
        action="store_true",
    )

    args = parser.parse_args()

    if args.self_test:

        HUD_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        print(
            {
                "status": "PASS",
                "version": HUD_VERSION,
                "hud_dir": str(HUD_DIR),
                "pyside6": True,
                "camera_access": False,
                "face_recognition": False,
            }
        )

        return 0

    app = QApplication(
        sys.argv
    )

    hud = FaceScanHUD(
        session_id=args.session,
        demo=args.demo,
    )

    hud.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
