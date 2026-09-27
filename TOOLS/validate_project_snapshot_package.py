#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

MAX_JSON_BYTES = 10 * 1024 * 1024
FIDELITY_RANK = {"PARTIAL": 1, "FULL": 2}
RUNTIME_STATUS_FIDELITY = {"PARTIAL": "PARTIAL", "COLLECTED": "FULL"}


class PackageReadError(Exception):
    pass


def load_json_strict(text: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=reject_duplicates)


class PackageView:
    def __init__(self, path: Path):
        self.path = path
        self._zip: zipfile.ZipFile | None = None
        if path.is_dir():
            self.kind = "DIRECTORY"
        elif path.is_file() and zipfile.is_zipfile(path):
            self.kind = "ZIP"
            self._zip = zipfile.ZipFile(path, "r")
        else:
            raise PackageReadError("package_must_be_zip_or_directory")

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()

    def names(self) -> list[str]:
        if self.kind == "DIRECTORY":
            return [p.relative_to(self.path).as_posix() for p in self.path.rglob("*") if p.is_file()]
        assert self._zip is not None
        return [info.filename for info in self._zip.infolist() if not info.is_dir()]

    def read_text(self, name: str) -> str:
        if self.kind == "DIRECTORY":
            target = self.path / Path(*PurePosixPath(name).parts)
            if not target.is_file():
                raise PackageReadError(f"missing_file:{name}")
            if target.stat().st_size > MAX_JSON_BYTES:
                raise PackageReadError(f"file_too_large:{name}")
            return target.read_text(encoding="utf-8-sig")

        assert self._zip is not None
        infos = [info for info in self._zip.infolist() if info.filename == name]
        if not infos:
            raise PackageReadError(f"missing_file:{name}")
        if len(infos) != 1:
            raise PackageReadError(f"duplicate_zip_entry:{name}")
        info = infos[0]
        if info.file_size > MAX_JSON_BYTES:
            raise PackageReadError(f"file_too_large:{name}")
        return self._zip.read(info).decode("utf-8-sig")


def _known_expected(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.startswith("<"):
        return None
    if text.casefold() in {"unknown", "неизвестно", "none", "null", "n/a"}:
        return None
    return text


def _selected_backend(row: dict[str, Any]) -> str | None:
    selected = row.get("selected")
    if not isinstance(selected, dict):
        return None
    backend = selected.get("backend")
    return str(backend) if backend else None


def _plan_items(plan: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    rows = plan.get("item_plan")
    if not isinstance(rows, list):
        errors.append("plan.item_plan_required")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"plan.item_not_object:{index}")
            continue
        item_id = row.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"plan.item_missing_id:{index}")
            continue
        if item_id in result:
            errors.append(f"plan.duplicate_item_id:{item_id}")
            continue
        if not isinstance(row.get("category"), str) or not row.get("category"):
            errors.append(f"plan.item_missing_category:{item_id}")
        if not isinstance(row.get("logical_target"), str) or not row.get("logical_target"):
            errors.append(f"plan.item_missing_logical_target:{item_id}")
        result[item_id] = row
    return result


def _runtime_items(runtime: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    rows = runtime.get("items")
    if not isinstance(rows, list):
        errors.append("runtime.items_required")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"runtime.item_not_object:{index}")
            continue
        item_id = row.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"runtime.item_missing_id:{index}")
            continue
        if item_id in result:
            errors.append(f"runtime.duplicate_item_id:{item_id}")
            continue
        result[item_id] = row
    return result


def _summary_matches(runtime: dict[str, Any], runtime_items: dict[str, dict[str, Any]], errors: list[str]) -> None:
    summary = runtime.get("summary")
    if not isinstance(summary, dict):
        errors.append("runtime.summary_required")
        return
    statuses = [str(row.get("status") or "") for row in runtime_items.values()]
    expected = {
        "collected": sum(status == "COLLECTED" for status in statuses),
        "partial": sum(status == "PARTIAL" for status in statuses),
        "errors": sum(status == "ERROR" for status in statuses),
        "skipped_other_backend": sum(status == "SKIPPED_OTHER_BACKEND" for status in statuses),
        "unsupported": sum(
            status not in {"COLLECTED", "PARTIAL", "ERROR", "SKIPPED_OTHER_BACKEND"}
            for status in statuses
        ),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"runtime.summary_mismatch:{key}:expected={value}:actual={summary.get(key)}")


def _safe_package_names(names: list[str], errors: list[str]) -> None:
    counts = Counter(names)
    for name, count in counts.items():
        if count > 1:
            errors.append(f"duplicate_package_entry:{name}")
        posix = PurePosixPath(name)
        if posix.is_absolute() or ".." in posix.parts or name.startswith(("/", "\\")):
            errors.append(f"unsafe_package_entry:{name}")


def _load_json(view: PackageView, name: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        value = load_json_strict(view.read_text(name))
    except Exception as exc:
        errors.append(f"invalid_json:{name}:{exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"json_root_must_be_object:{name}")
        return None
    return value


def validate_package(package_path: Path, expected_request_id: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    unresolved: list[dict[str, Any]] = []
    usable_runtime: list[dict[str, Any]] = []
    source_available: list[dict[str, Any]] = []
    collector_runtime_proven: bool | None = None

    try:
        view = PackageView(package_path)
    except Exception as exc:
        return {
            "result": "REJECTED",
            "coverage": "INVALID",
            "binding_errors": [str(exc)],
            "warnings": [],
            "usable_runtime_items": [],
            "source_items_available": [],
            "unresolved_items": [],
            "collector_implementation_runtime_proven": None,
        }

    try:
        names = view.names()
        _safe_package_names(names, errors)

        plan = _load_json(view, "collection-plan.json", errors)
        manifest = _load_json(view, "manifest.json", errors)
        runtime = _load_json(view, "runtime-evidence.json", errors)
        if plan is None or manifest is None or runtime is None:
            return {
                "result": "REJECTED",
                "coverage": "INVALID",
                "binding_errors": errors,
                "warnings": warnings,
                "usable_runtime_items": usable_runtime,
                "source_items_available": source_available,
                "unresolved_items": unresolved,
                "collector_implementation_runtime_proven": collector_runtime_proven,
            }

        if plan.get("schema_version") != 1:
            errors.append("plan.schema_version_must_be_1")
        if manifest.get("schema_version") != 1:
            errors.append("manifest.schema_version_must_be_1")
        if runtime.get("schema_version") != 1:
            errors.append("runtime.schema_version_must_be_1")
        if manifest.get("package_kind") != "PROJECT_SNAPSHOT_EVIDENCE":
            errors.append(f"manifest.bad_package_kind:{manifest.get('package_kind')}")

        request_id = plan.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            errors.append("plan.request_id_required")
        if manifest.get("request_id") != request_id:
            errors.append("manifest.request_id_mismatch")
        if runtime.get("request_id") != request_id:
            errors.append("runtime.request_id_mismatch")
        if expected_request_id is not None and request_id != expected_request_id:
            errors.append(f"expected_request_id_mismatch:expected={expected_request_id}:actual={request_id}")

        runtime_manifest = manifest.get("runtime")
        if not isinstance(runtime_manifest, dict):
            errors.append("manifest.runtime_required")
        else:
            if runtime_manifest.get("backend") != "RUNTIME_METADATA":
                errors.append("manifest.runtime.backend_must_be_RUNTIME_METADATA")
            if runtime_manifest.get("result_file") != "runtime-evidence.json":
                errors.append("manifest.runtime.result_file_mismatch")
            if runtime_manifest.get("collected") is not True:
                errors.append("manifest.runtime.collected_must_be_true")

        collector = runtime.get("collector")
        if not isinstance(collector, dict):
            errors.append("runtime.collector_required")
        else:
            if collector.get("name") != "ProjectSnapshotRuntimeCollector":
                errors.append(f"runtime.collector.name_unexpected:{collector.get('name')}")
            if collector.get("backend") != "RUNTIME_METADATA":
                errors.append("runtime.collector.backend_must_be_RUNTIME_METADATA")
            if collector.get("read_only") is not True:
                errors.append("runtime.collector.read_only_must_be_true")
            collector_runtime_proven = collector.get("runtime_proven") if isinstance(collector.get("runtime_proven"), bool) else None
            if collector_runtime_proven is None:
                errors.append("runtime.collector.runtime_proven_must_be_boolean")

        plan_items = _plan_items(plan, errors)
        runtime_items = _runtime_items(runtime, errors)
        extra_runtime = sorted(set(runtime_items) - set(plan_items))
        if extra_runtime:
            errors.append(f"runtime.items_not_in_plan:{','.join(extra_runtime)}")
        missing_runtime_rows = sorted(set(plan_items) - set(runtime_items))
        if missing_runtime_rows:
            errors.append(f"runtime.plan_items_missing:{','.join(missing_runtime_rows)}")

        _summary_matches(runtime, runtime_items, errors)

        configuration = runtime.get("configuration")
        baseline = plan.get("baseline_expectation")
        if baseline is not None and not isinstance(baseline, dict):
            errors.append("plan.baseline_expectation_must_be_object")
            baseline = None
        if isinstance(baseline, dict):
            if not isinstance(configuration, dict):
                errors.append("runtime.configuration_required_for_baseline_binding")
            else:
                expected_name = _known_expected(baseline.get("configuration_name"))
                expected_version = _known_expected(baseline.get("configuration_version"))
                if expected_name is not None and str(configuration.get("name") or "") != expected_name:
                    errors.append(
                        f"configuration_name_mismatch:expected={expected_name}:actual={configuration.get('name')}"
                    )
                if expected_version is not None and str(configuration.get("version") or "") != expected_version:
                    errors.append(
                        f"configuration_version_mismatch:expected={expected_version}:actual={configuration.get('version')}"
                    )
        else:
            warnings.append("plan_has_no_baseline_expectation; configuration binding is limited to request_id")

        for item_id, row in plan_items.items():
            runtime_row = runtime_items.get(item_id)
            backend = _selected_backend(row)
            if runtime_row is None:
                continue
            if runtime_row.get("category") != row.get("category"):
                errors.append(f"runtime.category_mismatch:{item_id}")
            if runtime_row.get("logical_target") != row.get("logical_target"):
                errors.append(f"runtime.logical_target_mismatch:{item_id}")
            if runtime_row.get("backend") != "RUNTIME_METADATA":
                errors.append(f"runtime.backend_marker_mismatch:{item_id}")

            status = str(runtime_row.get("status") or "")
            if backend != "RUNTIME_METADATA":
                if status != "SKIPPED_OTHER_BACKEND":
                    errors.append(f"runtime.non_runtime_item_not_skipped:{item_id}:{status}")
                if backend is None:
                    unresolved.append({"id": item_id, "reason": "PLAN_UNSUPPORTED", "backend": None})
                elif backend not in {"SOURCE_EXPORT"}:
                    unresolved.append({"id": item_id, "reason": "BACKEND_NOT_IN_PACKAGE", "backend": backend})
                continue

            fidelity = RUNTIME_STATUS_FIDELITY.get(status)
            if fidelity is None:
                unresolved.append({"id": item_id, "reason": f"RUNTIME_{status or 'MISSING_STATUS'}", "backend": backend})
                continue
            minimum = str(row.get("minimum_fidelity") or "FULL")
            satisfies = FIDELITY_RANK.get(fidelity, 0) >= FIDELITY_RANK.get(minimum, 99)
            usable_runtime.append(
                {
                    "id": item_id,
                    "category": row.get("category"),
                    "logical_target": row.get("logical_target"),
                    "status": status,
                    "fidelity": fidelity,
                    "minimum_fidelity": minimum,
                    "satisfies_minimum_fidelity": satisfies,
                    "claim_boundary": "BOUND_RUNTIME_OBSERVATION_ONLY",
                }
            )
            if not satisfies:
                unresolved.append(
                    {
                        "id": item_id,
                        "reason": f"RUNTIME_FIDELITY_{fidelity}_BELOW_{minimum}",
                        "backend": backend,
                    }
                )

        source_rows = {item_id: row for item_id, row in plan_items.items() if _selected_backend(row) == "SOURCE_EXPORT"}
        source_manifest = manifest.get("source_export")
        if not isinstance(source_manifest, dict):
            errors.append("manifest.source_export_required")
        else:
            if source_manifest.get("backend") != "SOURCE_EXPORT":
                errors.append("manifest.source_export.backend_must_be_SOURCE_EXPORT")
            requested_items = source_manifest.get("requested_items")
            if not isinstance(requested_items, list):
                errors.append("manifest.source_export.requested_items_required")
                requested_items = []
            manifest_source: dict[str, dict[str, Any]] = {}
            for index, item in enumerate(requested_items):
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item.get("id"):
                    errors.append(f"manifest.source_export.bad_requested_item:{index}")
                    continue
                item_id = item["id"]
                if item_id in manifest_source:
                    errors.append(f"manifest.source_export.duplicate_requested_item:{item_id}")
                    continue
                manifest_source[item_id] = item
            if set(manifest_source) != set(source_rows):
                errors.append(
                    "manifest.source_export.requested_items_mismatch:"
                    f"plan={sorted(source_rows)}:manifest={sorted(manifest_source)}"
                )
            for item_id, item in manifest_source.items():
                planned = source_rows.get(item_id)
                if planned is None:
                    continue
                if item.get("category") != planned.get("category"):
                    errors.append(f"manifest.source_export.category_mismatch:{item_id}")
                if item.get("logical_target") != planned.get("logical_target"):
                    errors.append(f"manifest.source_export.logical_target_mismatch:{item_id}")

            unresolved_targets = source_manifest.get("unresolved_items") or []
            if not isinstance(unresolved_targets, list):
                errors.append("manifest.source_export.unresolved_items_must_be_array")
                unresolved_targets = []
            source_targets = {str(row.get("logical_target") or "") for row in source_rows.values()}
            unknown_unresolved_targets = sorted(str(x) for x in unresolved_targets if str(x) not in source_targets)
            if unknown_unresolved_targets:
                errors.append(
                    "manifest.source_export.unresolved_target_not_in_plan:"
                    + ",".join(unknown_unresolved_targets)
                )

            status = str(source_manifest.get("status") or "")
            source_files = [name for name in names if name.startswith("source/") and not name.endswith("/")]
            if source_rows:
                if status.startswith("COLLECTED"):
                    if not source_files:
                        errors.append("source_status_collected_but_dump_missing")
                    for item_id, row in source_rows.items():
                        if str(row.get("logical_target") or "") in {str(x) for x in unresolved_targets}:
                            unresolved.append({"id": item_id, "reason": "SOURCE_TARGET_UNRESOLVED", "backend": "SOURCE_EXPORT"})
                            continue
                        source_available.append(
                            {
                                "id": item_id,
                                "category": row.get("category"),
                                "logical_target": row.get("logical_target"),
                                "status": "SOURCE_AVAILABLE_FOR_INSPECTION",
                                "claim_boundary": "SOURCE_BYTES_MUST_BE_INSPECTED_BEFORE_PROOF",
                            }
                        )
                        unresolved.append(
                            {
                                "id": item_id,
                                "reason": "SOURCE_REQUIRES_CONTENT_INSPECTION",
                                "backend": "SOURCE_EXPORT",
                            }
                        )
                    exit_code = source_manifest.get("designer_exit_code")
                    if isinstance(exit_code, (int, float)) and exit_code != 0:
                        errors.append(f"source_collected_with_nonzero_designer_exit:{exit_code}")
                else:
                    for item_id in source_rows:
                        unresolved.append({"id": item_id, "reason": f"SOURCE_{status or 'MISSING_STATUS'}", "backend": "SOURCE_EXPORT"})
            elif status not in {"NOT_REQUESTED", ""}:
                warnings.append(f"source_export_status_without_source_plan:{status}")

        dedup_unresolved: list[dict[str, Any]] = []
        seen_unresolved: set[tuple[str, str]] = set()
        for row in unresolved:
            key = (str(row.get("id")), str(row.get("reason")))
            if key not in seen_unresolved:
                seen_unresolved.add(key)
                dedup_unresolved.append(row)
        unresolved = dedup_unresolved

        result = "REJECTED" if errors else "ACCEPTED"
        coverage = "INVALID" if errors else ("COMPLETE_FOR_AUTOMATIC_VALIDATION" if not unresolved else "PARTIAL")
        return {
            "result": result,
            "coverage": coverage,
            "request_id": request_id,
            "package_kind": manifest.get("package_kind"),
            "configuration": runtime.get("configuration"),
            "binding_errors": errors,
            "warnings": warnings,
            "usable_runtime_items": usable_runtime,
            "source_items_available": source_available,
            "unresolved_items": unresolved,
            "collector_implementation_runtime_proven": collector_runtime_proven,
            "proof_boundary": (
                "ACCEPTED validates package/request/plan/configuration binding and per-item provenance only. "
                "Bound runtime observations may support the matching item at their observed fidelity even when "
                "collector.runtime_proven is false; that flag is implementation-level and never promotes unrelated claims. "
                "SOURCE_EXPORT items remain unresolved until the returned source bytes are inspected and matched to the item."
            ),
        }
    finally:
        view.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a ProjectSnapshotCollector ZIP/directory before using returned evidence in chat or analysis."
    )
    parser.add_argument("package", type=Path)
    parser.add_argument("--expected-request-id")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 3 when the package is bound but still has unresolved evidence items.",
    )
    args = parser.parse_args()

    report = validate_package(args.package, args.expected_request_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("result") != "ACCEPTED":
        return 2
    if args.strict and report.get("unresolved_items"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
