"""Validate AYO's central AP decision-ID registry without mutating Git state."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AP_PATTERN = re.compile(r"^AP-[0-9]{3,}$")
HEADING_PATTERN = re.compile(r"^###\s+(AP-[0-9]{3,})\s+[—-]\s+(.+?)\s*$", re.MULTILINE)
STATUSES = frozenset({"RESERVED", "ALLOCATED", "SUPERSEDED", "COLLISION_REPAIR"})
RECONCILIATION_STATUSES = frozenset(
    {"NOT_REQUIRED", "PENDING_MAIN_REVIEW", "UNRESOLVED", "RESOLVED"}
)
REGISTRY_FIELDS = frozenset(
    {
        "schema_version",
        "registry_namespace",
        "serialization_authority",
        "cutover",
        "blocked_unexplained_ranges",
        "allocations",
    }
)
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


class RegistryValidationError(ValueError):
    """A bounded, user-facing AP registry invariant failure."""


@dataclass(frozen=True)
class RegistryReport:
    allocation_count: int
    ap_id_count: int
    collision_id_count: int
    decision_heading_count: int


def _exact_fields(
    value: dict[str, Any], expected: frozenset[str], location: str
) -> None:
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
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
    return tuple(
        (match.group(1), match.group(2)) for match in HEADING_PATTERN.finditer(text)
    )


def _validate_ranges(value: Any) -> list[tuple[int, int]]:
    if not isinstance(value, list):
        raise RegistryValidationError("blocked_unexplained_ranges must be an array")
    ranges: list[tuple[int, int]] = []
    for index, item in enumerate(value):
        location = f"blocked_unexplained_ranges[{index}]"
        if not isinstance(item, dict) or frozenset(item) != {"start", "end", "reason"}:
            raise RegistryValidationError(f"{location}: malformed range record")
        start, end, reason = item["start"], item["end"], item["reason"]
        if type(start) is not int or type(end) is not int or start < 1 or end < start:
            raise RegistryValidationError(f"{location}: invalid numeric range")
        if not isinstance(reason, str) or not reason:
            raise RegistryValidationError(f"{location}: reason must be non-empty")
        if ranges and start <= ranges[-1][1]:
            raise RegistryValidationError(
                f"{location}: ranges overlap or are unordered"
            )
        ranges.append((start, end))
    return ranges


def validate_registry(
    registry: dict[str, Any],
    decision_log_text: str,
    *,
    baseline_registry: dict[str, Any] | None = None,
) -> RegistryReport:
    """Validate registry structure, historical repair, and decision-log authority."""

    _exact_fields(registry, REGISTRY_FIELDS, "registry")
    if registry["schema_version"] != 1:
        raise RegistryValidationError("schema_version must be integer 1")
    if registry["registry_namespace"] != "ayo.governance.ap_decision_ids":
        raise RegistryValidationError("unexpected registry_namespace")
    if registry["serialization_authority"] != "GIT_MAIN":
        raise RegistryValidationError("serialization_authority must be GIT_MAIN")

    cutover = registry["cutover"]
    if not isinstance(cutover, dict):
        raise RegistryValidationError("cutover must be an object")
    _exact_fields(cutover, CUTOVER_FIELDS, "cutover")
    expected_cutover = {
        "cutover_id": "AYO_AP_REGISTRY_V1",
        "approved_date": "2026-08-26",
        "activation": "ON_REGISTRY_INCLUSION_IN_MAIN",
        "founder_approval": "APPROVED",
        "cto_approval": "APPROVED",
    }
    for field, expected in expected_cutover.items():
        if cutover[field] != expected:
            raise RegistryValidationError(
                f"cutover.{field} differs from approved bootstrap"
            )
    if cutover["status"] not in {
        "PENDING_MAIN_ACTIVATION",
        "READY_FOR_MAIN_ACTIVATION",
        "ACTIVE",
    }:
        raise RegistryValidationError("cutover.status is invalid")

    blocked_ranges = _validate_ranges(registry["blocked_unexplained_ranges"])
    allocations = registry["allocations"]
    if not isinstance(allocations, list) or not allocations:
        raise RegistryValidationError("allocations must be a non-empty array")

    identities: set[tuple[str, str, str]] = set()
    by_id: dict[str, list[dict[str, Any]]] = {}
    previous_key: tuple[int, str, str] | None = None
    for index, item in enumerate(allocations):
        location = f"allocations[{index}]"
        if not isinstance(item, dict):
            raise RegistryValidationError(f"{location}: allocation must be an object")
        _exact_fields(item, ALLOCATION_FIELDS, location)
        ap_id = item["ap_id"]
        if not isinstance(ap_id, str) or AP_PATTERN.fullmatch(ap_id) is None:
            raise RegistryValidationError(f"{location}: malformed AP identifier")
        numeric_id = int(ap_id[3:])
        title = item["title"]
        if not isinstance(title, str) or not title:
            raise RegistryValidationError(f"{location}: title must be non-empty")
        status = item["status"]
        if status not in STATUSES:
            raise RegistryValidationError(f"{location}: invalid status")
        for field in ("authority", "introducing_commit", "lineage_ref", "origin"):
            if not isinstance(item[field], str) or not item[field]:
                raise RegistryValidationError(f"{location}: {field} must be non-empty")
        commit = item["introducing_commit"]
        if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
            raise RegistryValidationError(f"{location}: malformed introducing_commit")
        if type(item["on_main"]) is not bool:
            raise RegistryValidationError(f"{location}: on_main must be boolean")
        reconciliation = item["reconciliation_status"]
        if reconciliation not in RECONCILIATION_STATUSES:
            raise RegistryValidationError(f"{location}: invalid reconciliation_status")
        if status == "COLLISION_REPAIR" and reconciliation not in {
            "UNRESOLVED",
            "RESOLVED",
        }:
            raise RegistryValidationError(
                f"{location}: collision repair must be unresolved or resolved"
            )
        if status != "COLLISION_REPAIR" and reconciliation == "UNRESOLVED":
            raise RegistryValidationError(
                f"{location}: unresolved reconciliation requires COLLISION_REPAIR"
            )
        if any(start <= numeric_id <= end for start, end in blocked_ranges):
            raise RegistryValidationError(
                f"{location}: unexplained historical gap {ap_id} cannot be allocated"
            )
        identity = (ap_id, title, commit)
        if identity in identities:
            raise RegistryValidationError(f"{location}: duplicate registry record")
        identities.add(identity)
        key = (numeric_id, title, commit)
        if previous_key is not None and key <= previous_key:
            raise RegistryValidationError("allocations must use deterministic ordering")
        previous_key = key
        by_id.setdefault(ap_id, []).append(item)

    collision_ids = 0
    for ap_id, records in by_id.items():
        titles = {record["title"] for record in records}
        active = [
            record
            for record in records
            if record["status"] in {"RESERVED", "ALLOCATED"}
        ]
        if len(titles) > 1:
            collision_ids += 1
            if any(record["status"] != "COLLISION_REPAIR" for record in records):
                raise RegistryValidationError(
                    f"{ap_id}: colliding legacy titles must all be COLLISION_REPAIR"
                )
        if len({record["title"] for record in active}) > 1:
            raise RegistryValidationError(
                f"{ap_id}: duplicate global AP ID assigned to active titles"
            )
        if (
            any(
                record["status"] in {"SUPERSEDED", "COLLISION_REPAIR"}
                for record in records
            )
            and active
        ):
            raise RegistryValidationError(
                f"{ap_id}: repaired or superseded identity cannot be silently reused"
            )

    registered_headings = {(item["ap_id"], item["title"]) for item in allocations}
    headings = parse_decision_headings(decision_log_text)
    for heading in headings:
        if heading not in registered_headings:
            raise RegistryValidationError(
                f"decision log allocation lacks registry authority: {heading[0]} — {heading[1]}"
            )

    if baseline_registry is not None:
        baseline_allocations = baseline_registry.get("allocations")
        if not isinstance(baseline_allocations, list):
            raise RegistryValidationError("baseline registry has malformed allocations")
        baseline_repairs = {
            (item.get("ap_id"), item.get("title"), item.get("introducing_commit"))
            for item in baseline_allocations
            if item.get("status") in {"COLLISION_REPAIR", "SUPERSEDED"}
        }
        current_repairs = {
            (item["ap_id"], item["title"], item["introducing_commit"])
            for item in allocations
            if item["status"] in {"COLLISION_REPAIR", "SUPERSEDED"}
        }
        if current_repairs != baseline_repairs:
            raise RegistryValidationError(
                "post-cutover change to historical repair identities is prohibited"
            )
        baseline_by_id = {
            item["ap_id"]: item
            for item in baseline_allocations
            if item.get("status") in {"RESERVED", "ALLOCATED"}
        }
        for item in allocations:
            if item["status"] not in {"RESERVED", "ALLOCATED"}:
                continue
            prior = baseline_by_id.get(item["ap_id"])
            if prior is None:
                if (
                    item["status"] == "RESERVED"
                    and (item["ap_id"], item["title"]) not in headings
                ):
                    continue
                raise RegistryValidationError(
                    f"{item['ap_id']}: permanent identity lacks prior main reservation"
                )
            if item["title"] != prior["title"]:
                raise RegistryValidationError(
                    f"{item['ap_id']}: reserved title does not match allocated title"
                )
            if prior["status"] == "ALLOCATED" and item["status"] != "ALLOCATED":
                raise RegistryValidationError(
                    f"{item['ap_id']}: allocated identity cannot return to reserved"
                )

    return RegistryReport(
        allocation_count=len(allocations),
        ap_id_count=len(by_id),
        collision_id_count=collision_ids,
        decision_heading_count=len(headings),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the central AYO AP registry."
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("docs/AYO_DECISION_ID_REGISTRY.json"),
    )
    parser.add_argument(
        "--decision-log", type=Path, default=Path("docs/AYO_DECISION_LOG.md")
    )
    parser.add_argument("--baseline-registry", type=Path)
    args = parser.parse_args(argv)
    try:
        registry = _load_json(args.registry)
        decision_text = args.decision_log.read_text(encoding="utf-8")
        baseline = (
            _load_json(args.baseline_registry) if args.baseline_registry else None
        )
        report = validate_registry(registry, decision_text, baseline_registry=baseline)
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
