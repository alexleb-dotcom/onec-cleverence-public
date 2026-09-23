#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from reference_locator import load_catalogs, locate
from build_local_bsl_reference_index import build_index as build_bsl_index
from build_local_cleverence_reference_index import build_index as build_cleverence_index

MODULE_RX = re.compile(r"(?:^|/)(CommonModules/([^/]+)/Ext/Module\.bsl)$", re.IGNORECASE)


def normalized_path(value: str | None) -> str:
    return (value or "").replace("\\", "/").lstrip("/")


def decode_xml(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def raw_bsl_modules(source_zip: Path) -> tuple[set[str], dict[str, set[str]], list[dict]]:
    modules: set[str] = set()
    paths: dict[str, set[str]] = {}
    errors = []
    try:
        with zipfile.ZipFile(source_zip, "r") as archive:
            for entry in archive.namelist():
                match = MODULE_RX.search(normalized_path(entry))
                if not match:
                    continue
                canonical_path = match.group(1)
                module = match.group(2)
                modules.add(module)
                paths.setdefault(module, set()).add(canonical_path)
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append({"type": "BSL_SOURCE_ZIP_UNREADABLE", "error": str(exc)})
    return modules, paths, errors


def raw_cleverence_oracle(source_zip: Path) -> tuple[set[tuple[str, str]], dict[tuple[str, str], set[str]], list[dict]]:
    objects: set[tuple[str, str]] = set()
    paths: dict[tuple[str, str], set[str]] = {}
    errors = []
    try:
        with zipfile.ZipFile(source_zip, "r") as archive:
            for entry in archive.namelist():
                normalized = normalized_path(entry)
                config_pos = normalized.find("Configuration/")
                if config_pos < 0:
                    continue
                canonical = normalized[config_pos:]
                if not canonical.startswith(("Configuration/Operations/", "Configuration/DocumentTypes/")):
                    continue
                if not canonical.lower().endswith((".mslx", ".xml")):
                    continue
                try:
                    root = ET.fromstring(decode_xml(archive.read(entry)))
                except (KeyError, ET.ParseError) as exc:
                    errors.append({"type": "CLEVERENCE_ORACLE_XML_UNREADABLE", "path": canonical, "error": str(exc)})
                    continue

                tag = local_name(root.tag)
                runtime_name = (root.attrib.get("name") or "").strip()
                if tag == "Operation":
                    object_type = "Operation"
                    if not runtime_name:
                        errors.append({"type": "CLEVERENCE_ORACLE_RUNTIME_NAME_MISSING", "path": canonical, "object_type": object_type})
                        continue
                    name = Path(canonical).stem
                elif tag == "DocumentType":
                    object_type = "DocumentType"
                    name = runtime_name
                    if not name:
                        errors.append({"type": "CLEVERENCE_ORACLE_NAME_MISSING", "path": canonical, "object_type": object_type})
                        continue
                else:
                    continue

                key = (object_type, name)
                objects.add(key)
                paths.setdefault(key, set()).add(canonical)
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append({"type": "CLEVERENCE_SOURCE_ZIP_UNREADABLE", "error": str(exc)})
    return objects, paths, errors


def catalog_candidates(catalog: dict) -> list[dict]:
    rows = []
    catalog_template = catalog.get("request_path_template")
    catalog_type = catalog.get("request_object_type")
    if not catalog_type and (catalog_template or "").replace("\\", "/").startswith("CommonModules/"):
        catalog_type = "CommonModule"
    for entry in catalog.get("entries", []):
        explicit = entry.get("request_candidates") or []
        if explicit:
            for raw in explicit:
                if raw.get("name"):
                    rows.append({
                        "entry_id": entry.get("id"),
                        "object_type": raw.get("object_type") or entry.get("request_object_type") or catalog_type or "UNKNOWN",
                        "name": raw["name"],
                        "suggested_path": raw.get("suggested_path"),
                    })
            continue
        names = list(entry.get("candidate_names") or entry.get("candidate_modules") or [])
        template = entry.get("request_path_template")
        if template is None:
            template = catalog_template
        object_type = entry.get("request_object_type") or catalog_type or "UNKNOWN"
        for name in names:
            rows.append({
                "entry_id": entry.get("id"),
                "object_type": object_type,
                "name": name,
                "suggested_path": template.format(module=name, name=name) if template else None,
            })
    return rows


def candidate_grounded(family: str, candidate: dict, grounding: dict) -> tuple[bool, str | None]:
    object_type = candidate.get("object_type") or "UNKNOWN"
    name = candidate.get("name") or ""
    suggested = normalized_path(candidate.get("suggested_path"))
    if family in {"BSP", "TYPICAL_ONEC"}:
        if object_type != "CommonModule" or name not in grounding[family]["names"]:
            return False, "name_not_in_exact_source"
        if suggested and suggested not in grounding[family]["paths"].get(name, set()):
            return False, "suggested_path_not_in_exact_source"
        return True, None
    if family == "CLEVERENCE":
        key = (object_type, name)
        if key not in grounding[family]["names"]:
            return False, "name_not_in_exact_source"
        if suggested and suggested not in grounding[family]["paths"].get(key, set()):
            return False, "suggested_path_not_in_exact_source"
        return True, None
    return False, "unknown_family"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare public discovery behavior with exact retained/user-supplied source across INTERNAL_FULL and SHAREABLE_CORE runtimes.")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--bsp-source", required=True)
    parser.add_argument("--typical-source", required=True)
    parser.add_argument("--cleverence-source", required=True)
    parser.add_argument("--catalog-root", default=str(ROOT / "REFERENCE/CATALOGS"))
    parser.add_argument("--projection-output")
    args = parser.parse_args()

    paths = {
        "cases": Path(args.cases).resolve(),
        "BSP": Path(args.bsp_source).resolve(),
        "TYPICAL_ONEC": Path(args.typical_source).resolve(),
        "CLEVERENCE": Path(args.cleverence_source).resolve(),
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        print(json.dumps({"result": "FAIL", "errors": [{"type": "INPUT_MISSING", "paths": missing}]}, ensure_ascii=False, indent=2))
        return 2

    errors = []
    cases_payload = json.loads(paths["cases"].read_text(encoding="utf-8-sig"))
    cases = cases_payload.get("cases") or []
    catalogs = load_catalogs(Path(args.catalog_root).resolve())

    bsp_raw_names, bsp_raw_paths, bsp_raw_errors = raw_bsl_modules(paths["BSP"])
    typical_raw_names, typical_raw_paths, typical_raw_errors = raw_bsl_modules(paths["TYPICAL_ONEC"])
    cleverence_raw_names, cleverence_raw_paths, cleverence_raw_errors = raw_cleverence_oracle(paths["CLEVERENCE"])
    errors.extend({"family": "BSP", **row} for row in bsp_raw_errors)
    errors.extend({"family": "TYPICAL_ONEC", **row} for row in typical_raw_errors)
    errors.extend({"family": "CLEVERENCE", **row} for row in cleverence_raw_errors)

    bsp_local = build_bsl_index([paths["BSP"]], [])
    typical_local = build_bsl_index([paths["TYPICAL_ONEC"]], [])
    cleverence_local = build_cleverence_index([paths["CLEVERENCE"]])
    if cleverence_local.get("result") != "PASS":
        errors.append({"family": "CLEVERENCE", "type": "LOCAL_EXACT_INDEX_FAILED", "details": cleverence_local.get("errors")})

    bsp_local_modules = {row.get("module") for row in bsp_local.get("definitions", []) if row.get("module")}
    typical_local_modules = {row.get("module") for row in typical_local.get("definitions", []) if row.get("module")}
    cleverence_local_objects = {
        (row.get("object_type"), row.get("name"))
        for key in ("operations", "document_types")
        for row in cleverence_local.get(key, [])
        if row.get("object_type") and row.get("name")
    }
    cleverence_local_paths = {
        (row.get("object_type"), row.get("name"), normalized_path(row.get("suggested_path")))
        for key in ("operations", "document_types")
        for row in cleverence_local.get(key, [])
        if row.get("object_type") and row.get("name") and row.get("suggested_path")
    }
    cleverence_oracle_paths = {
        (object_type, name, path)
        for (object_type, name), values in cleverence_raw_paths.items()
        for path in values
    }
    cleverence_missing_local = sorted(cleverence_raw_names - cleverence_local_objects)
    cleverence_unexpected_local = sorted(cleverence_local_objects - cleverence_raw_names)
    cleverence_missing_local_paths = sorted(cleverence_oracle_paths - cleverence_local_paths)
    if cleverence_missing_local or cleverence_unexpected_local or cleverence_missing_local_paths:
        errors.append({
            "family": "CLEVERENCE",
            "type": "LOCAL_EXACT_INDEX_ORACLE_MISMATCH",
            "missing_objects": cleverence_missing_local[:50],
            "unexpected_objects": cleverence_unexpected_local[:50],
            "missing_paths": cleverence_missing_local_paths[:50],
        })

    grounding = {
        "BSP": {"names": bsp_raw_names, "paths": bsp_raw_paths, "local_names": bsp_local_modules},
        "TYPICAL_ONEC": {"names": typical_raw_names, "paths": typical_raw_paths, "local_names": typical_local_modules},
        "CLEVERENCE": {"names": cleverence_raw_names, "paths": cleverence_raw_paths, "local_names": cleverence_local_objects},
    }

    family_grounding = {}
    for family in ("BSP", "TYPICAL_ONEC", "CLEVERENCE"):
        family_catalogs = [catalog for catalog in catalogs if catalog.get("source_family") == family]
        candidates = [candidate for catalog in family_catalogs for candidate in catalog_candidates(catalog)]
        ungrounded = []
        for candidate in candidates:
            ok, reason = candidate_grounded(family, candidate, grounding)
            if not ok:
                ungrounded.append({**candidate, "reason": reason})
        if not family_catalogs:
            errors.append({"family": family, "type": "PUBLIC_DISCOVERY_CATALOG_MISSING"})
        if ungrounded:
            errors.append({"family": family, "type": "PUBLIC_CANDIDATE_NOT_GROUNDED_IN_EXACT_SOURCE", "candidates": ungrounded[:100]})
        family_grounding[family] = {
            "catalog_count": len(family_catalogs),
            "public_candidate_count": len(candidates),
            "ungrounded_count": len(ungrounded),
            "exact_source_object_count": len(grounding[family]["names"]),
            "local_exact_index_object_count": len(grounding[family]["local_names"]),
        }

    case_results = []
    for case in cases:
        case_id = case.get("id") or "<missing-id>"
        family = case.get("family")
        query = case.get("query") or ""
        object_type = case.get("object_type") or "UNKNOWN"
        expected = set(case.get("expected_any") or [])
        locator = locate(query, catalogs, int(case.get("limit") or 50))
        matches = [row for row in locator.get("matches", []) if row.get("source_family") == family]
        candidates = []
        proof_gate = bool(matches)
        for match in matches:
            if match.get("role") != "DISCOVERY_ONLY" or not match.get("proof_required_after_locator_match"):
                proof_gate = False
            for candidate in match.get("request_candidates", []):
                row = {
                    "object_type": candidate.get("object_type") or "UNKNOWN",
                    "name": candidate.get("name") or "",
                    "suggested_path": normalized_path(candidate.get("suggested_path")) or None,
                }
                if row not in candidates:
                    candidates.append(row)

        expected_hits = [row for row in candidates if row["object_type"] == object_type and row["name"] in expected]
        ungrounded = []
        for candidate in candidates:
            ok, reason = candidate_grounded(family, candidate, grounding) if family in grounding else (False, "unknown_family")
            if not ok:
                ungrounded.append({**candidate, "reason": reason})

        local_names = grounding.get(family, {}).get("local_names", set())
        if family == "CLEVERENCE":
            expected_local = any((object_type, name) in local_names for name in expected)
        else:
            expected_local = any(name in local_names for name in expected)

        passed = bool(expected_hits) and not ungrounded and proof_gate and expected_local
        if not passed:
            errors.append({
                "case": case_id,
                "type": "DISCOVERY_EQUIVALENCE_CASE_FAILED",
                "family": family,
                "expected": sorted(expected),
                "expected_hits": expected_hits,
                "proof_gate": proof_gate,
                "expected_in_local_exact_index": expected_local,
                "ungrounded": ungrounded,
                "returned_candidates": candidates,
            })
        case_results.append({
            "id": case_id,
            "family": family,
            "query": query,
            "object_type": object_type,
            "expected_any": sorted(expected),
            "expected_hits": expected_hits,
            "returned_candidates": candidates,
            "proof_gate": proof_gate,
            "expected_in_local_exact_index": expected_local,
            "ungrounded_count": len(ungrounded),
            "pass": passed,
        })

    projection = {
        "schema_version": 1,
        "family_grounding": family_grounding,
        "cases": case_results,
        "rule": "A public locator is equivalent for these migration cases only when it finds the intended evidence class, every returned candidate is grounded in exact supplied source, the intended target survives local exact indexing, and the locator still requires exact-source/runtime proof instead of promoting hints to contracts.",
    }
    projection_text = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    projection_sha256 = hashlib.sha256(projection_text.encode("utf-8")).hexdigest()
    if args.projection_output:
        Path(args.projection_output).write_text(json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = {
        "result": "PASS" if not errors else "FAIL",
        "case_count": len(case_results),
        "projection_sha256": projection_sha256,
        "errors": errors,
        "projection": projection,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
