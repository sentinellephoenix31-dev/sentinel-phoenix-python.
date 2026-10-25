import re
import subprocess


HELPER = "/usr/local/sbin/phoenix-sandbox-helper"


def safe_session_id(session_id):

    value = str(
        session_id
    )

    if not re.fullmatch(
        r"[a-f0-9]{8,32}",
        value
    ):

        raise ValueError(
            "Invalid sandbox session ID"
        )

    return value


def sandbox_name(
    session_id
):

    session_id = (
        safe_session_id(
            session_id
        )
    )

    return (
        f"phoenix-{session_id}"
    )


def run_helper(
    action,
    session_id,
    timeout=20
):

    session_id = (
        safe_session_id(
            session_id
        )
    )

    if action not in (
        "create",
        "check",
        "destroy"
    ):

        raise ValueError(
            "Invalid sandbox action"
        )

    try:

        result = subprocess.run(
            [
                "sudo",
                "-n",
                HELPER,
                action,
                session_id
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )

    except subprocess.TimeoutExpired:

        return {
            "success": False,
            "error": "TIMEOUT"
        }

    return {
        "success":
            result.returncode == 0,

        "returncode":
            result.returncode,

        "stdout":
            result.stdout.strip(),

        "stderr":
            result.stderr.strip()
    }


def create_sandbox(
    session_id
):

    session_id = (
        safe_session_id(
            session_id
        )
    )

    # Ne crée pas un deuxième conteneur
    # si celui de cette session existe déjà.

    if sandbox_exists(
        session_id
    ):

        return {
            "sandbox_active":
                True,

            "sandbox_name":
                sandbox_name(
                    session_id
                ),

            "sandbox_id":
                None,

            "sandbox_reused":
                True,

            "sandbox_network":
                "NONE",

            "sandbox_read_only":
                True,

            "sandbox_privileged":
                False,

            "payload_execution":
                False,

            "sandbox_error":
                None
        }

    result = run_helper(
        "create",
        session_id
    )

    if not result[
        "success"
    ]:

        return {
            "sandbox_active":
                False,

            "sandbox_name":
                sandbox_name(
                    session_id
                ),

            "sandbox_id":
                None,

            "sandbox_reused":
                False,

            "payload_execution":
                False,

            "sandbox_error":
                result.get(
                    "stderr"
                )
                or
                result.get(
                    "error"
                )
                or
                "UNKNOWN_ERROR"
        }

    container_id = (
        result.get(
            "stdout",
            ""
        )
    )

    return {
        "sandbox_active":
            True,

        "sandbox_name":
            sandbox_name(
                session_id
            ),

        "sandbox_id":
            container_id[:12],

        "sandbox_reused":
            False,

        "sandbox_network":
            "NONE",

        "sandbox_read_only":
            True,

        "sandbox_privileged":
            False,

        "payload_execution":
            False,

        "sandbox_error":
            None
    }


def sandbox_exists(
    session_id
):

    result = run_helper(
        "check",
        session_id,
        timeout=10
    )

    return result[
        "success"
    ]


def destroy_sandbox(
    session_id
):

    result = run_helper(
        "destroy",
        session_id,
        timeout=15
    )

    return result[
        "success"
    ]