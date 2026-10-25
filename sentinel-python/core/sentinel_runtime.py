import os
import subprocess
import sys
import threading
import time
from collections import deque

import fcntl

from core.evidence_bridge import (
    start_background,
    stop_background,
    self_test as evidence_bridge_self_test,
)

from core.wake_word import (
    run as run_wake_word,
    self_test as wake_word_self_test,
)

from core.text_console import (
    self_test as text_console_self_test,
)

from core.command_dispatcher import (
    self_test as dispatcher_self_test,
)


# ============================================================
# SENTINEL PHOENIX
# MAIN RUNTIME V2.2
#
# FIXES:
#
# 1. SINGLE RUNTIME INSTANCE
#
#    Even if Sentinel is already running from autostart,
#    launching:
#
#        python -m core.sentinel_runtime
#
#    will NOT create a second Runtime.
#
#
# 2. TEXT CONSOLE BEHAVIOR
#
#    Normal close / return code 0:
#        → user closed the bar intentionally
#        → DO NOT restart it
#
#    Abnormal crash / non-zero return code:
#        → Supervisor detects crash
#        → automatic recovery
#
#
# Result:
#
#       ONE SENTINEL
#            |
#       ONE TEXT BAR
#            |
#     normal close = closed
#     real crash   = recovered
# ============================================================


RUNTIME_VERSION = "2.2"


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

TEXT_CONSOLE_LOG = os.path.join(
    DATA_DIR,
    "text_console.log"
)

CACHE_DIR = os.path.join(
    os.path.expanduser("~"),
    ".cache"
)

RUNTIME_LOCK_FILE = os.path.join(
    CACHE_DIR,
    "sentinel-phoenix-runtime.lock"
)


# ============================================================
# SUPERVISOR CONFIG
# ============================================================

TEXT_CHECK_INTERVAL = 1.5

TEXT_STARTUP_GRACE = 1.0

TEXT_STABLE_RUNTIME = 10.0

TEXT_RESTART_WINDOW = 60.0

TEXT_MAX_RESTARTS_IN_WINDOW = 5

TEXT_MAX_BACKOFF = 15.0

TEXT_CIRCUIT_BREAKER_DELAY = 20.0


# ============================================================
# LOG
# ============================================================

def runtime_log(
    *parts
):

    print(
        *parts,
        flush=True
    )


# ============================================================
# STORAGE
# ============================================================

def ensure_runtime_storage():

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    os.makedirs(
        CACHE_DIR,
        exist_ok=True
    )


# ============================================================
# RUNTIME SINGLETON LOCK
# ============================================================

def acquire_runtime_lock():

    ensure_runtime_storage()

    handle = open(
        RUNTIME_LOCK_FILE,
        "a+",
        encoding="utf-8"
    )


    try:

        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_EX
            |
            fcntl.LOCK_NB
        )


    except BlockingIOError:

        handle.close()

        return None


    try:

        handle.seek(
            0
        )

        handle.truncate()

        handle.write(
            str(
                os.getpid()
            )
        )

        handle.flush()

    except OSError:

        pass


    return handle


def release_runtime_lock(
    handle
):

    if handle is None:

        return


    try:

        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_UN
        )

    except OSError:

        pass


    try:

        handle.close()

    except OSError:

        pass


# ============================================================
# TEXT CONSOLE LOG
# ============================================================

def read_text_console_log_tail(
    maximum_lines=12
):

    if not os.path.isfile(
        TEXT_CONSOLE_LOG
    ):

        return []


    try:

        with open(
            TEXT_CONSOLE_LOG,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as handle:

            lines = handle.readlines()


        return [
            line.rstrip()
            for line in lines[
                -maximum_lines:
            ]
        ]


    except OSError:

        return []


# ============================================================
# START TEXT CONSOLE
# ============================================================

def start_text_console():

    ensure_runtime_storage()


    runtime_log(
        "[RUNTIME] Starting Sentinel Text Console..."
    )


    command = [
        sys.executable,
        "-u",
        "-m",
        "core.text_console",
    ]


    environment = os.environ.copy()

    environment[
        "PYTHONUNBUFFERED"
    ] = "1"


    try:

        log_handle = open(
            TEXT_CONSOLE_LOG,
            "a",
            encoding="utf-8",
            buffering=1
        )


    except OSError as error:

        runtime_log(
            "[RUNTIME] Cannot open Text Console log:",
            str(error)
        )

        return None


    try:

        log_handle.write(
            "\n"
        )

        log_handle.write(
            "=" * 72
            +
            "\n"
        )

        log_handle.write(
            "[TEXT CONSOLE START] "
            +
            time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            +
            "\n"
        )

        log_handle.write(
            "=" * 72
            +
            "\n"
        )


        process = subprocess.Popen(
            command,
            cwd=BASE_DIR,
            env=environment,
            shell=False,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


    except Exception as error:

        log_handle.close()

        runtime_log(
            "[RUNTIME] Text Console failed to start:",
            str(error)
        )

        return None


    log_handle.close()


    time.sleep(
        TEXT_STARTUP_GRACE
    )


    if process.poll() is not None:

        runtime_log(
            "[RUNTIME] Text Console exited during startup."
        )

        runtime_log(
            "[RUNTIME] Return code:",
            process.returncode
        )

        return None


    runtime_log(
        "[RUNTIME] Text Console: ONLINE"
    )

    runtime_log(
        "[RUNTIME] Text Console PID:",
        process.pid
    )


    return process


# ============================================================
# STOP TEXT CONSOLE
# ============================================================

def stop_text_console(
    process
):

    if process is None:

        return


    if process.poll() is not None:

        return


    runtime_log(
        "[RUNTIME] Stopping Text Console..."
    )


    try:

        process.terminate()


        try:

            process.wait(
                timeout=3.0
            )


        except subprocess.TimeoutExpired:

            runtime_log(
                "[RUNTIME] Forcing Text Console shutdown..."
            )

            process.kill()

            process.wait(
                timeout=2.0
            )


    except Exception as error:

        runtime_log(
            "[RUNTIME] Text Console shutdown warning:",
            str(error)
        )


# ============================================================
# TEXT CONSOLE SUPERVISOR
# ============================================================

class TextConsoleSupervisor:

    def __init__(
        self
    ):

        self._lock = (
            threading.RLock()
        )

        self._stop_event = (
            threading.Event()
        )

        self._monitor_thread = None

        self._process = None

        self._last_start = 0.0

        self._restart_times = deque()

        self._consecutive_failures = 0

        self._total_restarts = 0


        # True:
        # Sentinel should have a text bar.
        #
        # False:
        # User intentionally closed it.

        self._desired_running = True


    # ========================================================
    # STATUS
    # ========================================================

    def is_running(
        self
    ):

        with self._lock:

            return (
                self._process is not None
                and
                self._process.poll() is None
            )


    def pid(
        self
    ):

        with self._lock:

            if (
                self._process is None
                or
                self._process.poll()
                is not None
            ):

                return None


            return self._process.pid


    def status(
        self
    ):

        return {
            "running":
                self.is_running(),

            "pid":
                self.pid(),

            "desired_running":
                self._desired_running,

            "total_restarts":
                self._total_restarts,

            "consecutive_failures":
                self._consecutive_failures,

            "log":
                TEXT_CONSOLE_LOG,
        }


    # ========================================================
    # LAUNCH
    # ========================================================

    def _launch(
        self,
        restart=False
    ):

        if self._stop_event.is_set():

            return False


        if not self._desired_running:

            return False


        # Do not create a second console for this Runtime.

        with self._lock:

            if (
                self._process is not None
                and
                self._process.poll() is None
            ):

                return True


        process = start_text_console()


        with self._lock:

            self._process = process


            if process is not None:

                self._last_start = (
                    time.monotonic()
                )


        if process is None:

            return False


        if restart:

            self._total_restarts += 1


            runtime_log(
                "[SUPERVISOR] Text Console recovered."
            )

            runtime_log(
                "[SUPERVISOR] New PID:",
                process.pid
            )


        return True


    # ========================================================
    # RESTART TRACKING
    # ========================================================

    def _record_restart_attempt(
        self
    ):

        now = time.monotonic()


        while (
            self._restart_times
            and
            now
            -
            self._restart_times[
                0
            ]
            >
            TEXT_RESTART_WINDOW
        ):

            self._restart_times.popleft()


        self._restart_times.append(
            now
        )


        return len(
            self._restart_times
        )


    # ========================================================
    # BACKOFF
    # ========================================================

    def _backoff_delay(
        self
    ):

        if self._consecutive_failures <= 0:

            return 0.5


        return float(
            min(
                TEXT_MAX_BACKOFF,
                2
                **
                (
                    self._consecutive_failures
                    -
                    1
                )
            )
        )


    # ========================================================
    # CLEAN USER CLOSE
    # ========================================================

    def _handle_normal_close(
        self
    ):

        with self._lock:

            self._process = None

            self._desired_running = False


        self._consecutive_failures = 0


        runtime_log(
            ""
        )

        runtime_log(
            "[SUPERVISOR] Text Console closed normally."
        )

        runtime_log(
            "[SUPERVISOR] User close detected."
        )

        runtime_log(
            "[SUPERVISOR] Text Console will NOT be restarted."
        )


    # ========================================================
    # ABNORMAL CRASH
    # ========================================================

    def _handle_crash(
        self,
        return_code
    ):

        if not self._desired_running:

            return


        now = time.monotonic()


        with self._lock:

            runtime = (
                now
                -
                self._last_start
                if self._last_start
                else
                0.0
            )

            self._process = None


        runtime_log(
            ""
        )

        runtime_log(
            "[SUPERVISOR] Text Console CRASH detected."
        )

        runtime_log(
            "[SUPERVISOR] Return code:",
            return_code
        )

        runtime_log(
            "[SUPERVISOR] Previous runtime:",
            f"{runtime:.2f}s"
        )


        if runtime >= TEXT_STABLE_RUNTIME:

            self._consecutive_failures = 0

        else:

            self._consecutive_failures += 1


        tail = read_text_console_log_tail()


        if tail:

            runtime_log(
                "[SUPERVISOR] Text Console log tail:"
            )


            for line in tail:

                runtime_log(
                    "   ",
                    line
                )


        restart_count = (
            self._record_restart_attempt()
        )


        if (
            restart_count
            >
            TEXT_MAX_RESTARTS_IN_WINDOW
        ):

            runtime_log(
                "[SUPERVISOR WARNING] "
                "Too many Text Console crashes."
            )

            runtime_log(
                "[SUPERVISOR] Cooling down for",
                TEXT_CIRCUIT_BREAKER_DELAY,
                "seconds."
            )


            if self._stop_event.wait(
                TEXT_CIRCUIT_BREAKER_DELAY
            ):

                return


            self._restart_times.clear()

            self._consecutive_failures = 0


        delay = (
            self._backoff_delay()
        )


        runtime_log(
            "[SUPERVISOR] Restarting crashed Text Console in",
            f"{delay:.1f}s..."
        )


        if self._stop_event.wait(
            delay
        ):

            return


        if not self._desired_running:

            return


        success = self._launch(
            restart=True
        )


        if not success:

            runtime_log(
                "[SUPERVISOR WARNING] "
                "Text Console recovery failed."
            )


    # ========================================================
    # WATCHDOG
    # ========================================================

    def _monitor_loop(
        self
    ):

        runtime_log(
            "[SUPERVISOR] Text Console watchdog: ONLINE"
        )


        while not self._stop_event.wait(
            TEXT_CHECK_INTERVAL
        ):

            with self._lock:

                process = self._process

                desired = (
                    self._desired_running
                )


            # User intentionally closed it.

            if not desired:

                continue


            # Initial launch failed.
            # Supervisor can still try recovery.

            if process is None:

                self._consecutive_failures += 1


                delay = self._backoff_delay()


                runtime_log(
                    "[SUPERVISOR] Text Console unavailable."
                )

                runtime_log(
                    "[SUPERVISOR] Recovery attempt in",
                    f"{delay:.1f}s..."
                )


                if self._stop_event.wait(
                    delay
                ):

                    break


                self._launch(
                    restart=True
                )

                continue


            return_code = process.poll()


            if return_code is None:

                continue


            # =================================================
            # IMPORTANT:
            #
            # 0 = normal Qt window close.
            #
            # Do not reopen it.
            # =================================================

            if return_code == 0:

                self._handle_normal_close()

                continue


            # Non-zero = abnormal failure.

            self._handle_crash(
                return_code
            )


        runtime_log(
            "[SUPERVISOR] Text Console watchdog: OFFLINE"
        )


    # ========================================================
    # START
    # ========================================================

    def start(
        self
    ):

        if (
            self._monitor_thread is not None
            and
            self._monitor_thread.is_alive()
        ):

            return self.status()


        self._stop_event.clear()

        self._desired_running = True


        initial_started = self._launch(
            restart=False
        )


        if not initial_started:

            runtime_log(
                "[RUNTIME WARNING] "
                "Initial Text Console startup failed."
            )

            runtime_log(
                "[RUNTIME WARNING] "
                "Supervisor will attempt recovery."
            )


        self._monitor_thread = (
            threading.Thread(
                target=self._monitor_loop,
                name="sentinel-text-supervisor",
                daemon=True
            )
        )


        self._monitor_thread.start()


        return self.status()


    # ========================================================
    # STOP
    # ========================================================

    def stop(
        self
    ):

        runtime_log(
            "[SUPERVISOR] Stopping Text Console supervisor..."
        )


        self._desired_running = False

        self._stop_event.set()


        with self._lock:

            process = self._process

            self._process = None


        stop_text_console(
            process
        )


        if (
            self._monitor_thread is not None
            and
            self._monitor_thread.is_alive()
        ):

            self._monitor_thread.join(
                timeout=3.0
            )


        runtime_log(
            "[SUPERVISOR] Text Console supervisor stopped."
        )


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    try:

        evidence = (
            evidence_bridge_self_test()
        )

    except Exception as error:

        evidence = {
            "status":
                "FAIL",

            "reason":
                str(error)
        }


    try:

        wake = (
            wake_word_self_test()
        )

    except Exception as error:

        wake = {
            "status":
                "FAIL",

            "reason":
                str(error)
        }


    try:

        dispatcher = (
            dispatcher_self_test()
        )

    except Exception as error:

        dispatcher = {
            "status":
                "FAIL",

            "reason":
                str(error)
        }


    try:

        text_console = (
            text_console_self_test()
        )

    except Exception as error:

        text_console = {
            "status":
                "FAIL",

            "reason":
                str(error)
        }


    passed = all(
        (
            evidence.get(
                "status"
            )
            ==
            "PASS",

            wake.get(
                "status"
            )
            ==
            "PASS",

            dispatcher.get(
                "status"
            )
            ==
            "PASS",

            text_console.get(
                "status"
            )
            ==
            "PASS",
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

        "runtime_version":
            RUNTIME_VERSION,

        "components": {
            "wake_word":
                wake,

            "evidence_bridge":
                evidence,

            "command_dispatcher":
                dispatcher,

            "text_console":
                text_console,
        },

        "process_control": {
            "single_runtime_instance":
                True,

            "runtime_lock":
                RUNTIME_LOCK_FILE,

            "single_text_console_per_runtime":
                True,
        },

        "text_console_policy": {
            "normal_close_restarts":
                False,

            "abnormal_crash_restarts":
                True,

            "watchdog":
                True,

            "backoff":
                True,

            "circuit_breaker":
                True,
        },

        "interfaces": {
            "voice":
                True,

            "text":
                True,

            "wake_word":
                True,

            "orb":
                True,

            "visual_incident_replay":
                True,
        },

        "safety": {
            "text_is_not_shell":
                True,

            "shell_execution":
                False,

            "payload_execution":
                False,
        },
    }


# ============================================================
# MAIN RUNTIME
# ============================================================

def run():

    runtime_lock = (
        acquire_runtime_lock()
    )


    # ========================================================
    # DUPLICATE RUNTIME PROTECTION
    # ========================================================

    if runtime_lock is None:

        runtime_log(
            "=" * 72
        )

        runtime_log(
            "SENTINEL PHOENIX"
        )

        runtime_log(
            "[RUNTIME] Sentinel is already running."
        )

        runtime_log(
            "[RUNTIME] Second instance blocked."
        )

        runtime_log(
            "=" * 72
        )


        return 0


    evidence_thread = None

    text_supervisor = None


    runtime_log(
        "=" * 72
    )

    runtime_log(
        "SENTINEL PHOENIX"
    )

    runtime_log(
        "MAIN RUNTIME V2.2"
    )

    runtime_log(
        "SINGLE INSTANCE + "
        "VOICE + TEXT + EVIDENCE + IDENTITY + REPLAY"
    )

    runtime_log(
        "=" * 72
    )


    try:

        # ====================================================
        # EVIDENCE
        # ====================================================

        runtime_log(
            ""
        )

        runtime_log(
            "[RUNTIME] Starting Evidence Lifecycle..."
        )


        evidence_thread = (
            start_background()
        )


        time.sleep(
            0.5
        )


        runtime_log(
            "[RUNTIME] Evidence Lifecycle: ONLINE"
        )


        # ====================================================
        # TEXT
        # ====================================================

        runtime_log(
            ""
        )

        runtime_log(
            "[RUNTIME] Starting Text Console Supervisor..."
        )


        text_supervisor = (
            TextConsoleSupervisor()
        )


        text_status = (
            text_supervisor.start()
        )


        runtime_log(
            "[RUNTIME] Text Supervisor: ONLINE"
        )


        runtime_log(
            "[RUNTIME] Text Console:",
            (
                "ONLINE"
                if text_status.get(
                    "running"
                )
                else
                "RECOVERY MODE"
            )
        )


        # ====================================================
        # INTERFACES
        # ====================================================

        runtime_log(
            ""
        )

        runtime_log(
            "=" * 72
        )

        runtime_log(
            "SENTINEL INTERFACES"
        )

        runtime_log(
            "VOICE    : STARTING"
        )

        runtime_log(
            "TEXT     : SUPERVISED"
        )

        runtime_log(
            "EVIDENCE : ONLINE"
        )

        runtime_log(
            "IDENTITY : CENTRAL"
        )

        runtime_log(
            "REPLAY   : READY"
        )

        runtime_log(
            "=" * 72
        )

        runtime_log(
            ""
        )


        # ====================================================
        # MAIN WAKE / ORB LOOP
        # ====================================================

        run_wake_word()


    except KeyboardInterrupt:

        runtime_log(
            ""
        )

        runtime_log(
            "[RUNTIME] Shutdown requested."
        )


    except Exception as error:

        runtime_log(
            ""
        )

        runtime_log(
            "[RUNTIME ERROR]",
            repr(
                error
            )
        )


    finally:

        # ====================================================
        # TEXT
        # ====================================================

        if text_supervisor is not None:

            try:

                text_supervisor.stop()

            except Exception as error:

                runtime_log(
                    "[RUNTIME] Text Supervisor warning:",
                    str(error)
                )


        # ====================================================
        # EVIDENCE
        # ====================================================

        try:

            stop_background()

        except Exception as error:

            runtime_log(
                "[RUNTIME] Evidence shutdown warning:",
                str(error)
            )


        if (
            evidence_thread is not None
            and
            evidence_thread.is_alive()
        ):

            try:

                evidence_thread.join(
                    timeout=2.0
                )

            except Exception:

                pass


        release_runtime_lock(
            runtime_lock
        )


        runtime_log(
            ""
        )

        runtime_log(
            "[RUNTIME] Sentinel stopped."
        )


    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        run()
    )