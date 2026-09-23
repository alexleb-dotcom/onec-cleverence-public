#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_corpus import inventory_paths, analyzable_entries


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def decode_xml(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise UnicodeDecodeError("utf-8", data, 0, min(1, len(data)), "unsupported text encoding")


def canonical_request_path(semantic_path: str) -> str:
    normalized = semantic_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("Configuration/"):
        return normalized
    if normalized.startswith(("Operations/", "DocumentTypes/", "Metadata/")):
        return f"Configuration/{normalized}"
    return normalized


def fingerprint(path: Path) -> dict:
    if path.is_file():
        data = path.read_bytes()
        return {"kind": "file", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return {"kind": "directory"}


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


def all_declared_fields(root: ET.Element) -> list[dict]:
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


def build_index(sources: list[Path]) -> dict:
    corpus = inventory_paths(sources)
    errors = []
    for warning in corpus.get("warnings", []):
        errors.append({"type": "ARTIFACT_INVENTORY_INCOMPLETE", "warning": warning})

    operations = []
    document_types = []
    for semantic_path, data, origin, row in analyzable_entries(corpus):
        semantic = semantic_path.replace("\\", "/")
        relevant_operation = semantic.startswith("Operations/")
        relevant_document_type = semantic.startswith("DocumentTypes/")
        if not (relevant_operation or relevant_document_type):
            continue

        try:
            root = ET.fromstring(decode_xml(data))
        except (UnicodeDecodeError, ET.ParseError) as exc:
            errors.append({
                "type": "EXACT_SOURCE_XML_UNREADABLE",
                "semantic_path": semantic,
                "physical_path": row.physical_path,
                "error": str(exc),
            })
            continue

        root_tag = local_name(root.tag)
        sha256 = hashlib.sha256(data).hexdigest()
        common = {
            "semantic_path": semantic,
            "suggested_path": canonical_request_path(semantic),
            "physical_path": row.physical_path,
            "sha256": sha256,
        }

        if relevant_operation:
            if root_tag != "Operation":
                continue
            runtime_name = root.attrib.get("name", "").strip()
            if not runtime_name:
                errors.append({"type": "OPERATION_RUNTIME_NAME_MISSING", "semantic_path": semantic, "physical_path": row.physical_path})
                continue
            reference_name = Path(semantic).stem
            structure = operation_structure(root)
            operations.append({
                "object_type": "Operation",
                "name": reference_name,
                "runtime_name": runtime_name,
                "action_count": sum(structure["action_types"].values()),
                **structure,
                **common,
            })

        if relevant_document_type:
            if root_tag != "DocumentType":
                continue
            name = root.attrib.get("name", "").strip()
            if not name:
                errors.append({"type": "DOCUMENT_TYPE_NAME_MISSING", "semantic_path": semantic, "physical_path": row.physical_path})
                continue
            fields = all_declared_fields(root)
            document_types.append({
                "object_type": "DocumentType",
                "name": name,
                "field_count": len(fields),
                "fields": fields,
                **common,
            })

    def dedupe(rows: list[dict]) -> list[dict]:
        unique = {}
        for item in rows:
            key = (item["object_type"], item["name"], item["semantic_path"], item["sha256"])
            unique.setdefault(key, item)
        return sorted(unique.values(), key=lambda item: (item["name"].casefold(), item["semantic_path"].casefold()))

    operations = dedupe(operations)
    document_types = dedupe(document_types)
    if not operations:
        errors.append({"type": "NO_OPERATIONS_FOUND"})
    if not document_types:
        errors.append({"type": "NO_DOCUMENT_TYPES_FOUND"})

    return {
        "schema_version": 2,
        "role": "LOCAL_EXACT_SOURCE_INDEX",
        "result": "PASS" if not errors else "FAIL",
        "source_inputs": [fingerprint(path) for path in sources],
        "artifact_model": corpus.get("artifact_model", {}),
        "operation_count": len(operations),
        "document_type_count": len(document_types),
        "operations": operations,
        "document_types": document_types,
        "errors": errors,
        "rule": "This index is reconstructed only from exact user/target/authorized Cleverence XML/MSLX source. For Operations, name is the exact reference artifact stem while runtime_name preserves XML Operation/@name. Parameters, returns, Action-type counts and operation targets are exact structural declarations only; expressions and Action bodies are not copied. For DocumentTypes, exact field declarations are indexed. None of these structures prove parser precedence, branch semantics, runtime behavior or cross-version compatibility.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an ephemeral exact Cleverence Operation/DocumentType structural index from user/target/authorized source.")
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    sources = [Path(value).resolve() for value in args.source]
    missing = [str(path) for path in sources if not path.exists()]
    if missing:
        print(json.dumps({"result": "FAIL", "errors": [{"type": "SOURCE_MISSING", "paths": missing}]}, ensure_ascii=False, indent=2))
        return 2

    report = build_index(sources)
    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": report["result"],
        "output": str(output),
        "operation_count": report["operation_count"],
        "document_type_count": report["document_type_count"],
        "errors": report["errors"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
