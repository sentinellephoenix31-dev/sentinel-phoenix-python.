import json
import math
import os
from datetime import datetime, timezone

from core.learning import (
    load_model,
    load_training_rows,
    build_candidate_model,
    distance_to_profile,
    safe_float,
    clamp
)


# ============================================================
# SENTINEL PHOENIX
# MODEL EVALUATION ENGINE V1
# CHAMPION / CHALLENGER
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

EVALUATION_FILE = os.path.join(
    DATA_DIR,
    "model_evaluations.jsonl"
)

MIN_VALIDATION_SAMPLES = 4


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def safe_divide(
    numerator,
    denominator
):

    if denominator == 0:
        return 0.0

    return numerator / denominator


# ============================================================
# TRUE LABEL
# ============================================================

def expected_label(
    row
):
    """
    Même définition défensive que Learning V2.

    Important :
    ceci reste un label dérivé de nos règles,
    pas une vérité absolue provenant d'un analyste humain.
    """

    payload_score = safe_float(
        row[0]
    )

    behavior_score = safe_float(
        row[1]
    )

    anomaly_score = safe_float(
        row[2]
    )

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
# DATASET SPLIT
# ============================================================

def split_dataset(
    rows
):
    """
    Sépare chaque classe afin que le jeu
    de validation contienne si possible :

    NORMAL
    +
    DANGEROUS
    """

    normal_rows = []
    dangerous_rows = []

    for row in rows:

        label = expected_label(
            row
        )

        if label == "DANGEROUS":

            dangerous_rows.append(
                row
            )

        else:

            normal_rows.append(
                row
            )

    training_rows = []
    validation_rows = []

    for class_rows in (
        normal_rows,
        dangerous_rows
    ):

        total = len(
            class_rows
        )

        if total <= 2:

            training_rows.extend(
                class_rows
            )

            continue

        validation_count = max(
            1,
            int(
                total * 0.25
            )
        )

        validation_count = min(
            validation_count,
            total - 2
        )

        training_rows.extend(
            class_rows[
                :-validation_count
            ]
        )

        validation_rows.extend(
            class_rows[
                -validation_count:
            ]
        )

    return (
        training_rows,
        validation_rows
    )


# ============================================================
# MODEL PREDICTION
# ============================================================

def model_score(
    model,
    row
):

    if not model:

        return 50.0

    if (
        model.get(
            "status"
        )
        !=
        "READY"
    ):

        return 50.0

    vector = {

        "payload":
            safe_float(
                row[0]
            ),

        "behavior":
            safe_float(
                row[1]
            ),

        "anomaly":
            safe_float(
                row[2]
            )
    }

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
        normal_distance is None
        or
        dangerous_distance is None
    ):

        return 50.0

    total_distance = (
        normal_distance
        +
        dangerous_distance
    )

    if total_distance <= 0:

        return 50.0

    score = (
        normal_distance
        /
        total_distance
    ) * 100

    return round(
        clamp(
            score
        ),
        2
    )


def model_prediction(
    model,
    row
):

    score = model_score(
        model,
        row
    )

    if score >= 60:

        return (
            "DANGEROUS",
            score
        )

    return (
        "NORMAL",
        score
    )


# ============================================================
# METRICS
# ============================================================

def evaluate_model(
    model,
    validation_rows
):

    true_positive = 0
    true_negative = 0

    false_positive = 0
    false_negative = 0

    results = []

    for row in validation_rows:

        expected = (
            expected_label(
                row
            )
        )

        predicted, score = (
            model_prediction(
                model,
                row
            )
        )

        if (
            expected == "DANGEROUS"
            and
            predicted == "DANGEROUS"
        ):

            true_positive += 1

        elif (
            expected == "NORMAL"
            and
            predicted == "NORMAL"
        ):

            true_negative += 1

        elif (
            expected == "NORMAL"
            and
            predicted == "DANGEROUS"
        ):

            false_positive += 1

        elif (
            expected == "DANGEROUS"
            and
            predicted == "NORMAL"
        ):

            false_negative += 1

        results.append(
            {
                "expected":
                    expected,

                "predicted":
                    predicted,

                "score":
                    score
            }
        )

    total = len(
        validation_rows
    )

    accuracy = safe_divide(
        true_positive
        +
        true_negative,
        total
    )

    precision = safe_divide(
        true_positive,
        true_positive
        +
        false_positive
    )

    recall = safe_divide(
        true_positive,
        true_positive
        +
        false_negative
    )

    specificity = safe_divide(
        true_negative,
        true_negative
        +
        false_positive
    )

    if (
        precision
        +
        recall
        >
        0
    ):

        f1_score = (
            2
            *
            precision
            *
            recall
            /
            (
                precision
                +
                recall
            )
        )

    else:

        f1_score = 0.0

    balanced_accuracy = (
        recall
        +
        specificity
    ) / 2

    false_negative_rate = safe_divide(
        false_negative,
        true_positive
        +
        false_negative
    )

    # ========================================================
    # SECURITY SCORE
    #
    # Les faux négatifs sont pénalisés davantage.
    # ========================================================

    security_score = (

        balanced_accuracy * 70

        +

        f1_score * 20

        +

        accuracy * 10

        -

        false_negative_rate * 20
    )

    security_score = round(
        clamp(
            security_score
        ),
        2
    )

    return {

        "samples":
            total,

        "true_positive":
            true_positive,

        "true_negative":
            true_negative,

        "false_positive":
            false_positive,

        "false_negative":
            false_negative,

        "accuracy":
            round(
                accuracy,
                4
            ),

        "precision":
            round(
                precision,
                4
            ),

        "recall":
            round(
                recall,
                4
            ),

        "specificity":
            round(
                specificity,
                4
            ),

        "f1":
            round(
                f1_score,
                4
            ),

        "balanced_accuracy":
            round(
                balanced_accuracy,
                4
            ),

        "false_negative_rate":
            round(
                false_negative_rate,
                4
            ),

        "security_score":
            security_score,

        "results":
            results
    }


# ============================================================
# CHAMPION / CHALLENGER
# ============================================================

def compare_models():

    rows = load_training_rows()

    if len(rows) < 8:

        return {

            "status":
                "INSUFFICIENT_DATA",

            "total_samples":
                len(rows),

            "minimum_recommended":
                8
        }

    training_rows, validation_rows = (
        split_dataset(
            rows
        )
    )

    if (
        len(validation_rows)
        <
        MIN_VALIDATION_SAMPLES
    ):

        return {

            "status":
                "INSUFFICIENT_VALIDATION_DATA",

            "total_samples":
                len(rows),

            "training_samples":
                len(
                    training_rows
                ),

            "validation_samples":
                len(
                    validation_rows
                ),

            "minimum_validation":
                MIN_VALIDATION_SAMPLES
        }

    # ========================================================
    # DEPLOYED CHAMPION
    # ========================================================

    champion = load_model()

    if champion is None:

        return {
            "status":
                "NO_CHAMPION_MODEL"
        }

    # ========================================================
    # NEW CHALLENGER
    # ========================================================

    challenger = (
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
            challenger,
            validation_rows
        )
    )

    champion_score = safe_float(
        champion_metrics.get(
            "security_score"
        )
    )

    challenger_score = safe_float(
        challenger_metrics.get(
            "security_score"
        )
    )

    champion_fn = int(
        champion_metrics.get(
            "false_negative",
            0
        )
    )

    challenger_fn = int(
        challenger_metrics.get(
            "false_negative",
            0
        )
    )

    # ========================================================
    # DECISION
    # ========================================================

    promote = False

    reasons = []

    if (
        challenger.get(
            "status"
        )
        !=
        "READY"
    ):

        reasons.append(
            "CHALLENGER_NOT_READY"
        )

    elif (
        challenger_fn
        >
        champion_fn
    ):

        reasons.append(
            "CHALLENGER_MORE_FALSE_NEGATIVES"
        )

    elif (
        challenger_score
        >
        champion_score
        +
        2
    ):

        promote = True

        reasons.append(
            "CHALLENGER_SECURITY_SCORE_IMPROVED"
        )

    elif (
        challenger_score
        >=
        champion_score
        and
        challenger_fn
        <
        champion_fn
    ):

        promote = True

        reasons.append(
            "CHALLENGER_REDUCES_FALSE_NEGATIVES"
        )

    else:

        reasons.append(
            "CHAMPION_REMAINS_PREFERRED"
        )

    evaluation = {

        "timestamp":
            utc_now(),

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

        "champion": {

            "version":
                champion.get(
                    "model_version"
                ),

            "samples":
                champion.get(
                    "total_samples"
                ),

            "metrics":
                champion_metrics
        },

        "challenger": {

            "version":
                challenger.get(
                    "model_version"
                ),

            "samples":
                challenger.get(
                    "total_samples"
                ),

            "quality":
                challenger.get(
                    "quality"
                ),

            "metrics":
                challenger_metrics
        },

        "recommend_promotion":
            promote,

        "decision_reasons":
            reasons,

        # V1 n'effectue aucune promotion.
        "automatic_promotion":
            False
    }

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    with open(
        EVALUATION_FILE,
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            json.dumps(
                evaluation,
                ensure_ascii=False
            )
            +
            "\n"
        )

    return evaluation


# ============================================================
# SHORT STATUS
# ============================================================

def evaluation_summary():

    evaluation = (
        compare_models()
    )

    if (
        evaluation.get(
            "status"
        )
        !=
        "EVALUATED"
    ):

        return evaluation

    return {

        "status":
            evaluation[
                "status"
            ],

        "training_samples":
            evaluation[
                "training_samples"
            ],

        "validation_samples":
            evaluation[
                "validation_samples"
            ],

        "champion_security_score":
            evaluation[
                "champion"
            ][
                "metrics"
            ][
                "security_score"
            ],

        "challenger_security_score":
            evaluation[
                "challenger"
            ][
                "metrics"
            ][
                "security_score"
            ],

        "champion_false_negatives":
            evaluation[
                "champion"
            ][
                "metrics"
            ][
                "false_negative"
            ],

        "challenger_false_negatives":
            evaluation[
                "challenger"
            ][
                "metrics"
            ][
                "false_negative"
            ],

        "recommend_promotion":
            evaluation[
                "recommend_promotion"
            ],

        "decision_reasons":
            evaluation[
                "decision_reasons"
            ],

        "automatic_promotion":
            False
    }