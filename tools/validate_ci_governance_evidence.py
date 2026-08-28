"""Deterministic, side-effect-free calculations for governed CI evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


class EvidenceValidationError(ValueError):
    """A bounded validation failure for malformed evidence input."""


def canonical_json(value: Any) -> str:
    """Return stable compact JSON without changing the supplied value."""

    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    except (TypeError, ValueError) as error:
        raise EvidenceValidationError(
            "value is not canonical-JSON encodable"
        ) from error


def sha256_bytes(value: bytes) -> str:
    if not isinstance(value, bytes) or not value:
        raise EvidenceValidationError("SHA-256 input must be non-empty bytes")
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class WorkflowMarker:
    name: str
    pattern: bytes
    replacement: bytes


def normalized_workflow_commitment(
    data: bytes, markers: Sequence[WorkflowMarker]
) -> tuple[str, tuple[str, ...]]:
    """Normalize each approved marker exactly once and hash the resulting bytes."""

    if not data:
        raise EvidenceValidationError("workflow bytes are empty")
    if not markers:
        raise EvidenceValidationError("workflow marker inventory is empty")
    names = [marker.name for marker in markers]
    if len(names) != len(set(names)):
        raise EvidenceValidationError("workflow marker names are duplicated")
    normalized = data
    found: list[str] = []
    for marker in markers:
        try:
            normalized, count = re.subn(marker.pattern, marker.replacement, normalized)
        except re.error as error:
            raise EvidenceValidationError(
                f"workflow marker {marker.name} is malformed"
            ) from error
        if count != 1:
            raise EvidenceValidationError(
                f"workflow marker {marker.name} cardinality is {count}, expected 1"
            )
        found.append(marker.name)
    return hashlib.sha256(normalized).hexdigest(), tuple(found)


MYPY_PATTERN = re.compile(
    r"^(?P<path>(?:BACKEND|tests)/.*?):(?P<line>\d+):(?P<column>\d+): "
    r"error: (?P<message>.+) \[(?P<code>[a-z0-9-]+)\]$"
)


@dataclass(frozen=True, order=True)
class MyPyDiagnostic:
    path: str
    line: int
    column: int
    code: str
    message: str

    def render(self) -> str:
        return (
            f"{self.path}:{self.line}:{self.column}: error: "
            f"{self.message} [{self.code}]"
        )


def parse_mypy_diagnostics(
    text: str,
    *,
    roots: Iterable[str] = (),
    allow_empty: bool = False,
    collapse_message_whitespace: bool = True,
) -> tuple[MyPyDiagnostic, ...]:
    if not isinstance(text, str):
        raise EvidenceValidationError("MyPy evidence must be text")
    normalized_roots = tuple(
        root.replace("\\", "/").rstrip("/") + "/" for root in roots
    )
    diagnostics: list[MyPyDiagnostic] = []
    malformed: list[str] = []
    for raw in text.splitlines():
        line = raw.replace("\\", "/")
        for root in normalized_roots:
            if line.startswith(root):
                line = line[len(root) :]
                break
        match = MYPY_PATTERN.fullmatch(line)
        if match:
            message = match["message"]
            if collapse_message_whitespace:
                message = " ".join(message.split())
            diagnostics.append(
                MyPyDiagnostic(
                    match["path"],
                    int(match["line"]),
                    int(match["column"]),
                    match["code"],
                    message,
                )
            )
        elif ": error:" in line and line.startswith(("BACKEND/", "tests/")):
            malformed.append(line)
    if malformed:
        raise EvidenceValidationError("malformed actionable MyPy diagnostic")
    if not diagnostics and not allow_empty:
        raise EvidenceValidationError("missing actionable MyPy diagnostics")
    if len(diagnostics) != len(set(diagnostics)):
        raise EvidenceValidationError("duplicate MyPy diagnostics")
    return tuple(sorted(diagnostics))


def mypy_fingerprint(diagnostics: Sequence[MyPyDiagnostic]) -> str:
    payload = "\n".join(item.render() for item in diagnostics)
    return hashlib.sha1(payload.encode(), usedforsecurity=False).hexdigest()


def mypy_column_fingerprint(diagnostics: Sequence[MyPyDiagnostic]) -> str:
    payload = "\n".join(
        f"{item.path}|{item.line}|{item.column}|{item.code}|{item.message}"
        for item in sorted(diagnostics)
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def mypy_semantic_fingerprint(diagnostics: Sequence[MyPyDiagnostic]) -> str:
    payload = "\n".join(
        f"{item.path}|{item.code}|{item.message}" for item in sorted(diagnostics)
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def mypy_inventory(diagnostics: Sequence[MyPyDiagnostic]) -> dict[str, Any]:
    return {
        "diagnostics": len(diagnostics),
        "files": len({item.path for item in diagnostics}),
        "codes": dict(sorted(Counter(item.code for item in diagnostics).items())),
        "fingerprint": mypy_fingerprint(diagnostics),
    }


def mypy_difference(
    source: Sequence[MyPyDiagnostic], candidate: Sequence[MyPyDiagnostic]
) -> dict[str, Any]:
    source_set, candidate_set = set(source), set(candidate)
    source_locations = Counter((item.path, item.line, item.column) for item in source)
    candidate_locations = Counter(
        (item.path, item.line, item.column) for item in candidate
    )
    source_codes = Counter((item.path, item.code) for item in source)
    candidate_codes = Counter((item.path, item.code) for item in candidate)
    return {
        "equal": tuple(source) == tuple(candidate),
        "source_only": tuple(sorted(source_set - candidate_set)),
        "candidate_only": tuple(sorted(candidate_set - source_set)),
        "source_only_locations": tuple(
            sorted((source_locations - candidate_locations).elements())
        ),
        "candidate_only_locations": tuple(
            sorted((candidate_locations - source_locations).elements())
        ),
        "source_only_codes": tuple(sorted((source_codes - candidate_codes).elements())),
        "candidate_only_codes": tuple(
            sorted((candidate_codes - source_codes).elements())
        ),
    }


def mypy_semantic_movement(
    source: Sequence[MyPyDiagnostic], candidate: Sequence[MyPyDiagnostic]
) -> tuple[
    tuple[
        tuple[str, str, str], tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]
    ],
    ...,
]:
    source_semantics = Counter((item.path, item.code, item.message) for item in source)
    candidate_semantics = Counter(
        (item.path, item.code, item.message) for item in candidate
    )
    if source_semantics != candidate_semantics:
        raise EvidenceValidationError("MyPy semantic diagnostic population changed")
    moved = []
    for semantic in sorted(source_semantics):
        old = tuple(
            sorted(
                (item.line, item.column)
                for item in source
                if (item.path, item.code, item.message) == semantic
            )
        )
        new = tuple(
            sorted(
                (item.line, item.column)
                for item in candidate
                if (item.path, item.code, item.message) == semantic
            )
        )
        if old != new:
            moved.append((semantic, old, new))
    return tuple(moved)


SecretFinding = tuple[str, int, str, str, bool]
SecretSemantic = tuple[str, str, str, bool]

BATCH2_ONLY_SECRET_PATHS = frozenset(
    {
        "tests/integration/test_account_access_foundation.py",
        "tests/integration/test_authentication_runtime.py",
        "tests/integration/test_identity_access_increment_2.py",
        "tests/test_authentication_runtime.py",
        "tests/test_q3_continuation3_identity_finance_coverage.py",
    }
)

IMMEDIATE_STANDARD_SECRET_ADDITIONS: dict[SecretFinding, str] = {
    (
        "AYO-Mobile/tests/auth-session-foundation.test.ts",
        59,
        "Secret Keyword",
        "df77a6b3e1381f280f62cc2eceea74ec575efde6",
        False,
    ): "synthetic authentication credential test fixture",
    (
        "AYO-Mobile/tests/authenticated-read-transport.test.ts",
        27,
        "Secret Keyword",
        "99d72c7fc3e2e145870beab37c0b70e343ea9c3b",
        False,
    ): "synthetic redaction test fixture",
    (
        "AYO-Mobile/tests/authenticated-read-transport.test.ts",
        43,
        "Basic Auth Credentials",
        "e5e9fa1ba31ecd1ae84f75caaa474f3a663f05f4",
        False,
    ): "synthetic URL-normalization test fixture",
    (
        "AYO-Mobile/tests/identity-session-provider.test.tsx",
        10,
        "Secret Keyword",
        "df77a6b3e1381f280f62cc2eceea74ec575efde6",
        False,
    ): "synthetic authentication credential test fixture",
    (
        "AYO-Mobile/tests/operational-context-provider.test.tsx",
        47,
        "Secret Keyword",
        "df77a6b3e1381f280f62cc2eceea74ec575efde6",
        False,
    ): "synthetic authentication credential test fixture",
    (
        "tests/test_merchant_anthropic_live_provider_evaluation.py",
        307,
        "Secret Keyword",
        "8ced3c87ee2c45dc7602ae84d04a8350d58039aa",
        False,
    ): "synthetic redaction test fixture",
    (
        "tests/test_merchant_live_provider_evaluation.py",
        127,
        "Secret Keyword",
        "8ced3c87ee2c45dc7602ae84d04a8350d58039aa",
        False,
    ): "synthetic redaction test fixture",
    (
        "AYO-Mobile/localization/authentication.ts",
        11,
        "Secret Keyword",
        "8be3c943b1609fffbfc51aad666d0a04adf83c9d",
        False,
    ): "ordinary public password-field localization wording",
}


def secret_inventory(results: Any) -> tuple[SecretFinding, ...]:
    if not isinstance(results, Mapping):
        raise EvidenceValidationError("secret scanner results must be an object")
    items: list[SecretFinding] = []
    for raw_path, records in results.items():
        if not isinstance(raw_path, str) or not isinstance(records, list):
            raise EvidenceValidationError("secret scanner inventory shape is malformed")
        path = raw_path.replace("\\", "/")
        if (
            not path
            or PurePosixPath(path).is_absolute()
            or ".." in PurePosixPath(path).parts
        ):
            raise EvidenceValidationError("secret scanner path is unsafe")
        for record in records:
            if not isinstance(record, Mapping):
                raise EvidenceValidationError("secret scanner record is malformed")
            try:
                item = (
                    path,
                    int(record["line_number"]),
                    str(record["type"]),
                    str(record["hashed_secret"]),
                    bool(record["is_verified"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise EvidenceValidationError(
                    "secret scanner record fields are malformed"
                ) from error
            if item[1] < 1 or not item[2] or not item[3]:
                raise EvidenceValidationError(
                    "secret scanner record values are malformed"
                )
            items.append(item)
    if len(items) != len(set(items)):
        raise EvidenceValidationError("secret scanner inventory contains duplicates")
    return tuple(sorted(items))


def reviewed_secret_inventory(
    results: Any,
) -> tuple[tuple[SecretFinding, ...], dict[tuple[str, int, str], str]]:
    if not isinstance(results, Mapping):
        raise EvidenceValidationError("reviewed secret results must be an object")
    required = {
        "type",
        "digest_bytes",
        "is_verified",
        "line_number",
        "classification",
    }
    items: list[SecretFinding] = []
    classes: dict[tuple[str, int, str], str] = {}
    for path, records in results.items():
        if not isinstance(path, str) or "\\" in path or not isinstance(records, list):
            raise EvidenceValidationError(
                "reviewed secret path or records are malformed"
            )
        for record in records:
            if not isinstance(record, Mapping) or set(record) != required:
                raise EvidenceValidationError("reviewed secret finding fields drifted")
            digest = record["digest_bytes"]
            if (
                not isinstance(digest, list)
                or len(digest) != 20
                or any(
                    type(value) is not int or not 0 <= value <= 255 for value in digest
                )
            ):
                raise EvidenceValidationError("reviewed secret digest is malformed")
            item = (
                path,
                int(record["line_number"]),
                str(record["type"]),
                bytes(digest).hex(),
                bool(record["is_verified"]),
            )
            items.append(item)
            classes[item[:3]] = str(record["classification"])
    if len(items) != len(set(items)):
        raise EvidenceValidationError("reviewed secret inventory contains duplicates")
    return tuple(sorted(items)), classes


def secret_semantic_inventory(
    findings: Iterable[SecretFinding],
) -> tuple[SecretSemantic, ...]:
    return tuple(
        sorted(
            (path, detector, digest, verified)
            for path, _, detector, digest, verified in findings
        )
    )


def candidate_only_secret_semantics(
    base: Iterable[SecretFinding], candidate: Iterable[SecretFinding]
) -> tuple[SecretSemantic, ...]:
    """Return the deterministic multiset difference without choosing authority."""
    base_items = Counter(secret_semantic_inventory(base))
    candidate_items = Counter(secret_semantic_inventory(candidate))
    return tuple(sorted((candidate_items - base_items).elements()))


def hex_byte_inventory(value: Any, length: int, label: str) -> str:
    if (
        not isinstance(value, list)
        or len(value) != length
        or any(type(item) is not int or not 0 <= item <= 255 for item in value)
    ):
        raise EvidenceValidationError(f"malformed {label} byte inventory")
    return bytes(value).hex()


def require_exact_secret_inventory(
    label: str,
    actual: Iterable[SecretFinding],
    expected: Iterable[SecretFinding],
) -> None:
    actual_items, expected_items = tuple(actual), tuple(expected)
    if actual_items != expected_items:
        actual_set, expected_set = set(actual_items), set(expected_items)
        for prefix, items in (
            ("EXPECTED_ONLY", expected_set - actual_set),
            ("ACTUAL_ONLY", actual_set - expected_set),
        ):
            for item in sorted(items):
                rendered = "|".join(
                    str(value).lower() if isinstance(value, bool) else str(value)
                    for value in item
                )
                print(f"{prefix}|{rendered}")
        raise EvidenceValidationError(f"{label} semantic finding inventory drift")


def classify_registry_git_provenance(
    findings: Iterable[SecretSemantic],
    registry: Mapping[str, Any],
    trusted_main: str,
    candidate_head: str,
    *,
    registry_validated: bool,
    main_reachable: bool,
) -> tuple[tuple[SecretSemantic, ...], tuple[SecretSemantic, ...]]:
    """Separate validator-proven registry Git provenance from secret semantics."""
    values = tuple(findings)
    if not registry_validated or not main_reachable:
        return (), tuple(sorted(values))
    if (
        not re.fullmatch(r"[0-9a-f]{40}", trusted_main)
        or trusted_main == candidate_head
    ):
        return (), tuple(sorted(values))
    events = registry.get("forward_identity_events")
    if not isinstance(events, list) or not events:
        return (), tuple(sorted(values))
    approved = [
        ("forward_identity_events", index, "base_main_commit")
        for index, event in enumerate(events)
        if isinstance(event, Mapping) and event.get("base_main_commit") == trusted_main
    ]
    locations: list[tuple[object, ...]] = []

    def walk(value: Any, path: tuple[object, ...] = ()) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                walk(child, path + (key,))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, path + (index,))
        elif value == trusted_main:
            locations.append(path)

    walk(registry)
    if not approved or sorted(locations) != sorted(approved):
        return (), tuple(sorted(values))
    digest = hashlib.sha1(trusted_main.encode(), usedforsecurity=False).hexdigest()
    target = (
        "docs/AYO_DECISION_ID_REGISTRY.json",
        "Hex High Entropy String",
        digest,
        False,
    )
    governed = tuple(item for item in values if item == target)
    unreviewed = tuple(sorted(item for item in values if item != target))
    return governed, unreviewed


def classify_reservation_secret_semantics(
    findings: Iterable[SecretSemantic],
    registry: Mapping[str, Any],
    trusted_main: str,
    candidate_head: str,
    *,
    evidence_mode: str,
    reservation_validated: str,
    trusted_mode: str,
) -> tuple[tuple[SecretSemantic, ...], tuple[SecretSemantic, ...]]:
    """Apply typed provenance only after authenticated reservation admission."""
    values = tuple(findings)
    if (
        evidence_mode != "ap-decision-registry-forward-reservation"
        or reservation_validated != "true"
        or trusted_mode != "verified-ap-registry-forward-reservation-base"
    ):
        return (), tuple(sorted(values))
    return classify_registry_git_provenance(
        values,
        registry,
        trusted_main,
        candidate_head,
        registry_validated=True,
        main_reachable=True,
    )


def secret_fingerprint(findings: Iterable[SecretFinding | SecretSemantic]) -> str:
    rendered: list[str] = []
    for item in sorted(findings):
        rendered.append(
            "|".join(
                str(value).lower() if isinstance(value, bool) else str(value)
                for value in item
            )
        )
    return hashlib.sha256("\n".join(rendered).encode()).hexdigest()


def canonical_manifest(paths: Iterable[str]) -> tuple[str, ...]:
    values = tuple(path.replace("\\", "/") for path in paths)
    if not values:
        raise EvidenceValidationError("path manifest is empty")
    if any(
        not path
        or PurePosixPath(path).is_absolute()
        or ".." in PurePosixPath(path).parts
        for path in values
    ):
        raise EvidenceValidationError("path manifest contains an unsafe path")
    if len(values) != len(set(values)):
        raise EvidenceValidationError("path manifest contains duplicates")
    if values != tuple(sorted(values)):
        raise EvidenceValidationError("path manifest is not canonically sorted")
    return values


def structured_transition_drift(
    baseline: Any, candidate: Any, allowed_paths: Iterable[tuple[str, ...]]
) -> tuple[tuple[str, ...], ...]:
    """Return changed object paths not included in an exact allow-list."""

    allowed = frozenset(allowed_paths)
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise EvidenceValidationError("structured transition roots must be objects")

    changed: list[tuple[str, ...]] = []

    def visit(left: Any, right: Any, path: tuple[str, ...]) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                if key not in left or key not in right:
                    changed.append(path + (key,))
                else:
                    visit(left[key], right[key], path + (key,))
            return
        if left != right:
            changed.append(path)

    visit(baseline, candidate, ())
    return tuple(path for path in changed if path not in allowed)


WORKFLOW_MARKERS = (
    WorkflowMarker(
        "pip",
        rb'expected_ci_normalized_sha256="[0-9a-f]{32}""[0-9a-f]{32}"',
        b'expected_ci_normalized_sha256="00000000000000000000000000000000"'
        b'"00000000000000000000000000000000"',
    ),
    WorkflowMarker(
        "ap-landing",
        rb'expected_ap_registry_ci_normalized_sha256="[0-9a-f]{16}""[0-9a-f]{16}""[0-9a-f]{16}""[0-9a-f]{16}"',
        b'expected_ap_registry_ci_normalized_sha256="0000000000000000"'
        b'"0000000000000000""0000000000000000""0000000000000000"',
    ),
    WorkflowMarker(
        "ap-active",
        rb'expected_ap_registry_active_state_ci_normalized_sha256="[0-9a-f]{16}""[0-9a-f]{16}""[0-9a-f]{16}""[0-9a-f]{16}"',
        b'expected_ap_registry_active_state_ci_normalized_sha256="0000000000000000"'
        b'"0000000000000000""0000000000000000""0000000000000000"',
    ),
    WorkflowMarker(
        "ap-main-ci",
        rb'expected_ap_main_ci_sha256="[0-9a-f]{32}""[0-9a-f]{32}"',
        b'expected_ap_main_ci_sha256="00000000000000000000000000000000"'
        b'"00000000000000000000000000000000"',
    ),
    WorkflowMarker(
        "ci-extraction",
        rb'expected_ci_governance_extraction_sha256="[0-9a-f]{32}""[0-9a-f]{32}"',
        b'expected_ci_governance_extraction_sha256="00000000000000000000000000000000"'
        b'"00000000000000000000000000000000"',
    ),
    WorkflowMarker(
        "registry-enablement",
        rb'expected_registry_reconciliation_enablement_sha256="[0-9a-f]{32}""[0-9a-f]{32}"',
        b'expected_registry_reconciliation_enablement_sha256="00000000000000000000000000000000"'
        b'"00000000000000000000000000000000"',
    ),
)


def governed_workflow_commitment(data: bytes, scope: str) -> str:
    if scope == "ap":
        selected = WORKFLOW_MARKERS
    elif scope == "pip":
        # Cardinality of every governed marker is checked before preserving the
        # historical pip commitment's approved single-marker normalization.
        for marker in WORKFLOW_MARKERS:
            if len(re.findall(marker.pattern, data)) != 1:
                raise EvidenceValidationError(
                    f"workflow marker {marker.name} cardinality drift"
                )
        selected = WORKFLOW_MARKERS[:1]
    else:
        raise EvidenceValidationError("unsupported workflow commitment scope")
    return normalized_workflow_commitment(data, selected)[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("workflow-commitment",))
    parser.add_argument("--scope", choices=("ap", "pip"), required=True)
    parser.add_argument("--workflow", required=True)
    args = parser.parse_args(argv)
    try:
        if args.workflow == "-":
            data = sys.stdin.buffer.read()
        else:
            from pathlib import Path

            data = Path(args.workflow).read_bytes()
        print(governed_workflow_commitment(data, args.scope))
    except (OSError, EvidenceValidationError) as error:
        print(f"governance evidence error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
