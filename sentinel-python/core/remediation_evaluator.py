import json
import os
import secrets

from datetime import datetime, timezone

from core.remediation import (
    validate_remediation_plan,
    simulate_remediation_plan
)


# ============================================================
# SENTINEL PHOENIX
# REMEDIATION SANDBOX EVALUATOR V1
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

EVALUATION_LOG = os.path.join(
    DATA_DIR,
    "remediation_evaluations.jsonl"
)


# ============================================================
# POLICY
# ============================================================

MINIMUM_EFFECTIVENESS = 15

MAXIMUM_REMAINING_RISK_FOR_ACCEPT = 60

CRITICAL_REMAINING_RISK_LIMIT = 75


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def evaluation_id():

    return (
        "eval-"
        +
        secrets.token_hex(8)
    )


def save_evaluation(
    evaluation
):

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    event = {
        "timestamp":
            utc_now(),

        "type":
            "REMEDIATION_EVALUATION",

        "evaluation":
            evaluation
    }

    with open(
        EVALUATION_LOG,
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
# ACTION ANALYSIS
# ============================================================

def analyse_actions(
    plan
):

    actions = plan.get(
        "actions",
        []
    )

    requires_confirmation = False

    high_priority_actions = []

    safe_actions = []

    for action in actions:

        name = action.get(
            "action"
        )

        priority = int(
            action.get(
                "priority",
                0
            )
        )

        if action.get(
            "requires_confirmation",
            False
        ):

            requires_confirmation = True

        if priority >= 80:

            high_priority_actions.append(
                name
            )

        if (
            not action.get(
                "host_modification",
                False
            )
            and
            not action.get(
                "payload_execution",
                False
            )
        ):

            safe_actions.append(
                name
            )

    return {
        "requires_confirmation":
            requires_confirmation,

        "high_priority_actions":
            high_priority_actions,

        "safe_actions":
            safe_actions,

        "total_actions":
            len(
                actions
            )
    }


# ============================================================
# EFFECTIVENESS SCORE
# ============================================================

def calculate_effectiveness(
    simulation
):

    original_risk = float(
        simulation.get(
            "original_risk",
            0
        )
    )

    reduction = float(
        simulation.get(
            "estimated_risk_reduction",
            0
        )
    )

    if original_risk <= 0:

        return 0.0

    effectiveness = (
        reduction
        /
        original_risk
    ) * 100

    effectiveness = max(
        0,
        min(
            100,
            effectiveness
        )
    )

    return round(
        effectiveness,
        2
    )


# ============================================================
# EVALUATION ENGINE
# ============================================================

def evaluate_remediation_plan(
    plan
):
    """
    Évalue un plan de remédiation sans l'exécuter.

    Aucun changement sur l'hôte.
    Aucun payload exécuté.
    Aucun shell.
    """

    identifier = (
        evaluation_id()
    )

    # ========================================================
    # PLAN VALIDATION
    # ========================================================

    validation = (
        validate_remediation_plan(
            plan
        )
    )

    if not validation.get(
        "valid",
        False
    ):

        evaluation = {
            "evaluation_id":
                identifier,

            "plan_id":
                plan.get(
                    "plan_id"
                ),

            "created_at":
                utc_now(),

            "status":
                "REJECT",

            "reason":
                "PLAN_VALIDATION_FAILED",

            "validation":
                validation,

            "host_modified":
                False,

            "payload_executed":
                False
        }

        save_evaluation(
            evaluation
        )

        return evaluation

    # ========================================================
    # SAFE SIMULATION
    # ========================================================

    simulation = (
        simulate_remediation_plan(
            plan
        )
    )

    if not simulation.get(
        "simulated",
        False
    ):

        evaluation = {
            "evaluation_id":
                identifier,

            "plan_id":
                plan.get(
                    "plan_id"
                ),

            "created_at":
                utc_now(),

            "status":
                "REJECT",

            "reason":
                "SIMULATION_FAILED",

            "simulation":
                simulation,

            "host_modified":
                False,

            "payload_executed":
                False
        }

        save_evaluation(
            evaluation
        )

        return evaluation

    # ========================================================
    # ACTION INSPECTION
    # ========================================================

    action_analysis = (
        analyse_actions(
            plan
        )
    )

    # ========================================================
    # SCORES
    # ========================================================

    original_risk = float(
        simulation.get(
            "original_risk",
            0
        )
    )

    remaining_risk = float(
        simulation.get(
            "estimated_remaining_risk",
            original_risk
        )
    )

    reduction = float(
        simulation.get(
            "estimated_risk_reduction",
            0
        )
    )

    effectiveness = (
        calculate_effectiveness(
            simulation
        )
    )

    reasons = []

    # ========================================================
    # SAFETY CHECK
    # ========================================================

    safety_passed = True

    if simulation.get(
        "host_modified",
        False
    ):

        safety_passed = False

        reasons.append(
            "HOST_MODIFICATION_DETECTED"
        )

    if simulation.get(
        "payload_executed",
        False
    ):

        safety_passed = False

        reasons.append(
            "PAYLOAD_EXECUTION_DETECTED"
        )

    for action in plan.get(
        "actions",
        []
    ):

        if action.get(
            "host_modification",
            False
        ):

            safety_passed = False

            reasons.append(
                "UNSAFE_HOST_ACTION"
            )

        if action.get(
            "payload_execution",
            False
        ):

            safety_passed = False

            reasons.append(
                "UNSAFE_PAYLOAD_ACTION"
            )

    # ========================================================
    # EFFECTIVENESS CHECK
    # ========================================================

    effectiveness_passed = (
        reduction
        >=
        MINIMUM_EFFECTIVENESS
    )

    if effectiveness_passed:

        reasons.append(
            "MEANINGFUL_RISK_REDUCTION"
        )

    else:

        reasons.append(
            "INSUFFICIENT_RISK_REDUCTION"
        )

    # ========================================================
    # REMAINING RISK
    # ========================================================

    remaining_risk_acceptable = (
        remaining_risk
        <=
        MAXIMUM_REMAINING_RISK_FOR_ACCEPT
    )

    if remaining_risk_acceptable:

        reasons.append(
            "REMAINING_RISK_ACCEPTABLE"
        )

    else:

        reasons.append(
            "REMAINING_RISK_TOO_HIGH"
        )

    # ========================================================
    # CRITICAL EVENT SPECIAL RULE
    # ========================================================

    critical_event = (
        str(
            plan.get(
                "global_level",
                ""
            )
        ).upper()
        ==
        "CRITICAL"
    )

    critical_control_passed = True

    if critical_event:

        critical_control_passed = (
            remaining_risk
            <=
            CRITICAL_REMAINING_RISK_LIMIT
        )

        if critical_control_passed:

            reasons.append(
                "CRITICAL_RISK_REDUCED"
            )

        else:

            reasons.append(
                "CRITICAL_RISK_REMAINS_TOO_HIGH"
            )

    # ========================================================
    # FINAL DECISION
    # ========================================================

    accepted = (

        safety_passed

        and

        effectiveness_passed

        and

        remaining_risk_acceptable

        and

        critical_control_passed
    )

    if accepted:

        status = "ACCEPT"

        reasons.append(
            "REMEDIATION_CANDIDATE_ACCEPTED"
        )

    else:

        status = "REJECT"

        reasons.append(
            "REMEDIATION_CANDIDATE_REJECTED"
        )

    # ========================================================
    # CONFIDENCE
    # ========================================================

    confidence = 50

    if safety_passed:

        confidence += 20

    if effectiveness_passed:

        confidence += 10

    if remaining_risk_acceptable:

        confidence += 10

    if critical_control_passed:

        confidence += 5

    if (
        action_analysis[
            "total_actions"
        ]
        > 0
    ):

        confidence += 5

    confidence = min(
        confidence,
        95
    )

    # ========================================================
    # RESULT
    # ========================================================

    evaluation = {

        "evaluation_id":
            identifier,

        "plan_id":
            plan.get(
                "plan_id"
            ),

        "created_at":
            utc_now(),

        "version":
            "1.0",

        "status":
            status,

        "original_risk":
            original_risk,

        "estimated_reduction":
            reduction,

        "estimated_remaining_risk":
            remaining_risk,

        "effectiveness_percent":
            effectiveness,

        "confidence":
            confidence,

        "safety_passed":
            safety_passed,

        "effectiveness_passed":
            effectiveness_passed,

        "remaining_risk_acceptable":
            remaining_risk_acceptable,

        "critical_control_passed":
            critical_control_passed,

        "requires_confirmation":
            action_analysis[
                "requires_confirmation"
            ],

        "action_analysis":
            action_analysis,

        "decision_reasons":
            list(
                dict.fromkeys(
                    reasons
                )
            ),

        # Important :
        # aucune action réelle dans V1.
        "host_modified":
            False,

        "payload_executed":
            False,

        "commands_executed":
            False,

        "deployment_allowed":
            False
    }

    save_evaluation(
        evaluation
    )

    return evaluation


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    from core.remediation import (
        generate_remediation_plan
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

    plan = generate_remediation_plan(
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

    evaluation = (
        evaluate_remediation_plan(
            plan
        )
    )

    return {
        "plan":
            plan,

        "evaluation":
            evaluation
    }