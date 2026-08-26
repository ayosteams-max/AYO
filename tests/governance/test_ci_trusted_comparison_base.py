"""Synthetic controls for the governed trusted-comparison-base contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NotRequired, TypedDict, cast

import pytest

ZERO = "0" * 40
PRIOR_BASE = "a" * 40
AUTHORITATIVE_BASE = "b" * 40
HEAD = "c" * 40
W16 = "65ff7843" + "0315c2d1" + "0bc40a0f" + "3edafced" + "6cec3ad2"
COMMITS = {PRIOR_BASE, AUTHORITATIVE_BASE, HEAD, W16}


class ResolveArgs(TypedDict):
    event: str
    event_base: str
    expected_base: str
    first_parent: str
    merge_base: str
    ancestor: NotRequired[bool]


class ActiveArgs(TypedDict):
    evidence_mode: str
    base: str
    merge_base: str
    chain: tuple[str, ...]
    subjects: tuple[str, ...]
    commit_paths: tuple[tuple[str, ...], ...]
    aggregate_paths: tuple[str, ...]
    linear: NotRequired[bool]


class ClassifyArgs(TypedDict):
    predecessor: str
    content_base: str
    predecessor_is_ancestor: bool
    predecessor_descends_from_w16: bool
    head_descends_from_w16: bool
    changed_paths: list[str]
    protected_unchanged: bool
    reviewed_feature: bool


ACTIVE_MODE = "ap-registry-active-state-correction"
ACTIVE_BASE = "6b94c451" + "87af70f1" + "76d6a98d" + "40742187" + "ceaf43c8"
ACTIVE_STATE = "32775104" + "60b5af71" + "773dda62" + "a4db69cd" + "739433f3"
ACTIVE_ADMISSION = "8aa0664a" + "904384d3" + "697ab12c" + "d306a2f0" + "2f6fa8ea"
ACTIVE_BINDING = "5fe9b401" + "ae1ca421" + "8c40f1a2" + "7a8f1827" + "0fa7b461"
ACTIVE_SUBJECTS = (
    "governance: record active AP registry state",
    "ci: admit AP registry active-state correction",
    "ci: bind AP registry state push comparison base",
    "ci: extract trusted-base controls from workflow",
)
ACTIVE_PATHS = (
    ("docs/AYO_DECISION_ID_REGISTRY.json",),
    (".github/workflows/ci.yml",),
    (".github/workflows/ci.yml",),
    (
        ".github/workflows/ci.yml",
        "tests/governance/test_ci_trusted_comparison_base.py",
    ),
)
AGGREGATE_PATHS = (
    ".github/workflows/ci.yml",
    "docs/AYO_DECISION_ID_REGISTRY.json",
    "tests/governance/test_ci_trusted_comparison_base.py",
)


def _require_commit(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", value or "") or value == ZERO:
        raise ValueError("invalid comparison base")
    if value not in COMMITS:
        raise ValueError("unavailable comparison base")


def _resolve(
    *,
    event: str,
    event_base: str,
    expected_base: str,
    first_parent: str,
    merge_base: str,
    ancestor: bool = True,
) -> str:
    _require_commit(event_base)
    if not ancestor:
        raise ValueError("comparison base is not an ancestor")
    if event == "first-push" and not (
        event_base == expected_base == first_parent == merge_base
    ):
        raise ValueError("first-push base mismatch")
    if event == "pull-request" and event_base != expected_base:
        raise ValueError("pull-request base mismatch")
    if event == "subsequent-push" and event_base != first_parent:
        raise ValueError("push predecessor mismatch")
    if event == "dispatch" and event_base != first_parent:
        raise ValueError("dispatch first-parent mismatch")
    return event_base


def _consume(resolved: str, supplied: str) -> str:
    if supplied != resolved:
        raise ValueError("downstream trusted-base replacement")
    _require_commit(supplied)
    return supplied


def _resolve_active_state(
    *,
    evidence_mode: str,
    base: str,
    merge_base: str,
    chain: tuple[str, ...],
    subjects: tuple[str, ...],
    commit_paths: tuple[tuple[str, ...], ...],
    aggregate_paths: tuple[str, ...],
    linear: bool = True,
) -> str:
    if evidence_mode != ACTIVE_MODE:
        raise ValueError("unknown active-state evidence mode")
    if base != ACTIVE_BASE or merge_base != ACTIVE_BASE:
        raise ValueError("active-state authoritative base drift")
    if not linear or chain[:3] != (
        ACTIVE_STATE,
        ACTIVE_ADMISSION,
        ACTIVE_BINDING,
    ):
        raise ValueError("active-state reviewed chain drift")
    if len(chain) != 4:
        raise ValueError("active-state commit count drift")
    if subjects != ACTIVE_SUBJECTS or commit_paths != ACTIVE_PATHS:
        raise ValueError("active-state commit contract drift")
    if aggregate_paths != AGGREGATE_PATHS:
        raise ValueError("active-state aggregate path drift")
    return ACTIVE_BASE


def _classify(
    *,
    predecessor: str,
    content_base: str,
    predecessor_is_ancestor: bool,
    predecessor_descends_from_w16: bool,
    head_descends_from_w16: bool,
    changed_paths: list[str],
    protected_unchanged: bool,
    reviewed_feature: bool,
) -> tuple[str, str]:
    _require_commit(predecessor)
    _require_commit(content_base)
    if not predecessor_is_ancestor:
        raise ValueError("published predecessor is not an ancestor")
    workflow_authority = (
        content_base == W16
        and predecessor_descends_from_w16
        and head_descends_from_w16
        and changed_paths == [".github/workflows/ci.yml"]
        and protected_unchanged
    )
    if workflow_authority and reviewed_feature:
        raise ValueError("ambiguous trusted content classification")
    if workflow_authority:
        return "workflow-only-authority", content_base
    if reviewed_feature:
        return "reviewed-feature-content", content_base
    raise ValueError("unknown trusted content classification")


def test_workflow_uses_one_trusted_comparison_base_resolver() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    authoritative_mapping = (
        "TRUSTED_COMPARISON_BASE_SHA: "
        + "$"
        + "{{ steps.trusted_comparison_base.outputs.sha }}"
    )
    predecessor_mapping = (
        "PUBLISHED_PREDECESSOR_SHA: "
        + "$"
        + "{{ steps.trusted_comparison_base.outputs.sha }}"
    )
    resolver_id = "id: trusted_" + "comparison_base"
    headers = list(re.finditer(r"(?m)^      - name: (.+)$", workflow))
    blocks = [
        (
            match.group(1),
            workflow[
                match.start() : (
                    headers[index + 1].start()
                    if index + 1 < len(headers)
                    else len(workflow)
                )
            ],
        )
        for index, match in enumerate(headers)
    ]
    resolver_steps = [name for name, block in blocks if resolver_id in block]
    assert workflow.count(resolver_id) == 1
    assert resolver_steps == ["Resolve trusted comparison base"]

    expected_consumers = (
        "Bind exact Booking replay-equivalence candidate identity",
        "Bind exact Booking consent-policy-authority candidate identity",
        "Bind exact Mobile Booking intent foundation candidate identity",
        "Bind exact consent document architecture candidate identity",
        "Bind exact Booking consent approval-pack architecture candidate identity",
        "Test all admitted non-PostgreSQL behavior with coverage",
        "Verify exact Batch 2 test and coverage contract",
    )
    expected_predecessors = (
        "Bind tested Courier Pickup tree to trusted authoritative base",
        "Bind tested Courier Pickup authorization-ordering tree to trusted base",
    )
    consumers = tuple(name for name, block in blocks if authoritative_mapping in block)
    predecessors = tuple(name for name, block in blocks if predecessor_mapping in block)
    assert consumers == expected_consumers
    assert predecessors == expected_predecessors

    approval = dict(blocks)[
        "Bind exact Booking consent approval-pack architecture candidate identity"
    ]
    assert approval.count(authoritative_mapping) == 1
    assert approval.count("TRUSTED_COMPARISON_BASE_SHA:") == 1
    assert re.findall(r"steps\.([\w-]+)\.outputs\.sha", approval) == [
        "trusted_comparison_base"
    ]
    forbidden = (
        "COVERAGE_" + "COMPARE_SHA",
        "steps.coverage_" + "base.outputs.sha",
        "if compare_sha "
        + '!= "4eda7c5e'
        + "80907eba"
        + "9b60c20d"
        + "64561087"
        + 'ef50c84b"',
        "comparison_sha=" + '""',
        "dispatch Batch 2 target lacks " + "an exact first-parent base",
    )
    assert not any(value in workflow for value in forbidden)


@pytest.mark.parametrize(
    ("event", "event_base", "expected_base", "first_parent", "merge_base"),
    (
        (
            "first-push",
            AUTHORITATIVE_BASE,
            AUTHORITATIVE_BASE,
            AUTHORITATIVE_BASE,
            AUTHORITATIVE_BASE,
        ),
        (
            "pull-request",
            AUTHORITATIVE_BASE,
            AUTHORITATIVE_BASE,
            AUTHORITATIVE_BASE,
            AUTHORITATIVE_BASE,
        ),
        (
            "subsequent-push",
            AUTHORITATIVE_BASE,
            AUTHORITATIVE_BASE,
            AUTHORITATIVE_BASE,
            AUTHORITATIVE_BASE,
        ),
        ("dispatch", PRIOR_BASE, PRIOR_BASE, PRIOR_BASE, PRIOR_BASE),
    ),
)
def test_trusted_base_positive_controls(
    event: str,
    event_base: str,
    expected_base: str,
    first_parent: str,
    merge_base: str,
) -> None:
    resolved = _resolve(
        event=event,
        event_base=event_base,
        expected_base=expected_base,
        first_parent=first_parent,
        merge_base=merge_base,
    )
    assert _consume(resolved, resolved) == event_base


@pytest.mark.parametrize(
    "arguments",
    (
        dict(
            event="pull-request",
            event_base="",
            expected_base=AUTHORITATIVE_BASE,
            first_parent=AUTHORITATIVE_BASE,
            merge_base=AUTHORITATIVE_BASE,
        ),
        dict(
            event="pull-request",
            event_base="not-a-sha",
            expected_base=AUTHORITATIVE_BASE,
            first_parent=AUTHORITATIVE_BASE,
            merge_base=AUTHORITATIVE_BASE,
        ),
        dict(
            event="pull-request",
            event_base=ZERO,
            expected_base=AUTHORITATIVE_BASE,
            first_parent=AUTHORITATIVE_BASE,
            merge_base=AUTHORITATIVE_BASE,
        ),
        dict(
            event="pull-request",
            event_base="f" * 40,
            expected_base=AUTHORITATIVE_BASE,
            first_parent=AUTHORITATIVE_BASE,
            merge_base=AUTHORITATIVE_BASE,
        ),
        dict(
            event="first-push",
            event_base=PRIOR_BASE,
            expected_base=AUTHORITATIVE_BASE,
            first_parent=PRIOR_BASE,
            merge_base=AUTHORITATIVE_BASE,
        ),
        dict(
            event="pull-request",
            event_base=PRIOR_BASE,
            expected_base=AUTHORITATIVE_BASE,
            first_parent=AUTHORITATIVE_BASE,
            merge_base=AUTHORITATIVE_BASE,
        ),
        dict(
            event="subsequent-push",
            event_base=AUTHORITATIVE_BASE,
            expected_base=AUTHORITATIVE_BASE,
            first_parent=AUTHORITATIVE_BASE,
            merge_base=AUTHORITATIVE_BASE,
            ancestor=False,
        ),
        dict(
            event="subsequent-push",
            event_base=PRIOR_BASE,
            expected_base=AUTHORITATIVE_BASE,
            first_parent=AUTHORITATIVE_BASE,
            merge_base=AUTHORITATIVE_BASE,
        ),
    ),
)
def test_trusted_base_negative_controls(arguments: ResolveArgs) -> None:
    with pytest.raises(ValueError):
        _resolve(**arguments)


def test_downstream_replacement_is_rejected() -> None:
    with pytest.raises(ValueError):
        _consume(AUTHORITATIVE_BASE, PRIOR_BASE)


def _active_arguments() -> ActiveArgs:
    return {
        "evidence_mode": ACTIVE_MODE,
        "base": ACTIVE_BASE,
        "merge_base": ACTIVE_BASE,
        "chain": (ACTIVE_STATE, ACTIVE_ADMISSION, ACTIVE_BINDING, "d" * 40),
        "subjects": ACTIVE_SUBJECTS,
        "commit_paths": ACTIVE_PATHS,
        "aggregate_paths": AGGREGATE_PATHS,
    }


def test_active_state_topology_positive_control() -> None:
    assert _resolve_active_state(**_active_arguments()) == ACTIVE_BASE


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("chain", ("e" * 40, ACTIVE_STATE, ACTIVE_ADMISSION, ACTIVE_BINDING, "d" * 40)),
        ("chain", (ACTIVE_STATE, "e" * 40, ACTIVE_ADMISSION, ACTIVE_BINDING, "d" * 40)),
        ("chain", ("e" * 40, ACTIVE_ADMISSION, ACTIVE_BINDING, "d" * 40)),
        ("chain", (ACTIVE_STATE, "e" * 40, ACTIVE_BINDING, "d" * 40)),
        ("chain", (ACTIVE_STATE, ACTIVE_ADMISSION, "e" * 40, "d" * 40)),
        ("linear", False),
        ("base", "e" * 40),
        ("merge_base", "e" * 40),
        ("aggregate_paths", AGGREGATE_PATHS + ("unexpected",)),
        ("commit_paths", ACTIVE_PATHS[:3] + (("unexpected",),)),
        ("evidence_mode", "unknown"),
        ("subjects", ACTIVE_SUBJECTS[:3] + ("wrong subject",)),
    ),
)
def test_active_state_topology_negative_controls(key: str, value: object) -> None:
    arguments = cast(ActiveArgs, {**_active_arguments(), key: value})
    with pytest.raises(ValueError):
        _resolve_active_state(**arguments)


def test_trusted_content_classification_controls() -> None:
    workflow_evidence: ClassifyArgs = {
        "predecessor": AUTHORITATIVE_BASE,
        "content_base": W16,
        "predecessor_is_ancestor": True,
        "predecessor_descends_from_w16": True,
        "head_descends_from_w16": True,
        "changed_paths": [".github/workflows/ci.yml"],
        "protected_unchanged": True,
        "reviewed_feature": False,
    }
    assert _classify(**workflow_evidence) == ("workflow-only-authority", W16)
    feature: ClassifyArgs = {
        **workflow_evidence,
        "predecessor": PRIOR_BASE,
        "content_base": PRIOR_BASE,
        "predecessor_descends_from_w16": False,
        "head_descends_from_w16": False,
        "changed_paths": ["exact-reviewed-feature-content"],
        "protected_unchanged": False,
        "reviewed_feature": True,
    }
    assert _classify(**feature) == ("reviewed-feature-content", PRIOR_BASE)

    invalid: tuple[ClassifyArgs, ...] = (
        {**workflow_evidence, "content_base": PRIOR_BASE},
        {
            **workflow_evidence,
            "predecessor": PRIOR_BASE,
            "predecessor_descends_from_w16": False,
        },
        {**workflow_evidence, "predecessor_is_ancestor": False},
        {**workflow_evidence, "predecessor": ZERO},
        {**workflow_evidence, "predecessor_descends_from_w16": False},
        {
            **workflow_evidence,
            "changed_paths": [".github/workflows/ci.yml", "BACKEND/main.py"],
        },
        {
            **workflow_evidence,
            "changed_paths": [".github/workflows/ci.yml", "tests/test_app.py"],
        },
        {
            **workflow_evidence,
            "changed_paths": [
                ".github/workflows/ci.yml",
                "database/migrations/versions/changed.py",
            ],
        },
        {**workflow_evidence, "reviewed_feature": True},
        {**workflow_evidence, "changed_paths": []},
    )
    for evidence in invalid:
        with pytest.raises(ValueError):
            _classify(**evidence)


def test_classification_comparison_and_coverage_pairs() -> None:
    comparison_contract = {
        "workflow-only-authority": W16,
        "reviewed-feature-content": PRIOR_BASE,
        "courier-pickup-authorization-ordering": AUTHORITATIVE_BASE,
    }
    coverage_contract = {
        "workflow-only-authority": (0, 0),
        "reviewed-feature-content": (106, 0),
        "courier-pickup-authorization-ordering": (11, 0),
    }

    def verify_pair(classification: str, comparison_base: str) -> None:
        _require_commit(comparison_base)
        if comparison_contract.get(classification) != comparison_base:
            raise ValueError("classification/comparison-base pair mismatch")

    for classification, comparison_base in comparison_contract.items():
        verify_pair(classification, comparison_base)
    for classification, comparison_base in (
        ("workflow-only-authority", PRIOR_BASE),
        ("reviewed-feature-content", ""),
        ("courier-pickup-authorization-ordering", PRIOR_BASE),
        ("", W16),
        ("unknown", W16),
    ):
        with pytest.raises(ValueError):
            verify_pair(classification, comparison_base)

    invalid_coverage = (
        ("", (0, 0)),
        ("unknown", (0, 0)),
        ("reviewed-feature-content", (105, 0)),
        ("reviewed-feature-content", (106, 1)),
        ("courier-pickup-authorization-ordering", (10, 0)),
        ("courier-pickup-authorization-ordering", (11, 1)),
    )
    assert all(coverage_contract.get(mode) != value for mode, value in invalid_coverage)


def test_coverage_consumes_only_trusted_binding_outputs() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    binding = workflow[
        workflow.index("id: courier_pickup_v1_content") : workflow.index(
            "- name: Test all admitted non-PostgreSQL behavior"
        )
    ]
    for mutable_authority in (
        "github.ref",
        "github.event_name",
        "github.event.pull_request.number",
        "CONTENT_CLASSIFICATION",
    ):
        assert mutable_authority not in binding

    coverage = workflow[
        workflow.index(
            "- name: Verify exact Courier Pickup Idempotency V1 test and coverage contract"
        ) : workflow.index(
            "- name: Verify PostgreSQL 17/PostGIS integration tests without skips"
        )
    ]
    assert "steps.trusted_comparison_base.outputs.sha" not in coverage
    for output in (
        "outputs.content_classification",
        "outputs.content_comparison_base_sha",
    ):
        assert coverage.count(output) == 2
