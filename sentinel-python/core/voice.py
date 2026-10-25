import os
import re
import shutil
import subprocess
import threading
import wave

import numpy as np


# ============================================================
# SENTINEL PHOENIX
# VOICE CORE V3.3.1
#
# STT:
# - Whisper SMALL
# - French / English only
# - Audio normalization
# - Silence filtering
# - Confidence filtering
#
# POLICY:
#
# < 75%      -> REJECT
# 75 - 89%   -> REPEAT REQUIRED
# >= 90%     -> ACCEPT
#
# Compatibility:
# - Voice
# - record_audio
# - record_command
# - record_command_audio
# - transcribe
# - transcribe_audio
# - transcribe_command
# - speak
# - speak_ready
# ============================================================


VOICE_VERSION = "3.3.1"


# ============================================================
# AUDIO CONFIG
# ============================================================

SAMPLE_RATE = 16000

CHANNELS = 1

DEFAULT_RECORD_SECONDS = 5.5


# ============================================================
# WHISPER CONFIG
# ============================================================

DEFAULT_MODEL_NAME = os.environ.get(
    "SENTINEL_STT_MODEL",
    "small"
).strip()

DEVICE = os.environ.get(
    "SENTINEL_STT_DEVICE",
    "cpu"
).strip()

COMPUTE_TYPE = os.environ.get(
    "SENTINEL_STT_COMPUTE_TYPE",
    "int8"
).strip()


# ============================================================
# CONFIDENCE
# ============================================================

REJECT_THRESHOLD = 75.0

ACCEPT_THRESHOLD = 90.0


# ============================================================
# AUDIO NORMALIZATION
# ============================================================

TARGET_RMS = (
    1800.0
    /
    32768.0
)

MAX_GAIN = 12.0

SAFE_PEAK = (
    28000.0
    /
    32768.0
)

MIN_AUDIO_RMS = 0.0025

MIN_ACTIVE_SECONDS = 0.18


# ============================================================
# GLOBAL MODEL
# ============================================================

_MODEL = None

_MODEL_LOCK = threading.Lock()


# ============================================================
# OPTIONAL IMPORTS
# ============================================================

def _import_sounddevice():

    try:

        import sounddevice as sd

        return sd

    except Exception as error:

        raise RuntimeError(
            "SOUNDDEVICE_UNAVAILABLE: "
            +
            str(error)
        )


def _import_whisper():

    try:

        from faster_whisper import WhisperModel

        return WhisperModel

    except Exception as error:

        raise RuntimeError(
            "FASTER_WHISPER_UNAVAILABLE: "
            +
            str(error)
        )


# ============================================================
# MODEL
# ============================================================

def get_model():

    global _MODEL

    with _MODEL_LOCK:

        if _MODEL is not None:

            return _MODEL


        WhisperModel = _import_whisper()


        print(
            "[VOICE V3.3.1] Loading STT model:",
            DEFAULT_MODEL_NAME,
            flush=True
        )


        _MODEL = WhisperModel(
            DEFAULT_MODEL_NAME,
            device=DEVICE,
            compute_type=COMPUTE_TYPE
        )


        print(
            "[VOICE V3.3.1] STT model ready.",
            flush=True
        )


        return _MODEL


# ============================================================
# AUDIO CONVERSION
# ============================================================

def _to_float32(
    audio
):

    if audio is None:

        return np.empty(
            0,
            dtype=np.float32
        )


    if isinstance(
        audio,
        bytes
    ):

        array = np.frombuffer(
            audio,
            dtype=np.int16
        )

        return (
            array.astype(
                np.float32
            )
            /
            32768.0
        )


    array = np.asarray(
        audio
    )


    if array.size == 0:

        return np.empty(
            0,
            dtype=np.float32
        )


    if array.ndim > 1:

        array = np.mean(
            array,
            axis=1
        )


    if np.issubdtype(
        array.dtype,
        np.integer
    ):

        info = np.iinfo(
            array.dtype
        )

        maximum = float(
            max(
                abs(info.min),
                abs(info.max)
            )
        )

        array = (
            array.astype(
                np.float32
            )
            /
            maximum
        )

    else:

        array = array.astype(
            np.float32
        )


    return np.clip(
        array,
        -1.0,
        1.0
    )


# ============================================================
# WAV
# ============================================================

def load_wav(
    path
):

    with wave.open(
        path,
        "rb"
    ) as handle:

        channels = handle.getnchannels()

        sample_width = (
            handle.getsampwidth()
        )

        sample_rate = (
            handle.getframerate()
        )

        frames = handle.readframes(
            handle.getnframes()
        )


    if sample_width != 2:

        raise RuntimeError(
            "ONLY_16_BIT_WAV_SUPPORTED"
        )


    audio = np.frombuffer(
        frames,
        dtype=np.int16
    )


    if channels > 1:

        audio = audio.reshape(
            -1,
            channels
        )

        audio = np.mean(
            audio,
            axis=1
        ).astype(
            np.int16
        )


    audio = _to_float32(
        audio
    )


    if sample_rate != SAMPLE_RATE:

        audio = resample_audio(
            audio,
            sample_rate,
            SAMPLE_RATE
        )


    return audio


# ============================================================
# RESAMPLING
# ============================================================

def resample_audio(
    audio,
    source_rate,
    target_rate
):

    audio = _to_float32(
        audio
    )


    if audio.size == 0:

        return audio


    if source_rate == target_rate:

        return audio


    duration = (
        audio.size
        /
        float(source_rate)
    )


    target_samples = int(
        duration
        *
        target_rate
    )


    if target_samples <= 0:

        return np.empty(
            0,
            dtype=np.float32
        )


    source_positions = np.linspace(
        0.0,
        1.0,
        num=audio.size,
        endpoint=False
    )


    target_positions = np.linspace(
        0.0,
        1.0,
        num=target_samples,
        endpoint=False
    )


    result = np.interp(
        target_positions,
        source_positions,
        audio
    )


    return result.astype(
        np.float32
    )


# ============================================================
# PREPARE AUDIO
# ============================================================

def prepare_audio(
    audio
):

    if isinstance(
        audio,
        str
    ):

        if not os.path.isfile(
            audio
        ):

            raise RuntimeError(
                "AUDIO_FILE_NOT_FOUND"
            )


        if audio.lower().endswith(
            ".wav"
        ):

            return load_wav(
                audio
            )


        return audio


    return _to_float32(
        audio
    )


# ============================================================
# AUDIO STATS
# ============================================================

def audio_statistics(
    audio
):

    if isinstance(
        audio,
        str
    ):

        try:

            audio = load_wav(
                audio
            )

        except Exception:

            return {
                "samples": 0,
                "duration": 0.0,
                "rms": 0.0,
                "peak": 0.0
            }


    audio = _to_float32(
        audio
    )


    if audio.size == 0:

        return {
            "samples": 0,
            "duration": 0.0,
            "rms": 0.0,
            "peak": 0.0
        }


    rms = float(
        np.sqrt(
            np.mean(
                np.square(
                    audio,
                    dtype=np.float64
                )
            )
        )
    )


    peak = float(
        np.max(
            np.abs(
                audio
            )
        )
    )


    return {
        "samples":
            int(audio.size),

        "duration":
            round(
                audio.size
                /
                float(SAMPLE_RATE),
                3
            ),

        "rms":
            round(
                rms,
                6
            ),

        "peak":
            round(
                peak,
                6
            )
    }


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_audio(
    audio
):

    if isinstance(
        audio,
        str
    ):

        return audio


    audio = _to_float32(
        audio
    )


    if audio.size == 0:

        return audio


    rms = float(
        np.sqrt(
            np.mean(
                np.square(
                    audio,
                    dtype=np.float64
                )
            )
        )
    )


    if rms <= 0.0:

        return audio


    gain = (
        TARGET_RMS
        /
        rms
    )


    gain = max(
        1.0,
        min(
            MAX_GAIN,
            gain
        )
    )


    peak = float(
        np.max(
            np.abs(
                audio
            )
        )
    )


    if peak > 0.0:

        maximum_gain = (
            SAFE_PEAK
            /
            peak
        )

        gain = min(
            gain,
            maximum_gain
        )


    gain = max(
        1.0,
        gain
    )


    normalized = (
        audio
        *
        gain
    )


    return np.clip(
        normalized,
        -SAFE_PEAK,
        SAFE_PEAK
    ).astype(
        np.float32
    )


# ============================================================
# SILENCE TRIM
# ============================================================

def trim_silence(
    audio
):

    if isinstance(
        audio,
        str
    ):

        return audio


    audio = _to_float32(
        audio
    )


    if audio.size == 0:

        return audio


    frame_size = int(
        SAMPLE_RATE
        *
        0.02
    )


    active = []


    for start in range(
        0,
        audio.size,
        frame_size
    ):

        frame = audio[
            start:
            start + frame_size
        ]


        if frame.size == 0:

            continue


        rms = float(
            np.sqrt(
                np.mean(
                    np.square(
                        frame,
                        dtype=np.float64
                    )
                )
            )
        )


        if rms >= MIN_AUDIO_RMS:

            active.append(
                (
                    start,
                    min(
                        audio.size,
                        start + frame_size
                    )
                )
            )


    if not active:

        return np.empty(
            0,
            dtype=np.float32
        )


    first = max(
        0,
        active[0][0]
        -
        int(
            SAMPLE_RATE
            *
            0.15
        )
    )


    last = min(
        audio.size,
        active[-1][1]
        +
        int(
            SAMPLE_RATE
            *
            0.20
        )
    )


    return audio[
        first:last
    ]


# ============================================================
# MICROPHONE
# ============================================================

def record_audio(
    seconds=DEFAULT_RECORD_SECONDS,
    duration=None,
    sample_rate=SAMPLE_RATE
):

    if duration is not None:

        seconds = duration


    seconds = max(
        0.5,
        float(seconds)
    )


    sd = _import_sounddevice()


    print(
        "[VOICE V3.3.1] Listening...",
        flush=True
    )


    recording = sd.rec(
        int(
            seconds
            *
            sample_rate
        ),
        samplerate=sample_rate,
        channels=CHANNELS,
        dtype="float32"
    )


    sd.wait()


    return np.asarray(
        recording,
        dtype=np.float32
    ).reshape(
        -1
    )


# ============================================================
# COMPATIBILITY RECORDING FUNCTIONS
# ============================================================

def record_command(
    seconds=DEFAULT_RECORD_SECONDS,
    duration=None
):

    return record_audio(
        seconds=seconds,
        duration=duration
    )


def record_command_audio(
    seconds=DEFAULT_RECORD_SECONDS,
    duration=None
):

    return record_audio(
        seconds=seconds,
        duration=duration
    )


# ============================================================
# TEXT
# ============================================================

def clean_text(
    text
):

    text = str(
        text or ""
    )


    text = re.sub(
        r"\s+",
        " ",
        text
    )


    return text.strip()


# ============================================================
# REPETITION PENALTY
# ============================================================

def repetition_penalty(
    text
):

    normalized = clean_text(
        text
    ).lower()


    words = re.findall(
        r"\w+",
        normalized,
        flags=re.UNICODE
    )


    if len(words) < 4:

        return 0.0


    most_common = max(
        (
            words.count(word)
            for word in set(words)
        ),
        default=1
    )


    ratio = (
        most_common
        /
        max(
            len(words),
            1
        )
    )


    penalty = 0.0


    if ratio >= 0.55:

        penalty += 30.0

    elif ratio >= 0.40:

        penalty += 15.0


    for size in (
        2,
        3,
        4
    ):

        if len(words) < size * 2:

            continue


        chunks = [
            tuple(
                words[
                    index:
                    index + size
                ]
            )
            for index in range(
                len(words)
                -
                size
                +
                1
            )
        ]


        maximum = max(
            (
                chunks.count(chunk)
                for chunk in set(chunks)
            ),
            default=1
        )


        if maximum >= 3:

            penalty += 20.0

            break


    return min(
        60.0,
        penalty
    )


# ============================================================
# CHARACTER PENALTY
# ============================================================

def strange_character_penalty(
    text
):

    if not text:

        return 100.0


    total_letters = 0

    latin_letters = 0


    french_chars = set(
        "àâäçéèêëîïôöùûüÿœæ"
    )


    for character in text:

        if character.isalpha():

            total_letters += 1


            if (
                "a"
                <=
                character.lower()
                <=
                "z"
            ):

                latin_letters += 1


            elif character.lower() in french_chars:

                latin_letters += 1


    if total_letters == 0:

        return 20.0


    ratio = (
        latin_letters
        /
        total_letters
    )


    if ratio >= 0.95:

        return 0.0


    if ratio >= 0.80:

        return 10.0


    return 50.0


# ============================================================
# LOGPROB -> CONFIDENCE
# ============================================================

def logprob_to_confidence(
    average_logprob
):

    value = (
        100.0
        +
        (
            50.0
            *
            float(
                average_logprob
            )
        )
    )


    return max(
        0.0,
        min(
            100.0,
            value
        )
    )


# ============================================================
# TRANSCRIPTION CANDIDATE
# ============================================================

def transcribe_candidate(
    model,
    audio,
    language
):

    try:

        segments, info = model.transcribe(
            audio,
            language=language,
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            word_timestamps=False
        )


        segments = list(
            segments
        )


    except Exception as error:

        return {
            "language": language,
            "text": "",
            "confidence": 0.0,
            "raw_confidence": 0.0,
            "average_logprob": -10.0,
            "no_speech_probability": 1.0,
            "valid": False,
            "reason":
                "TRANSCRIPTION_ERROR: "
                +
                str(error)
        }


    text = clean_text(
        " ".join(
            segment.text
            for segment in segments
        )
    )


    if not segments:

        return {
            "language": language,
            "text": "",
            "confidence": 0.0,
            "raw_confidence": 0.0,
            "average_logprob": -10.0,
            "no_speech_probability": 1.0,
            "valid": False,
            "reason": "NO_SEGMENTS"
        }


    weights = []

    logprobs = []

    no_speech_values = []


    for segment in segments:

        duration = max(
            0.05,
            float(
                segment.end
                -
                segment.start
            )
        )


        weights.append(
            duration
        )


        logprobs.append(
            float(
                getattr(
                    segment,
                    "avg_logprob",
                    -1.0
                )
            )
        )


        no_speech_values.append(
            float(
                getattr(
                    segment,
                    "no_speech_prob",
                    0.0
                )
            )
        )


    average_logprob = float(
        np.average(
            logprobs,
            weights=weights
        )
    )


    no_speech_probability = float(
        np.average(
            no_speech_values,
            weights=weights
        )
    )


    raw_confidence = (
        logprob_to_confidence(
            average_logprob
        )
    )


    confidence = (
        raw_confidence
        *
        (
            1.0
            -
            min(
                0.85,
                no_speech_probability
            )
        )
    )


    confidence -= repetition_penalty(
        text
    )


    confidence -= strange_character_penalty(
        text
    )


    word_count = len(
        re.findall(
            r"\w+",
            text,
            flags=re.UNICODE
        )
    )


    if word_count == 0:

        confidence = 0.0


    confidence = max(
        0.0,
        min(
            100.0,
            confidence
        )
    )


    return {
        "language":
            language,

        "text":
            text,

        "confidence":
            round(
                confidence,
                2
            ),

        "raw_confidence":
            round(
                raw_confidence,
                2
            ),

        "average_logprob":
            round(
                average_logprob,
                4
            ),

        "no_speech_probability":
            round(
                no_speech_probability,
                4
            ),

        "word_count":
            word_count,

        "valid":
            bool(text),

        "reason":
            (
                "OK"
                if text
                else
                "EMPTY_TEXT"
            )
    }


# ============================================================
# DECISION
# ============================================================

def decide_transcription(
    candidate
):

    confidence = float(
        candidate.get(
            "confidence",
            0.0
        )
    )


    text = clean_text(
        candidate.get(
            "text",
            ""
        )
    )


    if not text:

        return (
            "NO_SPEECH",
            False,
            False
        )


    if confidence < REJECT_THRESHOLD:

        return (
            "REJECTED_LOW_CONFIDENCE",
            False,
            False
        )


    if confidence < ACCEPT_THRESHOLD:

        return (
            "REPEAT_REQUIRED",
            False,
            True
        )


    return (
        "ACCEPTED",
        True,
        False
    )


# ============================================================
# TRANSCRIBE AUDIO
# ============================================================

def transcribe_audio(
    audio,
    language=None
):

    prepared = prepare_audio(
        audio
    )


    if not isinstance(
        prepared,
        str
    ):

        original_stats = audio_statistics(
            prepared
        )


        if (
            original_stats["rms"]
            <
            MIN_AUDIO_RMS
        ):

            return {
                "status": "NO_SPEECH",
                "accepted": False,
                "valid": False,
                "needs_repeat": False,
                "should_repeat": False,
                "rejected": True,
                "text": "",
                "language": None,
                "confidence": 0.0,
                "selection_confidence": 0.0,
                "reason": "AUDIO_TOO_QUIET",
                "audio": original_stats,
                "version": VOICE_VERSION
            }


        prepared = normalize_audio(
            prepared
        )


        prepared = trim_silence(
            prepared
        )


        processed_stats = (
            audio_statistics(
                prepared
            )
        )


        if (
            processed_stats["duration"]
            <
            MIN_ACTIVE_SECONDS
        ):

            return {
                "status": "NO_SPEECH",
                "accepted": False,
                "valid": False,
                "needs_repeat": False,
                "should_repeat": False,
                "rejected": True,
                "text": "",
                "language": None,
                "confidence": 0.0,
                "selection_confidence": 0.0,
                "reason": "ACTIVE_SPEECH_TOO_SHORT",
                "audio": processed_stats,
                "version": VOICE_VERSION
            }


    else:

        original_stats = (
            audio_statistics(
                prepared
            )
        )

        processed_stats = (
            original_stats
        )


    model = get_model()


    candidates = []


    for candidate_language in (
        "fr",
        "en"
    ):

        candidate = (
            transcribe_candidate(
                model,
                prepared,
                candidate_language
            )
        )


        if (
            language in (
                "fr",
                "en"
            )
            and
            candidate_language
            ==
            language
        ):

            candidate[
                "confidence"
            ] = round(
                min(
                    100.0,
                    float(
                        candidate[
                            "confidence"
                        ]
                    )
                    +
                    2.0
                ),
                2
            )


        candidates.append(
            candidate
        )


    candidates.sort(
        key=lambda item:
            float(
                item.get(
                    "confidence",
                    0.0
                )
            ),
        reverse=True
    )


    best = candidates[
        0
    ]

    second = candidates[
        1
    ]


    best_confidence = float(
        best.get(
            "confidence",
            0.0
        )
    )


    second_confidence = float(
        second.get(
            "confidence",
            0.0
        )
    )


    language_margin = (
        best_confidence
        -
        second_confidence
    )


    best_text = clean_text(
        best.get(
            "text",
            ""
        )
    )


    second_text = clean_text(
        second.get(
            "text",
            ""
        )
    )


    if (
        language_margin < 4.0
        and
        best_text.lower()
        !=
        second_text.lower()
    ):

        best_confidence = max(
            0.0,
            best_confidence
            -
            5.0
        )


    best[
        "confidence"
    ] = round(
        best_confidence,
        2
    )


    (
        status,
        accepted,
        repeat
    ) = decide_transcription(
        best
    )


    result = {
        "status":
            status,

        "accepted":
            accepted,

        "valid":
            accepted,

        "needs_repeat":
            repeat,

        "should_repeat":
            repeat,

        "rejected":
            not accepted,

        "text":
            best_text,

        "language":
            best.get(
                "language"
            ),

        "confidence":
            round(
                best_confidence,
                2
            ),

        "selection_confidence":
            round(
                best_confidence,
                2
            ),

        "language_margin":
            round(
                language_margin,
                2
            ),

        "reason":
            status,

        "candidates":
            candidates,

        "audio":
            processed_stats,

        "thresholds": {
            "reject_below":
                REJECT_THRESHOLD,

            "accept_from":
                ACCEPT_THRESHOLD
        },

        "version":
            VOICE_VERSION
    }


    print(
        "[VOICE V3.3.1]",
        (
            f"{result['language']} | "
            f"{result['confidence']:.2f}% | "
            f"{result['status']} | "
            f"{result['text']}"
        ),
        flush=True
    )


    return result


# ============================================================
# TRANSCRIPTION COMPATIBILITY
# ============================================================

def transcribe(
    audio,
    language=None
):

    return transcribe_audio(
        audio,
        language=language
    )


def transcribe_command(
    audio,
    language=None
):

    return transcribe_audio(
        audio,
        language=language
    )


# ============================================================
# LOCAL TTS
# ============================================================

def speak(
    text,
    language="en",
    wait=True
):

    text = clean_text(
        text
    )


    if not text:

        return False


    language = str(
        language or "en"
    ).lower()


    if language.startswith(
        "fr"
    ):

        voice = "fr+f3"

    else:

        voice = "en-us+f3"


    executable = (
        shutil.which(
            "espeak-ng"
        )
        or
        shutil.which(
            "espeak"
        )
    )


    if executable is None:

        print(
            "[VOICE V3.3.1] TTS unavailable:",
            text,
            flush=True
        )

        return False


    command = [
        executable,
        "-v",
        voice,
        "-s",
        "165",
        text
    ]


    try:

        if wait:

            subprocess.run(
                command,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        else:

            subprocess.Popen(
                command,
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )


        return True


    except Exception as error:

        print(
            "[VOICE V3.3.1] TTS error:",
            str(error),
            flush=True
        )

        return False


# ============================================================
# WAKE WORD COMPATIBILITY
#
# Required by core.wake_word
# ============================================================

def speak_ready(
    language="en"
):

    language = str(
        language or "en"
    ).lower()


    if language.startswith(
        "fr"
    ):

        return speak(
            "Je vous écoute.",
            language="fr",
            wait=True
        )


    return speak(
        "I'm listening.",
        language="en",
        wait=True
    )


# ============================================================
# VOICE CLASS
# ============================================================

class Voice:

    def __init__(
        self,
        model_name=None
    ):

        global DEFAULT_MODEL_NAME


        if model_name:

            requested = str(
                model_name
            ).strip()


            if (
                requested
                and
                requested
                !=
                DEFAULT_MODEL_NAME
            ):

                DEFAULT_MODEL_NAME = (
                    requested
                )


    # ========================================================
    # RECORD
    # ========================================================

    def record(
        self,
        seconds=DEFAULT_RECORD_SECONDS,
        duration=None
    ):

        return record_audio(
            seconds=seconds,
            duration=duration
        )


    def record_audio(
        self,
        seconds=DEFAULT_RECORD_SECONDS,
        duration=None
    ):

        return self.record(
            seconds=seconds,
            duration=duration
        )


    def record_command(
        self,
        seconds=DEFAULT_RECORD_SECONDS,
        duration=None
    ):

        return self.record(
            seconds=seconds,
            duration=duration
        )


    def record_command_audio(
        self,
        seconds=DEFAULT_RECORD_SECONDS,
        duration=None
    ):

        return self.record(
            seconds=seconds,
            duration=duration
        )


    # ========================================================
    # TRANSCRIBE
    # ========================================================

    def transcribe(
        self,
        audio,
        language=None
    ):

        return transcribe_audio(
            audio,
            language=language
        )


    def transcribe_audio(
        self,
        audio,
        language=None
    ):

        return self.transcribe(
            audio,
            language=language
        )


    def transcribe_command(
        self,
        audio,
        language=None
    ):

        return self.transcribe(
            audio,
            language=language
        )


    # ========================================================
    # LISTEN
    # ========================================================

    def listen(
        self,
        seconds=DEFAULT_RECORD_SECONDS,
        duration=None,
        language=None
    ):

        audio = self.record(
            seconds=seconds,
            duration=duration
        )


        return self.transcribe(
            audio,
            language=language
        )


    def listen_once(
        self,
        seconds=DEFAULT_RECORD_SECONDS,
        duration=None,
        language=None
    ):

        return self.listen(
            seconds=seconds,
            duration=duration,
            language=language
        )


    def record_and_transcribe(
        self,
        seconds=DEFAULT_RECORD_SECONDS,
        duration=None,
        language=None
    ):

        return self.listen(
            seconds=seconds,
            duration=duration,
            language=language
        )


    # ========================================================
    # SPEAK
    # ========================================================

    def speak(
        self,
        text,
        language="en",
        wait=True
    ):

        return speak(
            text,
            language=language,
            wait=wait
        )


    def speak_ready(
        self,
        language="en"
    ):

        return speak_ready(
            language=language
        )


# ============================================================
# HELPERS
# ============================================================

def is_accepted(
    result
):

    return bool(
        isinstance(
            result,
            dict
        )
        and
        result.get(
            "accepted",
            False
        )
    )


def needs_repeat(
    result
):

    return bool(
        isinstance(
            result,
            dict
        )
        and
        result.get(
            "needs_repeat",
            False
        )
    )


# ============================================================
# SELF TEST
#
# No microphone.
# No model loading.
# No TTS playback.
# ============================================================

def self_test():

    try:

        import sounddevice

        sounddevice_ok = True

    except Exception:

        sounddevice_ok = False


    try:

        import faster_whisper

        faster_whisper_ok = True

    except Exception:

        faster_whisper_ok = False


    tts_available = bool(
        shutil.which(
            "espeak-ng"
        )
        or
        shutil.which(
            "espeak"
        )
    )


    confidence_policy_ok = (
        0
        <
        REJECT_THRESHOLD
        <
        ACCEPT_THRESHOLD
        <=
        100
    )


    compatibility = {
        "record_audio":
            callable(
                record_audio
            ),

        "record_command":
            callable(
                record_command
            ),

        "record_command_audio":
            callable(
                record_command_audio
            ),

        "transcribe":
            callable(
                transcribe
            ),

        "transcribe_audio":
            callable(
                transcribe_audio
            ),

        "transcribe_command":
            callable(
                transcribe_command
            ),

        "speak":
            callable(
                speak
            ),

        "speak_ready":
            callable(
                speak_ready
            ),

        "Voice":
            callable(
                Voice
            )
    }


    compatibility_ok = all(
        compatibility.values()
    )


    passed = all(
        (
            sounddevice_ok,
            faster_whisper_ok,
            confidence_policy_ok,
            compatibility_ok
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
            VOICE_VERSION,

        "stt_model":
            DEFAULT_MODEL_NAME,

        "languages": [
            "fr",
            "en"
        ],

        "dependencies": {
            "sounddevice":
                sounddevice_ok,

            "faster_whisper":
                faster_whisper_ok,

            "local_tts":
                tts_available
        },

        "confidence_policy": {
            "below_75":
                "REJECT",

            "75_to_89_99":
                "REPEAT_REQUIRED",

            "90_and_above":
                "ACCEPT",

            "reject_threshold":
                REJECT_THRESHOLD,

            "accept_threshold":
                ACCEPT_THRESHOLD
        },

        "compatibility":
            compatibility,

        "audio": {
            "sample_rate":
                SAMPLE_RATE,

            "auto_gain":
                True,

            "max_gain":
                MAX_GAIN,

            "silence_detection":
                True
        },

        "security": {
            "automatic_language_unrestricted":
                False,

            "languages_limited_to_fr_en":
                True,

            "previous_text_conditioning":
                False,

            "low_confidence_execution":
                False,

            "medium_confidence_execution":
                False,

            "shell_execution":
                False,

            "speech_only_returns_text":
                True
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