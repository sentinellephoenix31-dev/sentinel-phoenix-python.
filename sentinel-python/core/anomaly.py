import math
import time
import threading
from collections import defaultdict, deque


WINDOW_SECONDS = 30
MAX_HISTORY = 50

_lock = threading.Lock()

_ip_history = defaultdict(
    lambda: deque(maxlen=MAX_HISTORY)
)

_global_lengths = deque(maxlen=100)


def calculate_entropy(text):
    if not text:
        return 0.0

    counts = {}

    for char in text:
        counts[char] = counts.get(char, 0) + 1

    length = len(text)
    entropy = 0.0

    for count in counts.values():
        probability = count / length
        entropy -= probability * math.log2(probability)

    return round(entropy, 2)


def calculate_non_printable_ratio(text):
    if not text:
        return 0.0

    non_printable = 0

    for char in text:
        if not char.isprintable():
            non_printable += 1

    return round(
        non_printable / len(text),
        3
    )


def calculate_length_zscore(length):
    if len(_global_lengths) < 10:
        return 0.0

    values = list(_global_lengths)

    mean = sum(values) / len(values)

    variance = sum(
        (value - mean) ** 2
        for value in values
    ) / len(values)

    deviation = math.sqrt(variance)

    if deviation == 0:
        return 0.0

    return round(
        abs(length - mean) / deviation,
        2
    )


def analyze_anomaly(ip, payload):
    now = time.time()

    payload_length = len(payload)

    entropy = calculate_entropy(payload)

    non_printable_ratio = (
        calculate_non_printable_ratio(payload)
    )

    reasons = []

    anomaly_score = 0

    with _lock:
        history = _ip_history[ip]

        history.append(now)

        while history:
            age = now - history[0]

            if age <= WINDOW_SECONDS:
                break

            history.popleft()

        connections_30s = len(history)

        length_zscore = (
            calculate_length_zscore(
                payload_length
            )
        )

        _global_lengths.append(
            payload_length
        )

    # ---------------------------------
    # Fréquence inhabituelle
    # ---------------------------------

    if connections_30s >= 5:
        anomaly_score += 20

        reasons.append(
            "HIGH_CONNECTION_FREQUENCY"
        )

    if connections_30s >= 10:
        anomaly_score += 20

        reasons.append(
            "CONNECTION_BURST"
        )

    # ---------------------------------
    # Taille inhabituelle
    # ---------------------------------

    if payload_length > 512:
        anomaly_score += 15

        reasons.append(
            "LARGE_PAYLOAD"
        )

    if payload_length > 1500:
        anomaly_score += 20

        reasons.append(
            "VERY_LARGE_PAYLOAD"
        )

    # ---------------------------------
    # Entropie élevée
    # ---------------------------------

    if entropy >= 4.5:
        anomaly_score += 20

        reasons.append(
            "HIGH_ENTROPY"
        )

    # ---------------------------------
    # Contenu binaire / étrange
    # ---------------------------------

    if non_printable_ratio >= 0.15:
        anomaly_score += 25

        reasons.append(
            "NON_PRINTABLE_CONTENT"
        )

    # ---------------------------------
    # Déviation statistique
    # ---------------------------------

    if length_zscore >= 3.0:
        anomaly_score += 20

        reasons.append(
            "STATISTICAL_LENGTH_ANOMALY"
        )

    anomaly_score = min(
        anomaly_score,
        100
    )

    if anomaly_score >= 80:
        anomaly_level = "CRITICAL"

    elif anomaly_score >= 55:
        anomaly_level = "HIGH"

    elif anomaly_score >= 25:
        anomaly_level = "MEDIUM"

    else:
        anomaly_level = "LOW"

    return {
        "anomaly_score": anomaly_score,
        "anomaly_level": anomaly_level,
        "anomaly_reasons": reasons,

        "payload_length": payload_length,

        "entropy": entropy,

        "non_printable_ratio":
            non_printable_ratio,

        "length_zscore":
            length_zscore,

        "connections_30s":
            connections_30s
    }