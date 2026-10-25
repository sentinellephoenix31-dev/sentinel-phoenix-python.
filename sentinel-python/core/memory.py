import hashlib
import json
import os
import sqlite3
import threading

from datetime import datetime, timezone


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

DATABASE_FILE = os.path.join(
    DATA_DIR,
    "phoenix_memory.db"
)

_lock = threading.RLock()


def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def get_connection():
    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    connection = sqlite3.connect(
        DATABASE_FILE,
        timeout=10
    )

    connection.row_factory = (
        sqlite3.Row
    )

    connection.execute(
        "PRAGMA journal_mode=WAL"
    )

    connection.execute(
        "PRAGMA synchronous=NORMAL"
    )

    return connection


# ============================================================
# INITIALISATION
# ============================================================

def init_memory():

    with _lock:

        connection = (
            get_connection()
        )

        try:

            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS source_profiles (

                    source_ip TEXT PRIMARY KEY,

                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,

                    total_events INTEGER NOT NULL DEFAULT 0,
                    critical_events INTEGER NOT NULL DEFAULT 0,
                    containment_events INTEGER NOT NULL DEFAULT 0,

                    max_payload_score REAL NOT NULL DEFAULT 0,
                    max_behavior_score REAL NOT NULL DEFAULT 0,
                    max_anomaly_score REAL NOT NULL DEFAULT 0,
                    max_global_score REAL NOT NULL DEFAULT 0,

                    last_global_level TEXT,
                    last_policy_action TEXT,

                    last_decoy_session TEXT,
                    sandbox_seen INTEGER NOT NULL DEFAULT 0,

                    indicators_json TEXT NOT NULL DEFAULT '[]',
                    anomaly_reasons_json TEXT NOT NULL DEFAULT '[]'
                );


                CREATE TABLE IF NOT EXISTS observations (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    timestamp TEXT NOT NULL,

                    source_ip TEXT NOT NULL,
                    source_port INTEGER,

                    payload_hash TEXT,

                    payload_length INTEGER,

                    payload_score REAL,
                    behavior_score REAL,
                    anomaly_score REAL,
                    global_score REAL,

                    global_level TEXT,

                    policy_action TEXT,

                    containment_requested INTEGER,

                    decoy_session_id TEXT,

                    sandbox_active INTEGER,

                    indicators_json TEXT,

                    anomaly_reasons_json TEXT
                );


                CREATE INDEX IF NOT EXISTS
                idx_observations_source_ip
                ON observations(source_ip);


                CREATE INDEX IF NOT EXISTS
                idx_observations_timestamp
                ON observations(timestamp);
                """
            )

            connection.commit()

        finally:

            connection.close()


# ============================================================
# OUTILS
# ============================================================

def payload_hash(payload):

    value = (
        payload or ""
    ).encode(
        "utf-8",
        errors="replace"
    )

    return hashlib.sha256(
        value
    ).hexdigest()


def merge_unique(
    old_values,
    new_values
):

    result = []

    seen = set()

    for value in (
        list(old_values)
        +
        list(new_values)
    ):

        text = str(value)

        if text in seen:
            continue

        seen.add(text)

        result.append(text)

    return result


def load_json_list(value):

    if not value:
        return []

    try:

        data = json.loads(
            value
        )

        if isinstance(
            data,
            list
        ):
            return data

    except json.JSONDecodeError:
        pass

    return []


# ============================================================
# MEMORISATION
# ============================================================

def remember_event(
    source_ip,
    source_port,
    payload,
    analysis,
    behavior,
    anomaly,
    fusion,
    response,
    deception,
    sandbox
):

    now = utc_now()

    indicators = analysis.get(
        "indicators",
        []
    )

    anomaly_reasons = anomaly.get(
        "anomaly_reasons",
        []
    )

    payload_score = float(
        analysis.get(
            "score",
            0
        )
    )

    behavior_score = float(
        behavior.get(
            "behavior_score",
            0
        )
    )

    anomaly_score = float(
        anomaly.get(
            "anomaly_score",
            0
        )
    )

    global_score = float(
        fusion.get(
            "global_score",
            0
        )
    )

    global_level = fusion.get(
        "global_level",
        "LOW"
    )

    policy_action = response.get(
        "action",
        "OBSERVE"
    )

    containment_requested = bool(
        response.get(
            "containment_requested",
            False
        )
    )

    decoy_session_id = deception.get(
        "decoy_session_id"
    )

    sandbox_active = bool(
        sandbox.get(
            "sandbox_active",
            False
        )
    )

    is_critical = (
        str(global_level).upper()
        ==
        "CRITICAL"
    )

    with _lock:

        connection = (
            get_connection()
        )

        try:

            # ======================================
            # OBSERVATION BRUTE
            # ======================================

            connection.execute(
                """
                INSERT INTO observations (

                    timestamp,
                    source_ip,
                    source_port,

                    payload_hash,
                    payload_length,

                    payload_score,
                    behavior_score,
                    anomaly_score,
                    global_score,

                    global_level,
                    policy_action,

                    containment_requested,

                    decoy_session_id,
                    sandbox_active,

                    indicators_json,
                    anomaly_reasons_json

                )

                VALUES (
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?,
                    ?, ?,
                    ?, ?
                )
                """,

                (
                    now,
                    source_ip,
                    source_port,

                    payload_hash(
                        payload
                    ),

                    len(
                        payload or ""
                    ),

                    payload_score,
                    behavior_score,
                    anomaly_score,
                    global_score,

                    global_level,
                    policy_action,

                    int(
                        containment_requested
                    ),

                    decoy_session_id,

                    int(
                        sandbox_active
                    ),

                    json.dumps(
                        indicators
                    ),

                    json.dumps(
                        anomaly_reasons
                    )
                )
            )

            # ======================================
            # PROFIL EXISTANT
            # ======================================

            row = connection.execute(
                """
                SELECT *
                FROM source_profiles
                WHERE source_ip = ?
                """,
                (
                    source_ip,
                )
            ).fetchone()

            if row is None:

                connection.execute(
                    """
                    INSERT INTO source_profiles (

                        source_ip,

                        first_seen,
                        last_seen,

                        total_events,
                        critical_events,
                        containment_events,

                        max_payload_score,
                        max_behavior_score,
                        max_anomaly_score,
                        max_global_score,

                        last_global_level,
                        last_policy_action,

                        last_decoy_session,
                        sandbox_seen,

                        indicators_json,
                        anomaly_reasons_json
                    )

                    VALUES (
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?,
                        ?, ?,
                        ?, ?
                    )
                    """,

                    (
                        source_ip,

                        now,
                        now,

                        1,

                        int(
                            is_critical
                        ),

                        int(
                            containment_requested
                        ),

                        payload_score,
                        behavior_score,
                        anomaly_score,
                        global_score,

                        global_level,
                        policy_action,

                        decoy_session_id,

                        int(
                            sandbox_active
                        ),

                        json.dumps(
                            indicators
                        ),

                        json.dumps(
                            anomaly_reasons
                        )
                    )
                )

            else:

                old_indicators = (
                    load_json_list(
                        row[
                            "indicators_json"
                        ]
                    )
                )

                old_anomalies = (
                    load_json_list(
                        row[
                            "anomaly_reasons_json"
                        ]
                    )
                )

                merged_indicators = (
                    merge_unique(
                        old_indicators,
                        indicators
                    )
                )

                merged_anomalies = (
                    merge_unique(
                        old_anomalies,
                        anomaly_reasons
                    )
                )

                connection.execute(
                    """
                    UPDATE source_profiles

                    SET
                        last_seen = ?,

                        total_events =
                            total_events + 1,

                        critical_events =
                            critical_events + ?,

                        containment_events =
                            containment_events + ?,

                        max_payload_score =
                            MAX(
                                max_payload_score,
                                ?
                            ),

                        max_behavior_score =
                            MAX(
                                max_behavior_score,
                                ?
                            ),

                        max_anomaly_score =
                            MAX(
                                max_anomaly_score,
                                ?
                            ),

                        max_global_score =
                            MAX(
                                max_global_score,
                                ?
                            ),

                        last_global_level = ?,

                        last_policy_action = ?,

                        last_decoy_session =
                            COALESCE(
                                ?,
                                last_decoy_session
                            ),

                        sandbox_seen =
                            MAX(
                                sandbox_seen,
                                ?
                            ),

                        indicators_json = ?,

                        anomaly_reasons_json = ?

                    WHERE source_ip = ?
                    """,

                    (
                        now,

                        int(
                            is_critical
                        ),

                        int(
                            containment_requested
                        ),

                        payload_score,
                        behavior_score,
                        anomaly_score,
                        global_score,

                        global_level,
                        policy_action,

                        decoy_session_id,

                        int(
                            sandbox_active
                        ),

                        json.dumps(
                            merged_indicators
                        ),

                        json.dumps(
                            merged_anomalies
                        ),

                        source_ip
                    )
                )

            connection.commit()

        finally:

            connection.close()


# ============================================================
# LECTURE D'UNE SOURCE
# ============================================================

def get_source_memory(
    source_ip
):

    with _lock:

        connection = (
            get_connection()
        )

        try:

            row = connection.execute(
                """
                SELECT *
                FROM source_profiles
                WHERE source_ip = ?
                """,
                (
                    source_ip,
                )
            ).fetchone()

            if row is None:
                return None

            result = dict(
                row
            )

            result[
                "indicators"
            ] = load_json_list(
                result.pop(
                    "indicators_json"
                )
            )

            result[
                "anomaly_reasons"
            ] = load_json_list(
                result.pop(
                    "anomaly_reasons_json"
                )
            )

            result[
                "sandbox_seen"
            ] = bool(
                result[
                    "sandbox_seen"
                ]
            )

            return result

        finally:

            connection.close()


# ============================================================
# STATISTIQUES MEMOIRE
# ============================================================

def get_memory_stats():

    with _lock:

        connection = (
            get_connection()
        )

        try:

            sources = connection.execute(
                """
                SELECT COUNT(*)
                FROM source_profiles
                """
            ).fetchone()[0]

            observations = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM observations
                    """
                ).fetchone()[0]
            )

            critical_sources = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM source_profiles
                    WHERE critical_events > 0
                    """
                ).fetchone()[0]
            )

            contained_sources = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM source_profiles
                    WHERE containment_events > 0
                    """
                ).fetchone()[0]
            )

            return {
                "known_sources":
                    sources,

                "observations":
                    observations,

                "critical_sources":
                    critical_sources,

                "contained_sources":
                    contained_sources
            }

        finally:

            connection.close()


# Initialise automatiquement la base
init_memory()