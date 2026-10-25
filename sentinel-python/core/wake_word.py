import json
import os
import re
import threading
import time

import sounddevice as sd

from vosk import (
    KaldiRecognizer,
    Model,
    SetLogLevel
)

from core.command_dispatcher import (
    CommandDispatcher,
    self_test as dispatcher_self_test
)

from core.orb import (
    SentinelOrb
)

from core.voice import (
    record_audio,
    speak,
    speak_ready,
    transcribe_audio
)


# ============================================================
# SENTINEL PHOENIX
# WAKE WORD CORE V2.3
#
#                HEY SENTINEL
#                      ↓
#                 MICROPHONE
#                      ↓
#            SPEECH ENGINE FR / EN
#                      ↓
#              COMMAND DISPATCHER
#                      ↓
#       ┌────────┬─────┼─────┬────────┐
#       │        │     │     │
#   EVIDENCE   GUEST  REPLAY BRAIN
#
#
# TEXT and VOICE now share the same dispatcher.
#
# No shell execution.
# No attacker payload execution.
# ============================================================


WAKE_VERSION = "2.3"

SAMPLE_RATE = 16000

BLOCK_SIZE = 4000

QUESTION_SECONDS = 7

WAKE_COOLDOWN = 1.5


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)


WAKE_MODEL_PATH = os.path.join(
    BASE_DIR,
    "models",
    "wake",
    "vosk-model-small-en-us-0.15"
)


WAKE_PHRASES = (
    "hey sentinel",
    "hey sentinelle"
)


_STOP_EVENT = threading.Event()


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(
    text
):

    text = str(
        text
        or
        ""
    ).lower()

    text = re.sub(
        r"[^a-z ]",
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
# WAKE WORD DETECTION
# ============================================================

def contains_wake_word(
    text
):

    normalized = normalize_text(
        text
    )

    return any(
        phrase in normalized
        for phrase in WAKE_PHRASES
    )


# ============================================================
# WAKE MODEL
# ============================================================

def wake_model_available():

    return os.path.isdir(
        WAKE_MODEL_PATH
    )


def load_wake_model():

    if not wake_model_available():

        raise RuntimeError(
            "WAKE_MODEL_NOT_FOUND: "
            +
            WAKE_MODEL_PATH
        )


    SetLogLevel(
        -1
    )


    print(
        "[WAKE] Loading local wake-word model..."
    )


    model = Model(
        WAKE_MODEL_PATH
    )


    print(
        "[WAKE] Wake-word model ready."
    )


    return model


# ============================================================
# WAIT FOR HEY SENTINEL
# ============================================================

def wait_for_wake_word(
    model
):

    grammar = json.dumps(
        [
            "hey sentinel",
            "hey sentinelle",
            "[unk]"
        ]
    )


    recognizer = KaldiRecognizer(
        model,
        SAMPLE_RATE,
        grammar
    )


    last_trigger = 0.0


    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        dtype="int16",
        channels=1
    ) as stream:

        print(
            '[WAKE] Waiting for "Hey Sentinel"...'
        )


        while not _STOP_EVENT.is_set():

            data, overflowed = stream.read(
                BLOCK_SIZE
            )


            if overflowed:
                continue


            raw = bytes(
                data
            )


            if recognizer.AcceptWaveform(
                raw
            ):

                result = json.loads(
                    recognizer.Result()
                )

                text = result.get(
                    "text",
                    ""
                )


            else:

                result = json.loads(
                    recognizer.PartialResult()
                )

                text = result.get(
                    "partial",
                    ""
                )


            if not text:
                continue


            if contains_wake_word(
                text
            ):

                now = time.monotonic()


                if (
                    now
                    -
                    last_trigger
                    <
                    WAKE_COOLDOWN
                ):

                    continue


                last_trigger = now


                print(
                    '[WAKE] "Hey Sentinel" detected.'
                )


                return True


    return False


# ============================================================
# SPEAK DISPATCHER ERROR
# ============================================================

def speak_dispatch_error(
    response,
    language
):

    response = str(
        response
        or
        ""
    ).strip()


    if not response:

        if str(
            language
        ).lower().startswith(
            "fr"
        ):

            response = (
                "Je n'ai pas pu terminer "
                "cette commande."
            )

        else:

            response = (
                "I could not complete "
                "that command."
            )


    speak(
        response,
        language
    )


# ============================================================
# HANDLE DISPATCHER RESULT
# ============================================================

def handle_dispatch_result(
    orb,
    result,
    language
):

    if not isinstance(
        result,
        dict
    ):

        result = {
            "status":
                "ERROR",

            "route":
                "UNKNOWN",

            "response":
                str(
                    result
                )
        }


    route = str(
        result.get(
            "route",
            "UNKNOWN"
        )
    )


    status = str(
        result.get(
            "status",
            "UNKNOWN"
        )
    )


    response = str(
        result.get(
            "response",
            ""
        )
    ).strip()


    print("")

    print(
        "[VOICE DISPATCH ROUTE]",
        route
    )


    print(
        "[VOICE DISPATCH STATUS]",
        status
    )


    # ========================================================
    # NORMAL BRAIN
    # ========================================================

    if route == "BRAIN":

        if not response:

            if str(
                language
            ).lower().startswith(
                "fr"
            ):

                response = (
                    "J'ai traité la demande, "
                    "mais je n'ai pas de réponse."
                )

            else:

                response = (
                    "I processed the request, "
                    "but I do not have a response."
                )


        print("")

        print(
            "SENTINEL > "
            +
            response
        )


        print(
            "[BRAIN ROUTE]",
            result.get(
                "brain_route"
            )
        )


        print(
            "[KNOWLEDGE SOURCE]",
            result.get(
                "knowledge_source"
            )
        )


        orb.set_state(
            "SPEAKING"
        )


        speak(
            response,
            language
        )


        return result


    # ========================================================
    # VISUAL INCIDENT REPLAY
    #
    # When successfully launched:
    # DO NOT speak here.
    #
    # The Visual Incident Replay already starts its
    # own F3 narration.
    # ========================================================

    if route == "VISUAL_INCIDENT_REPLAY":

        if status == "LAUNCHED":

            print(
                "[VOICE REPLAY] "
                "Visual replay launched."
            )


            print(
                "[VOICE REPLAY] "
                "Replay narration owns audio output."
            )


            orb.set_state(
                "STANDBY"
            )


            return result


        # Already running / failure:
        # a short spoken response is useful.

        if response:

            orb.set_state(
                "SPEAKING"
            )


            speak(
                response,
                language
            )


        return result


    # ========================================================
    # EVIDENCE CONTROL
    #
    # Evidence subsystem manages its own secure workflow
    # and may already speak during verification.
    #
    # Avoid unnecessary duplicate TTS.
    # ========================================================

    if route == "EVIDENCE_CONTROL":

        print(
            "[VOICE EVIDENCE]",
            status
        )


        if status == "ERROR":

            orb.set_state(
                "SPEAKING"
            )


            speak_dispatch_error(
                response,
                language
            )


        return result


    # ========================================================
    # GUEST ENROLLMENT
    #
    # Guest workflow owns its identity/liveness interaction.
    # ========================================================

    if route == "GUEST_ENROLLMENT":

        print(
            "[VOICE GUEST]",
            status
        )


        if status == "ERROR":

            orb.set_state(
                "SPEAKING"
            )


            speak_dispatch_error(
                response,
                language
            )


        return result


    # ========================================================
    # UNKNOWN / ERROR
    # ========================================================

    if (
        status == "ERROR"
        or
        route == "UNKNOWN"
    ):

        orb.set_state(
            "SPEAKING"
        )


        speak_dispatch_error(
            response,
            language
        )


    return result


# ============================================================
# COMPLETE VOICE INTERACTION
# ============================================================

def handle_interaction(
    dispatcher,
    orb
):

    audio_path = None


    try:

        # ====================================================
        # SHOW ORB
        # ====================================================

        orb.show()


        orb.set_state(
            "SPEAKING"
        )


        speak_ready(
            "en"
        )


        # Prevent microphone from recording
        # the end of Sentinel's own voice.

        time.sleep(
            0.4
        )


        # ====================================================
        # LISTEN
        # ====================================================

        orb.set_state(
            "LISTENING"
        )


        audio_path = record_audio(
            QUESTION_SECONDS
        )


        # ====================================================
        # LOCAL STT
        # ====================================================

        orb.set_state(
            "THINKING"
        )


        transcription = transcribe_audio(
            audio_path
        )


        question = str(
            transcription.get(
                "text",
                ""
            )
        ).strip()


        language = (
            transcription.get(
                "language"
            )
            or
            "en"
        )


        confidence = (
            transcription.get(
                "language_probability"
            )
        )


        rejection_reason = (
            transcription.get(
                "reason"
            )
        )


        # ====================================================
        # REJECTED / NO SPEECH
        #
        # Voice V3.2 fails closed.
        #
        # A rejected transcription NEVER reaches the
        # Command Dispatcher.
        # ====================================================

        if not question:

            print("")

            print(
                "[VOICE] Command not dispatched."
            )


            print(
                "[VOICE] Reason:",
                rejection_reason
            )


            orb.set_state(
                "SPEAKING"
            )


            speak(
                (
                    "I didn't understand clearly. "
                    "Please repeat."
                ),
                "en"
            )


            return {
                "status":
                    "NO_SPEECH",

                "reason":
                    rejection_reason,

                "dispatched":
                    False
            }


        # ====================================================
        # TRANSCRIPTION OUTPUT
        # ====================================================

        print("")

        print(
            "YOU > "
            +
            question
        )


        print(
            "[LANGUAGE] "
            f"{language} "
            f"({confidence}%)"
        )


        # ====================================================
        # UNIFIED COMMAND DISPATCHER
        # ====================================================

        print(
            "[VOICE] Sending command "
            "to unified dispatcher..."
        )


        result = dispatcher.dispatch(
            question,
            source="voice",
            language=language
        )


        # ====================================================
        # ROUTE-SPECIFIC OUTPUT
        # ====================================================

        return handle_dispatch_result(
            orb,
            result,
            language
        )


    finally:

        # ====================================================
        # DELETE TEMPORARY QUESTION AUDIO
        # ====================================================

        if (
            isinstance(audio_path, (str, os.PathLike))
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


        # ====================================================
        # RETURN ORB TO STANDBY
        # ====================================================

        try:

            orb.set_state(
                "STANDBY"
            )


            time.sleep(
                0.5
            )


            orb.hide()


        except Exception:

            pass


# ============================================================
# SENTINEL BACKGROUND WORKER
# ============================================================

def sentinel_worker(
    orb
):

    try:

        # ====================================================
        # WAKE MODEL
        # ====================================================

        model = load_wake_model()


        # ====================================================
        # SINGLE COMMAND DISPATCHER INSTANCE
        # ====================================================

        dispatcher = (
            CommandDispatcher()
        )


        print(
            "=" * 72
        )


        print(
            "SENTINEL PHOENIX"
        )


        print(
            "WAKE WORD CORE V2.3"
        )


        print(
            '"HEY SENTINEL" ONLINE'
        )


        print(
            "UNIFIED VOICE + TEXT COMMAND ARCHITECTURE"
        )


        print(
            "=" * 72
        )


        print(
            "[WAKE] Voice route:"
        )


        print(
            "VOICE -> COMMAND DISPATCHER"
        )


        print(
            "[WAKE] Available routes:"
        )


        print(
            "EVIDENCE / GUEST / REPLAY / BRAIN"
        )


        print("")


        while not _STOP_EVENT.is_set():

            detected = wait_for_wake_word(
                model
            )


            if not detected:
                continue


            try:

                handle_interaction(
                    dispatcher,
                    orb
                )


            except Exception as error:

                print(
                    "[WAKE ERROR] "
                    +
                    str(
                        error
                    )
                )


                try:

                    orb.show()


                    orb.set_state(
                        "ERROR"
                    )


                    speak(
                        (
                            "I encountered an error, "
                            "but Sentinel is still running."
                        ),
                        "en"
                    )


                except Exception:

                    pass


                time.sleep(
                    1.0
                )


                try:

                    orb.hide()


                except Exception:

                    pass


            # =================================================
            # Prevent Sentinel hearing its own response
            # =================================================

            time.sleep(
                0.8
            )


    except Exception as error:

        print(
            "[FATAL WAKE ERROR] "
            +
            str(
                error
            )
        )


        try:

            orb.show()


            orb.set_state(
                "ERROR"
            )


        except Exception:

            pass


# ============================================================
# APPLICATION
# ============================================================

def run():

    _STOP_EVENT.clear()


    orb = SentinelOrb()


    worker = threading.Thread(
        target=sentinel_worker,
        args=(
            orb,
        ),
        daemon=True,
        name="SentinelWakeWorker"
    )


    worker.start()


    try:

        orb.run()


    finally:

        _STOP_EVENT.set()


    return 0


# ============================================================
# SELF TEST
#
# No microphone recording.
# No evidence action.
# No guest enrollment.
# No Replay window.
# ============================================================

def self_test():

    dispatcher = None


    try:

        dispatcher = (
            dispatcher_self_test()
        )


    except Exception as error:

        dispatcher = {
            "status":
                "FAIL",

            "reason":
                str(
                    error
                )
        }


    tests = {

        # ====================================================
        # WAKE WORD
        # ====================================================

        "wake_model":
            wake_model_available(),


        "wake_exact":
            contains_wake_word(
                "hey sentinel"
            ),


        "wake_french":
            contains_wake_word(
                "hey sentinelle"
            ),


        "normal_text_rejected_as_wake":
            not contains_wake_word(
                "what happened today"
            ),


        # ====================================================
        # UNIFIED DISPATCHER
        # ====================================================

        "dispatcher":
            dispatcher.get(
                "status"
            ) == "PASS",


        "voice_source_supported":
            (
                "VOICE"
                in
                dispatcher.get(
                    "inputs",
                    []
                )
            ),


        "text_source_supported":
            (
                "TEXT"
                in
                dispatcher.get(
                    "inputs",
                    []
                )
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


        "wake_version":
            WAKE_VERSION,


        "architecture":
            "UNIFIED_COMMAND_DISPATCHER",


        "tests":
            tests,


        "dispatcher":
            dispatcher,


        "input_interfaces": [

            "VOICE",

            "TEXT"
        ],


        "intent_router": [

            "EVIDENCE_CONTROL",

            "GUEST_ENROLLMENT",

            "VISUAL_INCIDENT_REPLAY",

            "BRAIN"
        ],


        "voice_flow": [

            "HEY_SENTINEL",

            "MICROPHONE",

            "VOICE_V3_2",

            "FR_EN_VALIDATION",

            "COMMAND_DISPATCHER",

            "ROUTE"
        ],


        "text_flow": [

            "TEXT_BAR",

            "COMMAND_DISPATCHER",

            "ROUTE"
        ],


        "security": {

            "bad_transcription_not_dispatched":
                True,

            "temporary_question_audio_deleted":
                True,

            "voice_and_text_same_router":
                True,

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

    raise SystemExit(
        run()
    )