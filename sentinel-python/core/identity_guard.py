import time
import threading
from copy import deepcopy

import cv2

from core import face_engine


# ============================================================
# SENTINEL PHOENIX
# IDENTITY GUARD V2.3
# ADAPTIVE MULTI-FACE AUTHENTICATION
#
# FIX V2.3:
#
# Face Engine V4 may return:
#
#     dict
#
# OR
#
#     list[dict]
#
# V2.2 expected only dict, therefore valid OWNER detections
# inside a list were ignored.
#
# V2.3:
#   - supports single or multiple face results
#   - selects strongest recognized identity per frame
#   - ignores tiny/poor UNKNOWN detections
#   - temporal multi-frame voting
#   - automatic retry
#   - successful identity cache
#
# FACE ENGINE V4 itself remains unchanged.
# ============================================================


IDENTITY_GUARD_VERSION = "2.3"

AUTHENTICATION_MODE = "ADAPTIVE_MULTI_FACE"

CAMERA_INDEX = 0


# ============================================================
# RECOGNITION THRESHOLDS
# ============================================================

ADAPTIVE_MATCH_THRESHOLD = 0.385

ADAPTIVE_IDENTITY_MARGIN = 0.040

ADAPTIVE_TOP_REFERENCES = 5


# ============================================================
# SIMILARITY LEVELS
# ============================================================

STRONG_SIMILARITY = 0.50

GOOD_SIMILARITY = 0.43

MINIMUM_ACCEPTED_SIMILARITY = 0.385


# ============================================================
# TEMPORAL VOTING
# ============================================================

SCAN_TIMEOUT = 8.0

SECOND_SCAN_TIMEOUT = 5.0

MAX_SCAN_FRAMES = 150

MIN_OBSERVATIONS = 5

OWNER_REQUIRED_VOTES = 5

GUEST_REQUIRED_VOTES = 5

STRONG_REQUIRED_VOTES = 3


# ============================================================
# FACE SIZE FILTER
#
# Prevent tiny false face detections from influencing
# authentication.
# ============================================================

MIN_FACE_WIDTH = 55

MIN_FACE_HEIGHT = 55


# ============================================================
# CACHE
# ============================================================

RECOGNIZED_CACHE_SECONDS = 45.0

UNKNOWN_CACHE_SECONDS = 2.0


# ============================================================
# ROUTE SECURITY
# ============================================================

ROUTE_POLICY = {

    "BRAIN": {
        "OWNER",
        "GUEST",
    },

    "VISUAL_INCIDENT_REPLAY": {
        "OWNER",
    },

    "EVIDENCE_CONTROL": {
        "OWNER",
    },

    "GUEST_ENROLLMENT": {
        "OWNER",
    },

    "REMEDIATION": {
        "OWNER",
    },

    "SYSTEM_CONTROL": {
        "OWNER",
    },
}


FRESH_IDENTITY_ROUTES = {
    "VISUAL_INCIDENT_REPLAY",
    "EVIDENCE_CONTROL",
    "GUEST_ENROLLMENT",
    "REMEDIATION",
    "SYSTEM_CONTROL",
}


# ============================================================
# GLOBAL CAMERA LOCK
# ============================================================

_SCAN_LOCK = threading.Lock()


# ============================================================
# BASIC HELPERS
# ============================================================

def _normalize_route(
    route
):

    return str(
        route or "BRAIN"
    ).strip().upper()


def _safe_float(
    value,
    default=0.0
):

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return float(
            default
        )


def _normalize_role(
    role
):

    value = str(
        role or "UNKNOWN"
    ).strip().upper()


    if value not in {
        "OWNER",
        "GUEST",
        "UNKNOWN",
    }:

        return "UNKNOWN"


    return value


# ============================================================
# FACE ENGINE RUNTIME CONFIG
# ============================================================

def _configure_face_engine():

    try:

        if hasattr(
            face_engine,
            "MATCH_THRESHOLD"
        ):

            face_engine.MATCH_THRESHOLD = (
                ADAPTIVE_MATCH_THRESHOLD
            )


        if hasattr(
            face_engine,
            "IDENTITY_MARGIN"
        ):

            face_engine.IDENTITY_MARGIN = (
                ADAPTIVE_IDENTITY_MARGIN
            )


        if hasattr(
            face_engine,
            "TOP_REFERENCE_MATCHES"
        ):

            face_engine.TOP_REFERENCE_MATCHES = (
                ADAPTIVE_TOP_REFERENCES
            )


    except Exception:

        pass


_configure_face_engine()


# ============================================================
# UNKNOWN RESULT
# ============================================================

def _unknown_result(
    reason="UNKNOWN"
):

    return {

        "status":
            "UNKNOWN",

        "verified":
            False,

        "role":
            "UNKNOWN",

        "name":
            "UNKNOWN",

        "similarity":
            0.0,

        "quality":
            0.0,

        "reason":
            reason,

        "authentication_mode":
            AUTHENTICATION_MODE,

        "face_engine_version":
            getattr(
                face_engine,
                "FACE_ENGINE_VERSION",
                "UNKNOWN"
            ),

        "cached":
            False,
    }


# ============================================================
# CAMERA
# ============================================================

def _open_camera():

    camera = cv2.VideoCapture(
        CAMERA_INDEX
    )


    if not camera.isOpened():

        return None


    camera.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        640
    )

    camera.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        480
    )


    try:

        camera.set(
            cv2.CAP_PROP_BUFFERSIZE,
            1
        )

    except Exception:

        pass


    return camera


# ============================================================
# FACE RESULT NORMALIZATION
# ============================================================

def _result_list(
    result
):

    """
    Convert Face Engine output to a list of dictionaries.

    Supported:
        dict
        list[dict]
        tuple[dict]
        nested list / tuple
    """

    if result is None:

        return []


    if isinstance(
        result,
        dict
    ):

        return [
            result
        ]


    if isinstance(
        result,
        (
            list,
            tuple,
        )
    ):

        output = []


        for item in result:

            if isinstance(
                item,
                dict
            ):

                output.append(
                    item
                )


            elif isinstance(
                item,
                (
                    list,
                    tuple,
                )
            ):

                output.extend(
                    _result_list(
                        item
                    )
                )


        return output


    return []


# ============================================================
# FACE BOX
# ============================================================

def _face_box(
    result
):

    box = result.get(
        "box"
    )


    if not isinstance(
        box,
        dict
    ):

        return {
            "x": 0,
            "y": 0,
            "w": 0,
            "h": 0,
        }


    return {

        "x":
            int(
                box.get(
                    "x",
                    0
                )
                or
                0
            ),

        "y":
            int(
                box.get(
                    "y",
                    0
                )
                or
                0
            ),

        "w":
            int(
                box.get(
                    "w",
                    0
                )
                or
                0
            ),

        "h":
            int(
                box.get(
                    "h",
                    0
                )
                or
                0
            ),
    }


def _face_is_large_enough(
    result
):

    box = _face_box(
        result
    )


    # Some older Face Engine results may not expose box size.
    # Do not reject those automatically.

    if (
        box["w"] <= 0
        or
        box["h"] <= 0
    ):

        return True


    return (
        box["w"]
        >=
        MIN_FACE_WIDTH

        and

        box["h"]
        >=
        MIN_FACE_HEIGHT
    )


# ============================================================
# QUALITY
# ============================================================

def _quality_score(
    result
):

    quality = result.get(
        "quality"
    )


    if isinstance(
        quality,
        (
            int,
            float,
        )
    ):

        return float(
            quality
        )


    if isinstance(
        quality,
        dict
    ):

        for key in (
            "score",
            "quality_score",
            "face_score",
        ):

            if key in quality:

                return _safe_float(
                    quality.get(
                        key
                    ),
                    0.0
                )


        if quality.get(
            "usable"
        ) is True:

            return 1.0


    return 0.0


# ============================================================
# NORMALIZE ONE FACE
# ============================================================

def _normalize_face(
    result
):

    if not isinstance(
        result,
        dict
    ):

        return None


    normalized = deepcopy(
        result
    )


    normalized[
        "role"
    ] = _normalize_role(
        normalized.get(
            "role"
        )
    )


    normalized[
        "name"
    ] = str(
        normalized.get(
            "name",
            normalized[
                "role"
            ]
        )
        or
        normalized[
            "role"
        ]
    )


    normalized[
        "similarity"
    ] = _safe_float(
        normalized.get(
            "similarity"
        ),
        0.0
    )


    normalized[
        "quality_score"
    ] = _quality_score(
        normalized
    )


    normalized[
        "face_box"
    ] = _face_box(
        normalized
    )


    return normalized


# ============================================================
# SELECT BEST FACE FROM FRAME
# ============================================================

def _best_identity_from_result(
    result
):

    raw_faces = _result_list(
        result
    )


    faces = []


    for raw_face in raw_faces:

        face = _normalize_face(
            raw_face
        )


        if face is None:

            continue


        if not _face_is_large_enough(
            face
        ):

            continue


        faces.append(
            face
        )


    if not faces:

        return None


    # --------------------------------------------------------
    # First preference:
    # recognized OWNER/GUEST identities.
    # --------------------------------------------------------

    recognized = [

        face
        for face in faces

        if (
            face.get(
                "role"
            )
            in {
                "OWNER",
                "GUEST",
            }

            and

            face.get(
                "similarity",
                0.0
            )
            >=
            MINIMUM_ACCEPTED_SIMILARITY
        )
    ]


    if recognized:

        recognized.sort(

            key=lambda face: (
                face.get(
                    "similarity",
                    0.0
                ),
                face.get(
                    "quality_score",
                    0.0
                ),
                (
                    face.get(
                        "face_box",
                        {}
                    ).get(
                        "w",
                        0
                    )
                    *
                    face.get(
                        "face_box",
                        {}
                    ).get(
                        "h",
                        0
                    )
                )
            ),

            reverse=True
        )


        best = recognized[
            0
        ]


        best[
            "faces_detected"
        ] = len(
            faces
        )


        return best


    # --------------------------------------------------------
    # No recognized identity.
    # Keep strongest UNKNOWN only for diagnostics.
    # --------------------------------------------------------

    faces.sort(

        key=lambda face: (
            face.get(
                "similarity",
                0.0
            ),
            face.get(
                "quality_score",
                0.0
            ),
            (
                face.get(
                    "face_box",
                    {}
                ).get(
                    "w",
                    0
                )
                *
                face.get(
                    "face_box",
                    {}
                ).get(
                    "h",
                    0
                )
            )
        ),

        reverse=True
    )


    best = faces[
        0
    ]


    best[
        "faces_detected"
    ] = len(
        faces
    )


    return best


# ============================================================
# RECOGNIZE FRAME
# ============================================================

def _recognize_frame(
    frame,
    detector,
    recognizer
):

    try:

        raw_result = (
            face_engine.recognize_frame(
                frame,
                detector=detector,
                recognizer=recognizer
            )
        )


    except TypeError:

        try:

            raw_result = (
                face_engine.recognize_frame(
                    frame,
                    detector,
                    recognizer
                )
            )

        except Exception:

            return None


    except Exception:

        return None


    return _best_identity_from_result(
        raw_result
    )


# ============================================================
# BUILD VERIFIED RESULT
# ============================================================

def _build_verified_result(
    role,
    best_result,
    votes,
    observations,
    similarity_sum,
    reason
):

    winner = deepcopy(
        best_result
        or
        {}
    )


    role_votes = int(
        votes.get(
            role,
            0
        )
    )


    average_similarity = (

        similarity_sum.get(
            role,
            0.0
        )
        /
        role_votes

        if role_votes > 0

        else 0.0
    )


    winner.update(
        {

            "status":
                "VERIFIED",

            "verified":
                True,

            "role":
                role,

            "name":
                winner.get(
                    "name",
                    role
                ),

            "reason":
                reason,

            "votes":
                role_votes,

            "all_votes":
                deepcopy(
                    votes
                ),

            "observations":
                observations,

            "average_similarity":
                average_similarity,

            "authentication_mode":
                AUTHENTICATION_MODE,

            "face_engine_version":
                getattr(
                    face_engine,
                    "FACE_ENGINE_VERSION",
                    "UNKNOWN"
                ),

            "cached":
                False,
        }
    )


    return winner


# ============================================================
# ONE SCAN PASS
# ============================================================

def _scan_once(
    timeout
):

    detector = None

    recognizer = None

    camera = None


    try:

        detector = (
            face_engine.create_detector(
                input_size=(
                    640,
                    480
                )
            )
        )


        recognizer = (
            face_engine.create_recognizer()
        )


        camera = _open_camera()


        if camera is None:

            return _unknown_result(
                "CAMERA_UNAVAILABLE"
            )


        start_time = (
            time.monotonic()
        )


        total_frames = 0

        observations = 0


        votes = {

            "OWNER":
                0,

            "GUEST":
                0,
        }


        similarity_sum = {

            "OWNER":
                0.0,

            "GUEST":
                0.0,
        }


        best_similarity = {

            "OWNER":
                0.0,

            "GUEST":
                0.0,
        }


        best_result = {

            "OWNER":
                None,

            "GUEST":
                None,
        }


        unknown_frames = 0

        last_faces_detected = 0


        while (
            time.monotonic()
            -
            start_time
            <
            timeout
        ):

            if (
                total_frames
                >=
                MAX_SCAN_FRAMES
            ):

                break


            ok, frame = (
                camera.read()
            )


            if (
                not ok
                or
                frame is None
            ):

                time.sleep(
                    0.02
                )

                continue


            total_frames += 1


            # Process one frame out of two.

            if (
                total_frames
                %
                2
                ==
                0
            ):

                continue


            result = _recognize_frame(
                frame,
                detector,
                recognizer
            )


            if result is None:

                continue


            last_faces_detected = int(
                result.get(
                    "faces_detected",
                    0
                )
                or
                0
            )


            role = _normalize_role(
                result.get(
                    "role"
                )
            )


            similarity = _safe_float(
                result.get(
                    "similarity"
                ),
                0.0
            )


            if role not in {
                "OWNER",
                "GUEST",
            }:

                unknown_frames += 1

                continue


            if (
                similarity
                <
                MINIMUM_ACCEPTED_SIMILARITY
            ):

                continue


            observations += 1


            votes[
                role
            ] += 1


            similarity_sum[
                role
            ] += similarity


            if (
                similarity
                >
                best_similarity[
                    role
                ]
            ):

                best_similarity[
                    role
                ] = similarity

                best_result[
                    role
                ] = deepcopy(
                    result
                )


            # =================================================
            # STRONG MATCH
            # =================================================

            if (
                similarity
                >=
                STRONG_SIMILARITY

                and

                votes[
                    role
                ]
                >=
                STRONG_REQUIRED_VOTES
            ):

                return _build_verified_result(

                    role=role,

                    best_result=best_result[
                        role
                    ],

                    votes=votes,

                    observations=observations,

                    similarity_sum=similarity_sum,

                    reason="STRONG_MULTI_FRAME_MATCH",
                )


            # =================================================
            # TEMPORAL MATCH
            # =================================================

            required_votes = (

                OWNER_REQUIRED_VOTES

                if role == "OWNER"

                else GUEST_REQUIRED_VOTES
            )


            if (
                observations
                >=
                MIN_OBSERVATIONS

                and

                votes[
                    role
                ]
                >=
                required_votes
            ):

                average = (

                    similarity_sum[
                        role
                    ]
                    /
                    votes[
                        role
                    ]
                )


                if (
                    average
                    >=
                    GOOD_SIMILARITY
                ):

                    return _build_verified_result(

                        role=role,

                        best_result=best_result[
                            role
                        ],

                        votes=votes,

                        observations=observations,

                        similarity_sum=similarity_sum,

                        reason="TEMPORAL_VOTE_MATCH",
                    )


        # =====================================================
        # END-OF-SCAN RECOVERY
        # =====================================================

        owner_votes = votes[
            "OWNER"
        ]

        guest_votes = votes[
            "GUEST"
        ]


        winner_role = (

            "OWNER"

            if owner_votes
            >=
            guest_votes

            else "GUEST"
        )


        winner_votes = votes[
            winner_role
        ]


        if winner_votes > 0:

            average = (

                similarity_sum[
                    winner_role
                ]
                /
                winner_votes
            )


            if (
                winner_votes
                >=
                4

                and

                average
                >=
                0.415
            ):

                return _build_verified_result(

                    role=winner_role,

                    best_result=best_result[
                        winner_role
                    ],

                    votes=votes,

                    observations=observations,

                    similarity_sum=similarity_sum,

                    reason="CONSISTENT_RECOVERY_MATCH",
                )


        result = _unknown_result(
            "INSUFFICIENT_CONSISTENT_MATCH"
        )


        result[
            "votes"
        ] = deepcopy(
            votes
        )


        result[
            "observations"
        ] = observations


        result[
            "unknown_frames"
        ] = unknown_frames


        result[
            "processed_frames"
        ] = total_frames


        result[
            "faces_detected_last_frame"
        ] = last_faces_detected


        result[
            "best_similarity"
        ] = deepcopy(
            best_similarity
        )


        return result


    except Exception as error:

        result = _unknown_result(
            "FACE_SCAN_ERROR"
        )


        result[
            "error"
        ] = repr(
            error
        )


        return result


    finally:

        if camera is not None:

            try:

                camera.release()

            except Exception:

                pass


# ============================================================
# LIVE IDENTIFICATION
# ============================================================

def identify_live_user(
    show_window=False,
    show_hud=False,
    retry=True,
    **kwargs
):

    with _SCAN_LOCK:

        first = _scan_once(
            SCAN_TIMEOUT
        )


        if first.get(
            "verified",
            False
        ):

            return first


        if retry:

            time.sleep(
                0.30
            )


            second = _scan_once(
                SECOND_SCAN_TIMEOUT
            )


            if second.get(
                "verified",
                False
            ):

                second[
                    "reason"
                ] = (
                    "AUTO_RETRY_"
                    +
                    str(
                        second.get(
                            "reason",
                            "MATCH"
                        )
                    )
                )


                return second


            first_observations = int(
                first.get(
                    "observations",
                    0
                )
                or
                0
            )


            second_observations = int(
                second.get(
                    "observations",
                    0
                )
                or
                0
            )


            if (
                second_observations
                >
                first_observations
            ):

                return second


        return first


# ============================================================
# IDENTITY GUARD
# ============================================================

class IdentityGuard:

    def __init__(
        self
    ):

        self._lock = (
            threading.RLock()
        )


        self._cache_result = None

        self._cache_time = 0.0


    # ========================================================
    # CACHE
    # ========================================================

    def _cache_valid(
        self
    ):

        if self._cache_result is None:

            return False


        age = (
            time.monotonic()
            -
            self._cache_time
        )


        role = _normalize_role(
            self._cache_result.get(
                "role"
            )
        )


        ttl = (

            RECOGNIZED_CACHE_SECONDS

            if role in {
                "OWNER",
                "GUEST",
            }

            else UNKNOWN_CACHE_SECONDS
        )


        return (
            age
            <=
            ttl
        )


    def _save_cache(
        self,
        result
    ):

        with self._lock:

            self._cache_result = deepcopy(
                result
            )


            self._cache_time = (
                time.monotonic()
            )


    # ========================================================
    # IDENTIFY
    # ========================================================

    def identify(
        self,
        force_fresh=False,
        show_window=False,
        show_hud=False,
        route=None,
        **kwargs
    ):

        normalized_route = (
            _normalize_route(
                route
            )
        )


        if (
            normalized_route
            in
            FRESH_IDENTITY_ROUTES
        ):

            force_fresh = True


        with self._lock:

            if (
                not force_fresh
                and
                self._cache_valid()
            ):

                result = deepcopy(
                    self._cache_result
                )


                result[
                    "cached"
                ] = True


                result[
                    "reason"
                ] = (
                    "IDENTITY_CACHE"
                )


                return result


        result = identify_live_user(
            show_window=False,
            show_hud=show_hud,
            retry=True,
        )


        result[
            "route"
        ] = normalized_route


        self._save_cache(
            result
        )


        return result


    # ========================================================
    # AUTHORIZE
    # ========================================================

    def authorize(
        self,
        route,
        force_fresh=None,
        show_window=False,
        show_hud=False,
        **kwargs
    ):

        normalized_route = (
            _normalize_route(
                route
            )
        )


        allowed_roles = (
            ROUTE_POLICY.get(
                normalized_route,
                {
                    "OWNER",
                }
            )
        )


        if force_fresh is None:

            force_fresh = (
                normalized_route
                in
                FRESH_IDENTITY_ROUTES
            )


        identity = self.identify(
            force_fresh=force_fresh,
            show_window=False,
            show_hud=show_hud,
            route=normalized_route,
        )


        role = _normalize_role(
            identity.get(
                "role"
            )
        )


        granted = (
            role
            in
            allowed_roles
        )


        return {

            "status":
                (
                    "GRANTED"
                    if granted
                    else
                    "DENIED"
                ),

            "authorized":
                granted,

            "granted":
                granted,

            "access":
                (
                    "GRANTED"
                    if granted
                    else
                    "DENIED"
                ),

            "route":
                normalized_route,

            "role":
                role,

            "name":
                identity.get(
                    "name",
                    role
                ),

            "similarity":
                identity.get(
                    "similarity"
                ),

            "average_similarity":
                identity.get(
                    "average_similarity"
                ),

            "votes":
                identity.get(
                    "votes"
                ),

            "reason":
                (
                    "ROLE_AUTHORIZED"
                    if granted
                    else
                    "ROLE_NOT_AUTHORIZED"
                ),

            "allowed_roles":
                sorted(
                    allowed_roles
                ),

            "authentication_mode":
                AUTHENTICATION_MODE,

            "identity":
                identity,
        }


# ============================================================
# SINGLETON
# ============================================================

_guard = None

_guard_lock = threading.Lock()


def get_identity_guard():

    global _guard


    with _guard_lock:

        if _guard is None:

            _guard = IdentityGuard()


        return _guard


# ============================================================
# COMPATIBILITY API
# ============================================================

def identify_user(
    force_fresh=False,
    show_window=False,
    show_hud=False,
    route=None,
    **kwargs
):

    return get_identity_guard().identify(
        force_fresh=force_fresh,
        show_window=show_window,
        show_hud=show_hud,
        route=route,
        **kwargs
    )


def authorize_route(
    route,
    force_fresh=None,
    show_window=False,
    show_hud=False,
    **kwargs
):

    return get_identity_guard().authorize(
        route=route,
        force_fresh=force_fresh,
        show_window=show_window,
        show_hud=show_hud,
        **kwargs
    )


def authorize_command(
    route,
    force_fresh=None,
    show_window=False,
    show_hud=False,
    **kwargs
):

    return authorize_route(
        route=route,
        force_fresh=force_fresh,
        show_window=show_window,
        show_hud=show_hud,
        **kwargs
    )


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    try:

        models_ok = bool(
            face_engine.models_available()
        )

    except Exception:

        models_ok = False


    required_routes = {
        "BRAIN",
        "VISUAL_INCIDENT_REPLAY",
        "EVIDENCE_CONTROL",
        "GUEST_ENROLLMENT",
    }


    policy_ok = (
        required_routes.issubset(
            set(
                ROUTE_POLICY
            )
        )
    )


    return {

        "status":
            (
                "PASS"
                if (
                    models_ok
                    and
                    policy_ok
                )
                else
                "FAIL"
            ),

        "version":
            IDENTITY_GUARD_VERSION,

        "authentication_mode":
            AUTHENTICATION_MODE,

        "face_engine_version":
            getattr(
                face_engine,
                "FACE_ENGINE_VERSION",
                "UNKNOWN"
            ),

        "models_available":
            models_ok,

        "multi_face_support":
            True,

        "adaptive_threshold":
            ADAPTIVE_MATCH_THRESHOLD,

        "owner_required_votes":
            OWNER_REQUIRED_VOTES,

        "automatic_retry":
            True,

        "headless_camera":
            True,

        "cache_seconds":
            RECOGNIZED_CACHE_SECONDS,

        "policy_ok":
            policy_ok,

        "security": {

            "single_frame_authentication":
                False,

            "multi_frame_voting":
                True,

            "multi_face_selection":
                True,

            "shell_execution":
                False,

            "payload_execution":
                False,
        },
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    import pprint

    pprint.pp(
        self_test()
    )