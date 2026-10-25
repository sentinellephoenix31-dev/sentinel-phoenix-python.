import json
import os
import re
import time
from datetime import datetime, timezone

from core.geo_intelligence import (
    lookup_ip,
    to_globe_payload
)


# ============================================================
# SENTINEL PHOENIX
# INCIDENT REPLAY BRIDGE V1
#
# events.jsonl
#      ↓
# normalize incident
#      ↓
# source IP
#      ↓
# Geo Intelligence
#      ↓
# Visual Incident Replay payload
#
# No shell execution.
# No payload execution.
# External geolocation is information only.
# ============================================================


BRIDGE_VERSION = "1.0"


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)


DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)


EVENTS_FILE = os.path.join(
    DATA_DIR,
    "events.jsonl"
)


OUTPUT_FILE = os.path.join(
    DATA_DIR,
    "incident_replay_payload.json"
)


# ============================================================
# GENERIC HELPERS
# ============================================================

def utc_now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


def nested_get(
    data,
    path
):

    current = data

    for part in path.split("."):

        if not isinstance(
            current,
            dict
        ):

            return None

        current = current.get(
            part
        )

    return current


def first_value(
    data,
    paths,
    default=None
):

    for path in paths:

        value = nested_get(
            data,
            path
        )

        if value not in (
            None,
            "",
            [],
            {}
        ):

            return value

    return default


# ============================================================
# IP EXTRACTION
# ============================================================

IP_PATTERN = re.compile(
    r"(?<![\d.])"
    r"(?:\d{1,3}\.){3}\d{1,3}"
    r"(?![\d.])"
)


def extract_ip_from_text(
    value
):

    if value is None:

        return None


    text = str(
        value
    )


    matches = IP_PATTERN.findall(
        text
    )


    if not matches:

        return None


    # geo_intelligence will perform final validation.

    return matches[
        0
    ]


def extract_source_ip(
    event
):

    direct = first_value(
        event,
        [
            "source_ip",
            "src_ip",
            "attacker_ip",
            "remote_ip",
            "client_ip",
            "ip",
            "source.ip",
            "network.source_ip",
            "connection.source_ip",
            "remote.ip",
            "client.ip"
        ]
    )


    candidate = extract_ip_from_text(
        direct
    )


    if candidate:

        return candidate


    # Search a few useful text fields.

    for field in (
        "message",
        "description",
        "details",
        "summary",
        "raw"
    ):

        candidate = extract_ip_from_text(
            event.get(
                field
            )
        )

        if candidate:

            return candidate


    return None


# ============================================================
# TIMESTAMP
# ============================================================

def normalize_timestamp(
    value
):

    if value is None:

        return utc_now_iso()


    # Unix timestamp.

    if isinstance(
        value,
        (
            int,
            float
        )
    ):

        try:

            return datetime.fromtimestamp(
                float(
                    value
                ),
                tz=timezone.utc
            ).isoformat()

        except (
            ValueError,
            OSError,
            OverflowError
        ):

            return utc_now_iso()


    text = str(
        value
    ).strip()


    if not text:

        return utc_now_iso()


    # Numeric timestamp stored as string.

    try:

        numeric = float(
            text
        )

        if numeric > 100000000:

            return datetime.fromtimestamp(
                numeric,
                tz=timezone.utc
            ).isoformat()

    except ValueError:

        pass


    # ISO-style value.

    try:

        parsed = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00"
            )
        )


        if parsed.tzinfo is None:

            parsed = parsed.replace(
                tzinfo=timezone.utc
            )


        return parsed.isoformat()


    except ValueError:

        return text


# ============================================================
# RISK NORMALIZATION
# ============================================================

def normalize_risk(
    value
):

    if value is None:

        return 0.0


    if isinstance(
        value,
        str
    ):

        severity = value.strip().upper()


        severity_map = {
            "INFO": 10,
            "LOW": 25,
            "MEDIUM": 50,
            "MODERATE": 50,
            "HIGH": 75,
            "CRITICAL": 95,
            "SEVERE": 95
        }


        if severity in severity_map:

            return float(
                severity_map[
                    severity
                ]
            )


        try:

            value = float(
                value
            )

        except ValueError:

            return 0.0


    try:

        score = float(
            value
        )

    except (
        TypeError,
        ValueError
    ):

        return 0.0


    # Support scores between 0 and 1.

    if 0.0 <= score <= 1.0:

        score *= 100.0


    return max(
        0.0,
        min(
            100.0,
            score
        )
    )


# ============================================================
# THREAT TYPE
# ============================================================

def normalize_threat_type(
    event
):

    value = first_value(
        event,
        [
            "threat_type",
            "attack_type",
            "category",
            "event_type",
            "event",
            "type",
            "behavior",
            "classification",
            "analysis.threat_type"
        ],
        default="SECURITY EVENT"
    )


    return str(
        value
    ).strip().upper()


# ============================================================
# ACTION
# ============================================================

def normalize_action(
    event
):

    value = first_value(
        event,
        [
            "action",
            "response",
            "decision",
            "policy_action",
            "mitigation",
            "containment",
            "analysis.action"
        ],
        default="OBSERVED"
    )


    if isinstance(
        value,
        dict
    ):

        value = first_value(
            value,
            [
                "action",
                "status",
                "decision",
                "result"
            ],
            default="OBSERVED"
        )


    return str(
        value
    ).strip().upper()


# ============================================================
# DESCRIPTION
# ============================================================

def normalize_description(
    event
):

    value = first_value(
        event,
        [
            "summary",
            "description",
            "message",
            "reason",
            "details"
        ]
    )


    if value is None:

        return (
            "Security event reconstructed "
            "from Sentinel telemetry."
        )


    if isinstance(
        value,
        (
            dict,
            list
        )
    ):

        try:

            value = json.dumps(
                value,
                ensure_ascii=False
            )

        except TypeError:

            value = str(
                value
            )


    text = str(
        value
    ).strip()


    return text[
        :500
    ]


# ============================================================
# READ EVENTS
# ============================================================

def read_events(
    limit=500
):

    if not os.path.isfile(
        EVENTS_FILE
    ):

        return []


    events = []


    try:

        with open(
            EVENTS_FILE,
            "r",
            encoding="utf-8"
        ) as handle:

            for line in handle:

                line = line.strip()


                if not line:

                    continue


                try:

                    event = json.loads(
                        line
                    )

                except json.JSONDecodeError:

                    continue


                if isinstance(
                    event,
                    dict
                ):

                    events.append(
                        event
                    )


    except OSError:

        return []


    if limit is not None:

        events = events[
            -int(
                limit
            ):
        ]


    return events


# ============================================================
# EVENT → NORMALIZED INCIDENT
# ============================================================

def normalize_event(
    event
):

    source_ip = extract_source_ip(
        event
    )


    timestamp = first_value(
        event,
        [
            "timestamp_iso",
            "timestamp",
            "time",
            "datetime",
            "created_at",
            "date"
        ]
    )


    risk_value = first_value(
        event,
        [
            "risk_score",
            "risk",
            "score",
            "severity",
            "risk.score",
            "analysis.risk_score",
            "fusion.risk_score"
        ]
    )


    incident_id = first_value(
        event,
        [
            "incident_id",
            "event_id",
            "id",
            "uuid"
        ]
    )


    return {
        "incident_id":
            incident_id,

        "source_ip":
            source_ip,

        "timestamp":
            normalize_timestamp(
                timestamp
            ),

        "threat_type":
            normalize_threat_type(
                event
            ),

        "risk_score":
            normalize_risk(
                risk_value
            ),

        "action":
            normalize_action(
                event
            ),

        "description":
            normalize_description(
                event
            )
    }


# ============================================================
# BUILD REPLAY PAYLOAD
# ============================================================

def build_incident_payload(
    event
):

    normalized = normalize_event(
        event
    )


    source_ip = normalized[
        "source_ip"
    ]


    # ========================================================
    # NO SOURCE IP
    # ========================================================

    if not source_ip:

        geo = {
            "available": False,
            "classification": "NO_SOURCE_IP",
            "reason": "SOURCE_IP_NOT_FOUND"
        }


    else:

        geo_result = lookup_ip(
            source_ip
        )


        geo = to_globe_payload(
            geo_result
        )


    payload = {

        "version":
            BRIDGE_VERSION,

        "generated_at":
            utc_now_iso(),

        "incident_id":
            normalized.get(
                "incident_id"
            ),

        "source_ip":
            source_ip
            or
            "UNKNOWN",

        "timestamp":
            normalized[
                "timestamp"
            ],

        "threat_type":
            normalized[
                "threat_type"
            ],

        "risk_score":
            normalized[
                "risk_score"
            ],

        "action":
            normalized[
                "action"
            ],

        "description":
            normalized[
                "description"
            ],

        "geo":
            geo,

        "display": {

            "country":
                (
                    geo.get(
                        "country"
                    )
                    if geo.get(
                        "available"
                    )
                    else
                    geo.get(
                        "classification",
                        "UNKNOWN"
                    )
                ),

            "region":
                (
                    geo.get(
                        "region"
                    )
                    if geo.get(
                        "available"
                    )
                    else
                    "NO PUBLIC GEOLOCATION"
                ),

            "city":
                (
                    geo.get(
                        "city"
                    )
                    if geo.get(
                        "available"
                    )
                    else
                    None
                ),

            "asn":
                (
                    geo.get(
                        "asn"
                    )
                    if geo.get(
                        "available"
                    )
                    else
                    None
                ),

            "provider":
                (
                    geo.get(
                        "provider"
                    )
                    if geo.get(
                        "available"
                    )
                    else
                    None
                )
        },

        "security": {
            "location_is_approximate":
                True,

            "person_identity_inferred":
                False,

            "external_geo_data_is_information_only":
                True,

            "shell_execution":
                False,

            "payload_execution":
                False
        }
    }


    return payload


# ============================================================
# FIND LATEST INCIDENT
# ============================================================

def latest_incident_payload():

    events = read_events()


    if not events:

        return {
            "status":
                "NO_EVENTS",

            "reason":
                "EVENT_LOG_EMPTY_OR_MISSING",

            "events_file":
                EVENTS_FILE
        }


    # Search backwards because newest events are normally last.

    for event in reversed(
        events
    ):

        normalized = normalize_event(
            event
        )


        # Prefer an event containing a source IP.

        if normalized.get(
            "source_ip"
        ):

            payload = build_incident_payload(
                event
            )

            payload[
                "status"
            ] = "READY"

            return payload


    # If no IP exists, still return the latest security event.

    payload = build_incident_payload(
        events[
            -1
        ]
    )


    payload[
        "status"
    ] = "READY_NO_SOURCE_IP"


    return payload


# ============================================================
# SAVE PAYLOAD
# ============================================================

def save_payload(
    payload
):

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )


    temporary = (
        OUTPUT_FILE
        +
        ".tmp"
    )


    with open(
        temporary,
        "w",
        encoding="utf-8"
    ) as handle:

        json.dump(
            payload,
            handle,
            indent=2,
            ensure_ascii=False
        )


    os.replace(
        temporary,
        OUTPUT_FILE
    )


    return OUTPUT_FILE


def write_latest_payload():

    payload = latest_incident_payload()


    if not payload.get(
        "status",
        ""
    ).startswith(
        "READY"
    ):

        return payload


    path = save_payload(
        payload
    )


    result = dict(
        payload
    )


    result[
        "payload_file"
    ] = path


    return result


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    synthetic_event = {

        "source_ip":
            "203.0.113.42",

        "timestamp":
            "2026-08-30T18:30:00+00:00",

        "event_type":
            "HONEYPOT_RECONNAISSANCE",

        "risk_score":
            87,

        "action":
            "CONTAINED",

        "description":
            "Synthetic Sentinel bridge test."
    }


    normalized = normalize_event(
        synthetic_event
    )


    payload = build_incident_payload(
        synthetic_event
    )


    passed = all(
        [
            normalized[
                "source_ip"
            ]
            ==
            "203.0.113.42",

            normalized[
                "risk_score"
            ]
            ==
            87.0,

            normalized[
                "threat_type"
            ]
            ==
            "HONEYPOT_RECONNAISSANCE",

            payload[
                "geo"
            ].get(
                "available"
            )
            is False,

            payload[
                "security"
            ][
                "person_identity_inferred"
            ]
            is False
        ]
    )


    return {

        "status":
            (
                "PASS"
                if passed
                else
                "FAIL"
            ),

        "version":
            BRIDGE_VERSION,

        "events_file":
            EVENTS_FILE,

        "output_file":
            OUTPUT_FILE,

        "event_file_exists":
            os.path.isfile(
                EVENTS_FILE
            ),

        "features": {
            "source_ip_detection":
                True,

            "nested_fields":
                True,

            "risk_normalization":
                True,

            "geo_intelligence":
                True,

            "private_ip_safe":
                True,

            "visual_replay_payload":
                True
        },

        "security": {
            "shell_execution":
                False,

            "payload_execution":
                False,

            "person_identification":
                False,

            "approximate_ip_location_only":
                True
        }
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    import pprint

    pprint.pp(
        write_latest_payload()
    )