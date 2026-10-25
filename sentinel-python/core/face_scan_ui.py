import time
from collections import Counter, deque

import cv2

from core.face_engine import (
    CAMERA_INDEX,
    create_detector,
    create_recognizer,
    load_gallery,
    recognize_frame
)

# PresenceTracker reste utilisé uniquement pour :
# - OWNER_PRESENT / OWNER_LEFT
# - GUEST_PRESENT / GUEST_LEFT
# - UNKNOWN evidence
#
# Il ne décide PLUS de l'identité.
from core.face_identity import PresenceTracker


# ============================================================
# SENTINEL PHOENIX
# FACE SCAN UI V4
#
# IDENTITY ENGINE:
# YuNet + SFace embeddings
#
# Face Identity:
#   Face Engine V4 ONLY
#
# Presence logging:
#   PresenceTracker
# ============================================================


FACE_SCAN_VERSION = "4.0"

WINDOW_NAME = "Sentinel Phoenix - Identity Scan V4"

STABLE_WINDOW = 10
STABLE_REQUIRED = 6

SCAN_SPEED = 7


# ============================================================
# STABILIZER
# ============================================================

class IdentityStabilizer:

    def __init__(
        self,
        window=STABLE_WINDOW,
        required=STABLE_REQUIRED
    ):

        self.history = deque(
            maxlen=window
        )

        self.required = required


    def update(
        self,
        identity
    ):

        if identity is None:

            self.history.append(
                (
                    "NONE",
                    "NONE"
                )
            )

            return None


        role = str(
            identity.get(
                "role",
                "UNKNOWN"
            )
        ).upper()


        name = str(
            identity.get(
                "name",
                role
            )
        )


        self.history.append(
            (
                role,
                name
            )
        )


        counts = Counter(
            self.history
        )


        if not counts:

            return None


        winner, votes = counts.most_common(
            1
        )[0]


        if votes < self.required:

            return None


        role, name = winner


        if role == "NONE":

            return None


        return {
            "role":
                role,

            "name":
                name,

            "votes":
                votes
        }


# ============================================================
# COLORS
# ============================================================

def role_color(
    role
):

    role = str(
        role
    ).upper()


    if role == "OWNER":

        return (
            80,
            255,
            100
        )


    if role == "GUEST":

        return (
            255,
            220,
            70
        )


    return (
        60,
        70,
        255
    )


# ============================================================
# DRAW CORNERS
# ============================================================

def draw_hud_corners(
    frame,
    box,
    color
):

    x = box[
        "x"
    ]

    y = box[
        "y"
    ]

    w = box[
        "w"
    ]

    h = box[
        "h"
    ]


    length = max(
        20,
        int(
            min(
                w,
                h
            )
            *
            0.18
        )
    )


    thickness = 2


    # Top left

    cv2.line(
        frame,
        (x, y),
        (x + length, y),
        color,
        thickness
    )

    cv2.line(
        frame,
        (x, y),
        (x, y + length),
        color,
        thickness
    )


    # Top right

    cv2.line(
        frame,
        (x + w, y),
        (x + w - length, y),
        color,
        thickness
    )

    cv2.line(
        frame,
        (x + w, y),
        (x + w, y + length),
        color,
        thickness
    )


    # Bottom left

    cv2.line(
        frame,
        (x, y + h),
        (x + length, y + h),
        color,
        thickness
    )

    cv2.line(
        frame,
        (x, y + h),
        (x, y + h - length),
        color,
        thickness
    )


    # Bottom right

    cv2.line(
        frame,
        (x + w, y + h),
        (x + w - length, y + h),
        color,
        thickness
    )

    cv2.line(
        frame,
        (x + w, y + h),
        (x + w, y + h - length),
        color,
        thickness
    )


# ============================================================
# LANDMARKS
# ============================================================

def draw_landmarks(
    frame,
    identity,
    color
):

    landmarks = identity.get(
        "landmarks",
        []
    )


    for landmark in landmarks:

        x = int(
            landmark.get(
                "x",
                0
            )
        )

        y = int(
            landmark.get(
                "y",
                0
            )
        )


        cv2.circle(
            frame,
            (
                x,
                y
            ),
            3,
            color,
            -1
        )


# ============================================================
# TEXT
# ============================================================

def draw_text(
    frame,
    text,
    position,
    scale=0.55,
    color=(255, 255, 255),
    thickness=1
):

    cv2.putText(
        frame,
        str(
            text
        ),
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA
    )


# ============================================================
# MAIN FACE SCAN
# ============================================================

def run_face_scan():

    detector = create_detector(
        (
            640,
            480
        )
    )

    recognizer = create_recognizer()

    gallery = load_gallery()


    if (
        gallery[
            "embeddings"
        ].shape[
            0
        ]
        ==
        0
    ):

        raise RuntimeError(
            "FACE_V4_GALLERY_EMPTY"
        )


    camera = cv2.VideoCapture(
        CAMERA_INDEX
    )


    if not camera.isOpened():

        raise RuntimeError(
            "CAMERA_NOT_AVAILABLE"
        )


    camera.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        1280
    )

    camera.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        720
    )


    stabilizer = IdentityStabilizer()

    tracker = PresenceTracker()


    scan_position = 0

    scan_direction = 1


    cv2.namedWindow(
        WINDOW_NAME,
        cv2.WINDOW_NORMAL
    )


    print(
        "[FACE SCAN V4] "
        "YuNet + SFace online."
    )


    try:

        while True:

            ok, frame = camera.read()


            if not ok:

                continue


            frame = cv2.flip(
                frame,
                1
            )


            results = recognize_frame(
                frame,
                detector=detector,
                recognizer=recognizer
            )


            # =================================================
            # Select largest detected face
            # =================================================

            primary = None


            if results:

                primary = max(
                    results,
                    key=lambda item:
                        item[
                            "box"
                        ][
                            "w"
                        ]
                        *
                        item[
                            "box"
                        ][
                            "h"
                        ]
                )


            stable = stabilizer.update(
                primary
            )


            # =================================================
            # TOP HUD
            # =================================================

            draw_text(
                frame,
                "SENTINEL PHOENIX",
                (
                    25,
                    35
                ),
                0.78,
                (
                    255,
                    255,
                    255
                ),
                2
            )


            draw_text(
                frame,
                "IDENTITY SCAN V4 | YUNET + SFACE",
                (
                    25,
                    65
                ),
                0.48,
                (
                    180,
                    205,
                    225
                ),
                1
            )


            # =================================================
            # FACE
            # =================================================

            if primary is not None:

                role = primary.get(
                    "role",
                    "UNKNOWN"
                )


                color = role_color(
                    role
                )


                box = primary[
                    "box"
                ]


                draw_hud_corners(
                    frame,
                    box,
                    color
                )


                draw_landmarks(
                    frame,
                    primary,
                    color
                )


                # =============================================
                # Animated scanning line inside FACE only
                # =============================================

                scan_position += (
                    SCAN_SPEED
                    *
                    scan_direction
                )


                if scan_position >= box[
                    "h"
                ]:

                    scan_position = box[
                        "h"
                    ]

                    scan_direction = -1


                elif scan_position <= 0:

                    scan_position = 0

                    scan_direction = 1


                scan_y = (
                    box[
                        "y"
                    ]
                    +
                    scan_position
                )


                cv2.line(
                    frame,
                    (
                        box[
                            "x"
                        ],
                        scan_y
                    ),
                    (
                        box[
                            "x"
                        ]
                        +
                        box[
                            "w"
                        ],
                        scan_y
                    ),
                    color,
                    1
                )


                similarity = float(
                    primary.get(
                        "similarity",
                        0.0
                    )
                )


                quality = primary.get(
                    "quality",
                    {}
                )


                quality_reason = quality.get(
                    "reason",
                    "UNKNOWN"
                )


                draw_text(
                    frame,
                    (
                        f"RAW: {role}  "
                        f"SIM: {similarity:.3f}"
                    ),
                    (
                        box[
                            "x"
                        ],
                        max(
                            95,
                            box[
                                "y"
                            ]
                            -
                            18
                        )
                    ),
                    0.51,
                    color,
                    2
                )


                draw_text(
                    frame,
                    (
                        f"VISUAL QUALITY: "
                        f"{quality_reason}"
                    ),
                    (
                        25,
                        100
                    ),
                    0.46,
                    (
                        180,
                        205,
                        225
                    ),
                    1
                )


            else:

                scan_position = 0


                draw_text(
                    frame,
                    "SEARCHING FOR FACE...",
                    (
                        25,
                        105
                    ),
                    0.60,
                    (
                        180,
                        205,
                        225
                    ),
                    2
                )


            # =================================================
            # STABLE DECISION
            # =================================================

            if stable is None:

                draw_text(
                    frame,
                    "ANALYZING IDENTITY...",
                    (
                        25,
                        145
                    ),
                    0.66,
                    (
                        255,
                        255,
                        255
                    ),
                    2
                )


            else:

                stable_role = stable[
                    "role"
                ]

                stable_name = stable[
                    "name"
                ]

                stable_color = role_color(
                    stable_role
                )


                if stable_role == "OWNER":

                    status_text = (
                        "OWNER RECOGNIZED"
                    )


                elif stable_role == "GUEST":

                    status_text = (
                        f"GUEST: {stable_name} "
                        "- LIMITED ACCESS"
                    )


                else:

                    status_text = (
                        "UNKNOWN - ACCESS RESTRICTED"
                    )


                draw_text(
                    frame,
                    status_text,
                    (
                        25,
                        145
                    ),
                    0.72,
                    stable_color,
                    2
                )


                draw_text(
                    frame,
                    (
                        f"STABILITY: "
                        f"{stable['votes']}/"
                        f"{STABLE_WINDOW}"
                    ),
                    (
                        25,
                        175
                    ),
                    0.48,
                    stable_color,
                    1
                )


                # =============================================
                # Presence tracking only after stable decision
                # =============================================

                confidence = 0.0


                if primary is not None:

                    confidence = float(
                        primary.get(
                            "confidence",
                            primary.get(
                                "similarity",
                                0.0
                            )
                        )
                    )


                tracker.observe(
                    stable_role,
                    stable_name,
                    confidence,
                    frame=frame
                )


            tracker.update_departures()


            # =================================================
            # FOOTER
            # =================================================

            draw_text(
                frame,
                (
                    "IDENTITY ENGINE: SFACE V4  |  "
                    "FACIAL LANDMARK ALIGNMENT: ON  |  "
                    "BIOMETRIC UPLOAD: OFF"
                ),
                (
                    20,
                    frame.shape[
                        0
                    ]
                    -
                    20
                ),
                0.40,
                (
                    145,
                    170,
                    190
                ),
                1
            )


            cv2.imshow(
                WINDOW_NAME,
                frame
            )


            key = cv2.waitKey(
                1
            ) & 0xFF


            if key in (
                ord(
                    "q"
                ),
                27
            ):

                break


    finally:

        camera.release()

        cv2.destroyAllWindows()


    return 0


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    detector_ok = False
    recognizer_ok = False


    try:

        create_detector()

        detector_ok = True

    except Exception:

        detector_ok = False


    try:

        create_recognizer()

        recognizer_ok = True

    except Exception:

        recognizer_ok = False


    gallery = load_gallery()


    gallery_samples = int(
        gallery[
            "embeddings"
        ].shape[
            0
        ]
    )


    passed = (
        detector_ok
        and
        recognizer_ok
        and
        gallery_samples > 0
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
            FACE_SCAN_VERSION,

        "identity_engine":
            "SFACE_EMBEDDING_V4",

        "detector":
            "YUNET",

        "detector_ok":
            detector_ok,

        "recognizer_ok":
            recognizer_ok,

        "gallery_samples":
            gallery_samples,

        "stable_window":
            STABLE_WINDOW,

        "stable_required":
            STABLE_REQUIRED,

        "security": {
            "lbph_identity_decision":
                False,

            "shoulders_used_for_identity":
                False,

            "clothes_used_for_identity":
                False,

            "facial_landmark_alignment":
                True,

            "multi_frame_decision":
                True,

            "unknown_evidence":
                True,

            "biometric_upload":
                False
        }
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        run_face_scan()
    )