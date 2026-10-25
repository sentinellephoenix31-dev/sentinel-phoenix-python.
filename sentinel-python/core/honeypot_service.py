# ============================================================
# SENTINEL PHOENIX
# HONEYPOT SERVICE V1.0
#
# Dedicated entry point for the network honeypot.
# Does NOT start the old dashboard/runtime stack.
# ============================================================

import sys
import traceback


SERVICE_VERSION = "1.0"


def run():
    print(
        f"[HONEYPOT SERVICE] V{SERVICE_VERSION} starting...",
        flush=True,
    )

    try:
        from core.main import run_honeypot

    except Exception as error:
        print(
            "[HONEYPOT SERVICE] Import failure:",
            repr(error),
            flush=True,
        )

        traceback.print_exc()

        return 2

    try:
        print(
            "[HONEYPOT SERVICE] Starting listener...",
            flush=True,
        )

        run_honeypot()

        print(
            "[HONEYPOT SERVICE] Listener stopped.",
            flush=True,
        )

        return 0

    except KeyboardInterrupt:
        print(
            "[HONEYPOT SERVICE] Shutdown requested.",
            flush=True,
        )

        return 0

    except Exception as error:
        print(
            "[HONEYPOT SERVICE] Fatal error:",
            repr(error),
            flush=True,
        )

        traceback.print_exc()

        return 1


if __name__ == "__main__":
    raise SystemExit(
        run()
    )