#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from build_local_cleverence_reference_index import build_index


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def decode_xml(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def norm(value: str) -> str:
    return value.replace("\\", "/").lstrip("/")


def field_descriptor(element: ET.Element) -> dict:
    return {
        "name": (element.attrib.get("fieldName") or "").strip(),
        "type": (element.attrib.get("fieldType") or "").strip(),
        "tag": local_name(element.tag),
        "alias": (element.attrib.get("alias") or "").strip(),
        "dir_name": (element.attrib.get("dirName") or "").strip(),
    }


def container_fields(root: ET.Element, container_name: str) -> list[dict]:
    rows = []
    for child in list(root):
        if local_name(child.tag) != container_name:
            continue
        for element in child.iter():
            if element is child or element.attrib.get("fieldName") is None:
                continue
            row = field_descriptor(element)
            if row["name"]:
                rows.append(row)
    return rows


def all_fields(root: ET.Element) -> list[dict]:
    rows = []
    for element in root.iter():
        if element.attrib.get("fieldName") is None:
            continue
        row = field_descriptor(element)
        if row["name"]:
            rows.append(row)
    return rows


def operation_structure(root: ET.Element) -> dict:
    action_types = Counter()
    operation_targets = set()
    for element in root.iter():
        tag = local_name(element.tag)
        if tag.endswith("Action"):
            action_types[tag] += 1
            target = (element.attrib.get("operationName") or "").strip()
            if target:
                operation_targets.add(target)
    return {
        "parameters": container_fields(root, "Parameters"),
        "returns": container_fields(root, "Returns"),
        "action_types": dict(sorted(action_types.items())),
        "operation_targets": sorted(operation_targets),
    }


def raw_oracle(source: Path) -> tuple[dict, list[dict]]:
    rows = {}
    errors = []
    try:
        with zipfile.ZipFile(source, "r") as archive:
            for entry in archive.namelist():
                normalized = norm(entry)
                config_pos = normalized.find("Configuration/")
                if config_pos < 0:
                    continue
                canonical = normalized[config_pos:]
                if not canonical.startswith(("Configuration/Operations/", "Configuration/DocumentTypes/")):
                    continue
                if not canonical.lower().endswith((".mslx", ".xml")):
                    continue
                try:
                    data = archive.read(entry)
                    root = ET.fromstring(decode_xml(data))
                except (KeyError, ET.ParseError) as exc:
                    errors.append({"type": "RAW_XML_UNREADABLE", "path": canonical, "error": str(exc)})
                    continue
                tag = local_name(root.tag)
                if tag == "Operation":
                    runtime_name = (root.attrib.get("name") or "").strip()
                    if not runtime_name:
                        errors.append({"type": "RAW_OPERATION_NAME_MISSING", "path": canonical})
                        continue
                    identity = ("Operation", Path(canonical).stem, canonical)
                    structure = operation_structure(root)
                    value = {
                        "object_type": "Operation",
                        "name": Path(canonical).stem,
                        "runtime_name": runtime_name,
                        "action_count": sum(structure["action_types"].values()),
                        **structure,
                        "suggested_path": canonical,
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                elif tag == "DocumentType":
                    name = (root.attrib.get("name") or "").strip()
                    if not name:
                        errors.append({"type": "RAW_DOCUMENT_TYPE_NAME_MISSING", "path": canonical})
                        continue
                    fields = all_fields(root)
                    identity = ("DocumentType", name, canonical)
                    value = {
                        "object_type": "DocumentType",
                        "name": name,
                        "field_count": len(fields),
                        "fields": fields,
                        "suggested_path": canonical,
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                else:
                    continue
                previous = rows.get(identity)
                if previous is not None and previous != value:
                    errors.append({"type": "RAW_MIRROR_OR_DUPLICATE_DRIFT", "identity": identity})
                else:
                    rows[identity] = value
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append({"type": "SOURCE_UNREADABLE", "error": str(exc)})
    return rows, errors


def local_projection(index: dict) -> dict:
    rows = {}
    for key in ("operations", "document_types"):
        for row in index.get(key, []):
            canonical = norm(row.get("suggested_path") or "")
            identity = (row.get("object_type"), row.get("name"), canonical)
            if row.get("object_type") == "Operation":
                value = {
                    "object_type": "Operation",
                    "name": row.get("name"),
                    "runtime_name": row.get("runtime_name"),
                    "action_count": row.get("action_count"),
                    "parameters": row.get("parameters") or [],
                    "returns": row.get("returns") or [],
                    "action_types": row.get("action_types") or {},
                    "operation_targets": row.get("operation_targets") or [],
                    "suggested_path": canonical,
                    "sha256": row.get("sha256"),
                }
            else:
                value = {
                    "object_type": "DocumentType",
                    "name": row.get("name"),
                    "field_count": row.get("field_count"),
                    "fields": row.get("fields") or [],
                    "suggested_path": canonical,
                    "sha256": row.get("sha256"),
                }
            rows[identity] = value
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove local exact Cleverence structural-contract indexing against an independent raw XML oracle.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--projection-output")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not source.is_file():
        print(json.dumps({"result": "FAIL", "errors": [{"type": "SOURCE_MISSING", "path": str(source)}]}, ensure_ascii=False, indent=2))
        return 2

    index = build_index([source])
    oracle, errors = raw_oracle(source)
    local = local_projection(index)
    if index.get("result") != "PASS":
        errors.append({"type": "LOCAL_INDEX_FAILED", "details": index.get("errors")})

    missing = sorted(set(oracle) - set(local))
    unexpected = sorted(set(local) - set(oracle))
    mismatched = sorted(key for key in set(oracle) & set(local) if oracle[key] != local[key])
    if missing or unexpected or mismatched:
        errors.append({
            "type": "STRUCTURAL_CONTRACT_ORACLE_MISMATCH",
            "missing": missing[:50],
            "unexpected": unexpected[:50],
            "mismatched": mismatched[:50],
        })

    operation_rows = [row for row in oracle.values() if row["object_type"] == "Operation"]
    document_rows = [row for row in oracle.values() if row["object_type"] == "DocumentType"]
    coverage = {
        "operations": len(operation_rows),
        "document_types": len(document_rows),
        "operations_with_parameters": sum(bool(row.get("parameters")) for row in operation_rows),
        "operations_with_returns": sum(bool(row.get("returns")) for row in operation_rows),
        "operations_with_operation_targets": sum(bool(row.get("operation_targets")) for row in operation_rows),
        "distinct_action_types": sorted({tag for row in operation_rows for tag in row.get("action_types", {})}),
        "document_types_with_fields": sum(bool(row.get("fields")) for row in document_rows),
    }
    for field in ("operations_with_parameters", "operations_with_returns", "operations_with_operation_targets", "document_types_with_fields"):
        if not coverage[field]:
            errors.append({"type": "STRUCTURAL_COVERAGE_CLASS_EMPTY", "class": field})
    if len(coverage["distinct_action_types"]) < 2:
        errors.append({"type": "STRUCTURAL_COVERAGE_CLASS_EMPTY", "class": "action_type_variety"})

    projection = {
        "schema_version": 1,
        "coverage": coverage,
        "object_count": len(oracle),
        "oracle_equals_local": not missing and not unexpected and not mismatched,
        "rule": "Exact-source structural contracts include Operation artifact/runtime identity, Parameters, Returns, Action type inventory, referenced operation targets and DocumentType field declarations. This gate does not infer Action branch semantics or runtime parser behavior.",
    }
    if args.projection_output:
        Path(args.projection_output).write_text(json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({"result": "PASS" if not errors else "FAIL", "errors": errors, "projection": projection}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
