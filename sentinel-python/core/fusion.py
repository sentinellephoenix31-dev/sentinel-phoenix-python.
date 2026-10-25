# ============================================================
# SENTINEL PHOENIX
# RISK FUSION ENGINE V3
# ============================================================


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


def fuse_risk(
    analysis,
    behavior,
    anomaly,
    reputation,
    learning
):
    """
    Risk Fusion Engine V3.

    Combine :
    - Payload Engine
    - Behavior Engine
    - Anomaly Engine
    - Reputation Engine
    - Learning Engine

    Le Learning Engine ne remplace pas
    les moteurs déterministes.

    Lorsqu'il est READY, Sentinel utilise
    une fusion hybride :
        80 % risque déterministe
        20 % score appris

    Puis les corrélations de sécurité
    peuvent augmenter le score final.
    """

    # ========================================================
    # INPUT SCORES
    # ========================================================

    payload_score = float(
        analysis.get(
            "score",
            0
        )
    )

    behavior_score = float(
        behavior.get(
            "behavior_score",
            0
        )
    )

    anomaly_score = float(
        anomaly.get(
            "anomaly_score",
            0
        )
    )

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

    model_status = str(
        learning.get(
            "model_status",
            "COLD_START"
        )
    ).upper()

    reasons = []

    # ========================================================
    # DETERMINISTIC CURRENT RISK
    # ========================================================

    current_score = (

        payload_score * 0.40

        +

        behavior_score * 0.35

        +

        anomaly_score * 0.25

    )

    current_score = round(
        current_score,
        2
    )

    # ========================================================
    # HISTORICAL REPUTATION
    #
    # Max theoretical bonus = 15
    # ========================================================

    historical_bonus = min(
        reputation_score * 0.15,
        15
    )

    historical_bonus = round(
        historical_bonus,
        2
    )

    deterministic_score = (
        current_score
        +
        historical_bonus
    )

    deterministic_score = clamp(
        deterministic_score
    )

    # ========================================================
    # LEARNING FUSION
    # ========================================================

    ml_active = False

    ml_weight = 0.0

    deterministic_weight = 1.0

    if (
        model_status == "READY"
        and
        ml_confidence >= 60
    ):

        ml_active = True

        ml_weight = 0.20

        deterministic_weight = 0.80

        base_fused_score = (

            deterministic_score
            *
            deterministic_weight

            +

            ml_score
            *
            ml_weight

        )

        reasons.append(
            "LEARNING_MODEL_ACTIVE"
        )

    else:

        base_fused_score = (
            deterministic_score
        )

        reasons.append(
            "DETERMINISTIC_FALLBACK"
        )

    # ========================================================
    # LEARNING AGREEMENT
    # ========================================================

    deterministic_dangerous = (
        deterministic_score >= 60
    )

    ml_dangerous = (
        ml_score >= 60
    )

    if (
        ml_active
        and
        deterministic_dangerous
        and
        ml_dangerous
    ):

        base_fused_score += 5

        reasons.append(
            "ML_DETERMINISTIC_AGREEMENT"
        )

    # ========================================================
    # LEARNING DISAGREEMENT
    #
    # On ne baisse pas brutalement le risque.
    # On signale simplement le désaccord.
    # ========================================================

    if (
        ml_active
        and
        abs(
            ml_score
            -
            deterministic_score
        ) >= 35
    ):

        reasons.append(
            "MODEL_DISAGREEMENT"
        )

    # ========================================================
    # REPUTATION INFORMATION
    # ========================================================

    if reputation.get(
        "known_source",
        False
    ):

        reasons.append(
            "KNOWN_SOURCE"
        )

    if reputation_score >= 80:

        reasons.append(
            "HOSTILE_HISTORY"
        )

    elif reputation_score >= 60:

        reasons.append(
            "HIGH_RISK_HISTORY"
        )

    elif reputation_score >= 30:

        reasons.append(
            "SUSPICIOUS_HISTORY"
        )

    elif reputation_score > 0:

        reasons.append(
            "KNOWN_RISK_HISTORY"
        )

    # ========================================================
    # CRITICAL ENGINE CORRELATION
    # ========================================================

    critical_engines = 0

    payload_level = str(
        analysis.get(
            "severity",
            ""
        )
    ).upper()

    behavior_level = str(
        behavior.get(
            "behavior_level",
            ""
        )
    ).upper()

    anomaly_level = str(
        anomaly.get(
            "anomaly_level",
            ""
        )
    ).upper()

    if payload_level == "CRITICAL":

        critical_engines += 1

        reasons.append(
            "CRITICAL_PAYLOAD"
        )

    if behavior_level == "CRITICAL":

        critical_engines += 1

        reasons.append(
            "CRITICAL_BEHAVIOR"
        )

    if anomaly_level == "CRITICAL":

        critical_engines += 1

        reasons.append(
            "CRITICAL_ANOMALY"
        )

    # ========================================================
    # MULTI-ENGINE CONSENSUS
    # ========================================================

    if critical_engines >= 2:

        base_fused_score += 15

        reasons.append(
            "MULTI_ENGINE_CRITICAL"
        )

    if critical_engines == 3:

        base_fused_score += 10

        reasons.append(
            "FULL_ENGINE_CONSENSUS"
        )

    # ========================================================
    # BEHAVIOR CORRELATION
    # ========================================================

    if (
        behavior.get(
            "behavior_type"
        )
        ==
        "REPEATED_CRITICAL_ACTIVITY"
    ):

        base_fused_score += 10

        reasons.append(
            "REPEATED_CRITICAL_ACTIVITY"
        )

    # ========================================================
    # ANOMALY CORRELATION
    # ========================================================

    anomaly_reasons = anomaly.get(
        "anomaly_reasons",
        []
    )

    if len(
        anomaly_reasons
    ) >= 2:

        base_fused_score += 5

        reasons.append(
            "MULTIPLE_ANOMALIES"
        )

    # ========================================================
    # HISTORY + CURRENT DANGER
    # ========================================================

    current_dangerous_engine = (

        payload_score >= 60

        or

        behavior_score >= 60

        or

        anomaly_score >= 60

    )

    if (
        reputation_score >= 60
        and
        current_dangerous_engine
    ):

        base_fused_score += 5

        reasons.append(
            "HISTORY_CURRENT_RISK_CORRELATION"
        )

    # ========================================================
    # STRONG ML SIGNAL
    #
    # Seulement si le modèle est READY,
    # suffisamment confiant et qu'un moteur
    # actuel confirme également un danger.
    # ========================================================

    if (
        ml_active
        and
        ml_score >= 80
        and
        ml_confidence >= 75
        and
        current_dangerous_engine
    ):

        base_fused_score += 5

        reasons.append(
            "STRONG_LEARNED_RISK"
        )

    # ========================================================
    # FINAL SCORE
    # ========================================================

    global_score = round(
        clamp(
            base_fused_score
        ),
        2
    )

    # ========================================================
    # GLOBAL LEVEL
    # ========================================================

    if global_score >= 80:

        global_level = "CRITICAL"

    elif global_score >= 60:

        global_level = "HIGH"

    elif global_score >= 30:

        global_level = "MEDIUM"

    else:

        global_level = "LOW"

    # ========================================================
    # FUSION DECISION
    # ========================================================

    if global_level == "CRITICAL":

        decision = (
            "ISOLATION_RECOMMENDED"
        )

    elif global_level == "HIGH":

        decision = (
            "ENHANCED_MONITORING"
        )

    elif global_level == "MEDIUM":

        decision = (
            "MONITOR"
        )

    else:

        decision = (
            "OBSERVE"
        )

    # ========================================================
    # CONFIDENCE
    # ========================================================

    active_current_engines = sum(

        1

        for score
        in (
            payload_score,
            behavior_score,
            anomaly_score
        )

        if score >= 30

    )

    if active_current_engines == 3:

        confidence = 92

    elif active_current_engines == 2:

        confidence = 82

    elif active_current_engines == 1:

        confidence = 68

    else:

        confidence = 52

    # Reputation support

    if (
        reputation.get(
            "known_source",
            False
        )
        and
        reputation_score >= 30
    ):

        confidence += 4

    # ML support

    if ml_active:

        confidence += min(
            int(
                ml_confidence
                *
                0.08
            ),
            7
        )

    # Agreement support

    if (
        "ML_DETERMINISTIC_AGREEMENT"
        in reasons
    ):

        confidence += 4

    # Disagreement decreases confidence

    if (
        "MODEL_DISAGREEMENT"
        in reasons
    ):

        confidence -= 8

    confidence = int(
        clamp(
            confidence,
            0,
            99
        )
    )

    # ========================================================
    # RESULT
    # ========================================================

    return {

        "global_score":
            global_score,

        "global_level":
            global_level,

        "decision":
            decision,

        "confidence":
            confidence,

        "fusion_version":
            "3.0",

        "fusion_mode":

            (
                "HYBRID_ML"
                if ml_active
                else
                "DETERMINISTIC"
            ),

        "fusion_reasons":
            reasons,

        "current_risk_score":
            current_score,

        "historical_bonus":
            historical_bonus,

        "deterministic_score":
            round(
                deterministic_score,
                2
            ),

        "ml_active":
            ml_active,

        "ml_weight":
            ml_weight,

        "deterministic_weight":
            deterministic_weight,

        "critical_engines":
            critical_engines,

        "engine_scores": {

            "payload":
                payload_score,

            "behavior":
                behavior_score,

            "anomaly":
                anomaly_score,

            "reputation":
                reputation_score,

            "learning":
                ml_score
        }
    }