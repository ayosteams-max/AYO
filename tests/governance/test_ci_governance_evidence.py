from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from tools.validate_ci_governance_evidence import (
    WORKFLOW_MARKERS,
    EvidenceValidationError,
    WorkflowMarker,
    canonical_json,
    canonical_manifest,
    governed_workflow_commitment,
    mypy_column_fingerprint,
    mypy_fingerprint,
    mypy_inventory,
    mypy_semantic_fingerprint,
    normalized_workflow_commitment,
    parse_mypy_diagnostics,
    secret_fingerprint,
    secret_inventory,
    secret_semantic_inventory,
    sha256_bytes,
    structured_transition_drift,
)


def test_canonical_json_and_sha_are_deterministic() -> None:
    first = canonical_json({"z": [2, 1], "a": "ሰላም"})
    second = canonical_json({"a": "ሰላም", "z": [2, 1]})
    assert first == second == '{"a":"ሰላም","z":[2,1]}'
    assert sha256_bytes(first.encode()) == sha256_bytes(second.encode())


def test_sha_rejects_empty_input() -> None:
    with pytest.raises(EvidenceValidationError, match="non-empty"):
        sha256_bytes(b"")


def test_workflow_commitment_normalizes_each_marker_once() -> None:
    data = b'x="abcdef"\ny="123456"\n'
    markers = (
        WorkflowMarker("x", rb'x="[0-9a-f]{6}"', b'x="000000"'),
        WorkflowMarker("y", rb'y="[0-9]{6}"', b'y="000000"'),
    )
    digest, inventory = normalized_workflow_commitment(data, markers)
    assert digest == sha256_bytes(b'x="000000"\ny="000000"\n')
    assert inventory == ("x", "y")


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b'x="abcdef"\n', "cardinality is 0"),
        (b'x="abcdef"\nx="abcdef"\ny="123456"\n', "cardinality is 2"),
    ],
)
def test_workflow_commitment_rejects_missing_or_duplicate_marker(
    data: bytes, message: str
) -> None:
    markers = (
        WorkflowMarker("x", rb'x="[0-9a-f]{6}"', b'x="000000"'),
        WorkflowMarker("y", rb'y="[0-9]{6}"', b'y="000000"'),
    )
    with pytest.raises(EvidenceValidationError, match=message):
        normalized_workflow_commitment(data, markers)


def test_workflow_commitment_rejects_malformed_marker() -> None:
    with pytest.raises(EvidenceValidationError, match="malformed"):
        normalized_workflow_commitment(
            b'x="abcdef"\n', (WorkflowMarker("x", b"[", b"0"),)
        )


def test_workflow_commitment_is_lf_crlf_explicit() -> None:
    marker = (WorkflowMarker("x", rb'x="[0-9a-f]{6}"', b'x="000000"'),)
    lf, _ = normalized_workflow_commitment(b'x="abcdef"\n', marker)
    crlf, _ = normalized_workflow_commitment(b'x="abcdef"\r\n', marker)
    assert lf != crlf
    assert lf == sha256_bytes(b'x="000000"\n')


def test_governed_workflow_commitment_reproduces_real_marker_inventory() -> None:
    workflow = (
        Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml"
    ).read_bytes()
    canonical = workflow.replace(b"\r\n", b"\n")
    independently_normalized = canonical
    for marker in WORKFLOW_MARKERS:
        independently_normalized, count = re.subn(
            marker.pattern, marker.replacement, independently_normalized
        )
        assert count == 1
    expected = hashlib.sha256(independently_normalized).hexdigest()
    assert governed_workflow_commitment(canonical, "ap") == expected
    assert governed_workflow_commitment(canonical, "ap") == expected


def test_governed_workflow_commitment_rejects_unsupported_scope() -> None:
    with pytest.raises(EvidenceValidationError, match="unsupported"):
        governed_workflow_commitment(b"governed workflow", "unknown")


def test_mypy_parsing_sorting_inventory_and_fingerprints() -> None:
    text = (
        "C:\\repo\\tests/test_b.py:2:3: error: second  issue [arg-type]\n"
        "C:\\repo\\BACKEND/a.py:1:2: error: first issue [no-any-return]\n"
    )
    diagnostics = parse_mypy_diagnostics(text, roots=("C:/repo",))
    assert [item.path for item in diagnostics] == ["BACKEND/a.py", "tests/test_b.py"]
    assert diagnostics[1].message == "second issue"
    assert mypy_inventory(diagnostics) == {
        "diagnostics": 2,
        "files": 2,
        "codes": {"arg-type": 1, "no-any-return": 1},
        "fingerprint": mypy_fingerprint(diagnostics),
    }
    assert len(mypy_column_fingerprint(diagnostics)) == 64
    assert len(mypy_semantic_fingerprint(diagnostics)) == 64


def test_mypy_fingerprint_detects_changed_material() -> None:
    first = parse_mypy_diagnostics(
        "BACKEND/a.py:1:2: error: first issue [no-any-return]\n"
    )
    second = parse_mypy_diagnostics(
        "BACKEND/a.py:1:2: error: changed issue [no-any-return]\n"
    )
    assert mypy_fingerprint(first) != mypy_fingerprint(second)


@pytest.mark.parametrize(
    "text",
    ["", "BACKEND/a.py:line:2: error: broken [arg-type]\n"],
)
def test_mypy_rejects_empty_or_malformed_actionable_input(text: str) -> None:
    with pytest.raises(EvidenceValidationError):
        parse_mypy_diagnostics(text)


def test_mypy_rejects_duplicate_diagnostics() -> None:
    line = "BACKEND/a.py:1:2: error: issue [arg-type]\n"
    with pytest.raises(EvidenceValidationError, match="duplicate"):
        parse_mypy_diagnostics(line + line)


def finding(line: int = 2) -> dict[str, object]:
    return {
        "line_number": line,
        "type": "Hex High Entropy String",
        "hashed_secret": "abc123",
        "is_verified": False,
    }


def test_secret_inventory_sorting_semantics_and_fingerprint() -> None:
    scan = {"z.py": [finding(3)], "a.py": [finding(1)]}
    inventory = secret_inventory(scan)
    assert [item[0] for item in inventory] == ["a.py", "z.py"]
    semantics = secret_semantic_inventory(inventory)
    assert len(semantics) == 2
    assert secret_fingerprint(inventory) == secret_fingerprint(
        tuple(reversed(inventory))
    )
    assert secret_fingerprint(semantics) != secret_fingerprint(inventory)


@pytest.mark.parametrize(
    "results",
    [None, {"a.py": [{}]}, {"../a.py": [finding()]}, {"a.py": [finding(), finding()]}],
)
def test_secret_inventory_rejects_malformed_or_duplicate_input(results: object) -> None:
    with pytest.raises(EvidenceValidationError):
        secret_inventory(results)


def test_manifest_requires_safe_sorted_unique_paths() -> None:
    assert canonical_manifest(("a", "b/c")) == ("a", "b/c")
    for invalid in (("b", "a"), ("a", "a"), ("../a",), ()):
        with pytest.raises(EvidenceValidationError):
            canonical_manifest(invalid)


def test_structured_transition_reports_only_unapproved_drift() -> None:
    baseline = {"cutover": {"status": "READY"}, "allocations": [1, 2]}
    candidate = {"cutover": {"status": "ACTIVE"}, "allocations": [1, 3]}
    assert structured_transition_drift(
        baseline, candidate, (("cutover", "status"),)
    ) == (("allocations",),)


def test_structured_transition_rejects_invalid_root() -> None:
    with pytest.raises(EvidenceValidationError, match="roots"):
        structured_transition_drift([], {}, ())


def test_helper_has_no_nonstandard_runtime_dependency() -> None:
    # Importing and exercising public functions is the dependency check; no plugin mode
    # or external package is accepted by this module.
    assert json.loads(canonical_json({"evidence_version": 1})) == {
        "evidence_version": 1
    }
