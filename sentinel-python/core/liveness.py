import os
import random
import time

import cv2


# ============================================================
# SENTINEL PHOENIX
# ACTIVE LIVENESS CORE V1.1
#
# LOCAL CAMERA ONLY
#
# CHALLENGES:
# - BLINK
# - MOVE LEFT
# - MOVE RIGHT
#
# V1.1:
# - More sensitive movement detection
# - Longer challenge timeout
# - Multi-frame confirmation
# - Better HUD feedback
# ============================================================


LIVENESS_VERSION = "1.1"


# ============================================================
# CONFIGURATION
# ============================================================

CAMERA_INDEX = 0

WINDOW_NAME = (
    "Sentinel Phoenix - Liveness Verification"
)

TOTAL_TIMEOUT = 45.0

CHALLENGE_TIMEOUT = 12.0

BASELINE_SECONDS = 1.8


# Movement required:
# 0.04 = 4% of camera frame width
#
# Previous version used 10%, which was
# too demanding in VirtualBox.

MOVEMENT_THRESHOLD = 0.04


# Require movement to remain valid
# for several consecutive frames.

MOVEMENT_CONFIRM_FRAMES = 3


# Blink detection

BLINK_MISSING_FRAMES = 2

BLINK_RETURN_FRAMES = 2


# ============================================================
# CASCADE FINDER
# ============================================================

def find_cascade(
    filename
):

    possible_paths = []


    # ========================================================
    # OpenCV Python location
    # ========================================================

    try:

        possible_paths.append(
            os.path.join(
                cv2.data.haarcascades,
                filename
            )
        )

    except Exception:

        pass


    # ========================================================
    # Common Ubuntu locations
    # ========================================================

    possible_paths.extend(
        [

            os.path.join(
                "/usr/share/opencv4/haarcascades",
                filename
            ),

            os.path.join(
                "/usr/share/opencv/haarcascades",
                filename
            ),

            os.path.join(
                "/usr/local/share/opencv4/haarcascades",
                filename
            ),

            os.path.join(
                "/usr/local/share/opencv/haarcascades",
                filename
            )
        ]
    )


    for path in possible_paths:

        if not os.path.isfile(
            path
        ):

            continue


        cascade = cv2.CascadeClassifier(
            path
        )


        if not cascade.empty():

            return cascade


    return None


# ============================================================
# DETECTORS
# ============================================================

def create_detectors():

    face = find_cascade(
        "haarcascade_frontalface_default.xml"
    )


    eye = find_cascade(
        "haarcascade_eye_tree_eyeglasses.xml"
    )


    if eye is None:

        eye = find_cascade(
            "haarcascade_eye.xml"
        )


    if face is None:

        raise RuntimeError(
            "FACE_CASCADE_UNAVAILABLE"
        )


    if eye is None:

        raise RuntimeError(
            "EYE_CASCADE_UNAVAILABLE"
        )


    return (
        face,
        eye
    )


# ============================================================
# FACE DETECTION
# ============================================================

def detect_primary_face(
    frame,
    face_detector
):

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )


    gray = cv2.equalizeHist(
        gray
    )


    faces = face_detector.detectMultiScale(

        gray,

        scaleFactor=1.15,

        minNeighbors=6,

        minSize=(
            100,
            100
        )
    )


    if len(
        faces
    ) == 0:

        return (
            gray,
            None
        )


    # Use the largest face.

    face = max(

        faces,

        key=lambda box:
            box[2]
            *
            box[3]
    )


    return (
        gray,
        face
    )


# ============================================================
# EYE DETECTION
# ============================================================

def eyes_visible(
    gray,
    face_box,
    eye_detector
):

    if face_box is None:

        return False


    x, y, w, h = face_box


    # Eyes should normally be in the
    # upper ~60% of the face.

    roi = gray[
        y:
        y + int(
            h * 0.60
        ),

        x:
        x + w
    ]


    if roi.size == 0:

        return False


    eyes = eye_detector.detectMultiScale(

        roi,

        scaleFactor=1.10,

        minNeighbors=5,

        minSize=(
            18,
            18
        )
    )


    return len(
        eyes
    ) >= 1


# ============================================================
# DRAW HELPERS
# ============================================================

def draw_text(
    frame,
    text,
    y,
    scale=0.65,
    thickness=2,
    color=(255, 255, 255)
):

    cv2.putText(

        frame,

        str(
            text
        ),

        (
            25,
            y
        ),

        cv2.FONT_HERSHEY_SIMPLEX,

        scale,

        color,

        thickness,

        cv2.LINE_AA
    )


def draw_face_box(
    frame,
    box,
    color=(255, 220, 80)
):

    if box is None:

        return


    x, y, w, h = box


    cv2.rectangle(

        frame,

        (
            x,
            y
        ),

        (
            x + w,
            y + h
        ),

        color,

        2
    )


def draw_progress_bar(
    frame,
    value,
    y
):

    value = max(
        0.0,
        min(
            1.0,
            float(
                value
            )
        )
    )


    width = frame.shape[
        1
    ]


    start_x = 25

    end_x = width - 25

    total_width = (
        end_x
        -
        start_x
    )


    cv2.rectangle(

        frame,

        (
            start_x,
            y
        ),

        (
            end_x,
            y + 10
        ),

        (
            80,
            80,
            80
        ),

        1
    )


    filled = int(
        total_width
        *
        value
    )


    cv2.rectangle(

        frame,

        (
            start_x,
            y
        ),

        (
            start_x + filled,
            y + 10
        ),

        (
            255,
            220,
            80
        ),

        -1
    )


def challenge_instruction(
    challenge
):

    if challenge == "BLINK":

        return (
            "BLINK NATURALLY"
        )


    if challenge == "MOVE_LEFT":

        return (
            "MOVE YOUR HEAD LEFT"
        )


    if challenge == "MOVE_RIGHT":

        return (
            "MOVE YOUR HEAD RIGHT"
        )


    return challenge


# ============================================================
# BASELINE
# ============================================================

def acquire_baseline(
    camera,
    face_detector
):

    started = time.monotonic()

    centers = []


    while (
        time.monotonic()
        -
        started
        <
        BASELINE_SECONDS
    ):

        ok, frame = camera.read()


        if not ok:

            continue


        # Mirror view so movement feels natural.

        frame = cv2.flip(
            frame,
            1
        )


        gray, face = detect_primary_face(
            frame,
            face_detector
        )


        if face is None:

            continue


        x, y, w, h = face


        centers.append(
            (
                x + w / 2,
                y + h / 2
            )
        )


        draw_face_box(
            frame,
            face
        )


        draw_text(
            frame,
            "SENTINEL LIVENESS CHECK",
            35
        )


        draw_text(
            frame,
            "LOOK STRAIGHT AT THE CAMERA",
            70,
            0.58
        )


        draw_text(
            frame,
            "Calibrating neutral position...",
            100,
            0.48,
            1
        )


        elapsed = (
            time.monotonic()
            -
            started
        )


        progress = (
            elapsed
            /
            BASELINE_SECONDS
        )


        draw_progress_bar(
            frame,
            progress,
            frame.shape[0] - 45
        )


        cv2.imshow(
            WINDOW_NAME,
            frame
        )


        key = (
            cv2.waitKey(
                1
            )
            &
            0xFF
        )


        if key in (
            ord(
                "q"
            ),
            27
        ):

            return None


    if not centers:

        return None


    center_x = sum(
        item[0]
        for item in centers
    ) / len(
        centers
    )


    center_y = sum(
        item[1]
        for item in centers
    ) / len(
        centers
    )


    return {

        "x":
            center_x,

        "y":
            center_y
    }


# ============================================================
# BLINK CHALLENGE
# ============================================================

def run_blink_challenge(
    camera,
    face_detector,
    eye_detector,
    deadline
):

    saw_open = False

    missing_frames = 0

    return_frames = 0

    blink_started = False


    while (
        time.monotonic()
        <
        deadline
    ):

        ok, frame = camera.read()


        if not ok:

            continue


        frame = cv2.flip(
            frame,
            1
        )


        gray, face = detect_primary_face(
            frame,
            face_detector
        )


        visible = eyes_visible(
            gray,
            face,
            eye_detector
        )


        # ====================================================
        # Eyes visible
        # ====================================================

        if visible:

            saw_open = True


            if blink_started:

                return_frames += 1


                if (
                    return_frames
                    >=
                    BLINK_RETURN_FRAMES
                ):

                    return True


            else:

                missing_frames = 0


        # ====================================================
        # Eyes temporarily missing
        # ====================================================

        else:

            if saw_open:

                missing_frames += 1


                if (
                    missing_frames
                    >=
                    BLINK_MISSING_FRAMES
                ):

                    blink_started = True

                    return_frames = 0


        draw_face_box(
            frame,
            face
        )


        draw_text(
            frame,
            "SENTINEL LIVENESS CHECK",
            35
        )


        draw_text(
            frame,
            "BLINK NATURALLY",
            70
        )


        if blink_started:

            draw_text(
                frame,
                "BLINK DETECTED - OPEN YOUR EYES",
                105,
                0.48,
                1,
                (
                    120,
                    255,
                    120
                )
            )

        else:

            draw_text(
                frame,
                "Waiting for blink...",
                105,
                0.48,
                1
            )


        remaining = max(
            0.0,
            deadline
            -
            time.monotonic()
        )


        draw_text(
            frame,
            f"Time remaining: {remaining:.1f}s",
            135,
            0.43,
            1
        )


        draw_text(
            frame,
            "Q / ESC = CANCEL",
            frame.shape[
                0
            ] - 25,
            0.45,
            1
        )


        cv2.imshow(
            WINDOW_NAME,
            frame
        )


        key = (
            cv2.waitKey(
                1
            )
            &
            0xFF
        )


        if key in (
            ord(
                "q"
            ),
            27
        ):

            return False


    return False


# ============================================================
# MOVEMENT CHALLENGE
# ============================================================

def run_movement_challenge(
    camera,
    face_detector,
    baseline,
    direction,
    deadline
):

    confirmation_frames = 0


    while (
        time.monotonic()
        <
        deadline
    ):

        ok, frame = camera.read()


        if not ok:

            continue


        frame = cv2.flip(
            frame,
            1
        )


        gray, face = detect_primary_face(
            frame,
            face_detector
        )


        direction_passed = False

        difference = 0.0

        required = (
            frame.shape[
                1
            ]
            *
            MOVEMENT_THRESHOLD
        )


        if face is not None:

            x, y, w, h = face


            center_x = (
                x
                +
                w / 2
            )


            difference = (
                center_x
                -
                baseline[
                    "x"
                ]
            )


            # =================================================
            # MOVE LEFT
            # =================================================

            if (
                direction
                ==
                "MOVE_LEFT"

                and

                difference
                <=
                -required
            ):

                direction_passed = True


            # =================================================
            # MOVE RIGHT
            # =================================================

            elif (
                direction
                ==
                "MOVE_RIGHT"

                and

                difference
                >=
                required
            ):

                direction_passed = True


        # ====================================================
        # Multi-frame confirmation
        # ====================================================

        if direction_passed:

            confirmation_frames += 1

        else:

            confirmation_frames = 0


        if (
            confirmation_frames
            >=
            MOVEMENT_CONFIRM_FRAMES
        ):

            return True


        draw_face_box(
            frame,
            face
        )


        draw_text(
            frame,
            "SENTINEL LIVENESS CHECK",
            35
        )


        draw_text(
            frame,
            challenge_instruction(
                direction
            ),
            70
        )


        draw_text(
            frame,
            (
                "Move slightly - "
                "you do not need a large movement."
            ),
            105,
            0.47,
            1
        )


        # ====================================================
        # Movement progress
        # ====================================================

        if direction == "MOVE_LEFT":

            movement_amount = max(
                0.0,
                -difference
            )

        else:

            movement_amount = max(
                0.0,
                difference
            )


        movement_progress = (
            movement_amount
            /
            required
            if required > 0
            else 0.0
        )


        movement_progress = max(
            0.0,
            min(
                1.0,
                movement_progress
            )
        )


        draw_progress_bar(
            frame,
            movement_progress,
            125
        )


        draw_text(
            frame,
            (
                "Confirmation: "
                f"{confirmation_frames}/"
                f"{MOVEMENT_CONFIRM_FRAMES}"
            ),
            165,
            0.45,
            1
        )


        remaining = max(
            0.0,
            deadline
            -
            time.monotonic()
        )


        draw_text(
            frame,
            f"Time remaining: {remaining:.1f}s",
            195,
            0.43,
            1
        )


        draw_text(
            frame,
            "Q / ESC = CANCEL",
            frame.shape[
                0
            ] - 25,
            0.45,
            1
        )


        cv2.imshow(
            WINDOW_NAME,
            frame
        )


        key = (
            cv2.waitKey(
                1
            )
            &
            0xFF
        )


        if key in (
            ord(
                "q"
            ),
            27
        ):

            return False


    return False


# ============================================================
# RESULT SCREEN
# ============================================================

def show_result(
    camera,
    face_detector,
    passed
):

    started = time.monotonic()


    while (
        time.monotonic()
        -
        started
        <
        1.5
    ):

        ok, frame = camera.read()


        if not ok:

            continue


        frame = cv2.flip(
            frame,
            1
        )


        gray, face = detect_primary_face(
            frame,
            face_detector
        )


        if passed:

            color = (
                120,
                255,
                120
            )

            title = (
                "LIVENESS VERIFIED"
            )

            subtitle = (
                "PHYSICAL PRESENCE CONFIRMED"
            )

        else:

            color = (
                80,
                80,
                255
            )

            title = (
                "LIVENESS FAILED"
            )

            subtitle = (
                "IDENTITY NOT AUTHORIZED"
            )


        draw_face_box(
            frame,
            face,
            color
        )


        draw_text(
            frame,
            title,
            45,
            0.80,
            2,
            color
        )


        draw_text(
            frame,
            subtitle,
            80,
            0.48,
            1,
            color
        )


        cv2.imshow(
            WINDOW_NAME,
            frame
        )


        cv2.waitKey(
            1
        )


# ============================================================
# VERIFY LIVENESS
# ============================================================

def verify_liveness(
    camera_index=CAMERA_INDEX
):

    face_detector, eye_detector = (
        create_detectors()
    )


    camera = cv2.VideoCapture(
        camera_index
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


    cv2.namedWindow(
        WINDOW_NAME,
        cv2.WINDOW_NORMAL
    )


    started = time.monotonic()


    try:

        print(
            "[LIVENESS] "
            "Look straight at the camera..."
        )


        baseline = acquire_baseline(
            camera,
            face_detector
        )


        if baseline is None:

            return {

                "passed":
                    False,

                "reason":
                    "FACE_NOT_FOUND",

                "version":
                    LIVENESS_VERSION
            }


        # ====================================================
        # Random challenge sequence
        # ====================================================

        challenges = [

            "BLINK",

            "MOVE_LEFT",

            "MOVE_RIGHT"
        ]


        random.shuffle(
            challenges
        )


        completed = []


        for challenge in challenges:

            if (
                time.monotonic()
                -
                started
                >
                TOTAL_TIMEOUT
            ):

                show_result(
                    camera,
                    face_detector,
                    False
                )

                return {

                    "passed":
                        False,

                    "reason":
                        "TOTAL_TIMEOUT",

                    "completed":
                        completed,

                    "version":
                        LIVENESS_VERSION
                }


            print(
                "[LIVENESS] Challenge:",
                challenge
            )


            deadline = (
                time.monotonic()
                +
                CHALLENGE_TIMEOUT
            )


            # =================================================
            # BLINK
            # =================================================

            if challenge == "BLINK":

                success = (
                    run_blink_challenge(
                        camera,
                        face_detector,
                        eye_detector,
                        deadline
                    )
                )


            # =================================================
            # HEAD MOVEMENT
            # =================================================

            else:

                success = (
                    run_movement_challenge(
                        camera,
                        face_detector,
                        baseline,
                        challenge,
                        deadline
                    )
                )


            if not success:

                show_result(
                    camera,
                    face_detector,
                    False
                )


                return {

                    "passed":
                        False,

                    "reason":
                        (
                            "CHALLENGE_FAILED_"
                            +
                            challenge
                        ),

                    "completed":
                        completed,

                    "version":
                        LIVENESS_VERSION
                }


            completed.append(
                challenge
            )


            print(
                "[LIVENESS] Passed:",
                challenge
            )


            time.sleep(
                0.30
            )


        # ====================================================
        # SUCCESS
        # ====================================================

        show_result(
            camera,
            face_detector,
            True
        )


        return {

            "passed":
                True,

            "reason":
                "ACTIVE_LIVENESS_PASSED",

            "completed":
                completed,

            "score":
                100.0,

            "version":
                LIVENESS_VERSION,

            "assurance":
                "BASIC_ACTIVE_CHALLENGE"
        }


    finally:

        camera.release()

        cv2.destroyAllWindows()


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    face_detector = None

    eye_detector = None


    try:

        face_detector, eye_detector = (
            create_detectors()
        )

    except Exception:

        pass


    camera = cv2.VideoCapture(
        CAMERA_INDEX
    )


    try:

        camera_ok = (
            camera.isOpened()
        )

    finally:

        camera.release()


    passed = (

        camera_ok

        and

        face_detector is not None

        and

        eye_detector is not None
    )


    return {

        "status":
            (
                "PASS"
                if passed
                else
                "PARTIAL"
            ),

        "liveness_version":
            LIVENESS_VERSION,

        "camera":
            camera_ok,

        "face_detector":
            (
                face_detector
                is not None
            ),

        "eye_detector":
            (
                eye_detector
                is not None
            ),

        "movement_threshold":
            MOVEMENT_THRESHOLD,

        "movement_confirmation_frames":
            MOVEMENT_CONFIRM_FRAMES,

        "challenge_timeout":
            CHALLENGE_TIMEOUT,

        "challenges":
            [

                "BLINK",

                "MOVE_LEFT",

                "MOVE_RIGHT"
            ],

        "safety":
            {

                "processing_local":
                    True,

                "images_persisted":
                    False,

                "internet_upload":
                    False,

                "shell_execution":
                    False,

                "payload_execution":
                    False
            },

        "security_note":
            (
                "V1.1 provides basic active "
                "liveness verification. "
                "Critical operations should still "
                "require additional owner confirmation."
            )
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    import pprint


    pprint.pp(
        verify_liveness()
    )