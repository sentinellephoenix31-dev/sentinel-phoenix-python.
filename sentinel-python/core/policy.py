import threading
import time


_lock = threading.Lock()

_source_state = {}


ACTION_PRIORITY = {
    "OBSERVE": 0,
    "MONITOR": 1,
    "HEIGHTEN_MONITORING": 2,
    "CONTAIN_DECOY": 3
}


def strongest_action(
    first,
    second
):
    first_value = ACTION_PRIORITY.get(
        first,
        0
    )

    second_value = ACTION_PRIORITY.get(
        second,
        0
    )

    if second_value > first_value:
        return second

    return first


def apply_policy(
    source_ip,
    fusion,
    behavior,
    anomaly,
    context
):
    """
    SENTINEL PHOENIX
    Policy Engine V2

    Combine :
    - Risk Fusion
    - Behavior
    - Anomaly
    - Context Engine

    CONTAIN_DECOY signifie uniquement
    confinement vers l'environnement leurre.
    """

    now = time.time()

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

    confidence = int(
        fusion.get(
            "confidence",
            0
        )
    )

    reasons = []

    # ============================================================
    # DECISION DE BASE
    # ============================================================

    if (
        global_level == "CRITICAL"
        and
        confidence >= 80
    ):

        action = "CONTAIN_DECOY"

        reasons.append(
            "CRITICAL_GLOBAL_RISK"
        )

    elif global_level == "HIGH":

        action = (
            "HEIGHTEN_MONITORING"
        )

        reasons.append(
            "HIGH_GLOBAL_RISK"
        )

    elif global_level == "MEDIUM":

        action = "MONITOR"

        reasons.append(
            "MEDIUM_GLOBAL_RISK"
        )

    else:

        action = "OBSERVE"

        reasons.append(
            "LOW_GLOBAL_RISK"
        )

    # ============================================================
    # CONTEXT ENGINE
    # ============================================================

    context_action = context.get(
        "recommended_action",
        "OBSERVE"
    )

    previous_action = action

    action = strongest_action(
        action,
        context_action
    )

    if action != previous_action:

        reasons.append(
            "CONTEXT_ESCALATION"
        )

    # ============================================================
    # COMPORTEMENT REPETE
    # ============================================================

    if (
        behavior.get(
            "behavior_type"
        )
        ==
        "REPEATED_CRITICAL_ACTIVITY"
    ):

        reasons.append(
            "REPEATED_CRITICAL_ACTIVITY"
        )

        action = strongest_action(
            action,
            "HEIGHTEN_MONITORING"
        )

    # ============================================================
    # ANOMALIES MULTIPLES
    # ============================================================

    anomaly_reasons = anomaly.get(
        "anomaly_reasons",
        []
    )

    if len(
        anomaly_reasons
    ) >= 3:

        reasons.append(
            "MULTIPLE_ANOMALY_SIGNALS"
        )

    # ============================================================
    # PARAMETRES DE REPONSE
    # ============================================================

    if action == "CONTAIN_DECOY":

        monitoring_level = "MAXIMUM"

        containment_requested = True

    elif action == "HEIGHTEN_MONITORING":

        monitoring_level = "HIGH"

        containment_requested = False

    elif action == "MONITOR":

        monitoring_level = "MEDIUM"

        containment_requested = False

    else:

        monitoring_level = "NORMAL"

        containment_requested = False

    # ============================================================
    # MEMOIRE COURTE DE LA SOURCE
    # ============================================================

    with _lock:

        previous = _source_state.get(
            source_ip,
            {
                "events": 0,
                "containment_requests": 0
            }
        )

        previous[
            "events"
        ] += 1

        if containment_requested:

            previous[
                "containment_requests"
            ] += 1

        previous[
            "last_seen"
        ] = now

        previous[
            "last_action"
        ] = action

        previous[
            "last_global_score"
        ] = global_score

        previous[
            "last_context_score"
        ] = context.get(
            "context_score",
            0
        )

        _source_state[
            source_ip
        ] = previous

        source_events = previous[
            "events"
        ]

        containment_count = previous[
            "containment_requests"
        ]

    response_id = (
        f"{source_ip}-"
        f"{int(now * 1000)}"
    )

    return {

        "response_id":
            response_id,

        "action":
            action,

        "monitoring_level":
            monitoring_level,

        "containment_requested":
            containment_requested,

        "response_reasons":
            reasons,

        "source_events":
            source_events,

        "containment_count":
            containment_count,

        "policy_status":
            "DECISION_READY",

        "context_used":
            True
    }