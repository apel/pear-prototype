import os
from typing import Final


# ==============================================================================
# CONSUMED MESSAGES - APEL
# ==============================================================================

DEFAULT_MESSAGES_DIR: Final[str] = "/var/spool/apel/grid/incoming"

APEL_DIRQ_SCHEMA: Final[dict[str, str]] = {
    "body": "string",
    "signer": "string",
    "empaid": "string?",
}

# ==============================================================================
# TOPOLOGY DATA
# ==============================================================================

CRIC_RCSITE_API: Final[str] = "https://wlcg-cric.cern.ch/api/core/rcsite/query/?json&state=ANY"
CRIC_REQUEST_TIMEOUT_SECONDS: Final[int] = 30
IGTF_TRUST_BUNDLE_PATH: Final[str] = "/cvmfs/grid.cern.ch/etc/grid-security/certificates"

UNKNOWN: Final[str] = "UNKNOWN"

LHC_VOS: Final[dict[str, str]] = {
    "atlas": "ATLAS",
    "cms": "CMS",
    "alice": "ALICE",
    "lhcb": "LHCb",
}

WLCG_TIERS: Final[set[int]] = {0, 1, 2, 3}
NON_WLCG_TIER: Final[str] = "NON-WLCG-Tier"

NON_MOU_FEDERATION: Final[str] = "NON-MOU-Federation"
DESY_FEDERATIONS: Final[dict[str, dict[str, object]]] = {
    "DE-DESY-ATLAS-T2": {
        "sites": ["DESY-HH", "DESY-ZN"],
        "vo": "atlas",
    },
    "DE-DESY-LHCB": {
        "sites": ["DESY-HH"],
        "vo": "lhcb",
    },
    "DE-DESY-RWTH-CMS-T2": {
        "sites": ["DESY-HH"],
        "vo": "cms",
    },
}
NON_WLCG_FEDERATION: Final[str] = "NON-WLCG-Federation"

# ==============================================================================
# PRODUCED ACCOUNTING DATA
# ==============================================================================

GRID_INFRASTRUCTURE: Final[str] = "Grid"
CLOUD_INFRASTRUCTURE: Final[str] = "Cloud"

COMMON_ACCOUNTING_FIELDS: Final[list[str]] = [
    "raw_wc_time",
    "raw_wc_work",
    "raw_cpu_time",
    "raw_cpu_work",
    "raw_cpu_eff",
]
GRID_ONLY_ACCOUNTING_FIELDS: Final[list[str]] = [
    "number_of_jobs",
]
CLOUD_ONLY_ACCOUNTING_FIELDS: Final[list[str]] = [
]
ALL_ACCOUNTING_FIELDS: Final[list[str]] = COMMON_ACCOUNTING_FIELDS + GRID_ONLY_ACCOUNTING_FIELDS + CLOUD_ONLY_ACCOUNTING_FIELDS

INFLUXDB_TAGS: Final[list[str]] = [
    "vo", "tier", "country", "federation", "site", "infrastructure", "benchmark"
]

PRODUCED_DOC_FIELDS: Final[list[str]] = (
    INFLUXDB_TAGS
    + ["roc"]
    + ALL_ACCOUNTING_FIELDS
    + ["idb_tags", "producer", "type", "timestamp"]
)

# ==============================================================================
# PUBLISHED MESSAGES - MONIT
# ==============================================================================

MQ_CONFIG: Final[dict[str, str | None]] = {
    "host": os.getenv("MQ_HOST"),
    "port": os.getenv("MQ_PORT"),
    "username": os.getenv("MQ_USERNAME"),
    "password": os.getenv("MQ_PASSWORD"),
}
MESSAGE_TOPIC: Final[str] = os.getenv("MESSAGE_TOPIC")
MESSAGE_PRODUCER: Final[str] = os.getenv("MESSAGE_PRODUCER")
MESSAGE_INFLUXDB_MEASUREMENT: Final[str] = os.getenv("MESSAGE_INFLUXDB_MEASUREMENT")
