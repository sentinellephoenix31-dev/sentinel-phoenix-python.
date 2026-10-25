from core.memory import get_source_memory


def evaluate_reputation(source_ip):
    """
    Calcule la réputation historique d'une source
    à partir de la mémoire persistante de Sentinel.

    Aucun blocage n'est effectué ici.
    Le module produit uniquement un score historique.
    """

    memory = get_source_memory(
        source_ip
    )

    # ==========================================
    # SOURCE JAMAIS VUE
    # ==========================================

    if memory is None:

        return {
            "known_source": False,
            "reputation_score": 0,
            "reputation_level": "UNKNOWN",
            "historical_risk": "NONE",
            "reputation_reasons": [],
            "historical_events": 0,
            "historical_critical": 0,
            "historical_containments": 0
        }

    score = 0
    reasons = []

    total_events = int(
        memory.get(
            "total_events",
            0
        )
    )

    critical_events = int(
        memory.get(
            "critical_events",
            0
        )
    )

    containment_events = int(
        memory.get(
            "containment_events",
            0
        )
    )

    max_global = float(
        memory.get(
            "max_global_score",
            0
        )
    )

    indicators = memory.get(
        "indicators",
        []
    )

    anomaly_reasons = memory.get(
        "anomaly_reasons",
        []
    )

    sandbox_seen = bool(
        memory.get(
            "sandbox_seen",
            False
        )
    )

    # ==========================================
    # HISTORIQUE DE RISQUE
    # ==========================================

    if max_global >= 80:

        score += 30

        reasons.append(
            "PAST_CRITICAL_RISK"
        )

    elif max_global >= 60:

        score += 20

        reasons.append(
            "PAST_HIGH_RISK"
        )

    elif max_global >= 30:

        score += 10

        reasons.append(
            "PAST_MEDIUM_RISK"
        )

    # ==========================================
    # EVENEMENTS CRITIQUES HISTORIQUES
    # ==========================================

    if critical_events > 0:

        critical_bonus = min(
            critical_events * 8,
            30
        )

        score += critical_bonus

        reasons.append(
            "HISTORICAL_CRITICAL_EVENTS"
        )

    # ==========================================
    # CONFINEMENTS HISTORIQUES
    # ==========================================

    if containment_events > 0:

        containment_bonus = min(
            containment_events * 10,
            30
        )

        score += containment_bonus

        reasons.append(
            "PAST_CONTAINMENT"
        )

    # ==========================================
    # SANDBOX DEJA UTILISEE
    # ==========================================

    if sandbox_seen:

        score += 10

        reasons.append(
            "PREVIOUS_SANDBOX_ACTIVITY"
        )

    # ==========================================
    # ACTIVITE REPETEE
    # ==========================================

    if total_events >= 25:

        score += 15

        reasons.append(
            "HIGH_HISTORICAL_ACTIVITY"
        )

    elif total_events >= 10:

        score += 10

        reasons.append(
            "REPEATED_HISTORICAL_ACTIVITY"
        )

    elif total_events >= 5:

        score += 5

        reasons.append(
            "KNOWN_REPEAT_SOURCE"
        )

    # ==========================================
    # INDICATEURS HISTORIQUES
    # ==========================================

    if indicators:

        indicator_bonus = min(
            len(indicators) * 2,
            10
        )

        score += indicator_bonus

        reasons.append(
            "KNOWN_THREAT_INDICATORS"
        )

    # ==========================================
    # ANOMALIES HISTORIQUES
    # ==========================================

    if anomaly_reasons:

        anomaly_bonus = min(
            len(anomaly_reasons) * 2,
            10
        )

        score += anomaly_bonus

        reasons.append(
            "KNOWN_ANOMALY_HISTORY"
        )

    score = min(
        score,
        100
    )

    # ==========================================
    # CLASSIFICATION
    # ==========================================

    if score >= 80:

        level = "HOSTILE_HISTORY"
        historical_risk = "CRITICAL"

    elif score >= 60:

        level = "HIGH_RISK_HISTORY"
        historical_risk = "HIGH"

    elif score >= 30:

        level = "SUSPICIOUS_HISTORY"
        historical_risk = "MEDIUM"

    elif score > 0:

        level = "KNOWN_HISTORY"
        historical_risk = "LOW"

    else:

        level = "KNOWN_CLEAN"
        historical_risk = "LOW"

    return {
        "known_source": True,

        "reputation_score":
            score,

        "reputation_level":
            level,

        "historical_risk":
            historical_risk,

        "reputation_reasons":
            reasons,

        "historical_events":
            total_events,

        "historical_critical":
            critical_events,

        "historical_containments":
            containment_events,

        "max_historical_risk":
            max_global,

        "historical_indicators":
            indicators,

        "historical_anomalies":
            anomaly_reasons
    }