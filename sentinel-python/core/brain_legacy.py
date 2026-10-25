from datetime import datetime, timezone


# ============================================================
# SENTINEL PHOENIX
# AI BRAIN / REASONING CORE V1
# ============================================================


BRAIN_VERSION = "1.0"


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

        return float(
            value
        )

    except (
        TypeError,
        ValueError
    ):

        return float(
            default
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


def unique(
    values
):

    return list(
        dict.fromkeys(
            values
        )
    )


# ============================================================
# SIGNAL EXTRACTION
# ============================================================

def extract_signals(
    analysis,
    behavior,
    anomaly,
    reputation,
    learning,
    fusion,
    context,
    response,
    deception,
    sandbox,
    integrity=None
):

    signals = []

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

    ml_score = safe_float(
        learning.get(
            "ml_score",
            0
        )
    )

    global_score = safe_float(
        fusion.get(
            "global_score",
            0
        )
    )

    # ========================================================
    # PAYLOAD
    # ========================================================

    if payload_score >= 70:

        signals.append(
            "STRONG_MALICIOUS_PAYLOAD_SIGNAL"
        )

    elif payload_score >= 40:

        signals.append(
            "SUSPICIOUS_PAYLOAD_SIGNAL"
        )

    indicators = analysis.get(
        "indicators",
        []
    )

    if indicators:

        signals.append(
            "KNOWN_THREAT_INDICATORS_PRESENT"
        )

    # ========================================================
    # BEHAVIOR
    # ========================================================

    if behavior_score >= 80:

        signals.append(
            "AGGRESSIVE_BEHAVIOR_PATTERN"
        )

    elif behavior_score >= 50:

        signals.append(
            "SUSPICIOUS_BEHAVIOR_PATTERN"
        )

    if (
        behavior.get(
            "behavior_type"
        )
        ==
        "REPEATED_CRITICAL_ACTIVITY"
    ):

        signals.append(
            "REPEATED_CRITICAL_ACTIVITY"
        )

    # ========================================================
    # ANOMALY
    # ========================================================

    if anomaly_score >= 70:

        signals.append(
            "STRONG_ANOMALY"
        )

    anomaly_reasons = anomaly.get(
        "anomaly_reasons",
        []
    )

    if len(
        anomaly_reasons
    ) >= 2:

        signals.append(
            "MULTIPLE_ANOMALIES"
        )

    # ========================================================
    # HISTORY
    # ========================================================

    if reputation.get(
        "known_source",
        False
    ):

        signals.append(
            "KNOWN_SOURCE"
        )

    if reputation_score >= 60:

        signals.append(
            "HIGH_RISK_HISTORY"
        )

    # ========================================================
    # LEARNING
    # ========================================================

    if (
        learning.get(
            "model_status"
        )
        ==
        "READY"
    ):

        signals.append(
            "LEARNING_MODEL_AVAILABLE"
        )

    if ml_score >= 70:

        signals.append(
            "LEARNING_MODEL_HIGH_RISK"
        )

    if (
        "MODEL_DISAGREEMENT"
        in fusion.get(
            "fusion_reasons",
            []
        )
    ):

        signals.append(
            "MODEL_DISAGREEMENT"
        )

    # ========================================================
    # GLOBAL RISK
    # ========================================================

    if global_score >= 80:

        signals.append(
            "CRITICAL_GLOBAL_RISK"
        )

    elif global_score >= 60:

        signals.append(
            "HIGH_GLOBAL_RISK"
        )

    elif global_score >= 30:

        signals.append(
            "ELEVATED_GLOBAL_RISK"
        )

    # ========================================================
    # POLICY
    # ========================================================

    if response.get(
        "containment_requested",
        False
    ):

        signals.append(
            "CONTAINMENT_REQUESTED"
        )

    # ========================================================
    # DECEPTION
    # ========================================================

    if deception.get(
        "decoy_active",
        False
    ):

        signals.append(
            "DECEPTION_ACTIVE"
        )

    if deception.get(
        "surface_rotated",
        False
    ):

        signals.append(
            "DECEPTION_SURFACE_ROTATED"
        )

    # ========================================================
    # SANDBOX
    # ========================================================

    if sandbox.get(
        "sandbox_active",
        False
    ):

        signals.append(
            "SANDBOX_ACTIVE"
        )

    # ========================================================
    # INTEGRITY
    # ========================================================

    if integrity:

        if not integrity.get(
            "clean",
            True
        ):

            signals.append(
                "CORE_INTEGRITY_FAILURE"
            )

    return unique(
        signals
    )


# ============================================================
# INTENT ESTIMATION
# ============================================================

def estimate_intent(
    signals,
    fusion
):

    global_score = safe_float(
        fusion.get(
            "global_score",
            0
        )
    )

    hostile_signals = {

        "STRONG_MALICIOUS_PAYLOAD_SIGNAL",
        "AGGRESSIVE_BEHAVIOR_PATTERN",
        "REPEATED_CRITICAL_ACTIVITY",
        "HIGH_RISK_HISTORY",
        "LEARNING_MODEL_HIGH_RISK"
    }

    hostile_count = sum(
        1
        for signal
        in signals
        if signal
        in hostile_signals
    )

    if (
        global_score >= 80
        and
        hostile_count >= 2
    ):

        return (
            "PROBABLE_HOSTILE_ACTIVITY",
            90
        )

    if (
        global_score >= 60
        or
        hostile_count >= 2
    ):

        return (
            "SUSPICIOUS_ACTIVITY",
            75
        )

    if global_score >= 30:

        return (
            "UNCERTAIN_ACTIVITY",
            55
        )

    return (
        "LOW_RISK_ACTIVITY",
        40
    )


# ============================================================
# POSTURE
# ============================================================

def determine_posture(
    fusion,
    response,
    integrity
):

    if (
        integrity
        and
        not integrity.get(
            "clean",
            True
        )
    ):

        return "RECOVERY"

    if response.get(
        "containment_requested",
        False
    ):

        return "CONTAIN"

    level = str(
        fusion.get(
            "global_level",
            "LOW"
        )
    ).upper()

    if level == "CRITICAL":

        return "CONTAIN"

    if level == "HIGH":

        return "HEIGHTEN_MONITORING"

    if level == "MEDIUM":

        return "MONITOR"

    return "OBSERVE"


# ============================================================
# EXPLANATION
# ============================================================

def build_explanation(
    source_ip,
    analysis,
    behavior,
    anomaly,
    reputation,
    learning,
    fusion,
    response,
    deception,
    signals
):

    global_score = safe_float(
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
    )

    reasons = []

    if analysis.get(
        "indicators"
    ):

        reasons.append(
            "known payload indicators were detected"
        )

    if safe_float(
        behavior.get(
            "behavior_score",
            0
        )
    ) >= 60:

        reasons.append(
            "the source displayed suspicious repeated behavior"
        )

    if safe_float(
        anomaly.get(
            "anomaly_score",
            0
        )
    ) >= 60:

        reasons.append(
            "the activity differed significantly from the observed baseline"
        )

    if safe_float(
        reputation.get(
            "reputation_score",
            0
        )
    ) >= 60:

        reasons.append(
            "the source already has a high-risk historical profile"
        )

    if safe_float(
        learning.get(
            "ml_score",
            0
        )
    ) >= 70:

        reasons.append(
            "the learned model classified the pattern near the dangerous profile"
        )

    if not reasons:

        reasons.append(
            "no strong correlated threat evidence was observed"
        )

    explanation = (
        f"Source {source_ip} was assessed as "
        f"{global_level} risk with a score of "
        f"{round(global_score, 2)}/100 because "
        +
        "; ".join(
            reasons
        )
        +
        "."
    )

    if deception.get(
        "decoy_active",
        False
    ):

        explanation += (
            " The interaction is currently being handled "
            "inside Sentinel's deception environment."
        )

    if deception.get(
        "surface_rotated",
        False
    ):

        explanation += (
            " The deception surface was rotated after "
            "reconnaissance activity was detected."
        )

    if response.get(
        "containment_requested",
        False
    ):

        explanation += (
            " Containment was requested by the policy engine."
        )

    return explanation


# ============================================================
# REASONING CORE
# ============================================================

def reason_about_incident(
    source_ip,
    analysis,
    behavior,
    anomaly,
    reputation,
    learning,
    fusion,
    context,
    response,
    deception,
    sandbox,
    integrity=None
):

    signals = extract_signals(
        analysis=analysis,
        behavior=behavior,
        anomaly=anomaly,
        reputation=reputation,
        learning=learning,
        fusion=fusion,
        context=context,
        response=response,
        deception=deception,
        sandbox=sandbox,
        integrity=integrity
    )

    intent, intent_confidence = (
        estimate_intent(
            signals,
            fusion
        )
    )

    posture = (
        determine_posture(
            fusion,
            response,
            integrity
        )
    )

    global_score = safe_float(
        fusion.get(
            "global_score",
            0
        )
    )

    fusion_confidence = safe_float(
        fusion.get(
            "confidence",
            50
        )
    )

    corroboration = sum(
        1
        for score
        in (
            safe_float(
                analysis.get(
                    "score",
                    0
                )
            ),
            safe_float(
                behavior.get(
                    "behavior_score",
                    0
                )
            ),
            safe_float(
                anomaly.get(
                    "anomaly_score",
                    0
                )
            ),
            safe_float(
                reputation.get(
                    "reputation_score",
                    0
                )
            ),
            safe_float(
                learning.get(
                    "ml_score",
                    0
                )
            )
        )
        if score >= 50
    )

    reasoning_confidence = (
        fusion_confidence
        +
        min(
            corroboration * 3,
            15
        )
    )

    if "MODEL_DISAGREEMENT" in signals:

        reasoning_confidence -= 10

    reasoning_confidence = round(
        clamp(
            reasoning_confidence,
            20,
            98
        ),
        2
    )

    explanation = build_explanation(
        source_ip=source_ip,
        analysis=analysis,
        behavior=behavior,
        anomaly=anomaly,
        reputation=reputation,
        learning=learning,
        fusion=fusion,
        response=response,
        deception=deception,
        signals=signals
    )

    return {

        "brain_version":
            BRAIN_VERSION,

        "timestamp":
            utc_now(),

        "source_ip":
            source_ip,

        "assessment": {

            "risk_level":
                fusion.get(
                    "global_level",
                    "LOW"
                ),

            "risk_score":
                round(
                    global_score,
                    2
                ),

            "intent":
                intent,

            "intent_confidence":
                intent_confidence,

            "reasoning_confidence":
                reasoning_confidence,

            "posture":
                posture
        },

        "signals":
            signals,

        "corroborating_engines":
            corroboration,

        "explanation":
            explanation,

        "decision": {

            "fusion_decision":
                fusion.get(
                    "decision"
                ),

            "context_recommendation":
                context.get(
                    "recommended_action"
                ),

            "policy_action":
                response.get(
                    "action"
                ),

            "containment_requested":
                response.get(
                    "containment_requested",
                    False
                )
        },

        "deception": {

            "active":
                deception.get(
                    "decoy_active",
                    False
                ),

            "profile":
                deception.get(
                    "decoy_profile"
                ),

            "generation":
                deception.get(
                    "surface_generation"
                ),

            "rotated":
                deception.get(
                    "surface_rotated",
                    False
                )
        },

        "sandbox": {

            "active":
                sandbox.get(
                    "sandbox_active",
                    False
                ),

            "network":
                sandbox.get(
                    "sandbox_network",
                    "NONE"
                ),

            "privileged":
                sandbox.get(
                    "sandbox_privileged",
                    False
                )
        },

        "safety": {

            "payload_execution":
                False,

            "shell_execution":
                False,

            "brain_host_modification":
                False
        }
    }


# ============================================================
# SIMPLE LOCAL QUESTION INTERFACE
# ============================================================

def answer_incident_question(
    question,
    reasoning
):

    text = str(
        question
    ).strip().lower()

    assessment = reasoning.get(
        "assessment",
        {}
    )

    if (
        "why"
        in text
        or
        "pourquoi"
        in text
    ):

        return reasoning.get(
            "explanation"
        )

    if (
        "risk"
        in text
        or
        "danger"
        in text
        or
        "risque"
        in text
    ):

        return (
            f"Current risk is "
            f"{assessment.get('risk_level')} "
            f"at {assessment.get('risk_score')}/100. "
            f"My reasoning confidence is "
            f"{assessment.get('reasoning_confidence')}%."
        )

    if (
        "intent"
        in text
        or
        "intention"
        in text
    ):

        return (
            f"I currently classify the activity as "
            f"{assessment.get('intent')} "
            f"with {assessment.get('intent_confidence')}% "
            f"confidence."
        )

    if (
        "what did you do"
        in text
        or
        "qu'est-ce que tu as fait"
        in text
        or
        "action"
        in text
    ):

        decision = reasoning.get(
            "decision",
            {}
        )

        return (
            f"My current defensive posture is "
            f"{assessment.get('posture')}. "
            f"The policy action is "
            f"{decision.get('policy_action')}."
        )

    if (
        "deception"
        in text
        or
        "decoy"
        in text
        or
        "leurre"
        in text
    ):

        deception = reasoning.get(
            "deception",
            {}
        )

        if deception.get(
            "active",
            False
        ):

            return (
                f"Deception is active using profile "
                f"{deception.get('profile')} at generation "
                f"{deception.get('generation')}."
            )

        return (
            "No deception environment is active "
            "for this incident."
        )

    return reasoning.get(
        "explanation"
    )


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    analysis = {
        "severity":
            "CRITICAL",

        "score":
            70,

        "indicators":
            [
                "powershell",
                "exploit"
            ]
    }

    behavior = {
        "behavior_level":
            "CRITICAL",

        "behavior_score":
            95,

        "behavior_type":
            "REPEATED_CRITICAL_ACTIVITY"
    }

    anomaly = {
        "anomaly_level":
            "MEDIUM",

        "anomaly_score":
            45,

        "anomaly_reasons":
            [
                "CONNECTION_BURST"
            ]
    }

    reputation = {
        "known_source":
            True,

        "reputation_score":
            70
    }

    learning = {
        "model_status":
            "READY",

        "ml_score":
            88,

        "ml_confidence":
            90
    }

    fusion = {
        "global_level":
            "CRITICAL",

        "global_score":
            94,

        "confidence":
            92,

        "decision":
            "ISOLATION_RECOMMENDED",

        "fusion_reasons":
            [
                "ML_DETERMINISTIC_AGREEMENT"
            ]
    }

    context = {
        "context_level":
            "CRITICAL",

        "recommended_action":
            "CONTAIN"
    }

    response = {
        "action":
            "CONTAIN_DECOY",

        "containment_requested":
            True
    }

    deception = {
        "decoy_active":
            True,

        "decoy_profile":
            "devops-runner",

        "surface_generation":
            2,

        "surface_rotated":
            True
    }

    sandbox = {
        "sandbox_active":
            True,

        "sandbox_network":
            "NONE",

        "sandbox_privileged":
            False
    }

    integrity = {
        "status":
            "CLEAN",

        "clean":
            True
    }

    reasoning = reason_about_incident(
        source_ip=
            "127.0.0.1",

        analysis=
            analysis,

        behavior=
            behavior,

        anomaly=
            anomaly,

        reputation=
            reputation,

        learning=
            learning,

        fusion=
            fusion,

        context=
            context,

        response=
            response,

        deception=
            deception,

        sandbox=
            sandbox,

        integrity=
            integrity
    )

    return {

        "reasoning":
            reasoning,

        "why":
            answer_incident_question(
                "Why is this source dangerous?",
                reasoning
            ),

        "action":
            answer_incident_question(
                "What did you do?",
                reasoning
            ),

        "deception":
            answer_incident_question(
                "What happened with the deception system?",
                reasoning
            )
    }