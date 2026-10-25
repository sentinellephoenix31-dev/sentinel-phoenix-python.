import json
import os
import secrets
import threading
import time

from datetime import datetime, timezone

from core.adaptive_deception import (
    process_interaction
)


# ============================================================
# SENTINEL PHOENIX
# DECEPTION CORE V4
# ADAPTIVE DECEPTION + MOVING TARGET DEFENSE
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

DECOY_DIR = os.path.join(
    DATA_DIR,
    "decoys"
)

REGISTRY_FILE = os.path.join(
    DECOY_DIR,
    "registry.json"
)

_lock = threading.RLock()


# ============================================================
# TIME
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# DIRECTORIES
# ============================================================

def ensure_directories():

    os.makedirs(
        DECOY_DIR,
        exist_ok=True
    )


# ============================================================
# SAFE JSON WRITE
# ============================================================

def atomic_json_write(
    path,
    data
):

    temporary = (
        path
        +
        ".tmp"
    )

    with open(
        temporary,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )

    os.replace(
        temporary,
        path
    )


# ============================================================
# REGISTRY
# ============================================================

def load_registry():

    ensure_directories()

    if not os.path.isfile(
        REGISTRY_FILE
    ):

        return {}

    try:

        with open(
            REGISTRY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            registry = json.load(
                file
            )

        if isinstance(
            registry,
            dict
        ):

            return registry

    except (
        OSError,
        json.JSONDecodeError
    ):

        pass

    return {}


def save_registry(
    registry
):

    ensure_directories()

    atomic_json_write(
        REGISTRY_FILE,
        registry
    )


# ============================================================
# SESSION PATHS
# ============================================================

def session_path(
    session_id
):

    return os.path.join(
        DECOY_DIR,
        session_id
    )


def session_file(
    session_id
):

    return os.path.join(
        session_path(
            session_id
        ),
        "session.json"
    )


# ============================================================
# SESSION STORAGE
# ============================================================

def load_session(
    session_id
):

    path = session_file(
        session_id
    )

    if not os.path.isfile(
        path
    ):

        return None

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

        if isinstance(
            data,
            dict
        ):

            return data

    except (
        OSError,
        json.JSONDecodeError
    ):

        pass

    return None


def save_session(
    session_id,
    session
):

    directory = session_path(
        session_id
    )

    os.makedirs(
        directory,
        exist_ok=True
    )

    atomic_json_write(
        session_file(
            session_id
        ),
        session
    )


# ============================================================
# CREATE SESSION
# ============================================================

def create_session(
    source_ip,
    source_port
):

    ensure_directories()

    while True:

        session_id = (
            secrets.token_hex(
                8
            )
        )

        directory = (
            session_path(
                session_id
            )
        )

        if not os.path.exists(
            directory
        ):

            break

    os.makedirs(
        directory,
        exist_ok=False
    )

    session = {

        "session_id":
            session_id,

        "source_ip":
            source_ip,

        "source_port":
            source_port,

        # Numérique pour Lifecycle Manager
        "created_at":
            time.time(),

        "created_at_iso":
            utc_now(),

        "last_seen":
            utc_now(),

        "state":
            "ACTIVE",

        "mode":
            "ADAPTIVE_DECEPTION",

        "interactions":
            0,

        "surface_profile":
            None,

        "surface_generation":
            1,

        "surface_rotations":
            0,

        "payload_execution":
            False,

        "host_modified":
            False
    }

    save_session(
        session_id,
        session
    )

    return session_id


# ============================================================
# SESSION REGISTRY
# ============================================================

def get_or_create_session(
    source_ip,
    source_port
):

    with _lock:

        registry = (
            load_registry()
        )

        existing_session = (
            registry.get(
                source_ip
            )
        )

        # ====================================================
        # REUSE EXISTING SESSION
        # ====================================================

        if existing_session:

            directory = (
                session_path(
                    existing_session
                )
            )

            if os.path.isdir(
                directory
            ):

                return (
                    existing_session,
                    True
                )

        # ====================================================
        # CREATE NEW SESSION
        # ====================================================

        session_id = (
            create_session(
                source_ip,
                source_port
            )
        )

        registry[
            source_ip
        ] = session_id

        save_registry(
            registry
        )

        return (
            session_id,
            False
        )


# ============================================================
# ACTIVITY LOG
# ============================================================

def log_activity(
    session_id,
    event
):

    directory = (
        session_path(
            session_id
        )
    )

    os.makedirs(
        directory,
        exist_ok=True
    )

    activity_file = os.path.join(
        directory,
        "activity.jsonl"
    )

    with open(
        activity_file,
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            json.dumps(
                event,
                ensure_ascii=False
            )
            +
            "\n"
        )


# ============================================================
# ACTIVE DECOY CHECK
# ============================================================

def has_active_decoy(
    source_ip
):

    with _lock:

        registry = (
            load_registry()
        )

        session_id = (
            registry.get(
                source_ip
            )
        )

        if not session_id:

            return False

        directory = (
            session_path(
                session_id
            )
        )

        if not os.path.isdir(
            directory
        ):

            return False

        session = (
            load_session(
                session_id
            )
        )

        if session is None:

            # Anciennes sessions sans metadata
            # restent récupérables par migration.
            return True

        state = str(
            session.get(
                "state",
                "ACTIVE"
            )
        ).upper()

        return state not in (
            "CLOSED",
            "DESTROYED"
        )


# ============================================================
# ROUTE TO ADAPTIVE DECOY
# ============================================================

def route_to_decoy(
    source_ip,
    source_port,
    payload,
    fusion,
    response
):

    """
    Important :

    Le payload entrant n'est JAMAIS exécuté.

    Il est uniquement transmis au moteur
    Adaptive Deception qui l'interprète comme
    une commande fictive.

    Aucun shell hôte.
    Aucun docker exec.
    Aucun subprocess avec le payload.
    """

    session_id, reused = (
        get_or_create_session(
            source_ip,
            source_port
        )
    )

    directory = (
        session_path(
            session_id
        )
    )

    # ========================================================
    # ADAPTIVE DECEPTION / MTD
    # ========================================================

    try:

        interaction = (
            process_interaction(
                session_dir=
                    directory,

                session_id=
                    session_id,

                source_ip=
                    source_ip,

                payload=
                    payload,

                fusion=
                    fusion
            )
        )

    except Exception as error:

        # Fail-safe :
        # aucune exécution réelle si le moteur de deception
        # rencontre une erreur.

        interaction = {

            "command":
                str(
                    payload
                )[:512],

            "response":
                (
                    "Temporary decoy service error.\n"
                ),

            "profile_id":
                None,

            "generation":
                1,

            "interactions":
                0,

            "rotations":
                0,

            "surface_rotated":
                False,

            "rotation_reason":
                None,

            "payload_execution":
                False,

            "host_modified":
                False,

            "error":
                str(
                    error
                )
        }

    # ========================================================
    # UPDATE SESSION
    # ========================================================

    session = (
        load_session(
            session_id
        )
        or
        {}
    )

    session[
        "session_id"
    ] = session_id

    session[
        "source_ip"
    ] = source_ip

    session[
        "source_port"
    ] = source_port

    # Anciennes sessions peuvent ne pas avoir
    # created_at sous forme numérique.
    if not isinstance(
        session.get(
            "created_at"
        ),
        (
            int,
            float
        )
    ):

        session[
            "created_at"
        ] = time.time()

    if not session.get(
        "created_at_iso"
    ):

        session[
            "created_at_iso"
        ] = utc_now()

    session[
        "last_seen"
    ] = utc_now()

    session[
        "state"
    ] = "ACTIVE"

    session[
        "mode"
    ] = (
        "ADAPTIVE_DECEPTION"
    )

    session[
        "interactions"
    ] = interaction.get(
        "interactions",
        0
    )

    session[
        "surface_profile"
    ] = interaction.get(
        "profile_id"
    )

    session[
        "surface_generation"
    ] = interaction.get(
        "generation",
        1
    )

    session[
        "surface_rotations"
    ] = interaction.get(
        "rotations",
        0
    )

    session[
        "payload_execution"
    ] = False

    session[
        "host_modified"
    ] = False

    save_session(
        session_id,
        session
    )

    # ========================================================
    # ACTIVITY EVENT
    # ========================================================

    activity_event = {

        "timestamp":
            utc_now(),

        "event":
            "DECOY_INTERACTION",

        "source_ip":
            source_ip,

        "source_port":
            source_port,

        "command":
            interaction.get(
                "command",
                ""
            )[:512],

        "response":
            interaction.get(
                "response",
                ""
            )[:4000],

        "global_score":
            fusion.get(
                "global_score",
                0
            ),

        "global_level":
            fusion.get(
                "global_level"
            ),

        "policy_action":
            response.get(
                "action"
            ),

        "surface_profile":
            interaction.get(
                "profile_id"
            ),

        "surface_generation":
            interaction.get(
                "generation",
                1
            ),

        "surface_rotated":
            interaction.get(
                "surface_rotated",
                False
            ),

        "surface_rotations":
            interaction.get(
                "rotations",
                0
            ),

        "rotation_reason":
            interaction.get(
                "rotation_reason"
            ),

        "executed":
            False,

        "payload_execution":
            False,

        "host_modified":
            False
    }

    if interaction.get(
        "error"
    ):

        activity_event[
            "deception_error"
        ] = interaction.get(
            "error"
        )

    log_activity(
        session_id,
        activity_event
    )

    # ========================================================
    # RESULT FOR MAIN / EVENTS
    # ========================================================

    return {

        "decoy_active":
            True,

        "decoy_session_id":
            session_id,

        "decoy_path":
            directory,

        "decoy_mode":
            "ADAPTIVE_TERMINAL",

        "decoy_reused":
            reused,

        "decoy_command":
            interaction.get(
                "command"
            ),

        "decoy_response":
            interaction.get(
                "response"
            ),

        "decoy_profile":
            interaction.get(
                "profile_id"
            ),

        "surface_generation":
            interaction.get(
                "generation",
                1
            ),

        "surface_rotated":
            interaction.get(
                "surface_rotated",
                False
            ),

        "surface_rotations":
            interaction.get(
                "rotations",
                0
            ),

        "rotation_reason":
            interaction.get(
                "rotation_reason"
            ),

        "payload_execution":
            False,

        "host_modified":
            False
    }


# ============================================================
# EMPTY DECOY RESULT
# ============================================================

def no_decoy():

    return {

        "decoy_active":
            False,

        "decoy_session_id":
            None,

        "decoy_path":
            None,

        "decoy_mode":
            None,

        "decoy_reused":
            False,

        "decoy_command":
            None,

        "decoy_response":
            None,

        "decoy_profile":
            None,

        "surface_generation":
            None,

        "surface_rotated":
            False,

        "surface_rotations":
            0,

        "rotation_reason":
            None,

        "payload_execution":
            False,

        "host_modified":
            False
    }