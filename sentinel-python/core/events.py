import json
import os

from datetime import datetime, timezone


# ============================================================
# SENTINEL PHOENIX
# EVENT LOGGER V3
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

EVENT_FILE = os.path.join(
    DATA_DIR,
    "events.jsonl"
)


def record_event(
    ip,
    port,
    payload,
    analysis,
    behavior,
    anomaly,
    reputation,
    learning,
    fusion,
    context,
    response,
    deception,
    sandbox
):

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    event = {

        # ====================================================
        # GENERAL
        # ====================================================

        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "type":
            "HONEYPOT_EVENT",

        "source_ip":
            ip,

        "source_port":
            port,

        "payload":
            payload[:500],

        # ====================================================
        # PAYLOAD ENGINE
        # ====================================================

        "severity":
            analysis.get(
                "severity"
            ),

        "score":
            analysis.get(
                "score",
                0
            ),

        "indicators":
            analysis.get(
                "indicators",
                []
            ),

        # ====================================================
        # BEHAVIOR ENGINE
        # ====================================================

        "behavior_level":
            behavior.get(
                "behavior_level"
            ),

        "behavior_score":
            behavior.get(
                "behavior_score",
                0
            ),

        "behavior_type":
            behavior.get(
                "behavior_type"
            ),

        "connections_60s":
            behavior.get(
                "connections_60s",
                0
            ),

        "critical_60s":
            behavior.get(
                "critical_60s",
                0
            ),

        "unique_indicators":
            behavior.get(
                "unique_indicators",
                []
            ),

        # ====================================================
        # ANOMALY ENGINE
        # ====================================================

        "anomaly_level":
            anomaly.get(
                "anomaly_level"
            ),

        "anomaly_score":
            anomaly.get(
                "anomaly_score",
                0
            ),

        "anomaly_reasons":
            anomaly.get(
                "anomaly_reasons",
                []
            ),

        "payload_length":
            anomaly.get(
                "payload_length",
                0
            ),

        "entropy":
            anomaly.get(
                "entropy",
                0
            ),

        "length_zscore":
            anomaly.get(
                "length_zscore",
                0
            ),

        "connections_30s":
            anomaly.get(
                "connections_30s",
                0
            ),

        # ====================================================
        # REPUTATION ENGINE
        # ====================================================

        "known_source":
            reputation.get(
                "known_source",
                False
            ),

        "reputation_score":
            reputation.get(
                "reputation_score",
                0
            ),

        "reputation_level":
            reputation.get(
                "reputation_level"
            ),

        "reputation_reasons":
            reputation.get(
                "reputation_reasons",
                []
            ),

        "historical_events":
            reputation.get(
                "historical_events",
                0
            ),

        "historical_critical":
            reputation.get(
                "historical_critical",
                0
            ),

        "historical_containments":
            reputation.get(
                "historical_containments",
                0
            ),

        # ====================================================
        # LEARNING ENGINE
        # ====================================================

        "ml_score":
            learning.get(
                "ml_score",
                0
            ),

        "ml_level":
            learning.get(
                "ml_level"
            ),

        "ml_confidence":
            learning.get(
                "ml_confidence",
                0
            ),

        "ml_model_status":
            learning.get(
                "model_status"
            ),

        "ml_model_samples":
            learning.get(
                "model_samples",
                0
            ),

        "ml_normal_samples":
            learning.get(
                "normal_samples",
                0
            ),

        "ml_dangerous_samples":
            learning.get(
                "dangerous_samples",
                0
            ),

        "ml_model_version":
            learning.get(
                "model_version"
            ),

        "learning_reasons":
            learning.get(
                "learning_reasons",
                []
            ),

        # ====================================================
        # FUSION ENGINE V3
        # ====================================================

        "current_risk_score":
            fusion.get(
                "current_risk_score",
                0
            ),

        "historical_bonus":
            fusion.get(
                "historical_bonus",
                0
            ),

        "deterministic_score":
            fusion.get(
                "deterministic_score",
                0
            ),

        "global_score":
            fusion.get(
                "global_score",
                0
            ),

        "global_level":
            fusion.get(
                "global_level"
            ),

        "confidence":
            fusion.get(
                "confidence",
                0
            ),

        "fusion_decision":
            fusion.get(
                "decision"
            ),

        "fusion_version":
            fusion.get(
                "fusion_version"
            ),

        "fusion_mode":
            fusion.get(
                "fusion_mode"
            ),

        "fusion_ml_active":
            fusion.get(
                "ml_active",
                False
            ),

        "fusion_ml_weight":
            fusion.get(
                "ml_weight",
                0
            ),

        "fusion_reasons":
            fusion.get(
                "fusion_reasons",
                []
            ),

        # ====================================================
        # CONTEXT ENGINE
        # ====================================================

        "context_score":
            context.get(
                "context_score",
                0
            ),

        "context_level":
            context.get(
                "context_level"
            ),

        "context_recommended_action":
            context.get(
                "recommended_action"
            ),

        "context_reasons":
            context.get(
                "context_reasons",
                []
            ),

        "context_summary":
            context.get(
                "context_summary",
                []
            ),

        "review_required":
            context.get(
                "review_required",
                False
            ),

        # ====================================================
        # POLICY ENGINE
        # ====================================================

        "response_action":
            response.get(
                "action"
            ),

        "monitoring_level":
            response.get(
                "monitoring_level"
            ),

        "containment_requested":
            response.get(
                "containment_requested",
                False
            ),

        "response_reasons":
            response.get(
                "response_reasons",
                []
            ),

        # ====================================================
        # DECEPTION
        # ====================================================

        "decoy_active":
            deception.get(
                "decoy_active",
                False
            ),

        "decoy_session_id":
            deception.get(
                "decoy_session_id"
            ),

        "decoy_mode":
            deception.get(
                "decoy_mode"
            ),

        "decoy_reused":
            deception.get(
                "decoy_reused",
                False
            ),

        # ====================================================
        # SANDBOX
        # ====================================================

        "sandbox_active":
            sandbox.get(
                "sandbox_active",
                False
            ),

        "sandbox_name":
            sandbox.get(
                "sandbox_name"
            ),

        "sandbox_id":
            sandbox.get(
                "sandbox_id"
            ),

        "sandbox_reused":
            sandbox.get(
                "sandbox_reused",
                False
            ),

        "sandbox_network":
            sandbox.get(
                "sandbox_network",
                "NONE"
            ),

        "sandbox_read_only":
            sandbox.get(
                "sandbox_read_only",
                True
            ),

        "sandbox_privileged":
            sandbox.get(
                "sandbox_privileged",
                False
            ),

        "sandbox_error":
            sandbox.get(
                "sandbox_error"
            ),

        # ====================================================
        # SAFETY
        # ====================================================

        "payload_execution":
            False,

        "status":
            "ANALYZED"
    }

    with open(
        EVENT_FILE,
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

    return event