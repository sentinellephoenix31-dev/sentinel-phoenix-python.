# ============================================================
# SENTINEL PHOENIX
# UNIFIED LAUNCHER V1.0
#
# Starts:
#   1. Honeypot service
#   2. Sentinel Runtime
#
# One launcher = one Sentinel.
# ============================================================

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


LAUNCHER_VERSION = "1.0"

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

HONEYPOT_HOST = "0.0.0.0"
HONEYPOT_PORT = 2222

HONEYPOT_START_TIMEOUT = 12.0
HONEYPOT_RESTART_DELAY = 2.0

running = True

honeypot_process = None
runtime_process = None


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(
        f"[LAUNCHER] {message}",
        flush=True,
    )


# ============================================================
# PORT CHECK
# ============================================================

def port_is_open(
    host=HONEYPOT_HOST,
    port=HONEYPOT_PORT,
):
    try:
        with socket.create_connection(
            (host, port),
            timeout=0.5,
        ):
            return True

    except OSError:
        return False


def wait_for_honeypot():
    deadline = time.time() + HONEYPOT_START_TIMEOUT

    while time.time() < deadline:

        if not running:
            return False

        if honeypot_process is not None:
            if honeypot_process.poll() is not None:
                return False

        if port_is_open():
            return True

        time.sleep(0.25)

    return False


# ============================================================
# PROCESS HELPERS
# ============================================================

def terminate_process(
    process,
    name,
    timeout=6,
):
    if process is None:
        return

    if process.poll() is not None:
        return

    log(
        f"Stopping {name}..."
    )

    try:
        os.killpg(
            os.getpgid(process.pid),
            signal.SIGINT,
        )

        process.wait(
            timeout=timeout
        )

        log(
            f"{name} stopped."
        )

        return

    except subprocess.TimeoutExpired:
        pass

    except ProcessLookupError:
        return

    except Exception as error:
        log(
            f"{name} graceful stop warning: {error}"
        )

    try:
        os.killpg(
            os.getpgid(process.pid),
            signal.SIGTERM,
        )

        process.wait(
            timeout=3
        )

    except Exception:
        pass


# ============================================================
# HONEYPOT
# ============================================================

def start_honeypot():
    global honeypot_process

    if port_is_open():

        log(
            f"Honeypot already listening on "
            f"{HONEYPOT_HOST}:{HONEYPOT_PORT}"
        )

        return None

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_path = (
        DATA_DIR /
        "honeypot_service.log"
    )

    log_handle = open(
        log_path,
        "a",
        encoding="utf-8",
        buffering=1,
    )

    log(
        "Starting Honeypot Service..."
    )

    honeypot_process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "core.honeypot_service",
        ],
        cwd=str(PROJECT_DIR),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    if wait_for_honeypot():

        log(
            f"Honeypot ONLINE "
            f"({HONEYPOT_HOST}:{HONEYPOT_PORT})"
        )

        return honeypot_process

    log(
        "Honeypot failed to become ready."
    )

    return honeypot_process


# ============================================================
# SENTINEL RUNTIME
# ============================================================

def start_runtime():
    global runtime_process

    log(
        "Starting Sentinel Runtime..."
    )

    runtime_process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "core.sentinel_runtime",
        ],
        cwd=str(PROJECT_DIR),
        start_new_session=True,
    )

    return runtime_process


# ============================================================
# SHUTDOWN
# ============================================================

def shutdown():
    global running

    if not running:
        return

    running = False

    print()

    log(
        "Shutdown requested."
    )

    terminate_process(
        runtime_process,
        "Sentinel Runtime",
    )

    terminate_process(
        honeypot_process,
        "Honeypot Service",
    )

    log(
        "Sentinel Phoenix stopped."
    )


def signal_handler(
    signum,
    frame,
):
    shutdown()


# ============================================================
# SUPERVISION
# ============================================================

def supervise():
    global honeypot_process

    while running:

        # Runtime is the primary process.
        if runtime_process is not None:

            runtime_code = (
                runtime_process.poll()
            )

            if runtime_code is not None:

                log(
                    "Sentinel Runtime exited "
                    f"with code {runtime_code}."
                )

                break

        # Honeypot watchdog.
        if honeypot_process is not None:

            honeypot_code = (
                honeypot_process.poll()
            )

            if honeypot_code is not None:

                log(
                    "Honeypot stopped "
                    f"with code {honeypot_code}."
                )

                if running:

                    log(
                        "Restarting Honeypot..."
                    )

                    time.sleep(
                        HONEYPOT_RESTART_DELAY
                    )

                    honeypot_process = (
                        start_honeypot()
                    )

        # Additional listener check.
        if not port_is_open():

            if (
                honeypot_process is not None
                and
                honeypot_process.poll()
                is None
            ):
                log(
                    "Warning: Honeypot process "
                    "exists but port 2222 "
                    "is not responding."
                )

        time.sleep(1)


# ============================================================
# MAIN
# ============================================================

def run():

    signal.signal(
        signal.SIGINT,
        signal_handler,
    )

    signal.signal(
        signal.SIGTERM,
        signal_handler,
    )

    print(
        "=" * 60
    )

    print(
        "SENTINEL PHOENIX "
        f"UNIFIED LAUNCHER V{LAUNCHER_VERSION}"
    )

    print(
        "=" * 60
    )

    print(
        "HONEYPOT : SUPERVISED"
    )

    print(
        "RUNTIME  : SUPERVISED"
    )

    print(
        "IDENTITY : RUNTIME CONTROLLED"
    )

    print(
        "REPLAY   : RUNTIME CONTROLLED"
    )

    print(
        "=" * 60
    )

    start_honeypot()

    if not port_is_open():

        log(
            "Startup aborted: "
            "Honeypot unavailable."
        )

        shutdown()

        return 2

    start_runtime()

    try:
        supervise()

    finally:
        shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(
        run()
    )
