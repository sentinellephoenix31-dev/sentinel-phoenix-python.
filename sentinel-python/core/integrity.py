import hashlib
import json
import os
import re
import shutil

from datetime import datetime, timezone


# ============================================================
# SENTINEL PHOENIX
# RECOVERY & INTEGRITY CORE V1
# ============================================================


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

CORE_DIR = os.path.join(
    BASE_DIR,
    "core"
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

RECOVERY_DIR = os.path.join(
    DATA_DIR,
    "phoenix_recovery"
)

SNAPSHOT_DIR = os.path.join(
    RECOVERY_DIR,
    "snapshots"
)

BASELINE_FILE = os.path.join(
    RECOVERY_DIR,
    "integrity_baseline.json"
)

EVENT_LOG = os.path.join(
    RECOVERY_DIR,
    "integrity_events.jsonl"
)


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def snapshot_id():

    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )


def safe_snapshot_id(
    value
):

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9_-]{8,64}",
            str(value)
        )
    )


def ensure_directories():

    os.makedirs(
        RECOVERY_DIR,
        exist_ok=True
    )

    os.makedirs(
        SNAPSHOT_DIR,
        exist_ok=True
    )


def log_event(
    event_type,
    details
):

    ensure_directories()

    event = {
        "timestamp":
            utc_now(),

        "event":
            event_type,

        "details":
            details
    }

    with open(
        EVENT_LOG,
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
# HASH
# ============================================================

def sha256_file(
    path
):

    digest = hashlib.sha256()

    with open(
        path,
        "rb"
    ) as file:

        while True:

            block = file.read(
                65536
            )

            if not block:
                break

            digest.update(
                block
            )

    return digest.hexdigest()


# ============================================================
# DISCOVERY
# ============================================================

def discover_core_files():

    files = []

    for root, directories, filenames in os.walk(
        CORE_DIR
    ):

        directories[:] = [
            directory
            for directory
            in directories
            if directory != "__pycache__"
        ]

        for filename in filenames:

            if not filename.endswith(
                ".py"
            ):
                continue

            full_path = os.path.join(
                root,
                filename
            )

            relative_path = os.path.relpath(
                full_path,
                BASE_DIR
            )

            files.append(
                relative_path
            )

    return sorted(
        files
    )


# ============================================================
# MANIFEST
# ============================================================

def build_manifest():

    manifest = {}

    for relative_path in discover_core_files():

        full_path = os.path.join(
            BASE_DIR,
            relative_path
        )

        manifest[
            relative_path
        ] = {
            "sha256":
                sha256_file(
                    full_path
                ),

            "size":
                os.path.getsize(
                    full_path
                )
        }

    return manifest


# ============================================================
# BASELINE
# ============================================================

def create_baseline(
    replace=False
):

    """
    Crée la baseline de confiance.

    Elle n'est PAS remplacée automatiquement.
    """

    ensure_directories()

    if (
        os.path.exists(
            BASELINE_FILE
        )
        and
        not replace
    ):

        return {
            "created": False,
            "reason":
                "BASELINE_ALREADY_EXISTS"
        }

    manifest = (
        build_manifest()
    )

    baseline = {
        "version":
            "1.0",

        "created_at":
            utc_now(),

        "tracked_files":
            len(
                manifest
            ),

        "files":
            manifest
    }

    temporary_file = (
        BASELINE_FILE
        +
        ".tmp"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            baseline,
            file,
            indent=2,
            ensure_ascii=False
        )

    os.replace(
        temporary_file,
        BASELINE_FILE
    )

    log_event(
        "BASELINE_CREATED",
        {
            "tracked_files":
                len(
                    manifest
                ),

            "replace":
                replace
        }
    )

    return {
        "created": True,

        "tracked_files":
            len(
                manifest
            ),

        "baseline_file":
            BASELINE_FILE
    }


def load_baseline():

    if not os.path.exists(
        BASELINE_FILE
    ):

        return None

    try:

        with open(
            BASELINE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(
                file
            )

    except (
        OSError,
        json.JSONDecodeError
    ):

        return None


# ============================================================
# INTEGRITY VERIFICATION
# ============================================================

def verify_integrity(
    log_result=True
):

    baseline = (
        load_baseline()
    )

    if baseline is None:

        return {
            "status":
                "NO_BASELINE",

            "clean":
                False,

            "modified":
                [],

            "missing":
                [],

            "unexpected":
                []
        }

    baseline_files = baseline.get(
        "files",
        {}
    )

    current_files = (
        build_manifest()
    )

    modified = []

    missing = []

    unexpected = []

    for relative_path, expected in baseline_files.items():

        current = current_files.get(
            relative_path
        )

        if current is None:

            missing.append(
                relative_path
            )

            continue

        if (
            current.get(
                "sha256"
            )
            !=
            expected.get(
                "sha256"
            )
        ):

            modified.append(
                {
                    "file":
                        relative_path,

                    "expected":
                        expected.get(
                            "sha256"
                        ),

                    "current":
                        current.get(
                            "sha256"
                        )
                }
            )

    for relative_path in current_files:

        if relative_path not in baseline_files:

            unexpected.append(
                relative_path
            )

    clean = (
        not modified
        and
        not missing
        and
        not unexpected
    )

    status = (
        "CLEAN"
        if clean
        else
        "CHANGED"
    )

    result = {
        "status":
            status,

        "clean":
            clean,

        "tracked_files":
            len(
                baseline_files
            ),

        "current_files":
            len(
                current_files
            ),

        "modified":
            modified,

        "missing":
            missing,

        "unexpected":
            unexpected
    }

    if log_result:

        log_event(
            "INTEGRITY_CHECK",
            {
                "status":
                    status,

                "modified_count":
                    len(
                        modified
                    ),

                "missing_count":
                    len(
                        missing
                    ),

                "unexpected_count":
                    len(
                        unexpected
                    )
            }
        )

    return result


# ============================================================
# RECOVERY SNAPSHOT
# ============================================================

def create_recovery_snapshot(
    note="manual"
):

    ensure_directories()

    identifier = (
        snapshot_id()
    )

    destination = os.path.join(
        SNAPSHOT_DIR,
        identifier
    )

    snapshot_core = os.path.join(
        destination,
        "core"
    )

    os.makedirs(
        snapshot_core,
        exist_ok=False
    )

    files = (
        discover_core_files()
    )

    manifest = {}

    for relative_path in files:

        source = os.path.join(
            BASE_DIR,
            relative_path
        )

        relative_inside_core = os.path.relpath(
            source,
            CORE_DIR
        )

        target = os.path.join(
            snapshot_core,
            relative_inside_core
        )

        os.makedirs(
            os.path.dirname(
                target
            ),
            exist_ok=True
        )

        shutil.copy2(
            source,
            target
        )

        manifest[
            relative_path
        ] = {
            "sha256":
                sha256_file(
                    target
                ),

            "size":
                os.path.getsize(
                    target
                )
        }

    metadata = {
        "snapshot_id":
            identifier,

        "created_at":
            utc_now(),

        "note":
            str(
                note
            )[:200],

        "files":
            manifest
    }

    metadata_file = os.path.join(
        destination,
        "snapshot.json"
    )

    with open(
        metadata_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metadata,
            file,
            indent=2,
            ensure_ascii=False
        )

    log_event(
        "RECOVERY_SNAPSHOT_CREATED",
        {
            "snapshot_id":
                identifier,

            "files":
                len(
                    manifest
                ),

            "note":
                str(
                    note
                )[:200]
        }
    )

    return {
        "created":
            True,

        "snapshot_id":
            identifier,

        "files":
            len(
                manifest
            ),

        "path":
            destination
    }


# ============================================================
# SNAPSHOT LIST
# ============================================================

def list_snapshots():

    ensure_directories()

    results = []

    for identifier in sorted(
        os.listdir(
            SNAPSHOT_DIR
        ),
        reverse=True
    ):

        if not safe_snapshot_id(
            identifier
        ):
            continue

        directory = os.path.join(
            SNAPSHOT_DIR,
            identifier
        )

        metadata_file = os.path.join(
            directory,
            "snapshot.json"
        )

        if not os.path.isfile(
            metadata_file
        ):
            continue

        try:

            with open(
                metadata_file,
                "r",
                encoding="utf-8"
            ) as file:

                metadata = json.load(
                    file
                )

        except (
            OSError,
            json.JSONDecodeError
        ):

            continue

        results.append(
            {
                "snapshot_id":
                    identifier,

                "created_at":
                    metadata.get(
                        "created_at"
                    ),

                "note":
                    metadata.get(
                        "note"
                    ),

                "files":
                    len(
                        metadata.get(
                            "files",
                            {}
                        )
                    )
            }
        )

    return results


# ============================================================
# SNAPSHOT VERIFICATION
# ============================================================

def verify_snapshot(
    identifier
):

    if not safe_snapshot_id(
        identifier
    ):

        return {
            "valid": False,
            "reason":
                "INVALID_SNAPSHOT_ID"
        }

    directory = os.path.join(
        SNAPSHOT_DIR,
        identifier
    )

    metadata_file = os.path.join(
        directory,
        "snapshot.json"
    )

    if not os.path.isfile(
        metadata_file
    ):

        return {
            "valid": False,
            "reason":
                "SNAPSHOT_NOT_FOUND"
        }

    try:

        with open(
            metadata_file,
            "r",
            encoding="utf-8"
        ) as file:

            metadata = json.load(
                file
            )

    except (
        OSError,
        json.JSONDecodeError
    ):

        return {
            "valid": False,
            "reason":
                "INVALID_METADATA"
        }

    corrupted = []

    missing = []

    for relative_path, expected in metadata.get(
        "files",
        {}
    ).items():

        relative_inside_core = (
            relative_path.removeprefix(
                "core/"
            )
        )

        snapshot_file = os.path.join(
            directory,
            "core",
            relative_inside_core
        )

        if not os.path.isfile(
            snapshot_file
        ):

            missing.append(
                relative_path
            )

            continue

        current_hash = sha256_file(
            snapshot_file
        )

        if (
            current_hash
            !=
            expected.get(
                "sha256"
            )
        ):

            corrupted.append(
                relative_path
            )

    valid = (
        not corrupted
        and
        not missing
    )

    return {
        "valid":
            valid,

        "snapshot_id":
            identifier,

        "files":
            len(
                metadata.get(
                    "files",
                    {}
                )
            ),

        "corrupted":
            corrupted,

        "missing":
            missing,

        "reason":
            (
                "SNAPSHOT_VALID"
                if valid
                else
                "SNAPSHOT_DAMAGED"
            )
    }


# ============================================================
# RESTORE PLAN
# ============================================================

def restore_snapshot(
    identifier,
    confirm=False
):

    """
    Le mode par défaut est NON destructif.

    confirm=False :
        affiche uniquement le plan.

    confirm=True :
        restaure le snapshot après :
        - validation du snapshot
        - création d'un snapshot de sécurité
    """

    validation = (
        verify_snapshot(
            identifier
        )
    )

    if not validation.get(
        "valid",
        False
    ):

        return {
            "restored": False,

            "reason":
                validation.get(
                    "reason"
                ),

            "validation":
                validation
        }

    if not confirm:

        return {
            "restored": False,

            "reason":
                "CONFIRMATION_REQUIRED",

            "snapshot_id":
                identifier,

            "files":
                validation.get(
                    "files",
                    0
                ),

            "would_create_safety_snapshot":
                True
        }

    # ========================================================
    # SAFETY SNAPSHOT BEFORE RESTORE
    # ========================================================

    safety_snapshot = (
        create_recovery_snapshot(
            note=(
                "automatic safety snapshot "
                "before restore"
            )
        )
    )

    directory = os.path.join(
        SNAPSHOT_DIR,
        identifier
    )

    metadata_file = os.path.join(
        directory,
        "snapshot.json"
    )

    with open(
        metadata_file,
        "r",
        encoding="utf-8"
    ) as file:

        metadata = json.load(
            file
        )

    restored_files = []

    for relative_path in metadata.get(
        "files",
        {}
    ):

        relative_inside_core = (
            relative_path.removeprefix(
                "core/"
            )
        )

        source = os.path.join(
            directory,
            "core",
            relative_inside_core
        )

        destination = os.path.join(
            BASE_DIR,
            relative_path
        )

        os.makedirs(
            os.path.dirname(
                destination
            ),
            exist_ok=True
        )

        temporary_file = (
            destination
            +
            ".phoenix-restore"
        )

        shutil.copy2(
            source,
            temporary_file
        )

        os.replace(
            temporary_file,
            destination
        )

        restored_files.append(
            relative_path
        )

    log_event(
        "RECOVERY_RESTORE",
        {
            "restored_snapshot":
                identifier,

            "safety_snapshot":
                safety_snapshot.get(
                    "snapshot_id"
                ),

            "restored_files":
                len(
                    restored_files
                )
        }
    )

    return {
        "restored": True,

        "reason":
            "SNAPSHOT_RESTORED",

        "snapshot_id":
            identifier,

        "safety_snapshot":
            safety_snapshot.get(
                "snapshot_id"
            ),

        "restored_files":
            len(
                restored_files
            )
    }


# ============================================================
# STATUS
# ============================================================

def integrity_status():

    baseline = (
        load_baseline()
    )

    verification = (
        verify_integrity(
            log_result=False
        )
    )

    snapshots = (
        list_snapshots()
    )

    return {
        "baseline_present":
            baseline is not None,

        "integrity_status":
            verification.get(
                "status"
            ),

        "clean":
            verification.get(
                "clean",
                False
            ),

        "modified":
            len(
                verification.get(
                    "modified",
                    []
                )
            ),

        "missing":
            len(
                verification.get(
                    "missing",
                    []
                )
            ),

        "unexpected":
            len(
                verification.get(
                    "unexpected",
                    []
                )
            ),

        "recovery_snapshots":
            len(
                snapshots
            )
    }