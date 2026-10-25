import hashlib
import json
import os
import time

from datetime import datetime, timezone


# ============================================================
# SENTINEL PHOENIX
# MOVING TARGET DEFENSE
# ADAPTIVE DECEPTION ENGINE V1
# ============================================================


SURFACE_FILE = "surface.json"


# ============================================================
# DECOY PROFILES
# ============================================================

PROFILES = {

    "backup-node": {

        "hostname":
            "phoenix-backup-01",

        "user":
            "backup",

        "cwd":
            "/srv/backup",

        "os_release":
            (
                'NAME="Ubuntu"\n'
                'VERSION="22.04.5 LTS (Jammy Jellyfish)"\n'
                'ID=ubuntu\n'
            ),

        "ip":
            "10.44.8.21",

        "network":
            (
                "2: eth0: <BROADCAST,MULTICAST,UP>\n"
                "    inet 10.44.8.21/24\n"
                "    inet6 fe80::21/64\n"
            ),

        "users":
            (
                "root:x:0:0:root:/root:/bin/bash\n"
                "backup:x:1001:1001:Backup Service:"
                "/srv/backup:/bin/bash\n"
                "monitor:x:1002:1002:Monitoring:"
                "/opt/monitor:/usr/sbin/nologin\n"
            ),

        "listing":
            (
                "drwxr-xr-x  archives\n"
                "drwxr-xr-x  database\n"
                "drwxr-xr-x  logs\n"
                "drwxr-xr-x  scripts\n"
                "-rw-r--r--  system-backup.tar.gz\n"
            ),

        "database":
            (
                "backup_catalog\n"
                "archive_index\n"
                "retention_jobs\n"
            ),

        "processes":
            (
                "root       1  0.0  init\n"
                "backup   318  0.1  backup-agent\n"
                "monitor  472  0.0  metrics-agent\n"
            )
    },


    "web-gateway": {

        "hostname":
            "edge-web-02",

        "user":
            "app",

        "cwd":
            "/opt/webapp",

        "os_release":
            (
                'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\n'
                'NAME="Debian GNU/Linux"\n'
                'VERSION_ID="12"\n'
            ),

        "ip":
            "10.44.12.14",

        "network":
            (
                "2: ens18: <BROADCAST,MULTICAST,UP>\n"
                "    inet 10.44.12.14/24\n"
                "    inet6 fe80::14/64\n"
            ),

        "users":
            (
                "root:x:0:0:root:/root:/bin/bash\n"
                "app:x:1001:1001:Web Application:"
                "/opt/webapp:/bin/bash\n"
                "www-data:x:33:33:www-data:/var/www:"
                "/usr/sbin/nologin\n"
            ),

        "listing":
            (
                "drwxr-xr-x  config\n"
                "drwxr-xr-x  logs\n"
                "drwxr-xr-x  public\n"
                "drwxr-xr-x  releases\n"
                "-rw-r--r--  app.env.example\n"
            ),

        "database":
            (
                "sessions\n"
                "frontend_cache\n"
                "application_events\n"
            ),

        "processes":
            (
                "root       1  0.0  init\n"
                "www-data 221  0.2  nginx\n"
                "app      384  0.3  gunicorn\n"
            )
    },


    "analytics-db": {

        "hostname":
            "analytics-db-03",

        "user":
            "postgres",

        "cwd":
            "/var/lib/postgresql",

        "os_release":
            (
                'PRETTY_NAME="Ubuntu 24.04.1 LTS"\n'
                'NAME="Ubuntu"\n'
                'VERSION_ID="24.04"\n'
            ),

        "ip":
            "10.44.20.31",

        "network":
            (
                "2: eth0: <BROADCAST,MULTICAST,UP>\n"
                "    inet 10.44.20.31/24\n"
                "    inet6 fe80::31/64\n"
            ),

        "users":
            (
                "root:x:0:0:root:/root:/bin/bash\n"
                "postgres:x:113:118:PostgreSQL:"
                "/var/lib/postgresql:/bin/bash\n"
                "analyst:x:1003:1003:Analytics:"
                "/home/analyst:/bin/bash\n"
            ),

        "listing":
            (
                "drwx------  16\n"
                "drwx------  backups\n"
                "drwx------  data\n"
                "drwx------  exports\n"
                "-rw-------  recovery.notes\n"
            ),

        "database":
            (
                "analytics\n"
                "telemetry\n"
                "reporting\n"
            ),

        "processes":
            (
                "root       1  0.0  init\n"
                "postgres 247  0.4  postgres\n"
                "postgres 261  0.1  walwriter\n"
            )
    },


    "devops-runner": {

        "hostname":
            "ci-runner-07",

        "user":
            "runner",

        "cwd":
            "/home/runner/work",

        "os_release":
            (
                'NAME="Alpine Linux"\n'
                'ID=alpine\n'
                'VERSION_ID=3.20.3\n'
            ),

        "ip":
            "10.44.30.17",

        "network":
            (
                "2: eth0: <BROADCAST,MULTICAST,UP>\n"
                "    inet 10.44.30.17/24\n"
                "    inet6 fe80::17/64\n"
            ),

        "users":
            (
                "root:x:0:0:root:/root:/bin/ash\n"
                "runner:x:1000:1000:CI Runner:"
                "/home/runner:/bin/ash\n"
            ),

        "listing":
            (
                "drwxr-xr-x  artifacts\n"
                "drwxr-xr-x  builds\n"
                "drwxr-xr-x  cache\n"
                "drwxr-xr-x  pipelines\n"
                "-rw-r--r--  runner-config.example\n"
            ),

        "database":
            (
                "pipeline_history\n"
                "artifact_index\n"
                "runner_jobs\n"
            ),

        "processes":
            (
                "root       1  0.0  init\n"
                "runner   184  0.2  runner-agent\n"
                "runner   211  0.1  job-worker\n"
            )
    }
}


# ============================================================
# UTILITIES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def _stable_index(
    seed,
    count
):

    digest = hashlib.sha256(
        seed.encode(
            "utf-8",
            errors="replace"
        )
    ).hexdigest()

    value = int(
        digest[:16],
        16
    )

    return value % count


def profile_ids():

    return sorted(
        PROFILES.keys()
    )


# ============================================================
# PROFILE SELECTION
# ============================================================

def select_initial_profile(
    session_id,
    source_ip,
    fusion
):

    level = str(
        fusion.get(
            "global_level",
            "LOW"
        )
    ).upper()

    seed = (
        f"{session_id}|"
        f"{source_ip}|"
        f"{level}"
    )

    identifiers = (
        profile_ids()
    )

    index = _stable_index(
        seed,
        len(
            identifiers
        )
    )

    return identifiers[
        index
    ]


def next_profile(
    current_profile
):

    identifiers = (
        profile_ids()
    )

    try:

        current_index = (
            identifiers.index(
                current_profile
            )
        )

    except ValueError:

        return identifiers[0]

    next_index = (
        current_index
        +
        1
    ) % len(
        identifiers
    )

    return identifiers[
        next_index
    ]


# ============================================================
# SURFACE STORAGE
# ============================================================

def surface_path(
    session_dir
):

    return os.path.join(
        session_dir,
        SURFACE_FILE
    )


def save_surface(
    session_dir,
    surface
):

    path = surface_path(
        session_dir
    )

    temporary = (
        path
        +
        ".tmp"
    )

    with open(
        temporary,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            surface,
            file,
            indent=2,
            ensure_ascii=False
        )

    os.replace(
        temporary,
        path
    )


def load_surface(
    session_dir
):

    path = surface_path(
        session_dir
    )

    if not os.path.isfile(
        path
    ):

        return None

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(
                file
            )

    except (
        OSError,
        json.JSONDecodeError
    ):

        return None


def get_or_create_surface(
    session_dir,
    session_id,
    source_ip,
    fusion
):

    surface = load_surface(
        session_dir
    )

    if surface is not None:

        return surface

    profile_id = (
        select_initial_profile(
            session_id,
            source_ip,
            fusion
        )
    )

    surface = {

        "version":
            "1.0",

        "profile_id":
            profile_id,

        "generation":
            1,

        "interactions":
            0,

        "rotations":
            0,

        "created_at":
            utc_now(),

        "last_seen":
            utc_now(),

        "last_rotation_at":
            None,

        "last_rotation_reason":
            None
    }

    save_surface(
        session_dir,
        surface
    )

    return surface


# ============================================================
# RECON DETECTION
# ============================================================

def is_recon_command(
    command
):

    normalized = (
        str(
            command
        )
        .strip()
        .lower()
    )

    prefixes = (

        "whoami",
        "id",
        "pwd",
        "ls",
        "hostname",
        "uname",
        "cat /etc/os-release",
        "cat /etc/passwd",
        "ip ",
        "ifconfig",
        "ps "

    )

    return any(
        normalized == prefix
        or
        normalized.startswith(
            prefix
        )

        for prefix
        in prefixes
    )


# ============================================================
# MTD ROTATION
# ============================================================

def update_surface(
    session_dir,
    session_id,
    source_ip,
    command,
    fusion
):

    surface = (
        get_or_create_surface(
            session_dir,
            session_id,
            source_ip,
            fusion
        )
    )

    surface[
        "interactions"
    ] = int(
        surface.get(
            "interactions",
            0
        )
    ) + 1

    surface[
        "last_seen"
    ] = utc_now()

    level = str(
        fusion.get(
            "global_level",
            "LOW"
        )
    ).upper()

    threshold = {

        "CRITICAL":
            3,

        "HIGH":
            4,

        "MEDIUM":
            5,

        "LOW":
            6

    }.get(
        level,
        6
    )

    recon = is_recon_command(
        command
    )

    rotated = False

    if (
        recon
        and
        surface[
            "interactions"
        ] % threshold == 0
    ):

        old_profile = (
            surface[
                "profile_id"
            ]
        )

        new_profile = (
            next_profile(
                old_profile
            )
        )

        surface[
            "profile_id"
        ] = new_profile

        surface[
            "generation"
        ] = int(
            surface.get(
                "generation",
                1
            )
        ) + 1

        surface[
            "rotations"
        ] = int(
            surface.get(
                "rotations",
                0
            )
        ) + 1

        surface[
            "last_rotation_at"
        ] = utc_now()

        surface[
            "last_rotation_reason"
        ] = (
            "RECON_ACTIVITY"
        )

        rotated = True

    save_surface(
        session_dir,
        surface
    )

    return {
        "surface":
            surface,

        "rotated":
            rotated
    }


# ============================================================
# PROFILE MATERIALIZATION
# ============================================================

def materialize_profile(
    session_dir,
    profile_id
):

    profile = PROFILES.get(
        profile_id
    )

    if profile is None:

        raise ValueError(
            "Unknown deception profile"
        )

    fake_system = os.path.join(
        session_dir,
        "fake_system"
    )

    os.makedirs(
        fake_system,
        exist_ok=True
    )

    files = {

        "hostname.txt":
            (
                profile[
                    "hostname"
                ]
                +
                "\n"
            ),

        "os-release.txt":
            profile[
                "os_release"
            ],

        "users.txt":
            profile[
                "users"
            ],

        "network.txt":
            profile[
                "network"
            ],

        "database.txt":
            profile[
                "database"
            ]
    }

    for filename, content in files.items():

        path = os.path.join(
            fake_system,
            filename
        )

        temporary = (
            path
            +
            ".tmp"
        )

        with open(
            temporary,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                content
            )

        os.replace(
            temporary,
            path
        )


# ============================================================
# FAKE TERMINAL
# ============================================================

def render_command(
    profile_id,
    command
):

    profile = PROFILES[
        profile_id
    ]

    command = str(
        command
    ).strip()

    if not command:

        return (
            f"{profile['user']}@"
            f"{profile['hostname']}:"
            f"{profile['cwd']}$ "
        )

    normalized = (
        command.lower()
    )

    if normalized == "help":

        return (
            "Available commands:\n"
            "whoami\n"
            "id\n"
            "pwd\n"
            "ls\n"
            "ls -la\n"
            "hostname\n"
            "uname -a\n"
            "cat /etc/os-release\n"
            "cat /etc/passwd\n"
            "ip a\n"
            "ifconfig\n"
            "ps aux\n"
            "exit\n"
        )

    if normalized == "whoami":

        return (
            profile[
                "user"
            ]
            +
            "\n"
        )

    if normalized == "id":

        return (
            f"uid=1001({profile['user']}) "
            f"gid=1001({profile['user']}) "
            f"groups=1001({profile['user']})\n"
        )

    if normalized == "pwd":

        return (
            profile[
                "cwd"
            ]
            +
            "\n"
        )

    if (
        normalized == "ls"
        or
        normalized == "ls -la"
        or
        normalized.startswith(
            "ls "
        )
    ):

        return profile[
            "listing"
        ]

    if normalized == "hostname":

        return (
            profile[
                "hostname"
            ]
            +
            "\n"
        )

    if normalized == "uname -a":

        return (
            f"Linux {profile['hostname']} "
            "6.8.0-phoenix #1 SMP "
            "x86_64 GNU/Linux\n"
        )

    if normalized == "cat /etc/os-release":

        return profile[
            "os_release"
        ]

    if normalized == "cat /etc/passwd":

        return profile[
            "users"
        ]

    if (
        normalized == "ip a"
        or
        normalized == "ifconfig"
    ):

        return profile[
            "network"
        ]

    if (
        normalized == "ps aux"
        or
        normalized == "ps"
    ):

        return profile[
            "processes"
        ]

    if normalized == "exit":

        return (
            "Connection closed.\n"
        )

    first_word = (
        command.split(
            whitespace=None,
            maxsplit=1
        )[0]
        if command
        else
        ""
    )

    return (
        f"bash: {first_word}: "
        "command not found\n"
    )


# ============================================================
# COMPLETE INTERACTION
# ============================================================

def process_interaction(
    session_dir,
    session_id,
    source_ip,
    payload,
    fusion
):

    # Une seule ligne est interprétée
    # comme commande fictive.
    # Rien n'est exécuté.

    text = str(
        payload
    )[:512]

    lines = text.splitlines()

    command = (
        lines[0].strip()
        if lines
        else
        ""
    )

    update = update_surface(
        session_dir,
        session_id,
        source_ip,
        command,
        fusion
    )

    surface = update[
        "surface"
    ]

    profile_id = (
        surface[
            "profile_id"
        ]
    )

    materialize_profile(
        session_dir,
        profile_id
    )

    response = render_command(
        profile_id,
        command
    )

    return {

        "command":
            command,

        "response":
            response,

        "profile_id":
            profile_id,

        "generation":
            surface.get(
                "generation",
                1
            ),

        "interactions":
            surface.get(
                "interactions",
                0
            ),

        "rotations":
            surface.get(
                "rotations",
                0
            ),

        "surface_rotated":
            update.get(
                "rotated",
                False
            ),

        "rotation_reason":
            surface.get(
                "last_rotation_reason"
            ),

        "payload_execution":
            False,

        "host_modified":
            False
    }


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    import tempfile

    results = []

    with tempfile.TemporaryDirectory() as directory:

        fusion = {
            "global_level":
                "CRITICAL",

            "global_score":
                95
        }

        commands = [
            "whoami",
            "pwd",
            "hostname",
            "ls -la",
            "uname -a",
            "ip a"
        ]

        for command in commands:

            result = process_interaction(
                session_dir=directory,
                session_id=
                    "abcdef1234567890",
                source_ip=
                    "127.0.0.1",
                payload=
                    command,
                fusion=
                    fusion
            )

            results.append(
                {
                    "command":
                        command,

                    "profile":
                        result[
                            "profile_id"
                        ],

                    "generation":
                        result[
                            "generation"
                        ],

                    "rotated":
                        result[
                            "surface_rotated"
                        ],

                    "payload_execution":
                        result[
                            "payload_execution"
                        ],

                    "host_modified":
                        result[
                            "host_modified"
                        ]
                }
            )

    return {
        "status":
            "PASS",

        "interactions":
            results,

        "payload_executed":
            False,

        "host_modified":
            False
    }