import time
import threading
from collections import defaultdict, deque


WINDOW_SECONDS = 60
MAX_HISTORY_PER_IP = 30

_lock = threading.Lock()

_history = defaultdict(
    lambda: deque(maxlen=MAX_HISTORY_PER_IP)
)


def analyze_behavior(ip, payload_analysis):
    now = time.time()

    current_event = {
        "time": now,
        "severity": payload_analysis["severity"],
        "score": payload_analysis["score"],
        "indicators": payload_analysis["indicators"]
    }

    with _lock:
        history = _history[ip]
        history.append(current_event)

        while history:
            age = now - history[0]["time"]

            if age <= WINDOW_SECONDS:
                break

            history.popleft()

        recent_events = list(history)

    connection_count = len(recent_events)

    critical_count = sum(
        1
        for event in recent_events
        if event["severity"] == "CRITICAL"
    )

    indicator_set = set()

    for event in recent_events:
        for indicator in event["indicators"]:
            indicator_set.add(indicator)

    score = payload_analysis["score"]

    if connection_count >= 3:
        score += 10

    if connection_count >= 5:
        score += 15

    if critical_count >= 2:
        score += 20

    if len(indicator_set) >= 3:
        score += 10

    score = min(score, 100)

    if score >= 80:
        level = "CRITICAL"

    elif score >= 60:
        level = "HIGH"

    elif score >= 30:
        level = "MEDIUM"

    else:
        level = "LOW"

    if critical_count >= 2:
        behavior_type = "REPEATED_CRITICAL_ACTIVITY"

    elif connection_count >= 3:
        behavior_type = "REPEATED_CONNECTIONS"

    else:
        behavior_type = "SINGLE_ACTIVITY"

    return {
        "behavior_score": score,
        "behavior_level": level,
        "behavior_type": behavior_type,
        "connections_60s": connection_count,
        "critical_60s": critical_count,
        "unique_indicators": sorted(indicator_set)
    }