import re
import unicodedata


# ============================================================
# SENTINEL PHOENIX
# SEMANTIC UNDERSTANDING CORE V2
# ============================================================

SEMANTIC_VERSION = "2.0"


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(text):

    text = str(text).strip().lower()

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = text.replace(
        "'",
        " "
    )

    text = re.sub(
        r"[^a-z0-9.:\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# LANGUAGE
# ============================================================

def detect_language(text):

    normalized = normalize_text(
        text
    )

    french_words = {
        "quoi",
        "que",
        "hier",
        "nuit",
        "aujourd",
        "semaine",
        "matin",
        "soir",
        "apres",
        "pendant",
        "depuis",
        "parti",
        "dormais",
        "absence",
        "attaque",
        "risque",
        "dangereux",
        "bizarre",
        "louche",
        "evenement",
        "resume",
        "passe"
    }

    score = sum(
        1
        for token in normalized.split()
        if token in french_words
    )

    return (
        "FR"
        if score > 0
        else
        "EN"
    )


# ============================================================
# IPV4
# ============================================================

def extract_ipv4(text):

    match = re.search(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        str(text)
    )

    if not match:
        return None

    candidate = match.group(0)

    try:

        parts = [
            int(part)
            for part in candidate.split(".")
        ]

    except ValueError:

        return None

    if (
        len(parts) == 4
        and
        all(
            0 <= part <= 255
            for part in parts
        )
    ):

        return candidate

    return None


# ============================================================
# PRESENCE CONTEXT
# ============================================================

def detect_presence_context(text):

    normalized = normalize_text(
        text
    )

    absence_markers = (
        "while i was away",
        "while i was gone",
        "during my absence",
        "while i wasnt here",
        "while i was not here",
        "pendant mon absence",
        "quand je n etais pas la",
        "pendant que j etais parti",
        "pendant que je n etais pas la"
    )

    since_left_markers = (
        "since i left",
        "after i left",
        "since i went out",
        "after i went out",
        "since i left the office",
        "after i left the office",
        "depuis que je suis parti",
        "apres que je sois parti",
        "apres mon depart",
        "depuis mon depart",
        "depuis que j ai quitte le bureau",
        "apres avoir quitte le bureau"
    )

    if any(
        marker in normalized
        for marker in absence_markers
    ):

        return "OWNER_ABSENCE"

    if any(
        marker in normalized
        for marker in since_left_markers
    ):

        return "SINCE_OWNER_LEFT"

    return None


# ============================================================
# EXPLICIT CLOCK WINDOW
# ============================================================

def _clock_to_24h(
    hour,
    minute=0,
    meridiem=None
):

    hour = int(hour)
    minute = int(minute or 0)

    if meridiem:

        meridiem = meridiem.lower()

        if (
            meridiem == "pm"
            and
            hour < 12
        ):

            hour += 12

        if (
            meridiem == "am"
            and
            hour == 12
        ):

            hour = 0

    if not (
        0 <= hour <= 23
        and
        0 <= minute <= 59
    ):

        return None

    return f"{hour:02d}:{minute:02d}"


def detect_explicit_clock_window(text):

    normalized = normalize_text(
        text
    )

    # ========================================================
    # ENGLISH
    # between 2pm and 6pm
    # between 14:00 and 18:30
    # ========================================================

    english = re.search(
        r"\bbetween\s+"
        r"(\d{1,2})"
        r"(?::(\d{2}))?"
        r"\s*(am|pm)?"
        r"\s+(?:and|to)\s+"
        r"(\d{1,2})"
        r"(?::(\d{2}))?"
        r"\s*(am|pm)?\b",
        normalized
    )

    if english:

        start = _clock_to_24h(
            english.group(1),
            english.group(2),
            english.group(3)
        )

        end = _clock_to_24h(
            english.group(4),
            english.group(5),
            english.group(6)
        )

        if start and end:

            return {
                "start":
                    start,

                "end":
                    end
            }

    # ========================================================
    # FRENCH
    # entre 14h et 18h
    # entre 14h30 et 18h45
    # ========================================================

    french = re.search(
        r"\bentre\s+"
        r"(\d{1,2})"
        r"(?:h|:)"
        r"(\d{0,2})"
        r"\s+(?:et|a)\s+"
        r"(\d{1,2})"
        r"(?:h|:)"
        r"(\d{0,2})\b",
        normalized
    )

    if french:

        start = _clock_to_24h(
            french.group(1),
            french.group(2) or 0
        )

        end = _clock_to_24h(
            french.group(3),
            french.group(4) or 0
        )

        if start and end:

            return {
                "start":
                    start,

                "end":
                    end
            }

    return None


# ============================================================
# TIME RANGE
# ============================================================

def detect_time_range(text):

    normalized = normalize_text(
        text
    )

    # ========================================================
    # ALL TIME
    # ========================================================

    markers = (
        "all time",
        "entire history",
        "full history",
        "since the beginning",
        "everything you know",
        "tout l historique",
        "historique complet",
        "depuis le debut"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "ALL_TIME",
            True
        )

    # ========================================================
    # LAST 7 DAYS
    # ========================================================

    markers = (
        "last 7 days",
        "past 7 days",
        "previous 7 days",
        "last seven days",
        "7 derniers jours",
        "sept derniers jours"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "LAST_7_DAYS",
            True
        )

    # ========================================================
    # LAST 24 HOURS
    # ========================================================

    markers = (
        "last 24 hours",
        "past 24 hours",
        "previous 24 hours",
        "24 dernieres heures",
        "dernieres 24 heures"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "LAST_24_HOURS",
            True
        )

    # ========================================================
    # THIS WEEK
    # ========================================================

    markers = (
        "this week",
        "current week",
        "cette semaine"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "THIS_WEEK",
            True
        )

    # ========================================================
    # WEEKEND
    # ========================================================

    markers = (
        "this weekend",
        "during the weekend",
        "over the weekend",
        "ce week end",
        "pendant le week end"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "THIS_WEEKEND",
            True
        )

    # ========================================================
    # LAST NIGHT
    # ========================================================

    markers = (
        "last night",
        "overnight",
        "during the night",
        "through the night",
        "while i slept",
        "while i was asleep",
        "while i was sleeping",
        "cette nuit",
        "hier soir",
        "pendant la nuit",
        "durant la nuit",
        "pendant que je dormais",
        "quand je dormais"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "LAST_NIGHT",
            True
        )

    # ========================================================
    # YESTERDAY
    # ========================================================

    markers = (
        "yesterday",
        "previous day",
        "hier",
        "journee d hier"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "YESTERDAY",
            True
        )

    # ========================================================
    # MORNING
    # ========================================================

    markers = (
        "this morning",
        "ce matin"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "THIS_MORNING",
            True
        )

    # ========================================================
    # AFTERNOON
    # ========================================================

    markers = (
        "this afternoon",
        "cet apres midi"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "THIS_AFTERNOON",
            True
        )

    # ========================================================
    # EVENING
    # ========================================================

    markers = (
        "this evening",
        "tonight",
        "ce soir"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "THIS_EVENING",
            True
        )

    # ========================================================
    # TODAY
    # ========================================================

    markers = (
        "today",
        "aujourd hui"
    )

    if any(
        marker in normalized
        for marker in markers
    ):

        return (
            "TODAY",
            True
        )

    return (
        "TODAY",
        False
    )


# ============================================================
# INTENT
# ============================================================

def detect_intent(
    text,
    source_ip=None
):

    normalized = normalize_text(
        text
    )

    # ========================================================
    # EXIT
    # ========================================================

    exit_markers = (
        "exit",
        "quit",
        "goodbye",
        "close conversation",
        "stop conversation",
        "au revoir",
        "quitter",
        "ferme la conversation"
    )

    if any(
        marker == normalized
        or
        marker in normalized
        for marker in exit_markers
    ):

        return (
            "EXIT",
            99.0
        )

    # ========================================================
    # HELP
    # ========================================================

    help_markers = (
        "help",
        "what can you do",
        "what can i ask",
        "show commands",
        "aide",
        "que peux tu faire",
        "que puis je demander",
        "montre les commandes"
    )

    if any(
        marker == normalized
        or
        marker in normalized
        for marker in help_markers
    ):

        return (
            "HELP",
            97.0
        )

    # ========================================================
    # STATUS
    # ========================================================

    status_markers = (
        "sentinel status",
        "system status",
        "how is sentinel",
        "is sentinel working",
        "is sentinel operational",
        "are you operational",
        "etat de sentinel",
        "statut de sentinel",
        "sentinel fonctionne",
        "sentinel est operationnel"
    )

    if any(
        marker in normalized
        for marker in status_markers
    ):

        return (
            "SYSTEM_STATUS",
            96.0
        )

    # ========================================================
    # SOURCE LOOKUP
    # ========================================================

    if source_ip:

        return (
            "SOURCE_LOOKUP",
            96.0
        )

    # ========================================================
    # CONTAINMENT
    # ========================================================

    containment_markers = (
        "contain",
        "contained",
        "containment",
        "isolate",
        "isolated",
        "isolation",
        "quarantine",
        "confine",
        "confinement",
        "isole",
        "isolation"
    )

    if any(
        marker in normalized
        for marker in containment_markers
    ):

        return (
            "CONTAINMENT_SUMMARY",
            91.0
        )

    # ========================================================
    # MOST DANGEROUS
    # ========================================================

    danger_markers = (
        "most dangerous",
        "worst incident",
        "worst event",
        "highest risk",
        "biggest threat",
        "nastiest",
        "most severe",
        "plus dangereux",
        "plus grave",
        "pire incident",
        "plus gros risque",
        "plus grosse menace"
    )

    if any(
        marker in normalized
        for marker in danger_markers
    ):

        return (
            "MOST_DANGEROUS",
            92.0
        )

    # ========================================================
    # INCIDENT SUMMARY
    # ========================================================

    summary_markers = (
        "what happened",
        "what went down",
        "anything happen",
        "anything weird",
        "anything strange",
        "anything suspicious",
        "anything sketchy",
        "what did you detect",
        "security recap",
        "security summary",
        "give me a recap",
        "what happened while",
        "qu est ce qui s est passe",
        "que s est il passe",
        "il s est passe quoi",
        "quelque chose de bizarre",
        "quelque chose de louche",
        "quelque chose de suspect",
        "tu as detecte quoi",
        "fais moi un resume",
        "resume des incidents"
    )

    if any(
        marker in normalized
        for marker in summary_markers
    ):

        return (
            "INCIDENT_SUMMARY",
            89.0
        )

    return (
        "GENERAL_MEMORY_QUERY",
        55.0
    )


# ============================================================
# COMPLETE ROUTER
# ============================================================

def route_question(question):

    original = str(
        question
    ).strip()

    language = detect_language(
        original
    )

    source_ip = extract_ipv4(
        original
    )

    context = detect_presence_context(
        original
    )

    time_range, time_explicit = (
        detect_time_range(
            original
        )
    )

    explicit_clock = (
        detect_explicit_clock_window(
            original
        )
    )

    intent, intent_confidence = (
        detect_intent(
            original,
            source_ip
        )
    )

    # If the user says "while I was away"
    # without another explicit date,
    # don't artificially restrict the query to today.

    if (
        context
        and
        not time_explicit
    ):

        time_range = "ALL_TIME"

    return {

        "semantic_version":
            SEMANTIC_VERSION,

        "original":
            original,

        "language":
            language,

        "intent":
            intent,

        "intent_confidence":
            intent_confidence,

        "time_range":
            time_range,

        "time_explicit":
            time_explicit,

        "presence_context":
            context,

        "source_ip":
            source_ip,

        "explicit_clock":
            explicit_clock,

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
# SELF TEST
# ============================================================

def self_test():

    tests = [

        {
            "question":
                "Anything sketchy happen while I was asleep?",

            "intent":
                "INCIDENT_SUMMARY",

            "time":
                "LAST_NIGHT"
        },

        {
            "question":
                "What happened this week?",

            "intent":
                "INCIDENT_SUMMARY",

            "time":
                "THIS_WEEK"
        },

        {
            "question":
                "Give me the nastiest incident from the last 7 days.",

            "intent":
                "MOST_DANGEROUS",

            "time":
                "LAST_7_DAYS"
        },

        {
            "question":
                "What happened this afternoon?",

            "intent":
                "INCIDENT_SUMMARY",

            "time":
                "THIS_AFTERNOON"
        },

        {
            "question":
                "Qu'est-ce qui s'est passé cette semaine ?",

            "intent":
                "INCIDENT_SUMMARY",

            "time":
                "THIS_WEEK"
        },

        {
            "question":
                "What happened after I left the office?",

            "intent":
                "INCIDENT_SUMMARY",

            "context":
                "SINCE_OWNER_LEFT"
        },

        {
            "question":
                "Qu'est-ce qui s'est passé pendant mon absence ?",

            "intent":
                "INCIDENT_SUMMARY",

            "context":
                "OWNER_ABSENCE"
        },

        {
            "question":
                "What happened between 2pm and 6pm?",

            "intent":
                "INCIDENT_SUMMARY",

            "clock":
                {
                    "start":
                        "14:00",

                    "end":
                        "18:00"
                }
        }
    ]

    results = []

    passed = True

    for test in tests:

        routed = route_question(
            test[
                "question"
            ]
        )

        ok = (
            routed[
                "intent"
            ]
            ==
            test[
                "intent"
            ]
        )

        if "time" in test:

            ok = (
                ok
                and
                routed[
                    "time_range"
                ]
                ==
                test[
                    "time"
                ]
            )

        if "context" in test:

            ok = (
                ok
                and
                routed[
                    "presence_context"
                ]
                ==
                test[
                    "context"
                ]
            )

        if "clock" in test:

            ok = (
                ok
                and
                routed[
                    "explicit_clock"
                ]
                ==
                test[
                    "clock"
                ]
            )

        if not ok:

            passed = False

        results.append(
            {
                "question":
                    test[
                        "question"
                    ],

                "intent":
                    routed[
                        "intent"
                    ],

                "time":
                    routed[
                        "time_range"
                    ],

                "context":
                    routed[
                        "presence_context"
                    ],

                "clock":
                    routed[
                        "explicit_clock"
                    ],

                "passed":
                    ok
            }
        )

    return {

        "status":
            (
                "PASS"
                if passed
                else
                "PARTIAL"
            ),

        "version":
            SEMANTIC_VERSION,

        "tests":
            results
    }