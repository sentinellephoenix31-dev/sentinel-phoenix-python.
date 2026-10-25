# ============================================================
# SENTINEL PHOENIX
# AI BRAIN V2.0
#
# Architecture:
#
#   Existing deterministic Brain V1
#              +
#         Qwen3 8B
#
# The deterministic Brain remains authoritative.
# Qwen is used only for reasoning/explanation over verified
# Sentinel context.
#
# If Ollama/Qwen fails:
#     automatic fallback -> Brain V1
# ============================================================


from typing import Any, Dict


# ============================================================
# LEGACY BRAIN
# ============================================================

from core import brain_legacy as _legacy
from core.brain_legacy import *


# Save original functions BEFORE monkey-patching.
_LEGACY_ANSWER_INCIDENT = (
    _legacy.answer_incident_question
)

_LEGACY_SELF_TEST = (
    _legacy.self_test
)


# ============================================================
# LOCAL LLM
# ============================================================

try:

    from core.brain_llm import (
        answer as _llm_answer,
        ollama_available,
        model_available,
        OLLAMA_MODEL,
    )

    LLM_MODULE_AVAILABLE = True

except Exception:

    _llm_answer = None

    LLM_MODULE_AVAILABLE = False

    OLLAMA_MODEL = "qwen3:8b"


# ============================================================
# VERSION
# ============================================================

BRAIN_VERSION = "2.0-QWEN"


# ============================================================
# HELPERS
# ============================================================

def _safe_bool_call(
    function,
    default=False,
):
    try:
        return bool(
            function()
        )

    except Exception:
        return default


def llm_status() -> Dict[str, Any]:

    if not LLM_MODULE_AVAILABLE:

        return {
            "available": False,
            "ollama": False,
            "model": False,
            "model_name":
                OLLAMA_MODEL,
            "reason":
                "BRAIN_LLM_IMPORT_FAILURE",
        }

    ollama_ok = _safe_bool_call(
        ollama_available
    )

    model_ok = False

    if ollama_ok:

        model_ok = _safe_bool_call(
            model_available
        )

    return {
        "available": (
            ollama_ok
            and model_ok
        ),
        "ollama": ollama_ok,
        "model": model_ok,
        "model_name":
            OLLAMA_MODEL,
        "reason": (
            "READY"
            if (
                ollama_ok
                and model_ok
            )
            else
            "LLM_UNAVAILABLE"
        ),
    }


# ============================================================
# VERIFIED CONTEXT
# ============================================================

def build_verified_context(
    question,
    reasoning,
    deterministic_answer,
):

    return {

        "source":
            "Sentinel Phoenix "
            "deterministic Brain V1",

        "user_question":
            str(
                question
                or ""
            ),

        "deterministic_answer":
            deterministic_answer,

        "reasoning":
            reasoning,

        "trust_policy": {

            "deterministic_brain":
                "AUTHORITATIVE",

            "llm":
                "EXPLANATION_ONLY",

            "invent_events":
                False,

            "invent_ip":
                False,

            "invent_location":
                False,

            "invent_actions":
                False,

        },
    }


# ============================================================
# QWEN ENHANCEMENT
# ============================================================

def enhance_with_llm(
    question,
    reasoning,
    deterministic_answer,
):

    if not LLM_MODULE_AVAILABLE:

        return None

    status = llm_status()

    if not status.get(
        "available",
        False,
    ):

        return None

    context = build_verified_context(
        question=question,
        reasoning=reasoning,
        deterministic_answer=(
            deterministic_answer
        ),
    )

    prompt = (
        "Answer the user's question using ONLY "
        "the verified Sentinel context supplied "
        "to you. "

        "The deterministic Sentinel answer and "
        "reasoning data are authoritative. "

        "You may explain them more naturally, "
        "connect the supplied facts, and make "
        "defensive recommendations, but you must "
        "not invent any incident, IP address, "
        "country, timestamp, action, malware, "
        "vulnerability, or system state. "

        "If information is missing, say that "
        "Sentinel does not currently have enough "
        "verified information. "

        "Do not claim that an action was executed "
        "unless the supplied context explicitly "
        "states that it was executed. "

        "Respond in the same language as the "
        "user whenever possible.\n\n"

        "USER QUESTION:\n"
        f"{question}"
    )

    try:

        response = _llm_answer(
            user_message=prompt,
            sentinel_context=context,
        )

    except Exception:

        return None

    if response is None:

        return None

    response = str(
        response
    ).strip()

    if not response:

        return None

    return response


# ============================================================
# INCIDENT QUESTION API
# ============================================================

def answer_incident_question(
    question,
    reasoning,
):

    # --------------------------------------------------------
    # STEP 1
    # Original deterministic Sentinel answer.
    # --------------------------------------------------------

    try:

        deterministic_answer = (
            _LEGACY_ANSWER_INCIDENT(
                question,
                reasoning,
            )
        )

    except Exception as error:

        deterministic_answer = (
            "Sentinel's deterministic "
            "incident analysis encountered "
            f"an error: {error}"
        )

    # --------------------------------------------------------
    # STEP 2
    # Ask Qwen to explain ONLY the verified context.
    # --------------------------------------------------------

    intelligent_answer = (
        enhance_with_llm(
            question=question,
            reasoning=reasoning,
            deterministic_answer=(
                deterministic_answer
            ),
        )
    )

    # --------------------------------------------------------
    # STEP 3
    # Qwen worked.
    # --------------------------------------------------------

    if intelligent_answer:

        return intelligent_answer

    # --------------------------------------------------------
    # STEP 4
    # Automatic Brain V1 fallback.
    # --------------------------------------------------------

    return deterministic_answer


# ============================================================
# GENERAL LOCAL REASONING API
# ============================================================

def answer_with_ai(
    question,
    sentinel_context=None,
):

    if not LLM_MODULE_AVAILABLE:

        return None

    status = llm_status()

    if not status.get(
        "available",
        False,
    ):

        return None

    try:

        return _llm_answer(
            user_message=str(
                question
                or ""
            ),
            sentinel_context=(
                sentinel_context
            ),
        )

    except Exception:

        return None


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    result = {

        "status":
            "PASS",

        "brain_version":
            BRAIN_VERSION,

        "architecture":
            "DETERMINISTIC_PLUS_LOCAL_LLM",

        "deterministic_brain":
            "AVAILABLE",

        "llm":
            llm_status(),

        "fallback":
            "ENABLED",

    }

    # --------------------------------------------------------
    # Legacy Brain self-test
    # --------------------------------------------------------

    try:

        legacy_result = (
            _LEGACY_SELF_TEST()
        )

        result[
            "legacy_self_test"
        ] = legacy_result

    except Exception as error:

        result[
            "legacy_self_test"
        ] = {
            "status":
                "ERROR",

            "error":
                repr(error),
        }

        result[
            "status"
        ] = "DEGRADED"

    # --------------------------------------------------------
    # The system is still operational without Qwen because
    # Brain V1 remains the fallback.
    # --------------------------------------------------------

    if not result[
        "llm"
    ].get(
        "available",
        False,
    ):

        result[
            "status"
        ] = "DEGRADED"

    return result


# ============================================================
# PATCH LEGACY MODULE
#
# If an older function inside brain_legacy references
# answer_incident_question() dynamically, it will now also use
# the V2 function.
# ============================================================

_legacy.answer_incident_question = (
    answer_incident_question
)


# ============================================================
# CLI TEST
# ============================================================

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
