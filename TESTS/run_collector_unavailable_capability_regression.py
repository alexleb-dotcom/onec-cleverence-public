#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_REL = "WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json"
PUBLIC_MANIFEST_REL = "DISTRIBUTION_MANIFEST.json"


def _finding(finding_type: str, **details) -> dict:
    return {"type": finding_type, **details}


def validate_collector_unavailable_contract(root: Path) -> dict:
    root = root.resolve()
    errors: list[dict] = []
    contract_path = root / CONTRACT_REL
    if not contract_path.is_file():
        return {"result": "FAIL", "errors": [_finding("COLLECTOR_FALLBACK_CONTRACT_MISSING", path=CONTRACT_REL)]}

    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"result": "FAIL", "errors": [_finding("COLLECTOR_FALLBACK_CONTRACT_INVALID_JSON", error=str(exc))]}

    distribution = payload.get("collector_distribution") if isinstance(payload, dict) else None
    if not isinstance(distribution, dict):
        errors.append(_finding("COLLECTOR_DISTRIBUTION_CONTRACT_MISSING"))
        distribution = {}

    guard = distribution.get("availability_guard")
    if not isinstance(guard, dict):
        errors.append(_finding("COLLECTOR_AVAILABILITY_GUARD_MISSING"))
        guard = {}
    if guard.get("required_before_project_snapshot_required") is not True:
        errors.append(_finding("COLLECTOR_AVAILABILITY_GUARD_NOT_REQUIRED"))
    if guard.get("unavailable_disposition") != "COLLECTOR_UNAVAILABLE":
        errors.append(_finding("COLLECTOR_UNAVAILABLE_DISPOSITION_MISMATCH"))

    guard_rule = str(guard.get("rule") or "")
    required_guard_fragments = (
        "apply only when the repository-pinned manifest/payload are present",
        "do not synthesize/build it",
        "COLLECTOR_UNAVAILABLE bounded manual fallback",
    )
    missing_guard_fragments = [fragment for fragment in required_guard_fragments if fragment not in guard_rule]
    if missing_guard_fragments:
        errors.append(_finding("COLLECTOR_AVAILABILITY_RULE_INCOMPLETE", missing=missing_guard_fragments))

    if distribution.get("ordinary_developer_build_required") is not False:
        errors.append(_finding("COLLECTOR_FALLBACK_TRANSFERS_BUILD_TO_DEVELOPER"))

    gate = payload.get("pre_manual_current_onec_gate") if isinstance(payload, dict) else None
    if not isinstance(gate, dict):
        errors.append(_finding("COLLECTOR_PRE_MANUAL_GATE_MISSING"))
        gate = {}

    dispositions = gate.get("dispositions") if isinstance(gate.get("dispositions"), list) else []
    allowed = gate.get("manual_request_allowed_for") if isinstance(gate.get("manual_request_allowed_for"), list) else []
    if "COLLECTOR_UNAVAILABLE" not in dispositions:
        errors.append(_finding("COLLECTOR_UNAVAILABLE_DISPOSITION_NOT_DECLARED"))
    if "COLLECTOR_UNAVAILABLE" not in allowed:
        errors.append(_finding("COLLECTOR_UNAVAILABLE_MANUAL_FALLBACK_NOT_ALLOWED"))

    rules = gate.get("rules") if isinstance(gate.get("rules"), list) else []
    if not any("manual fallback must retain a concrete reason" in str(rule) for rule in rules):
        errors.append(_finding("COLLECTOR_MANUAL_FALLBACK_REASON_RULE_MISSING"))

    must_not = payload.get("developer_must_not_be_required_to") if isinstance(payload, dict) else None
    must_not = must_not if isinstance(must_not, list) else []
    required_developer_guards = (
        "build ProjectSnapshotCollector.epf for ordinary collection",
        "run build_epf.ps1 for ordinary collection",
    )
    missing_developer_guards = [item for item in required_developer_guards if item not in must_not]
    if missing_developer_guards:
        errors.append(_finding("COLLECTOR_DEVELOPER_BUILD_GUARD_MISSING", missing=missing_developer_guards))

    is_public_snapshot = (root / PUBLIC_MANIFEST_REL).is_file()
    if is_public_snapshot and (root / "COLLECTOR").exists():
        errors.append(_finding("PUBLIC_SHAREABLE_COLLECTOR_PRESENT"))

    return {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "disposition": "COLLECTOR_UNAVAILABLE",
        "manual_fallback": "BOUNDED",
        "ordinary_developer_build_required": False,
        "public_snapshot": is_public_snapshot,
        "rule": "When the public SHAREABLE_CORE omits Collector bytes, the skill must explicitly resolve COLLECTOR_UNAVAILABLE and use a bounded reasoned manual fallback without fabricating an EPF or transferring build responsibility to the user.",
    }


def _base_contract() -> dict:
    return {
        "collector_distribution": {
            "ordinary_developer_build_required": False,
            "availability_guard": {
                "required_before_project_snapshot_required": True,
                "unavailable_disposition": "COLLECTOR_UNAVAILABLE",
                "rule": "Collector-specific transitions apply only when the repository-pinned manifest/payload are present. If unavailable, do not synthesize/build it; use the existing COLLECTOR_UNAVAILABLE bounded manual fallback.",
            },
        },
        "developer_must_not_be_required_to": [
            "build ProjectSnapshotCollector.epf for ordinary collection",
            "run build_epf.ps1 for ordinary collection",
        ],
        "pre_manual_current_onec_gate": {
            "dispositions": ["COLLECTOR_UNAVAILABLE"],
            "manual_request_allowed_for": ["COLLECTOR_UNAVAILABLE"],
            "rules": ["manual fallback must retain a concrete reason and must not imply that ProjectSnapshot is unavailable when it was merely deferred"],
        },
    }


def _run_synthetic(mutator=None, *, collector_present: bool = False) -> dict:
    payload = _base_contract()
    if mutator is not None:
        mutator(payload)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        contract = root / CONTRACT_REL
        contract.parent.mkdir(parents=True)
        contract.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        (root / PUBLIC_MANIFEST_REL).write_text("{}\n", encoding="utf-8")
        if collector_present:
            (root / "COLLECTOR").mkdir()
        return validate_collector_unavailable_contract(root)


def _types(report: dict) -> set[str]:
    return {row.get("type") for row in report.get("errors", [])}


def _require(case: str, report: dict, finding: str) -> None:
    if finding not in _types(report):
        raise AssertionError(f"{case}: expected {finding}, got {report!r}")


def self_test() -> int:
    clean = _run_synthetic()
    if clean.get("result") != "PASS":
        raise AssertionError(f"clean unavailable contract should pass: {clean!r}")

    _require(
        "guard-missing",
        _run_synthetic(lambda p: p["collector_distribution"].pop("availability_guard")),
        "COLLECTOR_AVAILABILITY_GUARD_MISSING",
    )
    _require(
        "wrong-disposition",
        _run_synthetic(lambda p: p["collector_distribution"]["availability_guard"].__setitem__("unavailable_disposition", "PROJECT_SNAPSHOT_REQUIRED")),
        "COLLECTOR_UNAVAILABLE_DISPOSITION_MISMATCH",
    )
    _require(
        "build-transferred",
        _run_synthetic(lambda p: p["collector_distribution"].__setitem__("ordinary_developer_build_required", True)),
        "COLLECTOR_FALLBACK_TRANSFERS_BUILD_TO_DEVELOPER",
    )
    _require(
        "manual-not-allowed",
        _run_synthetic(lambda p: p["pre_manual_current_onec_gate"].__setitem__("manual_request_allowed_for", [])),
        "COLLECTOR_UNAVAILABLE_MANUAL_FALLBACK_NOT_ALLOWED",
    )
    _require(
        "reason-rule-missing",
        _run_synthetic(lambda p: p["pre_manual_current_onec_gate"].__setitem__("rules", [])),
        "COLLECTOR_MANUAL_FALLBACK_REASON_RULE_MISSING",
    )
    _require(
        "public-collector-present",
        _run_synthetic(collector_present=True),
        "PUBLIC_SHAREABLE_COLLECTOR_PRESENT",
    )

    print(json.dumps({"result": "PASS", "cases": 7}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the public COLLECTOR_UNAVAILABLE capability/fallback contract without requiring Collector bytes.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    report = validate_collector_unavailable_contract(Path(args.root))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
