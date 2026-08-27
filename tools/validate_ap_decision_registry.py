"""Validate AYO's append-only AP decision-ID registry without mutating Git."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AP_PATTERN = re.compile(r"^AP-[0-9]{3,}$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
HEADING_PATTERN = re.compile(r"^###\s+(AP-[0-9]{3,})\s+[—-]\s+(.+?)\s*$", re.MULTILINE)
BOOTSTRAP_STATUSES = frozenset(
    {"RESERVED", "ALLOCATED", "SUPERSEDED", "COLLISION_REPAIR"}
)
EVENT_TYPES = frozenset({"RESERVED", "ALLOCATED", "SUPERSEDED"})
RECONCILIATION_STATUSES = frozenset(
    {"NOT_REQUIRED", "PENDING_MAIN_REVIEW", "UNRESOLVED", "RESOLVED"}
)
REGISTRY_FIELDS_V1 = frozenset(
    {
        "schema_version",
        "registry_namespace",
        "serialization_authority",
        "cutover",
        "blocked_unexplained_ranges",
        "allocations",
    }
)
REGISTRY_FIELDS_V2 = REGISTRY_FIELDS_V1 | {
    "forward_identity_events",
    "collision_reconciliations",
}
CUTOVER_FIELDS = frozenset(
    {
        "cutover_id",
        "approved_date",
        "activation",
        "status",
        "founder_approval",
        "cto_approval",
    }
)
ALLOCATION_FIELDS = frozenset(
    {
        "ap_id",
        "title",
        "status",
        "authority",
        "introducing_commit",
        "lineage_ref",
        "on_main",
        "origin",
        "reconciliation_status",
    }
)
EVENT_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "ap_id",
        "title",
        "purpose",
        "base_main_commit",
        "prior_event_id",
        "authority",
        "approved_date",
    }
)
RECONCILIATION_FIELDS = frozenset(
    {
        "reconciliation_id",
        "historical_introducing_commit",
        "historical_ap_id",
        "historical_title",
        "historical_composite_commitment",
        "successor_ap_id",
        "successor_title",
        "successor_allocation_event_id",
        "base_main_commit",
        "authority",
        "approved_date",
    }
)

AP_099_TITLE = (
    "AYO Founder Institutional Discovery Corpus Phase 5 Preservation Foundation"
)
AP_099_PURPOSE = "Replacement forward permanent identity for the already-approved Phase 5 Preservation Foundation historically recorded under colliding AP-079. It grants no dual-corpus amendment authority, corpus receipt authority, or ingestion authority."
AP_100_TITLE = "AYO Founder Institutional Discovery Phase 5 Dual-Corpus and Source-Preservation Amendment"
AP_100_PURPOSE = "Future authority for raw source artifact custody, source-unit inventory, canonical numbered corpus provenance, separate Discovery Intelligence preservation, extraction ledger, coverage semantics, and open-count Discovery Intelligence validation. Reservation alone grants no implementation or ingestion authority."
AUTHORIZED_FORWARD_RESERVATIONS = {
    "AP-099": (AP_099_TITLE, AP_099_PURPOSE),
    "AP-100": (AP_100_TITLE, AP_100_PURPOSE),
}


class RegistryValidationError(ValueError):
    """A bounded, user-facing AP registry invariant failure."""


@dataclass(frozen=True)
class RegistryReport:
    allocation_count: int
    ap_id_count: int
    collision_id_count: int
    decision_heading_count: int
    forward_event_count: int
    reconciliation_count: int
    effectively_resolved_count: int


def _exact_fields(
    value: dict[str, Any], expected: frozenset[str], location: str
) -> None:
    missing = sorted(expected - frozenset(value))
    unexpected = sorted(frozenset(value) - expected)
    if missing:
        raise RegistryValidationError(
            f"{location}: missing fields: {', '.join(missing)}"
        )
    if unexpected:
        raise RegistryValidationError(
            f"{location}: unexpected fields: {', '.join(unexpected)}"
        )


def _load_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise RegistryValidationError(f"{path}: UTF-8 BOM is forbidden")
    if b"\x00" in raw or b"\r" in raw:
        raise RegistryValidationError(f"{path}: NUL and CR bytes are forbidden")
    if not raw.endswith(b"\n"):
        raise RegistryValidationError(f"{path}: exactly one terminal LF is required")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryValidationError(
            f"{path}: malformed UTF-8 or JSON: {error}"
        ) from None
    if not isinstance(value, dict):
        raise RegistryValidationError(f"{path}: registry must be a JSON object")
    return value


def parse_decision_headings(text: str) -> tuple[tuple[str, str], ...]:
    return tuple((m.group(1), m.group(2)) for m in HEADING_PATTERN.finditer(text))


def canonical_commitment(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def historical_composite_commitment(
    introducing_commit: str, ap_id: str, title: str
) -> str:
    return hashlib.sha256(
        introducing_commit.encode() + b"\0" + ap_id.encode() + b"\0" + title.encode()
    ).hexdigest()


def event_id(event: dict[str, Any]) -> str:
    return canonical_commitment({k: v for k, v in event.items() if k != "event_id"})


def reconciliation_id(item: dict[str, Any]) -> str:
    return canonical_commitment(
        {k: v for k, v in item.items() if k != "reconciliation_id"}
    )


def effective_reconciliation_status(
    allocation: dict[str, Any], reconciliations: list[dict[str, Any]]
) -> str:
    identity = (
        allocation["introducing_commit"],
        allocation["ap_id"],
        allocation["title"],
    )
    n = sum(
        (
            r["historical_introducing_commit"],
            r["historical_ap_id"],
            r["historical_title"],
        )
        == identity
        for r in reconciliations
    )
    return "RESOLVED" if n == 1 else allocation["reconciliation_status"]


def validate_authorized_forward_reservation(event: dict[str, Any]) -> None:
    expected = AUTHORIZED_FORWARD_RESERVATIONS.get(event.get("ap_id"))
    if event.get("event_type") != "RESERVED" or expected != (
        event.get("title"),
        event.get("purpose"),
    ):
        raise RegistryValidationError(
            "forward reservation lacks exact AP-099/AP-100 authorization"
        )


def _validate_ranges(value: Any) -> list[tuple[int, int]]:
    if not isinstance(value, list):
        raise RegistryValidationError("blocked_unexplained_ranges must be an array")
    result = []
    for i, item in enumerate(value):
        location = f"blocked_unexplained_ranges[{i}]"
        if not isinstance(item, dict) or frozenset(item) != {"start", "end", "reason"}:
            raise RegistryValidationError(f"{location}: malformed range record")
        start, end, reason = item["start"], item["end"], item["reason"]
        if type(start) is not int or type(end) is not int or start < 1 or end < start:
            raise RegistryValidationError(f"{location}: invalid numeric range")
        if not isinstance(reason, str) or not reason:
            raise RegistryValidationError(f"{location}: reason must be non-empty")
        if result and start <= result[-1][1]:
            raise RegistryValidationError(
                f"{location}: ranges overlap or are unordered"
            )
        result.append((start, end))
    return result


def _commit(sha: Any, location: str, resolver: Callable[[str], bool] | None) -> str:
    if not isinstance(sha, str) or not SHA_PATTERN.fullmatch(sha):
        raise RegistryValidationError(f"{location}: malformed Git commit")
    if resolver is not None and not resolver(sha):
        raise RegistryValidationError(f"{location}: Git commit object does not exist")
    return sha


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegistryValidationError(f"{location}: value must be non-empty")
    return value


def validate_registry(
    registry: dict[str, Any],
    decision_log_text: str,
    *,
    baseline_registry: dict[str, Any] | None = None,
    baseline_main_commit: str | None = None,
    commit_exists: Callable[[str], bool] | None = None,
    enablement_only: bool = False,
) -> RegistryReport:
    """Validate immutable bootstrap history and append-only lifecycle evidence."""
    schema = registry.get("schema_version")
    fields = REGISTRY_FIELDS_V1 if schema == 1 else REGISTRY_FIELDS_V2
    _exact_fields(registry, fields, "registry")
    if schema not in {1, 2}:
        raise RegistryValidationError("schema_version must be integer 1 or 2")
    if registry["registry_namespace"] != "ayo.governance.ap_decision_ids":
        raise RegistryValidationError("unexpected registry_namespace")
    if registry["serialization_authority"] != "GIT_MAIN":
        raise RegistryValidationError("serialization_authority must be GIT_MAIN")
    cutover = registry["cutover"]
    if not isinstance(cutover, dict):
        raise RegistryValidationError("cutover must be an object")
    _exact_fields(cutover, CUTOVER_FIELDS, "cutover")
    approved = {
        "cutover_id": "AYO_AP_REGISTRY_V1",
        "approved_date": "2026-08-26",
        "activation": "ON_REGISTRY_INCLUSION_IN_MAIN",
        "founder_approval": "APPROVED",
        "cto_approval": "APPROVED",
    }
    if any(cutover[k] != v for k, v in approved.items()):
        raise RegistryValidationError("cutover differs from approved bootstrap")
    if cutover["status"] not in {
        "PENDING_MAIN_ACTIVATION",
        "READY_FOR_MAIN_ACTIVATION",
        "ACTIVE",
    }:
        raise RegistryValidationError("cutover.status is invalid")
    blocked = _validate_ranges(registry["blocked_unexplained_ranges"])
    allocations = registry["allocations"]
    if not isinstance(allocations, list) or not allocations:
        raise RegistryValidationError("allocations must be a non-empty array")
    events = registry.get("forward_identity_events", [])
    reconciliations = registry.get("collision_reconciliations", [])
    if not isinstance(events, list) or not isinstance(reconciliations, list):
        raise RegistryValidationError("lifecycle collections must be arrays")
    if enablement_only and (events or reconciliations):
        raise RegistryValidationError(
            "enablement candidate cannot instantiate lifecycle authority"
        )
    identities = set()
    by_id: dict[str, list[dict[str, Any]]] = {}
    previous = None
    for i, item in enumerate(allocations):
        loc = f"allocations[{i}]"
        if not isinstance(item, dict):
            raise RegistryValidationError(f"{loc}: allocation must be an object")
        _exact_fields(item, ALLOCATION_FIELDS, loc)
        ap_id = item["ap_id"]
        if not isinstance(ap_id, str) or not AP_PATTERN.fullmatch(ap_id):
            raise RegistryValidationError(f"{loc}: malformed AP identifier")
        title = _text(item["title"], f"{loc}.title")
        status = item["status"]
        if status not in BOOTSTRAP_STATUSES:
            raise RegistryValidationError(f"{loc}: invalid status")
        for field in ("authority", "lineage_ref", "origin"):
            _text(item[field], f"{loc}.{field}")
        commit = _commit(
            item["introducing_commit"], f"{loc}.introducing_commit", commit_exists
        )
        if type(item["on_main"]) is not bool:
            raise RegistryValidationError(f"{loc}: on_main must be boolean")
        state = item["reconciliation_status"]
        if state not in RECONCILIATION_STATUSES:
            raise RegistryValidationError(f"{loc}: invalid reconciliation_status")
        if status == "COLLISION_REPAIR" and state not in {"UNRESOLVED", "RESOLVED"}:
            raise RegistryValidationError(
                f"{loc}: collision repair must be unresolved or resolved"
            )
        if status != "COLLISION_REPAIR" and state == "UNRESOLVED":
            raise RegistryValidationError(
                f"{loc}: unresolved reconciliation requires COLLISION_REPAIR"
            )
        number = int(ap_id[3:])
        if any(a <= number <= b for a, b in blocked):
            raise RegistryValidationError(
                f"{loc}: unexplained historical gap {ap_id} cannot be allocated"
            )
        identity = (ap_id, title, commit)
        key = (number, title, commit)
        if identity in identities:
            raise RegistryValidationError(f"{loc}: duplicate registry record")
        if previous is not None and key <= previous:
            raise RegistryValidationError("allocations must use deterministic ordering")
        identities.add(identity)
        previous = key
        by_id.setdefault(ap_id, []).append(item)
    collisions = 0
    for ap_id, records in by_id.items():
        titles = {r["title"] for r in records}
        active = [r for r in records if r["status"] in {"RESERVED", "ALLOCATED"}]
        if len(titles) > 1:
            collisions += 1
            if any(r["status"] != "COLLISION_REPAIR" for r in records):
                raise RegistryValidationError(
                    f"{ap_id}: colliding legacy titles must all be COLLISION_REPAIR"
                )
        if len({r["title"] for r in active}) > 1:
            raise RegistryValidationError(
                f"{ap_id}: duplicate global AP ID assigned to active titles"
            )
        if (
            any(r["status"] in {"SUPERSEDED", "COLLISION_REPAIR"} for r in records)
            and active
        ):
            raise RegistryValidationError(
                f"{ap_id}: repaired identity cannot be silently reused"
            )
    event_by_id = {}
    latest = {}
    for i, item in enumerate(events):
        loc = f"forward_identity_events[{i}]"
        if not isinstance(item, dict):
            raise RegistryValidationError(f"{loc}: event must be an object")
        _exact_fields(item, EVENT_FIELDS, loc)
        if item["event_type"] not in EVENT_TYPES:
            raise RegistryValidationError(f"{loc}: unsupported event type")
        ap_id = item["ap_id"]
        if not isinstance(ap_id, str) or not AP_PATTERN.fullmatch(ap_id):
            raise RegistryValidationError(f"{loc}: malformed AP identifier")
        if ap_id in by_id:
            raise RegistryValidationError(
                f"{loc}: active historical AP ID cannot be reused"
            )
        if any(a <= int(ap_id[3:]) <= b for a, b in blocked):
            raise RegistryValidationError(f"{loc}: blocked AP range cannot be reserved")
        for field in ("title", "purpose", "authority"):
            _text(item[field], f"{loc}.{field}")
        _commit(item["base_main_commit"], f"{loc}.base_main_commit", commit_exists)
        if not DATE_PATTERN.fullmatch(str(item["approved_date"])):
            raise RegistryValidationError(f"{loc}: malformed approved_date")
        if item["event_id"] != event_id(item):
            raise RegistryValidationError(f"{loc}: malformed event_id")
        if item["event_id"] in event_by_id:
            raise RegistryValidationError(f"{loc}: duplicate event_id")
        prior_id = item["prior_event_id"]
        prior = event_by_id.get(prior_id) if isinstance(prior_id, str) else None
        kind = item["event_type"]
        if kind == "RESERVED":
            if prior_id is not None or ap_id in latest:
                raise RegistryValidationError(
                    f"{loc}: reservation must start a new identity chain"
                )
        else:
            if prior is None or prior is not latest.get(ap_id):
                raise RegistryValidationError(
                    f"{loc}: missing, circular, or non-latest prior event"
                )
            if (item["title"], item["purpose"]) != (prior["title"], prior["purpose"]):
                raise RegistryValidationError(
                    f"{loc}: lifecycle title or purpose mismatch"
                )
            if prior["event_type"] != (
                "RESERVED" if kind == "ALLOCATED" else "ALLOCATED"
            ):
                raise RegistryValidationError(f"{loc}: invalid lifecycle transition")
        event_by_id[item["event_id"]] = item
        latest[ap_id] = item
    rec_ids = set()
    historical_maps = set()
    successor_maps = set()
    for i, item in enumerate(reconciliations):
        loc = f"collision_reconciliations[{i}]"
        if not isinstance(item, dict):
            raise RegistryValidationError(f"{loc}: reconciliation must be an object")
        _exact_fields(item, RECONCILIATION_FIELDS, loc)
        for field in ("historical_title", "successor_title", "authority"):
            _text(item[field], f"{loc}.{field}")
        commit = _commit(
            item["historical_introducing_commit"],
            f"{loc}.historical_introducing_commit",
            commit_exists,
        )
        _commit(item["base_main_commit"], f"{loc}.base_main_commit", commit_exists)
        if not DATE_PATTERN.fullmatch(str(item["approved_date"])):
            raise RegistryValidationError(f"{loc}: malformed approved_date")
        historical = (commit, item["historical_ap_id"], item["historical_title"])
        matching = [
            r
            for r in allocations
            if (r["introducing_commit"], r["ap_id"], r["title"]) == historical
        ]
        if len(matching) != 1 or matching[0]["status"] != "COLLISION_REPAIR":
            raise RegistryValidationError(f"{loc}: malformed historical tuple")
        if item["historical_composite_commitment"] != historical_composite_commitment(
            *historical
        ):
            raise RegistryValidationError(
                f"{loc}: historical composite commitment mismatch"
            )
        successor = event_by_id.get(item["successor_allocation_event_id"])
        if successor is None or successor["event_type"] != "ALLOCATED":
            raise RegistryValidationError(
                f"{loc}: successor lacks authoritative allocation"
            )
        if latest.get(successor["ap_id"]) is not successor:
            raise RegistryValidationError(f"{loc}: successor allocation is superseded")
        if (item["successor_ap_id"], item["successor_title"]) != (
            successor["ap_id"],
            successor["title"],
        ):
            raise RegistryValidationError(f"{loc}: wrong successor AP identity")
        if item["reconciliation_id"] != reconciliation_id(item):
            raise RegistryValidationError(f"{loc}: malformed reconciliation_id")
        if item["reconciliation_id"] in rec_ids:
            raise RegistryValidationError(f"{loc}: duplicate reconciliation_id")
        if historical in historical_maps:
            raise RegistryValidationError(
                f"{loc}: historical identity mapped more than once"
            )
        if successor["event_id"] in successor_maps:
            raise RegistryValidationError(
                f"{loc}: successor mapped to multiple historical identities"
            )
        rec_ids.add(item["reconciliation_id"])
        historical_maps.add(historical)
        successor_maps.add(successor["event_id"])
    headings = parse_decision_headings(decision_log_text)
    allocated = {
        (e["ap_id"], e["title"]) for e in events if e["event_type"] == "ALLOCATED"
    }
    registered = {(a["ap_id"], a["title"]) for a in allocations} | allocated
    for h in headings:
        if h not in registered:
            raise RegistryValidationError(
                f"decision log allocation lacks registry authority: {h[0]} — {h[1]}"
            )
    for item in events:
        h = (item["ap_id"], item["title"])
        if item["event_type"] == "RESERVED" and h in headings and h not in allocated:
            raise RegistryValidationError(
                f"{item['ap_id']}: reservation has an allocation heading"
            )
    heading_counts = Counter(headings)
    for ap_id, item in latest.items():
        if (
            item["event_type"] == "ALLOCATED"
            and heading_counts[(ap_id, item["title"])] != 1
        ):
            raise RegistryValidationError(
                f"{ap_id}: effective allocation requires exactly one decision-log heading"
            )
    if baseline_registry is not None:
        if allocations != baseline_registry.get("allocations"):
            raise RegistryValidationError(
                "post-cutover bootstrap allocation mutation is prohibited"
            )
        base_events = baseline_registry.get("forward_identity_events", [])
        base_recs = baseline_registry.get("collision_reconciliations", [])
        if events[: len(base_events)] != base_events:
            raise RegistryValidationError("forward identity events are not append-only")
        if reconciliations[: len(base_recs)] != base_recs:
            raise RegistryValidationError(
                "collision reconciliations are not append-only"
            )
        if baseline_main_commit is not None:
            _commit(baseline_main_commit, "baseline_main_commit", commit_exists)
            for item in events[len(base_events) :] + reconciliations[len(base_recs) :]:
                if item["base_main_commit"] != baseline_main_commit:
                    raise RegistryValidationError(
                        "new lifecycle evidence uses the wrong authoritative base"
                    )
        base_event_ids = {e.get("event_id") for e in base_events if isinstance(e, dict)}
        for item in events[len(base_events) :]:
            if (
                item["event_type"] == "ALLOCATED"
                and item["prior_event_id"] not in base_event_ids
            ):
                raise RegistryValidationError(
                    "allocation lacks prior baseline-main reservation"
                )
        base_allocated = {
            e.get("event_id")
            for e in base_events
            if isinstance(e, dict) and e.get("event_type") == "ALLOCATED"
        }
        for item in reconciliations[len(base_recs) :]:
            if item["successor_allocation_event_id"] not in base_allocated:
                raise RegistryValidationError(
                    "reconciliation lacks prior baseline-main allocation"
                )
    resolved = sum(
        effective_reconciliation_status(a, reconciliations) == "RESOLVED"
        for a in allocations
        if a["status"] == "COLLISION_REPAIR"
    )
    return RegistryReport(
        len(allocations),
        len(by_id),
        collisions,
        len(headings),
        len(events),
        len(reconciliations),
        resolved,
    )


def _git_commit_exists(sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the central AYO AP registry."
    )
    parser.add_argument(
        "--registry", type=Path, default=Path("docs/AYO_DECISION_ID_REGISTRY.json")
    )
    parser.add_argument(
        "--decision-log", type=Path, default=Path("docs/AYO_DECISION_LOG.md")
    )
    parser.add_argument("--baseline-registry", type=Path)
    parser.add_argument("--baseline-main-commit")
    parser.add_argument("--enablement-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        registry = _load_json(args.registry)
        decision = args.decision_log.read_text(encoding="utf-8")
        baseline = (
            _load_json(args.baseline_registry) if args.baseline_registry else None
        )
        report = validate_registry(
            registry,
            decision,
            baseline_registry=baseline,
            baseline_main_commit=args.baseline_main_commit,
            commit_exists=_git_commit_exists,
            enablement_only=args.enablement_only,
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        RegistryValidationError,
    ) as error:
        print(f"AYO_AP_REGISTRY_INVALID: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report.__dict__, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
