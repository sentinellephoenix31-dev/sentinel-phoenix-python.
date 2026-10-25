import json
import os
import sqlite3

from datetime import (
    datetime,
    timedelta,
    timezone
)

from core.semantic import (
    route_question
)


# ============================================================
# SENTINEL PHOENIX
# BRAIN MEMORY + CONTEXT TIMELINE ENGINE V2
# ============================================================


BRAIN_MEMORY_VERSION = "2.0"


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

PRESENCE_FILE = os.path.join(
    DATA_DIR,
    "presence_events.jsonl"
)

MEMORY_DATABASE = os.path.join(
    DATA_DIR,
    "phoenix_memory.db"
)

MAX_EVENTS_TO_LOAD = 10000


# ============================================================
# TIME
# ============================================================

def local_now():

    return datetime.now().astimezone()


def parse_timestamp(value):

    if value is None:

        return None

    if isinstance(
        value,
        (
            int,
            float
        )
    ):

        try:

            return datetime.fromtimestamp(
                value,
                tz=timezone.utc
            )

        except (
            OSError,
            OverflowError,
            ValueError
        ):

            return None

    text = str(
        value
    ).strip()

    if not text:

        return None

    try:

        if text.endswith("Z"):

            text = (
                text[:-1]
                +
                "+00:00"
            )

        result = datetime.fromisoformat(
            text
        )

        if result.tzinfo is None:

            result = result.replace(
                tzinfo=timezone.utc
            )

        return result

    except ValueError:

        return None


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


# ============================================================
# SECURITY EVENTS
# ============================================================

def load_events(
    limit=MAX_EVENTS_TO_LOAD
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
        ) as file:

            for line in file:

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

    return events[
        -int(limit):
    ]


# ============================================================
# PRESENCE EVENTS
# ============================================================

def load_presence_events():

    if not os.path.isfile(
        PRESENCE_FILE
    ):

        return []

    results = []

    try:

        with open(
            PRESENCE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            for line in file:

                line = line.strip()

                if not line:

                    continue

                try:

                    event = json.loads(
                        line
                    )

                except json.JSONDecodeError:

                    continue

                timestamp = parse_timestamp(
                    event.get(
                        "timestamp"
                    )
                )

                event_type = str(
                    event.get(
                        "event",

                        event.get(
                            "type",
                            ""
                        )
                    )
                ).upper()

                if (
                    timestamp
                    and
                    event_type
                ):

                    results.append(
                        {
                            "timestamp":
                                timestamp,

                            "event":
                                event_type
                        }
                    )

    except OSError:

        return []

    return sorted(
        results,
        key=lambda item:
            item[
                "timestamp"
            ]
    )


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_event(event):

    timestamp = parse_timestamp(

        event.get(
            "timestamp",

            event.get(
                "created_at"
            )
        )
    )

    source_ip = str(

        event.get(
            "source_ip",

            event.get(
                "ip",
                "UNKNOWN"
            )
        )
    )

    global_score = safe_float(

        event.get(
            "global_score",

            (
                event.get(
                    "fusion"
                )
                or
                {}
            ).get(
                "global_score",
                0
            )
        )
    )

    global_level = str(

        event.get(
            "global_level",

            (
                event.get(
                    "fusion"
                )
                or
                {}
            ).get(
                "global_level",
                "LOW"
            )
        )

    ).upper()

    policy_action = str(

        event.get(
            "response_action",

            (
                event.get(
                    "response"
                )
                or
                {}
            ).get(
                "action",
                ""
            )
        )
    )

    containment = bool(

        event.get(
            "containment_requested",

            (
                event.get(
                    "response"
                )
                or
                {}
            ).get(
                "containment_requested",
                False
            )
        )
    )

    if (
        "CONTAIN"
        in policy_action.upper()
    ):

        containment = True

    decoy_active = bool(

        event.get(
            "decoy_active",

            (
                event.get(
                    "deception"
                )
                or
                {}
            ).get(
                "decoy_active",
                False
            )
        )
    )

    surface_rotated = bool(

        event.get(
            "surface_rotated",

            (
                event.get(
                    "deception"
                )
                or
                {}
            ).get(
                "surface_rotated",
                False
            )
        )
    )

    return {

        "timestamp":
            timestamp,

        "source_ip":
            source_ip,

        "source_port":
            event.get(
                "source_port",

                event.get(
                    "port"
                )
            ),

        "payload":
            str(
                event.get(
                    "payload",
                    ""
                )
            )[:512],

        "global_score":
            global_score,

        "global_level":
            global_level,

        "policy_action":
            policy_action,

        "containment":
            containment,

        "decoy_active":
            decoy_active,

        "surface_rotated":
            surface_rotated,

        "raw":
            event
    }


def normalized_events():

    return [
        normalize_event(
            event
        )
        for event in load_events()
    ]


# ============================================================
# BASIC TIME WINDOW
# ============================================================

def basic_time_window(
    time_range,
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

    # ========================================================
    # ALL TIME
    # ========================================================

    if time_range == "ALL_TIME":

        return {
            "start":
                None,

            "end":
                now
        }

    # ========================================================
    # TODAY
    # ========================================================

    if time_range == "TODAY":

        return {
            "start":
                today,

            "end":
                now
        }

    # ========================================================
    # YESTERDAY
    # ========================================================

    if time_range == "YESTERDAY":

        return {
            "start":
                today
                -
                timedelta(
                    days=1
                ),

            "end":
                today
        }

    # ========================================================
    # LAST NIGHT
    # ========================================================

    if time_range == "LAST_NIGHT":

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

        if now < end:

            end = now

        return {
            "start":
                start,

            "end":
                end
        }

    # ========================================================
    # THIS MORNING
    # ========================================================

    if time_range == "THIS_MORNING":

        start = today.replace(
            hour=6
        )

        end = today.replace(
            hour=12
        )

        return {
            "start":
                start,

            "end":
                min(
                    now,
                    end
                )
        }

    # ========================================================
    # THIS AFTERNOON
    # ========================================================

    if time_range == "THIS_AFTERNOON":

        start = today.replace(
            hour=12
        )

        end = today.replace(
            hour=18
        )

        return {
            "start":
                start,

            "end":
                min(
                    now,
                    end
                )
        }

    # ========================================================
    # THIS EVENING
    # ========================================================

    if time_range == "THIS_EVENING":

        start = today.replace(
            hour=18
        )

        return {
            "start":
                start,

            "end":
                now
        }

    # ========================================================
    # LAST 24 HOURS
    # ========================================================

    if time_range == "LAST_24_HOURS":

        return {
            "start":
                now
                -
                timedelta(
                    hours=24
                ),

            "end":
                now
        }

    # ========================================================
    # LAST 7 DAYS
    # ========================================================

    if time_range == "LAST_7_DAYS":

        return {
            "start":
                now
                -
                timedelta(
                    days=7
                ),

            "end":
                now
        }

    # ========================================================
    # THIS WEEK
    # Monday 00:00 -> now
    # ========================================================

    if time_range == "THIS_WEEK":

        start = (
            today
            -
            timedelta(
                days=today.weekday()
            )
        )

        return {
            "start":
                start,

            "end":
                now
        }

    # ========================================================
    # THIS WEEKEND
    # Most recent/current Saturday -> now
    # ========================================================

    if time_range == "THIS_WEEKEND":

        days_since_saturday = (
            today.weekday()
            -
            5
        ) % 7

        start = (
            today
            -
            timedelta(
                days=days_since_saturday
            )
        )

        return {
            "start":
                start,

            "end":
                now
        }

    return {
        "start":
            today,

        "end":
            now
    }


# ============================================================
# EXPLICIT CLOCK
# ============================================================

def apply_explicit_clock(
    window,
    clock
):

    if not clock:

        return window

    start_reference = (
        window.get(
            "start"
        )
        or
        local_now()
    )

    start_hour, start_minute = [
        int(value)
        for value in clock[
            "start"
        ].split(":")
    ]

    end_hour, end_minute = [
        int(value)
        for value in clock[
            "end"
        ].split(":")
    ]

    start = start_reference.replace(
        hour=start_hour,
        minute=start_minute,
        second=0,
        microsecond=0
    )

    end = start_reference.replace(
        hour=end_hour,
        minute=end_minute,
        second=0,
        microsecond=0
    )

    if end < start:

        end += timedelta(
            days=1
        )

    base_start = window.get(
        "start"
    )

    base_end = window.get(
        "end"
    )

    if (
        base_start
        and
        start < base_start
    ):

        start = base_start

    if (
        base_end
        and
        end > base_end
    ):

        end = base_end

    return {
        "start":
            start,

        "end":
            end
    }


# ============================================================
# OWNER PRESENCE CONTEXT
# ============================================================

def latest_owner_left(
    now=None
):

    if now is None:

        now = local_now()

    presence = load_presence_events()

    candidates = [
        item
        for item in presence
        if (
            item[
                "event"
            ]
            ==
            "OWNER_LEFT"
            and
            item[
                "timestamp"
            ].astimezone()
            <=
            now
        )
    ]

    if not candidates:

        return None

    return candidates[-1]


def owner_absence_window(
    now=None
):

    if now is None:

        now = local_now()

    presence = load_presence_events()

    owner_left = latest_owner_left(
        now
    )

    if owner_left is None:

        return None

    start = (
        owner_left[
            "timestamp"
        ].astimezone()
    )

    returns = [
        item
        for item in presence
        if (
            item[
                "event"
            ]
            in (
                "OWNER_RETURNED",
                "OWNER_PRESENT"
            )
            and
            item[
                "timestamp"
            ].astimezone()
            >
            start
        )
    ]

    if returns:

        end = (
            returns[0][
                "timestamp"
            ].astimezone()
        )

    else:

        end = now

    return {
        "start":
            start,

        "end":
            end
    }


# ============================================================
# WINDOW INTERSECTION
# ============================================================

def intersect_windows(
    first,
    second
):

    starts = [
        value
        for value in (
            first.get(
                "start"
            ),
            second.get(
                "start"
            )
        )
        if value is not None
    ]

    ends = [
        value
        for value in (
            first.get(
                "end"
            ),
            second.get(
                "end"
            )
        )
        if value is not None
    ]

    start = (
        max(starts)
        if starts
        else None
    )

    end = (
        min(ends)
        if ends
        else None
    )

    return {
        "start":
            start,

        "end":
            end
    }


# ============================================================
# SEMANTIC WINDOW
# ============================================================

def resolve_semantic_window(
    semantic,
    now=None
):

    if now is None:

        now = local_now()

    time_range = semantic.get(
        "time_range",
        "TODAY"
    )

    window = basic_time_window(
        time_range,
        now
    )

    window = apply_explicit_clock(
        window,
        semantic.get(
            "explicit_clock"
        )
    )

    context = semantic.get(
        "presence_context"
    )

    if context == "OWNER_ABSENCE":

        absence = owner_absence_window(
            now
        )

        if absence is None:

            return {
                "resolved":
                    False,

                "reason":
                    "OWNER_PRESENCE_HISTORY_UNAVAILABLE",

                "start":
                    None,

                "end":
                    None
            }

        window = intersect_windows(
            window,
            absence
        )

    elif context == "SINCE_OWNER_LEFT":

        owner_left = latest_owner_left(
            now
        )

        if owner_left is None:

            return {
                "resolved":
                    False,

                "reason":
                    "OWNER_PRESENCE_HISTORY_UNAVAILABLE",

                "start":
                    None,

                "end":
                    None
            }

        since_left = {
            "start":
                owner_left[
                    "timestamp"
                ].astimezone(),

            "end":
                now
        }

        window = intersect_windows(
            window,
            since_left
        )

    return {
        "resolved":
            True,

        "reason":
            "WINDOW_RESOLVED",

        "start":
            window.get(
                "start"
            ),

        "end":
            window.get(
                "end"
            )
    }


# ============================================================
# EVENT FILTER
# ============================================================

def events_in_window(
    events,
    window
):

    if not window.get(
        "resolved",
        True
    ):

        return []

    start = window.get(
        "start"
    )

    end = window.get(
        "end"
    )

    selected = []

    for event in events:

        timestamp = event.get(
            "timestamp"
        )

        if timestamp is None:

            continue

        local_timestamp = (
            timestamp.astimezone()
        )

        if (
            start is not None
            and
            local_timestamp < start
        ):

            continue

        if (
            end is not None
            and
            local_timestamp > end
        ):

            continue

        selected.append(
            event
        )

    return selected


# ============================================================
# SUMMARY
# ============================================================

def summarize_events(events):

    if not events:

        return {
            "total_events":
                0,

            "unique_sources":
                0,

            "high_risk_events":
                0,

            "critical_events":
                0,

            "containments":
                0,

            "deception_events":
                0,

            "surface_rotations":
                0,

            "maximum_risk":
                0.0,

            "most_dangerous":
                None
        }

    sources = {
        event[
            "source_ip"
        ]
        for event in events
    }

    high_risk = [
        event
        for event in events
        if (
            event[
                "global_score"
            ] >= 60
            or
            event[
                "global_level"
            ]
            in (
                "HIGH",
                "CRITICAL"
            )
        )
    ]

    critical = [
        event
        for event in events
        if (
            event[
                "global_score"
            ] >= 80
            or
            event[
                "global_level"
            ]
            ==
            "CRITICAL"
        )
    ]

    containments = [
        event
        for event in events
        if event[
            "containment"
        ]
    ]

    deception_events = [
        event
        for event in events
        if event[
            "decoy_active"
        ]
    ]

    rotations = [
        event
        for event in events
        if event[
            "surface_rotated"
        ]
    ]

    most_dangerous = max(
        events,
        key=lambda item:
            item[
                "global_score"
            ]
    )

    return {
        "total_events":
            len(events),

        "unique_sources":
            len(sources),

        "high_risk_events":
            len(high_risk),

        "critical_events":
            len(critical),

        "containments":
            len(containments),

        "deception_events":
            len(deception_events),

        "surface_rotations":
            len(rotations),

        "maximum_risk":
            round(
                most_dangerous[
                    "global_score"
                ],
                2
            ),

        "most_dangerous":
            most_dangerous
    }


# ============================================================
# SOURCE MEMORY
# ============================================================

def source_memory(
    source_ip
):

    try:

        from core.memory import (
            get_source_memory
        )

        memory = get_source_memory(
            source_ip
        )

        if memory:

            return memory

    except Exception:

        pass

    events = [
        event
        for event in normalized_events()
        if (
            event[
                "source_ip"
            ]
            ==
            source_ip
        )
    ]

    summary = summarize_events(
        events
    )

    return {
        "source_ip":
            source_ip,

        "total_events":
            summary[
                "total_events"
            ],

        "critical_events":
            summary[
                "critical_events"
            ],

        "containment_events":
            summary[
                "containments"
            ],

        "max_global_score":
            summary[
                "maximum_risk"
            ]
    }


# ============================================================
# DATABASE STATUS
# ============================================================

def database_summary():

    if not os.path.isfile(
        MEMORY_DATABASE
    ):

        return {
            "available":
                False
        }

    connection = sqlite3.connect(
        MEMORY_DATABASE,
        timeout=5
    )

    try:

        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """
        ).fetchall()

        tables = {}

        for row in rows:

            name = str(
                row[0]
            )

            safe_name = (
                name.replace(
                    '"',
                    '""'
                )
            )

            try:

                count = connection.execute(
                    f'SELECT COUNT(*) FROM "{safe_name}"'
                ).fetchone()[0]

            except sqlite3.Error:

                count = None

            tables[
                name
            ] = count

        return {
            "available":
                True,

            "tables":
                tables
        }

    finally:

        connection.close()


# ============================================================
# QUERY
# ============================================================

def query_semantic(
    semantic
):

    events = normalized_events()

    window = resolve_semantic_window(
        semantic
    )

    selected = events_in_window(
        events,
        window
    )

    source_ip = semantic.get(
        "source_ip"
    )

    if source_ip:

        selected = [
            event
            for event in selected
            if (
                event[
                    "source_ip"
                ]
                ==
                source_ip
            )
        ]

    return {
        "version":
            BRAIN_MEMORY_VERSION,

        "semantic":
            semantic,

        "window":
            {
                "resolved":
                    window.get(
                        "resolved",
                        True
                    ),

                "reason":
                    window.get(
                        "reason"
                    ),

                "start":
                    (
                        window[
                            "start"
                        ].isoformat()
                        if window.get(
                            "start"
                        )
                        else None
                    ),

                "end":
                    (
                        window[
                            "end"
                        ].isoformat()
                        if window.get(
                            "end"
                        )
                        else None
                    )
            },

        "summary":
            summarize_events(
                selected
            ),

        "source_memory":
            (
                source_memory(
                    source_ip
                )
                if source_ip
                else None
            ),

        "presence_events":
            len(
                load_presence_events()
            ),

        "database":
            database_summary(),

        "safety":
            {
                "internet_access":
                    False,

                "shell_execution":
                    False,

                "payload_execution":
                    False,

                "host_modification":
                    False
            }
    }


# ============================================================
# NATURAL ANSWER
# ============================================================

def answer_semantic_question(
    question,
    semantic=None
):

    if semantic is None:

        semantic = route_question(
            question
        )

    result = query_semantic(
        semantic
    )

    language = semantic.get(
        "language",
        "EN"
    )

    window = result[
        "window"
    ]

    # ========================================================
    # MISSING PRESENCE CONTEXT
    # ========================================================

    if not window.get(
        "resolved",
        True
    ):

        if language == "FR":

            return (
                "Je comprends que tu parles de ton absence, "
                "mais je n'ai pas encore d'événement "
                "OWNER_LEFT ou OWNER_RETURNED enregistré. "
                "Cette information sera disponible lorsque "
                "le module local de présence et d'identité "
                "sera connecté."
            )

        return (
            "I understand that you are asking about your "
            "absence, but I do not yet have an OWNER_LEFT "
            "or OWNER_RETURNED event recorded. "
            "That context will become available when the "
            "local presence and identity module is connected."
        )

    summary = result[
        "summary"
    ]

    intent = semantic.get(
        "intent"
    )

    # ========================================================
    # SOURCE LOOKUP
    # ========================================================

    if intent == "SOURCE_LOOKUP":

        source_ip = semantic.get(
            "source_ip"
        )

        memory = (
            result.get(
                "source_memory"
            )
            or
            {}
        )

        total = int(
            memory.get(
                "total_events",
                0
            )
        )

        critical = int(
            memory.get(
                "critical_events",
                0
            )
        )

        containments = int(

            memory.get(
                "containment_events",

                memory.get(
                    "historical_containments",
                    0
                )
            )
        )

        maximum = safe_float(

            memory.get(
                "max_global_score",

                memory.get(
                    "maximum_global_score",
                    0
                )
            )
        )

        if language == "FR":

            return (
                f"La source {source_ip} possède "
                f"{total} événement(s) enregistré(s). "
                f"J'ai observé {critical} événement(s) "
                f"critique(s), {containments} confinement(s), "
                f"avec un risque maximal de "
                f"{round(maximum, 2)}/100."
            )

        return (
            f"Source {source_ip} has "
            f"{total} recorded event(s). "
            f"I observed {critical} critical event(s), "
            f"{containments} containment event(s), "
            f"with a maximum risk of "
            f"{round(maximum, 2)}/100."
        )

    # ========================================================
    # MOST DANGEROUS
    # ========================================================

    if intent == "MOST_DANGEROUS":

        event = summary.get(
            "most_dangerous"
        )

        if event is None:

            return (
                "Je n'ai trouvé aucun événement dans cette période."
                if language == "FR"
                else
                "I found no event in that period."
            )

        timestamp = (
            event[
                "timestamp"
            ].astimezone().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if event.get(
                "timestamp"
            )
            else
            "unknown"
        )

        if language == "FR":

            return (
                f"L'événement le plus dangereux venait de "
                f"{event['source_ip']}. "
                f"Son risque a atteint "
                f"{event['global_score']}/100, niveau "
                f"{event['global_level']}, à {timestamp}."
            )

        return (
            f"The most dangerous event came from "
            f"{event['source_ip']}. "
            f"Its risk reached "
            f"{event['global_score']}/100, level "
            f"{event['global_level']}, at {timestamp}."
        )

    # ========================================================
    # CONTAINMENT
    # ========================================================

    if intent == "CONTAINMENT_SUMMARY":

        if language == "FR":

            return (
                f"J'ai enregistré "
                f"{summary['containments']} décision(s) "
                f"de confinement dans cette période."
            )

        return (
            f"I recorded "
            f"{summary['containments']} containment "
            f"decision(s) in that period."
        )

    # ========================================================
    # GENERAL SUMMARY
    # ========================================================

    if summary[
        "total_events"
    ] == 0:

        return (
            "Je n'ai trouvé aucun événement de sécurité "
            "dans cette période."
            if language == "FR"
            else
            "I found no security events in that period."
        )

    if language == "FR":

        return (
            f"Dans cette période, j'ai trouvé "
            f"{summary['total_events']} événement(s) de sécurité "
            f"provenant de "
            f"{summary['unique_sources']} source(s). "
            f"{summary['high_risk_events']} étaient à risque "
            f"élevé ou critique, dont "
            f"{summary['critical_events']} critiques. "
            f"Le risque maximal était "
            f"{summary['maximum_risk']}/100. "
            f"J'ai enregistré "
            f"{summary['containments']} confinement(s), "
            f"{summary['deception_events']} événement(s) "
            f"associé(s) à la deception et "
            f"{summary['surface_rotations']} rotation(s) "
            f"de surface."
        )

    return (
        f"In that period, I found "
        f"{summary['total_events']} security event(s) "
        f"from {summary['unique_sources']} source(s). "
        f"{summary['high_risk_events']} were high or critical "
        f"risk, including "
        f"{summary['critical_events']} critical event(s). "
        f"The maximum risk was "
        f"{summary['maximum_risk']}/100. "
        f"I recorded "
        f"{summary['containments']} containment decision(s), "
        f"{summary['deception_events']} deception-associated "
        f"event(s), and "
        f"{summary['surface_rotations']} deception "
        f"surface rotation(s)."
    )


# ============================================================
# OLD COMPATIBILITY
# ============================================================

def answer_memory_question(
    question
):

    semantic = route_question(
        question
    )

    return answer_semantic_question(
        question,
        semantic
    )


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    questions = [

        "What happened today?",

        "What happened this week?",

        "Anything sketchy happen while I was asleep?",

        "Give me the nastiest incident from the last 7 days.",

        "Qu'est-ce qui s'est passé cet après-midi ?",

        "What happened after I left the office?"
    ]

    results = []

    for question in questions:

        semantic = route_question(
            question
        )

        answer = answer_semantic_question(
            question,
            semantic
        )

        results.append(
            {
                "question":
                    question,

                "intent":
                    semantic[
                        "intent"
                    ],

                "time":
                    semantic[
                        "time_range"
                    ],

                "context":
                    semantic[
                        "presence_context"
                    ],

                "answer":
                    answer
            }
        )

    return {
        "status":
            "PASS",

        "version":
            BRAIN_MEMORY_VERSION,

        "loaded_events":
            len(
                normalized_events()
            ),

        "presence_events":
            len(
                load_presence_events()
            ),

        "results":
            results,

        "safety":
            {
                "internet_access":
                    False,

                "shell_execution":
                    False,

                "payload_execution":
                    False,

                "host_modification":
                    False
            }
    }