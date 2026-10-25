import socket
import threading

from core.config import (
    HONEYPOT_HOST,
    HONEYPOT_PORT,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    MAX_PAYLOAD_SIZE
)

from core.analyser import (
    analyze_payload
)

from core.behavior import (
    analyze_behavior
)

from core.anomaly import (
    analyze_anomaly
)

from core.reputation import (
    evaluate_reputation
)

from core.learning import (
    evaluate_learning,
    get_learning_status,
    maybe_retrain_model
)

from core.fusion import (
    fuse_risk
)

from core.context_engine import (
    build_context
)

from core.policy import (
    apply_policy
)

from core.events import (
    record_event
)

from core.dashboard import (
    run_dashboard
)

from core.deception import (
    route_to_decoy,
    no_decoy,
    has_active_decoy
)

from core.sandbox import (
    create_sandbox
)

from core.lifecycle import (
    start_lifecycle_manager
)

from core.memory import (
    remember_event,
    get_source_memory,
    get_memory_stats
)

from core.integrity_guard import (
    preflight_integrity_check,
    print_integrity_report
)


# ============================================================
# SENTINEL PHOENIX
# MAIN CORE
# INTEGRITY GUARD V2
# ============================================================


def empty_sandbox():

    return {
        "sandbox_active": False,
        "sandbox_name": None,
        "sandbox_id": None,
        "sandbox_reused": False,
        "sandbox_network": "NONE",
        "sandbox_read_only": True,
        "sandbox_privileged": False,
        "payload_execution": False,
        "sandbox_error": None
    }


# ============================================================
# HONEYPOT
# ============================================================

def run_honeypot():

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server.bind(
        (
            HONEYPOT_HOST,
            HONEYPOT_PORT
        )
    )

    server.listen(5)

    print(
        f"[+] Honeypot actif : "
        f"{HONEYPOT_HOST}:"
        f"{HONEYPOT_PORT}"
    )

    print(
        "[+] En attente de connexions..."
    )

    try:

        while True:

            client = None

            try:

                client, address = (
                    server.accept()
                )

                source_ip = (
                    address[0]
                )

                source_port = (
                    address[1]
                )

                client.settimeout(
                    2
                )

                # =================================================
                # CAPTURE
                # =================================================

                try:

                    raw_data = (
                        client.recv(
                            MAX_PAYLOAD_SIZE
                        )
                    )

                except socket.timeout:

                    raw_data = b""

                payload = raw_data.decode(
                    "utf-8",
                    errors="replace"
                ).strip()

                # =================================================
                # ENGINE 1
                # PAYLOAD
                # =================================================

                analysis = (
                    analyze_payload(
                        payload
                    )
                )

                # =================================================
                # ENGINE 2
                # BEHAVIOR
                # =================================================

                behavior = (
                    analyze_behavior(
                        source_ip,
                        analysis
                    )
                )

                # =================================================
                # ENGINE 3
                # ANOMALY
                # =================================================

                anomaly = (
                    analyze_anomaly(
                        source_ip,
                        payload
                    )
                )

                # =================================================
                # ENGINE 4
                # REPUTATION
                # =================================================

                reputation = (
                    evaluate_reputation(
                        source_ip
                    )
                )

                # =================================================
                # ENGINE 5
                # LEARNING
                # =================================================

                learning = (
                    evaluate_learning(
                        analysis,
                        behavior,
                        anomaly,
                        reputation
                    )
                )

                # =================================================
                # ENGINE 6
                # RISK FUSION
                # =================================================

                fusion = (
                    fuse_risk(
                        analysis,
                        behavior,
                        anomaly,
                        reputation,
                        learning
                    )
                )

                # =================================================
                # ENGINE 7
                # CONTEXT
                # =================================================

                context = (
                    build_context(
                        analysis,
                        behavior,
                        anomaly,
                        reputation,
                        fusion
                    )
                )

                # =================================================
                # ENGINE 8
                # POLICY
                # =================================================

                response = (
                    apply_policy(
                        source_ip,
                        fusion,
                        behavior,
                        anomaly,
                        context
                    )
                )

                # =================================================
                # ENGINE 9
                # DECEPTION
                # =================================================

                already_contained = (
                    has_active_decoy(
                        source_ip
                    )
                )

                if (
                    response.get(
                        "containment_requested",
                        False
                    )
                    or
                    already_contained
                ):

                    deception = (
                        route_to_decoy(
                            source_ip,
                            source_port,
                            payload,
                            fusion,
                            response
                        )
                    )

                else:

                    deception = (
                        no_decoy()
                    )

                # =================================================
                # ENGINE 10
                # SANDBOX
                # =================================================

                sandbox = (
                    empty_sandbox()
                )

                if deception.get(
                    "decoy_active",
                    False
                ):

                    session_id = (
                        deception.get(
                            "decoy_session_id"
                        )
                    )

                    try:

                        sandbox = (
                            create_sandbox(
                                session_id
                            )
                        )

                    except Exception as error:

                        sandbox = (
                            empty_sandbox()
                        )

                        sandbox[
                            "sandbox_error"
                        ] = str(
                            error
                        )

                # =================================================
                # EVENT LOG
                # =================================================

                try:

                    record_event(
                        ip=source_ip,
                        port=source_port,
                        payload=payload,
                        analysis=analysis,
                        behavior=behavior,
                        anomaly=anomaly,
                        reputation=reputation,
                        learning=learning,
                        fusion=fusion,
                        context=context,
                        response=response,
                        deception=deception,
                        sandbox=sandbox
                    )

                except Exception as error:

                    print(
                        "[EVENT ERROR] "
                        f"{error}"
                    )

                # =================================================
                # LONG TERM MEMORY
                # =================================================

                memory = None

                try:

                    remember_event(
                        source_ip=source_ip,
                        source_port=source_port,
                        payload=payload,
                        analysis=analysis,
                        behavior=behavior,
                        anomaly=anomaly,
                        fusion=fusion,
                        response=response,
                        deception=deception,
                        sandbox=sandbox
                    )

                    memory = (
                        get_source_memory(
                            source_ip
                        )
                    )

                except Exception as error:

                    print(
                        "[MEMORY ERROR] "
                        f"{error}"
                    )

                # =================================================
                # CONTROLLED LEARNING UPDATE
                # =================================================

                learning_update = None

                try:

                    learning_update = (
                        maybe_retrain_model()
                    )

                except Exception as error:

                    print(
                        "[LEARNING UPDATE ERROR] "
                        f"{error}"
                    )

                # =================================================
                # TERMINAL OUTPUT
                # =================================================

                print("")
                print(
                    "=" * 78
                )

                print(
                    "SENTINEL PHOENIX"
                )

                print(
                    "INTEGRITY PROTECTED CORE"
                )

                print(
                    "=" * 78
                )

                print(
                    f"SOURCE : "
                    f"{source_ip}:"
                    f"{source_port}"
                )

                print(
                    f"PAYLOAD : "
                    f"{payload if payload else '<vide>'}"
                )

                print(
                    "-" * 78
                )

                print(
                    "[PAYLOAD] "
                    f"{analysis.get('severity', 'UNKNOWN')} | "
                    f"{analysis.get('score', 0)}/100"
                )

                print(
                    "[BEHAVIOR] "
                    f"{behavior.get('behavior_level', 'UNKNOWN')} | "
                    f"{behavior.get('behavior_score', 0)}/100"
                )

                print(
                    "[ANOMALY] "
                    f"{anomaly.get('anomaly_level', 'UNKNOWN')} | "
                    f"{anomaly.get('anomaly_score', 0)}/100"
                )

                print(
                    "[REPUTATION] "
                    f"{reputation.get('reputation_level', 'UNKNOWN')} | "
                    f"{reputation.get('reputation_score', 0)}/100"
                )

                print(
                    "-" * 78
                )

                print(
                    "[LEARNING] "
                    f"{learning.get('ml_level', 'UNKNOWN')} | "
                    f"{learning.get('ml_score', 0)}/100"
                )

                print(
                    "[ML CONFIDENCE] "
                    f"{learning.get('ml_confidence', 0)}%"
                )

                print(
                    "[MODEL STATUS] "
                    f"{learning.get('model_status')}"
                )

                print(
                    "[MODEL VERSION] "
                    f"{learning.get('model_version')}"
                )

                if (
                    learning_update
                    and
                    learning_update.get(
                        "retrained",
                        False
                    )
                ):

                    print(
                        "[LEARNING UPDATE] "
                        f"{learning_update}"
                    )

                print(
                    "-" * 78
                )

                print(
                    "[FUSION MODE] "
                    f"{fusion.get('fusion_mode')}"
                )

                print(
                    "[ML ACTIVE] "
                    f"{fusion.get('ml_active')}"
                )

                print(
                    "[GLOBAL RISK] "
                    f"{fusion.get('global_level')} | "
                    f"{fusion.get('global_score', 0)}/100"
                )

                print(
                    "[CONFIDENCE] "
                    f"{fusion.get('confidence', 0)}%"
                )

                print(
                    "-" * 78
                )

                print(
                    "[CONTEXT LEVEL] "
                    f"{context.get('context_level')}"
                )

                print(
                    "[CONTEXT SCORE] "
                    f"{context.get('context_score', 0)}/100"
                )

                print(
                    "[CONTEXT RECOMMENDATION] "
                    f"{context.get('recommended_action')}"
                )

                print(
                    "-" * 78
                )

                print(
                    "[POLICY ACTION] "
                    f"{response.get('action')}"
                )

                print(
                    "[MONITORING] "
                    f"{response.get('monitoring_level')}"
                )

                print(
                    "[CONTAINMENT] "
                    f"{response.get('containment_requested')}"
                )

                print(
                    "-" * 78
                )

                if deception.get(
                    "decoy_active",
                    False
                ):

                    print(
                        "[DECEPTION] ACTIVE"
                    )

                    print(
                        "[DECOY SESSION] "
                        f"{deception.get('decoy_session_id')}"
                    )

                else:

                    print(
                        "[DECEPTION] NONE"
                    )

                if sandbox.get(
                    "sandbox_active",
                    False
                ):

                    print(
                        "[SANDBOX] ACTIVE"
                    )

                    print(
                        "[SANDBOX NAME] "
                        f"{sandbox.get('sandbox_name')}"
                    )

                    print(
                        "[NETWORK] "
                        f"{sandbox.get('sandbox_network', 'NONE')}"
                    )

                    print(
                        "[READ ONLY] "
                        f"{sandbox.get('sandbox_read_only', True)}"
                    )

                    print(
                        "[PRIVILEGED] "
                        f"{sandbox.get('sandbox_privileged', False)}"
                    )

                    print(
                        "[PAYLOAD EXECUTION] False"
                    )

                else:

                    print(
                        "[SANDBOX] NONE"
                    )

                print(
                    "-" * 78
                )

                if memory:

                    print(
                        "[MEMORY EVENTS] "
                        f"{memory.get('total_events', 0)}"
                    )

                    print(
                        "[MEMORY CRITICAL] "
                        f"{memory.get('critical_events', 0)}"
                    )

                    print(
                        "[MEMORY MAX GLOBAL] "
                        f"{memory.get('max_global_score', 0)}/100"
                    )

                print(
                    "=" * 78
                )

                # =================================================
                # REMOTE RESPONSE
                # =================================================

                try:

                    if deception.get(
                        "decoy_active",
                        False
                    ):

                        fake_output = (
                            deception.get(
                                "decoy_response",
                                ""
                            )
                        )

                        client.sendall(
                            fake_output.encode(
                                "utf-8",
                                errors="replace"
                            )
                        )

                    else:

                        client.sendall(
                            b"Sentinel Phoenix Honeypot\r\n"
                        )

                except OSError:

                    pass

            except Exception as error:

                print(
                    "[ERREUR CONNEXION] "
                    f"{error}"
                )

            finally:

                if client is not None:

                    try:

                        client.close()

                    except OSError:

                        pass

    finally:

        server.close()


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=" * 78
    )

    print(
        "                      SENTINEL PHOENIX"
    )

    print(
        "                  INTEGRITY GUARD V2"
    )

    print(
        "=" * 78
    )

    # ========================================================
    # PRE-FLIGHT INTEGRITY
    # ========================================================

    integrity = (
        preflight_integrity_check()
    )

    print_integrity_report(
        integrity
    )

    if not integrity.get(
        "operational",
        False
    ):

        print("")
        print(
            "[SAFE MODE] Sentinel Phoenix "
            "n'activera aucun service opérationnel."
        )

        print(
            "[SAFE MODE] Honeypot désactivé."
        )

        print(
            "[SAFE MODE] Dashboard désactivé."
        )

        print(
            "[SAFE MODE] Sandbox désactivée."
        )

        print(
            "[SAFE MODE] Lifecycle Manager désactivé."
        )

        print("")
        print(
            "Vérifie l'intégrité avant de "
            "réautoriser le démarrage."
        )

        return 2

    # ========================================================
    # NORMAL MODE
    # ========================================================

    print(
        "[INTEGRITY] CORE VERIFIED ✓"
    )

    print(
        f"Honeypot  : "
        f"{HONEYPOT_HOST}:"
        f"{HONEYPOT_PORT}"
    )

    print(
        f"Dashboard : "
        f"http://{DASHBOARD_HOST}:"
        f"{DASHBOARD_PORT}"
    )

    print(
        "=" * 78
    )

    # ========================================================
    # MEMORY
    # ========================================================

    try:

        memory_stats = (
            get_memory_stats()
        )

        print(
            "[MEMORY] "
            f"Sources="
            f"{memory_stats.get('known_sources', 0)} | "
            f"Observations="
            f"{memory_stats.get('observations', 0)}"
        )

    except Exception as error:

        print(
            "[MEMORY ERROR] "
            f"{error}"
        )

    # ========================================================
    # LEARNING
    # ========================================================

    try:

        learning_status = (
            get_learning_status()
        )

        print(
            "[LEARNING] "
            f"Version="
            f"{learning_status.get('version')} | "
            f"Status="
            f"{learning_status.get('status')} | "
            f"Samples="
            f"{learning_status.get('total_samples', 0)}"
        )

        print(
            "[LEARNING QUALITY] "
            f"{learning_status.get('quality', {})}"
        )

    except Exception as error:

        print(
            "[LEARNING ERROR] "
            f"{error}"
        )

    # ========================================================
    # DASHBOARD
    # ========================================================

    dashboard_thread = (
        threading.Thread(
            target=run_dashboard,
            daemon=True,
            name="phoenix-dashboard"
        )
    )

    dashboard_thread.start()

    # ========================================================
    # LIFECYCLE
    # ========================================================

    start_lifecycle_manager()

    print(
        "[+] Lifecycle Manager démarré."
    )

    # ========================================================
    # HONEYPOT
    # ========================================================

    try:

        run_honeypot()

    except KeyboardInterrupt:

        print("")

        print(
            "[STOP] Sentinel Phoenix arrêté."
        )

        return 0

    except OSError as error:

        print(
            f"[ERREUR] {error}"
        )

        return 1

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )