# ============================================================
# SENTINEL PHOENIX
# INTEGRITY GUARD V2
# ============================================================

from core.integrity import (
    load_baseline,
    verify_integrity,
    log_event
)


def preflight_integrity_check():
    """
    Vérification effectuée avant le démarrage
    des composants opérationnels de Sentinel.

    Ce module :
    - ne restaure rien automatiquement
    - ne modifie pas la baseline
    - ne lance aucune commande système
    """

    baseline = load_baseline()

    # ========================================================
    # AUCUNE BASELINE
    # ========================================================

    if baseline is None:

        result = {
            "operational": False,
            "mode": "SAFE_MODE",
            "status": "NO_BASELINE",
            "reason": "TRUST_BASELINE_REQUIRED",
            "modified": [],
            "missing": [],
            "unexpected": []
        }

        log_event(
            "INTEGRITY_GUARD_BLOCK",
            {
                "reason":
                    "NO_BASELINE"
            }
        )

        return result

    # ========================================================
    # VERIFICATION
    # ========================================================

    verification = verify_integrity(
        log_result=True
    )

    if verification.get(
        "clean",
        False
    ):

        result = {
            "operational": True,
            "mode": "NORMAL",
            "status": "CLEAN",
            "reason": "INTEGRITY_VERIFIED",
            "modified": [],
            "missing": [],
            "unexpected": []
        }

        log_event(
            "INTEGRITY_GUARD_PASS",
            {
                "status":
                    "CLEAN"
            }
        )

        return result

    # ========================================================
    # MODIFICATION DETECTEE
    # ========================================================

    modified = verification.get(
        "modified",
        []
    )

    missing = verification.get(
        "missing",
        []
    )

    unexpected = verification.get(
        "unexpected",
        []
    )

    result = {
        "operational": False,
        "mode": "SAFE_MODE",
        "status": "CHANGED",
        "reason": "CORE_INTEGRITY_FAILURE",
        "modified": modified,
        "missing": missing,
        "unexpected": unexpected
    }

    log_event(
        "INTEGRITY_GUARD_BLOCK",
        {
            "reason":
                "CORE_INTEGRITY_FAILURE",

            "modified":
                [
                    item.get(
                        "file"
                    )
                    for item
                    in modified
                ],

            "missing":
                missing,

            "unexpected":
                unexpected
        }
    )

    return result


def print_integrity_report(
    result
):

    print(
        "=" * 78
    )

    print(
        "PHOENIX INTEGRITY GUARD"
    )

    print(
        "=" * 78
    )

    print(
        "[MODE] "
        f"{result.get('mode')}"
    )

    print(
        "[STATUS] "
        f"{result.get('status')}"
    )

    print(
        "[REASON] "
        f"{result.get('reason')}"
    )

    modified = result.get(
        "modified",
        []
    )

    missing = result.get(
        "missing",
        []
    )

    unexpected = result.get(
        "unexpected",
        []
    )

    if modified:

        print(
            "[MODIFIED FILES]"
        )

        for item in modified:

            print(
                "  - "
                f"{item.get('file')}"
            )

    if missing:

        print(
            "[MISSING FILES]"
        )

        for filename in missing:

            print(
                "  - "
                f"{filename}"
            )

    if unexpected:

        print(
            "[UNEXPECTED FILES]"
        )

        for filename in unexpected:

            print(
                "  - "
                f"{filename}"
            )

    print(
        "=" * 78
    )