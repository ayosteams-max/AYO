"""Synthetic controls for the governed trusted-comparison-base contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NotRequired, TypedDict, Unpack, cast

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


class MergeArgs(TypedDict):
    event: str
    ref: str
    before: str
    parents: tuple[str, ...]
    merge_tree: str
    feature_tree: str
    merge_base: str
    changed_paths: tuple[str, ...]
    registry_active: bool
    ap099_absent: bool
    phase5_absent: bool


class CorrectionArgs(TypedDict):
    context: str
    event: str
    ref: str
    before: str
    base: str
    parents: tuple[str, ...]
    second_parent_base: str
    subject: str
    commit_paths: tuple[str, ...]
    aggregate_paths: tuple[str, ...]
    head_tree: str
    second_parent_tree: str
    registry_active: bool
    ap099_absent: bool
    phase5_absent: bool
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


class PrResolverArgs(TypedDict):
    event: str
    ref: str
    mode: str
    base: str
    head: str
    checked_out_head: str
    reservation_validated: bool
    base_is_ancestor: NotRequired[bool]
    head_is_ancestor: NotRequired[bool]


ACTIVE_MODE = "ap-registry-active-state-correction"
ACTIVE_BASE = "6b94c451" + "87af70f1" + "76d6a98d" + "40742187" + "ceaf43c8"
ACTIVE_STATE = "32775104" + "60b5af71" + "773dda62" + "a4db69cd" + "739433f3"
ACTIVE_ADMISSION = "8aa0664a" + "904384d3" + "697ab12c" + "d306a2f0" + "2f6fa8ea"
ACTIVE_BINDING = "5fe9b401" + "ae1ca421" + "8c40f1a2" + "7a8f1827" + "0fa7b461"
ACTIVE_HEAD = "a6e4bb52" + "bf765e98" + "46c75b7b" + "32454aac" + "9c97453d"
ACTIVE_MERGE = "a765a3e6" + "c4a4e920" + "2fb4f1a7" + "70e5a5da" + "f2dec0b1"
ACTIVE_TREE = "610c6b04" + "125dcb67" + "bb5089ae" + "83246e22" + "c9e6c456"
CORRECTION_MODE = "ap-registry-active-state-main-ci-correction"
CORRECTION_SUBJECT = "ci: govern AP registry post-merge main topology"
CORRECTION_PATHS = (
    ".github/workflows/ci.yml",
    "tests/governance/test_ci_trusted_comparison_base.py",
)
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
RESERVATION_MODE = "ap-decision-registry-forward-reservation"
RESERVATION_ENABLEMENT_MODE = RESERVATION_MODE + "-enablement"
RESERVATION_ENABLEMENT_BASE = (
    "334ca80b" + "3c9701a7" + "1756cccb" + "00d4ce9d" + "fd9b59f7"
)
RESERVATION_PATHS = ("docs/AYO_DECISION_ID_REGISTRY.json",)
GENERIC_PR_MODE = "booking-complete-replay-equivalence"
RESERVATION_RESOLVER = "verified-ap-registry-forward-reservation-base"


def _validate_reservation_paths(paths: tuple[str, ...]) -> None:
    if paths != RESERVATION_PATHS:
        raise ValueError("reservation candidate path drift")


def _resolve_reservation_source(
    *, mode: str, event: str, ref: str, base: str, before: str, parents: tuple[str, ...]
) -> str:
    if mode not in {RESERVATION_MODE, RESERVATION_ENABLEMENT_MODE}:
        raise ValueError("unknown reservation mode")
    if event == "pull_request":
        source = base
    elif event == "push" and ref == "refs/heads/main":
        if len(parents) != 2 or before != parents[0] or base != parents[0]:
            raise ValueError("reservation merge source drift")
        source = parents[0]
    elif event == "push" and ref != "refs/heads/main":
        if base not in parents:
            raise ValueError("reservation feature source drift")
        source = base
    else:
        raise ValueError("unsupported reservation context")
    if mode == RESERVATION_ENABLEMENT_MODE and source != RESERVATION_ENABLEMENT_BASE:
        raise ValueError("reservation enablement base drift")
    return source


def _resolve_pr_source(
    *,
    event: str,
    ref: str,
    mode: str,
    base: str,
    head: str,
    checked_out_head: str,
    reservation_validated: bool,
    base_is_ancestor: bool = True,
    head_is_ancestor: bool = True,
) -> tuple[str, str]:
    if event != "pull_request" or not re.fullmatch(r"refs/pull/[1-9][0-9]*/merge", ref):
        raise ValueError("pull-request event/ref drift")
    if mode not in {RESERVATION_MODE, GENERIC_PR_MODE}:
        raise ValueError("unknown PR evidence mode")
    for value in (base, head, checked_out_head):
        if not re.fullmatch(r"[0-9a-f]{40}", value) or value == ZERO:
            raise ValueError("pull-request identity drift")
    if not base_is_ancestor or not head_is_ancestor:
        raise ValueError("synthetic merge topology drift")
    if mode == RESERVATION_MODE:
        if not reservation_validated or head == base:
            raise ValueError("reservation PR authority drift")
        return base, RESERVATION_RESOLVER
    return base, "pull-request-base"


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


def _resolve_active_merge(**values: Unpack[MergeArgs]) -> str:
    if (
        values["event"] != "push"
        or values["ref"] != "refs/heads/main"
        or values["before"] != ACTIVE_BASE
        or values["parents"] != (ACTIVE_BASE, ACTIVE_HEAD)
        or values["merge_tree"] != ACTIVE_TREE
        or values["feature_tree"] != ACTIVE_TREE
        or values["merge_base"] != ACTIVE_BASE
        or values["changed_paths"] != AGGREGATE_PATHS
        or not values["registry_active"]
        or not values["ap099_absent"]
        or not values["phase5_absent"]
    ):
        raise ValueError("active-state authoritative merge drift")
    return ACTIVE_BASE


def _resolve_correction(**values: Unpack[CorrectionArgs]) -> str:
    if (
        values["base"] != ACTIVE_MERGE
        or values["subject"] != CORRECTION_SUBJECT
        or values["commit_paths"] != CORRECTION_PATHS
        or values["aggregate_paths"] != CORRECTION_PATHS
        or not values.get("linear", True)
        or not values["registry_active"]
        or not values["ap099_absent"]
        or not values["phase5_absent"]
    ):
        raise ValueError("active-state CI correction drift")
    if values["context"] == "candidate":
        if values["parents"] != (ACTIVE_MERGE,):
            raise ValueError("active-state CI candidate ancestry drift")
        return ACTIVE_MERGE
    if values["context"] == "merge":
        if (
            values["event"] != "push"
            or values["ref"] != "refs/heads/main"
            or values["before"] != ACTIVE_MERGE
            or len(values["parents"]) != 2
            or values["parents"][0] != ACTIVE_MERGE
            or values["second_parent_base"] != ACTIVE_MERGE
            or values["head_tree"] != values["second_parent_tree"]
        ):
            raise ValueError("active-state CI merge drift")
        return ACTIVE_MERGE
    raise ValueError("unknown active-state CI correction context")


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


@pytest.mark.parametrize(
    ("mode", "event", "ref", "base", "before", "parents"),
    (
        (
            RESERVATION_ENABLEMENT_MODE,
            "pull_request",
            "refs/pull/1/merge",
            RESERVATION_ENABLEMENT_BASE,
            "",
            (RESERVATION_ENABLEMENT_BASE,),
        ),
        (
            RESERVATION_MODE,
            "push",
            "refs/heads/agent/reserve",
            "e" * 40,
            "f" * 40,
            ("e" * 40,),
        ),
        (
            RESERVATION_MODE,
            "push",
            "refs/heads/main",
            "e" * 40,
            "e" * 40,
            ("e" * 40, "f" * 40),
        ),
    ),
)
def test_forward_reservation_trusted_source_positive_controls(
    mode: str, event: str, ref: str, base: str, before: str, parents: tuple[str, ...]
) -> None:
    assert (
        _resolve_reservation_source(
            mode=mode, event=event, ref=ref, base=base, before=before, parents=parents
        )
        == base
    )


def test_forward_reservation_pr_uses_verified_resolver() -> None:
    assert _resolve_pr_source(
        event="pull_request",
        ref="refs/pull/102/merge",
        mode=RESERVATION_MODE,
        base=AUTHORITATIVE_BASE,
        head=HEAD,
        checked_out_head="d" * 40,
        reservation_validated=True,
    ) == (AUTHORITATIVE_BASE, RESERVATION_RESOLVER)


def test_generic_pr_resolver_is_unchanged() -> None:
    assert _resolve_pr_source(
        event="pull_request",
        ref="refs/pull/7/merge",
        mode=GENERIC_PR_MODE,
        base=AUTHORITATIVE_BASE,
        head=HEAD,
        checked_out_head="d" * 40,
        reservation_validated=False,
    ) == (AUTHORITATIVE_BASE, "pull-request-base")


@pytest.mark.parametrize(
    "changes",
    (
        {"event": "push"},
        {"ref": "refs/heads/feature"},
        {"base": "not-a-sha"},
        {"head": ZERO},
        {"base_is_ancestor": False},
        {"head_is_ancestor": False},
        {"reservation_validated": False},
        {"mode": "unknown"},
        {"head": AUTHORITATIVE_BASE},
    ),
)
def test_forward_reservation_pr_resolver_fails_closed(
    changes: dict[str, object],
) -> None:
    values: PrResolverArgs = {
        "event": "pull_request",
        "ref": "refs/pull/102/merge",
        "mode": RESERVATION_MODE,
        "base": AUTHORITATIVE_BASE,
        "head": HEAD,
        "checked_out_head": "d" * 40,
        "reservation_validated": True,
    }
    values.update(cast(PrResolverArgs, changes))
    with pytest.raises(ValueError):
        _resolve_pr_source(**values)


@pytest.mark.parametrize(
    "values",
    (
        dict(
            mode="unknown",
            event="push",
            ref="refs/heads/feature",
            base="e" * 40,
            before="",
            parents=("e" * 40,),
        ),
        dict(
            mode=RESERVATION_ENABLEMENT_MODE,
            event="pull_request",
            ref="refs/pull/1/merge",
            base="e" * 40,
            before="",
            parents=("e" * 40,),
        ),
        dict(
            mode=RESERVATION_MODE,
            event="push",
            ref="refs/heads/feature",
            base="e" * 40,
            before="e" * 40,
            parents=("f" * 40,),
        ),
        dict(
            mode=RESERVATION_MODE,
            event="push",
            ref="refs/heads/main",
            base="e" * 40,
            before="f" * 40,
            parents=("e" * 40, "f" * 40),
        ),
    ),
)
def test_forward_reservation_trusted_source_negative_controls(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        _resolve_reservation_source(**values)  # type: ignore[arg-type]


def test_workflow_routes_forward_reservation_before_generic_push() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    dedicated = 'elif [[ "$EVIDENCE_MODE" == ap-decision-registry-forward-reservation*'
    generic = 'elif [[ -n "$EVENT_BEFORE" && "$EVENT_BEFORE" != "$zero" ]]'
    assert workflow.index(dedicated) < workflow.index(generic)
    assert "mode=verified-ap-registry-forward-reservation-base" in workflow
    assert "AP_VALIDATED: ${{ steps.apr.outputs.validated }}" in workflow
    assert "^refs/pull/[1-9][0-9]*/merge$" in workflow
    assert (
        "if [[ $EVIDENCE_MODE == ap-decision-registry-forward-reservation ]];then"
        in workflow
    )
    assert "mode=ap-reservation-pr-resolver-correction" in workflow
    assert "--forward-reservation-only" in workflow
    assert "x=docs/AYO_DECISION_ID_REGISTRY.json" in workflow
    assert "institutional/founder-discovery/phase-5/" in workflow


def test_forward_reservation_path_positive_control() -> None:
    _validate_reservation_paths(RESERVATION_PATHS)


@pytest.mark.parametrize(
    "extra_path",
    (
        "docs/UNAUTHORIZED.md",
        "institutional/founder-discovery/phase-5/implementation.json",
    ),
)
def test_forward_reservation_path_negative_controls(extra_path: str) -> None:
    with pytest.raises(ValueError, match="path drift"):
        _validate_reservation_paths(RESERVATION_PATHS + (extra_path,))


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


def _merge_arguments() -> MergeArgs:
    return {
        "event": "push",
        "ref": "refs/heads/main",
        "before": ACTIVE_BASE,
        "parents": (ACTIVE_BASE, ACTIVE_HEAD),
        "merge_tree": ACTIVE_TREE,
        "feature_tree": ACTIVE_TREE,
        "merge_base": ACTIVE_BASE,
        "changed_paths": AGGREGATE_PATHS,
        "registry_active": True,
        "ap099_absent": True,
        "phase5_absent": True,
    }


def _correction_arguments(context: str = "candidate") -> CorrectionArgs:
    return {
        "context": context,
        "event": "push" if context == "merge" else "pull_request",
        "ref": "refs/heads/main" if context == "merge" else "refs/heads/correction",
        "before": ACTIVE_MERGE,
        "base": ACTIVE_MERGE,
        "parents": (ACTIVE_MERGE, "e" * 40) if context == "merge" else (ACTIVE_MERGE,),
        "second_parent_base": ACTIVE_MERGE,
        "subject": CORRECTION_SUBJECT,
        "commit_paths": CORRECTION_PATHS,
        "aggregate_paths": CORRECTION_PATHS,
        "head_tree": "f" * 40,
        "second_parent_tree": "f" * 40,
        "registry_active": True,
        "ap099_absent": True,
        "phase5_absent": True,
    }


def test_active_state_authoritative_merge_positive_control() -> None:
    assert _resolve_active_merge(**_merge_arguments()) == ACTIVE_BASE


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("event", "pull_request"),
        ("ref", "refs/heads/feature"),
        ("before", "e" * 40),
        ("parents", ("e" * 40, ACTIVE_HEAD)),
        ("parents", (ACTIVE_BASE, "e" * 40)),
        ("parents", (ACTIVE_BASE, ACTIVE_HEAD, "e" * 40)),
        ("merge_tree", "e" * 40),
        ("feature_tree", "e" * 40),
        ("merge_base", "e" * 40),
        ("changed_paths", AGGREGATE_PATHS + ("unexpected",)),
        ("registry_active", False),
        ("ap099_absent", False),
        ("phase5_absent", False),
    ),
)
def test_active_state_authoritative_merge_negative_controls(
    key: str, value: object
) -> None:
    with pytest.raises(ValueError):
        _resolve_active_merge(**cast(MergeArgs, {**_merge_arguments(), key: value}))


@pytest.mark.parametrize("context", ("candidate", "merge"))
def test_active_state_ci_correction_positive_controls(context: str) -> None:
    assert _resolve_correction(**_correction_arguments(context)) == ACTIVE_MERGE


@pytest.mark.parametrize(
    ("context", "key", "value"),
    (
        ("candidate", "base", "e" * 40),
        ("candidate", "parents", (ACTIVE_MERGE, "e" * 40)),
        ("candidate", "subject", "wrong subject"),
        ("candidate", "commit_paths", CORRECTION_PATHS + ("unexpected",)),
        ("candidate", "aggregate_paths", CORRECTION_PATHS + ("unexpected",)),
        ("candidate", "linear", False),
        ("merge", "event", "pull_request"),
        ("merge", "ref", "refs/heads/feature"),
        ("merge", "before", "e" * 40),
        ("merge", "parents", ("e" * 40, "f" * 40)),
        ("merge", "parents", (ACTIVE_MERGE,)),
        ("merge", "second_parent_base", "e" * 40),
        ("merge", "second_parent_tree", "e" * 40),
        ("merge", "registry_active", False),
        ("merge", "ap099_absent", False),
        ("merge", "phase5_absent", False),
        ("unknown", "context", "unknown"),
    ),
)
def test_active_state_ci_correction_negative_controls(
    context: str, key: str, value: object
) -> None:
    with pytest.raises(ValueError):
        _resolve_correction(
            **cast(CorrectionArgs, {**_correction_arguments(context), key: value})
        )


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
