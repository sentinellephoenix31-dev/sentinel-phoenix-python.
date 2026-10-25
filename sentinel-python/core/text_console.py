import sys
import threading

from PySide6.QtCore import (
    QObject,
    Qt,
    Signal
)

from PySide6.QtGui import (
    QFont
)

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget
)

from core.command_dispatcher import (
    CommandDispatcher
)


# ============================================================
# SENTINEL PHOENIX
# MINI TEXT CONSOLE V1
#
# Compact graphical command bar.
#
# No terminal required for normal use.
#
#        USER TEXT
#            ↓
#     Command Dispatcher
#            ↓
# Evidence / Guest / Replay / Brain
# ============================================================


TEXT_CONSOLE_VERSION = "1.0"


# ============================================================
# WORKER SIGNALS
# ============================================================

class WorkerSignals(
    QObject
):

    completed = Signal(
        object
    )

    failed = Signal(
        str
    )


# ============================================================
# SENTINEL MINI BAR
# ============================================================

class SentinelTextBar(
    QWidget
):

    def __init__(
        self
    ):

        super().__init__()


        self.dispatcher = (
            CommandDispatcher()
        )


        self.signals = (
            WorkerSignals()
        )


        self.signals.completed.connect(
            self.on_result
        )


        self.signals.failed.connect(
            self.on_error
        )


        self.busy = False


        self.build_ui()


    # ========================================================
    # UI
    # ========================================================

    def build_ui(
        self
    ):

        self.setWindowTitle(
            "Sentinel Phoenix"
        )


        self.setWindowFlags(
            self.windowFlags()
            |
            Qt.WindowStaysOnTopHint
        )


        self.setMinimumWidth(
            620
        )


        self.setMaximumWidth(
            760
        )


        self.setFixedHeight(
            112
        )


        self.setStyleSheet(
            """
            QWidget {
                background-color: #07110c;
                color: #8cffb5;
                font-family: Sans Serif;
            }

            QLineEdit {
                background-color: white;
                color: #101010;
                border: 2px solid #28d17c;
                border-radius: 10px;
                padding-left: 14px;
                padding-right: 14px;
                min-height: 38px;
                font-size: 15px;
            }

            QLineEdit:focus {
                border: 2px solid #74ffad;
            }

            QPushButton {
                background-color: #0b2417;
                color: #7dffae;
                border: 1px solid #28d17c;
                border-radius: 10px;
                min-width: 52px;
                min-height: 38px;
                font-size: 18px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #123b25;
            }

            QPushButton:disabled {
                color: #4d6b58;
                border-color: #294737;
            }

            QLabel {
                color: #77d99b;
                background: transparent;
                padding-left: 4px;
                font-size: 12px;
            }
            """
        )


        main_layout = QVBoxLayout(
            self
        )


        main_layout.setContentsMargins(
            12,
            10,
            12,
            8
        )


        main_layout.setSpacing(
            5
        )


        command_layout = QHBoxLayout()


        command_layout.setSpacing(
            8
        )


        self.input = QLineEdit()


        self.input.setPlaceholderText(
            "Ask Sentinel..."
        )


        self.input.setClearButtonEnabled(
            True
        )


        self.input.returnPressed.connect(
            self.submit
        )


        self.send_button = QPushButton(
            "➤"
        )


        self.send_button.setToolTip(
            "Send command"
        )


        self.send_button.clicked.connect(
            self.submit
        )


        command_layout.addWidget(
            self.input,
            1
        )


        command_layout.addWidget(
            self.send_button
        )


        self.status = QLabel(
            "SENTINEL // READY"
        )


        status_font = QFont()

        status_font.setPointSize(
            9
        )


        self.status.setFont(
            status_font
        )


        main_layout.addLayout(
            command_layout
        )


        main_layout.addWidget(
            self.status
        )


        self.input.setFocus()


    # ========================================================
    # SUBMIT
    # ========================================================

    def submit(
        self
    ):

        if self.busy:
            return


        command = self.input.text().strip()


        if not command:

            self.status.setText(
                "SENTINEL // ENTER A COMMAND"
            )

            return


        self.busy = True


        self.input.setEnabled(
            False
        )


        self.send_button.setEnabled(
            False
        )


        self.status.setText(
            "SENTINEL // PROCESSING..."
        )


        print("")

        print(
            "TEXT USER >",
            command
        )


        thread = threading.Thread(
            target=self.command_worker,
            args=(
                command,
            ),
            daemon=True,
            name="SentinelTextCommand"
        )


        thread.start()


    # ========================================================
    # BACKGROUND COMMAND
    # ========================================================

    def command_worker(
        self,
        command
    ):

        try:

            result = (
                self.dispatcher.dispatch(
                    command,
                    source="text"
                )
            )


            self.signals.completed.emit(
                result
            )


        except Exception as error:

            self.signals.failed.emit(
                str(
                    error
                )
            )


    # ========================================================
    # RESULT
    # ========================================================

    def on_result(
        self,
        result
    ):

        self.busy = False


        self.input.setEnabled(
            True
        )


        self.send_button.setEnabled(
            True
        )


        route = str(
            result.get(
                "route",
                "UNKNOWN"
            )
        )


        status = str(
            result.get(
                "status",
                "UNKNOWN"
            )
        )


        response = str(
            result.get(
                "response",
                ""
            )
        ).strip()


        print(
            "[TEXT ROUTE]",
            route
        )


        print(
            "[TEXT STATUS]",
            status
        )


        if response:

            print(
                "SENTINEL >",
                response
            )


        # ====================================================
        # Compact response shown under the input bar.
        # ====================================================

        if response:

            compact = " ".join(
                response.split()
            )


            if len(
                compact
            ) > 150:

                compact = (
                    compact[:147]
                    +
                    "..."
                )


            self.status.setText(
                "SENTINEL // "
                +
                compact
            )


            self.status.setToolTip(
                response
            )


        else:

            self.status.setText(
                "SENTINEL // "
                +
                route
                +
                " // "
                +
                status
            )


        self.input.clear()


        self.input.setFocus()


    # ========================================================
    # ERROR
    # ========================================================

    def on_error(
        self,
        error
    ):

        self.busy = False


        self.input.setEnabled(
            True
        )


        self.send_button.setEnabled(
            True
        )


        self.status.setText(
            "SENTINEL // ERROR"
        )


        self.status.setToolTip(
            error
        )


        print(
            "[TEXT CONSOLE ERROR]",
            error
        )


        self.input.setFocus()


# ============================================================
# RUN
# ============================================================

def run():

    app = (
        QApplication.instance()
    )


    owns_application = (
        app is None
    )


    if app is None:

        app = QApplication(
            sys.argv
        )


    app.setApplicationName(
        "Sentinel Phoenix"
    )


    window = SentinelTextBar()


    window.show()


    window.raise_()


    window.activateWindow()


    if owns_application:

        return app.exec()


    return 0


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    dispatcher_ok = False


    try:

        dispatcher = (
            CommandDispatcher()
        )

        dispatcher_ok = (
            dispatcher is not None
        )

    except Exception:

        dispatcher_ok = False


    return {
        "status":
            (
                "PASS"
                if dispatcher_ok
                else
                "FAIL"
            ),

        "version":
            TEXT_CONSOLE_VERSION,

        "dispatcher":
            dispatcher_ok,

        "compact_window":
            True,

        "keyboard_enter":
            True,

        "send_button":
            True,

        "always_on_top":
            True,

        "routes": [
            "EVIDENCE_CONTROL",
            "GUEST_ENROLLMENT",
            "VISUAL_INCIDENT_REPLAY",
            "BRAIN"
        ],

        "security": {
            "shell_execution":
                False,

            "typed_text_is_shell":
                False,

            "payload_execution":
                False
        }
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        run()
    )