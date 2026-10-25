import hashlib
import json
import math
import os
import sqlite3
import threading

from datetime import datetime, timezone


# ============================================================
# SENTINEL PHOENIX
# LEARNING ENGINE V2
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

DATABASE_FILE = os.path.join(
    DATA_DIR,
    "phoenix_memory.db"
)

MODEL_FILE = os.path.join(
    DATA_DIR,
    "phoenix_learning.json"
)

HISTORY_FILE = os.path.join(
    DATA_DIR,
    "learning_history.jsonl"
)

MODEL_VERSION = "2.0"

AUTO_RETRAIN_NEW_SAMPLES = 10

AUTO_RETRAIN_MIN_INTERVAL_SECONDS = 300

MINIMUM_SAMPLES = 5

MINIMUM_CLASS_SAMPLES = 2

_lock = threading.RLock()


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def safe_float(
    value,
    default=0.0
):

    try:
        return float(value)

    except (
        TypeError,
        ValueError
    ):
        return float(default)


def clamp(
    value,
    minimum=0.0,
    maximum=100.0
):

    return max(
        minimum,
        min(
            maximum,
            value
        )
    )


def average(
    values
):

    if not values:
        return 0.0

    return (
        sum(values)
        /
        len(values)
    )


def standard_deviation(
    values
):

    if len(values) < 2:
        return 1.0

    mean_value = average(
        values
    )

    variance = sum(
        (
            value
            -
            mean_value
        ) ** 2
        for value
        in values
    ) / len(values)

    return max(
        math.sqrt(
            variance
        ),
        1.0
    )


# ============================================================
# DATABASE
# ============================================================

def get_connection():

    return sqlite3.connect(
        DATABASE_FILE,
        timeout=10
    )


def load_training_rows():

    if not os.path.exists(
        DATABASE_FILE
    ):
        return []

    connection = (
        get_connection()
    )

    try:

        rows = connection.execute(
            """
            SELECT
                payload_score,
                behavior_score,
                anomaly_score,
                global_score,
                containment_requested

            FROM observations

            WHERE
                payload_score IS NOT NULL
                AND behavior_score IS NOT NULL
                AND anomaly_score IS NOT NULL
                AND global_score IS NOT NULL

            ORDER BY id ASC
            """
        ).fetchall()

    finally:

        connection.close()

    valid_rows = []

    for row in rows:

        payload_score = safe_float(
            row[0]
        )

        behavior_score = safe_float(
            row[1]
        )

        anomaly_score = safe_float(
            row[2]
        )

        global_score = safe_float(
            row[3]
        )

        containment = int(
            bool(
                row[4]
            )
        )

        values = (
            payload_score,
            behavior_score,
            anomaly_score,
            global_score
        )

        if not all(
            0 <= value <= 100
            for value
            in values
        ):
            continue

        valid_rows.append(
            (
                payload_score,
                behavior_score,
                anomaly_score,
                global_score,
                containment
            )
        )

    return valid_rows


# ============================================================
# DATASET FINGERPRINT
# ============================================================

def dataset_fingerprint(
    rows
):

    serialized = json.dumps(
        rows,
        separators=(
            ",",
            ":"
        )
    )

    return hashlib.sha256(
        serialized.encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================
# STORAGE
# ============================================================

def save_model(
    model
):

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    temporary_file = (
        MODEL_FILE
        +
        ".tmp"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            model,
            file,
            indent=2,
            ensure_ascii=False
        )

    os.replace(
        temporary_file,
        MODEL_FILE
    )


def load_model():

    if not os.path.exists(
        MODEL_FILE
    ):
        return None

    try:

        with open(
            MODEL_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            model = json.load(
                file
            )

        if (
            model.get(
                "model_version"
            )
            !=
            MODEL_VERSION
        ):
            return None

        return model

    except (
        OSError,
        json.JSONDecodeError
    ):
        return None


def log_learning_event(
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
        HISTORY_FILE,
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
# PROFILES
# ============================================================

def build_profile(
    rows
):

    payload_values = [
        row[0]
        for row
        in rows
    ]

    behavior_values = [
        row[1]
        for row
        in rows
    ]

    anomaly_values = [
        row[2]
        for row
        in rows
    ]

    return {

        "samples":
            len(rows),

        "centroid": {

            "payload":
                round(
                    average(
                        payload_values
                    ),
                    4
                ),

            "behavior":
                round(
                    average(
                        behavior_values
                    ),
                    4
                ),

            "anomaly":
                round(
                    average(
                        anomaly_values
                    ),
                    4
                )
        },

        "spread": {

            "payload":
                round(
                    standard_deviation(
                        payload_values
                    ),
                    4
                ),

            "behavior":
                round(
                    standard_deviation(
                        behavior_values
                    ),
                    4
                ),

            "anomaly":
                round(
                    standard_deviation(
                        anomaly_values
                    ),
                    4
                )
        }
    }


def classify_training_row(
    row
):
    """
    Classification V2 volontairement basée
    principalement sur les moteurs bruts.

    On évite ainsi que le modèle ML apprenne
    simplement ses propres anciennes décisions.
    """

    payload_score = row[0]
    behavior_score = row[1]
    anomaly_score = row[2]
    containment = bool(
        row[4]
    )

    if containment:
        return "DANGEROUS"

    if (
        payload_score >= 60
        and
        behavior_score >= 60
    ):
        return "DANGEROUS"

    if anomaly_score >= 70:
        return "DANGEROUS"

    if (
        payload_score >= 70
        and
        behavior_score >= 50
    ):
        return "DANGEROUS"

    return "NORMAL"


# ============================================================
# QUALITY
# ============================================================

def calculate_quality(
    normal_profile,
    dangerous_profile,
    scales
):

    if (
        normal_profile.get(
            "samples",
            0
        ) == 0
        or
        dangerous_profile.get(
            "samples",
            0
        ) == 0
    ):

        return {
            "separation": 0.0,
            "class_balance": 0.0,
            "quality_score": 0.0
        }

    normal = normal_profile[
        "centroid"
    ]

    dangerous = dangerous_profile[
        "centroid"
    ]

    payload_scale = max(
        safe_float(
            scales.get(
                "payload"
            ),
            1
        ),
        1
    )

    behavior_scale = max(
        safe_float(
            scales.get(
                "behavior"
            ),
            1
        ),
        1
    )

    anomaly_scale = max(
        safe_float(
            scales.get(
                "anomaly"
            ),
            1
        ),
        1
    )

    separation = math.sqrt(

        (
            (
                dangerous["payload"]
                -
                normal["payload"]
            )
            /
            payload_scale
        ) ** 2

        +

        (
            (
                dangerous["behavior"]
                -
                normal["behavior"]
            )
            /
            behavior_scale
        ) ** 2

        +

        (
            (
                dangerous["anomaly"]
                -
                normal["anomaly"]
            )
            /
            anomaly_scale
        ) ** 2
    )

    normal_samples = (
        normal_profile[
            "samples"
        ]
    )

    dangerous_samples = (
        dangerous_profile[
            "samples"
        ]
    )

    class_balance = (

        min(
            normal_samples,
            dangerous_samples
        )
        /
        max(
            normal_samples,
            dangerous_samples
        )
    )

    quality_score = min(
        (
            separation * 25
        )
        +
        (
            class_balance * 25
        ),
        100
    )

    return {

        "separation":
            round(
                separation,
                4
            ),

        "class_balance":
            round(
                class_balance,
                4
            ),

        "quality_score":
            round(
                quality_score,
                2
            )
    }


# ============================================================
# MODEL BUILDER
# ============================================================

def build_candidate_model(
    rows
):

    normal_rows = []

    dangerous_rows = []

    all_payload = []

    all_behavior = []

    all_anomaly = []

    for row in rows:

        all_payload.append(
            row[0]
        )

        all_behavior.append(
            row[1]
        )

        all_anomaly.append(
            row[2]
        )

        classification = (
            classify_training_row(
                row
            )
        )

        clean_row = (
            row[0],
            row[1],
            row[2]
        )

        if (
            classification
            ==
            "DANGEROUS"
        ):

            dangerous_rows.append(
                clean_row
            )

        else:

            normal_rows.append(
                clean_row
            )

    scales = {

        "payload":
            standard_deviation(
                all_payload
            ),

        "behavior":
            standard_deviation(
                all_behavior
            ),

        "anomaly":
            standard_deviation(
                all_anomaly
            )
    }

    normal_profile = (
        build_profile(
            normal_rows
        )
    )

    dangerous_profile = (
        build_profile(
            dangerous_rows
        )
    )

    enough_samples = (
        len(rows)
        >=
        MINIMUM_SAMPLES
    )

    both_classes_present = (

        len(normal_rows)
        >=
        MINIMUM_CLASS_SAMPLES

        and

        len(dangerous_rows)
        >=
        MINIMUM_CLASS_SAMPLES
    )

    if (
        enough_samples
        and
        both_classes_present
    ):

        status = "READY"

    else:

        status = "COLD_START"

    quality = calculate_quality(
        normal_profile,
        dangerous_profile,
        scales
    )

    return {

        "model_version":
            MODEL_VERSION,

        "trained_at":
            utc_now(),

        "status":
            status,

        "total_samples":
            len(rows),

        "normal_samples":
            len(
                normal_rows
            ),

        "dangerous_samples":
            len(
                dangerous_rows
            ),

        "minimum_samples":
            MINIMUM_SAMPLES,

        "minimum_class_samples":
            MINIMUM_CLASS_SAMPLES,

        "dataset_fingerprint":
            dataset_fingerprint(
                rows
            ),

        "normal_profile":
            normal_profile,

        "dangerous_profile":
            dangerous_profile,

        "global_scales": {

            "payload":
                round(
                    scales["payload"],
                    4
                ),

            "behavior":
                round(
                    scales["behavior"],
                    4
                ),

            "anomaly":
                round(
                    scales["anomaly"],
                    4
                )
        },

        "quality":
            quality
    }


# ============================================================
# CANDIDATE VALIDATION
# ============================================================

def candidate_is_acceptable(
    current_model,
    candidate
):

    if current_model is None:
        return (
            True,
            "FIRST_V2_MODEL"
        )

    current_status = current_model.get(
        "status",
        "COLD_START"
    )

    candidate_status = candidate.get(
        "status",
        "COLD_START"
    )

    if (
        current_status == "READY"
        and
        candidate_status != "READY"
    ):

        return (
            False,
            "READY_MODEL_WOULD_DEGRADE"
        )

    current_separation = safe_float(
        current_model.get(
            "quality",
            {}
        ).get(
            "separation",
            0
        )
    )

    candidate_separation = safe_float(
        candidate.get(
            "quality",
            {}
        ).get(
            "separation",
            0
        )
    )

    if (
        current_status == "READY"
        and
        candidate_status == "READY"
        and
        current_separation > 0
        and
        candidate_separation
        <
        (
            current_separation
            *
            0.70
        )
    ):

        return (
            False,
            "MODEL_SEPARATION_DEGRADED"
        )

    return (
        True,
        "QUALITY_CHECK_PASSED"
    )


# ============================================================
# MANUAL TRAINING
# ============================================================

def train_learning_model(
    save=True
):

    with _lock:

        rows = load_training_rows()

        candidate = (
            build_candidate_model(
                rows
            )
        )

        if save:

            save_model(
                candidate
            )

            log_learning_event(
                "MODEL_TRAINED",
                {
                    "samples":
                        candidate[
                            "total_samples"
                        ],

                    "normal":
                        candidate[
                            "normal_samples"
                        ],

                    "dangerous":
                        candidate[
                            "dangerous_samples"
                        ],

                    "status":
                        candidate[
                            "status"
                        ],

                    "quality":
                        candidate[
                            "quality"
                        ]
                }
            )

        return candidate


# ============================================================
# AUTOMATIC CONTROLLED RETRAINING
# ============================================================

def maybe_retrain_model(
    force=False,
    min_new_samples=AUTO_RETRAIN_NEW_SAMPLES,
    min_interval_seconds=AUTO_RETRAIN_MIN_INTERVAL_SECONDS
):

    with _lock:

        rows = load_training_rows()

        total_samples = len(
            rows
        )

        current_model = (
            load_model()
        )

        if current_model is None:

            candidate = (
                build_candidate_model(
                    rows
                )
            )

            save_model(
                candidate
            )

            log_learning_event(
                "MODEL_ACCEPTED",
                {
                    "reason":
                        "NO_CURRENT_V2_MODEL",

                    "samples":
                        total_samples,

                    "status":
                        candidate[
                            "status"
                        ],

                    "quality":
                        candidate[
                            "quality"
                        ]
                }
            )

            return {
                "retrained": True,
                "accepted": True,
                "reason":
                    "NO_CURRENT_V2_MODEL",
                "old_samples": 0,
                "new_samples":
                    total_samples,
                "status":
                    candidate[
                        "status"
                    ]
            }

        old_samples = int(
            current_model.get(
                "total_samples",
                0
            )
        )

        new_samples = (
            total_samples
            -
            old_samples
        )

        if (
            not force
            and
            new_samples
            <
            min_new_samples
        ):

            return {
                "retrained": False,
                "accepted": False,
                "reason":
                    "NOT_ENOUGH_NEW_SAMPLES",
                "old_samples":
                    old_samples,
                "new_samples":
                    new_samples,
                "status":
                    current_model.get(
                        "status"
                    )
            }

        trained_at = (
            current_model.get(
                "trained_at"
            )
        )

        if (
            not force
            and
            trained_at
        ):

            try:

                trained_time = (
                    datetime.fromisoformat(
                        trained_at
                    )
                )

                age_seconds = (
                    datetime.now(
                        timezone.utc
                    )
                    -
                    trained_time
                ).total_seconds()

                if (
                    age_seconds
                    <
                    min_interval_seconds
                ):

                    return {
                        "retrained": False,
                        "accepted": False,
                        "reason":
                            "RETRAIN_INTERVAL_ACTIVE",
                        "old_samples":
                            old_samples,
                        "new_samples":
                            new_samples,
                        "status":
                            current_model.get(
                                "status"
                            )
                    }

            except ValueError:
                pass

        candidate = (
            build_candidate_model(
                rows
            )
        )

        accepted, reason = (
            candidate_is_acceptable(
                current_model,
                candidate
            )
        )

        if accepted:

            save_model(
                candidate
            )

            log_learning_event(
                "MODEL_ACCEPTED",
                {
                    "reason":
                        reason,

                    "previous_samples":
                        old_samples,

                    "new_total":
                        total_samples,

                    "quality":
                        candidate[
                            "quality"
                        ]
                }
            )

            return {
                "retrained": True,
                "accepted": True,
                "reason":
                    reason,
                "old_samples":
                    old_samples,
                "new_samples":
                    new_samples,
                "status":
                    candidate[
                        "status"
                    ]
            }

        log_learning_event(
            "MODEL_REJECTED",
            {
                "reason":
                    reason,

                "previous_samples":
                    old_samples,

                "candidate_samples":
                    total_samples,

                "candidate_quality":
                    candidate[
                        "quality"
                    ]
            }
        )

        return {
            "retrained": True,
            "accepted": False,
            "reason":
                reason,
            "old_samples":
                old_samples,
            "new_samples":
                new_samples,
            "status":
                current_model.get(
                    "status"
                )
        }


# ============================================================
# DISTANCE
# ============================================================

def distance_to_profile(
    vector,
    profile,
    scales
):

    if (
        not profile
        or
        profile.get(
            "samples",
            0
        ) == 0
    ):
        return None

    centroid = profile.get(
        "centroid",
        {}
    )

    payload_scale = max(
        safe_float(
            scales.get(
                "payload"
            ),
            1
        ),
        1
    )

    behavior_scale = max(
        safe_float(
            scales.get(
                "behavior"
            ),
            1
        ),
        1
    )

    anomaly_scale = max(
        safe_float(
            scales.get(
                "anomaly"
            ),
            1
        ),
        1
    )

    payload_difference = (
        (
            vector["payload"]
            -
            safe_float(
                centroid.get(
                    "payload"
                )
            )
        )
        /
        payload_scale
    )

    behavior_difference = (
        (
            vector["behavior"]
            -
            safe_float(
                centroid.get(
                    "behavior"
                )
            )
        )
        /
        behavior_scale
    )

    anomaly_difference = (
        (
            vector["anomaly"]
            -
            safe_float(
                centroid.get(
                    "anomaly"
                )
            )
        )
        /
        anomaly_scale
    )

    return math.sqrt(
        payload_difference ** 2
        +
        behavior_difference ** 2
        +
        anomaly_difference ** 2
    )


# ============================================================
# FALLBACK
# ============================================================

def fallback_score(
    payload_score,
    behavior_score,
    anomaly_score,
    reputation_score
):

    current_score = (
        payload_score * 0.40
        +
        behavior_score * 0.35
        +
        anomaly_score * 0.25
    )

    reputation_bonus = (
        reputation_score
        *
        0.10
    )

    return clamp(
        current_score
        +
        reputation_bonus
    )


# ============================================================
# INFERENCE
# ============================================================

def evaluate_learning(
    analysis,
    behavior,
    anomaly,
    reputation
):

    with _lock:

        model = (
            load_model()
        )

        if model is None:

            model = (
                train_learning_model()
            )

        payload_score = safe_float(
            analysis.get(
                "score",
                0
            )
        )

        behavior_score = safe_float(
            behavior.get(
                "behavior_score",
                0
            )
        )

        anomaly_score = safe_float(
            anomaly.get(
                "anomaly_score",
                0
            )
        )

        reputation_score = safe_float(
            reputation.get(
                "reputation_score",
                0
            )
        )

        vector = {
            "payload":
                payload_score,

            "behavior":
                behavior_score,

            "anomaly":
                anomaly_score
        }

        status = model.get(
            "status",
            "COLD_START"
        )

        total_samples = int(
            model.get(
                "total_samples",
                0
            )
        )

        reasons = []

        if status == "READY":

            scales = model.get(
                "global_scales",
                {}
            )

            normal_distance = (
                distance_to_profile(
                    vector,
                    model.get(
                        "normal_profile"
                    ),
                    scales
                )
            )

            dangerous_distance = (
                distance_to_profile(
                    vector,
                    model.get(
                        "dangerous_profile"
                    ),
                    scales
                )
            )

            if (
                normal_distance is not None
                and
                dangerous_distance is not None
            ):

                total_distance = (
                    normal_distance
                    +
                    dangerous_distance
                )

                if total_distance <= 0:

                    learned_score = 50.0

                else:

                    learned_score = (
                        normal_distance
                        /
                        total_distance
                    ) * 100

                reasons.append(
                    "LEARNED_CLASS_PROXIMITY"
                )

            else:

                learned_score = (
                    fallback_score(
                        payload_score,
                        behavior_score,
                        anomaly_score,
                        reputation_score
                    )
                )

                reasons.append(
                    "MODEL_PROFILE_FALLBACK"
                )

            learned_score += min(
                reputation_score
                *
                0.10,
                10
            )

            learned_score = clamp(
                learned_score
            )

            class_balance = safe_float(
                model.get(
                    "quality",
                    {}
                ).get(
                    "class_balance",
                    0
                )
            )

            sample_confidence = min(
                total_samples * 2,
                25
            )

            balance_confidence = (
                class_balance
                *
                10
            )

            confidence = min(
                60
                +
                sample_confidence
                +
                balance_confidence,
                95
            )

            reasons.append(
                "TRAINED_MODEL_ACTIVE"
            )

        else:

            learned_score = (
                fallback_score(
                    payload_score,
                    behavior_score,
                    anomaly_score,
                    reputation_score
                )
            )

            confidence = min(
                35
                +
                total_samples * 4,
                55
            )

            reasons.append(
                "COLD_START_FALLBACK"
            )

        learned_score = round(
            clamp(
                learned_score
            ),
            2
        )

        confidence = int(
            clamp(
                confidence
            )
        )

        if learned_score >= 80:

            level = "CRITICAL"

        elif learned_score >= 60:

            level = "HIGH"

        elif learned_score >= 30:

            level = "MEDIUM"

        else:

            level = "LOW"

        return {

            "ml_score":
                learned_score,

            "ml_level":
                level,

            "ml_confidence":
                confidence,

            "model_status":
                status,

            "model_samples":
                total_samples,

            "normal_samples":
                int(
                    model.get(
                        "normal_samples",
                        0
                    )
                ),

            "dangerous_samples":
                int(
                    model.get(
                        "dangerous_samples",
                        0
                    )
                ),

            "model_version":
                MODEL_VERSION,

            "model_quality":
                model.get(
                    "quality",
                    {}
                ),

            "learning_reasons":
                reasons,

            "payload_execution":
                False
        }


# ============================================================
# STATUS
# ============================================================

def get_learning_status():

    model = (
        load_model()
    )

    if model is None:

        model = (
            train_learning_model()
        )

    return {

        "status":
            model.get(
                "status"
            ),

        "version":
            model.get(
                "model_version"
            ),

        "total_samples":
            model.get(
                "total_samples",
                0
            ),

        "normal_samples":
            model.get(
                "normal_samples",
                0
            ),

        "dangerous_samples":
            model.get(
                "dangerous_samples",
                0
            ),

        "trained_at":
            model.get(
                "trained_at"
            ),

        "quality":
            model.get(
                "quality",
                {}
            )
    }