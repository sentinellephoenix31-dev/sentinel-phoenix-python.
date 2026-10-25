import ipaddress
import json
import os
import time
import urllib.error
import urllib.request


# ============================================================
# SENTINEL PHOENIX
# GEO INTELLIGENCE V1
#
# Public IP
#     ↓
# HTTPS lookup
#     ↓
# Country / Region / City
# Latitude / Longitude
# ASN / Organization
#
# External geolocation data is INFORMATION ONLY.
# It never executes commands or modifies the host.
# ============================================================


GEO_VERSION = "1.0"

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

CACHE_FILE = os.path.join(
    DATA_DIR,
    "geo_cache.json"
)


CACHE_TTL_SECONDS = 24 * 60 * 60

REQUEST_TIMEOUT = 6

MAX_RESPONSE_BYTES = 65536


DOCUMENTATION_NETWORKS = [
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("2001:db8::/32")
]


# ============================================================
# STORAGE
# ============================================================

def ensure_storage():

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )


# ============================================================
# CACHE
# ============================================================

def load_cache():

    ensure_storage()

    if not os.path.isfile(
        CACHE_FILE
    ):

        return {}

    try:

        with open(
            CACHE_FILE,
            "r",
            encoding="utf-8"
        ) as handle:

            data = json.load(
                handle
            )

        if isinstance(
            data,
            dict
        ):

            return data

    except (
        OSError,
        json.JSONDecodeError
    ):

        pass

    return {}


def save_cache(
    cache
):

    ensure_storage()

    temporary = (
        CACHE_FILE
        +
        ".tmp"
    )

    with open(
        temporary,
        "w",
        encoding="utf-8"
    ) as handle:

        json.dump(
            cache,
            handle,
            indent=2,
            ensure_ascii=False
        )

    os.replace(
        temporary,
        CACHE_FILE
    )


# ============================================================
# IP CLASSIFICATION
# ============================================================

def is_documentation_ip(
    ip_obj
):

    return any(
        ip_obj in network
        for network in DOCUMENTATION_NETWORKS
    )


def classify_ip(
    value
):

    try:

        ip_obj = ipaddress.ip_address(
            str(
                value
            ).strip()
        )

    except ValueError:

        return {
            "valid": False,
            "public": False,
            "classification": "INVALID"
        }


    if is_documentation_ip(
        ip_obj
    ):

        classification = "DOCUMENTATION"

    elif ip_obj.is_loopback:

        classification = "LOOPBACK"

    elif ip_obj.is_link_local:

        classification = "LINK_LOCAL"

    elif ip_obj.is_multicast:

        classification = "MULTICAST"

    elif ip_obj.is_unspecified:

        classification = "UNSPECIFIED"

    elif ip_obj.is_private:

        classification = "PRIVATE"

    elif ip_obj.is_reserved:

        classification = "RESERVED"

    elif not ip_obj.is_global:

        classification = "NON_PUBLIC"

    else:

        classification = "PUBLIC"


    return {
        "valid": True,
        "public": bool(
            ip_obj.is_global
        ),
        "classification": classification,
        "version": ip_obj.version,
        "normalized": str(
            ip_obj
        )
    }


# ============================================================
# LOCAL / NON-PUBLIC RESPONSE
# ============================================================

def local_result(
    ip_value,
    classification
):

    return {
        "status": "LOCAL_OR_NON_PUBLIC",

        "ip": ip_value,

        "classification":
            classification,

        "country":
            "LOCAL / NON-PUBLIC",

        "country_code":
            None,

        "region":
            "LOCAL NETWORK",

        "city":
            None,

        "latitude":
            None,

        "longitude":
            None,

        "timezone":
            None,

        "asn":
            None,

        "provider":
            None,

        "geolocation_available":
            False,

        "accuracy":
            "NOT_APPLICABLE",

        "source":
            "LOCAL_IP_CLASSIFICATION",

        "external_data_trust":
            "UNTRUSTED_INFORMATION_ONLY"
    }


# ============================================================
# CACHE LOOKUP
# ============================================================

def cached_result(
    ip_value
):

    cache = load_cache()

    entry = cache.get(
        ip_value
    )

    if not isinstance(
        entry,
        dict
    ):

        return None


    timestamp = float(
        entry.get(
            "_cached_at",
            0
        )
    )


    if (
        time.time()
        -
        timestamp
        >
        CACHE_TTL_SECONDS
    ):

        return None


    result = dict(
        entry
    )

    result.pop(
        "_cached_at",
        None
    )

    result[
        "cache"
    ] = "HIT"

    return result


def cache_result(
    ip_value,
    result
):

    cache = load_cache()

    stored = dict(
        result
    )

    stored[
        "_cached_at"
    ] = time.time()

    cache[
        ip_value
    ] = stored

    save_cache(
        cache
    )


# ============================================================
# HTTPS GEOLOOKUP
# ============================================================

def request_geolocation(
    ip_value
):

    url = (
        "https://ipapi.co/"
        +
        ip_value
        +
        "/json/"
    )


    request = urllib.request.Request(

        url,

        headers={
            "User-Agent":
                "Sentinel-Phoenix-Geo/1.0",

            "Accept":
                "application/json"
        },

        method="GET"
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT
        ) as response:

            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                )
                .lower()
            )


            if (
                "json"
                not in
                content_type
            ):

                return {
                    "status":
                        "FAILED",

                    "reason":
                        "NON_JSON_RESPONSE"
                }


            payload = response.read(
                MAX_RESPONSE_BYTES + 1
            )


            if (
                len(
                    payload
                )
                >
                MAX_RESPONSE_BYTES
            ):

                return {
                    "status":
                        "FAILED",

                    "reason":
                        "RESPONSE_TOO_LARGE"
                }


    except urllib.error.HTTPError as error:

        return {
            "status":
                "FAILED",

            "reason":
                "HTTP_ERROR",

            "http_status":
                error.code
        }


    except urllib.error.URLError as error:

        return {
            "status":
                "FAILED",

            "reason":
                "NETWORK_ERROR",

            "detail":
                str(
                    error.reason
                )
        }


    except TimeoutError:

        return {
            "status":
                "FAILED",

            "reason":
                "TIMEOUT"
        }


    try:

        data = json.loads(
            payload.decode(
                "utf-8"
            )
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError
    ):

        return {
            "status":
                "FAILED",

            "reason":
                "INVALID_JSON"
        }


    if not isinstance(
        data,
        dict
    ):

        return {
            "status":
                "FAILED",

            "reason":
                "INVALID_RESPONSE_STRUCTURE"
        }


    if data.get(
        "error"
    ):

        return {
            "status":
                "FAILED",

            "reason":
                data.get(
                    "reason",
                    "REMOTE_API_ERROR"
                )
        }


    return {
        "status":
            "OK",

        "ip":
            ip_value,

        "country":
            data.get(
                "country_name"
            )
            or
            "UNKNOWN",

        "country_code":
            data.get(
                "country_code"
            )
            or
            data.get(
                "country"
            ),

        "region":
            data.get(
                "region"
            )
            or
            "UNKNOWN",

        "city":
            data.get(
                "city"
            )
            or
            "UNKNOWN",

        "latitude":
            data.get(
                "latitude"
            ),

        "longitude":
            data.get(
                "longitude"
            ),

        "timezone":
            data.get(
                "timezone"
            ),

        "asn":
            data.get(
                "asn"
            ),

        "provider":
            data.get(
                "org"
            ),

        "geolocation_available":
            True,

        "accuracy":
            "APPROXIMATE_IP_GEOLOCATION",

        "source":
            "IPAPI.CO",

        "external_data_trust":
            "UNTRUSTED_INFORMATION_ONLY",

        "can_identify_person":
            False
    }


# ============================================================
# PUBLIC API
# ============================================================

def lookup_ip(
    ip_value,
    use_cache=True
):

    classification = classify_ip(
        ip_value
    )


    if not classification.get(
        "valid"
    ):

        return {
            "status":
                "INVALID_IP",

            "ip":
                str(
                    ip_value
                ),

            "geolocation_available":
                False
        }


    normalized = classification[
        "normalized"
    ]


    if not classification.get(
        "public"
    ):

        return local_result(
            normalized,
            classification[
                "classification"
            ]
        )


    if use_cache:

        cached = cached_result(
            normalized
        )

        if cached is not None:

            return cached


    result = request_geolocation(
        normalized
    )


    if (
        result.get(
            "status"
        )
        ==
        "OK"
    ):

        result[
            "classification"
        ] = "PUBLIC"

        result[
            "cache"
        ] = "MISS"

        cache_result(
            normalized,
            result
        )


    return result


# ============================================================
# GLOBE PAYLOAD
# ============================================================

def to_globe_payload(
    geo_result
):

    if (
        geo_result.get(
            "status"
        )
        !=
        "OK"
    ):

        return {
            "available":
                False,

            "ip":
                geo_result.get(
                    "ip"
                ),

            "classification":
                geo_result.get(
                    "classification"
                ),

            "reason":
                geo_result.get(
                    "reason",
                    "NO_PUBLIC_GEOLOCATION"
                )
        }


    latitude = geo_result.get(
        "latitude"
    )

    longitude = geo_result.get(
        "longitude"
    )


    try:

        latitude = float(
            latitude
        )

        longitude = float(
            longitude
        )

    except (
        TypeError,
        ValueError
    ):

        return {
            "available":
                False,

            "ip":
                geo_result.get(
                    "ip"
                ),

            "reason":
                "INVALID_COORDINATES"
        }


    return {
        "available":
            True,

        "ip":
            geo_result.get(
                "ip"
            ),

        "country":
            geo_result.get(
                "country"
            ),

        "country_code":
            geo_result.get(
                "country_code"
            ),

        "region":
            geo_result.get(
                "region"
            ),

        "city":
            geo_result.get(
                "city"
            ),

        "latitude":
            latitude,

        "longitude":
            longitude,

        "asn":
            geo_result.get(
                "asn"
            ),

        "provider":
            geo_result.get(
                "provider"
            ),

        "accuracy":
            "APPROXIMATE"
    }


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    local = lookup_ip(
        "127.0.0.1"
    )

    documentation = lookup_ip(
        "203.0.113.42"
    )

    invalid = lookup_ip(
        "not-an-ip"
    )


    passed = all(
        [
            local.get(
                "classification"
            )
            ==
            "LOOPBACK",

            documentation.get(
                "classification"
            )
            ==
            "DOCUMENTATION",

            invalid.get(
                "status"
            )
            ==
            "INVALID_IP"
        ]
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
            GEO_VERSION,

        "local_test":
            local.get(
                "classification"
            ),

        "documentation_test":
            documentation.get(
                "classification"
            ),

        "invalid_test":
            invalid.get(
                "status"
            ),

        "security": {
            "https_only":
                True,

            "private_ips_sent_to_api":
                False,

            "response_size_limit":
                MAX_RESPONSE_BYTES,

            "external_data_trust":
                "UNTRUSTED_INFORMATION_ONLY",

            "shell_execution":
                False,

            "host_modification":
                False,

            "person_identification":
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