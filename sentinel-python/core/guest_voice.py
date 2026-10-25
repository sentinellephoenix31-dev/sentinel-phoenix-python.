import os
import re
import unicodedata

from difflib import SequenceMatcher

from core.guest_access import (
    secure_enroll_guest
)

from core.voice import (
    record_audio,
    transcribe_audio,
    speak
)


# ============================================================
# SENTINEL PHOENIX
# GUEST VOICE ENROLLMENT CORE V1.1
#
# ROBUST NATURAL LANGUAGE INTENT
#
# Handles:
# - accents
# - speech-to-text variations
# - imperfect English
# - French
# - short commands
# ============================================================


GUEST_VOICE_VERSION = "1.1"

NAME_LISTEN_SECONDS = 5

MAX_NAME_LENGTH = 40


# ============================================================
# STRONG PHRASES
# ============================================================

GUEST_PHRASES = (

    # English

    "this person is my guest",
    "this is my guest",
    "he is my guest",
    "she is my guest",
    "they are my guest",

    "add guest",
    "add a guest",
    "add this guest",
    "add this person as guest",

    "register guest",
    "register a guest",
    "register this guest",
    "register this person as guest",

    "enroll guest",
    "enroll a guest",
    "enroll this person",

    "save this person as guest",
    "remember this person as guest",
    "mark this person as guest",

    # Common transcription variations

    "ten person is my guest",
    "the person is my guest",
    "dis person is my guest",
    "this person is my guess",
    "this is my guess",

    # French

    "cette personne est mon invite",
    "c est mon invite",
    "lui c est mon invite",
    "elle c est mon invitee",

    "ajoute un invite",
    "ajouter un invite",
    "ajoute cette personne comme invite",

    "enregistre un invite",
    "enregistrer un invite",
    "enregistre cette personne comme invite",

    "memorise cette personne comme invite",
    "cette personne est une invitee"
)


# ============================================================
# KEYWORDS
# ============================================================

GUEST_WORDS = {
    "guest",
    "guests",
    "visitor",
    "visiteur",
    "invite",
    "invitee"
}


ACTION_WORDS = {
    "add",
    "register",
    "enroll",
    "save",
    "remember",
    "mark",

    "ajoute",
    "ajouter",
    "enregistre",
    "enregistrer",
    "memorise",
    "memoriser"
}


PERSON_WORDS = {
    "person",
    "this",
    "he",
    "she",
    "they",
    "him",
    "her",
    "my",

    "personne",
    "lui",
    "elle",
    "mon",
    "ma",
    "cette"
}


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(
    text
):

    text = str(
        text
    ).strip().lower()

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(
            character
        )
    )

    text = (
        text
        .replace(
            "'",
            " "
        )
        .replace(
            "’",
            " "
        )
    )

    # Convert spoken/recognized number 10
    # into a useful approximation.
    #
    # Example:
    # "10 person is my guest"
    # remains detectable through guest/person logic.

    text = re.sub(
        r"[^a-z0-9\s_-]",
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
# TOKEN HELPERS
# ============================================================

def text_tokens(
    text
):

    return set(
        normalize_text(
            text
        ).split()
    )


def similarity(
    first,
    second
):

    return SequenceMatcher(
        None,
        normalize_text(
            first
        ),
        normalize_text(
            second
        )
    ).ratio()


# ============================================================
# FUZZY GUEST WORD
# ============================================================

def fuzzy_guest_word_present(
    tokens
):

    for token in tokens:

        for guest_word in (
            "guest",
            "invite",
            "invitee"
        ):

            score = SequenceMatcher(
                None,
                token,
                guest_word
            ).ratio()

            # Helps with STT errors such as:
            # guest -> guess

            if score >= 0.80:

                return True

    return False


# ============================================================
# INTENT DETECTION
# ============================================================

def is_guest_enrollment_request(
    question
):

    normalized = normalize_text(
        question
    )

    if not normalized:

        return False


    # ========================================================
    # 1. DIRECT PHRASE
    # ========================================================

    for phrase in GUEST_PHRASES:

        if (
            phrase
            in
            normalized
        ):

            return True


    # ========================================================
    # 2. FUZZY PHRASE MATCH
    # ========================================================

    for phrase in GUEST_PHRASES:

        if (
            similarity(
                normalized,
                phrase
            )
            >=
            0.84
        ):

            return True


    # ========================================================
    # 3. SEMANTIC TOKEN RULES
    # ========================================================

    tokens = text_tokens(
        normalized
    )


    guest_present = bool(
        tokens
        &
        GUEST_WORDS
    )


    # Handles "guest" -> "guess" etc.

    if not guest_present:

        guest_present = (
            fuzzy_guest_word_present(
                tokens
            )
        )


    action_present = bool(
        tokens
        &
        ACTION_WORDS
    )


    person_present = bool(
        tokens
        &
        PERSON_WORDS
    )


    # ========================================================
    # Example:
    #
    # "add guest"
    # "register my guest"
    # ========================================================

    if (
        guest_present
        and
        action_present
    ):

        return True


    # ========================================================
    # Example:
    #
    # "this person is my guest"
    # "he is my guest"
    # "ten person is my guest"
    # ========================================================

    if (
        guest_present
        and
        person_present
    ):

        return True


    return False


# ============================================================
# SAFE NAME CLEANUP
# ============================================================

def clean_guest_name(
    value
):

    value = str(
        value
    ).strip()

    if not value:

        return None


    normalized = normalize_text(
        value
    )


    patterns = (

        r"^his name is\s+",
        r"^her name is\s+",
        r"^their name is\s+",
        r"^the name is\s+",
        r"^name is\s+",

        r"^il s appelle\s+",
        r"^elle s appelle\s+",
        r"^son nom est\s+",
        r"^le nom est\s+",
        r"^c est\s+"
    )


    for pattern in patterns:

        normalized = re.sub(
            pattern,
            "",
            normalized,
            flags=re.IGNORECASE
        )


    normalized = normalized.strip()


    normalized = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        normalized
    )


    normalized = re.sub(
        r"_+",
        "_",
        normalized
    )


    normalized = normalized.strip(
        "_"
    )


    if not normalized:

        return None


    return normalized[
        :MAX_NAME_LENGTH
    ]


# ============================================================
# ASK FOR GUEST NAME
# ============================================================

def ask_guest_name(
    language="en"
):

    language = str(
        language
        or
        "en"
    ).lower()


    if language.startswith(
        "fr"
    ):

        prompt = (
            "Quel est le nom de cette personne ?"
        )

    else:

        prompt = (
            "What is this person's name?"
        )


    speak(
        prompt,
        language
    )


    audio_path = None


    try:

        audio_path = record_audio(
            NAME_LISTEN_SECONDS
        )


        transcription = transcribe_audio(
            audio_path
        )


        raw_name = str(
            transcription.get(
                "text",
                ""
            )
        ).strip()


        detected_language = (
            transcription.get(
                "language"
            )
        )


        guest_name = clean_guest_name(
            raw_name
        )


        return {

            "raw":
                raw_name,

            "name":
                guest_name,

            "language":
                detected_language
        }


    finally:

        if (
            audio_path
            and
            os.path.isfile(
                audio_path
            )
        ):

            try:

                os.remove(
                    audio_path
                )

            except OSError:

                pass


# ============================================================
# COMPLETE VOICE ENROLLMENT FLOW
# ============================================================

def run_guest_enrollment_voice(
    language="en"
):

    language = str(
        language
        or
        "en"
    ).lower()


    # ========================================================
    # ASK NAME
    # ========================================================

    name_result = ask_guest_name(
        language
    )


    guest_name = name_result.get(
        "name"
    )


    if not guest_name:

        if language.startswith(
            "fr"
        ):

            response = (
                "Je n'ai pas compris le nom. "
                "L'enregistrement de l'invité est annulé."
            )

        else:

            response = (
                "I could not understand the name. "
                "Guest enrollment has been cancelled."
            )


        speak(
            response,
            language
        )


        return {

            "status":
                "CANCELLED",

            "reason":
                "GUEST_NAME_NOT_UNDERSTOOD"
        }


    # ========================================================
    # CONFIRM INTENTION
    # ========================================================

    if language.startswith(
        "fr"
    ):

        response = (
            f"D'accord. "
            f"Je vais enregistrer {guest_name} "
            "comme invité. "
            "Je dois d'abord vérifier le propriétaire."
        )

    else:

        response = (
            f"Okay. "
            f"I will register {guest_name} "
            "as a guest. "
            "I must verify the owner first."
        )


    speak(
        response,
        language
    )


    # ========================================================
    # OWNER FACE + LIVENESS + GUEST CAPTURE
    # ========================================================

    try:

        result = secure_enroll_guest(
            guest_name
        )


    except Exception as error:

        result = {

            "status":
                "DENIED",

            "reason":
                str(
                    error
                )
        }


    # ========================================================
    # RESULT
    # ========================================================

    if (
        result.get(
            "status"
        )
        ==
        "GUEST_ENROLLED"
    ):

        if language.startswith(
            "fr"
        ):

            response = (
                f"{guest_name} est maintenant "
                "enregistré comme invité. "
                "Ses permissions sont limitées."
            )

        else:

            response = (
                f"{guest_name} is now registered "
                "as a guest. "
                "Guest permissions are limited."
            )


    else:

        reason = result.get(
            "reason",
            "UNKNOWN"
        )


        if language.startswith(
            "fr"
        ):

            response = (
                "Je n'ai pas autorisé "
                "l'enregistrement de l'invité. "
                f"Raison : {reason}."
            )

        else:

            response = (
                "I did not authorize guest enrollment. "
                f"Reason: {reason}."
            )


    speak(
        response,
        language
    )


    return result


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    positive_tests = (

        "this person is my guest",

        "ten person is my guest",

        "this person is my guess",

        "this is my guest",

        "he is my guest",

        "she is my guest",

        "add guest",

        "register guest",

        "please register this person as guest",

        "cette personne est mon invité",

        "lui c'est mon invité",

        "ajoute un invité",

        "enregistre cette personne comme invité"
    )


    positive_results = {

        text:
            is_guest_enrollment_request(
                text
            )

        for text in positive_tests
    }


    negative_tests = (

        "what happened today",

        "what happened this week",

        "tell me about the security system",

        "what is my risk score"
    )


    negative_results = {

        text:
            not is_guest_enrollment_request(
                text
            )

        for text in negative_tests
    }


    passed = (
        all(
            positive_results.values()
        )
        and
        all(
            negative_results.values()
        )
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
            GUEST_VOICE_VERSION,

        "positive_tests":
            positive_results,

        "negative_tests":
            negative_results,

        "recommended_short_commands":
            [

                "add guest",

                "register guest",

                "ajoute un invite"
            ],

        "safety":
            {

                "guest_self_authorization":
                    False,

                "owner_required":
                    True,

                "owner_liveness_required":
                    True,

                "shell_execution":
                    False,

                "payload_execution":
                    False
            }
    }


# ============================================================
# MANUAL TEST
# ============================================================

if __name__ == "__main__":

    import pprint

    pprint.pp(
        self_test()
    )