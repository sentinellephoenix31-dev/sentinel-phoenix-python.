import json
import os
import re
from datetime import (
    datetime,
    timedelta,
    timezone,
)


# ============================================================
# SENTINEL PHOENIX
# INCIDENT REPLAY QUERY ENGINE V1.5
#
# V1.5 FIX:
#
# Presence / Face / Identity / Evidence events are NOT
# Visual Incident Replay cybersecurity incidents.
#
# Query
#   ↓
# Cyber-event discovery
#   ↓
# Noise filtering
#   ↓
# Time filtering
#   ↓
# Replay payload
#   ↓
# Globe
# ============================================================


QUERY_VERSION = "1.5"

MAX_EVENTS = 3000

LATEST_LIMIT = 100


# ============================================================
# PATHS
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

REPLAY_DATA_DIR = os.path.join(
    DATA_DIR,
    "incident_replay"
)

LATEST_PAYLOAD_FILE = os.path.join(
    REPLAY_DATA_DIR,
    "latest_payload.json"
)


# ============================================================
# FILE FILTERING
# ============================================================

CYBER_FILE_MARKERS = (
    "event",
    "incident",
    "alert",
    "threat",
    "attack",
    "honeypot",
    "deception",
    "sandbox",
    "network",
    "security",
)

EXCLUDED_FILE_MARKERS = (
    "presence",
    "identity",
    "face",
    "guest",
    "owner",
    "evidence",
    "liveness",
    "hud",
    "gallery",
    "registry",
    "text_console",
    "runtime",
)


# ============================================================
# EVENT FILTERING
# ============================================================

PRESENCE_EVENT_MARKERS = (
    "OWNER_PRESENT",
    "OWNER_ABSENT",
    "UNKNOWN_PERSON",
    "GUEST_PRESENT",
    "FACE_DETECTED",
    "FACE_VERIFIED",
    "LIVENESS",
    "IDENTITY",
    "GUEST_ENROLLMENT",
)


CYBER_EVENT_MARKERS = (
    "ATTACK",
    "INTRUSION",
    "THREAT",
    "ALERT",
    "INCIDENT",
    "EXPLOIT",
    "MALWARE",
    "PAYLOAD",
    "SCAN",
    "PORT_SCAN",
    "BRUTE_FORCE",
    "BRUTEFORCE",
    "SSH",
    "HTTP",
    "HTTPS",
    "TELNET",
    "FTP",
    "CONNECTION",
    "NETWORK",
    "COMMAND",
    "PROBE",
    "INJECTION",
    "SQLI",
    "XSS",
    "RCE",
    "HONEYPOT",
    "DECEPTION",
    "SANDBOX",
    "AUTH_FAILURE",
    "LOGIN_FAILURE",
    "REQUEST",
)


NETWORK_KEYS = (
    "ip",
    "source_ip",
    "src_ip",
    "remote_ip",
    "attacker_ip",
    "client_ip",
    "destination_ip",
    "dst_ip",
    "port",
    "source_port",
    "src_port",
    "destination_port",
    "dst_port",
    "protocol",
)


CYBER_KEYS = (
    "attack_type",
    "threat",
    "threat_type",
    "severity",
    "risk",
    "risk_score",
    "payload",
    "exploit",
    "vulnerability",
    "signature",
    "technique",
    "protocol",
    "port",
    "service",
    "request",
    "command",
    "user_agent",
)


TIMESTAMP_KEYS = (
    "timestamp",
    "timestamp_iso",
    "time",
    "datetime",
    "created_at",
    "detected_at",
    "event_time",
    "occurred_at",
    "date",
)


# ============================================================
# STORAGE
# ============================================================

def ensure_storage():

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    os.makedirs(
        REPLAY_DATA_DIR,
        exist_ok=True
    )


# ============================================================
# QUERY NORMALIZATION
# ============================================================

def normalize_query(
    query
):

    value = str(
        query or ""
    ).strip().lower()

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value


# ============================================================
# PERIOD DETECTION
# ============================================================

def detect_period(
    query
):

    value = normalize_query(
        query
    )


    dangerous_markers = (
        "most dangerous",
        "most severe",
        "highest risk",
        "worst attack",
        "attaque la plus dangereuse",
        "attaque la plus grave",
        "incident le plus grave",
    )


    selection = (
        "MOST_DANGEROUS"
        if any(
            marker in value
            for marker in dangerous_markers
        )
        else
        "ALL"
    )


    if any(
        marker in value
        for marker in (
            "last night",
            "overnight",
            "cette nuit",
            "la nuit derniere",
            "la nuit dernière",
            "hier soir",
        )
    ):

        period = "LAST_NIGHT"


    elif any(
        marker in value
        for marker in (
            "yesterday",
            "hier",
        )
    ):

        period = "YESTERDAY"


    elif any(
        marker in value
        for marker in (
            "this morning",
            "ce matin",
        )
    ):

        period = "THIS_MORNING"


    elif any(
        marker in value
        for marker in (
            "this afternoon",
            "cet apres-midi",
            "cet après-midi",
        )
    ):

        period = "THIS_AFTERNOON"


    elif any(
        marker in value
        for marker in (
            "this evening",
            "ce soir",
        )
    ):

        period = "THIS_EVENING"


    elif any(
        marker in value
        for marker in (
            "last 24 hours",
            "past 24 hours",
            "24 hours",
            "dernieres 24 heures",
            "dernières 24 heures",
        )
    ):

        period = "LAST_24_HOURS"


    elif any(
        marker in value
        for marker in (
            "last 7 days",
            "past 7 days",
            "7 days",
            "7 derniers jours",
        )
    ):

        period = "LAST_7_DAYS"


    elif any(
        marker in value
        for marker in (
            "this week",
            "cette semaine",
        )
    ):

        period = "THIS_WEEK"


    elif any(
        marker in value
        for marker in (
            "today",
            "aujourd'hui",
            "aujourdhui",
        )
    ):

        period = "TODAY"


    else:

        period = "LATEST"


    return {
        "period":
            period,

        "selection":
            selection,
    }


# ============================================================
# LOCAL TIME
# ============================================================

def local_now():

    return datetime.now().astimezone()


# ============================================================
# PERIOD WINDOW
# ============================================================

def period_window(
    period,
    now=None
):

    if now is None:

        now = local_now()


    today = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )


    if period == "TODAY":

        return (
            today,
            now
        )


    if period == "YESTERDAY":

        return (
            today
            -
            timedelta(
                days=1
            ),
            today
        )


    if period == "LAST_NIGHT":

        start = (
            today
            -
            timedelta(
                days=1
            )
        ).replace(
            hour=18
        )

        end = today.replace(
            hour=6
        )

        return (
            start,
            end
        )


    if period == "THIS_MORNING":

        start = today.replace(
            hour=5
        )

        end = min(
            now,
            today.replace(
                hour=12
            )
        )

        return (
            start,
            end
        )


    if period == "THIS_AFTERNOON":

        start = today.replace(
            hour=12
        )

        end = min(
            now,
            today.replace(
                hour=18
            )
        )

        return (
            start,
            end
        )


    if period == "THIS_EVENING":

        return (
            today.replace(
                hour=18
            ),
            now
        )


    if period == "LAST_24_HOURS":

        return (
            now
            -
            timedelta(
                hours=24
            ),
            now
        )


    if period == "LAST_7_DAYS":

        return (
            now
            -
            timedelta(
                days=7
            ),
            now
        )


    if period == "THIS_WEEK":

        return (
            today
            -
            timedelta(
                days=today.weekday()
            ),
            now
        )


    return (
        None,
        None
    )


# ============================================================
# TIMESTAMP
# ============================================================

def parse_timestamp(
    value
):

    if value is None:

        return None


    if isinstance(
        value,
        (
            int,
            float,
        )
    ):

        number = float(
            value
        )


        if number > 100000000000:

            number /= 1000.0


        try:

            return datetime.fromtimestamp(
                number,
                tz=timezone.utc
            ).astimezone()

        except Exception:

            return None


    text = str(
        value
    ).strip()


    if not text:

        return None


    try:

        if re.fullmatch(
            r"\d+(?:\.\d+)?",
            text
        ):

            return parse_timestamp(
                float(
                    text
                )
            )

    except ValueError:

        pass


    if text.endswith(
        "Z"
    ):

        text = (
            text[:-1]
            +
            "+00:00"
        )


    try:

        parsed = datetime.fromisoformat(
            text
        )


        if parsed.tzinfo is None:

            parsed = parsed.replace(
                tzinfo=local_now().tzinfo
            )


        return parsed.astimezone()

    except ValueError:

        pass


    for format_string in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ):

        try:

            parsed = datetime.strptime(
                text,
                format_string
            )


            return parsed.replace(
                tzinfo=local_now().tzinfo
            )

        except ValueError:

            continue


    return None


def recursive_value(
    mapping,
    keys
):

    if not isinstance(
        mapping,
        dict
    ):

        return None


    for key in keys:

        value = mapping.get(
            key
        )

        if value not in (
            None,
            "",
        ):

            return value


    for value in mapping.values():

        if isinstance(
            value,
            dict
        ):

            result = recursive_value(
                value,
                keys
            )


            if result not in (
                None,
                "",
            ):

                return result


    return None


def event_timestamp(
    event
):

    return parse_timestamp(
        recursive_value(
            event,
            TIMESTAMP_KEYS
        )
    )


# ============================================================
# CYBER EVENT CLASSIFICATION
# ============================================================

def flatten_strings(
    value
):

    results = []


    if isinstance(
        value,
        dict
    ):

        for nested in value.values():

            results.extend(
                flatten_strings(
                    nested
                )
            )


    elif isinstance(
        value,
        list
    ):

        for nested in value:

            results.extend(
                flatten_strings(
                    nested
                )
            )


    elif isinstance(
        value,
        str
    ):

        results.append(
            value
        )


    return results


def has_recursive_key(
    mapping,
    keys
):

    if not isinstance(
        mapping,
        dict
    ):

        return False


    for key, value in mapping.items():

        if (
            key.lower() in keys
            and
            value not in (
                None,
                "",
                [],
                {},
            )
        ):

            return True


        if isinstance(
            value,
            dict
        ):

            if has_recursive_key(
                value,
                keys
            ):

                return True


    return False


def is_presence_event(
    event
):

    strings = " ".join(
        flatten_strings(
            event
        )
    ).upper()


    if any(
        marker in strings
        for marker in PRESENCE_EVENT_MARKERS
    ):

        # A real network incident could theoretically contain
        # words such as "identity", so network evidence wins.

        if not has_recursive_key(
            event,
            set(
                NETWORK_KEYS
            )
        ):

            return True


    return False


def is_cyber_event(
    event
):

    if not isinstance(
        event,
        dict
    ):

        return False


    if is_presence_event(
        event
    ):

        return False


    if has_recursive_key(
        event,
        set(
            NETWORK_KEYS
        )
    ):

        return True


    if has_recursive_key(
        event,
        set(
            CYBER_KEYS
        )
    ):

        return True


    strings = " ".join(
        flatten_strings(
            event
        )
    ).upper()


    return any(
        marker in strings
        for marker in CYBER_EVENT_MARKERS
    )


# ============================================================
# FILE DISCOVERY
# ============================================================

def file_is_excluded(
    filename
):

    lower_name = str(
        filename
    ).lower()


    return any(
        marker in lower_name
        for marker in EXCLUDED_FILE_MARKERS
    )


def discover_event_files():

    ensure_storage()


    results = []

    seen = set()


    for root, directories, files in os.walk(
        DATA_DIR
    ):

        directories[:] = [
            directory
            for directory in directories
            if not file_is_excluded(
                directory
            )
        ]


        for filename in files:

            lower_name = filename.lower()


            if not lower_name.endswith(
                (
                    ".json",
                    ".jsonl",
                )
            ):

                continue


            if file_is_excluded(
                lower_name
            ):

                continue


            if lower_name == (
                "latest_payload.json"
            ):

                continue


            if not any(
                marker in lower_name
                for marker in CYBER_FILE_MARKERS
            ):

                continue


            path = os.path.join(
                root,
                filename
            )


            real_path = os.path.realpath(
                path
            )


            if real_path in seen:

                continue


            seen.add(
                real_path
            )

            results.append(
                path
            )


    return results


# ============================================================
# JSON EXTRACTION
# ============================================================

EVENT_CONTAINER_KEYS = (
    "events",
    "incidents",
    "alerts",
    "threats",
    "attacks",
    "records",
    "items",
    "results",
    "data",
)


def extract_event_objects(
    value
):

    if isinstance(
        value,
        list
    ):

        return [
            item
            for item in value
            if isinstance(
                item,
                dict
            )
        ]


    if not isinstance(
        value,
        dict
    ):

        return []


    for key in EVENT_CONTAINER_KEYS:

        nested = value.get(
            key
        )


        if isinstance(
            nested,
            list
        ):

            return [
                item
                for item in nested
                if isinstance(
                    item,
                    dict
                )
            ]


    return [
        value
    ]


# ============================================================
# READ FILE
# ============================================================

def read_event_file(
    path,
    remaining
):

    events = []


    try:

        if path.lower().endswith(
            ".jsonl"
        ):

            with open(
                path,
                "r",
                encoding="utf-8",
                errors="replace"
            ) as handle:

                for line in handle:

                    if len(
                        events
                    ) >= remaining:

                        break


                    line = line.strip()


                    if not line:

                        continue


                    try:

                        value = json.loads(
                            line
                        )

                    except json.JSONDecodeError:

                        continue


                    for event in extract_event_objects(
                        value
                    ):

                        if is_cyber_event(
                            event
                        ):

                            events.append(
                                event
                            )


                            if len(
                                events
                            ) >= remaining:

                                break


            return events


        with open(
            path,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as handle:

            value = json.load(
                handle
            )


        for event in extract_event_objects(
            value
        ):

            if is_cyber_event(
                event
            ):

                events.append(
                    event
                )


                if len(
                    events
                ) >= remaining:

                    break


    except (
        OSError,
        json.JSONDecodeError,
    ):

        pass


    return events


# ============================================================
# READ ALL CYBER EVENTS
# ============================================================

def read_events(
    limit=MAX_EVENTS
):

    files = discover_event_files()

    events = []


    for path in files:

        remaining = (
            limit
            -
            len(
                events
            )
        )


        if remaining <= 0:

            break


        loaded = read_event_file(
            path,
            remaining
        )


        for event in loaded:

            copied = dict(
                event
            )


            copied[
                "_sentinel_source_file"
            ] = os.path.relpath(
                path,
                BASE_DIR
            )


            events.append(
                copied
            )


    return (
        events,
        files
    )


# ============================================================
# TIME FILTER
# ============================================================

def event_in_window(
    event,
    start,
    end
):

    timestamp = event_timestamp(
        event
    )


    if timestamp is None:

        return False


    if (
        start is not None
        and
        timestamp < start
    ):

        return False


    if (
        end is not None
        and
        timestamp >= end
    ):

        return False


    return True


def timestamp_sort_value(
    event
):

    timestamp = event_timestamp(
        event
    )


    if timestamp is None:

        return float(
            "-inf"
        )


    return timestamp.timestamp()


# ============================================================
# SEVERITY
# ============================================================

def event_severity_score(
    event
):

    value = recursive_value(
        event,
        (
            "severity",
            "risk",
            "risk_score",
            "score",
            "threat_score",
            "priority",
        )
    )


    if isinstance(
        value,
        (
            int,
            float,
        )
    ):

        return float(
            value
        )


    text = str(
        value or ""
    ).lower().strip()


    mapping = {
        "critical": 100,
        "high": 80,
        "severe": 80,
        "medium": 50,
        "moderate": 50,
        "low": 20,
        "info": 5,
    }


    if text in mapping:

        return float(
            mapping[
                text
            ]
        )


    try:

        return float(
            text
        )

    except ValueError:

        return 0.0


# ============================================================
# QUERY
# ============================================================

def query_events(
    query
):

    detection = detect_period(
        query
    )


    period = detection[
        "period"
    ]

    selection = detection[
        "selection"
    ]


    events, files = read_events()


    events.sort(
        key=timestamp_sort_value,
        reverse=True
    )


    if period == "LATEST":

        matched = events[
            :LATEST_LIMIT
        ]


    else:

        start, end = period_window(
            period
        )


        matched = [
            event
            for event in events
            if event_in_window(
                event,
                start,
                end
            )
        ]


    if (
        selection
        ==
        "MOST_DANGEROUS"
        and
        matched
    ):

        matched.sort(
            key=lambda event:
                (
                    event_severity_score(
                        event
                    ),
                    timestamp_sort_value(
                        event
                    )
                ),
            reverse=True
        )


        matched = matched[
            :1
        ]


    return {
        "query":
            str(
                query or ""
            ),

        "period":
            period,

        "selection":
            selection,

        "events":
            matched,

        "total_events":
            len(
                events
            ),

        "matched_events":
            len(
                matched
            ),

        "source_files":
            files,
    }


# ============================================================
# SAVE PAYLOAD
# ============================================================

def save_payload(
    payload
):

    ensure_storage()


    temporary = (
        LATEST_PAYLOAD_FILE
        +
        ".tmp"
    )


    try:

        with open(
            temporary,
            "w",
            encoding="utf-8"
        ) as handle:

            json.dump(
                payload,
                handle,
                indent=2,
                ensure_ascii=False,
                default=str
            )


        os.replace(
            temporary,
            LATEST_PAYLOAD_FILE
        )


        return True


    except OSError:

        return False


# ============================================================
# PUBLIC API
# ============================================================

def replay_payload_for_query(
    query
):

    result = query_events(
        query
    )


    now = local_now()


    start, end = period_window(
        result[
            "period"
        ],
        now=now
    )


    payload = {
        "status":
            "READY",

        "version":
            QUERY_VERSION,

        "engine":
            "SENTINEL_INCIDENT_REPLAY_QUERY",

        "query":
            result[
                "query"
            ],

        "period":
            result[
                "period"
            ],

        "selection":
            result[
                "selection"
            ],

        "generated_at":
            now.isoformat(),

        "window": {
            "start":
                (
                    start.isoformat()
                    if start is not None
                    else None
                ),

            "end":
                (
                    end.isoformat()
                    if end is not None
                    else None
                ),
        },

        "total_events":
            result[
                "total_events"
            ],

        "matched_events":
            result[
                "matched_events"
            ],

        "source_files": [
            os.path.relpath(
                path,
                BASE_DIR
            )
            for path in result[
                "source_files"
            ]
        ],

        "incidents":
            result[
                "events"
            ],

        "events":
            result[
                "events"
            ],
    }


    save_payload(
        payload
    )


    return payload


# ============================================================
# COMPATIBILITY
# ============================================================

def build_replay_payload(
    query
):

    return replay_payload_for_query(
        query
    )


def get_replay_payload(
    query
):

    return replay_payload_for_query(
        query
    )


def query_replay(
    query
):

    return replay_payload_for_query(
        query
    )


def run_query(
    query
):

    return replay_payload_for_query(
        query
    )


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    presence_example = {
        "event":
            "OWNER_PRESENT",

        "role":
            "OWNER",

        "confidence":
            95.0,
    }


    cyber_example = {
        "event":
            "CONNECTION",

        "source_ip":
            "203.0.113.5",

        "port":
            22,

        "protocol":
            "tcp",
    }


    tests = {
        "today":
            detect_period(
                "What happened today?"
            )["period"]
            ==
            "TODAY",

        "yesterday":
            detect_period(
                "What happened yesterday?"
            )["period"]
            ==
            "YESTERDAY",

        "last_night":
            detect_period(
                "What happened last night?"
            )["period"]
            ==
            "LAST_NIGHT",

        "last_24_hours":
            detect_period(
                "Show last 24 hours"
            )["period"]
            ==
            "LAST_24_HOURS",

        "last_7_days":
            detect_period(
                "Show last 7 days"
            )["period"]
            ==
            "LAST_7_DAYS",

        "presence_rejected":
            not is_cyber_event(
                presence_example
            ),

        "network_event_accepted":
            is_cyber_event(
                cyber_example
            ),

        "presence_file_rejected":
            file_is_excluded(
                "presence_events.jsonl"
            ),

        "public_api":
            callable(
                replay_payload_for_query
            ),
    }


    passed = all(
        tests.values()
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
            QUERY_VERSION,

        "replay_payload_for_query":
            True,

        "cyber_only":
            True,

        "presence_events_excluded":
            True,

        "identity_events_excluded":
            True,

        "tests":
            tests,

        "security": {
            "local_files_only":
                True,

            "shell_execution":
                False,

            "attacker_payload_execution":
                False,
        }
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    import pprint

    pprint.pp(
        self_test()
    )