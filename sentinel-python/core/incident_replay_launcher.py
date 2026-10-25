# ============================================================
# SENTINEL PHOENIX
# INCIDENT REPLAY LAUNCHER V1.1
#
# Priority:
#   1. Incident Globe V3.1
#   2. Incident Globe V2
#   3. Legacy Qt Replay
#
# The launcher stays isolated from the GUI processes.
# ============================================================

import argparse
import subprocess
import sys


LAUNCHER_VERSION = "1.1"

PRIMARY_MODULE = (
    "core.incident_globe_v3"
)

SECONDARY_MODULE = (
    "core.incident_globe_v2"
)

FALLBACK_MODULE = (
    "core.incident_replay_qt"
)


# ============================================================
# RUN MODULE
# ============================================================

def run_module(
    module_name,
    query="latest",
):

    command = [
        sys.executable,
        "-u",
        "-m",
        module_name,
        "--query",
        str(query),
    ]

    print(
        f"[REPLAY LAUNCHER] Starting {module_name}",
        flush=True,
    )

    try:

        process = subprocess.run(
            command,
            check=False,
        )

        code = int(
            process.returncode
        )

        print(
            f"[REPLAY LAUNCHER] "
            f"{module_name} exited with code {code}.",
            flush=True,
        )

        return code

    except KeyboardInterrupt:

        print(
            "[REPLAY LAUNCHER] Interrupted.",
            flush=True,
        )

        return 130

    except Exception as error:

        print(
            f"[REPLAY LAUNCHER] Failed to launch "
            f"{module_name}: {error!r}",
            flush=True,
        )

        return 1


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Sentinel Phoenix Incident Replay Launcher"
        )
    )

    parser.add_argument(
        "query_positional",
        nargs="?",
        default=None,
    )

    parser.add_argument(
        "--query",
        default=None,
    )

    args = parser.parse_args()

    query = (
        args.query
        or args.query_positional
        or "latest"
    )

    print(
        "=" * 66,
        flush=True,
    )

    print(
        f"SENTINEL PHOENIX REPLAY LAUNCHER "
        f"V{LAUNCHER_VERSION}",
        flush=True,
    )

    print(
        f"QUERY : {query}",
        flush=True,
    )

    print(
        "PRIMARY   : GLOBE V3.1",
        flush=True,
    )

    print(
        "SECONDARY : GLOBE V2",
        flush=True,
    )

    print(
        "FALLBACK  : LEGACY QT",
        flush=True,
    )

    print(
        "=" * 66,
        flush=True,
    )


    # ========================================================
    # 1. GLOBE V3.1
    # ========================================================

    primary_code = run_module(
        PRIMARY_MODULE,
        query,
    )

    if primary_code == 0:
        return 0


    print(
        "[REPLAY LAUNCHER] "
        "Globe V3.1 failed. "
        "Starting Globe V2 fallback.",
        flush=True,
    )


    # ========================================================
    # 2. GLOBE V2
    # ========================================================

    secondary_code = run_module(
        SECONDARY_MODULE,
        query,
    )

    if secondary_code == 0:
        return 0


    print(
        "[REPLAY LAUNCHER] "
        "Globe V2 failed. "
        "Starting legacy replay fallback.",
        flush=True,
    )


    # ========================================================
    # 3. LEGACY QT
    # ========================================================

    return run_module(
        FALLBACK_MODULE,
        query,
    )


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
