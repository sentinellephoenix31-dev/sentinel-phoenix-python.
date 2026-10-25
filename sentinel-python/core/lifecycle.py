import json
import os
import time
from datetime import datetime, timezone


# ============================================================
# SENTINEL PHOENIX
# SESSION LIFECYCLE CORE
#
# Purpose:
# - Track deception / sandbox sessions
# - Record session activity
# - Detect expiration
# - Expire inactive sessions safely
# - Keep lifecycle state persistent
#
# This module does NOT execute payloads or shell commands.
# ============================================================


LIFECYCLE_VERSION = "1.0"


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

LIFECYCLE_FILE = os.path.join(
    DATA_DIR,
    "lifecycle_sessions.json"
)


# ============================================================
# POLICY
# ============================================================

# Default session lifetime:
# 30 minutes without activity.

DEFAULT_TTL_SECONDS = 30 * 60


# ============================================================
# UTILITIES
# ============================================================

def utc_now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


def ensure_storage():

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    if not os.path.isfile(
        LIFECYCLE_FILE
    ):

        save_state(
            {
                "version":
                    LIFECYCLE_VERSION,

                "sessions":
                    {}
            }
        )


# ============================================================
# LOAD / SAVE
# ============================================================

def load_state():

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    if not os.path.isfile(
        LIFECYCLE_FILE
    ):

        return {
            "version":
                LIFECYCLE_VERSION,

            "sessions":
                {}
        }

    try:

        with open(
            LIFECYCLE_FILE,
            "r",
            encoding="utf-8"
        ) as handle:

            data = json.load(
                handle
            )

    except (
        OSError,
        json.JSONDecodeError
    ):

        return {
            "version":
                LIFECYCLE_VERSION,

            "sessions":
                {}
        }

    if not isinstance(
        data,
        dict
    ):

        data = {}

    if not isinstance(
        data.get(
            "sessions"
        ),
        dict
    ):

        data[
            "sessions"
        ] = {}

    data[
        "version"
    ] = LIFECYCLE_VERSION

    return data


def save_state(
    data
):

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    temporary_file = (
        LIFECYCLE_FILE
        +
        ".tmp"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8"
    ) as handle:

        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False
        )

    os.replace(
        temporary_file,
        LIFECYCLE_FILE
    )


# ============================================================
# SESSION ID VALIDATION
# ============================================================

def normalize_session_id(
    session_id
):

    session_id = str(
        session_id
    ).strip()

    if not session_id:

        raise ValueError(
            "SESSION_ID_REQUIRED"
        )

    if len(
        session_id
    ) > 128:

        raise ValueError(
            "SESSION_ID_TOO_LONG"
        )

    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "-_"
    )

    if not all(
        character in allowed
        for character in session_id
    ):

        raise ValueError(
            "INVALID_SESSION_ID"
        )

    return session_id


# ============================================================
# REGISTER SESSION
# ============================================================

def register_session(
    session_id,
    profile=None,
    ttl_seconds=DEFAULT_TTL_SECONDS,
    metadata=None
):

    ensure_storage()

    session_id = normalize_session_id(
        session_id
    )

    ttl_seconds = int(
        ttl_seconds
    )

    if ttl_seconds <= 0:

        ttl_seconds = (
            DEFAULT_TTL_SECONDS
        )

    state = load_state()

    now = time.time()

    existing = state[
        "sessions"
    ].get(
        session_id
    )

    # ========================================================
    # Existing session
    # ========================================================

    if existing:

        existing[
            "last_activity"
        ] = now

        existing[
            "last_activity_iso"
        ] = utc_now_iso()

        existing[
            "ttl_seconds"
        ] = ttl_seconds

        existing[
            "status"
        ] = "ACTIVE"

        existing[
            "expired"
        ] = False

        existing[
            "expired_at"
        ] = None

        existing[
            "expiration_reason"
        ] = None

        if profile is not None:

            existing[
                "profile"
            ] = profile

        if isinstance(
            metadata,
            dict
        ):

            existing.setdefault(
                "metadata",
                {}
            )

            existing[
                "metadata"
            ].update(
                metadata
            )

        save_state(
            state
        )

        return {
            "status":
                "UPDATED",

            "session_id":
                session_id,

            "session":
                existing
        }

    # ========================================================
    # New session
    # ========================================================

    record = {

        "session_id":
            session_id,

        "status":
            "ACTIVE",

        "profile":
            profile,

        "created_at":
            now,

        "created_at_iso":
            utc_now_iso(),

        "last_activity":
            now,

        "last_activity_iso":
            utc_now_iso(),

        "ttl_seconds":
            ttl_seconds,

        "expired":
            False,

        "expired_at":
            None,

        "expiration_reason":
            None,

        "interaction_count":
            0,

        "metadata":
            (
                metadata
                if isinstance(
                    metadata,
                    dict
                )
                else {}
            )
    }

    state[
        "sessions"
    ][
        session_id
    ] = record

    save_state(
        state
    )

    return {
        "status":
            "REGISTERED",

        "session_id":
            session_id,

        "session":
            record
    }


# ============================================================
# CREATE SESSION
#
# Compatibility alias.
# ============================================================

def create_session(
    session_id,
    profile=None,
    ttl_seconds=DEFAULT_TTL_SECONDS,
    metadata=None
):

    return register_session(
        session_id=session_id,
        profile=profile,
        ttl_seconds=ttl_seconds,
        metadata=metadata
    )


# ============================================================
# GET SESSION
# ============================================================

def get_session(
    session_id
):

    session_id = normalize_session_id(
        session_id
    )

    state = load_state()

    session = state[
        "sessions"
    ].get(
        session_id
    )

    if session is None:

        return None

    return dict(
        session
    )


# ============================================================
# LIST SESSIONS
# ============================================================

def list_sessions(
    include_expired=True
):

    state = load_state()

    sessions = list(
        state[
            "sessions"
        ].values()
    )

    if not include_expired:

        sessions = [
            session
            for session in sessions
            if not session.get(
                "expired",
                False
            )
        ]

    sessions.sort(
        key=lambda session:
            float(
                session.get(
                    "last_activity",
                    0
                )
            ),
        reverse=True
    )

    return sessions


# ============================================================
# TOUCH / UPDATE ACTIVITY
# ============================================================

def touch_session(
    session_id,
    metadata=None
):

    session_id = normalize_session_id(
        session_id
    )

    state = load_state()

    session = state[
        "sessions"
    ].get(
        session_id
    )

    if session is None:

        return {
            "status":
                "NOT_FOUND",

            "session_id":
                session_id
        }

    now = time.time()

    session[
        "last_activity"
    ] = now

    session[
        "last_activity_iso"
    ] = utc_now_iso()

    session[
        "interaction_count"
    ] = int(
        session.get(
            "interaction_count",
            0
        )
    ) + 1

    # A touched session becomes active again.

    session[
        "status"
    ] = "ACTIVE"

    session[
        "expired"
    ] = False

    session[
        "expired_at"
    ] = None

    session[
        "expiration_reason"
    ] = None

    if isinstance(
        metadata,
        dict
    ):

        session.setdefault(
            "metadata",
            {}
        )

        session[
            "metadata"
        ].update(
            metadata
        )

    save_state(
        state
    )

    return {
        "status":
            "TOUCHED",

        "session_id":
            session_id,

        "interaction_count":
            session[
                "interaction_count"
            ]
    }


# ============================================================
# UPDATE ACTIVITY
#
# Compatibility alias.
# ============================================================

def update_session_activity(
    session_id,
    metadata=None
):

    return touch_session(
        session_id,
        metadata=metadata
    )


# ============================================================
# CHECK EXPIRATION
# ============================================================

def is_expired(
    session_id,
    now=None
):

    session = get_session(
        session_id
    )

    if session is None:

        return True

    if session.get(
        "expired",
        False
    ):

        return True

    if now is None:

        now = time.time()

    last_activity = float(
        session.get(
            "last_activity",
            session.get(
                "created_at",
                now
            )
        )
    )

    ttl_seconds = int(
        session.get(
            "ttl_seconds",
            DEFAULT_TTL_SECONDS
        )
    )

    age = (
        float(
            now
        )
        -
        last_activity
    )

    return (
        age
        >=
        ttl_seconds
    )


# ============================================================
# EXPIRE SESSION
# ============================================================

def expire_session(
    session_id,
    reason="TTL_EXPIRED"
):

    session_id = normalize_session_id(
        session_id
    )

    state = load_state()

    session = state[
        "sessions"
    ].get(
        session_id
    )

    if session is None:

        return {
            "status":
                "NOT_FOUND",

            "session_id":
                session_id
        }

    if session.get(
        "expired"
    ):

        return {
            "status":
                "ALREADY_EXPIRED",

            "session_id":
                session_id
        }

    now = time.time()

    session[
        "status"
    ] = "EXPIRED"

    session[
        "expired"
    ] = True

    session[
        "expired_at"
    ] = now

    session[
        "expired_at_iso"
    ] = utc_now_iso()

    session[
        "expiration_reason"
    ] = str(
        reason
    )

    save_state(
        state
    )

    return {
        "status":
            "EXPIRED",

        "session_id":
            session_id,

        "reason":
            reason
    }


# ============================================================
# EXPIRE OLD SESSIONS
# ============================================================

def expire_old_sessions(
    now=None
):

    if now is None:

        now = time.time()

    sessions = list_sessions(
        include_expired=False
    )

    expired = []

    for session in sessions:

        session_id = session.get(
            "session_id"
        )

        if not session_id:

            continue

        if is_expired(
            session_id,
            now=now
        ):

            result = expire_session(
                session_id,
                reason="TTL_EXPIRED"
            )

            if (
                result.get(
                    "status"
                )
                ==
                "EXPIRED"
            ):

                expired.append(
                    session_id
                )

    return {
        "status":
            "LIFECYCLE_CHECK_COMPLETE",

        "expired_count":
            len(
                expired
            ),

        "expired_sessions":
            expired
    }


# ============================================================
# CLEANUP EXPIRED RECORDS
# ============================================================

def cleanup_expired_sessions(
    older_than_seconds=24 * 60 * 60
):

    older_than_seconds = int(
        older_than_seconds
    )

    state = load_state()

    now = time.time()

    removed = []

    sessions = list(
        state[
            "sessions"
        ].items()
    )

    for session_id, session in sessions:

        if not session.get(
            "expired",
            False
        ):

            continue

        expired_at = float(
            session.get(
                "expired_at",
                now
            )
        )

        age = (
            now
            -
            expired_at
        )

        if age < older_than_seconds:

            continue

        del state[
            "sessions"
        ][
            session_id
        ]

        removed.append(
            session_id
        )

    save_state(
        state
    )

    return {
        "status":
            "CLEANUP_COMPLETE",

        "removed_count":
            len(
                removed
            ),

        "removed_sessions":
            removed
    }


# ============================================================
# REMOVE ONE SESSION RECORD
# ============================================================

def remove_session(
    session_id
):

    session_id = normalize_session_id(
        session_id
    )

    state = load_state()

    if (
        session_id
        not in
        state[
            "sessions"
        ]
    ):

        return {
            "status":
                "NOT_FOUND",

            "session_id":
                session_id
        }

    del state[
        "sessions"
    ][
        session_id
    ]

    save_state(
        state
    )

    return {
        "status":
            "REMOVED",

        "session_id":
            session_id
    }


# ============================================================
# SESSION STATUS
# ============================================================

def session_status(
    session_id
):

    session = get_session(
        session_id
    )

    if session is None:

        return {
            "status":
                "NOT_FOUND",

            "session_id":
                str(
                    session_id
                )
        }

    expired = is_expired(
        session_id
    )

    now = time.time()

    last_activity = float(
        session.get(
            "last_activity",
            now
        )
    )

    age = max(
        0.0,
        now
        -
        last_activity
    )

    ttl = int(
        session.get(
            "ttl_seconds",
            DEFAULT_TTL_SECONDS
        )
    )

    remaining = max(
        0.0,
        ttl
        -
        age
    )

    return {
        "status":
            (
                "EXPIRED"
                if expired
                else
                "ACTIVE"
            ),

        "session_id":
            session_id,

        "profile":
            session.get(
                "profile"
            ),

        "interaction_count":
            session.get(
                "interaction_count",
                0
            ),

        "age_seconds":
            round(
                age,
                2
            ),

        "ttl_seconds":
            ttl,

        "remaining_seconds":
            round(
                remaining,
                2
            )
    }


# ============================================================
# LIFECYCLE MANAGER CLASS
#
# Compatibility wrapper for other Sentinel modules.
# ============================================================

class LifecycleManager:

    def __init__(
        self,
        default_ttl_seconds=DEFAULT_TTL_SECONDS
    ):

        self.default_ttl_seconds = int(
            default_ttl_seconds
        )

        ensure_storage()


    def register(
        self,
        session_id,
        profile=None,
        metadata=None,
        ttl_seconds=None
    ):

        if ttl_seconds is None:

            ttl_seconds = (
                self.default_ttl_seconds
            )

        return register_session(
            session_id=session_id,
            profile=profile,
            ttl_seconds=ttl_seconds,
            metadata=metadata
        )


    def create(
        self,
        session_id,
        profile=None,
        metadata=None,
        ttl_seconds=None
    ):

        return self.register(
            session_id=session_id,
            profile=profile,
            metadata=metadata,
            ttl_seconds=ttl_seconds
        )


    def touch(
        self,
        session_id,
        metadata=None
    ):

        return touch_session(
            session_id,
            metadata=metadata
        )


    def get(
        self,
        session_id
    ):

        return get_session(
            session_id
        )


    def status(
        self,
        session_id
    ):

        return session_status(
            session_id
        )


    def expire(
        self,
        session_id,
        reason="MANUAL_EXPIRE"
    ):

        return expire_session(
            session_id,
            reason=reason
        )


    def expire_old(
        self
    ):

        return expire_old_sessions()


    def cleanup(
        self,
        older_than_seconds=24 * 60 * 60
    ):

        return cleanup_expired_sessions(
            older_than_seconds
        )


# ============================================================
# ALIAS
# ============================================================

SessionLifecycleManager = LifecycleManager


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    ensure_storage()

    test_id = (
        "sentinel_lifecycle_self_test"
    )

    # Clean previous test.

    remove_session(
        test_id
    )

    registered = register_session(
        test_id,
        profile="SELF_TEST",
        ttl_seconds=2,
        metadata={
            "test":
                True
        }
    )

    touched = touch_session(
        test_id
    )

    current = get_session(
        test_id
    )

    active_before_expiration = (
        current is not None
        and
        not is_expired(
            test_id
        )
    )

    manually_expired = expire_session(
        test_id,
        reason="SELF_TEST"
    )

    expired_after = is_expired(
        test_id
    )

    removed = remove_session(
        test_id
    )

    passed = all(
        [
            registered.get(
                "status"
            )
            in (
                "REGISTERED",
                "UPDATED"
            ),

            touched.get(
                "status"
            )
            ==
            "TOUCHED",

            active_before_expiration,

            manually_expired.get(
                "status"
            )
            in (
                "EXPIRED",
                "ALREADY_EXPIRED"
            ),

            expired_after,

            removed.get(
                "status"
            )
            ==
            "REMOVED"
        ]
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
            LIFECYCLE_VERSION,

        "storage":
            LIFECYCLE_FILE,

        "features":
            {

                "persistent_sessions":
                    True,

                "session_touch":
                    True,

                "ttl_expiration":
                    True,

                "manual_expiration":
                    True,

                "expired_cleanup":
                    True
            },

        "safety":
            {

                "shell_execution":
                    False,

                "payload_execution":
                    False,

                "sudo_execution":
                    False,

                "host_modification":
                    False
            }
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    import pprint

    pprint.pp(
        self_test()
    )

# ============================================================
# SENTINEL PHOENIX - LEGACY LIFECYCLE COMPATIBILITY
# ============================================================

_lifecycle_manager_singleton = None


def start_lifecycle_manager():
    global _lifecycle_manager_singleton

    if _lifecycle_manager_singleton is None:
        _lifecycle_manager_singleton = LifecycleManager()

    return _lifecycle_manager_singleton

