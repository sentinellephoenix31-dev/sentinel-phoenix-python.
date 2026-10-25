import json
import os
import secrets

from datetime import datetime, timezone

from core.semantic import (
    route_question
)

from core.brain_memory import (
    answer_semantic_question
)

from core.internet_gateway import (
    classify_external_question,
    answer_internet_question
)


# ============================================================
# SENTINEL PHOENIX
# BRAIN CONVERSATION CORE V4
#
# LOCAL MEMORY
# + SEMANTIC UNDERSTANDING
# + CONTEXT TIMELINE
# + CONTROLLED INTERNET KNOWLEDGE
# ============================================================


CONVERSATION_VERSION = "4.0"


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

CONVERSATION_LOG = os.path.join(
    DATA_DIR,
    "brain_conversations.jsonl"
)

MAX_HISTORY = 40


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def new_session_id():

    return (
        "brain-"
        +
        secrets.token_hex(8)
    )


def log_event(event):

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    with open(
        CONVERSATION_LOG,
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            json.dumps(
                event,
                ensure_ascii=False
            )
            +
            "\n"
        )


# ============================================================
# HELP
# ============================================================

def help_message(
    language="EN"
):

    if language == "FR":

        return (
            "Tu peux me parler naturellement.\n"
            "\n"
            "Mémoire Sentinel :\n"
            "- Qu'est-ce qui s'est passé aujourd'hui ?\n"
            "- Il y a eu quelque chose de bizarre cette nuit ?\n"
            "- Qu'est-ce qui s'est passé cette semaine ?\n"
            "- Quel était l'incident le plus dangereux ?\n"
            "- Qu'est-ce qui s'est passé entre 14h et 18h ?\n"
            "- Qu'est-ce qui s'est passé pendant mon absence ?\n"
            "- Que sais-tu sur 127.0.0.1 ?\n"
            "\n"
            "Connaissance Internet :\n"
            "- Que sais-tu sur CVE-2021-44228 ?\n"
            "- Recherche NVD Log4j.\n"
            "- Cherche les vulnérabilités OpenSSH.\n"
            "\n"
            "Les informations Internet sont consultatives "
            "uniquement et ne peuvent pas exécuter de commandes "
            "ou modifier l'hôte."
        )

    return (
        "You can speak naturally.\n"
        "\n"
        "Sentinel memory:\n"
        "- What happened today?\n"
        "- Anything suspicious overnight?\n"
        "- What happened this week?\n"
        "- What was the most dangerous incident?\n"
        "- What happened between 2pm and 6pm?\n"
        "- What happened while I was away?\n"
        "- What do you know about 127.0.0.1?\n"
        "\n"
        "Internet knowledge:\n"
        "- Tell me about CVE-2021-44228.\n"
        "- Search NVD for Log4j.\n"
        "- Search vulnerabilities affecting OpenSSH.\n"
        "\n"
        "Internet information is advisory only and cannot "
        "execute commands or modify the host."
    )


# ============================================================
# SYSTEM STATUS
# ============================================================

def system_status(
    language="EN"
):

    # ========================================================
    # INTEGRITY
    # ========================================================

    try:

        from core.integrity import (
            verify_integrity
        )

        integrity = verify_integrity(
            log_result=False
        )

        integrity_status = integrity.get(
            "status",
            "UNKNOWN"
        )

    except Exception:

        integrity_status = "UNKNOWN"

    # ========================================================
    # LEARNING
    # ========================================================

    try:

        from core.learning import (
            get_learning_status
        )

        learning = get_learning_status()

        learning_status = learning.get(
            "status",
            "UNKNOWN"
        )

        model_version = learning.get(
            "version",
            "UNKNOWN"
        )

    except Exception:

        learning_status = "UNKNOWN"
        model_version = "UNKNOWN"

    # ========================================================
    # RESPONSE
    # ========================================================

    if language == "FR":

        return (
            "État de Sentinel Phoenix :\n"
            f"- Intégrité du cœur : {integrity_status}\n"
            f"- Modèle d'apprentissage : {learning_status}\n"
            f"- Version du modèle : {model_version}\n"
            "- Cerveau conversationnel : ONLINE\n"
            "- Compréhension sémantique : ONLINE\n"
            "- Timeline contextuelle : ONLINE\n"
            "- Mémoire locale : ONLINE\n"
            "- Internet Knowledge Gateway : ONLINE\n"
            "- Internet → shell : INTERDIT\n"
            "- Internet → payload : INTERDIT\n"
            "- Internet → patch automatique : INTERDIT\n"
            "- Modification hôte par Internet : INTERDITE"
        )

    return (
        "Sentinel Phoenix status:\n"
        f"- Core integrity: {integrity_status}\n"
        f"- Learning model: {learning_status}\n"
        f"- Model version: {model_version}\n"
        "- Conversation brain: ONLINE\n"
        "- Semantic understanding: ONLINE\n"
        "- Context timeline: ONLINE\n"
        "- Local memory: ONLINE\n"
        "- Internet Knowledge Gateway: ONLINE\n"
        "- Internet -> shell: DISABLED\n"
        "- Internet -> payload: DISABLED\n"
        "- Internet -> automatic patching: DISABLED\n"
        "- Internet host modification: DISABLED"
    )


# ============================================================
# BRAIN CONVERSATION
# ============================================================

class BrainConversation:

    def __init__(self):

        self.session_id = new_session_id()

        self.created_at = utc_now()

        self.active = True

        self.history = []

        self.last_semantic = None

        self.last_route = None

        self.last_external = None


    # ========================================================
    # HISTORY
    # ========================================================

    def remember(
        self,
        role,
        text,
        semantic=None,
        route_mode=None,
        knowledge_source=None
    ):

        event = {

            "timestamp":
                utc_now(),

            "role":
                role,

            "text":
                str(text)[:6000],

            "route_mode":
                route_mode,

            "knowledge_source":
                knowledge_source
        }

        if semantic:

            event["semantic"] = {

                "intent":
                    semantic.get(
                        "intent"
                    ),

                "time_range":
                    semantic.get(
                        "time_range"
                    ),

                "presence_context":
                    semantic.get(
                        "presence_context"
                    ),

                "source_ip":
                    semantic.get(
                        "source_ip"
                    ),

                "intent_confidence":
                    semantic.get(
                        "intent_confidence"
                    )
            }

        self.history.append(
            event
        )

        self.history = self.history[
            -MAX_HISTORY:
        ]

        log_event(
            {
                "session_id":
                    self.session_id,

                **event
            }
        )


    # ========================================================
    # LOCAL ANSWER
    # ========================================================

    def answer_local(
        self,
        question,
        semantic
    ):

        response = answer_semantic_question(
            question,
            semantic
        )

        return {

            "response":
                response,

            "route":
                "LOCAL",

            "knowledge_source":
                "SENTINEL_MEMORY",

            "external":
                False
        }


    # ========================================================
    # INTERNET ANSWER
    # ========================================================

    def answer_external(
        self,
        question,
        language
    ):

        result = answer_internet_question(
            question,
            language
        )

        self.last_external = result

        if not result.get(
            "ok"
        ):

            reason = result.get(
                "reason",
                "UNKNOWN_EXTERNAL_ERROR"
            )

            if language == "FR":

                response = (
                    "Je n'ai pas pu obtenir cette information "
                    "externe de manière sûre. "
                    f"Raison : {reason}."
                )

            else:

                response = (
                    "I could not retrieve that external "
                    "information safely. "
                    f"Reason: {reason}."
                )

        else:

            response = result.get(
                "answer",
                ""
            )

        return {

            "response":
                response,

            "route":
                "INTERNET",

            "knowledge_source":
                "NVD/NIST",

            "external":
                True,

            "external_result":
                result
        }


    # ========================================================
    # ANSWER
    # ========================================================

    def answer(
        self,
        question
    ):

        question = str(
            question
        ).strip()

        if not question:

            return {

                "status":
                    "EMPTY",

                "response":
                    "I didn't receive a question.",

                "continue":
                    True,

                "route":
                    None
            }

        # ====================================================
        # SEMANTIC ANALYSIS
        # ====================================================

        semantic = route_question(
            question
        )

        self.last_semantic = semantic

        language = semantic.get(
            "language",
            "EN"
        )

        intent = semantic.get(
            "intent"
        )

        # ====================================================
        # EXTERNAL KNOWLEDGE ANALYSIS
        # ====================================================

        external_route = (
            classify_external_question(
                question
            )
        )

        # ====================================================
        # LOCAL CONTROL COMMANDS ALWAYS WIN
        # ====================================================

        if intent == "EXIT":

            route_mode = "LOCAL"

            knowledge_source = (
                "CONVERSATION_CONTROL"
            )

            self.remember(
                "USER",
                question,
                semantic,
                route_mode,
                knowledge_source
            )

            response = (
                "Session Sentinel fermée."
                if language == "FR"
                else
                "Sentinel conversation session closed."
            )

            self.active = False

            self.remember(
                "SENTINEL",
                response,
                semantic,
                route_mode,
                knowledge_source
            )

            return {

                "status":
                    "EXIT",

                "response":
                    response,

                "continue":
                    False,

                "route":
                    route_mode,

                "knowledge_source":
                    knowledge_source,

                "semantic":
                    semantic
            }

        # ====================================================
        # HELP
        # ====================================================

        if intent == "HELP":

            route_mode = "LOCAL"

            knowledge_source = (
                "CONVERSATION_CONTROL"
            )

            self.remember(
                "USER",
                question,
                semantic,
                route_mode,
                knowledge_source
            )

            response = help_message(
                language
            )

            self.remember(
                "SENTINEL",
                response,
                semantic,
                route_mode,
                knowledge_source
            )

            return {

                "status":
                    "ANSWERED",

                "response":
                    response,

                "continue":
                    True,

                "route":
                    route_mode,

                "knowledge_source":
                    knowledge_source,

                "semantic":
                    semantic
            }

        # ====================================================
        # STATUS
        # ====================================================

        if intent == "SYSTEM_STATUS":

            route_mode = "LOCAL"

            knowledge_source = (
                "SENTINEL_INTERNAL"
            )

            self.remember(
                "USER",
                question,
                semantic,
                route_mode,
                knowledge_source
            )

            response = system_status(
                language
            )

            self.remember(
                "SENTINEL",
                response,
                semantic,
                route_mode,
                knowledge_source
            )

            return {

                "status":
                    "ANSWERED",

                "response":
                    response,

                "continue":
                    True,

                "route":
                    route_mode,

                "knowledge_source":
                    knowledge_source,

                "semantic":
                    semantic
            }

        # ====================================================
        # KNOWLEDGE ROUTER
        # ====================================================

        if external_route.get(
            "external"
        ):

            route_result = self.answer_external(
                question,
                language
            )

        else:

            try:

                route_result = self.answer_local(
                    question,
                    semantic
                )

            except Exception as error:

                if language == "FR":

                    response = (
                        "Je n'ai pas pu traiter la demande "
                        "locale en sécurité. "
                        f"Raison : {error}"
                    )

                else:

                    response = (
                        "I could not process the local "
                        "request safely. "
                        f"Reason: {error}"
                    )

                route_result = {

                    "response":
                        response,

                    "route":
                        "LOCAL",

                    "knowledge_source":
                        "SENTINEL_MEMORY",

                    "external":
                        False
                }

        route_mode = route_result[
            "route"
        ]

        knowledge_source = route_result[
            "knowledge_source"
        ]

        self.last_route = route_mode

        # ====================================================
        # LOG USER
        # ====================================================

        self.remember(
            "USER",
            question,
            semantic,
            route_mode,
            knowledge_source
        )

        # ====================================================
        # LOG SENTINEL
        # ====================================================

        response = route_result[
            "response"
        ]

        self.remember(
            "SENTINEL",
            response,
            semantic,
            route_mode,
            knowledge_source
        )

        return {

            "status":
                "ANSWERED",

            "response":
                response,

            "continue":
                True,

            "route":
                route_mode,

            "knowledge_source":
                knowledge_source,

            "external":
                route_result.get(
                    "external",
                    False
                ),

            "semantic":
                semantic,

            "session_id":
                self.session_id,

            "history_size":
                len(
                    self.history
                ),

            "safety":
                {

                    "internet_information_only":
                        True,

                    "internet_shell_execution":
                        False,

                    "internet_payload_execution":
                        False,

                    "internet_patching":
                        False,

                    "internet_host_modification":
                        False
                }
        }


    # ========================================================
    # SESSION STATUS
    # ========================================================

    def status(self):

        return {

            "session_id":
                self.session_id,

            "version":
                CONVERSATION_VERSION,

            "created_at":
                self.created_at,

            "active":
                self.active,

            "history_size":
                len(
                    self.history
                ),

            "last_route":
                self.last_route,

            "last_semantic":
                self.last_semantic,

            "safety":
                {

                    "internet_information_only":
                        True,

                    "internet_shell_execution":
                        False,

                    "internet_payload_execution":
                        False,

                    "internet_patching":
                        False,

                    "internet_host_modification":
                        False
                }
        }


# ============================================================
# INTERACTIVE CONSOLE
# ============================================================

def run_console():

    conversation = (
        BrainConversation()
    )

    print(
        "=" * 74
    )

    print(
        "SENTINEL PHOENIX"
    )

    print(
        "BRAIN CONVERSATION CORE V4"
    )

    print(
        "LOCAL MEMORY + SEMANTIC + INTERNET KNOWLEDGE"
    )

    print(
        "=" * 74
    )

    print(
        "Speak naturally in English or French."
    )

    print(
        "Type 'help' for examples."
    )

    print(
        "Type 'exit' to close."
    )

    print("")

    while conversation.active:

        try:

            question = input(
                "YOU > "
            )

        except (
            KeyboardInterrupt,
            EOFError
        ):

            print("")
            break

        result = conversation.answer(
            question
        )

        print("")

        print(
            "SENTINEL > "
            +
            result.get(
                "response",
                ""
            )
        )

        print("")

        print(
            "[ROUTE] "
            f"{result.get('route')} | "
            f"Source="
            f"{result.get('knowledge_source')}"
        )

        semantic = result.get(
            "semantic",
            {}
        )

        print(
            "[SEMANTIC] "
            f"Intent="
            f"{semantic.get('intent')} | "
            f"Time="
            f"{semantic.get('time_range')} | "
            f"Context="
            f"{semantic.get('presence_context')}"
        )

        print("")

    return 0


# ============================================================
# OFFLINE SELF TEST
# ============================================================

def self_test():

    conversation = BrainConversation()

    # ========================================================
    # LOCAL QUERY
    # ========================================================

    local_result = conversation.answer(
        "What happened today?"
    )

    # ========================================================
    # EXTERNAL ROUTING CHECK
    #
    # Do NOT actually contact Internet in the offline self-test.
    # We verify the classifier separately.
    # ========================================================

    external_route = classify_external_question(
        "Tell me about CVE-2021-44228"
    )

    external_detected = bool(
        external_route.get(
            "external"
        )
    )

    external_type = external_route.get(
        "type"
    )

    # ========================================================
    # LOCAL MUST STAY LOCAL
    # ========================================================

    local_ok = (
        local_result.get(
            "route"
        )
        ==
        "LOCAL"
    )

    # ========================================================
    # EXTERNAL MUST BE IDENTIFIED
    # ========================================================

    external_ok = (
        external_detected
        and
        external_type
        ==
        "CVE_LOOKUP"
    )

    passed = (
        local_ok
        and
        external_ok
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
            CONVERSATION_VERSION,

        "local_test":
            {

                "route":
                    local_result.get(
                        "route"
                    ),

                "source":
                    local_result.get(
                        "knowledge_source"
                    ),

                "passed":
                    local_ok
            },

        "external_test":
            {

                "external":
                    external_detected,

                "type":
                    external_type,

                "passed":
                    external_ok
            },

        "network_used_by_self_test":
            False,

        "safety":
            {

                "internet_information_only":
                    True,

                "internet_shell_execution":
                    False,

                "internet_payload_execution":
                    False,

                "internet_patching":
                    False,

                "internet_host_modification":
                    False
            }
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        run_console()
    )