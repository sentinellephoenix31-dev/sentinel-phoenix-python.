import hashlib
import json
import os
import shutil

from datetime import datetime, timezone

from core.learning import (
    DATA_DIR,
    MODEL_FILE,
    load_model,
    load_training_rows,
    build_candidate_model,
    save_model,
    safe_float
)

from core.model_evaluation import (
    split_dataset,
    evaluate_model
)


# ============================================================
# SENTINEL PHOENIX
# MODEL PROMOTION + ROLLBACK ENGINE V1
# ============================================================


BACKUP_DIR = os.path.join(
    DATA_DIR,
    "model_backups"
)

PROMOTION_LOG = os.path.join(
    DATA_DIR,
    "model_promotions.jsonl"
)


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def timestamp_id():

    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )


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


def write_log(
    event_type,
    details
):

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    event = {

        "timestamp":
            utc_now(),

        "event":
            event_type,

        "details":
            details
    }

    with open(
        PROMOTION_LOG,
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
# MODEL VALIDATION
# ============================================================

def validate_model_file(
    path
):

    if not os.path.isfile(
        path
    ):

        return {
            "valid": False,
            "reason":
                "FILE_NOT_FOUND"
        }

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            model = json.load(
                file
            )

    except (
        OSError,
        json.JSONDecodeError
    ):

        return {
            "valid": False,
            "reason":
                "INVALID_JSON"
        }

    required = (
        "model_version",
        "status",
        "total_samples",
        "normal_profile",
        "dangerous_profile",
        "global_scales"
    )

    missing = [

        key

        for key
        in required

        if key not in model
    ]

    if missing:

        return {
            "valid": False,
            "reason":
                "MISSING_FIELDS",

            "missing":
                missing
        }

    if (
        model.get(
            "status"
        )
        !=
        "READY"
    ):

        return {
            "valid": False,
            "reason":
                "MODEL_NOT_READY"
        }

    return {

        "valid": True,

        "reason":
            "MODEL_VALID",

        "hash":
            sha256_file(
                path
            ),

        "version":
            model.get(
                "model_version"
            ),

        "samples":
            model.get(
                "total_samples",
                0
            )
    }


# ============================================================
# CHAMPION BACKUP
# ============================================================

def backup_current_champion():

    champion = load_model()

    if champion is None:

        return {
            "created": False,
            "reason":
                "NO_CHAMPION_MODEL"
        }

    validation = (
        validate_model_file(
            MODEL_FILE
        )
    )

    if not validation.get(
        "valid",
        False
    ):

        return {

            "created": False,

            "reason":
                validation.get(
                    "reason"
                )
        }

    os.makedirs(
        BACKUP_DIR,
        exist_ok=True
    )

    backup_name = (
        "champion_"
        +
        timestamp_id()
        +
        ".json"
    )

    backup_path = os.path.join(
        BACKUP_DIR,
        backup_name
    )

    shutil.copy2(
        MODEL_FILE,
        backup_path
    )

    backup_hash = sha256_file(
        backup_path
    )

    write_log(
        "CHAMPION_BACKUP_CREATED",
        {

            "backup":
                backup_name,

            "hash":
                backup_hash,

            "samples":
                champion.get(
                    "total_samples",
                    0
                ),

            "model_version":
                champion.get(
                    "model_version"
                )
        }
    )

    return {

        "created": True,

        "backup":
            backup_name,

        "path":
            backup_path,

        "hash":
            backup_hash
    }


# ============================================================
# BACKUPS
# ============================================================

def list_backups():

    if not os.path.isdir(
        BACKUP_DIR
    ):

        return []

    backups = []

    for filename in sorted(
        os.listdir(
            BACKUP_DIR
        ),
        reverse=True
    ):

        if (
            filename.startswith(
                "champion_"
            )
            and
            filename.endswith(
                ".json"
            )
        ):

            path = os.path.join(
                BACKUP_DIR,
                filename
            )

            validation = (
                validate_model_file(
                    path
                )
            )

            backups.append(
                {

                    "filename":
                        filename,

                    "valid":
                        validation.get(
                            "valid",
                            False
                        ),

                    "hash":
                        validation.get(
                            "hash"
                        ),

                    "samples":
                        validation.get(
                            "samples"
                        )
                }
            )

    return backups


# ============================================================
# CHAMPION VS CHALLENGER
# ============================================================

def evaluate_promotion_candidate():

    rows = load_training_rows()

    if len(rows) < 8:

        return {

            "status":
                "INSUFFICIENT_DATA",

            "total_samples":
                len(rows),

            "recommend_promotion":
                False
        }

    training_rows, validation_rows = (
        split_dataset(
            rows
        )
    )

    if len(
        validation_rows
    ) < 2:

        return {

            "status":
                "INSUFFICIENT_VALIDATION_DATA",

            "training_samples":
                len(
                    training_rows
                ),

            "validation_samples":
                len(
                    validation_rows
                ),

            "recommend_promotion":
                False
        }

    champion = load_model()

    if champion is None:

        return {

            "status":
                "NO_CHAMPION",

            "recommend_promotion":
                False
        }

    challenger_test = (
        build_candidate_model(
            training_rows
        )
    )

    champion_metrics = (
        evaluate_model(
            champion,
            validation_rows
        )
    )

    challenger_metrics = (
        evaluate_model(
            challenger_test,
            validation_rows
        )
    )

    champion_score = safe_float(
        champion_metrics.get(
            "security_score",
            0
        )
    )

    challenger_score = safe_float(
        challenger_metrics.get(
            "security_score",
            0
        )
    )

    champion_false_negatives = int(
        champion_metrics.get(
            "false_negative",
            0
        )
    )

    challenger_false_negatives = int(
        challenger_metrics.get(
            "false_negative",
            0
        )
    )

    recommend_promotion = False

    reasons = []

    if (
        challenger_test.get(
            "status"
        )
        !=
        "READY"
    ):

        reasons.append(
            "CHALLENGER_NOT_READY"
        )

    elif (
        challenger_false_negatives
        >
        champion_false_negatives
    ):

        reasons.append(
            "MORE_FALSE_NEGATIVES"
        )

    elif (
        challenger_score
        >
        champion_score
        +
        2
    ):

        recommend_promotion = True

        reasons.append(
            "SECURITY_SCORE_IMPROVED"
        )

    elif (
        challenger_score
        >=
        champion_score
        and
        challenger_false_negatives
        <
        champion_false_negatives
    ):

        recommend_promotion = True

        reasons.append(
            "FALSE_NEGATIVES_REDUCED"
        )

    else:

        reasons.append(
            "CHAMPION_REMAINS_BETTER_OR_EQUAL"
        )

    return {

        "status":
            "EVALUATED",

        "training_samples":
            len(
                training_rows
            ),

        "validation_samples":
            len(
                validation_rows
            ),

        "champion_security_score":
            champion_score,

        "challenger_security_score":
            challenger_score,

        "champion_false_negatives":
            champion_false_negatives,

        "challenger_false_negatives":
            challenger_false_negatives,

        "recommend_promotion":
            recommend_promotion,

        "reasons":
            reasons
    }


# ============================================================
# CONTROLLED PROMOTION
# ============================================================

def promote_challenger():

    """
    Promotion volontairement contrôlée.

    Aucun modèle n'est promu si les tests
    ne recommandent pas explicitement
    la promotion.
    """

    evaluation = (
        evaluate_promotion_candidate()
    )

    if (
        evaluation.get(
            "status"
        )
        !=
        "EVALUATED"
    ):

        return {

            "promoted": False,

            "reason":
                evaluation.get(
                    "status"
                ),

            "evaluation":
                evaluation
        }

    if not evaluation.get(
        "recommend_promotion",
        False
    ):

        write_log(
            "CHALLENGER_REJECTED",
            evaluation
        )

        return {

            "promoted": False,

            "reason":
                "CHAMPION_RETAINED",

            "evaluation":
                evaluation
        }

    # ========================================================
    # BACKUP BEFORE CHANGE
    # ========================================================

    backup = (
        backup_current_champion()
    )

    if not backup.get(
        "created",
        False
    ):

        return {

            "promoted": False,

            "reason":
                "CHAMPION_BACKUP_FAILED",

            "backup":
                backup
        }

    # ========================================================
    # TRAIN FINAL CANDIDATE ON ALL VALID DATA
    # ========================================================

    rows = load_training_rows()

    production_candidate = (
        build_candidate_model(
            rows
        )
    )

    if (
        production_candidate.get(
            "status"
        )
        !=
        "READY"
    ):

        return {

            "promoted": False,

            "reason":
                "PRODUCTION_CANDIDATE_NOT_READY",

            "backup":
                backup
        }

    # ========================================================
    # ATOMIC MODEL SAVE
    # ========================================================

    save_model(
        production_candidate
    )

    validation = (
        validate_model_file(
            MODEL_FILE
        )
    )

    if not validation.get(
        "valid",
        False
    ):

        rollback_result = (
            rollback_latest()
        )

        return {

            "promoted": False,

            "reason":
                "PROMOTED_MODEL_VALIDATION_FAILED",

            "rollback":
                rollback_result
        }

    write_log(
        "CHALLENGER_PROMOTED",
        {

            "backup":
                backup.get(
                    "backup"
                ),

            "new_hash":
                validation.get(
                    "hash"
                ),

            "new_samples":
                production_candidate.get(
                    "total_samples"
                ),

            "evaluation":
                evaluation
        }
    )

    return {

        "promoted": True,

        "reason":
            "CHALLENGER_PROMOTED",

        "backup":
            backup.get(
                "backup"
            ),

        "new_model_hash":
            validation.get(
                "hash"
            ),

        "new_samples":
            production_candidate.get(
                "total_samples"
            ),

        "evaluation":
            evaluation
    }


# ============================================================
# ROLLBACK
# ============================================================

def rollback_latest():

    backups = list_backups()

    if not backups:

        return {

            "rolled_back": False,

            "reason":
                "NO_BACKUP_AVAILABLE"
        }

    selected = None

    for backup in backups:

        if backup.get(
            "valid",
            False
        ):

            selected = backup

            break

    if selected is None:

        return {

            "rolled_back": False,

            "reason":
                "NO_VALID_BACKUP"
        }

    backup_path = os.path.join(
        BACKUP_DIR,
        selected[
            "filename"
        ]
    )

    # Verify integrity immediately before restore

    validation = (
        validate_model_file(
            backup_path
        )
    )

    if not validation.get(
        "valid",
        False
    ):

        return {

            "rolled_back": False,

            "reason":
                "BACKUP_VALIDATION_FAILED"
        }

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    temporary_file = (
        MODEL_FILE
        +
        ".rollback"
    )

    shutil.copy2(
        backup_path,
        temporary_file
    )

    os.replace(
        temporary_file,
        MODEL_FILE
    )

    final_validation = (
        validate_model_file(
            MODEL_FILE
        )
    )

    if not final_validation.get(
        "valid",
        False
    ):

        return {

            "rolled_back": False,

            "reason":
                "RESTORED_MODEL_INVALID"
        }

    write_log(
        "MODEL_ROLLBACK",
        {

            "restored_backup":
                selected[
                    "filename"
                ],

            "hash":
                final_validation.get(
                    "hash"
                )
        }
    )

    return {

        "rolled_back": True,

        "reason":
            "CHAMPION_RESTORED",

        "backup":
            selected[
                "filename"
            ],

        "hash":
            final_validation.get(
                "hash"
            )
    }


# ============================================================
# STATUS
# ============================================================

def promotion_status():

    champion = load_model()

    champion_validation = (
        validate_model_file(
            MODEL_FILE
        )
        if champion
        else
        {
            "valid": False,
            "reason":
                "NO_CHAMPION"
        }
    )

    return {

        "champion_present":
            champion is not None,

        "champion_valid":
            champion_validation.get(
                "valid",
                False
            ),

        "champion_hash":
            champion_validation.get(
                "hash"
            ),

        "champion_samples":
            (
                champion.get(
                    "total_samples",
                    0
                )
                if champion
                else
                0
            ),

        "backups":
            len(
                list_backups()
            ),

        "evaluation":
            evaluate_promotion_candidate()
    }