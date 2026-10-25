import hashlib
import json
import os
import secrets

from datetime import datetime, timezone


# ============================================================
# SENTINEL PHOENIX
# PATCH / MITIGATION CANDIDATE ENGINE V1
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

CANDIDATE_LOG = os.path.join(
    DATA_DIR,
    "mitigation_candidates.jsonl"
)


# ============================================================
# CANDIDATE TYPES
# ============================================================

ALLOWED_CANDIDATE_TYPES = {
    "MONITORING_PROFILE",
    "DECEPTION_PROFILE",
    "SESSION_ISOLATION",
    "EVIDENCE_PRESERVATION",
    "REPUTATION_POLICY",
    "MODEL_REVIEW",
    "RECOVERY_RECOMMENDATION"
}


# ============================================================
# SCOPE
# ============================================================

ALLOWED_SCOPES = {
    "SENTINEL_INTERNAL",
    "SESSION_ONLY",
    "DECOY_ONLY",
    "SANDBOX_ONLY"
}


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def generate_candidate_id():

    return (
        "mit-"
        +
        secrets.token_hex(8)
    )


def fingerprint_candidate(
    candidate
):

    serialized = json.dumps(
        candidate,
        sort_keys=True,
        separators=(
            ",",
            ":"
        ),
        ensure_ascii=False
    )

    return hashlib.sha256(
        serialized.encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================
# SAFE CANDIDATE BUILDER
# ============================================================

def build_candidate(
    candidate_type,
    scope,
    reason,
    expected_effect,
    reversible=True,
    requires_confirmation=False
):

    if candidate_type not in ALLOWED_CANDIDATE_TYPES:

        raise ValueError(
            "Unsupported candidate type"
        )

    if scope not in ALLOWED_SCOPES:

        raise ValueError(
            "Unsupported candidate scope"
        )

    candidate = {

        "candidate_id":
            generate_candidate_id(),

        "created_at":
            utc_now(),

        "version":
            "1.0",

        "candidate_type":
            candidate_type,

        "scope":
            scope,

        "reason":
            str(
                reason
            )[:300],

        "expected_effect":
            str(
                expected_effect
            )[:300],

        "reversible":
            bool(
                reversible
            ),

        "requires_confirmation":
            bool(
                requires_confirmation
            ),

        # ====================================================
        # HARD SAFETY LIMITS
        # ====================================================

        "host_modification":
            False,

        "host_execution":
            False,

        "shell_execution":
            False,

        "payload_execution":
            False,

        "network_access_required":
            False,

        "privileged_execution":
            False,

        "deployment_allowed":
            False,

        "status":
            "CANDIDATE"
    }

    candidate[
        "fingerprint"
    ] = fingerprint_candidate(
        candidate
    )

    return candidate


# ============================================================
# TRANSLATE REMEDIATION ACTION
# ============================================================

def candidate_from_action(
    action
):

    name = action.get(
        "action"
    )

    reason = action.get(
        "reason",
        "UNSPECIFIED"
    )

    requires_confirmation = bool(
        action.get(
            "requires_confirmation",
            False
        )
    )

    # ========================================================
    # OBSERVE
    # ========================================================

    if name == "OBSERVE":

        return build_candidate(
            candidate_type=
                "MONITORING_PROFILE",

            scope=
                "SENTINEL_INTERNAL",

            reason=
                reason,

            expected_effect=
                (
                    "Maintain observation without "
                    "changing the protected host."
                ),

            reversible=True,

            requires_confirmation=False
        )

    # ========================================================
    # INCREASE MONITORING
    # ========================================================

    if name == "INCREASE_MONITORING":

        return build_candidate(
            candidate_type=
                "MONITORING_PROFILE",

            scope=
                "SENTINEL_INTERNAL",

            reason=
                reason,

            expected_effect=
                (
                    "Increase Sentinel telemetry "
                    "and analysis intensity."
                ),

            reversible=True,

            requires_confirmation=False
        )

    # ========================================================
    # PRESERVE EVIDENCE
    # ========================================================

    if name == "PRESERVE_EVIDENCE":

        return build_candidate(
            candidate_type=
                "EVIDENCE_PRESERVATION",

            scope=
                "SENTINEL_INTERNAL",

            reason=
                reason,

            expected_effect=
                (
                    "Preserve Sentinel event metadata "
                    "for later forensic review."
                ),

            reversible=True,

            requires_confirmation=False
        )

    # ========================================================
    # DECEPTION
    # ========================================================

    if name == "ACTIVATE_DECEPTION":

        return build_candidate(
            candidate_type=
                "DECEPTION_PROFILE",

            scope=
                "DECOY_ONLY",

            reason=
                reason,

            expected_effect=
                (
                    "Route suspicious interaction "
                    "toward the controlled decoy."
                ),

            reversible=True,

            requires_confirmation=False
        )

    # ========================================================
    # ISOLATION REVIEW
    # ========================================================

    if name == "ISOLATION_REVIEW":

        return build_candidate(
            candidate_type=
                "SESSION_ISOLATION",

            scope=
                "SESSION_ONLY",

            reason=
                reason,

            expected_effect=
                (
                    "Prepare an isolation candidate "
                    "for the suspicious session."
                ),

            reversible=True,

            requires_confirmation=True
        )

    # ========================================================
    # RECOVERY REVIEW
    # ========================================================

    if name == "RECOVERY_REVIEW":

        return build_candidate(
            candidate_type=
                "RECOVERY_RECOMMENDATION",

            scope=
                "SENTINEL_INTERNAL",

            reason=
                reason,

            expected_effect=
                (
                    "Recommend Phoenix Recovery "
                    "validation before restoration."
                ),

            reversible=True,

            requires_confirmation=True
        )

    # ========================================================
    # MODEL REVIEW
    # ========================================================

    if name == "MODEL_REVIEW":

        return build_candidate(
            candidate_type=
                "MODEL_REVIEW",

            scope=
                "SENTINEL_INTERNAL",

            reason=
                reason,

            expected_effect=
                (
                    "Request Champion/Challenger "
                    "model re-evaluation."
                ),

            reversible=True,

            requires_confirmation=False
        )

    # ========================================================
    # REPUTATION REVIEW
    # ========================================================

    if name == "REPUTATION_REVIEW":

        return build_candidate(
            candidate_type=
                "REPUTATION_POLICY",

            scope=
                "SENTINEL_INTERNAL",

            reason=
                reason,

            expected_effect=
                (
                    "Increase historical scrutiny "
                    "for the source profile."
                ),

            reversible=True,

            requires_confirmation=False
        )

    return None


# ============================================================
# GENERATE CANDIDATES
# ============================================================

def generate_mitigation_candidates(
    remediation_plan,
    remediation_evaluation
):

    if not isinstance(
        remediation_plan,
        dict
    ):

        return {
            "generated":
                False,

            "reason":
                "INVALID_REMEDIATION_PLAN",

            "candidates":
                []
        }

    if not isinstance(
        remediation_evaluation,
        dict
    ):

        return {
            "generated":
                False,

            "reason":
                "INVALID_REMEDIATION_EVALUATION",

            "candidates":
                []
        }

    if (
        remediation_evaluation.get(
            "status"
        )
        !=
        "ACCEPT"
    ):

        return {
            "generated":
                False,

            "reason":
                "REMEDIATION_NOT_ACCEPTED",

            "candidates":
                []
        }

    candidates = []

    for action in remediation_plan.get(
        "actions",
        []
    ):

        candidate = (
            candidate_from_action(
                action
            )
        )

        if candidate is not None:

            candidates.append(
                candidate
            )

    return {

        "generated":
            True,

        "reason":
            "CANDIDATES_GENERATED",

        "plan_id":
            remediation_plan.get(
                "plan_id"
            ),

        "evaluation_id":
            remediation_evaluation.get(
                "evaluation_id"
            ),

        "candidate_count":
            len(
                candidates
            ),

        "candidates":
            candidates,

        "host_modified":
            False,

        "commands_executed":
            False,

        "payload_executed":
            False
    }


# ============================================================
# CANDIDATE VALIDATION
# ============================================================

def validate_candidate(
    candidate
):

    if not isinstance(
        candidate,
        dict
    ):

        return {
            "valid":
                False,

            "reason":
                "INVALID_CANDIDATE"
        }

    candidate_type = (
        candidate.get(
            "candidate_type"
        )
    )

    scope = candidate.get(
        "scope"
    )

    if (
        candidate_type
        not in
        ALLOWED_CANDIDATE_TYPES
    ):

        return {
            "valid":
                False,

            "reason":
                "UNSUPPORTED_CANDIDATE_TYPE"
        }

    if scope not in ALLOWED_SCOPES:

        return {
            "valid":
                False,

            "reason":
                "UNSUPPORTED_SCOPE"
        }

    forbidden_true_fields = (
        "host_modification",
        "host_execution",
        "shell_execution",
        "payload_execution",
        "network_access_required",
        "privileged_execution",
        "deployment_allowed"
    )

    for field in forbidden_true_fields:

        if candidate.get(
            field,
            False
        ):

            return {
                "valid":
                    False,

                "reason":
                    "FORBIDDEN_CAPABILITY",

                "field":
                    field
            }

    forbidden_fields = {
        "command",
        "commands",
        "shell",
        "script",
        "exec",
        "executable",
        "payload",
        "docker_args",
        "sudo",
        "powershell"
    }

    for field in forbidden_fields:

        if field in candidate:

            return {
                "valid":
                    False,

                "reason":
                    "EXECUTION_FIELD_PRESENT",

                "field":
                    field
            }

    stored_fingerprint = (
        candidate.get(
            "fingerprint"
        )
    )

    if not stored_fingerprint:

        return {
            "valid":
                False,

            "reason":
                "MISSING_FINGERPRINT"
        }

    candidate_copy = dict(
        candidate
    )

    candidate_copy.pop(
        "fingerprint",
        None
    )

    calculated = (
        fingerprint_candidate(
            candidate_copy
        )
    )

    if calculated != stored_fingerprint:

        return {
            "valid":
                False,

            "reason":
                "CANDIDATE_FINGERPRINT_MISMATCH"
        }

    return {
        "valid":
            True,

        "reason":
            "CANDIDATE_VALIDATED",

        "candidate_id":
            candidate.get(
                "candidate_id"
            ),

        "candidate_type":
            candidate_type,

        "scope":
            scope,

        "requires_confirmation":
            candidate.get(
                "requires_confirmation",
                False
            )
    }


# ============================================================
# BATCH VALIDATION
# ============================================================

def validate_candidate_set(
    candidate_set
):

    candidates = candidate_set.get(
        "candidates",
        []
    )

    results = []

    all_valid = True

    for candidate in candidates:

        result = (
            validate_candidate(
                candidate
            )
        )

        results.append(
            result
        )

        if not result.get(
            "valid",
            False
        ):

            all_valid = False

    return {

        "valid":
            all_valid,

        "candidate_count":
            len(
                candidates
            ),

        "validated":
            sum(
                1
                for result
                in results
                if result.get(
                    "valid",
                    False
                )
            ),

        "requires_confirmation":
            any(
                result.get(
                    "requires_confirmation",
                    False
                )
                for result
                in results
            ),

        "results":
            results
    }


# ============================================================
# SAVE CANDIDATES
# ============================================================

def save_candidate_set(
    candidate_set
):

    validation = (
        validate_candidate_set(
            candidate_set
        )
    )

    if not validation.get(
        "valid",
        False
    ):

        return {
            "saved":
                False,

            "reason":
                "CANDIDATE_VALIDATION_FAILED",

            "validation":
                validation
        }

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    event = {

        "timestamp":
            utc_now(),

        "type":
            "MITIGATION_CANDIDATE_SET",

        "plan_id":
            candidate_set.get(
                "plan_id"
            ),

        "evaluation_id":
            candidate_set.get(
                "evaluation_id"
            ),

        "candidates":
            candidate_set.get(
                "candidates",
                []
            )
    }

    with open(
        CANDIDATE_LOG,
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

    return {

        "saved":
            True,

        "reason":
            "CANDIDATES_SAVED",

        "candidate_count":
            len(
                candidate_set.get(
                    "candidates",
                    []
                )
            ),

        "file":
            CANDIDATE_LOG
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
                "TEST"
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

    remediation_plan = (
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
            remediation_plan
        )
    )

    candidate_set = (
        generate_mitigation_candidates(
            remediation_plan,
            remediation_evaluation
        )
    )

    validation = (
        validate_candidate_set(
            candidate_set
        )
    )

    saved = (
        save_candidate_set(
            candidate_set
        )
        if validation.get(
            "valid",
            False
        )
        else
        {
            "saved": False
        }
    )

    return {

        "remediation_status":
            remediation_evaluation.get(
                "status"
            ),

        "candidate_set":
            candidate_set,

        "validation":
            validation,

        "saved":
            saved
    }