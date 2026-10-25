import json
import os
import shutil

from core.integrity import (
    BASE_DIR,
    BASELINE_FILE,
    SNAPSHOT_DIR,
    create_recovery_snapshot,
    ensure_directories,
    list_snapshots,
    load_baseline,
    log_event,
    safe_snapshot_id,
    sha256_file,
    verify_integrity,
    verify_snapshot
)


# ============================================================
# SENTINEL PHOENIX
# RECOVERY GUARD V2
# ============================================================


def _safe_core_path(relative_path):
    """
    Empêche toute restauration en dehors de core/.
    """

    if not isinstance(
        relative_path,
        str
    ):
        return False

    normalized = os.path.normpath(
        relative_path
    )

    if os.path.isabs(
        normalized
    ):
        return False

    if normalized.startswith(
        ".."
    ):
        return False

    if not normalized.startswith(
        "core" + os.sep
    ):
        return False

    destination = os.path.abspath(
        os.path.join(
            BASE_DIR,
            normalized
        )
    )

    core_root = os.path.abspath(
        os.path.join(
            BASE_DIR,
            "core"
        )
    )

    try:

        common = os.path.commonpath(
            [
                core_root,
                destination
            ]
        )

    except ValueError:

        return False

    return common == core_root


# ============================================================
# SNAPSHOT METADATA
# ============================================================

def load_snapshot_metadata(
    identifier
):

    if not safe_snapshot_id(
        identifier
    ):

        return None

    metadata_file = os.path.join(
        SNAPSHOT_DIR,
        identifier,
        "snapshot.json"
    )

    if not os.path.isfile(
        metadata_file
    ):

        return None

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

        return None

    return metadata


# ============================================================
# SNAPSHOT VS TRUSTED BASELINE
# ============================================================

def snapshot_matches_baseline(
    identifier
):

    baseline = load_baseline()

    if baseline is None:

        return {
            "match": False,
            "reason":
                "NO_BASELINE"
        }

    validation = verify_snapshot(
        identifier
    )

    if not validation.get(
        "valid",
        False
    ):

        return {
            "match": False,
            "reason":
                validation.get(
                    "reason",
                    "INVALID_SNAPSHOT"
                )
        }

    metadata = load_snapshot_metadata(
        identifier
    )

    if metadata is None:

        return {
            "match": False,
            "reason":
                "INVALID_SNAPSHOT_METADATA"
        }

    baseline_files = baseline.get(
        "files",
        {}
    )

    snapshot_files = metadata.get(
        "files",
        {}
    )

    # Le snapshot sain doit contenir
    # exactement l'ensemble attendu.

    if (
        set(
            baseline_files.keys()
        )
        !=
        set(
            snapshot_files.keys()
        )
    ):

        return {
            "match": False,
            "reason":
                "FILE_SET_MISMATCH"
        }

    mismatches = []

    for relative_path, expected in baseline_files.items():

        if not _safe_core_path(
            relative_path
        ):

            return {
                "match": False,
                "reason":
                    "UNSAFE_BASELINE_PATH",

                "file":
                    relative_path
            }

        snapshot_entry = snapshot_files.get(
            relative_path,
            {}
        )

        if (
            expected.get(
                "sha256"
            )
            !=
            snapshot_entry.get(
                "sha256"
            )
        ):

            mismatches.append(
                relative_path
            )

    if mismatches:

        return {
            "match": False,

            "reason":
                "HASH_MISMATCH",

            "mismatches":
                mismatches
        }

    return {
        "match": True,

        "reason":
            "SNAPSHOT_MATCHES_BASELINE",

        "snapshot_id":
            identifier,

        "files":
            len(
                baseline_files
            )
    }


# ============================================================
# TRUSTED SNAPSHOTS
# ============================================================

def find_trusted_snapshots():

    trusted = []

    for snapshot in list_snapshots():

        identifier = snapshot.get(
            "snapshot_id"
        )

        if not identifier:
            continue

        result = snapshot_matches_baseline(
            identifier
        )

        if result.get(
            "match",
            False
        ):

            trusted.append(
                {
                    "snapshot_id":
                        identifier,

                    "created_at":
                        snapshot.get(
                            "created_at"
                        ),

                    "note":
                        snapshot.get(
                            "note"
                        ),

                    "files":
                        snapshot.get(
                            "files"
                        )
                }
            )

    return trusted


def latest_trusted_snapshot():

    snapshots = find_trusted_snapshots()

    if not snapshots:

        return None

    # list_snapshots() est déjà trié
    # du plus récent au plus ancien.

    return snapshots[0]


# ============================================================
# RECOVERY PLAN
# ============================================================

def build_recovery_plan():

    integrity = verify_integrity(
        log_result=False
    )

    if integrity.get(
        "clean",
        False
    ):

        return {
            "status":
                "CLEAN",

            "recovery_required":
                False,

            "reason":
                "NO_RECOVERY_REQUIRED",

            "modified":
                [],

            "missing":
                [],

            "unexpected":
                [],

            "trusted_snapshot":
                None
        }

    modified_entries = integrity.get(
        "modified",
        []
    )

    modified_files = [
        item.get(
            "file"
        )
        for item
        in modified_entries
        if item.get(
            "file"
        )
    ]

    missing_files = integrity.get(
        "missing",
        []
    )

    unexpected_files = integrity.get(
        "unexpected",
        []
    )

    files_to_restore = []

    for relative_path in (
        modified_files
        +
        missing_files
    ):

        if (
            relative_path
            not in files_to_restore
        ):

            files_to_restore.append(
                relative_path
            )

    trusted = latest_trusted_snapshot()

    if trusted is None:

        return {
            "status":
                "RECOVERY_BLOCKED",

            "recovery_required":
                True,

            "reason":
                "NO_TRUSTED_SNAPSHOT",

            "modified":
                modified_files,

            "missing":
                missing_files,

            "unexpected":
                unexpected_files,

            "files_to_restore":
                files_to_restore,

            "trusted_snapshot":
                None
        }

    unsafe_paths = [
        path
        for path
        in files_to_restore
        if not _safe_core_path(
            path
        )
    ]

    if unsafe_paths:

        return {
            "status":
                "RECOVERY_BLOCKED",

            "recovery_required":
                True,

            "reason":
                "UNSAFE_RECOVERY_PATH",

            "unsafe_paths":
                unsafe_paths,

            "trusted_snapshot":
                trusted.get(
                    "snapshot_id"
                )
        }

    return {
        "status":
            "RECOVERY_AVAILABLE",

        "recovery_required":
            True,

        "reason":
            "TRUSTED_SNAPSHOT_FOUND",

        "modified":
            modified_files,

        "missing":
            missing_files,

        "unexpected":
            unexpected_files,

        "files_to_restore":
            files_to_restore,

        "trusted_snapshot":
            trusted.get(
                "snapshot_id"
            ),

        "trusted_snapshot_note":
            trusted.get(
                "note"
            ),

        "automatic_unexpected_file_deletion":
            False,

        "confirmation_required":
            True
    }


# ============================================================
# RESTORE ONE FILE
# ============================================================

def _restore_file(
    snapshot_id,
    relative_path
):

    if not _safe_core_path(
        relative_path
    ):

        return {
            "restored": False,

            "file":
                relative_path,

            "reason":
                "UNSAFE_PATH"
        }

    relative_inside_core = os.path.relpath(
        relative_path,
        "core"
    )

    source = os.path.join(
        SNAPSHOT_DIR,
        snapshot_id,
        "core",
        relative_inside_core
    )

    destination = os.path.join(
        BASE_DIR,
        relative_path
    )

    if not os.path.isfile(
        source
    ):

        return {
            "restored": False,

            "file":
                relative_path,

            "reason":
                "SNAPSHOT_FILE_MISSING"
        }

    os.makedirs(
        os.path.dirname(
            destination
        ),
        exist_ok=True
    )

    temporary_file = (
        destination
        +
        ".phoenix-recovery"
    )

    shutil.copy2(
        source,
        temporary_file
    )

    os.replace(
        temporary_file,
        destination
    )

    return {
        "restored": True,

        "file":
            relative_path,

        "sha256":
            sha256_file(
                destination
            )
    }


# ============================================================
# CONTROLLED RECOVERY
# ============================================================

def repair_from_trusted_snapshot(
    confirm=False
):
    """
    Restauration contrôlée.

    confirm=False :
        aucun fichier n'est modifié.

    confirm=True :
        - vérification de la baseline
        - sélection d'un snapshot sain
        - snapshot de sécurité
        - restauration des fichiers modifiés/manquants
        - vérification finale

    Les fichiers inattendus ne sont JAMAIS
    supprimés automatiquement.
    """

    ensure_directories()

    plan = build_recovery_plan()

    if (
        not plan.get(
            "recovery_required",
            False
        )
    ):

        return {
            "repaired": False,

            "reason":
                "NO_RECOVERY_REQUIRED",

            "integrity_status":
                "CLEAN"
        }

    if (
        plan.get(
            "status"
        )
        !=
        "RECOVERY_AVAILABLE"
    ):

        log_event(
            "RECOVERY_BLOCKED",
            plan
        )

        return {
            "repaired": False,

            "reason":
                plan.get(
                    "reason"
                ),

            "plan":
                plan
        }

    if not confirm:

        return {
            "repaired": False,

            "reason":
                "CONFIRMATION_REQUIRED",

            "plan":
                plan
        }

    snapshot_id = plan.get(
        "trusted_snapshot"
    )

    # Vérifie encore le snapshot juste
    # avant toute modification.

    trusted_check = (
        snapshot_matches_baseline(
            snapshot_id
        )
    )

    if not trusted_check.get(
        "match",
        False
    ):

        log_event(
            "RECOVERY_BLOCKED",
            {
                "reason":
                    "TRUSTED_SNAPSHOT_RECHECK_FAILED",

                "snapshot_id":
                    snapshot_id,

                "details":
                    trusted_check
            }
        )

        return {
            "repaired": False,

            "reason":
                "TRUSTED_SNAPSHOT_RECHECK_FAILED"
        }

    # ========================================================
    # SAFETY SNAPSHOT
    # ========================================================

    safety_snapshot = (
        create_recovery_snapshot(
            note=(
                "pre-recovery safety snapshot"
            )
        )
    )

    restored = []

    failed = []

    for relative_path in plan.get(
        "files_to_restore",
        []
    ):

        result = _restore_file(
            snapshot_id,
            relative_path
        )

        if result.get(
            "restored",
            False
        ):

            restored.append(
                result
            )

        else:

            failed.append(
                result
            )

    # ========================================================
    # FINAL VERIFICATION
    # ========================================================

    final_integrity = (
        verify_integrity(
            log_result=True
        )
    )

    clean = final_integrity.get(
        "clean",
        False
    )

    if clean:

        status = (
            "RECOVERY_SUCCESS"
        )

    elif (
        not final_integrity.get(
            "modified"
        )
        and
        not final_integrity.get(
            "missing"
        )
        and
        final_integrity.get(
            "unexpected"
        )
    ):

        status = (
            "RECOVERY_PARTIAL_UNEXPECTED_FILES_REMAIN"
        )

    else:

        status = (
            "RECOVERY_INCOMPLETE"
        )

    log_event(
        status,
        {
            "trusted_snapshot":
                snapshot_id,

            "safety_snapshot":
                safety_snapshot.get(
                    "snapshot_id"
                ),

            "restored_files":
                [
                    item.get(
                        "file"
                    )
                    for item
                    in restored
                ],

            "failed":
                failed,

            "final_status":
                final_integrity.get(
                    "status"
                )
        }
    )

    return {
        "repaired":
            clean,

        "status":
            status,

        "trusted_snapshot":
            snapshot_id,

        "safety_snapshot":
            safety_snapshot.get(
                "snapshot_id"
            ),

        "restored":
            restored,

        "failed":
            failed,

        "final_integrity":
            final_integrity,

        "unexpected_files_removed":
            False
    }


# ============================================================
# RECOVERY STATUS
# ============================================================

def recovery_status():

    integrity = verify_integrity(
        log_result=False
    )

    trusted = find_trusted_snapshots()

    plan = build_recovery_plan()

    return {
        "integrity":
            integrity.get(
                "status"
            ),

        "clean":
            integrity.get(
                "clean",
                False
            ),

        "trusted_snapshots":
            len(
                trusted
            ),

        "latest_trusted_snapshot":
            (
                trusted[0].get(
                    "snapshot_id"
                )
                if trusted
                else
                None
            ),

        "recovery_plan":
            plan
    }