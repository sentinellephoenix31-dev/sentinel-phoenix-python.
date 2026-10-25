from core.evidence_lifecycle import (
    list_evidence,
    get_evidence,
    mark_presented,
    keep_evidence,
    delete_evidence,
    acknowledge_evidence
)

from core.guest_access import (
    verify_owner_face
)

from core.liveness import (
    verify_liveness
)


# ============================================================
# SENTINEL PHOENIX
# OWNER EVIDENCE CONTROL V1
#
# Sensitive evidence operations require:
#
# OWNER FACE
#      +
# ACTIVE LIVENESS
#
# Supported:
# - latest evidence
# - present
# - KEEP
# - DELETE
# - ACKNOWLEDGE
# ============================================================


OWNER_EVIDENCE_VERSION = "1.0"


# ============================================================
# OWNER AUTHORIZATION
# ============================================================

def authorize_owner():

    # ========================================================
    # STEP 1 — OWNER FACE
    # ========================================================

    face = verify_owner_face()

    if not face.get(
        "verified"
    ):

        return {
            "authorized":
                False,

            "reason":
                face.get(
                    "reason",
                    "OWNER_FACE_FAILED"
                ),

            "face":
                face,

            "liveness":
                None
        }


    print(
        "[EVIDENCE OWNER] "
        "OWNER face verified."
    )


    # ========================================================
    # STEP 2 — ACTIVE LIVENESS
    # ========================================================

    print(
        "[EVIDENCE OWNER] "
        "Starting liveness verification..."
    )


    liveness = verify_liveness()


    if not liveness.get(
        "passed"
    ):

        return {
            "authorized":
                False,

            "reason":
                "OWNER_LIVENESS_FAILED",

            "face":
                face,

            "liveness":
                liveness
        }


    return {
        "authorized":
            True,

        "reason":
            "OWNER_AUTHORIZED",

        "face":
            face,

        "liveness":
            liveness
    }


# ============================================================
# GET LATEST EVIDENCE
# ============================================================

def latest_evidence():

    records = list_evidence()


    if not records:

        return {
            "status":
                "EMPTY",

            "reason":
                "NO_EVIDENCE_AVAILABLE"
        }


    record = records[
        0
    ]


    return {
        "status":
            "FOUND",

        "evidence_id":
            record.get(
                "id"
            ),

        "record":
            record
    }


# ============================================================
# RESOLVE TARGET
#
# If no ID is given:
# use latest evidence.
# ============================================================

def resolve_evidence(
    evidence_id=None
):

    if evidence_id:

        result = get_evidence(
            evidence_id
        )

        if (
            result.get(
                "status"
            )
            !=
            "FOUND"
        ):

            return {
                "status":
                    "NOT_FOUND"
            }

        return {
            "status":
                "FOUND",

            "evidence_id":
                evidence_id,

            "record":
                result.get(
                    "record"
                )
        }


    return latest_evidence()


# ============================================================
# PRESENT EVIDENCE
# ============================================================

def present_evidence(
    evidence_id=None
):

    target = resolve_evidence(
        evidence_id
    )


    if (
        target.get(
            "status"
        )
        !=
        "FOUND"
    ):

        return {
            "status":
                "NOT_FOUND",

            "reason":
                "NO_EVIDENCE_AVAILABLE"
        }


    evidence_id = target[
        "evidence_id"
    ]


    result = mark_presented(
        evidence_id
    )


    return {
        "status":
            result.get(
                "status"
            ),

        "evidence_id":
            evidence_id,

        "record":
            target.get(
                "record"
            )
    }


# ============================================================
# KEEP
# ============================================================

def owner_keep_evidence(
    evidence_id=None
):

    target = resolve_evidence(
        evidence_id
    )


    if (
        target.get(
            "status"
        )
        !=
        "FOUND"
    ):

        return {
            "status":
                "NOT_FOUND",

            "reason":
                "NO_EVIDENCE_AVAILABLE"
        }


    # ========================================================
    # OWNER AUTHORIZATION
    # ========================================================

    authorization = authorize_owner()


    if not authorization.get(
        "authorized"
    ):

        return {
            "status":
                "DENIED",

            "reason":
                authorization.get(
                    "reason"
                ),

            "authorization":
                authorization
        }


    evidence_id = target[
        "evidence_id"
    ]


    result = keep_evidence(
        evidence_id
    )


    return {
        "status":
            result.get(
                "status"
            ),

        "action":
            "KEEP",

        "evidence_id":
            evidence_id,

        "owner_verified":
            True,

        "liveness_verified":
            True
    }


# ============================================================
# DELETE
# ============================================================

def owner_delete_evidence(
    evidence_id=None
):

    target = resolve_evidence(
        evidence_id
    )


    if (
        target.get(
            "status"
        )
        !=
        "FOUND"
    ):

        return {
            "status":
                "NOT_FOUND",

            "reason":
                "NO_EVIDENCE_AVAILABLE"
        }


    # ========================================================
    # OWNER AUTHORIZATION
    # ========================================================

    authorization = authorize_owner()


    if not authorization.get(
        "authorized"
    ):

        return {
            "status":
                "DENIED",

            "reason":
                authorization.get(
                    "reason"
                ),

            "authorization":
                authorization
        }


    evidence_id = target[
        "evidence_id"
    ]


    result = delete_evidence(
        evidence_id,
        reason="OWNER_VERIFIED_DELETE"
    )


    return {
        "status":
            result.get(
                "status"
            ),

        "action":
            "DELETE",

        "evidence_id":
            evidence_id,

        "owner_verified":
            True,

        "liveness_verified":
            True
    }


# ============================================================
# ACKNOWLEDGE
#
# If evidence is NOT kept:
# evidence_lifecycle.py deletes it.
#
# If evidence IS kept:
# it remains preserved.
# ============================================================

def owner_acknowledge_evidence(
    evidence_id=None
):

    target = resolve_evidence(
        evidence_id
    )


    if (
        target.get(
            "status"
        )
        !=
        "FOUND"
    ):

        return {
            "status":
                "NOT_FOUND",

            "reason":
                "NO_EVIDENCE_AVAILABLE"
        }


    # ========================================================
    # OWNER AUTHORIZATION
    # ========================================================

    authorization = authorize_owner()


    if not authorization.get(
        "authorized"
    ):

        return {
            "status":
                "DENIED",

            "reason":
                authorization.get(
                    "reason"
                ),

            "authorization":
                authorization
        }


    evidence_id = target[
        "evidence_id"
    ]


    result = acknowledge_evidence(
        evidence_id
    )


    return {
        "status":
            result.get(
                "status"
            ),

        "action":
            "ACKNOWLEDGE",

        "evidence_id":
            evidence_id,

        "owner_verified":
            True,

        "liveness_verified":
            True
    }


# ============================================================
# SAFE STATUS
#
# Does NOT expose/delete/change evidence.
# No liveness required for this local status call.
# ============================================================

def evidence_summary():

    records = list_evidence()


    kept = sum(
        1
        for record in records
        if record.get(
            "kept"
        )
    )


    temporary = (
        len(
            records
        )
        -
        kept
    )


    latest = (
        records[
            0
        ]
        if records
        else None
    )


    return {
        "status":
            "ONLINE",

        "total":
            len(
                records
            ),

        "temporary":
            temporary,

        "kept":
            kept,

        "latest":
            (
                {
                    "id":
                        latest.get(
                            "id"
                        ),

                    "state":
                        latest.get(
                            "state"
                        ),

                    "created_at_iso":
                        latest.get(
                            "created_at_iso"
                        ),

                    "source":
                        latest.get(
                            "source"
                        )
                }

                if latest
                else None
            )
    }


# ============================================================
# SELF TEST
#
# IMPORTANT:
# This does NOT launch webcam/liveness.
# It only validates routing and configuration.
# ============================================================

def self_test():

    summary = evidence_summary()


    functions_available = all(
        [
            callable(
                owner_keep_evidence
            ),

            callable(
                owner_delete_evidence
            ),

            callable(
                owner_acknowledge_evidence
            ),

            callable(
                authorize_owner
            )
        ]
    )


    passed = (
        functions_available
        and
        summary.get(
            "status"
        )
        ==
        "ONLINE"
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
            OWNER_EVIDENCE_VERSION,

        "evidence_engine":
            summary.get(
                "status"
            ),

        "commands":
            [
                "KEEP",
                "DELETE",
                "ACKNOWLEDGE"
            ],

        "authorization":
            [
                "OWNER_FACE",
                "ACTIVE_LIVENESS"
            ],

        "safety":
            {
                "unknown_can_manage_evidence":
                    False,

                "guest_can_manage_evidence":
                    False,

                "owner_face_required":
                    True,

                "owner_liveness_required":
                    True,

                "arbitrary_path_delete":
                    False,

                "internet_upload":
                    False,

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