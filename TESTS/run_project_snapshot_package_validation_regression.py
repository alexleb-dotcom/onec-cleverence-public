#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from validate_project_snapshot_package import validate_package  # noqa: E402
from machine_receipts import create_receipt, verify_receipt  # noqa: E402


def base_documents() -> dict[str, object]:
    plan = {
        "schema_version": 1,
        "result": "READY",
        "request_id": "req-chat-fixture",
        "baseline_expectation": {
            "configuration_name": "FixtureConfiguration",
            "configuration_version": "1.0",
            "source_role": "DEPLOYED_OR_USER_BASELINE",
            "known_fingerprint": None,
        },
        "item_plan": [
            {
                "id": "metadata-item",
                "category": "METADATA_PROPERTIES",
                "logical_target": "DOCUMENT.Test",
                "required_for_claim": "fixture:metadata",
                "minimum_fidelity": "PARTIAL",
                "status": "READY",
                "selected": {
                    "backend": "RUNTIME_METADATA",
                    "state": "PARTIAL",
                    "method": "runtime metadata objects",
                    "limitations": [],
                    "automatic": True,
                },
            },
            {
                "id": "module-item",
                "category": "MODULE_SOURCE",
                "logical_target": "DOCUMENT.Test.ObjectModule",
                "required_for_claim": "fixture:source",
                "minimum_fidelity": "FULL",
                "status": "READY",
                "selected": {
                    "backend": "SOURCE_EXPORT",
                    "state": "FULL",
                    "method": "Designer source export",
                    "limitations": [],
                    "automatic": True,
                },
            },
        ],
        "unresolved_items": [],
    }
    runtime = {
        "schema_version": 1,
        "request_id": "req-chat-fixture",
        "collector": {
            "name": "ProjectSnapshotRuntimeCollector",
            "version": "1",
            "backend": "RUNTIME_METADATA",
            "read_only": True,
            "runtime_proven": False,
        },
        "configuration": {
            "name": "FixtureConfiguration",
            "synonym": "Fixture Configuration",
            "version": "1.0",
            "vendor": "FixtureVendor",
        },
        "items": [
            {
                "id": "metadata-item",
                "category": "METADATA_PROPERTIES",
                "logical_target": "DOCUMENT.Test",
                "backend": "RUNTIME_METADATA",
                "collector_version": "1",
                "status": "PARTIAL",
                "evidence": {"scope": "RUNTIME_METADATA_STRUCTURE", "name": "Test"},
                "limitations": ["runtime metadata does not prove exact source bytes"],
            },
            {
                "id": "module-item",
                "category": "MODULE_SOURCE",
                "logical_target": "DOCUMENT.Test.ObjectModule",
                "backend": "RUNTIME_METADATA",
                "collector_version": "1",
                "status": "SKIPPED_OTHER_BACKEND",
                "limitations": ["item is assigned to another collection backend"],
            },
        ],
        "summary": {
            "collected": 0,
            "partial": 1,
            "unsupported": 0,
            "errors": 0,
            "skipped_other_backend": 1,
        },
    }
    manifest = {
        "schema_version": 1,
        "package_kind": "PROJECT_SNAPSHOT_EVIDENCE",
        "request_id": "req-chat-fixture",
        "runtime": {
            "backend": "RUNTIME_METADATA",
            "result_file": "runtime-evidence.json",
            "collected": True,
        },
        "source_export": {
            "backend": "SOURCE_EXPORT",
            "status": "COLLECTED_OBJECT_GRANULARITY",
            "granularity": "METADATA_OBJECT",
            "requested_items": [
                {
                    "id": "module-item",
                    "category": "MODULE_SOURCE",
                    "logical_target": "DOCUMENT.Test.ObjectModule",
                }
            ],
            "exported_objects": ["Документ.Test"],
            "unresolved_items": [],
            "designer_exit_code": 0,
            "dump_directory_in_package": "source/",
            "limitations": ["object-granular"],
        },
    }
    return {"plan": plan, "runtime": runtime, "manifest": manifest}


def write_package(path: Path, docs: dict[str, object], include_source: bool = True) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("collection-plan.json", json.dumps(docs["plan"], ensure_ascii=False))
        archive.writestr("runtime-evidence.json", json.dumps(docs["runtime"], ensure_ascii=False))
        archive.writestr("manifest.json", json.dumps(docs["manifest"], ensure_ascii=False))
        archive.writestr("source-objects.txt", "Документ.Test\n")
        archive.writestr("designer.log", "fixture\n")
        if include_source:
            archive.writestr("source/Documents/Test/Ext/ObjectModule.bsl", "Процедура Тест()\nКонецПроцедуры\n")


def has_reason(report: dict[str, object], item_id: str, reason_fragment: str) -> bool:
    for row in report.get("unresolved_items", []):
        if row.get("id") == item_id and reason_fragment in str(row.get("reason")):
            return True
    return False


def main() -> int:
    errors: list[str] = []

    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8-sig")
    evidence_text = (ROOT / "KNOWLEDGE/EVIDENCE_ACQUISITION.md").read_text(encoding="utf-8-sig")
    chat_text = (ROOT / "KNOWLEDGE/PROJECT_SNAPSHOT_CHAT_WORKFLOW.md").read_text(encoding="utf-8-sig")
    if "KNOWLEDGE/EVIDENCE_ACQUISITION.md" not in skill_text:
        errors.append("skill_must_route_missing_evidence_to_evidence_acquisition_owner")
    if "KNOWLEDGE/PROJECT_SNAPSHOT_CHAT_WORKFLOW.md" not in evidence_text:
        errors.append("evidence_acquisition_must_route_collectible_1c_gaps_to_chat_workflow")
    for required_token in (
        "Собрать пакет",
        "TOOLS/validate_project_snapshot_package.py",
        "SOURCE_REQUIRES_CONTENT_INSPECTION",
        "runtime_proven",
    ):
        if required_token not in chat_text:
            errors.append(f"chat_workflow_contract_missing:{required_token}")

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        docs = base_documents()
        valid_path = root / "valid.zip"
        write_package(valid_path, docs)
        valid = validate_package(valid_path, "req-chat-fixture")
        if valid.get("result") != "ACCEPTED":
            errors.append(f"valid_package_rejected:{valid.get('binding_errors')}")
        usable = {row["id"]: row for row in valid.get("usable_runtime_items", [])}
        if usable.get("metadata-item", {}).get("satisfies_minimum_fidelity") is not True:
            errors.append("bound_partial_runtime_observation_should_satisfy_partial_request")
        if valid.get("collector_implementation_runtime_proven") is not False:
            errors.append("fixture_runtime_proven_false_not_preserved")
        if "metadata-item" not in usable:
            errors.append("runtime_proven_false_must_not_discard_bound_runtime_observation")
        source_available = {row["id"] for row in valid.get("source_items_available", [])}
        if "module-item" not in source_available:
            errors.append("collected_source_item_not_exposed_for_inspection")
        if not has_reason(valid, "module-item", "SOURCE_REQUIRES_CONTENT_INSPECTION"):
            errors.append("source_item_must_not_be_auto_promoted_to_proof")

        receipt_path = root / "snapshot-binding-receipt.json"
        receipt = create_receipt(
            "TOOLS/validate_project_snapshot_package.py",
            [str(valid_path), "--expected-request-id", "req-chat-fixture"],
            [str(valid_path)],
            ["EVIDENCE:PROJECT_SNAPSHOT_PACKAGE_BINDING"],
            receipt_path,
        )
        receipt_check = verify_receipt(receipt_path, replay=True)
        if receipt.get("derived_result") != "PASS" or receipt_check.get("integrity_result") != "PASS":
            errors.append(f"project_snapshot_binding_receipt_failed:{receipt_check.get('errors')}")
        try:
            create_receipt(
                "TOOLS/validate_project_snapshot_package.py",
                [str(valid_path)],
                [str(valid_path)],
                ["EVIDENCE:PROJECT_SNAPSHOT_SOURCE_CONTENT"],
                root / "unsupported-source-proof-receipt.json",
            )
        except ValueError:
            pass
        else:
            errors.append("package_validator_must_not_claim_source_content_inspection")

        mismatch = copy.deepcopy(docs)
        mismatch["manifest"]["request_id"] = "wrong-request"
        mismatch_path = root / "mismatch.zip"
        write_package(mismatch_path, mismatch)
        mismatch_report = validate_package(mismatch_path, "req-chat-fixture")
        if mismatch_report.get("result") != "REJECTED":
            errors.append("request_id_mismatch_must_reject_package")

        wrong_config = copy.deepcopy(docs)
        wrong_config["runtime"]["configuration"]["name"] = "OtherConfiguration"
        wrong_config_path = root / "wrong-config.zip"
        write_package(wrong_config_path, wrong_config)
        wrong_config_report = validate_package(wrong_config_path)
        if wrong_config_report.get("result") != "REJECTED":
            errors.append("configuration_identity_mismatch_must_reject_package")

        runtime_error = copy.deepcopy(docs)
        runtime_error["runtime"]["items"][0]["status"] = "ERROR"
        runtime_error["runtime"]["items"][0].pop("evidence", None)
        runtime_error["runtime"]["summary"] = {
            "collected": 0,
            "partial": 0,
            "unsupported": 0,
            "errors": 1,
            "skipped_other_backend": 1,
        }
        runtime_error_path = root / "runtime-error.zip"
        write_package(runtime_error_path, runtime_error)
        runtime_error_report = validate_package(runtime_error_path)
        if runtime_error_report.get("result") != "ACCEPTED":
            errors.append("runtime_item_error_should_not_break_package_binding")
        if any(row.get("id") == "metadata-item" for row in runtime_error_report.get("usable_runtime_items", [])):
            errors.append("runtime_error_must_not_be_usable_evidence")
        if not has_reason(runtime_error_report, "metadata-item", "RUNTIME_ERROR"):
            errors.append("runtime_error_must_remain_unresolved")

        laundering = copy.deepcopy(docs)
        laundering["runtime"]["items"][1]["status"] = "PARTIAL"
        laundering["runtime"]["summary"] = {
            "collected": 0,
            "partial": 2,
            "unsupported": 0,
            "errors": 0,
            "skipped_other_backend": 0,
        }
        laundering_path = root / "laundering.zip"
        write_package(laundering_path, laundering)
        laundering_report = validate_package(laundering_path)
        if laundering_report.get("result") != "REJECTED":
            errors.append("runtime_must_not_claim_source_export_item")

        no_source_path = root / "no-source.zip"
        write_package(no_source_path, docs, include_source=False)
        no_source_report = validate_package(no_source_path)
        if no_source_report.get("result") != "REJECTED":
            errors.append("collected_source_status_without_source_dump_must_reject")

        extra_runtime = copy.deepcopy(docs)
        extra_runtime["runtime"]["items"].append(
            {
                "id": "extra-item",
                "category": "METADATA_PROPERTIES",
                "logical_target": "DOCUMENT.Extra",
                "backend": "RUNTIME_METADATA",
                "collector_version": "1",
                "status": "PARTIAL",
            }
        )
        extra_runtime["runtime"]["summary"] = {
            "collected": 0,
            "partial": 2,
            "unsupported": 0,
            "errors": 0,
            "skipped_other_backend": 1,
        }
        extra_path = root / "extra.zip"
        write_package(extra_path, extra_runtime)
        extra_report = validate_package(extra_path)
        if extra_report.get("result") != "REJECTED":
            errors.append("runtime_item_outside_plan_must_reject")

    out = {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "rule": (
            "SKILL routes resolvable evidence gaps through the existing evidence-acquisition owner into the ProjectSnapshot chat workflow. "
            "Returned ProjectSnapshot packages must bind to the active request/plan/configuration. "
            "Only matching successful runtime rows are usable at their observed fidelity; source bytes require inspection. "
            "Collector implementation runtime_proven status never launders unrelated claims."
        ),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
