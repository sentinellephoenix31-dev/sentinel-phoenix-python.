# ============================================================
# SENTINEL PHOENIX
# GLOBE NARRATION BRIDGE V1.2
#
# PRIORITY AI EDITION
#
# Automatic narration:
#     lightweight deterministic TTS
#
# AI ANALYZE:
#     strict priority
#     Qwen3:4b
#     automatic narration temporarily suppressed
#
# The AI request can no longer be overwritten by
# automatic Globe narration events.
# ============================================================

import queue
import threading
from typing import Any, Dict, Optional


BRIDGE_VERSION = "1.2"


class GlobeNarrationBridge:

    def __init__(
        self,
        language: str = "fr",
    ):

        self.language = (
            "fr"
            if str(language).lower() == "fr"
            else "en"
        )

        # ----------------------------------------------------
        # Separate queues.
        #
        # AI has its own queue and therefore cannot be
        # removed/replaced by automatic narration.
        # ----------------------------------------------------

        self._ai_queue = queue.Queue(
            maxsize=1
        )

        self._auto_queue = queue.Queue(
            maxsize=1
        )

        self._running = True

        self._ai_pending = threading.Event()

        self._last_auto_key = None

        self._worker = threading.Thread(
            target=self._run,
            name="sentinel-globe-narration-v1.2",
            daemon=True,
        )

        self._worker.start()

        print(
            "[GLOBE BRIDGE V1.2] ONLINE",
            flush=True,
        )


    # ========================================================
    # EVENT KEY
    # ========================================================

    def _event_key(
        self,
        incident: Dict[str, Any],
    ) -> str:

        return "|".join(
            [
                str(
                    incident.get(
                        "index",
                        "",
                    )
                ),
                str(
                    incident.get(
                        "timestamp",
                        "",
                    )
                ),
                str(
                    incident.get(
                        "source_ip",
                        "",
                    )
                ),
                str(
                    incident.get(
                        "type",
                        "",
                    )
                ),
            ]
        )


    # ========================================================
    # AUTOMATIC LIGHT NARRATION
    # ========================================================

    def narrate(
        self,
        incident: Dict[str, Any],
    ) -> bool:

        if not isinstance(
            incident,
            dict,
        ):
            return False

        # ----------------------------------------------------
        # AI always has priority.
        #
        # While an AI request is queued/running,
        # automatic narrations are ignored.
        # ----------------------------------------------------

        if self._ai_pending.is_set():

            print(
                "[GLOBE BRIDGE V1.2] "
                "Auto narration skipped: AI priority active.",
                flush=True,
            )

            return False

        key = self._event_key(
            incident
        )

        if (
            key
            and key == self._last_auto_key
        ):
            return False

        self._last_auto_key = key

        # Keep only newest automatic narration.
        try:

            while True:
                self._auto_queue.get_nowait()

        except queue.Empty:
            pass

        try:

            self._auto_queue.put_nowait(
                dict(incident)
            )

            return True

        except queue.Full:
            return False


    # ========================================================
    # EXPLICIT AI ANALYSIS
    # ========================================================

    def analyze(
        self,
        incident: Dict[str, Any],
    ) -> bool:

        if not isinstance(
            incident,
            dict,
        ):
            return False

        # ----------------------------------------------------
        # Lock automatic narration immediately.
        # ----------------------------------------------------

        self._ai_pending.set()

        # Remove any old AI request.
        try:

            while True:
                self._ai_queue.get_nowait()

        except queue.Empty:
            pass

        # Remove pending automatic narration.
        try:

            while True:
                self._auto_queue.get_nowait()

        except queue.Empty:
            pass

        try:

            self._ai_queue.put_nowait(
                dict(incident)
            )

            print(
                "[GLOBE AI] REQUEST QUEUED:",
                incident.get(
                    "source_ip",
                    "UNKNOWN",
                ),
                incident.get(
                    "level",
                    "UNKNOWN",
                ),
                flush=True,
            )

            return True

        except queue.Full:

            self._ai_pending.clear()

            return False


    # ========================================================
    # STOP
    # ========================================================

    def stop(
        self,
    ):

        self._running = False

        self._ai_pending.clear()

        print(
            "[GLOBE BRIDGE V1.2] STOPPED",
            flush=True,
        )


    # ========================================================
    # WORKER
    # ========================================================

    def _run(
        self,
    ):

        while self._running:

            # ------------------------------------------------
            # 1. AI ALWAYS FIRST
            # ------------------------------------------------

            try:

                incident = (
                    self._ai_queue
                    .get_nowait()
                )

                print(
                    "[GLOBE AI] WORKER STARTING QWEN",
                    flush=True,
                )

                try:

                    self._narrate_with_ai(
                        incident
                    )

                finally:

                    self._ai_pending.clear()

                    print(
                        "[GLOBE AI] WORKER FINISHED",
                        flush=True,
                    )

                continue

            except queue.Empty:
                pass

            except Exception as error:

                self._ai_pending.clear()

                print(
                    "[GLOBE AI] Worker error:",
                    repr(error),
                    flush=True,
                )

                continue


            # ------------------------------------------------
            # 2. LIGHT NARRATION
            # ------------------------------------------------

            try:

                incident = (
                    self._auto_queue.get(
                        timeout=0.25
                    )
                )

            except queue.Empty:
                continue

            # AI may have arrived while we were waiting.
            if self._ai_pending.is_set():

                continue

            try:

                self._narrate_light(
                    incident
                )

            except Exception as error:

                print(
                    "[GLOBE NARRATION] Worker error:",
                    repr(error),
                    flush=True,
                )


    # ========================================================
    # LIGHTWEIGHT DETERMINISTIC TEXT
    # ========================================================

    def _light_text(
        self,
        incident: Dict[str, Any],
    ) -> str:

        source_ip = str(
            incident.get(
                "source_ip",
                "UNKNOWN",
            )
        )

        level = str(
            incident.get(
                "level",
                "UNKNOWN",
            )
        )

        event_type = str(
            incident.get(
                "type",
                "SECURITY_EVENT",
            )
        )

        action = str(
            incident.get(
                "action",
                "MONITOR",
            )
        )

        local = bool(
            incident.get(
                "local",
                False,
            )
        )

        has_geo = bool(
            incident.get(
                "has_geo",
                False,
            )
        )

        country = str(
            incident.get(
                "country",
                "UNKNOWN",
            )
        )


        if self.language == "fr":

            text = (
                f"Incident {event_type}. "
                f"Niveau de risque {level}. "
                f"Source {source_ip}. "
            )

            if local:

                text += (
                    "La source est locale ou loopback, "
                    "donc aucune géolocalisation publique "
                    "n'est attribuée. "
                )

            elif has_geo:

                text += (
                    "La géolocalisation IP approximative "
                    f"indique {country}. "
                )

            else:

                text += (
                    "La localisation de cette source "
                    "n'est pas disponible. "
                )

            text += (
                "Réponse défensive actuelle : "
                f"{action}."
            )

            return text


        text = (
            f"Security incident {event_type}. "
            f"Risk level {level}. "
            f"Source {source_ip}. "
        )

        if local:

            text += (
                "The source is local or loopback, "
                "so no public geolocation is assigned. "
            )

        elif has_geo:

            text += (
                "Approximate IP geolocation indicates "
                f"{country}. "
            )

        else:

            text += (
                "Source geolocation is unavailable. "
            )

        text += (
            "Current defensive action: "
            f"{action}."
        )

        return text


    # ========================================================
    # SPEAK
    # ========================================================

    def _speak(
        self,
        text: str,
    ):

        text = str(
            text
        ).strip()

        if not text:
            return

        print(
            "[GLOBE NARRATION]",
            text,
            flush=True,
        )

        try:

            from core.replay_narration import (
                speak_text,
            )

            speak_text(
                text,
                language=self.language,
            )

            return

        except Exception as error:

            print(
                "[GLOBE NARRATION] "
                "Replay TTS fallback:",
                repr(error),
                flush=True,
            )

        try:

            from core.voice import (
                speak,
            )

            speak(
                text,
                language=self.language,
                wait=True,
            )

        except Exception as error:

            print(
                "[GLOBE NARRATION] "
                "Voice unavailable:",
                repr(error),
                flush=True,
            )


    # ========================================================
    # LIGHT NARRATION
    # ========================================================

    def _narrate_light(
        self,
        incident: Dict[str, Any],
    ):

        self._speak(
            self._light_text(
                incident
            )
        )


    # ========================================================
    # QWEN AI ANALYSIS
    # ========================================================

    def _narrate_with_ai(
        self,
        incident: Dict[str, Any],
    ):

        print(
            "[GLOBE AI] Importing Sentinel Brain...",
            flush=True,
        )

        response: Optional[str] = None


        if self.language == "fr":

            request = (
                "Analyse cet incident de cybersécurité "
                "en deux ou trois phrases maximum. "
                "Explique pourquoi il est important et "
                "ce que signifie la réponse défensive. "
                "Utilise uniquement les faits vérifiés "
                "contenus dans le contexte Sentinel. "
                "N'invente aucune attaque, adresse IP, "
                "localisation, vulnérabilité ou action."
            )

        else:

            request = (
                "Analyze this cybersecurity incident "
                "in no more than two or three sentences. "
                "Explain why it matters and what the "
                "defensive response means. "
                "Use only verified facts supplied in "
                "the Sentinel context. "
                "Do not invent attacks, IP addresses, "
                "locations, vulnerabilities or actions."
            )


        # ----------------------------------------------------
        # PRIMARY BRAIN API
        # ----------------------------------------------------

        try:

            from core.brain import (
                answer_with_ai,
            )

            print(
                "[GLOBE AI] Calling answer_with_ai()...",
                flush=True,
            )

            response = answer_with_ai(
                request,
                sentinel_context=incident,
            )

            print(
                "[GLOBE AI] "
                "answer_with_ai() returned.",
                flush=True,
            )

        except Exception as error:

            print(
                "[GLOBE AI] "
                "Primary Brain API failed:",
                repr(error),
                flush=True,
            )


        # ----------------------------------------------------
        # DIRECT BRAIN_LLM FALLBACK
        # ----------------------------------------------------

        if not response:

            try:

                from core.brain_llm import (
                    answer,
                )

                print(
                    "[GLOBE AI] "
                    "Trying brain_llm.answer() fallback...",
                    flush=True,
                )

                response = answer(
                    request,
                    sentinel_context=incident,
                )

            except Exception as error:

                print(
                    "[GLOBE AI] "
                    "brain_llm fallback failed:",
                    repr(error),
                    flush=True,
                )


        # ----------------------------------------------------
        # LAST SAFE FALLBACK
        # ----------------------------------------------------

        if not response:

            print(
                "[GLOBE AI] "
                "No AI response. "
                "Using deterministic fallback.",
                flush=True,
            )

            response = self._light_text(
                incident
            )


        # Some APIs may return dictionaries.
        if isinstance(
            response,
            dict,
        ):

            response = (
                response.get(
                    "response"
                )
                or
                response.get(
                    "answer"
                )
                or
                response.get(
                    "content"
                )
                or
                str(response)
            )


        response = str(
            response
        ).strip()


        print(
            "[GLOBE AI] RESPONSE READY:",
            response,
            flush=True,
        )


        self._speak(
            response
        )


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    return {
        "status":
            "PASS",

        "version":
            BRIDGE_VERSION,

        "automatic_mode":
            "DETERMINISTIC_TTS",

        "ai_mode":
            "STRICT_PRIORITY_QWEN",

        "separate_ai_queue":
            True,

        "auto_cannot_replace_ai":
            True,

        "qwen_auto_load":
            False,

        "brain_api":
            "core.brain.answer_with_ai",

        "brain_fallback":
            "core.brain_llm.answer",

        "worker_thread":
            True,

        "ui_blocking":
            False,
    }


if __name__ == "__main__":

    import json

    print(
        json.dumps(
            self_test(),
            ensure_ascii=False,
            indent=2,
        )
    )
