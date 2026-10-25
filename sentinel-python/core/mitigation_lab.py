import json
import os
import secrets

from datetime import datetime, timezone

from core.mitigation import (
    validate_candidate,
    validate_candidate_set
)


# ============================================================
# SENTINEL PHOENIX
# MITIGATION LAB / CANDIDATE EVALUATOR V2
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

LAB_LOG = os.path.join(
    DATA_DIR,
    "mitigation_lab.jsonl"
)


# ============================================================
# LAB POLICY
# ============================================================

CANDIDATE_PROFILES = {

    "MONITORING_PROFILE": {
        "security_gain": 20,
        "stability": 100,
        "reversibility": 100,
        "containment": 10
    },

    "DECEPTION_PROFILE": {
        "security_gain": 75,
        "stability": 95,
        "reversibility": 100,
        "containment": 80
    },

    "SESSION_ISOLATION": {
        "security_gain": 90,
        "stability": 85,
        "reversibility": 95,
        "containment": 95
    },

    "EVIDENCE_PRESERVATION": {
        "security_gain": 25,
        "stability": 100,
        "reversibility": 100,
        "containment": 5
    },

    "REPUTATION_POLICY": {
        "security_gain": 35,
        "stability": 100,
        "reversibility": 100,
        "containment": 20
    },

    "MODEL_REVIEW": {
        "security_gain": 30,
        "stability": 95,
        "reversibility": 100,
        "containment": 10
    },

    "RECOVERY_RECOMMENDATION": {
        "security_gain": 70,
        "stability": 90,
        "reversibility": 95,
        "containment": 50
    }
}


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def generate_lab_id():

    return (
        "lab-"
        +
        secrets.token_hex(8)
    )


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


def save_lab_result(
    result
):

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    event = {

        "timestamp":
            utc_now(),

        "type":
            "MITIGATION_LAB_RESULT",

        "result":
            result
    }

    with open(
        LAB_LOG,
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
# SAFETY SCORE
# ============================================================

def calculate_safety_score(
    candidate
):

    score = 100.0

    forbidden_flags = (

        "host_modification",
        "host_execution",
        "shell_execution",
        "payload_execution",
        "network_access_required",
        "privileged_execution",
        "deployment_allowed"

    )

    for field in forbidden_flags:

        if candidate.get(
            field,
            False
        ):

            score -= 100

    if not candidate.get(
        "reversible",
        False
    ):

        score -= 30

    return round(
        clamp(
            score
        ),
        2
    )


# ============================================================
# CANDIDATE EVALUATION
# ============================================================

def evaluate_candidate(
    candidate
):

    validation = (
        validate_candidate(
            candidate
        )
    )

    if not validation.get(
        "valid",
        False
    ):

        return {

            "candidate_id":
                candidate.get(
                    "candidate_id"
                ),

            "status":
                "REJECT",

            "reason":
                "VALIDATION_FAILED",

            "validation":
                validation,

            "final_score":
                0,

            "host_modified":
                False,

            "commands_executed":
                False,

            "payload_executed":
                False
        }

    candidate_type = (
        candidate.get(
            "candidate_type"
        )
    )

    profile = CANDIDATE_PROFILES.get(
        candidate_type
    )

    if profile is None:

        return {

            "candidate_id":
                candidate.get(
                    "candidate_id"
                ),

            "status":
                "REJECT",

            "reason":
                "NO_LAB_PROFILE",

            "final_score":
                0,

            "host_modified":
                False,

            "commands_executed":
                False,

            "payload_executed":
                False
        }

    safety_score = (
        calculate_safety_score(
            candidate
        )
    )

    security_gain = float(
        profile[
            "security_gain"
        ]
    )

    stability = float(
        profile[
            "stability"
        ]
    )

    reversibility = float(
        profile[
            "reversibility"
        ]
    )

    containment = float(
        profile[
            "containment"
        ]
    )

    # ========================================================
    # WEIGHTED SCORE
    # ========================================================

    final_score = (

        safety_score
        *
        0.35

        +

        security_gain
        *
        0.30

        +

        stability
        *
        0.15

        +

        reversibility
        *
        0.10

        +

        containment
        *
        0.10
    )

    # Confirmation-sensitive candidates remain testable,
    # but are marked for authorization.

    requires_confirmation = bool(
        candidate.get(
            "requires_confirmation",
            False
        )
    )

    if safety_score < 100:

        status = "REJECT"

        reason = (
            "SAFETY_POLICY_FAILED"
        )

    elif final_score >= 75:

        status = "ACCEPT"

        reason = (
            "LAB_SCORE_ACCEPTED"
        )

    elif final_score >= 60:

        status = "REVIEW"

        reason = (
            "LAB_SCORE_REQUIRES_REVIEW"
        )

    else:

        status = "REJECT"

        reason = (
            "LAB_SCORE_TOO_LOW"
        )

    return {

        "candidate_id":
            candidate.get(
                "candidate_id"
            ),

        "candidate_type":
            candidate_type,

        "scope":
            candidate.get(
                "scope"
            ),

        "status":
            status,

        "reason":
            reason,

        "scores": {

            "safety":
                safety_score,

            "security_gain":
                security_gain,

            "stability":
                stability,

            "reversibility":
                reversibility,

            "containment":
                containment
        },

        "final_score":
            round(
                final_score,
                2
            ),

        "requires_confirmation":
            requires_confirmation,

        "fingerprint":
            candidate.get(
                "fingerprint"
            ),

        "host_modified":
            False,

        "commands_executed":
            False,

        "payload_executed":
            False,

        "deployment_allowed":
            False
    }


# ============================================================
# LAB
# ============================================================

def run_mitigation_lab(
    candidate_set
):

    lab_id = (
        generate_lab_id()
    )

    validation = (
        validate_candidate_set(
            candidate_set
        )
    )

    if not validation.get(
        "valid",
        False
    ):

        result = {

            "lab_id":
                lab_id,

            "created_at":
                utc_now(),

            "status":
                "FAILED",

            "reason":
                "CANDIDATE_SET_INVALID",

            "validation":
                validation,

            "winner":
                None,

            "host_modified":
                False,

            "commands_executed":
                False,

            "payload_executed":
                False
        }

        save_lab_result(
            result
        )

        return result

    evaluations = []

    candidates = candidate_set.get(
        "candidates",
        []
    )

    for candidate in candidates:

        evaluations.append(
            evaluate_candidate(
                candidate
            )
        )

    accepted = [

        evaluation

        for evaluation
        in evaluations

        if evaluation.get(
            "status"
        )
        ==
        "ACCEPT"

    ]

    reviews = [

        evaluation

        for evaluation
        in evaluations

        if evaluation.get(
            "status"
        )
        ==
        "REVIEW"

    ]

    winner = None

    if accepted:

        winner = max(
            accepted,
            key=lambda item:
                item.get(
                    "final_score",
                    0
                )
        )

    elif reviews:

        winner = max(
            reviews,
            key=lambda item:
                item.get(
                    "final_score",
                    0
                )
        )

    # ========================================================
    # LAB STATUS
    # ========================================================

    if winner is None:

        status = "NO_SAFE_CANDIDATE"

        decision = "REJECT"

    elif winner.get(
        "status"
    ) == "ACCEPT":

        status = "WINNER_SELECTED"

        decision = "ACCEPT"

    else:

        status = (
            "MANUAL_REVIEW_REQUIRED"
        )

        decision = "REVIEW"

    # ========================================================
    # RESULT
    # ========================================================

    result = {

        "lab_id":
            lab_id,

        "created_at":
            utc_now(),

        "version":
            "2.0",

        "status":
            status,

        "decision":
            decision,

        "candidate_count":
            len(
                candidates
            ),

        "accepted_candidates":
            len(
                accepted
            ),

        "review_candidates":
            len(
                reviews
            ),

        "rejected_candidates":
            len(
                evaluations
            )
            -
            len(
                accepted
            )
            -
            len(
                reviews
            ),

        "winner":
            winner,

        "evaluations":
            evaluations,

        # ====================================================
        # SAFETY BOUNDARIES
        # ====================================================

        "host_modified":
            False,

        "commands_executed":
            False,

        "payload_executed":
            False,

        "privileged_execution":
            False,

        "deployment_allowed":
            False
    }

    save_lab_result(
        result
    )

    return result


# ============================================================
# WINNER VALIDATION
# ============================================================

def validate_lab_winner(
    lab_result
):

    if not isinstance(
        lab_result,
        dict
    ):

        return {

            "valid":
                False,

            "reason":
                "INVALID_LAB_RESULT"
        }

    winner = lab_result.get(
        "winner"
    )

    if winner is None:

        return {

            "valid":
                False,

            "reason":
                "NO_WINNER"
        }

    if (
        winner.get(
            "status"
        )
        !=
        "ACCEPT"
    ):

        return {

            "valid":
                False,

            "reason":
                "WINNER_NOT_ACCEPTED"
        }

    if winner.get(
        "final_score",
        0
    ) < 75:

        return {

            "valid":
                False,

            "reason":
                "WINNER_SCORE_TOO_LOW"
        }

    if lab_result.get(
        "host_modified",
        False
    ):

        return {

            "valid":
                False,

            "reason":
                "HOST_MODIFICATION_DETECTED"
        }

    if lab_result.get(
        "commands_executed",
        False
    ):

        return {

            "valid":
                False,

            "reason":
                "COMMAND_EXECUTION_DETECTED"
        }

    if lab_result.get(
        "payload_executed",
        False
    ):

        return {

            "valid":
                False,

            "reason":
                "PAYLOAD_EXECUTION_DETECTED"
        }

    return {

        "valid":
            True,

        "reason":
            "LAB_WINNER_VALIDATED",

        "candidate_id":
            winner.get(
                "candidate_id"
            ),

        "candidate_type":
            winner.get(
                "candidate_type"
            ),

        "scope":
            winner.get(
                "scope"
            ),

        "score":
            winner.get(
                "final_score"
            ),

        "requires_confirmation":
            winner.get(
                "requires_confirmation",
                False
            ),

        "deployment_allowed":
            False
    }


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    from core.remediation import (
        generate_remediation_plan
    )

    from core.remediation_evaluator import (
        evaluate_remediation_plan
    )

    from core.mitigation import (
        generate_mitigation_candidates
    )

    analysis = {
        "severity":
            "CRITICAL",

        "score":
            80
    }

    behavior = {
        "behavior_level":
            "CRITICAL",

        "behavior_score":
            90,

        "behavior_type":
            "REPEATED_CRITICAL_ACTIVITY"
    }

    anomaly = {
        "anomaly_level":
            "HIGH",

        "anomaly_score":
            70,

        "anomaly_reasons":
            [
                "LAB_TEST"
            ]
    }

    reputation = {
        "known_source":
            True,

        "reputation_score":
            70
    }

    learning = {
        "ml_score":
            88,

        "ml_level":
            "CRITICAL",

        "ml_confidence":
            90
    }

    fusion = {
        "global_score":
            92,

        "global_level":
            "CRITICAL",

        "fusion_reasons":
            []
    }

    context = {
        "context_level":
            "CRITICAL"
    }

    response = {
        "containment_requested":
            True
    }

    integrity = {
        "status":
            "CLEAN",

        "clean":
            True
    }

    plan = (
        generate_remediation_plan(
            analysis=analysis,
            behavior=behavior,
            anomaly=anomaly,
            reputation=reputation,
            learning=learning,
            fusion=fusion,
            context=context,
            response=response,
            integrity=integrity
        )
    )

    remediation_evaluation = (
        evaluate_remediation_plan(
            plan
        )
    )

    candidates = (
        generate_mitigation_candidates(
            plan,
            remediation_evaluation
        )
    )

    lab = (
        run_mitigation_lab(
            candidates
        )
    )

    winner_validation = (
        validate_lab_winner(
            lab
        )
    )

    return {

        "candidate_count":
            candidates.get(
                "candidate_count",
                0
            ),

        "lab":
            lab,

        "winner_validation":
            winner_validation
    }