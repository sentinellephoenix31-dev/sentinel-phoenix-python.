import os
import shutil
import subprocess


# ============================================================
# SENTINEL PHOENIX
# INCIDENT REPLAY NARRATION V1
#
# Local TTS only:
#   eSpeak-ng
#
# French: fr+f3
# English: en-us+f3
#
# No shell=True.
# No command execution from incident data.
# ============================================================


NARRATION_VERSION = "1.0"

DEFAULT_LANGUAGE = os.environ.get(
    "SENTINEL_REPLAY_LANGUAGE",
    "fr"
).strip().lower()

MAX_TEXT_LENGTH = 1400


# ============================================================
# SAFE VALUES
# ============================================================

def clean_value(
    value,
    fallback="inconnu",
    max_length=180
):

    if value is None:
        return fallback

    text = str(
        value
    ).strip()

    if not text:
        return fallback

    text = " ".join(
        text.split()
    )

    return text[:max_length]


# ============================================================
# LANGUAGE
# ============================================================

def normalize_language(
    language
):

    language = str(
        language or DEFAULT_LANGUAGE
    ).lower()

    if language.startswith(
        "en"
    ):
        return "en"

    return "fr"


def voice_for_language(
    language
):

    language = normalize_language(
        language
    )

    if language == "en":
        return "en-us+f3"

    return "fr+f3"


# ============================================================
# IP SPEECH
# ============================================================

def spoken_ip(
    value,
    language="fr"
):

    text = clean_value(
        value,
        fallback="inconnue"
    )

    language = normalize_language(
        language
    )

    separator = (
        " point "
        if language == "fr"
        else
        " dot "
    )

    if "." in text:
        return separator.join(
            text.split(".")
        )

    return text


# ============================================================
# BUILD FRENCH NARRATION
# ============================================================

def build_french_narration(
    payload
):

    source_ip = spoken_ip(
        payload.get(
            "source_ip",
            "inconnue"
        ),
        "fr"
    )

    threat = clean_value(
        payload.get(
            "threat_type"
        ),
        "événement de sécurité"
    )

    action = clean_value(
        payload.get(
            "action"
        ),
        "observé"
    )

    risk = payload.get(
        "risk_score",
        0
    )

    try:
        risk = round(
            float(
                risk
            )
        )

    except (
        TypeError,
        ValueError
    ):
        risk = 0


    geo = payload.get(
        "geo"
    )

    if not isinstance(
        geo,
        dict
    ):
        geo = {}


    parts = [
        "Analyse de l'incident terminée.",
        f"L'adresse I P source est {source_ip}.",
        f"Le type de menace détecté est {threat}.",
        f"Le niveau de risque évalué est de {risk} sur 100."
    ]


    if geo.get(
        "available"
    ):

        country = clean_value(
            geo.get(
                "country"
            ),
            "pays inconnu"
        )

        region = clean_value(
            geo.get(
                "region"
            ),
            "région inconnue"
        )

        city = clean_value(
            geo.get(
                "city"
            ),
            ""
        )

        asn = clean_value(
            geo.get(
                "asn"
            ),
            ""
        )

        provider = clean_value(
            geo.get(
                "provider"
            ),
            ""
        )


        if city:

            parts.append(
                "La géolocalisation approximative "
                f"de cette adresse indique {city}, "
                f"dans la région {region}, "
                f"en {country}."
            )

        else:

            parts.append(
                "La géolocalisation approximative "
                f"de cette adresse indique la région "
                f"{region}, en {country}."
            )


        if asn and provider:

            parts.append(
                f"Le réseau observé est {asn}, "
                f"associé à {provider}."
            )

        elif asn:

            parts.append(
                f"Le réseau observé est {asn}."
            )

        elif provider:

            parts.append(
                f"Le fournisseur réseau observé "
                f"est {provider}."
            )


        parts.append(
            "Cette localisation provient de "
            "l'adresse I P et reste approximative."
        )

    else:

        classification = clean_value(
            geo.get(
                "classification"
            ),
            "non publique"
        )

        parts.append(
            "Cette adresse ne dispose pas "
            "d'une géolocalisation publique fiable."
        )

        parts.append(
            f"Classification réseau : {classification}."
        )


    parts.append(
        f"Action de Sentinel : {action}."
    )


    description = clean_value(
        payload.get(
            "description"
        ),
        "",
        max_length=300
    )

    if description:

        parts.append(
            description
        )


    return " ".join(
        parts
    )[:MAX_TEXT_LENGTH]


# ============================================================
# BUILD ENGLISH NARRATION
# ============================================================

def build_english_narration(
    payload
):

    source_ip = spoken_ip(
        payload.get(
            "source_ip",
            "unknown"
        ),
        "en"
    )

    threat = clean_value(
        payload.get(
            "threat_type"
        ),
        "security event"
    )

    action = clean_value(
        payload.get(
            "action"
        ),
        "observed"
    )

    risk = payload.get(
        "risk_score",
        0
    )

    try:
        risk = round(
            float(
                risk
            )
        )

    except (
        TypeError,
        ValueError
    ):
        risk = 0


    geo = payload.get(
        "geo"
    )

    if not isinstance(
        geo,
        dict
    ):
        geo = {}


    parts = [
        "Incident analysis complete.",
        f"The source I P address is {source_ip}.",
        f"The detected threat is {threat}.",
        f"The evaluated risk score is {risk} out of 100."
    ]


    if geo.get(
        "available"
    ):

        country = clean_value(
            geo.get(
                "country"
            ),
            "unknown country"
        )

        region = clean_value(
            geo.get(
                "region"
            ),
            "unknown region"
        )

        city = clean_value(
            geo.get(
                "city"
            ),
            ""
        )

        asn = clean_value(
            geo.get(
                "asn"
            ),
            ""
        )

        provider = clean_value(
            geo.get(
                "provider"
            ),
            ""
        )


        if city:

            parts.append(
                "Approximate I P geolocation "
                f"indicates {city}, {region}, "
                f"{country}."
            )

        else:

            parts.append(
                "Approximate I P geolocation "
                f"indicates {region}, {country}."
            )


        if asn and provider:

            parts.append(
                f"The observed network is {asn}, "
                f"associated with {provider}."
            )

        elif asn:

            parts.append(
                f"The observed network is {asn}."
            )

        elif provider:

            parts.append(
                f"The observed network provider "
                f"is {provider}."
            )


        parts.append(
            "This location is derived from "
            "I P geolocation and is approximate."
        )

    else:

        classification = clean_value(
            geo.get(
                "classification"
            ),
            "non public"
        )

        parts.append(
            "No reliable public geolocation "
            "is available for this source."
        )

        parts.append(
            f"Network classification: {classification}."
        )


    parts.append(
        f"Sentinel action: {action}."
    )


    return " ".join(
        parts
    )[:MAX_TEXT_LENGTH]


# ============================================================
# PUBLIC BUILDER
# ============================================================

def build_narration(
    payload,
    language=DEFAULT_LANGUAGE
):

    language = normalize_language(
        language
    )

    if language == "en":

        return build_english_narration(
            payload
        )

    return build_french_narration(
        payload
    )


# ============================================================
# LOCAL TTS
# ============================================================

def speak_text(
    text,
    language=DEFAULT_LANGUAGE
):

    executable = shutil.which(
        "espeak-ng"
    )

    if not executable:

        return {
            "spoken": False,
            "reason": "ESPEAK_NG_NOT_FOUND"
        }


    text = clean_value(
        text,
        fallback="",
        max_length=MAX_TEXT_LENGTH
    )

    if not text:

        return {
            "spoken": False,
            "reason": "EMPTY_TEXT"
        }


    voice = voice_for_language(
        language
    )


    command = [
        executable,
        "-v",
        voice,
        "-s",
        "155",
        "-p",
        "48",
        "-a",
        "165",
        text
    ]


    try:

        result = subprocess.run(
            command,
            shell=False,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120
        )

    except subprocess.TimeoutExpired:

        return {
            "spoken": False,
            "reason": "TTS_TIMEOUT"
        }


    return {
        "spoken":
            result.returncode == 0,

        "reason":
            (
                "OK"
                if result.returncode == 0
                else
                "TTS_FAILED"
            ),

        "voice":
            voice
    }


# ============================================================
# INCIDENT SPEECH
# ============================================================

def speak_incident(
    payload,
    language=DEFAULT_LANGUAGE
):

    narration = build_narration(
        payload,
        language
    )


    result = speak_text(
        narration,
        language
    )


    result[
        "narration"
    ] = narration


    return result


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    sample = {

        "source_ip":
            "127.0.0.1",

        "threat_type":
            "HONEYPOT RECONNAISSANCE",

        "risk_score":
            87,

        "action":
            "CONTAINED",

        "geo": {
            "available":
                False,

            "classification":
                "LOOPBACK"
        }
    }


    narration = build_narration(
        sample,
        "fr"
    )


    return {

        "status":
            "PASS"
            if narration
            else
            "FAIL",

        "version":
            NARRATION_VERSION,

        "espeak_ng":
            shutil.which(
                "espeak-ng"
            )
            is not None,

        "default_language":
            DEFAULT_LANGUAGE,

        "french_voice":
            "fr+f3",

        "english_voice":
            "en-us+f3",

        "shell":
            False,

        "sample_narration":
            narration
    }


if __name__ == "__main__":

    import pprint

    pprint.pp(
        self_test()
    )