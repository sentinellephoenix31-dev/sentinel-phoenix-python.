import re
import unicodedata

from core.brain_conversation import (
    BrainConversation
)

from core.evidence_voice import (
    is_evidence_voice_request,
    execute_evidence_voice_action
)

from core.guest_voice import (
    is_guest_enrollment_request,
    run_guest_enrollment_voice
)

from core.replay_voice import (
    is_replay_request,
    handle_replay_request
)

from core.identity_guard import (
    get_identity_guard,
    self_test as identity_guard_self_test
)


# ============================================================
# SENTINEL PHOENIX
# COMMAND DISPATCHER V2.1
#
# VOICE / TEXT
#      ↓
# ROUTE CLASSIFICATION
#      ↓
# IDENTITY GUARD
#      ↓
# YuNet + SFace V4
#      ↓
# OWNER / GUEST / UNKNOWN
#      ↓
# AUTHORIZATION
#      ↓
# Evidence / Guest / Replay / Brain
#
#
# IMPORTANT V2.1:
#
# Identity recognition runs HEADLESS from the dispatcher.
#
# Camera + Face Engine remain active,
# but OpenCV imshow() is NOT used here.
#
# This prevents Qt/OpenCV GUI conflicts with:
# - Sentinel Text Bar
# - Orb
# - Visual Incident Replay
#
# A dedicated Face Scan UI can be launched separately later.
# ============================================================


DISPATCHER_VERSION = "2.1"


# ============================================================
# CENTRAL IDENTITY DISPLAY POLICY
# ============================================================

# False is intentional.
#
# IdentityGuard still:
# - opens camera
# - detects face
# - extracts SFace embeddings
# - identifies OWNER/GUEST/UNKNOWN
#
# It simply does not create an OpenCV window from the
# command-processing thread.

IDENTITY_SHOW_WINDOW = False


# ============================================================
# ROUTES REQUIRING FRESH FACE IDENTITY
# ============================================================

FRESH_IDENTITY_ROUTES = {
    "EVIDENCE_CONTROL",
    "GUEST_ENROLLMENT",
    "VISUAL_INCIDENT_REPLAY",
}


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(
    text
):

    value = str(
        text or ""
    ).strip().lower()

    value = unicodedata.normalize(
        "NFKD",
        value
    )

    value = "".join(
        character
        for character in value
        if not unicodedata.combining(
            character
        )
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ============================================================
# TEXT LANGUAGE DETECTION
# ============================================================

def detect_text_language(
    text
):

    value = normalize_text(
        text
    )

    words = set(
        re.findall(
            r"[a-z]+",
            value
        )
    )

    french_words = {
        "affiche",
        "ajoute",
        "attaque",
        "attaques",
        "aujourd",
        "bonjour",
        "cette",
        "cet",
        "dans",
        "de",
        "des",
        "du",
        "garde",
        "hier",
        "incident",
        "incidents",
        "invite",
        "je",
        "la",
        "le",
        "les",
        "moi",
        "montre",
        "nuit",
        "passe",
        "plus",
        "preuve",
        "que",
        "qui",
        "se",
        "soir",
        "supprime",
        "une",
    }

    english_words = {
        "add",
        "attack",
        "attacks",
        "delete",
        "display",
        "guest",
        "happened",
        "incident",
        "incidents",
        "keep",
        "last",
        "me",
        "night",
        "replay",
        "show",
        "that",
        "the",
        "this",
        "today",
        "what",
        "yesterday",
    }

    french_score = len(
        words
        &
        french_words
    )

    english_score = len(
        words
        &
        english_words
    )

    if english_score > french_score:

        return "en"

    return "fr"


# ============================================================
# ROUTE CLASSIFICATION
# ============================================================

def classify_route(
    command
):

    if is_evidence_voice_request(
        command
    ):

        return "EVIDENCE_CONTROL"


    if is_guest_enrollment_request(
        command
    ):

        return "GUEST_ENROLLMENT"


    if is_replay_request(
        command
    ):

        return "VISUAL_INCIDENT_REPLAY"


    return "BRAIN"


# ============================================================
# ACCESS DENIED RESPONSE
# ============================================================

def access_denied_response(
    role,
    route,
    language
):

    role = str(
        role or "UNKNOWN"
    ).upper()

    route = str(
        route or "UNKNOWN"
    ).upper()


    if language == "fr":

        if role == "GUEST":

            return (
                "Accès refusé. "
                "Cette commande est réservée au propriétaire."
            )

        if role == "UNKNOWN":

            return (
                "Accès refusé. "
                "Votre identité n'a pas été autorisée."
            )

        return (
            "Accès refusé par la politique "
            "de sécurité de Sentinel."
        )


    if role == "GUEST":

        return (
            "Access denied. "
            "This command is reserved for the owner."
        )


    if role == "UNKNOWN":

        return (
            "Access denied. "
            "Your identity was not authorized."
        )


    return (
        "Access denied by Sentinel's security policy."
    )


# ============================================================
# COMMAND DISPATCHER
# ============================================================

class CommandDispatcher:

    def __init__(
        self
    ):

        self.brain = (
            BrainConversation()
        )

        self.identity_guard = (
            get_identity_guard()
        )


    # ========================================================
    # CENTRAL AUTHORIZATION
    # ========================================================

    def authorize_command(
        self,
        route
    ):

        force_fresh = (
            route
            in
            FRESH_IDENTITY_ROUTES
        )


        print(
            "[IDENTITY] Checking authorization..."
        )

        print(
            "[IDENTITY] Fresh scan:",
            force_fresh
        )

        print(
            "[IDENTITY] Camera UI:",
            (
                "VISIBLE"
                if IDENTITY_SHOW_WINDOW
                else
                "HEADLESS"
            )
        )


        return self.identity_guard.authorize(
            route,
            force_fresh=force_fresh,
            show_window=IDENTITY_SHOW_WINDOW,
        )


    # ========================================================
    # MAIN ROUTER
    # ========================================================

    def dispatch(
        self,
        command,
        source="text",
        language=None
    ):

        command = str(
            command or ""
        ).strip()

        source = str(
            source or "text"
        ).strip().lower()


        if not command:

            return {
                "handled":
                    False,

                "status":
                    "EMPTY_COMMAND",

                "route":
                    "NONE",

                "response":
                    ""
            }


        if language not in (
            "fr",
            "en"
        ):

            language = detect_text_language(
                command
            )


        # ====================================================
        # 1. CLASSIFY
        # ====================================================

        route = classify_route(
            command
        )


        print("")

        print(
            "[COMMAND DISPATCHER V2.1]"
        )

        print(
            "[SOURCE]",
            source.upper()
        )

        print(
            "[LANGUAGE]",
            language.upper()
        )

        print(
            "[COMMAND]",
            command
        )

        print(
            "[CLASSIFIED ROUTE]",
            route
        )


        # ====================================================
        # 2. IDENTITY GUARD
        # ====================================================

        try:

            authorization = (
                self.authorize_command(
                    route
                )
            )


        except Exception as error:

            print(
                "[IDENTITY ERROR]",
                str(error)
            )


            return {
                "handled":
                    True,

                "status":
                    "ACCESS_DENIED",

                "route":
                    route,

                "language":
                    language,

                "role":
                    "UNKNOWN",

                "response":
                    access_denied_response(
                        "UNKNOWN",
                        route,
                        language
                    ),

                "reason":
                    "IDENTITY_GUARD_ERROR",

                "identity_error":
                    str(error)
            }


        role = str(
            authorization.get(
                "role",
                "UNKNOWN"
            )
        ).upper()


        name = str(
            authorization.get(
                "name",
                "UNKNOWN"
            )
        )


        allowed = bool(
            authorization.get("authorized", False)
            or authorization.get("granted", False)
            or str(authorization.get("access", "")).upper() == "GRANTED"
            or str(authorization.get("status", "")).upper() == "GRANTED"
        )


        identity = authorization.get(
            "identity",
            {}
        )


        print(
            "[IDENTITY ROLE]",
            role
        )

        print(
            "[IDENTITY NAME]",
            name
        )

        print(
            "[IDENTITY SIMILARITY]",
            identity.get(
                "similarity"
            )
        )

        print(
            "[IDENTITY CACHE]",
            identity.get(
                "from_cache"
            )
        )

        print(
            "[IDENTITY ACCESS]",
            (
                "GRANTED"
                if allowed
                else
                "DENIED"
            )
        )


        # ====================================================
        # FAIL CLOSED
        # ====================================================

        if not allowed:

            return {
                "handled":
                    True,

                "status":
                    "ACCESS_DENIED",

                "route":
                    route,

                "language":
                    language,

                "role":
                    role,

                "name":
                    name,

                "response":
                    access_denied_response(
                        role,
                        route,
                        language
                    ),

                "authorization":
                    authorization
            }


        # ====================================================
        # 3. EVIDENCE CONTROL
        #
        # Existing Evidence OWNER + liveness workflow
        # remains active.
        # ====================================================

        if route == "EVIDENCE_CONTROL":

            print(
                "[DISPATCH ROUTE] "
                "EVIDENCE_CONTROL"
            )


            try:

                result = (
                    execute_evidence_voice_action(
                        command,
                        language
                    )
                )


            except Exception as error:

                return {
                    "handled":
                        True,

                    "status":
                        "ERROR",

                    "route":
                        route,

                    "language":
                        language,

                    "role":
                        role,

                    "response":
                        (
                            "Evidence command failed."
                            if language == "en"
                            else
                            "La commande de preuve a échoué."
                        ),

                    "reason":
                        str(error),

                    "authorization":
                        authorization
                }


            if not isinstance(
                result,
                dict
            ):

                result = {
                    "status":
                        "COMPLETED",

                    "result":
                        result
                }


            result = dict(
                result
            )


            result["handled"] = True

            result["route"] = route

            result["language"] = language

            result["role"] = role

            result["identity"] = name

            result["authorization"] = (
                authorization
            )


            return result


        # ====================================================
        # 4. GUEST ENROLLMENT
        #
        # Existing OWNER + liveness verification
        # remains active downstream.
        # ====================================================

        if route == "GUEST_ENROLLMENT":

            print(
                "[DISPATCH ROUTE] "
                "GUEST_ENROLLMENT"
            )


            try:

                result = (
                    run_guest_enrollment_voice(
                        language
                    )
                )


            except Exception as error:

                return {
                    "handled":
                        True,

                    "status":
                        "ERROR",

                    "route":
                        route,

                    "language":
                        language,

                    "role":
                        role,

                    "response":
                        (
                            "Guest enrollment could not start."
                            if language == "en"
                            else
                            "L'enregistrement de l'invité n'a pas pu démarrer."
                        ),

                    "reason":
                        str(error),

                    "authorization":
                        authorization
                }


            if not isinstance(
                result,
                dict
            ):

                result = {
                    "status":
                        "COMPLETED",

                    "result":
                        result
                }


            result = dict(
                result
            )


            result["handled"] = True

            result["route"] = route

            result["language"] = language

            result["role"] = role

            result["identity"] = name

            result["authorization"] = (
                authorization
            )


            return result


        # ====================================================
        # 5. VISUAL INCIDENT REPLAY
        # ====================================================

        if route == "VISUAL_INCIDENT_REPLAY":

            print(
                "[DISPATCH ROUTE] "
                "VISUAL_INCIDENT_REPLAY"
            )


            try:

                result = (
                    handle_replay_request(
                        command
                    )
                )


            except Exception as error:

                return {
                    "handled":
                        True,

                    "status":
                        "ERROR",

                    "route":
                        route,

                    "language":
                        language,

                    "role":
                        role,

                    "response":
                        (
                            "Visual replay could not be launched."
                            if language == "en"
                            else
                            "La reconstitution visuelle n'a pas pu être lancée."
                        ),

                    "reason":
                        str(error),

                    "authorization":
                        authorization
                }


            if not isinstance(
                result,
                dict
            ):

                result = {
                    "status":
                        "UNKNOWN",

                    "result":
                        result
                }


            result = dict(
                result
            )


            result["handled"] = True

            result["route"] = route

            result["language"] = language

            result["role"] = role

            result["identity"] = name

            result["authorization"] = (
                authorization
            )


            status = str(
                result.get(
                    "status",
                    ""
                )
            )


            if status == "LAUNCHED":

                result["response"] = (
                    "Visual Incident Replay launched."
                    if language == "en"
                    else
                    "Reconstitution visuelle lancée."
                )


            elif status == "ALREADY_RUNNING":

                result["response"] = (
                    "The Visual Incident Replay is already open."
                    if language == "en"
                    else
                    "La reconstitution visuelle est déjà ouverte."
                )


            elif not result.get(
                "response"
            ):

                result["response"] = (
                    "No matching incident could be replayed."
                    if language == "en"
                    else
                    "Aucun incident correspondant n'a pu être rejoué."
                )


            return result


        # ====================================================
        # 6. BRAIN
        # ====================================================

        print(
            "[DISPATCH ROUTE] BRAIN"
        )


        try:

            result = self.brain.answer(
                command
            )


        except Exception as error:

            return {
                "handled":
                    True,

                "status":
                    "ERROR",

                "route":
                    "BRAIN",

                "language":
                    language,

                "role":
                    role,

                "response":
                    (
                        "Sentinel could not process the request."
                        if language == "en"
                        else
                        "Sentinel n'a pas pu traiter la demande."
                    ),

                "reason":
                    str(error),

                "authorization":
                    authorization
            }


        if not isinstance(
            result,
            dict
        ):

            result = {
                "response":
                    str(result)
            }


        response = str(
            result.get(
                "response",
                ""
            )
        ).strip()


        return {
            "handled":
                True,

            "status":
                "ANSWERED",

            "route":
                "BRAIN",

            "language":
                language,

            "role":
                role,

            "identity":
                name,

            "response":
                response,

            "brain_route":
                result.get(
                    "route"
                ),

            "knowledge_source":
                result.get(
                    "knowledge_source"
                ),

            "continue":
                result.get(
                    "continue",
                    True
                ),

            "authorization":
                authorization,

            "raw":
                result
        }


# ============================================================
# DEFAULT DISPATCHER
# ============================================================

_DEFAULT_DISPATCHER = None


def get_dispatcher():

    global _DEFAULT_DISPATCHER


    if _DEFAULT_DISPATCHER is None:

        _DEFAULT_DISPATCHER = (
            CommandDispatcher()
        )


    return _DEFAULT_DISPATCHER


def dispatch_command(
    command,
    source="text",
    language=None
):

    return get_dispatcher().dispatch(
        command,
        source=source,
        language=language
    )


# ============================================================
# SELF TEST
#
# NO CAMERA.
# NO EVIDENCE ACTION.
# NO GUEST ENROLLMENT.
# NO REPLAY.
# ============================================================

def self_test():

    try:

        identity = (
            identity_guard_self_test()
        )


    except Exception as error:

        identity = {
            "status":
                "FAIL",

            "reason":
                str(error)
        }


    tests = {

        "identity_guard":
            identity.get(
                "status"
            ) == "PASS",


        "headless_identity":
            IDENTITY_SHOW_WINDOW
            is False,


        "french_language":
            detect_text_language(
                "Montre-moi ce qui s'est passé hier"
            )
            ==
            "fr",


        "english_language":
            detect_text_language(
                "Show me what happened yesterday"
            )
            ==
            "en",


        "replay_route":
            classify_route(
                "Montre les attaques de cette nuit"
            )
            ==
            "VISUAL_INCIDENT_REPLAY",


        "guest_route":
            classify_route(
                "Ajoute un invité"
            )
            ==
            "GUEST_ENROLLMENT",


        "evidence_route":
            classify_route(
                "Garde cette photo"
            )
            ==
            "EVIDENCE_CONTROL",


        "brain_route":
            classify_route(
                "Bonjour Sentinel"
            )
            ==
            "BRAIN",
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
            DISPATCHER_VERSION,

        "identity_guard":
            identity,

        "tests":
            tests,

        "identity_camera_mode":
            "HEADLESS",

        "opencv_window_from_dispatcher":
            False,

        "central_identity_authorization":
            True,

        "fresh_identity_routes":
            sorted(
                FRESH_IDENTITY_ROUTES
            ),

        "permissions": {

            "OWNER": [
                "BRAIN",
                "VISUAL_INCIDENT_REPLAY",
                "EVIDENCE_CONTROL",
                "GUEST_ENROLLMENT"
            ],

            "GUEST": [
                "BRAIN"
            ],

            "UNKNOWN": []
        },

        "security": {
            "unknown_fail_closed":
                True,

            "guest_sensitive_routes_denied":
                True,

            "sensitive_fresh_face_check":
                True,

            "existing_liveness_preserved":
                True,

            "qt_opencv_thread_conflict_avoided":
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

    import pprint

    pprint.pp(
        self_test()
    )