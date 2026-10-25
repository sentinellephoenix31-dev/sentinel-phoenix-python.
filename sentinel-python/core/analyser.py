def analyze_payload(payload):
    """
    Première analyse heuristique de Sentinel Phoenix.
    Pour l'instant, ce n'est pas encore notre modèle IA.
    """

    text = payload.lower()

    score = 0
    indicators = []

    suspicious_words = {
        "powershell": 30,
        "cmd": 20,
        "bash": 20,
        "exec": 25,
        "exploit": 40,
        "nc ": 30,
        "wget": 15,
        "curl": 15,
    }

    for word, value in suspicious_words.items():
        if word in text:
            score += value
            indicators.append(word.strip())

    score = min(score, 100)

    if score >= 70:
        severity = "CRITICAL"

    elif score >= 40:
        severity = "HIGH"

    elif score >= 20:
        severity = "MEDIUM"

    else:
        severity = "LOW"

    return {
        "score": score,
        "severity": severity,
        "indicators": indicators
    }