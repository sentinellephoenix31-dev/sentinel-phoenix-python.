import os
import re
import time

import cv2

from core.face_engine import (
    CAMERA_INDEX,
    GUEST_IMAGE_DIR,
    add_to_gallery,
    create_detector,
    create_recognizer,
    detect_faces,
    ensure_storage,
    extract_embedding,
    load_registry,
    match_embedding,
    models_available,
    save_registry,
    verify_owner
)

from core.liveness import verify_liveness


# ============================================================
# SENTINEL PHOENIX
# SECURE GUEST ACCESS V2
#
# Face recognition:
#     YuNet + SFace / Face Engine V4
#
# OWNER
#   ↓
# Face Engine V4 verification
#   ↓
# Active liveness
#   ↓
# Guest enrollment using SFace embeddings
#   ↓
# GUEST limited permissions
#
# LBPH is NOT used for authentication here.
# ============================================================


GUEST_ACCESS_VERSION = "2.0"

GUEST_SAMPLES = 32
CAPTURE_DELAY_SECONDS = 0.22


# ============================================================
# SAFE GUEST NAME
# ============================================================

def safe_guest_name(name):

    value = str(name).strip()

    value = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        value
    )

    value = re.sub(
        r"_+",
        "_",
        value
    )

    value = value.strip("_")

    return value[:40]


# ============================================================
# OWNER FACE VERIFICATION
#
# Compatibility function:
# other Sentinel modules may still import verify_owner_face().
# It now uses Face Engine V4 internally.
# ============================================================

def verify_owner_face():

    result = verify_owner(
        camera_index=CAMERA_INDEX,
        show_window=True
    )

    return {
        "verified":
            bool(
                result.get("verified")
            ),

        "reason":
            result.get(
                "reason",
                "OWNER_FACE_NOT_VERIFIED_V4"
            ),

        "engine":
            "SFACE_EMBEDDING_V4",

        "owner_votes":
            result.get(
                "owner_votes",
                0
            ),

        "observations":
            result.get(
                "observations",
                0
            ),

        "similarity":
            result.get(
                "similarity",
                0.0
            )
    }


# ============================================================
# OWNER + LIVENESS AUTHORIZATION
# ============================================================

def authorize_owner_for_guest_enrollment():

    print(
        "[GUEST ACCESS V2] "
        "Verifying OWNER with Face Engine V4..."
    )

    face_result = verify_owner_face()

    if not face_result.get("verified"):

        return {
            "authorized": False,
            "reason": face_result.get(
                "reason"
            ),
            "face": face_result,
            "liveness": None
        }

    print(
        "[GUEST ACCESS V2] OWNER verified."
    )

    print(
        "[GUEST ACCESS V2] "
        "Starting active liveness verification..."
    )

    liveness = verify_liveness()

    if not liveness.get("passed"):

        return {
            "authorized": False,
            "reason": "OWNER_LIVENESS_FAILED",
            "face": face_result,
            "liveness": liveness
        }

    return {
        "authorized": True,
        "reason": "OWNER_AUTHORIZED_V4",
        "face": face_result,
        "liveness": liveness
    }


# ============================================================
# GUEST CAPTURE INSTRUCTIONS
# ============================================================

def guest_instruction(collected, total):

    ratio = collected / max(total, 1)

    if ratio < 0.30:
        return "LOOK STRAIGHT AT THE CAMERA"

    if ratio < 0.50:
        return "TURN SLIGHTLY LEFT"

    if ratio < 0.70:
        return "TURN SLIGHTLY RIGHT"

    if ratio < 0.85:
        return "MOVE SLIGHTLY CLOSER OR FARTHER"

    return "LOOK STRAIGHT AGAIN"


# ============================================================
# CAPTURE GUEST EMBEDDINGS
# ============================================================

def capture_guest_embeddings(
    guest_name,
    samples=GUEST_SAMPLES
):

    ensure_storage()

    guest_name = safe_guest_name(
        guest_name
    )

    if not guest_name:

        return {
            "status": "FAILED",
            "reason": "INVALID_GUEST_NAME"
        }

    guest_directory = os.path.join(
        GUEST_IMAGE_DIR,
        guest_name
    )

    os.makedirs(
        guest_directory,
        exist_ok=True
    )

    detector = create_detector(
        (640, 480)
    )

    recognizer = create_recognizer()

    camera = cv2.VideoCapture(
        CAMERA_INDEX
    )

    if not camera.isOpened():

        return {
            "status": "FAILED",
            "reason": "CAMERA_NOT_AVAILABLE"
        }

    embeddings = []

    collected = 0
    last_capture = 0.0

    print("")
    print(
        "[GUEST ACCESS V2] "
        f"Capturing guest: {guest_name}"
    )

    try:

        while collected < samples:

            ok, frame = camera.read()

            if not ok:
                continue

            frame = cv2.flip(
                frame,
                1
            )

            processed, faces = detect_faces(
                frame,
                detector
            )

            instruction = guest_instruction(
                collected,
                samples
            )

            status_text = "SEARCHING FOR ONE FACE"

            if len(faces) == 1:

                face = faces[0]

                embedding, quality = (
                    extract_embedding(
                        processed,
                        face,
                        recognizer
                    )
                )

                if embedding is not None:

                    current_identity = (
                        match_embedding(
                            embedding
                        )
                    )

                    # =========================================
                    # SECURITY:
                    # OWNER must move away before guest capture.
                    # =========================================

                    if (
                        current_identity.get("role")
                        ==
                        "OWNER"
                    ):

                        status_text = (
                            "OWNER STILL VISIBLE - "
                            "PLEASE MOVE AWAY"
                        )

                    else:

                        status_text = (
                            "GUEST FACE DETECTED"
                        )

                        if (
                            time.monotonic()
                            -
                            last_capture
                            >=
                            CAPTURE_DELAY_SECONDS
                        ):

                            embeddings.append(
                                embedding
                            )

                            collected += 1

                            last_capture = (
                                time.monotonic()
                            )

                            x = max(
                                0,
                                int(face[0])
                            )

                            y = max(
                                0,
                                int(face[1])
                            )

                            w = int(
                                face[2]
                            )

                            h = int(
                                face[3]
                            )

                            x2 = min(
                                frame.shape[1],
                                x + w
                            )

                            y2 = min(
                                frame.shape[0],
                                y + h
                            )

                            crop = frame[
                                y:y2,
                                x:x2
                            ]

                            if crop.size:

                                filename = os.path.join(
                                    guest_directory,
                                    (
                                        f"guest_v4_"
                                        f"{int(time.time() * 1000)}_"
                                        f"{collected:03d}.jpg"
                                    )
                                )

                                cv2.imwrite(
                                    filename,
                                    crop
                                )

                            print(
                                "[GUEST ACCESS V2] "
                                f"Sample {collected}/{samples}"
                            )

            elif len(faces) > 1:

                status_text = (
                    "MULTIPLE FACES - "
                    "ONLY THE GUEST SHOULD REMAIN"
                )

            display = frame.copy()

            cv2.putText(
                display,
                "SENTINEL PHOENIX - GUEST ENROLLMENT V4",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )

            cv2.putText(
                display,
                f"GUEST: {guest_name}",
                (20, 68),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.56,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )

            cv2.putText(
                display,
                instruction,
                (20, 101),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )

            cv2.putText(
                display,
                status_text,
                (20, 134),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )

            cv2.putText(
                display,
                f"{collected}/{samples}",
                (20, 167),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )

            cv2.imshow(
                "Sentinel Phoenix - Guest Enrollment V4",
                display
            )

            key = cv2.waitKey(1) & 0xFF

            if key in (
                ord("q"),
                27
            ):
                break

    finally:

        camera.release()
        cv2.destroyAllWindows()

    if len(embeddings) < samples:

        return {
            "status": "FAILED",
            "reason": "INSUFFICIENT_GUEST_SAMPLES",
            "samples": len(
                embeddings
            )
        }

    # ========================================================
    # Add SFace embeddings directly to V4 gallery.
    # No LBPH retraining required.
    # ========================================================

    add_to_gallery(
        embeddings,
        name=guest_name,
        role="GUEST",
        replace_identity=True
    )

    registry = load_registry()

    registry.setdefault(
        "identities",
        {}
    )

    registry[
        "identities"
    ][
        f"GUEST:{guest_name}"
    ] = {
        "name": guest_name,
        "role": "GUEST",
        "samples": len(
            embeddings
        )
    }

    save_registry(
        registry
    )

    return {
        "status": "GUEST_ENROLLED_V4",
        "guest": guest_name,
        "samples": len(
            embeddings
        ),
        "engine": "SFACE_EMBEDDING_V4",
        "permissions": "LIMITED_GUEST_ACCESS"
    }


# ============================================================
# COMPLETE SECURE GUEST ENROLLMENT
# ============================================================

def secure_enroll_guest(
    guest_name,
    samples=GUEST_SAMPLES
):

    guest_name = safe_guest_name(
        guest_name
    )

    if not guest_name:

        return {
            "status": "DENIED",
            "reason": "GUEST_NAME_REQUIRED"
        }

    # ========================================================
    # STEP 1 — OWNER AUTHORIZATION
    # ========================================================

    authorization = (
        authorize_owner_for_guest_enrollment()
    )

    if not authorization.get(
        "authorized"
    ):

        return {
            "status": "DENIED",
            "reason": authorization.get(
                "reason"
            ),
            "authorization": authorization
        }

    # ========================================================
    # STEP 2 — OWNER LEAVES CAMERA
    # ========================================================

    print("")
    print(
        "[GUEST ACCESS V2] "
        "OWNER authorization complete."
    )

    print(
        "[GUEST ACCESS V2] "
        "OWNER: please move away from the camera."
    )

    print(
        "[GUEST ACCESS V2] "
        f"Guest {guest_name}: prepare to face the camera."
    )

    time.sleep(
        3.0
    )

    # ========================================================
    # STEP 3 — SFace enrollment
    # ========================================================

    enrollment = capture_guest_embeddings(
        guest_name,
        samples=samples
    )

    if (
        enrollment.get("status")
        !=
        "GUEST_ENROLLED_V4"
    ):

        return {
            "status": "FAILED",
            "reason": enrollment.get(
                "reason"
            ),
            "authorization": authorization,
            "enrollment": enrollment
        }

    return {
        "status": "GUEST_ENROLLED",
        "guest": guest_name,

        "authorization": {
            "owner_face": True,
            "owner_liveness": True,
            "face_engine":
                "SFACE_EMBEDDING_V4"
        },

        "enrollment": enrollment,

        "permissions":
            "LIMITED_GUEST_ACCESS"
    }


# ============================================================
# SELF TEST
#
# No camera enrollment is started.
# ============================================================

def self_test():

    models = models_available()

    functions_ok = all(
        [
            callable(
                verify_owner_face
            ),
            callable(
                secure_enroll_guest
            ),
            callable(
                capture_guest_embeddings
            )
        ]
    )

    passed = (
        models.get("yunet")
        and
        models.get("sface")
        and
        functions_ok
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
            GUEST_ACCESS_VERSION,

        "face_engine":
            "SFACE_EMBEDDING_V4",

        "models":
            models,

        "flow": [
            "OWNER_SFACE_VERIFY",
            "OWNER_LIVENESS",
            "OWNER_MOVES_AWAY",
            "GUEST_SFACE_CAPTURE",
            "GUEST_GALLERY_REGISTER",
            "LIMITED_GUEST_ACCESS"
        ],

        "security": {
            "lbph_authentication":
                False,

            "owner_required":
                True,

            "owner_liveness_required":
                True,

            "owner_cannot_be_captured_as_guest":
                True,

            "multiple_faces_during_enrollment":
                False,

            "guest_admin_permissions":
                False,

            "biometric_processing_local":
                True,

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