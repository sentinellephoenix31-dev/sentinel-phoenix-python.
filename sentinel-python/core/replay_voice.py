import os
import subprocess
import sys
import time


# ============================================================
# SENTINEL PHOENIX
# VISUAL INCIDENT REPLAY VOICE ROUTER V1
#
# Voice / text command
#        ↓
# Detect replay intent
#        ↓
# Launch Incident Replay Query
#        ↓
# Globe + Geo Intelligence + F3 narration
#
# No shell=True.
# No attacker-controlled command execution.
# ============================================================


REPLAY_VOICE_VERSION = "1.0"


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)


_current_replay_process = None


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value):

    return " ".join(
        str(
            value or ""
        )
        .strip()
        .lower()
        .split()
    )


# ============================================================
# REPLAY INTENT
# ============================================================

def is_replay_request(text):
    """
    Detect natural-language requests for Sentinel
    Visual Incident Replay.

    Supports French + English and does not require
    the user to explicitly say "visual" or "security".
    """

    import re
    import unicodedata

    if text is None:
        return False

    value = str(text).strip().lower()

    if not value:
        return False

    # Normalize accents and punctuation.
    value = unicodedata.normalize(
        "NFKD",
        value
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = value.replace("’", "'")

    value = re.sub(
        r"[^a-z0-9']+",
        " ",
        value
    )

    value = value.replace(
        "'",
        " "
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    ).strip()


    temporal_words = (
        "today",
        "yesterday",
        "last night",
        "overnight",
        "last 24 hours",
        "past 24 hours",
        "last 7 days",
        "past 7 days",
        "this week",
        "this morning",
        "this afternoon",
        "this evening",

        "aujourd hui",
        "hier",
        "cette nuit",
        "hier soir",
        "dernieres 24 heures",
        "derniere 24 heures",
        "7 derniers jours",
        "cette semaine",
        "ce matin",
        "cet apres midi",
        "ce soir",
    )


    history_phrases = (
        "what happened",
        "what has happened",
        "what occurred",
        "show me what happened",
        "show what happened",

        "qu est ce qui s est passe",
        "que s est il passe",
        "ce qui s est passe",
        "montre moi ce qui s est passe",
        "montre ce qui s est passe",
        "qu est ce qu il s est passe",
    )


    security_words = (
        "attack",
        "attacks",
        "incident",
        "incidents",
        "security",
        "threat",
        "threats",
        "intrusion",
        "intrusions",
        "alert",
        "alerts",
        "honeypot",
        "cyber",

        "attaque",
        "attaques",
        "incident",
        "incidents",
        "securite",
        "menace",
        "menaces",
        "intrusion",
        "intrusions",
        "alerte",
        "alertes",
        "cyber",
    )


    visual_words = (
        "replay",
        "visual replay",
        "incident replay",
        "visual incident replay",
        "globe",
        "map",
        "world map",

        "rejoue",
        "rejouer",
        "visualise",
        "visualiser",
        "globe",
        "carte",
    )


    has_time = any(
        marker in value
        for marker in temporal_words
    )

    has_history = any(
        marker in value
        for marker in history_phrases
    )

    has_security = any(
        marker in value
        for marker in security_words
    )

    has_visual = any(
        marker in value
        for marker in visual_words
    )


    # Explicit Replay request.
    if has_visual:
        return True


    # Natural historical request:
    #
    # "What happened yesterday?"
    # "Qu'est-ce qui s'est passé aujourd'hui ?"
    if (
        has_history
        and
        has_time
    ):
        return True


    # Security + time:
    #
    # "What attacks happened today?"
    # "Quelles attaques ont eu lieu aujourd'hui ?"
    if (
        has_security
        and
        has_time
    ):
        return True


    return False


def replay_is_running():

    global _current_replay_process


    if _current_replay_process is None:
        return False


    return (
        _current_replay_process.poll()
        is None
    )


# ============================================================
# LAUNCH REPLAY
# ============================================================

def launch_replay(query):

    global _current_replay_process


    query = str(
        query or ""
    ).strip()


    if not query:

        return {
            "status":
                "DENIED",

            "reason":
                "EMPTY_QUERY"
        }


    if replay_is_running():

        return {
            "status":
                "ALREADY_RUNNING",

            "reason":
                "VISUAL_REPLAY_ALREADY_OPEN"
        }


    command = [
        sys.executable,
        "-m",
        "core.incident_replay_launcher",
        "--query",
        query,
    ]


    try:

        _current_replay_process = (
            subprocess.Popen(
                command,
                cwd=BASE_DIR,
                shell=False,
                start_new_session=True,
            )
        )


    except OSError as error:

        return {
            "status":
                "FAILED",

            "reason":
                "REPLAY_PROCESS_START_FAILED",

            "detail":
                str(
                    error
                )
        }


    # Short delay catches an immediate Python/import failure.

    time.sleep(
        0.25
    )


    if (
        _current_replay_process.poll()
        is not None
    ):

        return {
            "status":
                "FAILED",

            "reason":
                "REPLAY_PROCESS_EXITED_EARLY",

            "returncode":
                _current_replay_process.returncode
        }


    return {
        "status":
            "LAUNCHED",

        "query":
            query,

        "pid":
            _current_replay_process.pid,

        "module":
            "core.incident_replay_launcher"
    }


# ============================================================
# MAIN ROUTER
# ============================================================

def handle_replay_request(text):

    if not is_replay_request(
        text
    ):

        return {
            "handled":
                False,

            "status":
                "NOT_REPLAY_REQUEST"
        }


    result = launch_replay(
        text
    )


    result[
        "handled"
    ] = True


    return result


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    positive_tests = (
        "montre-moi ce qui s'est passé aujourd'hui",
        "montre les attaques de cette nuit",
        "affiche l'incident le plus dangereux aujourd'hui",
        "show me what happened last night",
        "show the most dangerous attack today",
        "replay the incident",
    )


    negative_tests = (
        "quelle heure est-il",
        "bonjour sentinel",
        "ouvre la caméra",
        "what is python",
    )


    positives_ok = all(
        is_replay_request(
            value
        )
        for value in positive_tests
    )


    negatives_ok = all(
        not is_replay_request(
            value
        )
        for value in negative_tests
    )


    passed = (
        positives_ok
        and
        negatives_ok
    )


    return {
        "status":
            (
                "PASS"
                if passed
                else
                "FAIL"
            ),

        "version":
            REPLAY_VOICE_VERSION,

        "replay_detection":
            positives_ok,

        "false_positive_test":
            negatives_ok,

        "launcher":
            callable(
                launch_replay
            ),

        "handler":
            callable(
                handle_replay_request
            ),

        "features": {
            "french":
                True,

            "english":
                True,

            "time_context_passthrough":
                True,

            "highest_risk_passthrough":
                True,

            "separate_replay_process":
                True,

            "duplicate_window_protection":
                True,
        },

        "security": {
            "shell_execution":
                False,

            "payload_execution":
                False,

            "command":
                "TRUSTED_INTERNAL_MODULE_ONLY",
        },
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    import pprint

    pprint.pp(
        self_test()
    )