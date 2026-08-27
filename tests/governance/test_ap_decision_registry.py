from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools.validate_ap_decision_registry import (
    AP_099_PURPOSE,
    AP_099_TITLE,
    AP_100_PURPOSE,
    AP_100_TITLE,
    APPROVED_MANIFEST_ONLY,
    RegistryValidationError,
    effective_reconciliation_status,
    event_id,
    historical_composite_commitment,
    manifest_entry_id,
    reconciliation_id,
    validate_authorized_forward_reservation,
    validate_registry,
)

BASE = "a" * 40
COMMITS = {BASE, "b" * 40, "c" * 40, "d" * 40}


def allocation(
    ap_id="AP-079",
    title="SYNTHETIC LEGACY",
    *,
    status="COLLISION_REPAIR",
    commit="b" * 40,
    reconciliation="UNRESOLVED",
) -> dict[str, Any]:
    return {
        "ap_id": ap_id,
        "title": title,
        "status": status,
        "authority": "SYNTHETIC_TEST_AUTHORITY",
        "introducing_commit": commit,
        "lineage_ref": "refs/heads/synthetic-test",
        "on_main": True,
        "origin": "SYNTHETIC_TEST_ONLY",
        "reconciliation_status": reconciliation,
    }


def registry(*records: dict[str, Any], schema=2) -> dict[str, Any]:
    value = {
        "schema_version": schema,
        "registry_namespace": "ayo.governance.ap_decision_ids",
        "serialization_authority": "GIT_MAIN",
        "cutover": {
            "cutover_id": "AYO_AP_REGISTRY_V1",
            "approved_date": "2026-08-26",
            "activation": "ON_REGISTRY_INCLUSION_IN_MAIN",
            "status": "ACTIVE",
            "founder_approval": "APPROVED",
            "cto_approval": "APPROVED",
        },
        "blocked_unexplained_ranges": [],
        "allocations": list(records),
    }
    if schema == 2:
        value.update(forward_identity_events=[], collision_reconciliations=[])
    return value


def heading(item: dict[str, Any]) -> str:
    return f"### {item['ap_id']} — {item['title']}\n"


def exists(sha: str) -> bool:
    return sha in COMMITS


def metadata(sha: str) -> dict[str, Any] | None:
    return (
        {"tree": "e" * 40, "parents": [], "subject": "SYNTHETIC"}
        if exists(sha)
        else None
    )


def chunks(value: str) -> list[str]:
    return [value[i : i + 8] for i in range(0, len(value), 8)]


def _repository_metadata(root: Path, sha: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%T%x00%P%x00%s", sha],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        return None
    tree, parents, subject = result.stdout.rstrip("\n").split("\0", 2)
    return {
        "tree": tree,
        "parents": parents.split() if parents else [],
        "subject": subject,
    }


def provenance(value: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for commit in sorted({item["introducing_commit"] for item in value["allocations"]}):
        identities = [
            {
                "ap_id": item["ap_id"],
                "exact_title": item["title"],
                "historical_composite_id": chunks(
                    historical_composite_commitment(
                        commit, item["ap_id"], item["title"]
                    )
                ),
            }
            for item in value["allocations"]
            if item["introducing_commit"] == commit
        ]
        entry = {
            "introducing_commit": chunks(commit),
            "commit_tree": chunks("e" * 40),
            "parent_shas": [],
            "commit_subject": "SYNTHETIC",
            "historical_identities": identities,
            "governed_lineage": "refs/heads/synthetic-test",
            "provenance_class": "MAIN_REACHABLE",
            "live_object_requirement": "REQUIRED",
            "authority": "SYNTHETIC_TEST_AUTHORITY",
            "manifest_entry_id": "",
        }
        entry["manifest_entry_id"] = chunks(manifest_entry_id(entry))
        entries.append(entry)
    return {
        "schema_version": 1,
        "namespace": "ayo.governance.ap_historical_provenance",
        "cutover": {
            "base_main_commit": chunks("dc564949c7d19e0384655251cb40bda3199ddace")
        },
        "authority_model": {
            "primary_authority": "MAIN_RESIDENT_IMMUTABLE_MANIFEST",
            "post_cutover_manifest_only": "PROHIBITED",
        },
        "entries": entries,
    }


def event(
    kind="RESERVED",
    ap_id="AP-101",
    title="SYNTHETIC FORWARD",
    purpose="SYNTHETIC PURPOSE",
    prior=None,
    base=BASE,
) -> dict[str, Any]:
    item = {
        "event_id": "",
        "event_type": kind,
        "ap_id": ap_id,
        "title": title,
        "purpose": purpose,
        "base_main_commit": base,
        "prior_event_id": prior,
        "authority": "FOUNDER_AND_CTO_APPROVED",
        "approved_date": "2026-08-27",
    }
    item["event_id"] = event_id(item)
    return item


def reconciliation(
    legacy: dict[str, Any], successor: dict[str, Any], base=BASE
) -> dict[str, Any]:
    item = {
        "reconciliation_id": "",
        "historical_introducing_commit": legacy["introducing_commit"],
        "historical_ap_id": legacy["ap_id"],
        "historical_title": legacy["title"],
        "historical_composite_commitment": historical_composite_commitment(
            legacy["introducing_commit"], legacy["ap_id"], legacy["title"]
        ),
        "successor_ap_id": successor["ap_id"],
        "successor_title": successor["title"],
        "successor_allocation_event_id": successor["event_id"],
        "base_main_commit": base,
        "authority": "FOUNDER_AND_CTO_APPROVED",
        "approved_date": "2026-08-27",
    }
    item["reconciliation_id"] = reconciliation_id(item)
    return item


def validate(value: dict[str, Any], text="", baseline=None, **kwargs: Any):
    main_reachable = kwargs.pop(
        "main_reachable",
        lambda sha, authoritative_main: sha == authoritative_main == BASE,
    )
    durable_ref_reachable = kwargs.pop("durable_ref_reachable", lambda _sha: False)
    return validate_registry(
        value,
        text,
        baseline_registry=baseline,
        baseline_main_commit=BASE,
        commit_exists=exists,
        main_reachable=main_reachable,
        durable_ref_reachable=durable_ref_reachable,
        provenance_manifest=provenance(value),
        resolve_commit=metadata,
        **kwargs,
    )


def test_schema_v2_empty_lifecycle_is_deterministic() -> None:
    item = allocation(status="ALLOCATED", reconciliation="NOT_REQUIRED")
    first = validate(registry(item), heading(item))
    second = validate(copy.deepcopy(registry(item)), heading(item))
    assert first == second and (
        first.forward_event_count,
        first.reconciliation_count,
    ) == (0, 0)


def test_historical_composite_commitment_is_exact_and_non_recursive() -> None:
    introducing_commit = "".join(
        ("32716a1c", "834ca24e", "3237966c", "53532886", "afa558fe")
    )
    expected = "".join(
        (
            "2abd8f95",
            "aabccffb",
            "2029ace4",
            "c99ad3bc",
            "890da513",
            "6b706f22",
            "0ae56a4e",
            "acd56689",
        )
    )
    assert (
        historical_composite_commitment(
            introducing_commit,
            "AP-079",
            "Founder Institutional Discovery Phase 5 Preservation Foundation",
        )
        == expected
    )


def test_event_ids_reproduce_and_tampering_fails() -> None:
    item = event()
    assert item["event_id"] == event_id(item)
    item["title"] = "DRIFT"
    with pytest.raises(RegistryValidationError, match="event_id"):
        validate({**registry(allocation()), "forward_identity_events": [item]})


def test_reservation_and_later_allocation_require_baseline_main() -> None:
    legacy = allocation()
    reserved = event()
    baseline = registry(legacy)
    baseline["forward_identity_events"] = [reserved]
    allocated = event("ALLOCATED", prior=reserved["event_id"])
    candidate = copy.deepcopy(baseline)
    candidate["forward_identity_events"].append(allocated)
    validate(candidate, heading(allocated), baseline)

    with pytest.raises(
        RegistryValidationError, match="exactly one decision-log heading"
    ):
        validate(candidate, "", baseline)
    with pytest.raises(
        RegistryValidationError, match="exactly one decision-log heading"
    ):
        validate(candidate, heading(allocated) * 2, baseline)
    with pytest.raises(RegistryValidationError, match="lacks registry authority"):
        validate(candidate, "### AP-101 — WRONG TITLE\n", baseline)
    empty = registry(legacy)
    manufactured = copy.deepcopy(empty)
    manufactured["forward_identity_events"] = [reserved, allocated]
    with pytest.raises(
        RegistryValidationError, match="prior baseline-main reservation"
    ):
        validate(manufactured, heading(allocated), empty)


def test_allocation_title_mismatch_and_circular_chain_fail() -> None:
    legacy = allocation()
    reserved = event()
    baseline = registry(legacy)
    baseline["forward_identity_events"] = [reserved]
    wrong = event("ALLOCATED", title="WRONG", prior=reserved["event_id"])
    candidate = copy.deepcopy(baseline)
    candidate["forward_identity_events"].append(wrong)
    with pytest.raises(RegistryValidationError, match="title or purpose"):
        validate(candidate, heading(wrong), baseline)
    circular = event()
    circular["prior_event_id"] = circular["event_id"]
    circular["event_id"] = event_id(circular)
    with pytest.raises(RegistryValidationError, match="start a new identity chain"):
        validate({**registry(legacy), "forward_identity_events": [circular]})


def test_reconciliation_requires_prior_authoritative_allocation() -> None:
    legacy = allocation()
    reserved = event()
    allocated = event("ALLOCATED", prior=reserved["event_id"])
    baseline = registry(legacy)
    baseline["forward_identity_events"] = [reserved, allocated]
    item = reconciliation(legacy, allocated)
    candidate = copy.deepcopy(baseline)
    candidate["collision_reconciliations"] = [item]
    validate(candidate, heading(allocated), baseline)
    assert effective_reconciliation_status(legacy, [item]) == "RESOLVED"
    empty = registry(legacy)
    no_prior = copy.deepcopy(empty)
    no_prior["forward_identity_events"] = [reserved, allocated]
    no_prior["collision_reconciliations"] = [item]
    with pytest.raises(RegistryValidationError, match="prior baseline-main"):
        validate(no_prior, heading(allocated), empty)

    malformed = copy.deepcopy(item)
    malformed["historical_composite_commitment"] = "0" * 64
    malformed["reconciliation_id"] = reconciliation_id(malformed)
    candidate["collision_reconciliations"] = [malformed]
    with pytest.raises(RegistryValidationError, match="composite commitment"):
        validate(candidate, heading(allocated), baseline)


def test_unresolved_and_resolved_unrelated_collisions_coexist() -> None:
    first = allocation(title="FIRST", commit="b" * 40)
    second = allocation(title="SECOND", commit="c" * 40)
    reserved = event()
    allocated = event("ALLOCATED", prior=reserved["event_id"])
    baseline = registry(first, second)
    baseline["forward_identity_events"] = [reserved, allocated]
    item = reconciliation(first, allocated)
    candidate = copy.deepcopy(baseline)
    candidate["collision_reconciliations"] = [item]
    validate(candidate, heading(first) + heading(second) + heading(allocated), baseline)
    assert (
        effective_reconciliation_status(first, [item]) == "RESOLVED"
        and effective_reconciliation_status(second, [item]) == "UNRESOLVED"
    )


@pytest.mark.parametrize("mutation", ["status", "title", "delete"])
def test_bootstrap_history_is_frozen_byte_for_byte(mutation: str) -> None:
    legacy = allocation()
    baseline = registry(legacy)
    candidate = copy.deepcopy(baseline)
    if mutation == "delete":
        candidate["allocations"].clear()
    elif mutation == "status":
        candidate["allocations"][0]["reconciliation_status"] = "RESOLVED"
    else:
        candidate["allocations"][0]["title"] = "DRIFT"
    with pytest.raises(
        RegistryValidationError, match="bootstrap allocation mutation|non-empty array"
    ):
        validate(candidate, baseline=baseline)


def test_missing_historical_commit_is_rejected() -> None:
    with pytest.raises(RegistryValidationError, match="unavailable"):
        validate(registry(allocation(commit="f" * 40)))


@pytest.mark.parametrize("kind", ["UNKNOWN", "reserved", ""])
def test_unsupported_event_type_is_rejected(kind: str) -> None:
    item = event()
    item["event_type"] = kind
    item["event_id"] = event_id(item)
    with pytest.raises(RegistryValidationError, match="unsupported event type"):
        validate({**registry(allocation()), "forward_identity_events": [item]})


def test_blocked_range_and_active_id_reuse_are_rejected() -> None:
    value = registry(allocation())
    value["blocked_unexplained_ranges"] = [{"start": 101, "end": 101, "reason": "TEST"}]
    value["forward_identity_events"] = [event(ap_id="AP-101")]
    with pytest.raises(RegistryValidationError, match="blocked AP range"):
        validate(value)
    value = registry(allocation())
    value["forward_identity_events"] = [event(ap_id="AP-079")]
    with pytest.raises(RegistryValidationError, match="historical AP ID"):
        validate(value)


def test_duplicate_event_and_reconciliation_ids_are_rejected() -> None:
    legacy = allocation()
    reserved = event()
    value = registry(legacy)
    value["forward_identity_events"] = [reserved, copy.deepcopy(reserved)]
    with pytest.raises(
        RegistryValidationError, match="duplicate event_id|new identity chain"
    ):
        validate(value)
    allocated = event("ALLOCATED", prior=reserved["event_id"])
    value = registry(legacy)
    value["forward_identity_events"] = [reserved, allocated]
    item = reconciliation(legacy, allocated)
    value["collision_reconciliations"] = [item, copy.deepcopy(item)]
    with pytest.raises(
        RegistryValidationError,
        match="duplicate reconciliation_id|mapped more than once",
    ):
        validate(value, heading(allocated))


def test_one_successor_cannot_reconcile_two_historical_composites() -> None:
    first = allocation(title="FIRST", commit="b" * 40)
    second = allocation(title="SECOND", commit="c" * 40)
    reserved = event()
    allocated = event("ALLOCATED", prior=reserved["event_id"])
    baseline = registry(first, second)
    baseline["forward_identity_events"] = [reserved, allocated]
    candidate = copy.deepcopy(baseline)
    candidate["collision_reconciliations"] = [
        reconciliation(first, allocated),
        reconciliation(second, allocated),
    ]
    with pytest.raises(RegistryValidationError, match="successor mapped"):
        validate(
            candidate, heading(first) + heading(second) + heading(allocated), baseline
        )


def test_reconciliation_rejects_superseded_successor() -> None:
    legacy = allocation()
    reserved = event()
    allocated = event("ALLOCATED", prior=reserved["event_id"])
    superseded = event("SUPERSEDED", prior=allocated["event_id"])
    baseline = registry(legacy)
    baseline["forward_identity_events"] = [reserved, allocated, superseded]
    validate(baseline, heading(allocated))
    candidate = copy.deepcopy(baseline)
    candidate["collision_reconciliations"] = [reconciliation(legacy, allocated)]
    with pytest.raises(RegistryValidationError, match="superseded"):
        validate(candidate, heading(allocated), baseline)


def test_reservation_has_no_heading_or_allocation_authority() -> None:
    legacy = allocation()
    reserved = event()
    candidate = registry(legacy)
    candidate["forward_identity_events"] = [reserved]
    validate(candidate)
    with pytest.raises(
        RegistryValidationError,
        match="lacks registry authority|reservation has an allocation heading",
    ):
        validate(candidate, heading(reserved))


def test_exact_future_reservation_authorizations_only() -> None:
    for ap_id, title, purpose in (
        ("AP-099", AP_099_TITLE, AP_099_PURPOSE),
        ("AP-100", AP_100_TITLE, AP_100_PURPOSE),
    ):
        validate_authorized_forward_reservation(
            event(ap_id=ap_id, title=title, purpose=purpose)
        )
    with pytest.raises(RegistryValidationError, match="exact AP-099/AP-100"):
        validate_authorized_forward_reservation(event(ap_id="AP-101"))


@pytest.mark.parametrize("kind", ["RESERVED", "ALLOCATED"])
@pytest.mark.parametrize("ap_id", ["AP-099", "AP-100"])
def test_enablement_candidate_rejects_future_identity_instantiation(
    ap_id: str, kind: str
) -> None:
    reserved = event("RESERVED", ap_id=ap_id)
    events = [reserved]
    if kind == "ALLOCATED":
        events.append(event("ALLOCATED", ap_id=ap_id, prior=reserved["event_id"]))
    value = registry(allocation())
    value["forward_identity_events"] = events
    with pytest.raises(RegistryValidationError, match="cannot instantiate"):
        validate(value, enablement_only=True)


@pytest.mark.parametrize("kind", ["RESERVED", "ALLOCATED"])
def test_forward_lifecycle_authority_is_required(kind: str) -> None:
    reserved = event()
    item = (
        reserved
        if kind == "RESERVED"
        else event("ALLOCATED", prior=reserved["event_id"])
    )
    item["authority"] = ""
    item["event_id"] = event_id(item)
    value = registry(allocation())
    value["forward_identity_events"] = (
        [reserved] if kind == "RESERVED" else [reserved, item]
    )
    with pytest.raises(RegistryValidationError, match="authority"):
        validate(value)


def test_mission2_workflow_binds_base_and_rejects_phase5_paths() -> None:
    workflow = (
        Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")
    exact_base = "".join(("dc564949", "c7d19e03", "84655251", "cb40bda3", "199ddace"))
    start = workflow.index(f"base={exact_base}")
    contract = workflow[start : workflow.index("          fi", start)]
    assert f"base={exact_base}" in contract
    assert 'git merge-base "$head" refs/remotes/origin/main' in contract
    assert 'base="$(git merge-base' not in contract
    registry_blob = "".join(
        ("2ffb2cfb", "9f6ac410", "cf4f75a7", "b4460ea9", "5fc117c2")
    )
    assert registry_blob in contract
    assert "'^institutional/founder-discovery/phase-5/'" in workflow

    resolver = workflow.index(
        'elif [[ "$EVIDENCE_MODE" == ap-decision-registry-reconciliation-enablement ]]'
    )
    generic = workflow.index(
        'elif [[ -n "$EVENT_BEFORE" && "$EVENT_BEFORE" != "$zero" ]]'
    )
    route = workflow[resolver:generic]
    assert resolver < generic
    assert f"b={exact_base}" in route
    assert 'comparison_sha="$b"' in route
    assert "mode=verified-ap-registry-reconciliation-enablement-base" in route
    assert 'comparison_sha="$EVENT_BEFORE"' not in route


def test_committed_registry_preserves_bootstrap_and_has_no_lifecycle_instances() -> (
    None
):
    root = Path(__file__).parents[2]
    value = json.loads(
        (root / "docs/AYO_DECISION_ID_REGISTRY.json").read_text(encoding="utf-8")
    )
    text = (root / "docs/AYO_DECISION_LOG.md").read_text(encoding="utf-8")
    manifest = json.loads(
        (root / "docs/AYO_AP_HISTORICAL_PROVENANCE.json").read_text(encoding="utf-8")
    )
    report = validate_registry(
        value,
        text,
        commit_exists=lambda sha: (
            subprocess.run(
                ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                cwd=root,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        ),
        provenance_manifest=manifest,
        resolve_commit=lambda sha: _repository_metadata(root, sha),
    )
    assert (report.allocation_count, report.ap_id_count, report.collision_id_count) == (
        66,
        51,
        13,
    )
    assert value["forward_identity_events"] == value["collision_reconciliations"] == []
    assert all(
        item["ap_id"] not in {"AP-099", "AP-100"} for item in value["allocations"]
    )


def test_repository_candidate_uses_authoritative_main_baseline() -> None:
    root = Path(__file__).parents[2]
    value = json.loads(
        (root / "docs/AYO_DECISION_ID_REGISTRY.json").read_text(encoding="utf-8")
    )
    text = (root / "docs/AYO_DECISION_LOG.md").read_text(encoding="utf-8")
    manifest = json.loads(
        (root / "docs/AYO_AP_HISTORICAL_PROVENANCE.json").read_text(encoding="utf-8")
    )
    result = subprocess.run(
        ["git", "show", "refs/remotes/origin/main:docs/AYO_DECISION_ID_REGISTRY.json"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    baseline = json.loads(result.stdout)
    validate_registry(
        value,
        text,
        baseline_registry=baseline,
        baseline_main_commit="".join(
            ("dc564949", "c7d19e03", "84655251", "cb40bda3", "199ddace")
        ),
        commit_exists=lambda _: True,
        provenance_manifest=manifest,
        resolve_commit=lambda sha: _repository_metadata(root, sha),
    )
    assert value["allocations"] == baseline["allocations"]


@pytest.mark.parametrize("field", ["commit_tree", "parent_shas", "commit_subject"])
def test_manifest_rejects_live_object_metadata_mismatch(field: str) -> None:
    value = registry(allocation())
    manifest = provenance(value)
    entry = manifest["entries"][0]
    entry[field] = {
        "commit_tree": chunks("f" * 40),
        "parent_shas": [chunks("f" * 40)],
        "commit_subject": "DRIFT",
    }[field]
    entry["manifest_entry_id"] = chunks(manifest_entry_id(entry))
    with pytest.raises(RegistryValidationError, match="disagrees"):
        validate_registry(
            value,
            "",
            commit_exists=exists,
            provenance_manifest=manifest,
            resolve_commit=metadata,
        )


def test_manifest_rejects_unapproved_unavailable_object() -> None:
    value = registry(allocation(commit="f" * 40))
    manifest = provenance(value)
    entry = manifest["entries"][0]
    entry["provenance_class"] = "HISTORICAL_MANIFEST_ONLY"
    entry["live_object_requirement"] = "APPROVED_PRE_CUTOVER_EXCEPTION"
    entry["manifest_entry_id"] = chunks(manifest_entry_id(entry))
    with pytest.raises(RegistryValidationError, match="approved exception"):
        validate_registry(
            value,
            "",
            commit_exists=exists,
            provenance_manifest=manifest,
            resolve_commit=metadata,
        )


def test_manifest_rejects_identity_and_entry_id_drift() -> None:
    value = registry(allocation())
    manifest = provenance(value)
    manifest["entries"][0]["historical_identities"][0]["exact_title"] = "DRIFT"
    with pytest.raises(RegistryValidationError, match="composite"):
        validate_registry(
            value,
            "",
            provenance_manifest=manifest,
            resolve_commit=metadata,
        )


@pytest.mark.parametrize("mutation", ["delete", "duplicate", "lineage", "class"])
def test_manifest_is_complete_unique_and_immutable(mutation: str) -> None:
    value = registry(allocation())
    manifest = provenance(value)
    baseline = copy.deepcopy(manifest)
    if mutation == "delete":
        manifest["entries"] = []
    elif mutation == "duplicate":
        manifest["entries"].append(copy.deepcopy(manifest["entries"][0]))
    elif mutation == "lineage":
        manifest["entries"][0]["governed_lineage"] = "refs/heads/substitute"
    else:
        manifest["entries"][0]["provenance_class"] = "REMOTE_REF_REACHABLE"
    with pytest.raises(RegistryValidationError):
        validate_registry(
            value,
            "",
            provenance_manifest=manifest,
            baseline_provenance_manifest=baseline,
            resolve_commit=metadata,
        )


def test_committed_manifest_uniformly_covers_bootstrap_history() -> None:
    root = Path(__file__).parents[2]
    value = json.loads(
        (root / "docs/AYO_DECISION_ID_REGISTRY.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (root / "docs/AYO_AP_HISTORICAL_PROVENANCE.json").read_text(encoding="utf-8")
    )
    assert len(manifest["entries"]) == 34
    assert {entry["provenance_class"] for entry in manifest["entries"]} == {
        "MAIN_REACHABLE",
        "REMOTE_REF_REACHABLE",
        "HISTORICAL_MANIFEST_ONLY",
    }
    assert (
        sum(
            entry["provenance_class"] == "HISTORICAL_MANIFEST_ONLY"
            for entry in manifest["entries"]
        )
        == 2
    )
    assert sum(
        len(entry["historical_identities"]) for entry in manifest["entries"]
    ) == len(value["allocations"])
    manifest_only = {
        "".join(entry["introducing_commit"]): entry["governed_lineage"]
        for entry in manifest["entries"]
        if entry["provenance_class"] == "HISTORICAL_MANIFEST_ONLY"
    }
    assert manifest_only == APPROVED_MANIFEST_ONLY


@pytest.mark.parametrize("sha", sorted(APPROVED_MANIFEST_ONLY))
def test_committed_manifest_only_orphans_are_approved_when_unavailable(
    sha: str,
) -> None:
    root = Path(__file__).parents[2]
    value = json.loads(
        (root / "docs/AYO_DECISION_ID_REGISTRY.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (root / "docs/AYO_AP_HISTORICAL_PROVENANCE.json").read_text(encoding="utf-8")
    )
    validate_registry(
        value,
        (root / "docs/AYO_DECISION_LOG.md").read_text(encoding="utf-8"),
        provenance_manifest=manifest,
        resolve_commit=lambda candidate: (
            None if candidate == sha else _repository_metadata(root, candidate)
        ),
    )


@pytest.mark.parametrize(
    "lineage",
    [
        "agent/mobile-booking-consent-founder-consultation-preferences",
        "refs/heads/agent/wrong-branch",
        "refs/tags/agent/mobile-booking-consent-founder-consultation-preferences",
        "refs/remotes/origin/agent/mobile-booking-consent-founder-consultation-preferences",
        "refs/heads/refs/heads/agent/mobile-booking-consent-founder-consultation-preferences",
        "refs/heads/agent//mobile-booking-consent-founder-consultation-preferences",
        "refs/heads/agent/founder-institutional-discovery-phase5-foundation",
    ],
)
def test_manifest_only_exception_rejects_noncanonical_or_wrong_lineage(
    lineage: str,
) -> None:
    root = Path(__file__).parents[2]
    value = json.loads(
        (root / "docs/AYO_DECISION_ID_REGISTRY.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (root / "docs/AYO_AP_HISTORICAL_PROVENANCE.json").read_text(encoding="utf-8")
    )
    sha = next(iter(APPROVED_MANIFEST_ONLY))
    entry = next(
        item
        for item in manifest["entries"]
        if "".join(item["introducing_commit"]) == sha
    )
    entry["governed_lineage"] = lineage
    entry["manifest_entry_id"] = chunks(manifest_entry_id(entry))
    with pytest.raises(RegistryValidationError, match="approved exception"):
        validate_registry(
            value,
            (root / "docs/AYO_DECISION_LOG.md").read_text(encoding="utf-8"),
            provenance_manifest=manifest,
            resolve_commit=lambda candidate: (
                None if candidate == sha else _repository_metadata(root, candidate)
            ),
        )


def test_post_cutover_event_requires_live_git_authority() -> None:
    value = registry(allocation())
    value["forward_identity_events"] = [event(base="f" * 40)]
    with pytest.raises(RegistryValidationError, match="does not exist"):
        validate_registry(
            value,
            "",
            commit_exists=exists,
            provenance_manifest=provenance(value),
            resolve_commit=metadata,
        )


def test_manifest_only_orphan_cannot_authorize_post_cutover_lifecycle() -> None:
    orphan = "".join(("20b81a0e", "4f4e0606", "0525a33f", "3a5f1c76", "7f4b88f7"))
    value = registry(allocation())
    value["forward_identity_events"] = [event(base=orphan)]
    with pytest.raises(RegistryValidationError, match="governed reachability"):
        validate_registry(
            value,
            "",
            baseline_main_commit=BASE,
            commit_exists=lambda _sha: True,
            main_reachable=lambda _sha, _main: False,
            durable_ref_reachable=lambda _sha: False,
            provenance_manifest=provenance(value),
            resolve_commit=metadata,
        )


def test_arbitrary_live_object_and_wrong_main_are_rejected() -> None:
    arbitrary = "f" * 40
    value = registry(allocation())
    value["forward_identity_events"] = [event(base=arbitrary)]
    with pytest.raises(RegistryValidationError, match="governed reachability"):
        validate_registry(
            value,
            "",
            baseline_main_commit=BASE,
            commit_exists=lambda _sha: True,
            main_reachable=lambda _sha, main: main == "c" * 40,
            durable_ref_reachable=lambda _sha: False,
            provenance_manifest=provenance(value),
            resolve_commit=metadata,
        )


@pytest.mark.parametrize("source", ["main", "durable"])
def test_post_cutover_governed_reachability_is_accepted(source: str) -> None:
    value = registry(allocation())
    value["forward_identity_events"] = [event()]
    validate(
        value,
        main_reachable=lambda sha, main: source == "main" and sha == main == BASE,
        durable_ref_reachable=lambda sha: source == "durable" and sha == BASE,
    )


def _bandit_inventory(evidence: dict[str, Any]) -> tuple[list[str], str]:
    rows = sorted(
        "|".join(
            (
                item["test_id"],
                item["issue_severity"],
                item["issue_confidence"],
                item["filename"].replace("\\", "/").lstrip("./"),
                item["issue_text"],
            )
        )
        for item in evidence["results"]
    )
    return rows, hashlib.sha256("\n".join(rows).encode()).hexdigest()


def _validate_bandit_evidence(evidence: dict[str, Any], expected: str) -> None:
    findings = evidence["results"]
    rows, actual = _bandit_inventory(evidence)
    totals = evidence["metrics"]["_totals"]
    assert len(findings) == 3
    assert sorted(item["test_id"] for item in findings) == ["B404", "B603", "B607"]
    assert {
        (item["issue_severity"], item["issue_confidence"]) for item in findings
    } == {("LOW", "HIGH")}
    assert actual == expected and len(rows) == 3
    assert totals["nosec"] == totals["skipped_tests"] == 0
    assert totals["SEVERITY.MEDIUM"] == totals["SEVERITY.HIGH"] == 0


def test_validator_bandit_inventory_is_exact() -> None:
    root = Path(__file__).parents[2]
    result = subprocess.run(
        [
            "bandit",
            "-c",
            "pyproject.toml",
            "-f",
            "json",
            "-q",
            "tools/validate_ap_decision_registry.py",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    evidence = json.loads(result.stdout)
    assert result.returncode == 1
    expected = "".join(
        (
            "08e68f3b",
            "b3f9d1e9",
            "c7ea85b5",
            "146c0038",
            "0ece5f27",
            "4ae97325",
            "14986e7e",
            "b8875c7f",
        )
    )
    _validate_bandit_evidence(evidence, expected)
    assert (
        "# nosec"
        not in (root / "tools/validate_ap_decision_registry.py")
        .read_text(encoding="utf-8")
        .lower()
    )


def test_bandit_evidence_drift_is_rejected() -> None:
    result = subprocess.run(
        [
            "bandit",
            "-c",
            "pyproject.toml",
            "-f",
            "json",
            "-q",
            "tools/validate_ap_decision_registry.py",
        ],
        cwd=Path(__file__).parents[2],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    pristine = json.loads(result.stdout)
    _, expected = _bandit_inventory(pristine)
    mutations = []
    for field, value in (
        ("issue_severity", "MEDIUM"),
        ("issue_confidence", "MEDIUM"),
        ("issue_text", "DRIFT"),
    ):
        item = copy.deepcopy(pristine)
        item["results"][0][field] = value
        mutations.append(item)
    missing = copy.deepcopy(pristine)
    missing["results"].pop()
    mutations.append(missing)
    fourth = copy.deepcopy(pristine)
    fourth["results"].append(copy.deepcopy(fourth["results"][0]))
    mutations.append(fourth)
    suppressed = copy.deepcopy(pristine)
    suppressed["metrics"]["_totals"]["nosec"] = 1
    mutations.append(suppressed)
    elevated = copy.deepcopy(pristine)
    elevated["metrics"]["_totals"]["SEVERITY.HIGH"] = 1
    mutations.append(elevated)
    for evidence in mutations:
        with pytest.raises(AssertionError):
            _validate_bandit_evidence(evidence, expected)
