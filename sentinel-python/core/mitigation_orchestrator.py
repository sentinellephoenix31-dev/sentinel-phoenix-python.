import json
import os
import secrets

from datetime import datetime, timezone

from core.mitigation import (
    validate_candidate
)

from core.mitigation_lab import (
    validate_lab_winner
)


# ============================================================
# SENTINEL PHOENIX
# CONTROLLED MITIGATION ORCHESTRATOR V1
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

ORCHESTRATOR_LOG = os.path.join(
    DATA_DIR,
    "mitigation_orchestrator.jsonl"
)


# ============================================================
# ACTIONS EXECUTABLES V1
#
# Elles restent internes à Sentinel.
# Aucune commande OS.
# ============================================================

EXECUTABLE_TYPES = {
    "MONITORING_PROFILE",
    "DECEPTION_PROFILE",
    "EVIDENCE_PRESERVATION",
    "REPUTATION_POLICY",
    "MODEL_REVIEW"
}


# ============================================================
# ACTIONS QUI RESTENT EN REVIEW
# ============================================================

REVIEW_ONLY_TYPES = {
    "SESSION_ISOLATION",
    "RECOVERY_RECOMMENDATION"
}


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def execution_id():

    return (
        "exec-"
        +
        secrets.token_hex(8)
    )


def log_execution(
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
        ORCHESTRATOR_LOG,
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
# INTERNAL STATE
# ============================================================

def default_state():

    return {
        "monitoring_level":
            "NORMAL",

        "deception_requested":
            False,

        "evidence_preservation":
            False,

        "reputation_review":
            False,

        "model_review":
            False,

        "session_isolation":
            False,

        "recovery_requested":
            False
    }


# ============================================================
# CANDIDATE EXECUTION
# ============================================================

def apply_internal_candidate(
    candidate,
    state
):

    candidate_type = (
        candidate.get(
            "candidate_type"
        )
    )

    result = {
        "candidate_id":
            candidate.get(
                "candidate_id"
            ),

        "candidate_type":
            candidate_type,

        "applied":
            False,

        "status":
            "REJECTED",

        "reason":
            None,

        "host_modified":
            False,

        "commands_executed":
            False,

        "payload_executed":
            False
    }

    # ========================================================
    # MONITORING
    # ========================================================

    if (
        candidate_type
        ==
        "MONITORING_PROFILE"
    ):

        state[
            "monitoring_level"
        ] = "HIGH"

        result[
            "applied"
        ] = True

        result[
            "status"
        ] = "APPLIED"

        result[
            "reason"
        ] = (
            "INTERNAL_MONITORING_ESCALATED"
        )

        return result

    # ========================================================
    # DECEPTION
    # ========================================================

    if (
        candidate_type
        ==
        "DECEPTION_PROFILE"
    ):

        state[
            "deception_requested"
        ] = True

        result[
            "applied"
        ] = True

        result[
            "status"
        ] = "APPLIED"

        result[
            "reason"
        ] = (
            "DECEPTION_REQUEST_REGISTERED"
        )

        return result

    # ========================================================
    # EVIDENCE
    # ========================================================

    if (
        candidate_type
        ==
        "EVIDENCE_PRESERVATION"
    ):

        state[
            "evidence_preservation"
        ] = True

        result[
            "applied"
        ] = True

        result[
            "status"
        ] = "APPLIED"

        result[
            "reason"
        ] = (
            "EVIDENCE_PRESERVATION_ENABLED"
        )

        return result

    # ========================================================
    # REPUTATION
    # ========================================================

    if (
        candidate_type
        ==
        "REPUTATION_POLICY"
    ):

        state[
            "reputation_review"
        ] = True

        result[
            "applied"
        ] = True

        result[
            "status"
        ] = "APPLIED"

        result[
            "reason"
        ] = (
            "REPUTATION_REVIEW_REQUESTED"
        )

        return result

    # ========================================================
    # MODEL
    # ========================================================

    if (
        candidate_type
        ==
        "MODEL_REVIEW"
    ):

        state[
            "model_review"
        ] = True

        result[
            "applied"
        ] = True

        result[
            "status"
        ] = "APPLIED"

        result[
            "reason"
        ] = (
            "MODEL_REVIEW_REQUESTED"
        )

        return result

    # ========================================================
    # REVIEW-ONLY ACTIONS
    # ========================================================

    if (
        candidate_type
        in
        REVIEW_ONLY_TYPES
    ):

        result[
            "status"
        ] = "REVIEW_REQUIRED"

        result[
            "reason"
        ] = (
            "SENSITIVE_ACTION_NOT_AUTOMATIC_V1"
        )

        return result

    result[
        "reason"
    ] = (
        "UNSUPPORTED_CANDIDATE"
    )

    return result


# ============================================================
# ORCHESTRATION
# ============================================================

def orchestrate_lab_result(
    lab_result
):

    identifier = (
        execution_id()
    )

    # ========================================================
    # WINNER VALIDATION
    # ========================================================

    winner_validation = (
        validate_lab_winner(
            lab_result
        )
    )

    if not winner_validation.get(
        "valid",
        False
    ):

        result = {
            "execution_id":
                identifier,

            "status":
                "BLOCKED",

            "reason":
                winner_validation.get(
                    "reason"
                ),

            "state":
                default_state(),

            "host_modified":
                False,

            "commands_executed":
                False,

            "payload_executed":
                False
        }

        log_execution(
            "ORCHESTRATION_BLOCKED",
            result
        )

        return result

    winner = lab_result.get(
        "winner",
        {}
    )

    # ========================================================
    # FIND ORIGINAL CANDIDATE
    #
    # Le winner contient les informations du candidat évalué.
    # ========================================================

    candidate = None

    winner_id = winner.get(
        "candidate_id"
    )

    for evaluation in lab_result.get(
        "evaluations",
        []
    ):

        if (
            evaluation.get(
                "candidate_id"
            )
            ==
            winner_id
        ):

            candidate = evaluation

            break

    # Le résultat du lab n'est pas le candidat original complet.
    # On reconstruit uniquement un objet interne minimal,
    # sans champ d'exécution.

    candidate_type = winner.get(
        "candidate_type"
    )

    scope = winner.get(
        "scope"
    )

    if (
        candidate_type
        not in
        EXECUTABLE_TYPES
        and
        candidate_type
        not in
        REVIEW_ONLY_TYPES
    ):

        result = {
            "execution_id":
                identifier,

            "status":
                "BLOCKED",

            "reason":
                "WINNER_TYPE_NOT_ALLOWED",

            "candidate_type":
                candidate_type,

            "host_modified":
                False,

            "commands_executed":
                False,

            "payload_executed":
                False
        }

        log_execution(
            "ORCHESTRATION_BLOCKED",
            result
        )

        return result

    internal_candidate = {
        "candidate_id":
            winner_id,

        "candidate_type":
            candidate_type,

        "scope":
            scope,

        "requires_confirmation":
            winner.get(
                "requires_confirmation",
                False
            )
    }

    # ========================================================
    # STATE
    # ========================================================

    state = (
        default_state()
    )

    application = (
        apply_internal_candidate(
            internal_candidate,
            state
        )
    )

    # ========================================================
    # RESULT
    # ========================================================

    if application.get(
        "applied",
        False
    ):

        status = (
            "APPLIED_INTERNAL"
        )

    elif (
        application.get(
            "status"
        )
        ==
        "REVIEW_REQUIRED"
    ):

        status = (
            "REVIEW_REQUIRED"
        )

    else:

        status = (
            "BLOCKED"
        )

    result = {
        "execution_id":
            identifier,

        "created_at":
            utc_now(),

        "version":
            "1.0",

        "status":
            status,

        "winner":
            {
                "candidate_id":
                    winner_id,

                "candidate_type":
                    candidate_type,

                "scope":
                    scope,

                "score":
                    winner.get(
                        "final_score"
                    )
            },

        "application":
            application,

        "state":
            state,

        # ====================================================
        # HARD SAFETY BOUNDARIES
        # ====================================================

        "host_modified":
            False,

        "commands_executed":
            False,

        "payload_executed":
            False,

        "privileged_execution":
            False
    }

    log_execution(
        "MITIGATION_ORCHESTRATED",
        result
    )

    return result


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

    from core.mitigation_lab import (
        run_mitigation_lab
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
                "ORCHESTRATOR_TEST"
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

    orchestration = (
        orchestrate_lab_result(
            lab
        )
    )

    return {
        "lab_status":
            lab.get(
                "status"
            ),

        "winner":
            lab.get(
                "winner"
            ),

        "orchestration":
            orchestration
    }