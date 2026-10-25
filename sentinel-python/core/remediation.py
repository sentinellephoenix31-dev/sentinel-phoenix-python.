import json
import os
import secrets

from datetime import datetime, timezone


# ============================================================
# SENTINEL PHOENIX
# REMEDIATION PLANNER V1
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

REMEDIATION_LOG = os.path.join(
    DATA_DIR,
    "remediation_plans.jsonl"
)


# ============================================================
# ACTIONS AUTORISEES
# ============================================================

ALLOWED_ACTIONS = {
    "OBSERVE",
    "INCREASE_MONITORING",
    "PRESERVE_EVIDENCE",
    "ACTIVATE_DECEPTION",
    "ISOLATION_REVIEW",
    "RECOVERY_REVIEW",
    "MODEL_REVIEW",
    "REPUTATION_REVIEW"
}


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def generate_plan_id():

    return (
        "rem-"
        +
        secrets.token_hex(8)
    )


def clamp(
    value,
    minimum=0,
    maximum=100
):

    return max(
        minimum,
        min(
            maximum,
            value
        )
    )


# ============================================================
# ACTION BUILDER
# ============================================================

def build_action(
    action,
    reason,
    priority,
    scope="SENTINEL",
    confirmation=False
):

    return {
        "action":
            action,

        "reason":
            reason,

        "priority":
            priority,

        "scope":
            scope,

        "requires_confirmation":
            confirmation,

        # V1 interdit toute modification directe du host.
        "host_modification":
            False,

        "payload_execution":
            False
    }


# ============================================================
# PLAN GENERATOR
# ============================================================

def generate_remediation_plan(
    analysis,
    behavior,
    anomaly,
    reputation,
    learning,
    fusion,
    context,
    response,
    integrity=None
):

    """
    Génère un plan défensif.

    Cette version :
    - ne lance aucune commande
    - ne modifie aucun fichier système
    - ne touche pas au firewall
    - n'exécute aucun payload
    """

    plan_id = (
        generate_plan_id()
    )

    global_score = float(
        fusion.get(
            "global_score",
            0
        )
    )

    global_level = str(
        fusion.get(
            "global_level",
            "LOW"
        )
    ).upper()

    reputation_score = float(
        reputation.get(
            "reputation_score",
            0
        )
    )

    ml_score = float(
        learning.get(
            "ml_score",
            0
        )
    )

    ml_confidence = int(
        learning.get(
            "ml_confidence",
            0
        )
    )

    context_level = str(
        context.get(
            "context_level",
            "NORMAL"
        )
    ).upper()

    actions = []

    reasons = []

    # ========================================================
    # LOW RISK
    # ========================================================

    if global_level == "LOW":

        actions.append(
            build_action(
                action="OBSERVE",
                reason="LOW_GLOBAL_RISK",
                priority=10
            )
        )

        reasons.append(
            "LOW_GLOBAL_RISK"
        )

    # ========================================================
    # MEDIUM
    # ========================================================

    if global_level == "MEDIUM":

        actions.append(
            build_action(
                action="INCREASE_MONITORING",
                reason="MEDIUM_GLOBAL_RISK",
                priority=40
            )
        )

        reasons.append(
            "MEDIUM_GLOBAL_RISK"
        )

    # ========================================================
    # HIGH
    # ========================================================

    if global_level == "HIGH":

        actions.append(
            build_action(
                action="INCREASE_MONITORING",
                reason="HIGH_GLOBAL_RISK",
                priority=70
            )
        )

        actions.append(
            build_action(
                action="PRESERVE_EVIDENCE",
                reason="HIGH_RISK_EVENT",
                priority=75
            )
        )

        reasons.append(
            "HIGH_GLOBAL_RISK"
        )

    # ========================================================
    # CRITICAL
    # ========================================================

    if global_level == "CRITICAL":

        actions.append(
            build_action(
                action="PRESERVE_EVIDENCE",
                reason="CRITICAL_EVENT",
                priority=95
            )
        )

        actions.append(
            build_action(
                action="ACTIVATE_DECEPTION",
                reason="CRITICAL_GLOBAL_RISK",
                priority=100
            )
        )

        actions.append(
            build_action(
                action="ISOLATION_REVIEW",
                reason="CRITICAL_GLOBAL_RISK",
                priority=90,
                confirmation=True
            )
        )

        reasons.append(
            "CRITICAL_GLOBAL_RISK"
        )

    # ========================================================
    # CONTEXT
    # ========================================================

    if context_level in (
        "ELEVATED",
        "CRITICAL"
    ):

        if not any(
            item["action"]
            ==
            "INCREASE_MONITORING"

            for item
            in actions
        ):

            actions.append(
                build_action(
                    action="INCREASE_MONITORING",
                    reason="CONTEXT_ESCALATION",
                    priority=70
                )
            )

        reasons.append(
            "CONTEXT_ESCALATION"
        )

    # ========================================================
    # REPUTATION
    # ========================================================

    if reputation_score >= 60:

        actions.append(
            build_action(
                action="REPUTATION_REVIEW",
                reason="HIGH_RISK_HISTORY",
                priority=65
            )
        )

        reasons.append(
            "HIGH_RISK_HISTORY"
        )

    # ========================================================
    # ML CORRELATION
    # ========================================================

    if (
        ml_score >= 70
        and
        ml_confidence >= 70
    ):

        reasons.append(
            "STRONG_ML_RISK"
        )

    # ========================================================
    # ML DISAGREEMENT
    # ========================================================

    fusion_reasons = fusion.get(
        "fusion_reasons",
        []
    )

    if (
        "MODEL_DISAGREEMENT"
        in fusion_reasons
    ):

        actions.append(
            build_action(
                action="MODEL_REVIEW",
                reason="MODEL_DISAGREEMENT",
                priority=60
            )
        )

        reasons.append(
            "MODEL_DISAGREEMENT"
        )

    # ========================================================
    # INTEGRITY
    # ========================================================

    if integrity:

        integrity_clean = integrity.get(
            "clean",
            True
        )

        if not integrity_clean:

            actions.append(
                build_action(
                    action="RECOVERY_REVIEW",
                    reason="CORE_INTEGRITY_FAILURE",
                    priority=100,
                    confirmation=True
                )
            )

            reasons.append(
                "CORE_INTEGRITY_FAILURE"
            )

    # ========================================================
    # CONTAINMENT ALREADY REQUESTED
    # ========================================================

    if response.get(
        "containment_requested",
        False
    ):

        if not any(
            item["action"]
            ==
            "ACTIVATE_DECEPTION"

            for item
            in actions
        ):

            actions.append(
                build_action(
                    action="ACTIVATE_DECEPTION",
                    reason="POLICY_CONTAINMENT_REQUEST",
                    priority=100
                )
            )

        reasons.append(
            "POLICY_CONTAINMENT_REQUEST"
        )

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    unique_actions = {}

    for item in actions:

        name = item[
            "action"
        ]

        previous = unique_actions.get(
            name
        )

        if (
            previous is None
            or
            item["priority"]
            >
            previous["priority"]
        ):

            unique_actions[
                name
            ] = item

    actions = list(
        unique_actions.values()
    )

    actions.sort(
        key=lambda item: (
            item[
                "priority"
            ]
        ),
        reverse=True
    )

    # ========================================================
    # PLAN RISK
    # ========================================================

    remediation_urgency = (
        global_score
    )

    if context_level == "CRITICAL":

        remediation_urgency += 10

    if reputation_score >= 60:

        remediation_urgency += 5

    if (
        ml_score >= 80
        and
        ml_confidence >= 75
    ):

        remediation_urgency += 5

    remediation_urgency = round(
        clamp(
            remediation_urgency
        ),
        2
    )

    # ========================================================
    # RESULT
    # ========================================================

    plan = {
        "plan_id":
            plan_id,

        "created_at":
            utc_now(),

        "version":
            "1.0",

        "status":
            "PROPOSED",

        "global_level":
            global_level,

        "global_score":
            global_score,

        "context_level":
            context_level,

        "ml_score":
            ml_score,

        "ml_confidence":
            ml_confidence,

        "reputation_score":
            reputation_score,

        "remediation_urgency":
            remediation_urgency,

        "actions":
            actions,

        "reasons":
            list(
                dict.fromkeys(
                    reasons
                )
            ),

        "automatic_host_changes":
            False,

        "payload_execution":
            False,

        "requires_validation":
            True
    }

    return plan


# ============================================================
# VALIDATION
# ============================================================

def validate_remediation_plan(
    plan
):

    if not isinstance(
        plan,
        dict
    ):

        return {
            "valid":
                False,

            "reason":
                "INVALID_PLAN"
        }

    actions = plan.get(
        "actions",
        []
    )

    if not isinstance(
        actions,
        list
    ):

        return {
            "valid":
                False,

            "reason":
                "INVALID_ACTION_LIST"
        }

    forbidden = []

    for item in actions:

        action = item.get(
            "action"
        )

        if action not in ALLOWED_ACTIONS:

            forbidden.append(
                action
            )

        if item.get(
            "host_modification",
            False
        ):

            return {
                "valid":
                    False,

                "reason":
                    "HOST_MODIFICATION_FORBIDDEN_V1"
            }

        if item.get(
            "payload_execution",
            False
        ):

            return {
                "valid":
                    False,

                "reason":
                    "PAYLOAD_EXECUTION_FORBIDDEN"
            }

        # Un plan de V1 ne doit jamais
        # transporter une commande shell.

        forbidden_keys = {
            "command",
            "shell",
            "exec",
            "script",
            "payload"
        }

        if any(
            key in item
            for key
            in forbidden_keys
        ):

            return {
                "valid":
                    False,

                "reason":
                    "EXECUTION_FIELD_FORBIDDEN"
            }

    if forbidden:

        return {
            "valid":
                False,

            "reason":
                "UNKNOWN_ACTION",

            "actions":
                forbidden
        }

    return {
        "valid":
            True,

        "reason":
            "PLAN_VALIDATED",

        "actions":
            len(
                actions
            ),

        "requires_confirmation":
            any(
                item.get(
                    "requires_confirmation",
                    False
                )
                for item
                in actions
            )
    }


# ============================================================
# SIMULATION
# ============================================================

def simulate_remediation_plan(
    plan
):

    validation = (
        validate_remediation_plan(
            plan
        )
    )

    if not validation.get(
        "valid",
        False
    ):

        return {
            "simulated":
                False,

            "reason":
                validation.get(
                    "reason"
                )
        }

    reduction = 0

    simulated_actions = []

    effect_table = {

        "OBSERVE":
            0,

        "INCREASE_MONITORING":
            5,

        "PRESERVE_EVIDENCE":
            0,

        "ACTIVATE_DECEPTION":
            25,

        "ISOLATION_REVIEW":
            20,

        "RECOVERY_REVIEW":
            20,

        "MODEL_REVIEW":
            5,

        "REPUTATION_REVIEW":
            5
    }

    for action in plan.get(
        "actions",
        []
    ):

        name = action.get(
            "action"
        )

        estimated = effect_table.get(
            name,
            0
        )

        reduction += estimated

        simulated_actions.append(
            {
                "action":
                    name,

                "estimated_risk_reduction":
                    estimated,

                "executed":
                    False
            }
        )

    reduction = min(
        reduction,
        60
    )

    original_risk = float(
        plan.get(
            "global_score",
            0
        )
    )

    estimated_after = max(
        0,
        original_risk
        -
        reduction
    )

    return {
        "simulated":
            True,

        "plan_id":
            plan.get(
                "plan_id"
            ),

        "original_risk":
            original_risk,

        "estimated_risk_reduction":
            reduction,

        "estimated_remaining_risk":
            round(
                estimated_after,
                2
            ),

        "actions":
            simulated_actions,

        "host_modified":
            False,

        "payload_executed":
            False
    }


# ============================================================
# SAVE PLAN
# ============================================================

def save_remediation_plan(
    plan
):

    validation = (
        validate_remediation_plan(
            plan
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
                validation.get(
                    "reason"
                )
        }

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    event = {
        "timestamp":
            utc_now(),

        "type":
            "REMEDIATION_PLAN",

        "plan":
            plan
    }

    with open(
        REMEDIATION_LOG,
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

        "plan_id":
            plan.get(
                "plan_id"
            ),

        "file":
            REMEDIATION_LOG
    }


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    analysis = {
        "severity":
            "CRITICAL",

        "score":
            80,

        "indicators":
            [
                "test"
            ]
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
                "TEST_ANOMALY"
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
            90,

        "model_status":
            "READY"
    }

    fusion = {
        "global_score":
            92,

        "global_level":
            "CRITICAL",

        "fusion_reasons":
            [
                "ML_DETERMINISTIC_AGREEMENT"
            ]
    }

    context = {
        "context_level":
            "CRITICAL"
    }

    response = {
        "action":
            "CONTAIN_DECOY",

        "containment_requested":
            True
    }

    integrity = {
        "clean":
            True,

        "status":
            "CLEAN"
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

    validation = (
        validate_remediation_plan(
            plan
        )
    )

    simulation = (
        simulate_remediation_plan(
            plan
        )
    )

    return {
        "plan":
            plan,

        "validation":
            validation,

        "simulation":
            simulation
    }