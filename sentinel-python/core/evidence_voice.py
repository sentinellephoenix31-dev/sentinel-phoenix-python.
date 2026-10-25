import os
import re
import unicodedata

from difflib import SequenceMatcher

from core.evidence_owner import (
    evidence_summary,
    owner_keep_evidence,
    owner_delete_evidence,
    owner_acknowledge_evidence
)

from core.voice import (
    record_audio,
    transcribe_audio,
    speak
)


# ============================================================
# SENTINEL PHOENIX
# EVIDENCE VOICE CONTROL V1
#
# Voice intentions:
#
# KEEP
# DELETE
# ACKNOWLEDGE
# STATUS
#
# Sensitive actions remain protected by:
#
# OWNER FACE + ACTIVE LIVENESS
# ============================================================


EVIDENCE_VOICE_VERSION = "1.0"

CONFIRMATION_LISTEN_SECONDS = 4


# ============================================================
# PHRASES
# ============================================================

KEEP_PHRASES = (
    "keep that photo",
    "keep this photo",
    "keep the photo",
    "keep that evidence",
    "save that photo",
    "preserve that photo",

    "garde cette photo",
    "garde la photo",
    "conserve cette photo",
    "conserve la photo",
    "garde cette preuve"
)


DELETE_PHRASES = (
    "delete that photo",
    "delete this photo",
    "delete the photo",
    "remove that photo",
    "erase that photo",
    "delete that evidence",

    "supprime cette photo",
    "supprime la photo",
    "efface cette photo",
    "efface la photo",
    "supprime cette preuve"
)


ACKNOWLEDGE_PHRASES = (
    "i have seen it",
    "ive seen it",
    "i saw it",
    "i have seen the photo",
    "acknowledge that photo",
    "mark it as seen",

    "je l ai vu",
    "je l ai vue",
    "j ai vu la photo",
    "j ai vu cette photo",
    "marque comme vu",
    "marque comme vue"
)


STATUS_PHRASES = (
    "evidence status",
    "show evidence status",
    "how many evidence photos",
    "how many unknown photos",
    "do we have evidence",

    "etat des preuves",
    "combien de preuves",
    "combien de photos inconnues",
    "avons nous des preuves"
)


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(text):

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

    text = re.sub(
        r"[^a-z0-9\s]",
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
# SIMILARITY
# ============================================================

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
# PHRASE MATCH
# ============================================================

def phrase_matches(
    text,
    phrases,
    fuzzy_threshold=0.84
):

    normalized = normalize_text(
        text
    )

    if not normalized:

        return False


    # Exact / contained phrase.

    for phrase in phrases:

        phrase_normalized = normalize_text(
            phrase
        )

        if phrase_normalized in normalized:

            return True


    # Fuzzy match for STT variations.

    for phrase in phrases:

        if (
            similarity(
                normalized,
                phrase
            )
            >=
            fuzzy_threshold
        ):

            return True


    return False


# ============================================================
# INTENT CLASSIFICATION
# ============================================================

def classify_evidence_intent(
    text
):

    normalized = normalize_text(
        text
    )


    if not normalized:

        return {
            "intent":
                None,

            "confidence":
                0.0
        }


    # ========================================================
    # DIRECT PHRASE MATCHES
    # ========================================================

    if phrase_matches(
        normalized,
        KEEP_PHRASES
    ):

        return {
            "intent":
                "KEEP",

            "confidence":
                1.0
        }


    if phrase_matches(
        normalized,
        DELETE_PHRASES
    ):

        return {
            "intent":
                "DELETE",

            "confidence":
                1.0
        }


    if phrase_matches(
        normalized,
        ACKNOWLEDGE_PHRASES
    ):

        return {
            "intent":
                "ACKNOWLEDGE",

            "confidence":
                1.0
        }


    if phrase_matches(
        normalized,
        STATUS_PHRASES
    ):

        return {
            "intent":
                "STATUS",

            "confidence":
                1.0
        }


    # ========================================================
    # TOKEN-BASED FALLBACK
    # ========================================================

    tokens = set(
        normalized.split()
    )


    photo_words = {
        "photo",
        "picture",
        "image",
        "evidence",
        "proof",
        "preuve"
    }


    keep_words = {
        "keep",
        "save",
        "preserve",
        "garde",
        "conserve"
    }


    delete_words = {
        "delete",
        "remove",
        "erase",
        "supprime",
        "efface"
    }


    seen_words = {
        "seen",
        "saw",
        "acknowledge",
        "vu",
        "vue"
    }


    evidence_context = bool(
        tokens
        &
        photo_words
    )


    if (
        evidence_context
        and
        tokens
        &
        keep_words
    ):

        return {
            "intent":
                "KEEP",

            "confidence":
                0.90
        }


    if (
        evidence_context
        and
        tokens
        &
        delete_words
    ):

        return {
            "intent":
                "DELETE",

            "confidence":
                0.90
        }


    if tokens & seen_words:

        return {
            "intent":
                "ACKNOWLEDGE",

            "confidence":
                0.85
        }


    return {
        "intent":
            None,

        "confidence":
            0.0
    }


# ============================================================
# PUBLIC INTENT CHECK
# ============================================================

def is_evidence_voice_request(
    text
):

    result = classify_evidence_intent(
        text
    )

    return (
        result.get(
            "intent"
        )
        is not None
    )


# ============================================================
# SPEAK SUMMARY
# ============================================================

def speak_evidence_summary(
    language="en"
):

    summary = evidence_summary()

    total = int(
        summary.get(
            "total",
            0
        )
    )

    temporary = int(
        summary.get(
            "temporary",
            0
        )
    )

    kept = int(
        summary.get(
            "kept",
            0
        )
    )


    if str(
        language
    ).lower().startswith(
        "fr"
    ):

        message = (
            f"J'ai {total} preuve photo au total. "
            f"{temporary} sont temporaires et "
            f"{kept} sont conservées."
        )

    else:

        message = (
            f"I have {total} evidence photos in total. "
            f"{temporary} are temporary and "
            f"{kept} are preserved."
        )


    speak(
        message,
        language
    )


    return summary


# ============================================================
# DELETE CONFIRMATION
#
# Voice confirmation occurs BEFORE owner biometric
# authorization and destructive deletion.
# ============================================================

def confirm_delete(
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

        speak(
            (
                "Cette action supprimera la dernière "
                "preuve photo. "
                "Dites confirmer suppression pour continuer."
            ),
            "fr"
        )

    else:

        speak(
            (
                "This will delete the latest evidence photo. "
                "Say confirm delete to continue."
            ),
            "en"
        )


    audio_path = None


    try:

        audio_path = record_audio(
            CONFIRMATION_LISTEN_SECONDS
        )


        transcription = transcribe_audio(
            audio_path
        )


        answer = normalize_text(
            transcription.get(
                "text",
                ""
            )
        )


        confirmations = (
            "confirm delete",
            "confirm deletion",
            "yes delete",
            "confirmer suppression",
            "confirme suppression",
            "oui supprime"
        )


        confirmed = any(
            normalize_text(
                phrase
            )
            in
            answer

            for phrase in confirmations
        )


        return {
            "confirmed":
                confirmed,

            "transcription":
                answer
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
# EXECUTE VOICE ACTION
# ============================================================

def execute_evidence_voice_action(
    text,
    language="en"
):

    language = str(
        language
        or
        "en"
    ).lower()


    classification = (
        classify_evidence_intent(
            text
        )
    )


    intent = classification.get(
        "intent"
    )


    # ========================================================
    # NOT AN EVIDENCE COMMAND
    # ========================================================

    if intent is None:

        return {
            "status":
                "NOT_HANDLED",

            "reason":
                "NO_EVIDENCE_INTENT"
        }


    # ========================================================
    # STATUS
    # ========================================================

    if intent == "STATUS":

        return speak_evidence_summary(
            language
        )


    # ========================================================
    # KEEP
    # ========================================================

    if intent == "KEEP":

        if language.startswith(
            "fr"
        ):

            speak(
                (
                    "Je vais vérifier votre identité "
                    "avant de conserver cette preuve."
                ),
                "fr"
            )

        else:

            speak(
                (
                    "I will verify your identity "
                    "before preserving this evidence."
                ),
                "en"
            )


        result = owner_keep_evidence()


        if result.get(
            "status"
        ) == "KEPT":

            if language.startswith(
                "fr"
            ):

                speak(
                    "La preuve a été conservée.",
                    "fr"
                )

            else:

                speak(
                    "The evidence has been preserved.",
                    "en"
                )


        return result


    # ========================================================
    # DELETE
    # ========================================================

    if intent == "DELETE":

        confirmation = confirm_delete(
            language
        )


        if not confirmation.get(
            "confirmed"
        ):

            if language.startswith(
                "fr"
            ):

                speak(
                    "Suppression annulée.",
                    "fr"
                )

            else:

                speak(
                    "Deletion cancelled.",
                    "en"
                )


            return {
                "status":
                    "CANCELLED",

                "action":
                    "DELETE",

                "reason":
                    "VOICE_CONFIRMATION_FAILED"
            }


        if language.startswith(
            "fr"
        ):

            speak(
                (
                    "Confirmation reçue. "
                    "Je dois maintenant vérifier "
                    "le propriétaire."
                ),
                "fr"
            )

        else:

            speak(
                (
                    "Confirmation received. "
                    "I must now verify the owner."
                ),
                "en"
            )


        result = owner_delete_evidence()


        if result.get(
            "status"
        ) == "DELETED":

            if language.startswith(
                "fr"
            ):

                speak(
                    "La preuve a été supprimée.",
                    "fr"
                )

            else:

                speak(
                    "The evidence has been deleted.",
                    "en"
                )


        return result


    # ========================================================
    # ACKNOWLEDGE
    #
    # NOTE:
    # Evidence Lifecycle may delete temporary evidence after
    # acknowledgment unless it was previously marked KEEP.
    # ========================================================

    if intent == "ACKNOWLEDGE":

        if language.startswith(
            "fr"
        ):

            speak(
                (
                    "Je vais vérifier votre identité "
                    "avant de marquer cette preuve comme vue."
                ),
                "fr"
            )

        else:

            speak(
                (
                    "I will verify your identity "
                    "before acknowledging this evidence."
                ),
                "en"
            )


        result = (
            owner_acknowledge_evidence()
        )


        status = result.get(
            "status"
        )


        if language.startswith(
            "fr"
        ):

            if status == "DELETED":

                speak(
                    (
                        "Preuve vue. "
                        "La copie temporaire a été supprimée."
                    ),
                    "fr"
                )

            elif status == "ACKNOWLEDGED":

                speak(
                    (
                        "Preuve marquée comme vue "
                        "et conservée."
                    ),
                    "fr"
                )

        else:

            if status == "DELETED":

                speak(
                    (
                        "Evidence acknowledged. "
                        "The temporary copy was deleted."
                    ),
                    "en"
                )

            elif status == "ACKNOWLEDGED":

                speak(
                    (
                        "Evidence acknowledged "
                        "and preserved."
                    ),
                    "en"
                )


        return result


    return {
        "status":
            "NOT_HANDLED"
    }


# ============================================================
# SELF TEST
#
# No camera.
# No liveness.
# No evidence is changed.
# ============================================================

def self_test():

    tests = {

        "keep_english":
            classify_evidence_intent(
                "Keep that photo"
            ).get(
                "intent"
            )
            ==
            "KEEP",

        "keep_french":
            classify_evidence_intent(
                "Garde cette photo"
            ).get(
                "intent"
            )
            ==
            "KEEP",

        "delete_english":
            classify_evidence_intent(
                "Delete that photo"
            ).get(
                "intent"
            )
            ==
            "DELETE",

        "delete_french":
            classify_evidence_intent(
                "Supprime cette photo"
            ).get(
                "intent"
            )
            ==
            "DELETE",

        "seen_english":
            classify_evidence_intent(
                "I've seen it"
            ).get(
                "intent"
            )
            ==
            "ACKNOWLEDGE",

        "seen_french":
            classify_evidence_intent(
                "Je l'ai vue"
            ).get(
                "intent"
            )
            ==
            "ACKNOWLEDGE",

        "status_english":
            classify_evidence_intent(
                "Evidence status"
            ).get(
                "intent"
            )
            ==
            "STATUS",

        "normal_question_rejected":
            not is_evidence_voice_request(
                "What happened today?"
            )
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
            EVIDENCE_VOICE_VERSION,

        "tests":
            tests,

        "supported_actions": [
            "KEEP",
            "DELETE",
            "ACKNOWLEDGE",
            "STATUS"
        ],

        "security": {

            "delete_voice_confirmation":
                True,

            "owner_face_for_changes":
                True,

            "owner_liveness_for_changes":
                True,

            "unknown_can_control_evidence":
                False,

            "guest_can_control_evidence":
                False,

            "arbitrary_path_control":
                False,

            "shell_execution":
                False,

            "payload_execution":
                False
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