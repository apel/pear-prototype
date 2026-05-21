import argparse
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TypedDict

try:  # Package imports
    from . import constants
    from .tools import fetch_cric_topology, publish
except ImportError:  # Script-style imports
    import constants
    from tools import fetch_cric_topology, publish

from dateutil.relativedelta import relativedelta
from dirq.queue import Queue

LOG = logging.getLogger("apel_parser")

DESY_FEDERATIONS_OVERRIDES: dict[tuple[str, str], str] = {}
for federation_name, override in constants.DESY_FEDERATIONS.items():
    for site_name in override["sites"]:
        DESY_FEDERATIONS_OVERRIDES[(site_name, str(override["vo"]))] = federation_name

RE_NORMALISED_COMPUTING_DURATION = re.compile(
    r'^\s*\{?\s*(?:(?P<benchmark>[^:}]+?)\s*:\s*)?(?P<duration>[-+]?\d+(?:\.\d+)?)\s*\}?\s*$'
)

SECONDS_PER_HOUR = 3600.0


class SiteInfo(TypedDict):
    tier: str
    country: str
    federation: str
    roc: str


class MessagePayload(TypedDict):
    msgid: str
    body: str


class ParsedAccountingRecord(TypedDict):
    year: int
    month: int
    site: str
    vo: str
    infrastructure: str
    benchmark: str
    tier: str
    country: str
    federation: str
    roc: str
    ce: str
    raw_wc_time: float
    raw_wc_work: float
    raw_cpu_time: float
    raw_cpu_work: float
    raw_cpu_eff: float
    number_of_jobs: int


MonthKey = tuple[int, int]
PerCeKey = tuple[str, str, str, str]
AggKey = tuple[str, str, str]
Bucket = dict[tuple[str, ...], dict[str, Any]]


@dataclass(frozen=True)
class ParserConfig:
    output_dir: Path
    messages_dir: str
    infra_type: str
    months: int
    lhc_only: bool = False
    publish: bool = False


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _canonicalize_vo(raw_vo: str) -> str:
    """Return canonical VO name if known, otherwise return VO name unchanged."""
    return constants.LHC_VOS.get(raw_vo.lower(), raw_vo)


class APELMessageParser:
    def __init__(self, config: ParserConfig) -> None:
        self.config = config
        self.cutoff = date.today().replace(day=1) - relativedelta(months=max(config.months, 1) - 1)
        self.cric_data = fetch_cric_topology()
        if not self.cric_data:
            LOG.warning("CRIC topology is empty; site enrichment may be incomplete")
        self.warned_sites: set[str] = set()

    @staticmethod
    def parse_normalised_computing_duration(raw: str | None) -> tuple[str, float]:
        """Extract benchmark and numeric value from NormalisedWallDuration/NormalisedCpuDuration."""
        if not raw:
            return constants.UNKNOWN, 0.0

        match = RE_NORMALISED_COMPUTING_DURATION.match(raw)
        if not match:
            return constants.UNKNOWN, 0.0

        benchmark = match.group("benchmark").strip().upper() if match.group("benchmark") else constants.UNKNOWN
        duration = _safe_float(match.group("duration"), default=0.0)
        return benchmark, duration

    @staticmethod
    def parse_apel_body(text: str) -> Iterator[dict[str, str]]:
        """Yield dicts from a %%-separated APEL body file."""
        current: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line == "%%":
                if current:
                    yield current
                    current = {}
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            current[key.strip()] = value.strip()

        if current:
            yield current

    def _extract_grid_record(self, rec: dict[str, str], msgid: str) -> ParsedAccountingRecord | None:
        """Convert a grid APEL record into the normalized internal record shape."""
        try:
            year = int(rec.get("Year", 0))
            month = int(rec.get("Month", 0))
        except ValueError:
            return None

        try:
            date_start = date(year, month, 1)
        except ValueError:
            return None
        if date_start < self.cutoff:
            return None

        site = rec.get("Site", "").strip()
        vo = _canonicalize_vo(rec.get("VO", "").strip())
        ce = rec.get("SubmitHost", "").strip() or "None"
        if not site or not vo:
            LOG.warning(
                "Skipping record missing required Site/VO (msgid=%s, year=%s, month=%s)",
                msgid,
                rec.get("Year"),
                rec.get("Month"),
            )
            return None

        if self.config.lhc_only and vo.lower() not in constants.LHC_VOS:
            return None

        processors = max(1, _safe_int(rec.get("Processors"), default=1))
        wc_time = _safe_float(rec.get("WallDuration"), default=0.0)
        wc_time = (wc_time / SECONDS_PER_HOUR) * processors
        benchmark, wc_work = self.parse_normalised_computing_duration(rec.get("NormalisedWallDuration"))
        wc_work = (wc_work / SECONDS_PER_HOUR) * processors
        cpu_time = _safe_float(rec.get("CpuDuration"), default=0.0) / SECONDS_PER_HOUR
        _, cpu_work = self.parse_normalised_computing_duration(rec.get("NormalisedCpuDuration"))
        cpu_work = cpu_work / SECONDS_PER_HOUR
        number_of_jobs = _safe_int(rec.get("NumberOfJobs"), default=0)

        site_info = self.resolve_site(site, vo, year, month)
        if site_info is None:
            if site not in self.warned_sites:
                LOG.warning("Site %s not found in CRIC - skipping enrichment", site)
                self.warned_sites.add(site)
            site_info = {
                "tier": constants.UNKNOWN,
                "country": constants.UNKNOWN,
                "federation": constants.UNKNOWN,
                "roc": constants.UNKNOWN,
            }

        return {
            "year": year,
            "month": month,
            "site": site,
            "vo": vo,
            "infrastructure": constants.GRID_INFRASTRUCTURE,
            "benchmark": benchmark,
            "tier": site_info["tier"],
            "country": site_info["country"],
            "federation": site_info["federation"],
            "roc": site_info["roc"],
            "ce": ce,
            "raw_wc_time": wc_time,
            "raw_wc_work": wc_work,
            "raw_cpu_time": cpu_time,
            "raw_cpu_work": cpu_work,
            "raw_cpu_eff": 0.0,
            "number_of_jobs": number_of_jobs,
        }

    @staticmethod
    def _initialize_bucket_entry(record: ParsedAccountingRecord, include_ce: bool = False) -> dict[str, Any]:
        """Create a new bucket entry from a normalized accounting record."""
        entry: dict[str, Any] = {
            "site": record["site"],
            "vo": record["vo"],
            "infrastructure": record["infrastructure"],
            "benchmark": record["benchmark"],
            "tier": record["tier"],
            "country": record["country"],
            "federation": record["federation"],
            "roc": record["roc"],
        }
        if include_ce:
            entry["ce"] = record["ce"]

        for field in constants.ALL_ACCOUNTING_FIELDS:
            entry[field] = 0.0
        entry["number_of_jobs"] = 0

        return entry

    @staticmethod
    def _accumulate_bucket_entry(entry: dict[str, Any], record: ParsedAccountingRecord) -> None:
        """Add a normalized accounting record into a bucket entry."""
        entry["raw_wc_time"] += record["raw_wc_time"]
        entry["raw_wc_work"] += record["raw_wc_work"]
        entry["raw_cpu_time"] += record["raw_cpu_time"]
        entry["raw_cpu_work"] += record["raw_cpu_work"]
        entry["number_of_jobs"] += record["number_of_jobs"]

    def _extract_record(self, rec: dict[str, str], msgid: str) -> ParsedAccountingRecord | None:
        """Dispatch extraction based on the parser infra type selected from CLI."""
        if self.config.infra_type == constants.GRID_INFRASTRUCTURE:
            return self._extract_grid_record(rec, msgid)
        raise ValueError(f"Unsupported infra type: {self.config.infra_type}")

    def resolve_site(self, site_name: str, vo: str, year: int, month: int) -> SiteInfo | None:
        """Look up tier, country, federation, and roc for an rcsite name."""
        if site_name not in self.cric_data:
            return None
        
        rcsite = self.cric_data[site_name]
        
        country = rcsite.get("country_code") or constants.UNKNOWN
        
        if vo.lower() in constants.LHC_VOS:
            tier_level = rcsite.get("rc_tier_level")
            if site_name == "CERN-PROD":
                tier = "Tier-0"
            elif tier_level in constants.WLCG_TIERS:
                tier = f"Tier-{tier_level}"
            else:
                tier = constants.UNKNOWN

            cric_federations = rcsite.get("federations", [])
            if not cric_federations:
                federation = constants.NON_MOU_FEDERATION
            elif len(cric_federations) == 1:
                federation = cric_federations[0]
            else:
                federation = constants.UNKNOWN
            if desy_federation_override := DESY_FEDERATIONS_OVERRIDES.get((site_name, vo.lower())):
                federation = desy_federation_override
            elif site_name == "JINR-LCG2":
                federation = "JINR-LCG2" if date(year, month, 1) >= date(2024, 11, 1) else "RU-RDIG"
        else:
            tier = constants.NON_WLCG_TIER
            federation = constants.NON_WLCG_FEDERATION

        roc = rcsite.get("roc") or constants.UNKNOWN
        
        return {"tier": tier, "country": country, "federation": federation, "roc": roc}

    def load_messages(self) -> tuple[Any, list[MessagePayload]]:
        """Lock and read all available dirq messages, returning payloads."""
        queue = Queue(self.config.messages_dir, schema=constants.APEL_DIRQ_SCHEMA)
        locked_messages: list[MessagePayload] = []

        for msgid in queue:
            if not queue.lock(msgid):
                continue

            try:
                record = queue.get(msgid)
                body = record.get("body", "") if isinstance(record, dict) else ""
                locked_messages.append({"msgid": msgid, "body": str(body or "")})
            except Exception:
                LOG.exception("Failed to read queue message %s; unlocking", msgid)
                try:
                    queue.unlock(msgid)
                except Exception:
                    LOG.exception("Failed to unlock queue message %s", msgid)

        return queue, locked_messages

    def ingest(
        self, messages: list[MessagePayload]
    ) -> tuple[dict[MonthKey, Bucket], dict[MonthKey, Bucket] | None]:
        """
        Parse APEL payloads and return aggregated and per-CE monthly buckets.

        The per-CE bucket is `None` when per-CE aggregation is not applicable
        for the configured infrastructure type (e.g. cloud).
        """
        agg: dict[MonthKey, Bucket] = {}
        per_ce: dict[MonthKey, Bucket] | None = (
            {} if self.config.infra_type == constants.GRID_INFRASTRUCTURE else None
        )

        for message in messages:
            msgid = message["msgid"]
            for rec in self.parse_apel_body(message["body"]):
                record = self._extract_record(rec, msgid)
                if record is None:
                    continue

                month_key: MonthKey = (record["year"], record["month"])

                agg_key: AggKey = (record["site"], record["vo"], record["benchmark"])
                agg_bucket = agg.setdefault(month_key, {})
                if agg_key not in agg_bucket:
                    agg_bucket[agg_key] = self._initialize_bucket_entry(record, include_ce=False)
                self._accumulate_bucket_entry(agg_bucket[agg_key], record)

                if per_ce is not None:
                    ce_key: PerCeKey = (record["site"], record["vo"], record["ce"], record["benchmark"])
                    ce_bucket = per_ce.setdefault(month_key, {})
                    if ce_key not in ce_bucket:
                        ce_bucket[ce_key] = self._initialize_bucket_entry(record, include_ce=True)
                    self._accumulate_bucket_entry(ce_bucket[ce_key], record)

        return agg, per_ce

    @staticmethod
    def build_docs(bucket: Bucket, year: int, month: int, with_ce: bool = False) -> list[OrderedDict[str, Any]]:
        """Turn an accumulated bucket into the JSON document list matching ACC.py schema."""
        dt = datetime(year, month, 1, tzinfo=timezone.utc)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        timestamp = int((dt - epoch).total_seconds() * 1000)

        idb_tags = list(constants.INFLUXDB_TAGS)
        produced_doc_fields = list(constants.PRODUCED_DOC_FIELDS)
        if with_ce:
            idb_tags += ["ce"]
            produced_doc_fields.insert(len(constants.INFLUXDB_TAGS), "ce")

        docs: list[OrderedDict[str, Any]] = []
        for entry in bucket.values():
            wc_time = _safe_float(entry.get("raw_wc_time"), default=0.0)
            cpu_time = _safe_float(entry.get("raw_cpu_time"), default=0.0)
            cpu_eff = cpu_time / wc_time if wc_time > 0 else 0.0

            doc: OrderedDict[str, Any] = OrderedDict()
            for key in produced_doc_fields:
                if key == "idb_tags":
                    doc[key] = idb_tags
                elif key == "producer":
                    doc[key] = constants.MESSAGE_PRODUCER
                elif key == "type":
                    doc[key] = constants.MESSAGE_INFLUXDB_MEASUREMENT
                elif key == "timestamp":
                    doc[key] = timestamp
                elif key == "raw_cpu_eff":
                    doc[key] = cpu_eff
                else:
                    doc[key] = entry.get(key, 0)
            docs.append(doc)
        return docs

    def write_outputs(
        self, agg: dict[MonthKey, Bucket], per_ce: dict[MonthKey, Bucket] | None
    ) -> None:
        """Write aggregated (and, for grid, per-CE) JSON output files for each month."""
        all_months = sorted(set(per_ce or {}) | set(agg))

        for year, month in all_months:
            LOG.info("Writing data for %02d/%d", month, year)

            agg_docs = self.build_docs(agg.get((year, month), {}), year, month, with_ce=False)
            agg_path = self.config.output_dir / f"data_cpu_acc_{year}_{month}.json"
            agg_path.write_text(json.dumps(agg_docs, indent=4), encoding="utf-8")

            if per_ce is not None:
                ce_docs = self.build_docs(per_ce.get((year, month), {}), year, month, with_ce=True)
                ce_path = self.config.output_dir / f"data_cpu_acc_ce_{year}_{month}.json"
                ce_path.write_text(json.dumps(ce_docs, indent=4), encoding="utf-8")

            if self.config.publish:
                publish(str(agg_path))

    def process(self) -> None:
        queue, locked_messages = self.load_messages()

        if not locked_messages:
            LOG.info("No dirq messages found for processing")
            try:
                queue.purge()
            except Exception:
                LOG.exception("Failed to purge dirq queue directories")
            return

        locked_msgids = [message["msgid"] for message in locked_messages]
        LOG.info("Locked %d dirq messages for processing", len(locked_msgids))

        try:
            agg, per_ce = self.ingest(locked_messages)
            self.write_outputs(agg, per_ce)
        except Exception:
            for msgid in locked_msgids:
                try:
                    queue.unlock(msgid)
                except Exception:
                    LOG.exception("Failed to unlock message %s after processing error", msgid)
            raise
        else:
            removed = 0
            for msgid in locked_msgids:
                try:
                    queue.remove(msgid)
                    removed += 1
                except Exception:
                    LOG.exception(
                        "Processing succeeded but failed to remove message %s; it will be retried",
                        msgid,
                    )
            LOG.info("Removed %d/%d processed dirq messages", removed, len(locked_msgids))
        finally:
            try:
                queue.purge()
            except Exception:
                LOG.exception("Failed to purge dirq queue directories")


def get_data_for_period(
    output_dir: str,
    messages_dir: str,
    infra_type: str,
    months: int,
    lhc_only: bool = False,
    publish: bool = False,
) -> None:
    config = ParserConfig(
        output_dir=Path(output_dir),
        messages_dir=messages_dir,
        infra_type=infra_type,
        months=months,
        lhc_only=lhc_only,
        publish=publish,
    )
    APELMessageParser(config).process()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate CPU accounting data from APEL spool files (replaces EGI portal source)"
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        metavar="",
        required=True,
        help="Path to output directory"
    )
    parser.add_argument(
        "--messages-dir",
        type=str,
        default=constants.DEFAULT_MESSAGES_DIR,
        help=f"Directory containing APEL dirq messages (default: {constants.DEFAULT_MESSAGES_DIR})",
    )
    parser.add_argument(
        "--infra-type",
        type=str,
        required=True,
        choices=[constants.GRID_INFRASTRUCTURE, constants.CLOUD_INFRASTRUCTURE],
        help=(
            "Infrastructure type of data contained in messages of --messages-dir"
        ),
    )
    parser.add_argument(
        "-m",
        "--months",
        type=int,
        metavar="",
        default=1,
        help="Months before current date to ingest. Default: 1",
    )
    parser.add_argument(
        "--lhc-only",
        action="store_true",
        help="Only ingest records of LHC VOs: ATLAS, CMS, ALICE, LHCb",
    )
    parser.add_argument(
        "-p",
        "--publish",
        action="store_true",
        help="Publish aggregated results to message broker",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    output_timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    output_path = Path(args.output_dir) / output_timestamp
    if not output_path.is_dir():
        LOG.info("Creating output directory %s", output_path)
        output_path.mkdir(parents=True, exist_ok=True)

    get_data_for_period(
        str(output_path),
        args.messages_dir,
        args.infra_type,
        args.months,
        args.lhc_only,
        args.publish,
    )


if __name__ == "__main__":
    main()
