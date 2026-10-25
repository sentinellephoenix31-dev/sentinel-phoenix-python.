import json
import os
import time
from collections import defaultdict, deque

import cv2
import numpy as np


# ============================================================
# SENTINEL PHOENIX
# FACE ENGINE V4
#
# MODERN FACE RECOGNITION:
#
# YuNet
#   ↓
# Face detection + 5 landmarks
#   ↓
# SFace alignment
#   ↓
# Facial embedding
#   ↓
# Gallery comparison
#   ↓
# Multi-frame identity verification
#
# OWNER / GUEST / UNKNOWN
#
# Hair, shoulders and clothing are NOT used as identity.
# ============================================================


FACE_ENGINE_VERSION = "4.0"

CAMERA_INDEX = 0


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

MODEL_DIR = os.path.join(
    BASE_DIR,
    "models",
    "face"
)

YUNET_MODEL = os.path.join(
    MODEL_DIR,
    "face_detection_yunet_2026may.onnx"
)

SFACE_MODEL = os.path.join(
    MODEL_DIR,
    "face_recognition_sface_2021dec.onnx"
)


IDENTITY_DIR = os.path.join(
    BASE_DIR,
    "data",
    "identity"
)

V4_DIR = os.path.join(
    IDENTITY_DIR,
    "v4"
)

OWNER_IMAGE_DIR = os.path.join(
    V4_DIR,
    "owner"
)

GUEST_IMAGE_DIR = os.path.join(
    V4_DIR,
    "guests"
)

GALLERY_FILE = os.path.join(
    V4_DIR,
    "sface_gallery.npz"
)

REGISTRY_FILE = os.path.join(
    V4_DIR,
    "registry.json"
)


# ============================================================
# DETECTION CONFIGURATION
# ============================================================

DETECTION_SCORE_THRESHOLD = 0.82

NMS_THRESHOLD = 0.30

TOP_K = 5000


# ============================================================
# RECOGNITION SECURITY
# ============================================================

# OpenCV SFace's reference cosine threshold is around 0.363.
#
# Sentinel intentionally uses a stricter value because
# this is an OWNER authentication system, not simply
# a photo similarity demonstration.

MATCH_THRESHOLD = 0.42


# Best identity must also beat the second-best identity
# by this margin.

IDENTITY_MARGIN = 0.055


# Average only strongest gallery matches.

TOP_REFERENCE_MATCHES = 4


# ============================================================
# MULTI-FRAME VERIFICATION
# ============================================================

VERIFY_WINDOW = 12

OWNER_REQUIRED_VOTES = 7

GUEST_REQUIRED_VOTES = 7

VERIFY_TIMEOUT_SECONDS = 8.0


# ============================================================
# QUALITY
# ============================================================

MIN_FACE_SIZE = 85

MIN_BRIGHTNESS = 22.0

MIN_SHARPNESS = 12.0


# ============================================================
# STORAGE
# ============================================================

def ensure_storage():

    for directory in (
        MODEL_DIR,
        IDENTITY_DIR,
        V4_DIR,
        OWNER_IMAGE_DIR,
        GUEST_IMAGE_DIR
    ):

        os.makedirs(
            directory,
            exist_ok=True
        )


# ============================================================
# MODEL CHECK
# ============================================================

def models_available():

    return {
        "yunet":
            os.path.isfile(
                YUNET_MODEL
            ),

        "sface":
            os.path.isfile(
                SFACE_MODEL
            )
    }


# ============================================================
# CREATE YUNET
# ============================================================

def create_detector(
    input_size=(640, 480)
):

    if not os.path.isfile(
        YUNET_MODEL
    ):

        raise RuntimeError(
            "YUNET_MODEL_NOT_FOUND"
        )


    if hasattr(
        cv2,
        "FaceDetectorYN_create"
    ):

        return cv2.FaceDetectorYN_create(
            YUNET_MODEL,
            "",
            input_size,
            DETECTION_SCORE_THRESHOLD,
            NMS_THRESHOLD,
            TOP_K
        )


    if (
        hasattr(
            cv2,
            "FaceDetectorYN"
        )
        and
        hasattr(
            cv2.FaceDetectorYN,
            "create"
        )
    ):

        return cv2.FaceDetectorYN.create(
            YUNET_MODEL,
            "",
            input_size,
            DETECTION_SCORE_THRESHOLD,
            NMS_THRESHOLD,
            TOP_K
        )


    raise RuntimeError(
        "OPENCV_YUNET_API_UNAVAILABLE"
    )


# ============================================================
# CREATE SFACE
# ============================================================

def create_recognizer():

    if not os.path.isfile(
        SFACE_MODEL
    ):

        raise RuntimeError(
            "SFACE_MODEL_NOT_FOUND"
        )


    if hasattr(
        cv2,
        "FaceRecognizerSF_create"
    ):

        return cv2.FaceRecognizerSF_create(
            SFACE_MODEL,
            ""
        )


    if (
        hasattr(
            cv2,
            "FaceRecognizerSF"
        )
        and
        hasattr(
            cv2.FaceRecognizerSF,
            "create"
        )
    ):

        return cv2.FaceRecognizerSF.create(
            SFACE_MODEL,
            ""
        )


    raise RuntimeError(
        "OPENCV_SFACE_API_UNAVAILABLE"
    )


# ============================================================
# LOW LIGHT NORMALIZATION
# ============================================================

def enhance_low_light(
    frame
):

    if frame is None:

        return frame


    lab = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2LAB
    )


    l_channel, a_channel, b_channel = (
        cv2.split(
            lab
        )
    )


    mean_light = float(
        np.mean(
            l_channel
        )
    )


    if mean_light >= 95:

        return frame


    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8)
    )


    improved_l = clahe.apply(
        l_channel
    )


    enhanced_lab = cv2.merge(
        (
            improved_l,
            a_channel,
            b_channel
        )
    )


    enhanced = cv2.cvtColor(
        enhanced_lab,
        cv2.COLOR_LAB2BGR
    )


    if mean_light < 55:

        enhanced = cv2.convertScaleAbs(
            enhanced,
            alpha=1.18,
            beta=10
        )


    return enhanced


# ============================================================
# DETECTION
# ============================================================

def detect_faces(
    frame,
    detector
):

    if frame is None:

        return (
            frame,
            []
        )


    processed = enhance_low_light(
        frame
    )


    height, width = processed.shape[
        :2
    ]


    detector.setInputSize(
        (
            width,
            height
        )
    )


    result = detector.detect(
        processed
    )


    if isinstance(
        result,
        tuple
    ):

        faces = result[
            1
        ]

    else:

        faces = result


    if faces is None:

        return (
            processed,
            []
        )


    faces = np.asarray(
        faces,
        dtype=np.float32
    )


    faces = sorted(
        faces,
        key=lambda face:
            float(
                face[2]
                *
                face[3]
            ),
        reverse=True
    )


    return (
        processed,
        faces
    )


# ============================================================
# QUALITY CHECK
# ============================================================

def face_quality(
    frame,
    face
):

    x = int(
        face[0]
    )

    y = int(
        face[1]
    )

    width = int(
        face[2]
    )

    height = int(
        face[3]
    )


    if (
        width < MIN_FACE_SIZE
        or
        height < MIN_FACE_SIZE
    ):

        return {
            "usable":
                False,

            "reason":
                "FACE_TOO_SMALL"
        }


    x = max(
        0,
        x
    )

    y = max(
        0,
        y
    )


    x2 = min(
        frame.shape[1],
        x + width
    )

    y2 = min(
        frame.shape[0],
        y + height
    )


    crop = frame[
        y:y2,
        x:x2
    ]


    if crop.size == 0:

        return {
            "usable":
                False,

            "reason":
                "INVALID_FACE_CROP"
        }


    gray = cv2.cvtColor(
        crop,
        cv2.COLOR_BGR2GRAY
    )


    brightness = float(
        np.mean(
            gray
        )
    )


    sharpness = float(
        cv2.Laplacian(
            gray,
            cv2.CV_64F
        ).var()
    )


    if brightness < MIN_BRIGHTNESS:

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


    if sharpness < MIN_SHARPNESS:

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
            ),

        "detector_score":
            round(
                float(
                    face[14]
                ),
                4
            )
    }


# ============================================================
# FACE EMBEDDING
# ============================================================

def extract_embedding(
    frame,
    face,
    recognizer
):

    quality = face_quality(
        frame,
        face
    )


    if not quality.get(
        "usable"
    ):

        return (
            None,
            quality
        )


    face_array = np.asarray(
        face,
        dtype=np.float32
    )


    try:

        aligned = recognizer.alignCrop(
            frame,
            face_array
        )


        feature = recognizer.feature(
            aligned
        )


    except cv2.error as error:

        return (
            None,
            {
                "usable":
                    False,

                "reason":
                    "ALIGNMENT_OR_EMBEDDING_FAILED",

                "error":
                    str(
                        error
                    )
            }
        )


    embedding = np.asarray(
        feature,
        dtype=np.float32
    ).reshape(
        -1
    )


    norm = float(
        np.linalg.norm(
            embedding
        )
    )


    if norm <= 0.0:

        return (
            None,
            {
                "usable":
                    False,

                "reason":
                    "INVALID_EMBEDDING"
            }
        )


    embedding = (
        embedding
        /
        norm
    )


    return (
        embedding,
        quality
    )


# ============================================================
# REGISTRY
# ============================================================

def default_registry():

    return {
        "version":
            FACE_ENGINE_VERSION,

        "identities":
            {
                "OWNER":
                    {
                        "role":
                            "OWNER",

                        "name":
                            "OWNER"
                    }
            }
    }


def load_registry():

    ensure_storage()


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
        data.get(
            "identities"
        ),
        dict
    ):

        data[
            "identities"
        ] = {}


    data[
        "identities"
    ][
        "OWNER"
    ] = {
        "role":
            "OWNER",

        "name":
            "OWNER"
    }


    return data


def save_registry(
    registry
):

    ensure_storage()


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
# GALLERY
# ============================================================

def empty_gallery():

    return {
        "embeddings":
            np.empty(
                (
                    0,
                    128
                ),
                dtype=np.float32
            ),

        "names":
            [],

        "roles":
            []
    }


def load_gallery():

    if not os.path.isfile(
        GALLERY_FILE
    ):

        return empty_gallery()


    try:

        data = np.load(
            GALLERY_FILE,
            allow_pickle=False
        )


        embeddings = np.asarray(
            data[
                "embeddings"
            ],
            dtype=np.float32
        )


        names = [
            str(
                value
            )
            for value in data[
                "names"
            ].tolist()
        ]


        roles = [
            str(
                value
            )
            for value in data[
                "roles"
            ].tolist()
        ]


        return {
            "embeddings":
                embeddings,

            "names":
                names,

            "roles":
                roles
        }


    except Exception:

        return empty_gallery()


def save_gallery(
    embeddings,
    names,
    roles
):

    ensure_storage()


    embeddings = np.asarray(
        embeddings,
        dtype=np.float32
    )


    np.savez_compressed(
        GALLERY_FILE,

        embeddings=
            embeddings,

        names=
            np.asarray(
                names,
                dtype="<U64"
            ),

        roles=
            np.asarray(
                roles,
                dtype="<U16"
            )
    )


# ============================================================
# ADD EMBEDDINGS
# ============================================================

def add_to_gallery(
    embeddings,
    name,
    role,
    replace_identity=False
):

    gallery = load_gallery()


    old_embeddings = gallery[
        "embeddings"
    ]

    old_names = gallery[
        "names"
    ]

    old_roles = gallery[
        "roles"
    ]


    if replace_identity:

        keep_indexes = [
            index
            for index, existing_name
            in enumerate(
                old_names
            )
            if not (
                existing_name == name
                and
                old_roles[
                    index
                ] == role
            )
        ]


        if keep_indexes:

            old_embeddings = (
                old_embeddings[
                    keep_indexes
                ]
            )

            old_names = [
                old_names[
                    index
                ]
                for index in keep_indexes
            ]

            old_roles = [
                old_roles[
                    index
                ]
                for index in keep_indexes
            ]

        else:

            old_embeddings = np.empty(
                (
                    0,
                    embeddings[
                        0
                    ].shape[
                        0
                    ]
                ),
                dtype=np.float32
            )

            old_names = []

            old_roles = []


    new_embeddings = np.asarray(
        embeddings,
        dtype=np.float32
    )


    if old_embeddings.size == 0:

        combined_embeddings = (
            new_embeddings
        )

    else:

        combined_embeddings = np.vstack(
            (
                old_embeddings,
                new_embeddings
            )
        )


    combined_names = (
        old_names
        +
        [
            name
            for _ in embeddings
        ]
    )


    combined_roles = (
        old_roles
        +
        [
            role
            for _ in embeddings
        ]
    )


    save_gallery(
        combined_embeddings,
        combined_names,
        combined_roles
    )


# ============================================================
# COSINE MATCHING
# ============================================================

def match_embedding(
    embedding
):

    gallery = load_gallery()


    gallery_embeddings = gallery[
        "embeddings"
    ]


    if gallery_embeddings.size == 0:

        return {
            "role":
                "UNKNOWN",

            "name":
                "UNKNOWN",

            "similarity":
                0.0,

            "reason":
                "EMPTY_GALLERY"
        }


    scores = (
        gallery_embeddings
        @
        embedding
    )


    grouped = defaultdict(
        list
    )


    for index, score in enumerate(
        scores
    ):

        key = (
            gallery[
                "roles"
            ][
                index
            ],

            gallery[
                "names"
            ][
                index
            ]
        )


        grouped[
            key
        ].append(
            float(
                score
            )
        )


    identity_scores = []


    for key, identity_values in grouped.items():

        identity_values = sorted(
            identity_values,
            reverse=True
        )


        strongest = identity_values[
            :TOP_REFERENCE_MATCHES
        ]


        average_score = float(
            np.mean(
                strongest
            )
        )


        identity_scores.append(
            (
                average_score,
                key[
                    0
                ],
                key[
                    1
                ]
            )
        )


    identity_scores.sort(
        reverse=True,
        key=lambda value:
            value[
                0
            ]
    )


    best = identity_scores[
        0
    ]


    best_score = float(
        best[
            0
        ]
    )


    second_score = (
        float(
            identity_scores[
                1
            ][
                0
            ]
        )
        if len(
            identity_scores
        ) > 1
        else
        -1.0
    )


    margin = (
        best_score
        -
        second_score
    )


    if best_score < MATCH_THRESHOLD:

        return {
            "role":
                "UNKNOWN",

            "name":
                "UNKNOWN",

            "similarity":
                round(
                    best_score,
                    4
                ),

            "second_similarity":
                round(
                    second_score,
                    4
                ),

            "margin":
                round(
                    margin,
                    4
                ),

            "reason":
                "SIMILARITY_TOO_LOW"
        }


    if (
        len(
            identity_scores
        ) > 1
        and
        margin < IDENTITY_MARGIN
    ):

        return {
            "role":
                "UNKNOWN",

            "name":
                "UNKNOWN",

            "similarity":
                round(
                    best_score,
                    4
                ),

            "second_similarity":
                round(
                    second_score,
                    4
                ),

            "margin":
                round(
                    margin,
                    4
                ),

            "reason":
                "IDENTITY_AMBIGUOUS"
        }


    return {
        "role":
            best[
                1
            ],

        "name":
            best[
                2
            ],

        "similarity":
            round(
                best_score,
                4
            ),

        "second_similarity":
            round(
                second_score,
                4
            ),

        "margin":
            round(
                margin,
                4
            ),

        "confidence":
            round(
                max(
                    0.0,
                    min(
                        100.0,
                        best_score
                        *
                        100.0
                    )
                ),
                2
            ),

        "reason":
            "MATCH"
    }


# ============================================================
# RECOGNIZE FRAME
# ============================================================

def recognize_frame(
    frame,
    detector=None,
    recognizer=None
):

    if detector is None:

        height, width = frame.shape[
            :2
        ]

        detector = create_detector(
            (
                width,
                height
            )
        )


    if recognizer is None:

        recognizer = create_recognizer()


    processed, faces = detect_faces(
        frame,
        detector
    )


    results = []


    for face in faces:

        embedding, quality = extract_embedding(
            processed,
            face,
            recognizer
        )


        x = int(
            face[
                0
            ]
        )

        y = int(
            face[
                1
            ]
        )

        width = int(
            face[
                2
            ]
        )

        height = int(
            face[
                3
            ]
        )


        if embedding is None:

            identity = {
                "role":
                    "UNKNOWN",

                "name":
                    "UNKNOWN",

                "similarity":
                    0.0,

                "reason":
                    quality.get(
                        "reason"
                    )
            }

        else:

            identity = match_embedding(
                embedding
            )


        identity[
            "quality"
        ] = quality


        identity[
            "box"
        ] = {
            "x":
                x,

            "y":
                y,

            "w":
                width,

            "h":
                height
        }


        # 5 facial landmarks:
        #
        # right eye / left eye / nose /
        # right mouth / left mouth

        identity[
            "landmarks"
        ] = [

            {
                "x":
                    float(
                        face[
                            4
                        ]
                    ),

                "y":
                    float(
                        face[
                            5
                        ]
                    )
            },

            {
                "x":
                    float(
                        face[
                            6
                        ]
                    ),

                "y":
                    float(
                        face[
                            7
                        ]
                    )
            },

            {
                "x":
                    float(
                        face[
                            8
                        ]
                    ),

                "y":
                    float(
                        face[
                            9
                        ]
                    )
            },

            {
                "x":
                    float(
                        face[
                            10
                        ]
                    ),

                "y":
                    float(
                        face[
                            11
                        ]
                    )
            },

            {
                "x":
                    float(
                        face[
                            12
                        ]
                    ),

                "y":
                    float(
                        face[
                            13
                        ]
                    )
            }
        ]


        results.append(
            identity
        )


    return results


# ============================================================
# ENROLLMENT INSTRUCTIONS
# ============================================================

def enrollment_instruction(
    collected,
    total
):

    fraction = (
        collected
        /
        max(
            total,
            1
        )
    )


    if fraction < 0.20:

        return (
            "LOOK STRAIGHT AT THE CAMERA"
        )


    if fraction < 0.40:

        return (
            "TURN SLIGHTLY TO YOUR LEFT"
        )


    if fraction < 0.60:

        return (
            "TURN SLIGHTLY TO YOUR RIGHT"
        )


    if fraction < 0.78:

        return (
            "MOVE SLIGHTLY CLOSER / FARTHER"
        )


    return (
        "CHANGE APPEARANCE / PUT ON YOUR HAT IF YOU USE ONE"
    )


# ============================================================
# OWNER ENROLLMENT
# ============================================================

def enroll_owner(
    samples=48,
    replace=True
):

    ensure_storage()


    detector = create_detector(
        (
            640,
            480
        )
    )


    recognizer = create_recognizer()


    camera = cv2.VideoCapture(
        CAMERA_INDEX
    )


    if not camera.isOpened():

        raise RuntimeError(
            "CAMERA_NOT_AVAILABLE"
        )


    embeddings = []

    collected = 0

    last_capture = 0.0


    print(
        "[FACE V4] OWNER enrollment started."
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


            instruction = enrollment_instruction(
                collected,
                samples
            )


            if len(
                faces
            ) == 1:

                face = faces[
                    0
                ]


                embedding, quality = extract_embedding(
                    processed,
                    face,
                    recognizer
                )


                if (
                    embedding is not None
                    and
                    time.monotonic()
                    -
                    last_capture
                    >=
                    0.22
                ):

                    embeddings.append(
                        embedding
                    )


                    collected += 1

                    last_capture = (
                        time.monotonic()
                    )


                    x = int(
                        face[
                            0
                        ]
                    )

                    y = int(
                        face[
                            1
                        ]
                    )

                    width = int(
                        face[
                            2
                        ]
                    )

                    height = int(
                        face[
                            3
                        ]
                    )


                    crop = frame[
                        max(
                            0,
                            y
                        ):
                        min(
                            frame.shape[
                                0
                            ],
                            y + height
                        ),

                        max(
                            0,
                            x
                        ):
                        min(
                            frame.shape[
                                1
                            ],
                            x + width
                        )
                    ]


                    if crop.size:

                        filename = os.path.join(
                            OWNER_IMAGE_DIR,
                            (
                                f"owner_v4_"
                                f"{int(time.time() * 1000)}_"
                                f"{collected:03d}.jpg"
                            )
                        )


                        cv2.imwrite(
                            filename,
                            crop
                        )


                    print(
                        "[FACE V4] OWNER sample "
                        f"{collected}/{samples}"
                    )


            display = frame.copy()


            cv2.putText(
                display,
                "SENTINEL PHOENIX - OWNER V4 ENROLLMENT",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )


            cv2.putText(
                display,
                instruction,
                (20, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )


            cv2.putText(
                display,
                f"{collected}/{samples}",
                (20, 105),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )


            cv2.imshow(
                "Sentinel Phoenix - Face Engine V4 Enrollment",
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


    if not embeddings:

        return {
            "status":
                "FAILED",

            "reason":
                "NO_VALID_EMBEDDINGS"
        }


    add_to_gallery(
        embeddings,
        name="OWNER",
        role="OWNER",
        replace_identity=replace
    )


    registry = load_registry()

    registry[
        "identities"
    ][
        "OWNER"
    ] = {
        "name":
            "OWNER",

        "role":
            "OWNER",

        "samples":
            len(
                embeddings
            )
    }


    save_registry(
        registry
    )


    return {
        "status":
            "OWNER_ENROLLED_V4",

        "samples":
            len(
                embeddings
            ),

        "gallery":
            GALLERY_FILE,

        "detector":
            "YuNet",

        "embedding_model":
            "SFace"
    }


# ============================================================
# MULTI-FRAME OWNER VERIFICATION
# ============================================================

def verify_owner(
    camera_index=CAMERA_INDEX,
    timeout=VERIFY_TIMEOUT_SECONDS,
    show_window=True
):

    detector = create_detector(
        (
            640,
            480
        )
    )


    recognizer = create_recognizer()


    camera = cv2.VideoCapture(
        camera_index
    )


    if not camera.isOpened():

        return {
            "verified":
                False,

            "reason":
                "CAMERA_NOT_AVAILABLE"
        }


    history = deque(
        maxlen=VERIFY_WINDOW
    )


    started = time.monotonic()

    observations = 0

    best_similarity = 0.0


    try:

        while (
            time.monotonic()
            -
            started
            <
            timeout
        ):

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


            # Security:
            # OWNER verification requires exactly one
            # visible face.

            if len(
                results
            ) == 1:

                identity = results[
                    0
                ]


                observations += 1


                role = identity.get(
                    "role",
                    "UNKNOWN"
                )


                similarity = float(
                    identity.get(
                        "similarity",
                        0.0
                    )
                )


                best_similarity = max(
                    best_similarity,
                    similarity
                )


                history.append(
                    role
                )


                owner_votes = sum(
                    1
                    for value in history
                    if value == "OWNER"
                )


                if (
                    len(
                        history
                    )
                    >=
                    OWNER_REQUIRED_VOTES
                    and
                    owner_votes
                    >=
                    OWNER_REQUIRED_VOTES
                ):

                    return {
                        "verified":
                            True,

                        "reason":
                            "OWNER_FACE_VERIFIED_V4",

                        "owner_votes":
                            owner_votes,

                        "observations":
                            observations,

                        "similarity":
                            round(
                                best_similarity,
                                4
                            ),

                        "engine":
                            "SFACE_EMBEDDING_V4"
                    }


            else:

                owner_votes = sum(
                    1
                    for value in history
                    if value == "OWNER"
                )


            if show_window:

                display = frame.copy()


                cv2.putText(
                    display,
                    "SENTINEL OWNER VERIFICATION V4",
                    (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA
                )


                cv2.putText(
                    display,
                    (
                        f"OWNER VOTES: "
                        f"{owner_votes}/"
                        f"{OWNER_REQUIRED_VOTES}"
                    ),
                    (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA
                )


                if len(
                    results
                ) == 1:

                    identity = results[
                        0
                    ]


                    box = identity[
                        "box"
                    ]


                    role = identity.get(
                        "role",
                        "UNKNOWN"
                    )


                    if role == "OWNER":

                        color = (
                            80,
                            255,
                            80
                        )

                    else:

                        color = (
                            80,
                            80,
                            255
                        )


                    cv2.rectangle(
                        display,
                        (
                            box[
                                "x"
                            ],
                            box[
                                "y"
                            ]
                        ),
                        (
                            box[
                                "x"
                            ]
                            +
                            box[
                                "w"
                            ],

                            box[
                                "y"
                            ]
                            +
                            box[
                                "h"
                            ]
                        ),
                        color,
                        2
                    )


                    cv2.putText(
                        display,
                        (
                            f"{role}  "
                            f"{identity.get('similarity', 0.0):.3f}"
                        ),
                        (
                            box[
                                "x"
                            ],
                            max(
                                20,
                                box[
                                    "y"
                                ]
                                -
                                10
                            )
                        ),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        color,
                        2,
                        cv2.LINE_AA
                    )


                cv2.imshow(
                    "Sentinel Phoenix - OWNER Verification V4",
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


    return {
        "verified":
            False,

        "reason":
            "OWNER_FACE_NOT_VERIFIED_V4",

        "owner_votes":
            sum(
                1
                for value in history
                if value == "OWNER"
            ),

        "observations":
            observations,

        "similarity":
            round(
                best_similarity,
                4
            ),

        "engine":
            "SFACE_EMBEDDING_V4"
    }


# ============================================================
# LIVE CAMERA TEST
# ============================================================

def run_camera_test():

    detector = create_detector(
        (
            640,
            480
        )
    )


    recognizer = create_recognizer()


    camera = cv2.VideoCapture(
        CAMERA_INDEX
    )


    if not camera.isOpened():

        raise RuntimeError(
            "CAMERA_NOT_AVAILABLE"
        )


    print(
        "[FACE V4] Live recognition started."
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


            for identity in results:

                box = identity[
                    "box"
                ]


                role = identity.get(
                    "role",
                    "UNKNOWN"
                )


                if role == "OWNER":

                    color = (
                        70,
                        255,
                        70
                    )

                elif role == "GUEST":

                    color = (
                        255,
                        220,
                        70
                    )

                else:

                    color = (
                        70,
                        70,
                        255
                    )


                cv2.rectangle(
                    frame,
                    (
                        box[
                            "x"
                        ],
                        box[
                            "y"
                        ]
                    ),
                    (
                        box[
                            "x"
                        ]
                        +
                        box[
                            "w"
                        ],

                        box[
                            "y"
                        ]
                        +
                        box[
                            "h"
                        ]
                    ),
                    color,
                    2
                )


                for landmark in identity.get(
                    "landmarks",
                    []
                ):

                    cv2.circle(
                        frame,
                        (
                            int(
                                landmark[
                                    "x"
                                ]
                            ),
                            int(
                                landmark[
                                    "y"
                                ]
                            )
                        ),
                        2,
                        color,
                        -1
                    )


                text = (
                    f"{role} | "
                    f"SIM "
                    f"{identity.get('similarity', 0.0):.3f}"
                )


                cv2.putText(
                    frame,
                    text,
                    (
                        box[
                            "x"
                        ],
                        max(
                            20,
                            box[
                                "y"
                            ]
                            -
                            10
                        )
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    color,
                    2,
                    cv2.LINE_AA
                )


            cv2.putText(
                frame,
                "FACE ENGINE V4 - YuNet + SFace",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )


            cv2.putText(
                frame,
                "5 LANDMARK ALIGNMENT | EMBEDDING IDENTITY",
                (20, 65),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.47,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )


            cv2.imshow(
                "Sentinel Phoenix - Face Engine V4",
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


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    ensure_storage()


    models = models_available()


    yunet_api = (
        hasattr(
            cv2,
            "FaceDetectorYN_create"
        )
        or
        (
            hasattr(
                cv2,
                "FaceDetectorYN"
            )
            and
            hasattr(
                cv2.FaceDetectorYN,
                "create"
            )
        )
    )


    sface_api = (
        hasattr(
            cv2,
            "FaceRecognizerSF_create"
        )
        or
        (
            hasattr(
                cv2,
                "FaceRecognizerSF"
            )
            and
            hasattr(
                cv2.FaceRecognizerSF,
                "create"
            )
        )
    )


    detector_ok = False

    recognizer_ok = False


    if models[
        "yunet"
    ] and yunet_api:

        try:

            create_detector()

            detector_ok = True

        except Exception:

            detector_ok = False


    if models[
        "sface"
    ] and sface_api:

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


    passed = all(
        [
            models[
                "yunet"
            ],
            models[
                "sface"
            ],
            yunet_api,
            sface_api,
            detector_ok,
            recognizer_ok
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
            FACE_ENGINE_VERSION,

        "opencv_version":
            cv2.__version__,

        "models":
            models,

        "apis":
            {
                "yunet":
                    yunet_api,

                "sface":
                    sface_api
            },

        "engines":
            {
                "detector":
                    "YuNet",

                "recognizer":
                    "SFace",

                "identity":
                    "FACIAL_EMBEDDING"
            },

        "gallery_samples":
            gallery_samples,

        "security":
            {
                "uses_shoulders":
                    False,

                "uses_clothing":
                    False,

                "requires_facial_landmarks":
                    True,

                "multi_frame_verification":
                    True,

                "identity_margin":
                    IDENTITY_MARGIN,

                "match_threshold":
                    MATCH_THRESHOLD,

                "processing_local":
                    True,

                "internet_upload":
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