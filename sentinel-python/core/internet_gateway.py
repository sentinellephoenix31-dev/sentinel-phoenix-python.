import ipaddress
import json
import os
import re
import socket

from urllib.error import (
    HTTPError,
    URLError
)

from urllib.parse import (
    urlencode,
    urlparse
)

from urllib.request import (
    Request,
    urlopen
)


# ============================================================
# SENTINEL PHOENIX
# INTERNET KNOWLEDGE GATEWAY V1
#
# INFORMATION ONLY.
# NO SHELL.
# NO PATCHING.
# NO PAYLOAD EXECUTION.
# ============================================================


INTERNET_GATEWAY_VERSION = "1.0"


NVD_HOST = "services.nvd.nist.gov"

NVD_CVE_ENDPOINT = (
    "https://services.nvd.nist.gov"
    "/rest/json/cves/2.0"
)


ALLOWED_HOSTS = {
    NVD_HOST
}


HTTP_TIMEOUT = 10

MAX_RESPONSE_BYTES = (
    2 * 1024 * 1024
)

MAX_RESULTS = 5


# ============================================================
# UTILITIES
# ============================================================

def safe_text(
    value,
    maximum=1000
):

    if value is None:

        return ""

    return str(
        value
    )[:maximum]


# ============================================================
# CVE
# ============================================================

def extract_cve_id(
    text
):

    match = re.search(
        r"\bCVE-\d{4}-\d{4,}\b",
        str(text),
        re.IGNORECASE
    )

    if not match:

        return None

    return match.group(
        0
    ).upper()


def valid_cve_id(
    value
):

    return bool(
        re.fullmatch(
            r"CVE-\d{4}-\d{4,}",
            str(
                value
            ).upper()
        )
    )


# ============================================================
# EXTERNAL INTENT
# ============================================================

def classify_external_question(
    question
):

    text = str(
        question
    ).lower()

    cve_id = extract_cve_id(
        question
    )

    if cve_id:

        return {
            "external":
                True,

            "type":
                "CVE_LOOKUP",

            "cve_id":
                cve_id
        }

    explicit_markers = (
        "search nvd",
        "look up nvd",
        "search vulnerability",
        "search vulnerabilities",
        "find vulnerability",
        "find vulnerabilities",
        "vulnerability database",
        "cherche nvd",
        "recherche nvd",
        "cherche les vulnerabilites",
        "recherche les vulnerabilites"
    )

    if any(
        marker in text
        for marker in explicit_markers
    ):

        return {
            "external":
                True,

            "type":
                "VULNERABILITY_SEARCH",

            "cve_id":
                None
        }

    return {
        "external":
            False,

        "type":
            None,

        "cve_id":
            None
    }


# ============================================================
# URL SECURITY
# ============================================================

def _host_is_allowed(
    hostname
):

    return (
        str(
            hostname
        ).lower()
        in
        ALLOWED_HOSTS
    )


def _resolve_public_addresses(
    hostname
):

    try:

        records = socket.getaddrinfo(
            hostname,
            443,
            type=socket.SOCK_STREAM
        )

    except socket.gaierror as error:

        raise RuntimeError(
            f"DNS_RESOLUTION_FAILED: {error}"
        )

    addresses = set()

    for record in records:

        address = record[4][0]

        addresses.add(
            address
        )

    if not addresses:

        raise RuntimeError(
            "NO_DNS_ADDRESS"
        )

    for address in addresses:

        try:

            parsed = ipaddress.ip_address(
                address
            )

        except ValueError:

            raise RuntimeError(
                "INVALID_DNS_ADDRESS"
            )

        # Prevent accidental access to:
        # localhost
        # LAN
        # link-local
        # multicast
        # reserved targets

        if not parsed.is_global:

            raise RuntimeError(
                "NON_PUBLIC_TARGET_REJECTED"
            )

    return sorted(
        addresses
    )


def validate_url(
    url
):

    parsed = urlparse(
        url
    )

    if parsed.scheme != "https":

        raise RuntimeError(
            "HTTPS_REQUIRED"
        )

    hostname = (
        parsed.hostname
        or
        ""
    ).lower()

    if not _host_is_allowed(
        hostname
    ):

        raise RuntimeError(
            "HOST_NOT_ALLOWED"
        )

    _resolve_public_addresses(
        hostname
    )

    return True


# ============================================================
# HTTP JSON
# ============================================================

def fetch_json(
    base_url,
    parameters=None
):

    if parameters:

        url = (
            base_url
            +
            "?"
            +
            urlencode(
                parameters
            )
        )

    else:

        url = base_url

    validate_url(
        url
    )

    headers = {
        "Accept":
            "application/json",

        "User-Agent":
            (
                "Sentinel-Phoenix/"
                f"{INTERNET_GATEWAY_VERSION}"
            )
    }

    # Optional NVD API key.
    #
    # Never hardcode the key inside source code.
    #
    # Example:
    # export NVD_API_KEY="..."
    #

    api_key = os.environ.get(
        "NVD_API_KEY"
    )

    if api_key:

        headers[
            "apiKey"
        ] = api_key

    request = Request(
        url,
        headers=headers,
        method="GET"
    )

    try:

        with urlopen(
            request,
            timeout=HTTP_TIMEOUT
        ) as response:

            final_url = response.geturl()

            # Check redirect destination as well.

            validate_url(
                final_url
            )

            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                )
            ).lower()

            if (
                "json"
                not in content_type
            ):

                raise RuntimeError(
                    "NON_JSON_RESPONSE"
                )

            raw = response.read(
                MAX_RESPONSE_BYTES + 1
            )

            if (
                len(raw)
                >
                MAX_RESPONSE_BYTES
            ):

                raise RuntimeError(
                    "RESPONSE_TOO_LARGE"
                )

    except HTTPError as error:

        if error.code == 429:

            raise RuntimeError(
                "REMOTE_RATE_LIMITED"
            )

        raise RuntimeError(
            f"REMOTE_HTTP_ERROR_{error.code}"
        )

    except URLError as error:

        raise RuntimeError(
            f"REMOTE_CONNECTION_ERROR: {error.reason}"
        )

    try:

        result = json.loads(
            raw.decode(
                "utf-8"
            )
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError
    ):

        raise RuntimeError(
            "INVALID_REMOTE_JSON"
        )

    if not isinstance(
        result,
        dict
    ):

        raise RuntimeError(
            "INVALID_REMOTE_STRUCTURE"
        )

    return result


# ============================================================
# NVD PARSING
# ============================================================

def _english_description(
    cve
):

    descriptions = cve.get(
        "descriptions",
        []
    )

    for item in descriptions:

        if (
            item.get(
                "lang"
            )
            ==
            "en"
        ):

            return safe_text(
                item.get(
                    "value"
                ),
                1500
            )

    if descriptions:

        return safe_text(
            descriptions[0].get(
                "value"
            ),
            1500
        )

    return ""


def _cvss_information(
    cve
):

    metrics = cve.get(
        "metrics",
        {}
    )

    preferred = (
        "cvssMetricV40",
        "cvssMetricV31",
        "cvssMetricV30",
        "cvssMetricV2"
    )

    for metric_name in preferred:

        items = metrics.get(
            metric_name
        )

        if not items:

            continue

        first = items[0]

        cvss = first.get(
            "cvssData",
            {}
        )

        score = cvss.get(
            "baseScore"
        )

        severity = (
            cvss.get(
                "baseSeverity"
            )
            or
            first.get(
                "baseSeverity"
            )
        )

        return {
            "metric":
                metric_name,

            "score":
                score,

            "severity":
                severity
        }

    return {
        "metric":
            None,

        "score":
            None,

        "severity":
            None
    }


def normalize_nvd_cve(
    cve
):

    cvss = _cvss_information(
        cve
    )

    references = []

    for item in cve.get(
        "references",
        []
    )[:5]:

        url = item.get(
            "url"
        )

        if url:

            references.append(
                safe_text(
                    url,
                    500
                )
            )

    return {
        "id":
            safe_text(
                cve.get(
                    "id"
                ),
                100
            ),

        "status":
            safe_text(
                cve.get(
                    "vulnStatus"
                ),
                100
            ),

        "published":
            safe_text(
                cve.get(
                    "published"
                ),
                100
            ),

        "last_modified":
            safe_text(
                cve.get(
                    "lastModified"
                ),
                100
            ),

        "description":
            _english_description(
                cve
            ),

        "cvss_score":
            cvss[
                "score"
            ],

        "severity":
            cvss[
                "severity"
            ],

        "cvss_metric":
            cvss[
                "metric"
            ],

        # NVD may expose CISA KEV metadata
        # in the CVE record when available.

        "known_exploited":
            bool(
                cve.get(
                    "cisaExploitAdd"
                )
            ),

        "cisa_exploit_added":
            cve.get(
                "cisaExploitAdd"
            ),

        "cisa_action_due":
            cve.get(
                "cisaActionDue"
            ),

        "cisa_required_action":
            safe_text(
                cve.get(
                    "cisaRequiredAction"
                ),
                1000
            ),

        "references":
            references,

        "source":
            "NVD/NIST",

        "external_data_trust":
            "UNTRUSTED_INFORMATION_ONLY"
    }


# ============================================================
# NVD LOOKUP
# ============================================================

def lookup_cve(
    cve_id
):

    cve_id = str(
        cve_id
    ).upper()

    if not valid_cve_id(
        cve_id
    ):

        return {
            "ok":
                False,

            "reason":
                "INVALID_CVE_ID"
        }

    data = fetch_json(
        NVD_CVE_ENDPOINT,
        {
            "cveId":
                cve_id
        }
    )

    vulnerabilities = data.get(
        "vulnerabilities",
        []
    )

    if not vulnerabilities:

        return {
            "ok":
                False,

            "reason":
                "CVE_NOT_FOUND",

            "cve_id":
                cve_id
        }

    cve = (
        vulnerabilities[0].get(
            "cve",
            {}
        )
    )

    return {
        "ok":
            True,

        "result":
            normalize_nvd_cve(
                cve
            )
    }


# ============================================================
# KEYWORD SEARCH
# ============================================================

def clean_keyword_query(
    question
):

    text = str(
        question
    )

    removal = (
        "search nvd",
        "look up nvd",
        "search vulnerabilities",
        "search vulnerability",
        "find vulnerabilities",
        "find vulnerability",
        "cherche nvd",
        "recherche nvd"
    )

    lowered = text.lower()

    for phrase in removal:

        position = lowered.find(
            phrase
        )

        if position >= 0:

            text = (
                text[
                    :position
                ]
                +
                " "
                +
                text[
                    position
                    +
                    len(
                        phrase
                    ):
                ]
            )

            lowered = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip(
        " ?.,:"
    )

    return text[:200]


def search_nvd(
    keywords,
    limit=MAX_RESULTS
):

    keywords = str(
        keywords
    ).strip()

    if not keywords:

        return {
            "ok":
                False,

            "reason":
                "EMPTY_SEARCH"
        }

    limit = max(
        1,
        min(
            int(limit),
            MAX_RESULTS
        )
    )

    data = fetch_json(
        NVD_CVE_ENDPOINT,
        {
            "keywordSearch":
                keywords,

            "resultsPerPage":
                limit
        }
    )

    results = []

    for item in data.get(
        "vulnerabilities",
        []
    )[:limit]:

        cve = item.get(
            "cve",
            {}
        )

        results.append(
            normalize_nvd_cve(
                cve
            )
        )

    return {
        "ok":
            True,

        "query":
            keywords,

        "total_results":
            data.get(
                "totalResults",
                len(results)
            ),

        "results":
            results
    }


# ============================================================
# NATURAL RESPONSE
# ============================================================

def _describe_specific_cve(
    record,
    language="EN"
):

    cve_id = record.get(
        "id"
    )

    severity = (
        record.get(
            "severity"
        )
        or
        "UNKNOWN"
    )

    score = record.get(
        "cvss_score"
    )

    description = record.get(
        "description"
    )

    exploited = record.get(
        "known_exploited",
        False
    )

    modified = record.get(
        "last_modified"
    )

    if language == "FR":

        answer = (
            f"{cve_id} — sévérité {severity}"
        )

        if score is not None:

            answer += (
                f", score CVSS {score}"
            )

        answer += (
            f". {description}"
        )

        if exploited:

            answer += (
                " La fiche NVD contient également "
                "des informations CISA indiquant "
                "une exploitation connue."
            )

        if modified:

            answer += (
                f" Dernière modification NVD : "
                f"{modified}."
            )

        return answer

    answer = (
        f"{cve_id} — severity {severity}"
    )

    if score is not None:

        answer += (
            f", CVSS score {score}"
        )

    answer += (
        f". {description}"
    )

    if exploited:

        answer += (
            " The NVD record also contains CISA "
            "known-exploitation information."
        )

    if modified:

        answer += (
            f" NVD last modified: {modified}."
        )

    return answer


def answer_internet_question(
    question,
    language="EN"
):

    route = classify_external_question(
        question
    )

    if not route.get(
        "external"
    ):

        return {
            "ok":
                False,

            "reason":
                "NOT_AN_EXTERNAL_QUERY",

            "answer":
                None
        }

    # ========================================================
    # CVE
    # ========================================================

    if (
        route[
            "type"
        ]
        ==
        "CVE_LOOKUP"
    ):

        result = lookup_cve(
            route[
                "cve_id"
            ]
        )

        if not result.get(
            "ok"
        ):

            return {
                **result,

                "answer":
                    (
                        "Je n'ai pas trouvé cette CVE dans NVD."
                        if language == "FR"
                        else
                        "I could not find that CVE in NVD."
                    )
            }

        record = result[
            "result"
        ]

        return {
            "ok":
                True,

            "type":
                "CVE_LOOKUP",

            "record":
                record,

            "answer":
                _describe_specific_cve(
                    record,
                    language
                ),

            "safety":
                {
                    "information_only":
                        True,

                    "remote_commands_allowed":
                        False,

                    "shell_execution":
                        False,

                    "payload_execution":
                        False,

                    "patching":
                        False,

                    "host_modification":
                        False
                }
        }

    # ========================================================
    # KEYWORD SEARCH
    # ========================================================

    keywords = clean_keyword_query(
        question
    )

    result = search_nvd(
        keywords
    )

    if not result.get(
        "ok"
    ):

        return {
            **result,

            "answer":
                (
                    "Je n'ai pas pu effectuer cette recherche."
                    if language == "FR"
                    else
                    "I could not perform that search."
                )
        }

    records = result.get(
        "results",
        []
    )

    if not records:

        return {
            "ok":
                True,

            "answer":
                (
                    "Je n'ai trouvé aucune vulnérabilité "
                    "correspondante dans NVD."
                    if language == "FR"
                    else
                    "I found no matching vulnerabilities in NVD."
                ),

            "results":
                []
        }

    lines = []

    for record in records:

        severity = (
            record.get(
                "severity"
            )
            or
            "UNKNOWN"
        )

        score = record.get(
            "cvss_score"
        )

        score_text = (
            f" / CVSS {score}"
            if score is not None
            else
            ""
        )

        description = safe_text(
            record.get(
                "description"
            ),
            220
        )

        lines.append(
            f"{record.get('id')} — "
            f"{severity}{score_text}: "
            f"{description}"
        )

    if language == "FR":

        answer = (
            f"J'ai trouvé les résultats NVD suivants "
            f"pour « {keywords} » :\n"
            +
            "\n".join(
                lines
            )
        )

    else:

        answer = (
            f"I found the following NVD results "
            f"for '{keywords}':\n"
            +
            "\n".join(
                lines
            )
        )

    return {
        "ok":
            True,

        "type":
            "VULNERABILITY_SEARCH",

        "results":
            records,

        "answer":
            answer,

        "safety":
            {
                "information_only":
                    True,

                "remote_commands_allowed":
                    False,

                "shell_execution":
                    False,

                "payload_execution":
                    False,

                "patching":
                    False,

                "host_modification":
                    False
            }
    }


# ============================================================
# OFFLINE SELF TEST
# ============================================================

def self_test():

    tests = {
        "cve_extraction":
            (
                extract_cve_id(
                    "Tell me about cve-2026-9999"
                )
                ==
                "CVE-2026-9999"
            ),

        "valid_cve":
            valid_cve_id(
                "CVE-2026-9999"
            ),

        "invalid_cve":
            not valid_cve_id(
                "CVE-test"
            ),

        "external_route":
            (
                classify_external_question(
                    "What is CVE-2026-9999?"
                )[
                    "type"
                ]
                ==
                "CVE_LOOKUP"
            ),

        "local_stays_local":
            (
                classify_external_question(
                    "What happened last night?"
                )[
                    "external"
                ]
                is False
            )
    }

    passed = all(
        tests.values()
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
            INTERNET_GATEWAY_VERSION,

        "tests":
            tests,

        "network_used":
            False,

        "safety":
            {
                "information_only":
                    True,

                "shell_execution":
                    False,

                "payload_execution":
                    False,

                "patching":
                    False,

                "host_modification":
                    False
            }
    }


# ============================================================
# LIVE TEST
# ============================================================

def live_test():

    try:

        result = lookup_cve(
            "CVE-2021-44228"
        )

        return {
            "status":
                (
                    "PASS"
                    if result.get(
                        "ok"
                    )
                    else
                    "FAIL"
                ),

            "internet":
                True,

            "source":
                "NVD/NIST",

            "result":
                result
        }

    except Exception as error:

        return {
            "status":
                "FAIL",

            "internet":
                False,

            "reason":
                str(
                    error
                )
        }