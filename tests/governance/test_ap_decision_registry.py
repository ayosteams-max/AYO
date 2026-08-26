from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools.validate_ap_decision_registry import (
    RegistryValidationError,
    parse_decision_headings,
    validate_registry,
)


def allocation(
    ap_id: str = "AP-100",
    title: str = "SYNTHETIC GOVERNANCE TEST DECISION",
    *,
    status: str = "ALLOCATED",
    commit: str = "a" * 40,
    reconciliation: str = "NOT_REQUIRED",
) -> dict[str, Any]:
    return {
        "ap_id": ap_id,
        "title": title,
        "status": status,
        "authority": "SYNTHETIC_TEST_AUTHORITY",
        "introducing_commit": commit,
        "lineage_ref": "refs/heads/synthetic-test",
        "on_main": False,
        "origin": "SYNTHETIC_TEST_ONLY",
        "reconciliation_status": reconciliation,
    }


def registry(*records: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "registry_namespace": "ayo.governance.ap_decision_ids",
        "serialization_authority": "GIT_MAIN",
        "cutover": {
            "cutover_id": "AYO_AP_REGISTRY_V1",
            "approved_date": "2026-08-26",
            "activation": "ON_REGISTRY_INCLUSION_IN_MAIN",
            "status": "PENDING_MAIN_ACTIVATION",
            "founder_approval": "APPROVED",
            "cto_approval": "APPROVED",
        },
        "blocked_unexplained_ranges": [],
        "allocations": list(records),
    }


def heading(item: dict[str, Any]) -> str:
    return f"### {item['ap_id']} — {item['title']}\n"


def test_unique_valid_registry_passes_deterministically() -> None:
    item = allocation()
    value = registry(item)
    first = validate_registry(value, heading(item))
    second = validate_registry(copy.deepcopy(value), heading(item))
    assert first == second
    assert first.allocation_count == first.ap_id_count == 1
    assert first.collision_id_count == 0


def test_duplicate_active_ap_identity_fails() -> None:
    first = allocation(title="SYNTHETIC FIRST")
    second = allocation(title="SYNTHETIC SECOND", commit="b" * 40)
    with pytest.raises(RegistryValidationError, match="colliding legacy titles"):
        validate_registry(registry(first, second), heading(first))


def test_title_mismatch_and_unregistered_post_cutover_decision_fail() -> None:
    item = allocation()
    with pytest.raises(RegistryValidationError, match="lacks registry authority"):
        validate_registry(registry(item), "### AP-100 — DIFFERENT TITLE\n")
    with pytest.raises(RegistryValidationError, match="lacks registry authority"):
        validate_registry(registry(item), heading(item) + "### AP-101 — UNREGISTERED\n")


@pytest.mark.parametrize("ap_id", ["AP-1", "AP-ABC", "100", "AP_100"])
def test_malformed_id_fails(ap_id: str) -> None:
    item = allocation(ap_id=ap_id)
    with pytest.raises(RegistryValidationError, match="malformed AP identifier"):
        validate_registry(registry(item), "")


def test_historical_collision_is_preserved_without_becoming_active() -> None:
    first = allocation(
        title="SYNTHETIC LEGACY FIRST",
        status="COLLISION_REPAIR",
        reconciliation="UNRESOLVED",
    )
    second = allocation(
        title="SYNTHETIC LEGACY SECOND",
        status="COLLISION_REPAIR",
        commit="b" * 40,
        reconciliation="UNRESOLVED",
    )
    value = registry(first, second)
    report = validate_registry(value, heading(first) + heading(second))
    assert report.collision_id_count == 1
    assert parse_decision_headings(heading(first) + heading(second)) == (
        ("AP-100", "SYNTHETIC LEGACY FIRST"),
        ("AP-100", "SYNTHETIC LEGACY SECOND"),
    )


def test_repaired_or_superseded_identity_cannot_be_silently_reused() -> None:
    repaired = allocation(status="COLLISION_REPAIR", reconciliation="RESOLVED")
    reused = allocation(title="SYNTHETIC REUSE", commit="b" * 40)
    with pytest.raises(RegistryValidationError, match="colliding legacy titles"):
        validate_registry(registry(repaired, reused), heading(repaired))


def test_main_first_reservation_and_title_match_are_enforced() -> None:
    reserved = allocation(status="RESERVED")
    baseline = registry(reserved)
    allocated = copy.deepcopy(reserved)
    allocated["status"] = "ALLOCATED"
    validate_registry(
        registry(allocated), heading(allocated), baseline_registry=baseline
    )

    new_reservation = allocation(
        ap_id="AP-101", title="SYNTHETIC FUTURE RESERVATION", status="RESERVED"
    )
    validate_registry(
        registry(reserved, new_reservation),
        heading(reserved),
        baseline_registry=baseline,
    )

    unreserved = allocation(ap_id="AP-101", commit="b" * 40)
    with pytest.raises(RegistryValidationError, match="lacks prior main reservation"):
        validate_registry(
            registry(reserved, unreserved),
            heading(reserved) + heading(unreserved),
            baseline_registry=baseline,
        )

    mismatch = copy.deepcopy(allocated)
    mismatch["title"] = "SYNTHETIC DIFFERENT TITLE"
    with pytest.raises(RegistryValidationError, match="reserved title does not match"):
        validate_registry(
            registry(mismatch), heading(mismatch), baseline_registry=baseline
        )


def test_post_cutover_historical_repairs_are_frozen() -> None:
    repaired = allocation(status="COLLISION_REPAIR", reconciliation="UNRESOLVED")
    baseline = registry(repaired)
    changed = allocation(
        title="SYNTHETIC NEW REPAIR",
        status="COLLISION_REPAIR",
        commit="b" * 40,
        reconciliation="UNRESOLVED",
    )
    with pytest.raises(RegistryValidationError, match="historical repair identities"):
        validate_registry(
            registry(repaired, changed),
            heading(repaired) + heading(changed),
            baseline_registry=baseline,
        )


def test_committed_bootstrap_registry_matches_recoverable_decision_history() -> None:
    root = Path(__file__).parents[2]
    registry_value = json.loads(
        (root / "docs" / "AYO_DECISION_ID_REGISTRY.json").read_text(encoding="utf-8")
    )
    decision_text = (root / "docs" / "AYO_DECISION_LOG.md").read_text(encoding="utf-8")
    report = validate_registry(registry_value, decision_text)
    assert report.allocation_count == 66
    assert report.ap_id_count == 51
    assert report.collision_id_count == 13
    assert report.decision_heading_count == len(parse_decision_headings(decision_text))
    assert all(item["ap_id"] != "AP-099" for item in registry_value["allocations"])


def test_repository_registry_uses_main_as_serialization_authority() -> None:
    root = Path(__file__).parents[2]
    registry_path = root / "docs" / "AYO_DECISION_ID_REGISTRY.json"
    registry_value = json.loads(registry_path.read_text(encoding="utf-8"))
    decision_text = (root / "docs" / "AYO_DECISION_LOG.md").read_text(encoding="utf-8")
    result = subprocess.run(
        [
            "git",
            "show",
            "refs/remotes/origin/main:docs/AYO_DECISION_ID_REGISTRY.json",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        assert registry_value["cutover"]["status"] == "READY_FOR_MAIN_ACTIVATION"
        validate_registry(registry_value, decision_text)
        return

    baseline = json.loads(result.stdout)
    validate_registry(registry_value, decision_text, baseline_registry=baseline)
