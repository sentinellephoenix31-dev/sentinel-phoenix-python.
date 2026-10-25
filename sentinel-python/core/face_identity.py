import json
import os
import re
import time
from datetime import datetime, timezone

import cv2
import numpy as np


# ============================================================
# SENTINEL PHOENIX
# FACE IDENTITY CORE V3
#
# ROBUST OWNER / GUEST / UNKNOWN RECOGNITION
#
# Improvements:
# - Low-light normalization
# - CLAHE local contrast
# - Reduced dependency on hair / upper forehead
# - Multi-condition training augmentation
# - Unified recognition pipeline
# - OWNER / GUEST / UNKNOWN
# - Local-only biometric processing
# ============================================================


FACE_IDENTITY_VERSION = "3.0"

CAMERA_INDEX = 0

OWNER_LABEL = 1

MATCH_THRESHOLD = 68.0

FACE_WIDTH = 180
FACE_HEIGHT = 180

UNKNOWN_EVIDENCE_COOLDOWN = 30.0

DEPARTURE_SECONDS = 3.0


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

IDENTITY_DIR = os.path.join(
    DATA_DIR,
    "identity"
)

OWNER_DIR = os.path.join(
    IDENTITY_DIR,
    "owner"
)

GUESTS_DIR = os.path.join(
    IDENTITY_DIR,
    "guests"
)

MODELS_DIR = os.path.join(
    IDENTITY_DIR,
    "models"
)

EVIDENCE_DIR = os.path.join(
    IDENTITY_DIR,
    "evidence"
)

REGISTRY_FILE = os.path.join(
    IDENTITY_DIR,
    "identity_registry.json"
)

MODEL_FILE = os.path.join(
    MODELS_DIR,
    "identity_lbph.yml"
)

PRESENCE_LOG_FILE = os.path.join(
    DATA_DIR,
    "presence_events.jsonl"
)


# ============================================================
# PERMISSIONS
# ============================================================

ROLE_PERMISSIONS = {

    "OWNER": {
        "ASK_GENERAL",
        "ASK_SECURITY",
        "VIEW_HISTORY",
        "VIEW_INCIDENTS",
        "VIEW_EXTERNAL_KNOWLEDGE",
        "MANAGE_GUESTS",
        "VIEW_EVIDENCE",
        "CHANGE_SECURITY_POLICY",
        "RECOVERY_REVIEW",
        "MODEL_REVIEW",
        "SENSITIVE_ACTION_REVIEW"
    },

    "GUEST": {
        "ASK_GENERAL",
        "VIEW_EXTERNAL_KNOWLEDGE"
    },

    "UNKNOWN": set()
}


SENSITIVE_ACTIONS = {
    "MANAGE_GUESTS",
    "CHANGE_SECURITY_POLICY",
    "RECOVERY_REVIEW",
    "MODEL_REVIEW",
    "SENSITIVE_ACTION_REVIEW"
}


# ============================================================
# STORAGE
# ============================================================

def ensure_identity_storage():

    for directory in (
        DATA_DIR,
        IDENTITY_DIR,
        OWNER_DIR,
        GUESTS_DIR,
        MODELS_DIR,
        EVIDENCE_DIR
    ):

        os.makedirs(
            directory,
            exist_ok=True
        )


def utc_now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# CASCADE
# ============================================================

def find_cascade(
    filename
):

    possible_paths = []

    try:

        possible_paths.append(
            os.path.join(
                cv2.data.haarcascades,
                filename
            )
        )

    except Exception:

        pass


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


        detector = cv2.CascadeClassifier(
            path
        )


        if not detector.empty():

            return detector


    return None


def create_face_detector():

    detector = find_cascade(
        "haarcascade_frontalface_default.xml"
    )

    if detector is None:

        raise RuntimeError(
            "FACE_CASCADE_UNAVAILABLE"
        )

    return detector


# ============================================================
# REGISTRY
# ============================================================

def default_registry():

    return {

        "version":
            FACE_IDENTITY_VERSION,

        "next_label":
            2,

        "identities": {

            "1": {
                "name":
                    "OWNER",

                "role":
                    "OWNER"
            }
        }
    }


def load_registry():

    ensure_identity_storage()

    if not os.path.isfile(
        REGISTRY_FILE
    ):

        registry = default_registry()

        save_registry(
            registry
        )

        return registry


    try:

        with open(
            REGISTRY_FILE,
            "r",
            encoding="utf-8"
        ) as handle:

            data = json.load(
                handle
            )

    except (
        OSError,
        json.JSONDecodeError
    ):

        data = default_registry()


    if not isinstance(
        data,
        dict
    ):

        data = default_registry()


    identities = data.get(
        "identities"
    )


    if not isinstance(
        identities,
        dict
    ):

        identities = {}


    # OWNER must always be label 1.

    identities[
        str(
            OWNER_LABEL
        )
    ] = {

        "name":
            "OWNER",

        "role":
            "OWNER"
    }


    data[
        "identities"
    ] = identities


    used_labels = []

    for key in identities:

        try:

            used_labels.append(
                int(
                    key
                )
            )

        except ValueError:

            pass


    data[
        "next_label"
    ] = max(
        [
            2
        ]
        +
        [
            label + 1
            for label in used_labels
        ]
    )


    data[
        "version"
    ] = FACE_IDENTITY_VERSION


    return data


def save_registry(
    registry
):

    ensure_identity_storage()

    temporary = (
        REGISTRY_FILE
        +
        ".tmp"
    )


    with open(
        temporary,
        "w",
        encoding="utf-8"
    ) as handle:

        json.dump(
            registry,
            handle,
            indent=2,
            ensure_ascii=False
        )


    os.replace(
        temporary,
        REGISTRY_FILE
    )


# ============================================================
# NAME SAFETY
# ============================================================

def safe_identity_name(
    name
):

    value = str(
        name
    ).strip()

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

    value = value.strip(
        "_"
    )

    return value[
        :40
    ]


# ============================================================
# LOW-LIGHT ENHANCEMENT
# ============================================================

def enhance_gray(
    gray
):

    if len(
        gray.shape
    ) == 3:

        gray = cv2.cvtColor(
            gray,
            cv2.COLOR_BGR2GRAY
        )


    gray = gray.astype(
        np.uint8
    )


    # ========================================================
    # Local contrast normalization
    # ========================================================

    clahe = cv2.createCLAHE(
        clipLimit=2.2,
        tileGridSize=(8, 8)
    )


    enhanced = clahe.apply(
        gray
    )


    mean_light = float(
        np.mean(
            enhanced
        )
    )


    # ========================================================
    # Additional correction in dark scenes
    # ========================================================

    if mean_light < 55:

        enhanced = cv2.convertScaleAbs(
            enhanced,
            alpha=1.45,
            beta=18
        )


    elif mean_light < 80:

        enhanced = cv2.convertScaleAbs(
            enhanced,
            alpha=1.20,
            beta=8
        )


    return enhanced


# ============================================================
# FACE DETECTION
# ============================================================

def detect_faces(
    frame,
    detector
):

    if frame is None:

        return (
            None,
            []
        )


    if len(
        frame.shape
    ) == 3:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

    else:

        gray = frame.copy()


    detection_gray = enhance_gray(
        gray
    )


    faces = detector.detectMultiScale(

        detection_gray,

        scaleFactor=1.12,

        minNeighbors=5,

        minSize=(90, 90)
    )


    faces = sorted(
        faces,
        key=lambda box:
            box[2]
            *
            box[3],
        reverse=True
    )


    return (
        detection_gray,
        faces
    )


# ============================================================
# FACE NORMALIZATION
# ============================================================

def crop_identity_region(
    face
):

    height, width = face.shape[
        :2
    ]


    # ========================================================
    # Remove part of the upper forehead/hair region.
    #
    # This makes recognition less dependent on:
    # - bonnet
    # - cap
    # - hair
    # - hairstyle
    #
    # Eyes, nose, cheeks and mouth remain.
    # ========================================================

    top = int(
        height
        *
        0.12
    )

    bottom = int(
        height
        *
        0.96
    )

    left = int(
        width
        *
        0.06
    )

    right = int(
        width
        *
        0.94
    )


    cropped = face[
        top:bottom,
        left:right
    ]


    if cropped.size == 0:

        return face


    return cropped


def preprocess_face(
    face
):

    if face is None:

        return None


    if len(
        face.shape
    ) == 3:

        gray = cv2.cvtColor(
            face,
            cv2.COLOR_BGR2GRAY
        )

    else:

        gray = face.copy()


    gray = enhance_gray(
        gray
    )


    gray = crop_identity_region(
        gray
    )


    normalized = cv2.resize(
        gray,
        (
            FACE_WIDTH,
            FACE_HEIGHT
        ),
        interpolation=cv2.INTER_AREA
    )


    normalized = cv2.GaussianBlur(
        normalized,
        (3, 3),
        0
    )


    return normalized


# ============================================================
# VISUAL QUALITY
# ============================================================

def visual_quality(
    face
):

    processed = preprocess_face(
        face
    )


    if processed is None:

        return {

            "usable":
                False,

            "reason":
                "NO_FACE"
        }


    brightness = float(
        np.mean(
            processed
        )
    )


    sharpness = float(
        cv2.Laplacian(
            processed,
            cv2.CV_64F
        ).var()
    )


    # Do not guess when the webcam contains almost
    # no usable facial information.

    if brightness < 18:

        return {

            "usable":
                False,

            "reason":
                "INSUFFICIENT_LIGHT",

            "brightness":
                round(
                    brightness,
                    2
                ),

            "sharpness":
                round(
                    sharpness,
                    2
                )
        }


    if sharpness < 8:

        return {

            "usable":
                False,

            "reason":
                "IMAGE_TOO_BLURRY",

            "brightness":
                round(
                    brightness,
                    2
                ),

            "sharpness":
                round(
                    sharpness,
                    2
                )
        }


    return {

        "usable":
            True,

        "reason":
            "OK",

        "brightness":
            round(
                brightness,
                2
            ),

        "sharpness":
            round(
                sharpness,
                2
            )
    }


# ============================================================
# TRAINING AUGMENTATION
# ============================================================

def training_variants(
    face
):

    base = preprocess_face(
        face
    )


    if base is None:

        return []


    variants = [
        base
    ]


    # ========================================================
    # Slightly darker version
    # ========================================================

    darker = cv2.convertScaleAbs(
        base,
        alpha=0.78,
        beta=0
    )


    # ========================================================
    # Slightly brighter version
    # ========================================================

    brighter = cv2.convertScaleAbs(
        base,
        alpha=1.18,
        beta=10
    )


    # ========================================================
    # Different contrast
    # ========================================================

    contrast = cv2.equalizeHist(
        base
    )


    variants.extend(
        [
            darker,
            brighter,
            contrast
        ]
    )


    return variants


# ============================================================
# RECOGNIZER
# ============================================================

def create_recognizer():

    if not hasattr(
        cv2,
        "face"
    ):

        raise RuntimeError(
            "OPENCV_FACE_MODULE_UNAVAILABLE"
        )


    return cv2.face.LBPHFaceRecognizer_create(
        radius=1,
        neighbors=8,
        grid_x=8,
        grid_y=8
    )


def load_recognizer():

    if not os.path.isfile(
        MODEL_FILE
    ):

        raise RuntimeError(
            "IDENTITY_MODEL_NOT_FOUND"
        )


    recognizer = create_recognizer()


    recognizer.read(
        MODEL_FILE
    )


    return recognizer


# ============================================================
# LOOKUP IDENTITY
# ============================================================

def identity_from_label(
    label
):

    registry = load_registry()


    identity = registry[
        "identities"
    ].get(
        str(
            int(
                label
            )
        )
    )


    if identity:

        return {

            "name":
                identity.get(
                    "name",
                    "UNKNOWN"
                ),

            "role":
                identity.get(
                    "role",
                    "UNKNOWN"
                )
        }


    if int(
        label
    ) == OWNER_LABEL:

        return {

            "name":
                "OWNER",

            "role":
                "OWNER"
        }


    return {

        "name":
            "UNKNOWN",

        "role":
            "UNKNOWN"
    }


# ============================================================
# CLASSIFY ONE FACE
# ============================================================

def classify_face(
    face,
    recognizer
):

    quality = visual_quality(
        face
    )


    if not quality.get(
        "usable"
    ):

        return {

            "role":
                "UNKNOWN",

            "name":
                "UNKNOWN",

            "confidence":
                0.0,

            "distance":
                999.0,

            "quality":
                quality,

            "reason":
                quality.get(
                    "reason"
                )
        }


    processed = preprocess_face(
        face
    )


    try:

        label, distance = recognizer.predict(
            processed
        )

    except cv2.error:

        return {

            "role":
                "UNKNOWN",

            "name":
                "UNKNOWN",

            "confidence":
                0.0,

            "distance":
                999.0,

            "quality":
                quality,

            "reason":
                "PREDICTION_FAILED"
        }


    distance = float(
        distance
    )


    # LBPH:
    # smaller distance = better match.

    confidence = max(
        0.0,
        min(
            100.0,
            100.0
            -
            distance
        )
    )


    if distance > MATCH_THRESHOLD:

        return {

            "role":
                "UNKNOWN",

            "name":
                "UNKNOWN",

            "confidence":
                round(
                    confidence,
                    2
                ),

            "distance":
                round(
                    distance,
                    2
                ),

            "quality":
                quality,

            "reason":
                "NO_TRUSTED_MATCH"
        }


    identity = identity_from_label(
        label
    )


    return {

        "role":
            identity[
                "role"
            ],

        "name":
            identity[
                "name"
            ],

        "label":
            int(
                label
            ),

        "confidence":
            round(
                confidence,
                2
            ),

        "distance":
            round(
                distance,
                2
            ),

        "quality":
            quality,

        "reason":
            "MATCH"
    }


# ============================================================
# RECOGNIZE FRAME
# ============================================================

def recognize_frame(
    frame,
    recognizer,
    detector
):

    gray, faces = detect_faces(
        frame,
        detector
    )


    if gray is None:

        return []


    results = []


    for x, y, w, h in faces:

        face = gray[
            y:y + h,
            x:x + w
        ]


        if face.size == 0:

            continue


        identity = classify_face(
            face,
            recognizer
        )


        identity[
            "box"
        ] = {

            "x":
                int(
                    x
                ),

            "y":
                int(
                    y
                ),

            "w":
                int(
                    w
                ),

            "h":
                int(
                    h
                )
        }


        results.append(
            identity
        )


    return results


# ============================================================
# IMAGE FILES
# ============================================================

def image_files(
    directory
):

    if not os.path.isdir(
        directory
    ):

        return []


    results = []


    for filename in sorted(
        os.listdir(
            directory
        )
    ):

        extension = os.path.splitext(
            filename
        )[1].lower()


        if extension not in (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp"
        ):

            continue


        path = os.path.join(
            directory,
            filename
        )


        if os.path.isfile(
            path
        ):

            results.append(
                path
            )


    return results


# ============================================================
# CAPTURE SAMPLES
# ============================================================

def capture_identity_samples(
    output_directory,
    samples=25,
    camera_index=CAMERA_INDEX
):

    ensure_identity_storage()


    os.makedirs(
        output_directory,
        exist_ok=True
    )


    detector = create_face_detector()


    camera = cv2.VideoCapture(
        camera_index
    )


    if not camera.isOpened():

        raise RuntimeError(
            "CAMERA_NOT_AVAILABLE"
        )


    collected = 0


    try:

        while collected < samples:

            ok, frame = camera.read()


            if not ok:

                continue


            frame = cv2.flip(
                frame,
                1
            )


            gray, faces = detect_faces(
                frame,
                detector
            )


            if faces:

                x, y, w, h = faces[
                    0
                ]


                face = gray[
                    y:y + h,
                    x:x + w
                ]


                quality = visual_quality(
                    face
                )


                if quality.get(
                    "usable"
                ):

                    processed = preprocess_face(
                        face
                    )


                    timestamp = int(
                        time.time()
                        *
                        1000
                    )


                    filename = (
                        f"sample_{timestamp}_"
                        f"{collected + 1:03d}.jpg"
                    )


                    path = os.path.join(
                        output_directory,
                        filename
                    )


                    cv2.imwrite(
                        path,
                        processed
                    )


                    collected += 1


                    print(
                        "[IDENTITY] Captured "
                        f"{collected}/{samples}"
                    )


                    # Prevent 25 virtually identical
                    # frames being collected instantly.

                    time.sleep(
                        0.12
                    )


            display = frame.copy()


            cv2.putText(
                display,
                (
                    "SENTINEL IDENTITY ENROLLMENT "
                    f"{collected}/{samples}"
                ),
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )


            cv2.imshow(
                "Sentinel Phoenix - Identity Enrollment",
                display
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


    return collected


# ============================================================
# OWNER ENROLLMENT
# ============================================================

def enroll_owner(
    samples=25,
    append=True
):

    ensure_identity_storage()


    if not append:

        for path in image_files(
            OWNER_DIR
        ):

            try:

                os.remove(
                    path
                )

            except OSError:

                pass


    captured = capture_identity_samples(
        OWNER_DIR,
        samples=samples
    )


    return {

        "status":
            "OWNER_ENROLLED",

        "samples":
            captured,

        "append":
            bool(
                append
            ),

        "total_owner_samples":
            len(
                image_files(
                    OWNER_DIR
                )
            )
    }


# ============================================================
# GUEST LABEL
# ============================================================

def guest_label(
    guest_name,
    registry
):

    guest_name = safe_identity_name(
        guest_name
    )


    for label, identity in registry[
        "identities"
    ].items():

        if (
            identity.get(
                "role"
            )
            ==
            "GUEST"
            and
            identity.get(
                "name"
            )
            ==
            guest_name
        ):

            return int(
                label
            )


    label = int(
        registry.get(
            "next_label",
            2
        )
    )


    registry[
        "next_label"
    ] = label + 1


    registry[
        "identities"
    ][
        str(
            label
        )
    ] = {

        "name":
            guest_name,

        "role":
            "GUEST"
    }


    return label


# ============================================================
# GUEST ENROLLMENT
# ============================================================

def enroll_guest(
    guest_name,
    owner_approved=False,
    owner_verified=False,
    samples=25
):

    if not owner_approved:

        return {

            "status":
                "DENIED",

            "reason":
                "OWNER_APPROVAL_REQUIRED"
        }


    if not owner_verified:

        return {

            "status":
                "DENIED",

            "reason":
                "OWNER_VERIFICATION_REQUIRED"
        }


    guest_name = safe_identity_name(
        guest_name
    )


    if not guest_name:

        return {

            "status":
                "DENIED",

            "reason":
                "INVALID_GUEST_NAME"
        }


    directory = os.path.join(
        GUESTS_DIR,
        guest_name
    )


    os.makedirs(
        directory,
        exist_ok=True
    )


    captured = capture_identity_samples(
        directory,
        samples=samples
    )


    registry = load_registry()


    label = guest_label(
        guest_name,
        registry
    )


    save_registry(
        registry
    )


    return {

        "status":
            "GUEST_ENROLLED",

        "guest":
            guest_name,

        "label":
            label,

        "samples":
            captured
    }


# ============================================================
# TRAIN MODEL
# ============================================================

def train_identity_model():

    ensure_identity_storage()


    recognizer = create_recognizer()


    faces = []

    labels = []


    raw_samples = 0

    owner_samples = 0

    guest_samples = 0


    registry = load_registry()


    # ========================================================
    # OWNER
    # ========================================================

    for path in image_files(
        OWNER_DIR
    ):

        image = cv2.imread(
            path,
            cv2.IMREAD_GRAYSCALE
        )


        if image is None:

            continue


        variants = training_variants(
            image
        )


        if not variants:

            continue


        raw_samples += 1

        owner_samples += 1


        for variant in variants:

            faces.append(
                variant
            )

            labels.append(
                OWNER_LABEL
            )


    # ========================================================
    # GUESTS
    # ========================================================

    if os.path.isdir(
        GUESTS_DIR
    ):

        for guest_name in sorted(
            os.listdir(
                GUESTS_DIR
            )
        ):

            guest_directory = os.path.join(
                GUESTS_DIR,
                guest_name
            )


            if not os.path.isdir(
                guest_directory
            ):

                continue


            label = guest_label(
                guest_name,
                registry
            )


            for path in image_files(
                guest_directory
            ):

                image = cv2.imread(
                    path,
                    cv2.IMREAD_GRAYSCALE
                )


                if image is None:

                    continue


                variants = training_variants(
                    image
                )


                if not variants:

                    continue


                raw_samples += 1

                guest_samples += 1


                for variant in variants:

                    faces.append(
                        variant
                    )

                    labels.append(
                        label
                    )


    if not faces:

        return {

            "status":
                "NO_TRAINING_DATA",

            "samples":
                0
        }


    recognizer.train(
        faces,
        np.array(
            labels,
            dtype=np.int32
        )
    )


    recognizer.write(
        MODEL_FILE
    )


    save_registry(
        registry
    )


    identity_labels = set(
        labels
    )


    return {

        "status":
            "TRAINED",

        "raw_samples":
            raw_samples,

        "training_faces":
            len(
                faces
            ),

        "owner_samples":
            owner_samples,

        "guest_samples":
            guest_samples,

        "identities":
            len(
                identity_labels
            ),

        "model":
            MODEL_FILE,

        "preprocessing":
            "ROBUST_V3"
    }


# Compatibility alias.

train_model = train_identity_model


# ============================================================
# UNKNOWN EVIDENCE
# ============================================================

def save_unknown_evidence(
    frame,
    confidence=None
):

    if frame is None:

        return None


    ensure_identity_storage()


    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%S_%fZ"
    )


    filename = (
        "unknown_"
        +
        timestamp
        +
        ".jpg"
    )


    path = os.path.join(
        EVIDENCE_DIR,
        filename
    )


    success = cv2.imwrite(
        path,
        frame,
        [
            cv2.IMWRITE_JPEG_QUALITY,
            88
        ]
    )


    if not success:

        return None


    return path


# ============================================================
# PRESENCE LOG
# ============================================================

def log_presence_event(
    event_type,
    role=None,
    name=None,
    confidence=None,
    evidence=None,
    extra=None
):

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )


    event = {

        "timestamp":
            time.time(),

        "timestamp_iso":
            utc_now_iso(),

        "event":
            event_type,

        "role":
            role,

        "name":
            name,

        "confidence":
            confidence,

        "evidence":
            evidence
    }


    if isinstance(
        extra,
        dict
    ):

        event.update(
            extra
        )


    with open(
        PRESENCE_LOG_FILE,
        "a",
        encoding="utf-8"
    ) as handle:

        handle.write(
            json.dumps(
                event,
                ensure_ascii=False
            )
            +
            "\n"
        )


    return event


# ============================================================
# PRESENCE TRACKER
# ============================================================

class PresenceTracker:

    def __init__(
        self
    ):

        self.current_role = None

        self.current_name = None

        self.last_seen = None

        self.owner_seen_before = False

        self.last_unknown_evidence = 0.0


    def observe(
        self,
        role,
        name,
        confidence,
        frame=None
    ):

        now = time.time()


        role = str(
            role
            or
            "UNKNOWN"
        ).upper()


        name = str(
            name
            or
            role
        )


        # ====================================================
        # OWNER
        # ====================================================

        if role == "OWNER":

            if self.current_role != "OWNER":

                event = (
                    "OWNER_RETURNED"
                    if self.owner_seen_before
                    else
                    "OWNER_PRESENT"
                )


                log_presence_event(
                    event,
                    role="OWNER",
                    name=name,
                    confidence=confidence
                )


                self.owner_seen_before = True


            self.current_role = "OWNER"

            self.current_name = name

            self.last_seen = now

            return


        # ====================================================
        # GUEST
        # ====================================================

        if role == "GUEST":

            if (
                self.current_role != "GUEST"
                or
                self.current_name != name
            ):

                log_presence_event(
                    "GUEST_PRESENT",
                    role="GUEST",
                    name=name,
                    confidence=confidence
                )


            self.current_role = "GUEST"

            self.current_name = name

            self.last_seen = now

            return


        # ====================================================
        # UNKNOWN
        # ====================================================

        evidence = None


        if (
            frame is not None
            and
            now
            -
            self.last_unknown_evidence
            >=
            UNKNOWN_EVIDENCE_COOLDOWN
        ):

            evidence = save_unknown_evidence(
                frame,
                confidence=confidence
            )


            self.last_unknown_evidence = now


            log_presence_event(
                "UNKNOWN_PERSON",
                role="UNKNOWN",
                name="UNKNOWN",
                confidence=confidence,
                evidence=evidence,
                extra={
                    "access":
                        "DENIED"
                }
            )


        self.current_role = "UNKNOWN"

        self.current_name = "UNKNOWN"

        self.last_seen = now


    def update_departures(
        self
    ):

        if self.last_seen is None:

            return


        now = time.time()


        if (
            now
            -
            self.last_seen
            <
            DEPARTURE_SECONDS
        ):

            return


        if self.current_role == "OWNER":

            log_presence_event(
                "OWNER_LEFT",
                role="OWNER",
                name=self.current_name
            )


        elif self.current_role == "GUEST":

            log_presence_event(
                "GUEST_LEFT",
                role="GUEST",
                name=self.current_name
            )


        self.current_role = None

        self.current_name = None

        self.last_seen = None


# ============================================================
# PERMISSIONS
# ============================================================

def get_permissions(
    role
):

    role = str(
        role
        or
        "UNKNOWN"
    ).upper()


    return set(
        ROLE_PERMISSIONS.get(
            role,
            set()
        )
    )


def check_permission(
    role,
    action,
    liveness_passed=False
):

    role = str(
        role
        or
        "UNKNOWN"
    ).upper()


    action = str(
        action
    ).upper()


    if action not in get_permissions(
        role
    ):

        return {

            "allowed":
                False,

            "reason":
                "ROLE_PERMISSION_DENIED"
        }


    if (
        action in SENSITIVE_ACTIONS
        and
        (
            role != "OWNER"
            or
            not liveness_passed
        )
    ):

        return {

            "allowed":
                False,

            "reason":
                "OWNER_LIVENESS_REQUIRED"
        }


    return {

        "allowed":
            True,

        "reason":
            "AUTHORIZED"
    }


def is_action_allowed(
    role,
    action,
    liveness_passed=False
):

    return check_permission(
        role,
        action,
        liveness_passed
    ).get(
        "allowed",
        False
    )


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    ensure_identity_storage()


    detector_ok = False

    try:

        detector = create_face_detector()

        detector_ok = (
            detector is not None
        )

    except Exception:

        detector_ok = False


    opencv_face = hasattr(
        cv2,
        "face"
    )


    model_exists = os.path.isfile(
        MODEL_FILE
    )


    registry = load_registry()


    owner_samples = len(
        image_files(
            OWNER_DIR
        )
    )


    sensitive_denied_without_liveness = (
        check_permission(
            "OWNER",
            "MANAGE_GUESTS",
            liveness_passed=False
        ).get(
            "allowed"
        )
        is False
    )


    sensitive_allowed_with_liveness = (
        check_permission(
            "OWNER",
            "MANAGE_GUESTS",
            liveness_passed=True
        ).get(
            "allowed"
        )
        is True
    )


    passed = all(
        [
            detector_ok,
            opencv_face,
            model_exists,
            owner_samples > 0,
            sensitive_denied_without_liveness,
            sensitive_allowed_with_liveness
        ]
    )


    return {

        "status":
            (
                "PASS"
                if passed
                else
                "PARTIAL"
            ),

        "version":
            FACE_IDENTITY_VERSION,

        "camera_index":
            CAMERA_INDEX,

        "face_detector":
            detector_ok,

        "opencv_face":
            opencv_face,

        "identity_model":
            model_exists,

        "owner_samples":
            owner_samples,

        "registered_identities":
            len(
                registry.get(
                    "identities",
                    {}
                )
            ),

        "recognition":
            {

                "threshold":
                    MATCH_THRESHOLD,

                "low_light_normalization":
                    True,

                "clahe":
                    True,

                "forehead_hair_reduction":
                    True,

                "training_augmentation":
                    True,

                "multi_condition_training":
                    True
            },

        "security":
            {

                "owner_liveness_for_sensitive_actions":
                    True,

                "unknown_permissions":
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