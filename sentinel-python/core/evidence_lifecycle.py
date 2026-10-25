import json
import os
import time
import hashlib
from datetime import datetime, timezone


# ============================================================
# SENTINEL PHOENIX
# EVIDENCE LIFECYCLE V1
#
# Temporary UNKNOWN-person evidence management.
#
# Safety goals:
# - evidence is local only
# - automatic expiration
# - owner can KEEP selected evidence
# - owner acknowledgment can delete immediately
# - maximum evidence count
# - maximum disk usage
# - no arbitrary paths can be deleted
# ============================================================


EVIDENCE_LIFECYCLE_VERSION = "1.0"


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

EVIDENCE_DIR = os.path.join(
    BASE_DIR,
    "data",
    "identity",
    "evidence"
)

INDEX_FILE = os.path.join(
    EVIDENCE_DIR,
    "evidence_index.json"
)


# ============================================================
# POLICY
# ============================================================

# Temporary evidence expires after 24 hours.

DEFAULT_TTL_SECONDS = 24 * 60 * 60


# Hard cap on number of temporary/kept images combined.

MAX_EVIDENCE_COUNT = 20


# Hard disk cap.

MAX_STORAGE_MB = 100


# If OWNER acknowledges evidence,
# delete immediately unless KEEP was selected.

DELETE_ON_ACKNOWLEDGE = True


SUPPORTED_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp"
)


# ============================================================
# UTILITIES
# ============================================================

def ensure_storage():

    os.makedirs(
        EVIDENCE_DIR,
        exist_ok=True
    )

    if not os.path.isfile(
        INDEX_FILE
    ):

        save_index(
            {
                "version":
                    EVIDENCE_LIFECYCLE_VERSION,

                "evidence":
                    {}
            }
        )


def utc_now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


def load_index():

    ensure_directory_only()

    if not os.path.isfile(
        INDEX_FILE
    ):

        return {
            "version":
                EVIDENCE_LIFECYCLE_VERSION,

            "evidence":
                {}
        }

    try:

        with open(
            INDEX_FILE,
            "r",
            encoding="utf-8"
        ) as handle:

            data = json.load(
                handle
            )

    except (
        json.JSONDecodeError,
        OSError
    ):

        data = {
            "version":
                EVIDENCE_LIFECYCLE_VERSION,

            "evidence":
                {}
        }

    if not isinstance(
        data.get(
            "evidence"
        ),
        dict
    ):

        data[
            "evidence"
        ] = {}

    return data


def save_index(
    data
):

    ensure_directory_only()

    temporary_file = (
        INDEX_FILE
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
        INDEX_FILE
    )


def ensure_directory_only():

    os.makedirs(
        EVIDENCE_DIR,
        exist_ok=True
    )


# ============================================================
# PATH SECURITY
# ============================================================

def safe_evidence_path(
    path
):

    if not path:

        return None

    candidate = os.path.realpath(
        path
    )

    evidence_root = os.path.realpath(
        EVIDENCE_DIR
    )

    try:

        common = os.path.commonpath(
            [
                candidate,
                evidence_root
            ]
        )

    except ValueError:

        return None

    if common != evidence_root:

        return None

    extension = os.path.splitext(
        candidate
    )[1].lower()

    if extension not in SUPPORTED_EXTENSIONS:

        return None

    return candidate


# ============================================================
# EVIDENCE ID
# ============================================================

def make_evidence_id(
    path
):

    name = os.path.basename(
        path
    )

    digest = hashlib.sha256(
        name.encode(
            "utf-8"
        )
    ).hexdigest()

    return digest[:16]


# ============================================================
# REGISTER
# ============================================================

def register_evidence(
    image_path,
    source="UNKNOWN_PERSON",
    metadata=None
):

    ensure_storage()

    safe_path = safe_evidence_path(
        image_path
    )

    if safe_path is None:

        return {
            "status":
                "DENIED",

            "reason":
                "INVALID_EVIDENCE_PATH"
        }

    if not os.path.isfile(
        safe_path
    ):

        return {
            "status":
                "NOT_FOUND",

            "reason":
                "EVIDENCE_FILE_NOT_FOUND"
        }

    index = load_index()

    evidence_id = make_evidence_id(
        safe_path
    )

    existing = index[
        "evidence"
    ].get(
        evidence_id
    )

    if existing:

        return {
            "status":
                "ALREADY_REGISTERED",

            "evidence_id":
                evidence_id,

            "record":
                existing
        }

    now = time.time()

    record = {

        "id":
            evidence_id,

        "filename":
            os.path.basename(
                safe_path
            ),

        "created_at":
            now,

        "created_at_iso":
            utc_now_iso(),

        "source":
            str(
                source
            ),

        "state":
            "TEMPORARY",

        "kept":
            False,

        "presented":
            False,

        "presented_at":
            None,

        "acknowledged":
            False,

        "acknowledged_at":
            None,

        "metadata":
            metadata
            if isinstance(
                metadata,
                dict
            )
            else {}
    }

    index[
        "evidence"
    ][
        evidence_id
    ] = record

    save_index(
        index
    )

    return {
        "status":
            "REGISTERED",

        "evidence_id":
            evidence_id,

        "record":
            record
    }


# ============================================================
# DISCOVER OLD / UNREGISTERED FILES
# ============================================================

def discover_evidence():

    ensure_storage()

    results = []

    for filename in os.listdir(
        EVIDENCE_DIR
    ):

        path = os.path.join(
            EVIDENCE_DIR,
            filename
        )

        if not os.path.isfile(
            path
        ):

            continue

        extension = os.path.splitext(
            filename
        )[1].lower()

        if extension not in SUPPORTED_EXTENSIONS:

            continue

        result = register_evidence(
            path
        )

        results.append(
            result
        )

    return results


# ============================================================
# GET RECORD
# ============================================================

def get_evidence(
    evidence_id
):

    index = load_index()

    record = index[
        "evidence"
    ].get(
        str(
            evidence_id
        )
    )

    if record is None:

        return {
            "status":
                "NOT_FOUND"
        }

    path = os.path.join(
        EVIDENCE_DIR,
        record[
            "filename"
        ]
    )

    return {
        "status":
            "FOUND",

        "record":
            record,

        "path":
            path,

        "exists":
            os.path.isfile(
                path
            )
    }


# ============================================================
# LIST
# ============================================================

def list_evidence():

    discover_evidence()

    index = load_index()

    records = list(
        index[
            "evidence"
        ].values()
    )

    records.sort(
        key=lambda item:
            float(
                item.get(
                    "created_at",
                    0
                )
            ),
        reverse=True
    )

    return records


# ============================================================
# MARK PRESENTED
# ============================================================

def mark_presented(
    evidence_id
):

    index = load_index()

    record = index[
        "evidence"
    ].get(
        str(
            evidence_id
        )
    )

    if record is None:

        return {
            "status":
                "NOT_FOUND"
        }

    record[
        "presented"
    ] = True

    record[
        "presented_at"
    ] = time.time()

    record[
        "state"
    ] = (
        "KEPT"
        if record.get(
            "kept"
        )
        else
        "PRESENTED"
    )

    save_index(
        index
    )

    return {
        "status":
            "PRESENTED",

        "evidence_id":
            evidence_id
    }


# ============================================================
# KEEP
# ============================================================

def keep_evidence(
    evidence_id
):

    index = load_index()

    record = index[
        "evidence"
    ].get(
        str(
            evidence_id
        )
    )

    if record is None:

        return {
            "status":
                "NOT_FOUND"
        }

    record[
        "kept"
    ] = True

    record[
        "state"
    ] = "KEPT"

    save_index(
        index
    )

    return {
        "status":
            "KEPT",

        "evidence_id":
            evidence_id
    }


# ============================================================
# RELEASE KEEP
# ============================================================

def release_evidence(
    evidence_id
):

    index = load_index()

    record = index[
        "evidence"
    ].get(
        str(
            evidence_id
        )
    )

    if record is None:

        return {
            "status":
                "NOT_FOUND"
        }

    record[
        "kept"
    ] = False

    record[
        "state"
    ] = "TEMPORARY"

    save_index(
        index
    )

    return {
        "status":
            "RELEASED",

        "evidence_id":
            evidence_id
    }


# ============================================================
# SECURE DELETE
# ============================================================

def delete_evidence(
    evidence_id,
    reason="OWNER_DELETE"
):

    index = load_index()

    evidence_id = str(
        evidence_id
    )

    record = index[
        "evidence"
    ].get(
        evidence_id
    )

    if record is None:

        return {
            "status":
                "NOT_FOUND"
        }

    path = os.path.join(
        EVIDENCE_DIR,
        record[
            "filename"
        ]
    )

    safe_path = safe_evidence_path(
        path
    )

    if safe_path is None:

        return {
            "status":
                "DENIED",

            "reason":
                "UNSAFE_PATH"
        }

    if os.path.isfile(
        safe_path
    ):

        try:

            os.remove(
                safe_path
            )

        except OSError as error:

            return {
                "status":
                    "ERROR",

                "reason":
                    str(
                        error
                    )
            }

    del index[
        "evidence"
    ][
        evidence_id
    ]

    save_index(
        index
    )

    return {
        "status":
            "DELETED",

        "evidence_id":
            evidence_id,

        "reason":
            reason
    }


# ============================================================
# OWNER ACKNOWLEDGMENT
# ============================================================

def acknowledge_evidence(
    evidence_id
):

    index = load_index()

    evidence_id = str(
        evidence_id
    )

    record = index[
        "evidence"
    ].get(
        evidence_id
    )

    if record is None:

        return {
            "status":
                "NOT_FOUND"
        }

    record[
        "acknowledged"
    ] = True

    record[
        "acknowledged_at"
    ] = time.time()

    record[
        "state"
    ] = "ACKNOWLEDGED"

    save_index(
        index
    )

    if (
        DELETE_ON_ACKNOWLEDGE
        and
        not record.get(
            "kept"
        )
    ):

        return delete_evidence(
            evidence_id,
            reason="OWNER_ACKNOWLEDGED"
        )

    return {
        "status":
            "ACKNOWLEDGED",

        "evidence_id":
            evidence_id
    }


# ============================================================
# STORAGE SIZE
# ============================================================

def current_storage_bytes():

    total = 0

    for record in list_evidence():

        path = os.path.join(
            EVIDENCE_DIR,
            record[
                "filename"
            ]
        )

        if os.path.isfile(
            path
        ):

            try:

                total += os.path.getsize(
                    path
                )

            except OSError:

                pass

    return total


# ============================================================
# CLEANUP
# ============================================================

def cleanup_evidence(
    ttl_seconds=DEFAULT_TTL_SECONDS
):

    discover_evidence()

    index = load_index()

    now = time.time()

    deleted = []

    expired = []


    # ========================================================
    # 1. TTL cleanup
    # ========================================================

    records = list(
        index[
            "evidence"
        ].items()
    )

    for evidence_id, record in records:

        if record.get(
            "kept"
        ):

            continue

        created_at = float(
            record.get(
                "created_at",
                now
            )
        )

        age = (
            now
            -
            created_at
        )

        if age >= ttl_seconds:

            result = delete_evidence(
                evidence_id,
                reason="TTL_EXPIRED"
            )

            if (
                result.get(
                    "status"
                )
                ==
                "DELETED"
            ):

                expired.append(
                    evidence_id
                )

                deleted.append(
                    evidence_id
                )


    # ========================================================
    # Reload after TTL cleanup
    # ========================================================

    index = load_index()

    records = list(
        index[
            "evidence"
        ].items()
    )


    # ========================================================
    # 2. Count limit
    #
    # Oldest non-kept evidence is removed first.
    # ========================================================

    if len(
        records
    ) > MAX_EVIDENCE_COUNT:

        removable = [

            (
                evidence_id,
                record
            )

            for evidence_id, record
            in records

            if not record.get(
                "kept"
            )
        ]

        removable.sort(
            key=lambda item:
                float(
                    item[
                        1
                    ].get(
                        "created_at",
                        0
                    )
                )
        )

        while (
            len(
                list_evidence()
            )
            >
            MAX_EVIDENCE_COUNT

            and

            removable
        ):

            evidence_id, _ = removable.pop(
                0
            )

            result = delete_evidence(
                evidence_id,
                reason="COUNT_LIMIT"
            )

            if (
                result.get(
                    "status"
                )
                ==
                "DELETED"
            ):

                deleted.append(
                    evidence_id
                )


    # ========================================================
    # 3. Disk-size limit
    # ========================================================

    maximum_bytes = (
        MAX_STORAGE_MB
        *
        1024
        *
        1024
    )

    while (
        current_storage_bytes()
        >
        maximum_bytes
    ):

        records = list_evidence()

        removable = [
            record
            for record in records
            if not record.get(
                "kept"
            )
        ]

        if not removable:

            break

        removable.sort(
            key=lambda record:
                float(
                    record.get(
                        "created_at",
                        0
                    )
                )
        )

        oldest = removable[
            0
        ]

        result = delete_evidence(
            oldest[
                "id"
            ],
            reason="STORAGE_LIMIT"
        )

        if (
            result.get(
                "status"
            )
            !=
            "DELETED"
        ):

            break

        deleted.append(
            oldest[
                "id"
            ]
        )


    return {

        "status":
            "CLEANUP_COMPLETE",

        "expired":
            expired,

        "deleted":
            list(
                dict.fromkeys(
                    deleted
                )
            ),

        "remaining":
            len(
                list_evidence()
            ),

        "storage_mb":
            round(
                current_storage_bytes()
                /
                (
                    1024
                    *
                    1024
                ),
                3
            )
    }


# ============================================================
# STATUS
# ============================================================

def evidence_status():

    records = list_evidence()

    temporary = sum(
        1
        for record in records
        if not record.get(
            "kept"
        )
    )

    kept = sum(
        1
        for record in records
        if record.get(
            "kept"
        )
    )

    return {

        "status":
            "ONLINE",

        "version":
            EVIDENCE_LIFECYCLE_VERSION,

        "total":
            len(
                records
            ),

        "temporary":
            temporary,

        "kept":
            kept,

        "storage_mb":
            round(
                current_storage_bytes()
                /
                (
                    1024
                    *
                    1024
                ),
                3
            ),

        "policy":
            {

                "ttl_hours":
                    DEFAULT_TTL_SECONDS
                    /
                    3600,

                "max_count":
                    MAX_EVIDENCE_COUNT,

                "max_storage_mb":
                    MAX_STORAGE_MB,

                "delete_on_acknowledge":
                    DELETE_ON_ACKNOWLEDGE
            }
    }


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    ensure_storage()

    safe_root = (
        safe_evidence_path(
            os.path.join(
                EVIDENCE_DIR,
                "test.jpg"
            )
        )
        is not None
    )

    unsafe_root = (
        safe_evidence_path(
            "/tmp/test.jpg"
        )
        is None
    )

    return {

        "status":
            (
                "PASS"
                if (
                    safe_root
                    and
                    unsafe_root
                )
                else
                "FAIL"
            ),

        "version":
            EVIDENCE_LIFECYCLE_VERSION,

        "evidence_directory":
            EVIDENCE_DIR,

        "path_guard":
            safe_root,

        "outside_path_blocked":
            unsafe_root,

        "policy":
            {

                "ttl_hours":
                    DEFAULT_TTL_SECONDS
                    /
                    3600,

                "max_evidence_count":
                    MAX_EVIDENCE_COUNT,

                "max_storage_mb":
                    MAX_STORAGE_MB,

                "owner_keep_supported":
                    True,

                "owner_acknowledge_supported":
                    True,

                "automatic_expiration":
                    True
            },

        "safety":
            {

                "local_storage_only":
                    True,

                "arbitrary_file_delete":
                    False,

                "shell_execution":
                    False,

                "internet_upload":
                    False
            }
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    import pprint

    pprint.pp(
        evidence_status()
    )