import os
from typing import Final


DEFAULT_MESSAGES_DIR: Final[str] = "/var/spool/apel/grid/incoming"

APEL_DIRQ_SCHEMA: Final[dict[str, str]] = {
    "body": "string",
    "signer": "string",
    "empaid": "string?",
}

CRIC_RCSITE_API: Final[str] = "https://wlcg-cric.cern.ch/api/core/rcsite/query/?json&state=ANY"
CRIC_REQUEST_TIMEOUT_SECONDS: Final[int] = 30
IGTF_TRUST_BUNDLE_PATH: Final[str] = "/cvmfs/grid.cern.ch/etc/grid-security/certificates"

UNKNOWN: Final[str] = "UNKNOWN"

GRID_INFRASTRUCTURE: Final[str] = "Grid"

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

MQ_CONFIG: Final[dict[str, str | None]] = {
    "host": os.getenv("MQ_HOST"),
    "port": os.getenv("MQ_PORT"),
    "username": os.getenv("MQ_USERNAME"),
    "password": os.getenv("MQ_PASSWORD"),
}
MESSAGE_TOPIC: Final[str] = os.getenv("MESSAGE_TOPIC")
MESSAGE_PRODUCER: Final[str] = os.getenv("MESSAGE_PRODUCER")
MESSAGE_INFLUXDB_MEASUREMENT: Final[str] = os.getenv("MESSAGE_INFLUXDB_MEASUREMENT")
