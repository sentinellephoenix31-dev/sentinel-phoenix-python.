def build_context(
    analysis,
    behavior,
    anomaly,
    reputation,
    fusion
):
    """
    SENTINEL PHOENIX
    Context / Decision Engine V1

    Transforme les différents signaux techniques
    en une représentation globale de la situation.

    Ce module ne lance aucune commande système.
    """

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

    global_score = float(
        fusion.get(
            "global_score",
            0
        )
    )

    confidence = int(
        fusion.get(
            "confidence",
            0
        )
    )

    context_score = global_score

    reasons = []

    # ============================================================
    # SOURCE CONNUE
    # ============================================================

    if reputation.get(
        "known_source",
        False
    ):

        reasons.append(
            "SOURCE_ALREADY_KNOWN"
        )

        if reputation_score >= 30:

            context_score += min(
                reputation_score * 0.10,
                10
            )

            reasons.append(
                "HISTORICAL_RISK_PRESENT"
            )

    # ============================================================
    # COMPORTEMENT
    # ============================================================

    behavior_type = str(
        behavior.get(
            "behavior_type",
            ""
        )
    )

    if (
        behavior_type
        ==
        "REPEATED_CRITICAL_ACTIVITY"
    ):

        context_score += 10

        reasons.append(
            "REPEATED_CRITICAL_PATTERN"
        )

    # ============================================================
    # ANOMALIES
    # ============================================================

    anomaly_reasons = anomaly.get(
        "anomaly_reasons",
        []
    )

    if len(
        anomaly_reasons
    ) >= 2:

        context_score += 5

        reasons.append(
            "MULTIPLE_ANOMALIES"
        )

    # ============================================================
    # CONVERGENCE
    # ============================================================

    dangerous_engines = sum(
        1
        for score in (
            payload_score,
            behavior_score,
            anomaly_score
        )
        if score >= 60
    )

    if dangerous_engines >= 2:

        context_score += 8

        reasons.append(
            "MULTIPLE_DANGEROUS_ENGINES"
        )

    # ============================================================
    # BORNE
    # ============================================================

    context_score = min(
        round(
            context_score,
            2
        ),
        100
    )

    # ============================================================
    # NIVEAU CONTEXTUEL
    # ============================================================

    if context_score >= 80:

        context_level = "CRITICAL"

    elif context_score >= 60:

        context_level = "ELEVATED"

    elif context_score >= 30:

        context_level = "WATCH"

    else:

        context_level = "NORMAL"

    # ============================================================
    # MODE RECOMMANDE
    # ============================================================

    if (
        context_level == "CRITICAL"
        and
        confidence >= 80
    ):

        recommended_action = (
            "CONTAIN_DECOY"
        )

    elif context_level in (
        "CRITICAL",
        "ELEVATED"
    ):

        recommended_action = (
            "HEIGHTEN_MONITORING"
        )

    elif context_level == "WATCH":

        recommended_action = (
            "MONITOR"
        )

    else:

        recommended_action = (
            "OBSERVE"
        )

    # ============================================================
    # BESOIN DE REVUE
    # ============================================================

    review_required = (
        context_level
        in (
            "ELEVATED",
            "CRITICAL"
        )
    )

    # ============================================================
    # RESUME
    # ============================================================

    summary = []

    if payload_score >= 60:

        summary.append(
            "dangerous_payload"
        )

    if behavior_score >= 60:

        summary.append(
            "dangerous_behavior"
        )

    if anomaly_score >= 60:

        summary.append(
            "strong_anomaly"
        )

    if reputation_score >= 30:

        summary.append(
            "historical_risk"
        )

    if not summary:

        summary.append(
            "no_major_signal"
        )

    return {

        "context_score":
            context_score,

        "context_level":
            context_level,

        "recommended_action":
            recommended_action,

        "review_required":
            review_required,

        "context_reasons":
            reasons,

        "context_summary":
            summary,

        "dangerous_engines":
            dangerous_engines,

        "confidence":
            confidence
    }