# ============================================================
# SENTINEL PHOENIX
# LOCAL LLM BRAIN ADAPTER V1.1
#
# Optimized for Qwen3 4B / Ollama
# ============================================================

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


BRAIN_LLM_VERSION = "1.1"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"

OLLAMA_MODEL = "qwen3:4b"

DEFAULT_TIMEOUT = 120


SYSTEM_PROMPT = """
You are Sentinel Phoenix's local reasoning engine.

You are a defensive cybersecurity assistant.

STRICT RULES:

1. Never invent incidents, IP addresses, locations, malware,
   alerts, timestamps, vulnerabilities, users or system state.

2. Security facts must come from verified context supplied by
   Sentinel Phoenix.

3. If information is missing, explicitly say that there is not
   enough verified information.

4. Never claim that an action was executed unless Sentinel
   explicitly reports that it was executed.

5. Never execute operating-system commands.

6. Never bypass Sentinel permissions or Identity Guard.

7. Sentinel deterministic components remain authoritative.

8. You may summarize events, explain risks, correlate supplied
   observations and recommend defensive actions.

9. Respond in the user's language whenever practical.

10. Keep normal answers concise.
""".strip()


def _safe_text(value: Any) -> str:

    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    except Exception:
        return str(value)


def ollama_available(
    timeout: float = 3.0,
) -> bool:

    try:

        request = urllib.request.Request(
            OLLAMA_TAGS_URL,
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:

            return 200 <= response.status < 300

    except Exception:
        return False


def model_available(
    model: str = OLLAMA_MODEL,
    timeout: float = 5.0,
) -> bool:

    try:

        request = urllib.request.Request(
            OLLAMA_TAGS_URL,
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:

            payload = json.loads(
                response.read().decode("utf-8")
            )

        for item in payload.get("models", []):

            name = str(
                item.get("name", "")
            )

            if name == model:
                return True

        return False

    except Exception:
        return False


def build_context_message(
    user_message: str,
    sentinel_context: Optional[Any] = None,
) -> str:

    user_message = _safe_text(
        user_message
    )

    context = _safe_text(
        sentinel_context
    )

    if not context:
        return user_message

    return (
        "VERIFIED SENTINEL CONTEXT:\n"
        "--------------------------\n"
        f"{context}\n\n"
        "USER REQUEST:\n"
        "-------------\n"
        f"{user_message}"
    )


def chat(
    user_message: str,
    sentinel_context: Optional[Any] = None,
    conversation: Optional[
        List[Dict[str, str]]
    ] = None,
    model: str = OLLAMA_MODEL,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    if conversation:

        for item in conversation[-4:]:

            if not isinstance(item, dict):
                continue

            role = str(
                item.get("role", "")
            ).strip()

            content = _safe_text(
                item.get("content")
            )

            if (
                role in {
                    "user",
                    "assistant",
                }
                and content
            ):
                messages.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )

    messages.append(
        {
            "role": "user",
            "content": build_context_message(
                user_message,
                sentinel_context,
            ),
        }
    )

    body = {
        "model": model,
        "messages": messages,
        "stream": False,

        # Qwen3 reasoning mode disabled for normal Sentinel
        # responses to reduce latency and RAM usage.
        "think": False,

        "keep_alive": "5m",

        "options": {
            "temperature": 0.2,
            "num_ctx": 2048,
            "num_predict": 256,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(
            body,
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Content-Type":
                "application/json"
        },
        method="POST",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:

            payload = json.loads(
                response.read().decode("utf-8")
            )

        message = payload.get(
            "message",
            {},
        )

        content = _safe_text(
            message.get("content")
        )

        if not content:

            return {
                "ok": False,
                "provider": "ollama",
                "model": model,
                "error": "EMPTY_RESPONSE",
                "response": "",
            }

        return {
            "ok": True,
            "provider": "ollama",
            "model": model,
            "response": content,
            "done": bool(
                payload.get("done", False)
            ),
        }

    except urllib.error.HTTPError as error:

        try:
            detail = (
                error.read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )
        except Exception:
            detail = str(error)

        return {
            "ok": False,
            "provider": "ollama",
            "model": model,
            "error": "HTTP_ERROR",
            "detail": detail,
            "response": "",
        }

    except urllib.error.URLError as error:

        return {
            "ok": False,
            "provider": "ollama",
            "model": model,
            "error": "OLLAMA_UNAVAILABLE",
            "detail": str(error),
            "response": "",
        }

    except TimeoutError:

        return {
            "ok": False,
            "provider": "ollama",
            "model": model,
            "error": "TIMEOUT",
            "response": "",
        }

    except Exception as error:

        return {
            "ok": False,
            "provider": "ollama",
            "model": model,
            "error": "LLM_FAILURE",
            "detail": repr(error),
            "response": "",
        }


def answer(
    user_message: str,
    sentinel_context: Optional[Any] = None,
    conversation: Optional[
        List[Dict[str, str]]
    ] = None,
) -> Optional[str]:

    result = chat(
        user_message=user_message,
        sentinel_context=sentinel_context,
        conversation=conversation,
    )

    if not result.get("ok", False):
        return None

    response = _safe_text(
        result.get("response")
    )

    return response or None


def self_test() -> Dict[str, Any]:

    ollama_ok = ollama_available()

    model_ok = (
        model_available()
        if ollama_ok
        else False
    )

    result = {
        "status": (
            "PASS"
            if ollama_ok and model_ok
            else "FAIL"
        ),
        "version": BRAIN_LLM_VERSION,
        "provider": "ollama",
        "model": OLLAMA_MODEL,
        "ollama_available": ollama_ok,
        "model_available": model_ok,
    }

    if ollama_ok and model_ok:

        test = chat(
            "Réponds uniquement : SENTINEL BRAIN ONLINE"
        )

        result["generation_ok"] = bool(
            test.get("ok", False)
        )

        result["response"] = test.get(
            "response",
            "",
        )

        if not result["generation_ok"]:
            result["status"] = "FAIL"

    return result


if __name__ == "__main__":

    print(
        json.dumps(
            self_test(),
            ensure_ascii=False,
            indent=2,
        )
    )
