# ============================================================
# SENTINEL PHOENIX
# BRAIN CONVERSATION V2.0
#
# Existing BrainConversation preserved as LEGACY engine.
#
# Architecture:
#
# Dispatcher
#    ↓
# BrainConversation V2
#    ├── Internet / control requests -> Legacy engine
#    ├── General questions -> Brain V2 / Qwen3 4B
#    └── Qwen unavailable -> Legacy fallback
#
# Existing history and safety structure are preserved.
# ============================================================

from typing import Any, Dict

from core import brain_conversation_legacy as _legacy
from core.brain_conversation_legacy import *

try:
    from core.brain import (
        answer_with_ai,
        llm_status,
        BRAIN_VERSION,
    )

    AI_BRAIN_AVAILABLE = True

except Exception:
    answer_with_ai = None
    llm_status = None
    BRAIN_VERSION = "UNAVAILABLE"
    AI_BRAIN_AVAILABLE = False


BRAIN_CONVERSATION_VERSION = "2.0-QWEN"


# Keep exact original method.
_LEGACY_ANSWER = _legacy.BrainConversation.answer


def _safe_text(value: Any) -> str:

    if value is None:
        return ""

    return str(value).strip()


def _is_external_result(result: Any) -> bool:

    if not isinstance(result, dict):
        return False

    if bool(
        result.get(
            "external",
            False,
        )
    ):
        return True

    route = str(
        result.get(
            "route",
            "",
        )
    ).upper()

    return route == "INTERNET"


def _keep_legacy_primary(
    question: str,
    legacy_result: Any,
) -> bool:

    """
    Commands already handled well by the deterministic
    conversation engine stay on that engine.
    """

    text = _safe_text(
        question
    ).lower()

    # Internet/NVD/NIST result remains authoritative.
    if _is_external_result(
        legacy_result
    ):
        return True

    control_phrases = (
        "help",
        "aide",
        "status",
        "statut",
        "system status",
        "sentinel status",
        "close conversation",
        "end conversation",
        "quit",
        "exit",
        "bye",
        "au revoir",
    )

    for phrase in control_phrases:

        if phrase in text:
            return True

    return False


def _update_result(
    legacy_result: Any,
    ai_response: str,
) -> Dict[str, Any]:

    """
    Preserve the old result structure and replace only
    the human-readable response.
    """

    if isinstance(
        legacy_result,
        dict,
    ):

        result = dict(
            legacy_result
        )

    else:

        result = {
            "status": "ANSWERED",
            "continue": True,
        }

    result[
        "response"
    ] = ai_response

    result[
        "llm_used"
    ] = True

    result[
        "llm_provider"
    ] = "ollama"

    result[
        "llm_model"
    ] = "qwen3:4b"

    result[
        "brain_version"
    ] = BRAIN_VERSION

    result[
        "conversation_version"
    ] = (
        BRAIN_CONVERSATION_VERSION
    )

    return result


class BrainConversation(
    _legacy.BrainConversation
):

    def answer(
        self,
        question,
    ):

        # ====================================================
        # STEP 1
        # Run existing deterministic conversation engine.
        #
        # This preserves:
        # - semantic analysis
        # - internet routing
        # - memory/history
        # - NVD/NIST
        # - safety metadata
        # ====================================================

        try:

            legacy_result = (
                _LEGACY_ANSWER(
                    self,
                    question,
                )
            )

        except Exception as error:

            legacy_result = {
                "status": "ERROR",
                "response": (
                    "Legacy conversational "
                    "engine error."
                ),
                "continue": True,
                "legacy_error": repr(
                    error
                ),
            }

        # ====================================================
        # STEP 2
        # Internet/control commands remain on legacy.
        # ====================================================

        if _keep_legacy_primary(
            question,
            legacy_result,
        ):

            return legacy_result

        # ====================================================
        # STEP 3
        # Check Qwen/Brain V2.
        # ====================================================

        if (
            not AI_BRAIN_AVAILABLE
            or
            answer_with_ai is None
        ):

            return legacy_result

        try:

            if llm_status is not None:

                status = llm_status()

                if not status.get(
                    "available",
                    False,
                ):

                    return legacy_result

        except Exception:

            return legacy_result

        # ====================================================
        # STEP 4
        # Ask Qwen3 4B.
        #
        # No unverified incident data are inserted here.
        # General knowledge questions can therefore be
        # answered normally.
        # ====================================================

        try:

            ai_response = (
                answer_with_ai(
                    question=str(
                        question
                    ),
                    sentinel_context=None,
                )
            )

        except Exception:

            ai_response = None

        if not ai_response:

            return legacy_result

        ai_response = str(
            ai_response
        ).strip()

        if not ai_response:

            return legacy_result

        # ====================================================
        # STEP 5
        # Preserve existing structure.
        # ====================================================

        result = _update_result(
            legacy_result,
            ai_response,
        )

        # ====================================================
        # STEP 6
        # Best-effort history correction.
        #
        # Legacy answer() may already have remembered its
        # original response. If its latest history item has
        # a response/answer field, replace that text with the
        # actual Qwen response.
        # ====================================================

        try:

            history = getattr(
                self,
                "history",
                None,
            )

            if (
                isinstance(
                    history,
                    list,
                )
                and history
            ):

                last = history[-1]

                if isinstance(
                    last,
                    dict,
                ):

                    if (
                        "response"
                        in last
                    ):
                        last[
                            "response"
                        ] = ai_response

                    if (
                        "answer"
                        in last
                    ):
                        last[
                            "answer"
                        ] = ai_response

        except Exception:
            pass

        return result


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    conversation = (
        BrainConversation()
    )

    result = conversation.answer(
        (
            "Explique brièvement "
            "ce qu'est une attaque "
            "par brute force."
        )
    )

    return {
        "status": (
            "PASS"
            if isinstance(
                result,
                dict,
            )
            else "FAIL"
        ),
        "conversation_version":
            BRAIN_CONVERSATION_VERSION,
        "brain_version":
            BRAIN_VERSION,
        "ai_module":
            AI_BRAIN_AVAILABLE,
        "result":
            result,
    }


if __name__ == "__main__":

    import json

    print(
        json.dumps(
            self_test(),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
