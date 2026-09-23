#!/usr/bin/env python3
"""Deterministic structural review for Cleverence XML/MSLX artifacts.

Checks parse/encoding, Action identity and direction resolution, operation targets,
Configuration/WinClient mirrors, and baseline-aware Action-flow deltas. Runtime
semantics still require stock-source and emulator/device evidence.

Artifact/container discovery is delegated to artifact_corpus so Configuration-root,
legacy Documents.zip and unpacked subsets share one bounded intake model without
making physical layout the semantic identity of an Operation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_corpus import inventory_paths, analyzable_entries


XML_SUFFIXES = {".mslx", ".xml"}
SPECIAL_DIRECTIONS = {
    "return",
    "abort",
    "break",
    "back",
    "continue",
    "undo",
    "cancel",
    "finishproc",
    "release",
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def looks_mojibake(name: str) -> bool:
    return "\ufffd" in name or any("\u2500" <= ch <= "\u257f" for ch in name)


def physical_leaf(row) -> str:
    return row.physical_path.split("!/")[-1].replace("\\", "/")


def physical_variant(logical: str) -> str:
    if logical.startswith("WinClient/Configuration/"):
        return "WINCLIENT"
    if logical.startswith("Configuration/"):
        return "MAIN"
    return "SUBSET"


def read_entries(path: Path):
    findings = []
    entries = {}
    metadata = {}
    corpus = inventory_paths([path])

    for warning in corpus.get("warnings", []):
        severity = "HIGH" if warning.get("type") in {"BAD_ZIP", "ZIP_ENTRY_READ_FAILED"} else "REVIEW"
        findings.append(finding(
            f"CLEVERENCE_{warning.get('type', 'ARTIFACT_WARNING')}",
            severity,
            json.dumps(warning, ensure_ascii=False),
            str(path),
            artifact_warning=warning,
        ))

    for semantic, data, origin, row in analyzable_entries(corpus):
        logical = physical_leaf(row)
        if Path(logical).suffix.lower() not in XML_SUFFIXES:
            continue
        if looks_mojibake(logical):
            findings.append(finding("CLEVERENCE_ZIP_FILENAME_MOJIBAKE", "HIGH", logical, str(path)))

        key = logical
        if key in entries and entries[key] != data:
            prefix = PurePosixPath(row.physical_path.split("!/", 1)[0]).stem or "artifact"
            key = f"{prefix}/{logical}"
            index = 2
            while key in entries:
                key = f"{prefix}-{index}/{logical}"
                index += 1

        entries[key] = data
        metadata[key] = {
            "semantic_path": semantic.replace("\\", "/"),
            "physical_path": row.physical_path,
            "container_chain": row.container_chain,
            "origin": origin,
            "variant": physical_variant(logical),
        }

    return entries, metadata, findings, corpus.get("artifact_model", {})


def finding(kind: str, severity: str, message: str, file: str, **extra):
    row = {"type": kind, "severity": severity, "file": file, "message": message}
    row.update(extra)
    return row


def direction_attributes(element):
    return {
        key: value
        for key, value in element.attrib.items()
        if key.lower().endswith("direction") and value
    }


def child_string_values(element, container_name):
    for child in list(element):
        if local_name(child.tag) == container_name:
            return [grandchild.text or "" for grandchild in list(child) if local_name(grandchild.tag) == "String"]
    return []


def parse_indent(element, logical, action_id, findings):
    raw = element.attrib.get("indent", "")
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        findings.append(finding(
            "CLEVERENCE_INDENT_INVALID",
            "HIGH",
            f"indent={raw!r} is not an integer",
            logical,
            action_id=action_id,
        ))
        return raw


def split_scoped_direction(value):
    target = value
    up_count = 0
    while target.lower().startswith("up:"):
        up_count += 1
        target = target[3:]
    return up_count, target


def parse_document(logical: str, data: bytes, metadata=None):
    findings = []
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return None, [finding("CLEVERENCE_ENCODING", "HIGH", str(exc), logical)]
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return None, [finding("CLEVERENCE_XML_PARSE", "HIGH", str(exc), logical)]

    actions = []

    def walk_actions(actions_element, scope):
        siblings = [child for child in list(actions_element) if local_name(child.tag).endswith("Action")]
        sibling_ids = [child.attrib.get("id", f"@{index}") for index, child in enumerate(siblings)]
        sibling_indents = [parse_indent(child, logical, sibling_ids[index], findings) for index, child in enumerate(siblings)]
        for index, action in enumerate(siblings):
            action_id = action.attrib.get("id", "")
            name = action.attrib.get("name", "")
            record = {
                "id": action_id,
                "tag": local_name(action.tag),
                "name": name,
                "scope": "/".join(scope),
                "index": index,
                "predecessor": sibling_ids[index - 1] if index else None,
                "successor": sibling_ids[index + 1] if index + 1 < len(sibling_ids) else None,
                "indent": sibling_indents[index],
                "nextIndent": sibling_indents[index + 1] if index + 1 < len(sibling_indents) else None,
                "scopeEnd": index + 1 == len(siblings),
                "indentExit": (
                    isinstance(sibling_indents[index], int)
                    and index + 1 < len(sibling_indents)
                    and isinstance(sibling_indents[index + 1], int)
                    and sibling_indents[index + 1] < sibling_indents[index]
                ),
                "directions": direction_attributes(action),
                "buttonDirections": child_string_values(action, "ButtonDirections"),
                "operationName": action.attrib.get("operationName", ""),
            }
            actions.append(record)
            child_scope = scope + [action_id or name or f"{record['tag']}@{index}"]
            for child in list(action):
                if local_name(child.tag) == "Actions":
                    walk_actions(child, child_scope)

    for child in list(root):
        if local_name(child.tag) == "Actions":
            walk_actions(child, [root.attrib.get("name", local_name(root.tag))])

    ids = [row["id"] for row in actions if row["id"]]
    for action_id, count in Counter(ids).items():
        if count > 1:
            findings.append(finding(
                "CLEVERENCE_ACTION_ID_DUPLICATE",
                "HIGH",
                f"Action id {action_id!r} occurs {count} times",
                logical,
                action_id=action_id,
            ))

    labels = {row["name"] for row in actions if row["name"]}
    labels.update(ids)
    labels_by_scope = {}
    for row in actions:
        labels_by_scope.setdefault(row["scope"], set()).update(
            value for value in (row["id"], row["name"]) if value
        )
    for row in actions:
        transitions = list(row["directions"].items())
        transitions.extend((f"ButtonDirections[{index}]", value) for index, value in enumerate(row["buttonDirections"]) if value)
        for attribute, value in transitions:
            up_count, target = split_scoped_direction(value)
            if target.lower() in SPECIAL_DIRECTIONS:
                continue
            resolved = target in labels
            expected_scope = None
            if up_count:
                scope_parts = row["scope"].split("/")
                if up_count >= len(scope_parts):
                    resolved = False
                else:
                    expected_scope = "/".join(scope_parts[:-up_count])
                    resolved = target in labels_by_scope.get(expected_scope, set())
            if resolved:
                continue
            findings.append(finding(
                "CLEVERENCE_DIRECTION_TARGET_UNRESOLVED",
                "HIGH",
                f"{attribute}={value!r} does not resolve to an Action label/id or a known control direction"
                + (f" in parent scope {expected_scope!r}" if up_count else ""),
                logical,
                action_id=row["id"],
            ))

    # Outer legacy export XML (AppDescription/settings/etc.) is inventory evidence,
    # not an execution graph merely because it is XML.
    if local_name(root.tag) != "Operation" and not actions:
        return None, findings

    metadata = metadata or {}
    doc = {
        "logical_path": logical,
        "semantic_path": metadata.get("semantic_path", logical),
        "physical_path": metadata.get("physical_path", logical),
        "container_chain": metadata.get("container_chain", []),
        "variant": metadata.get("variant", physical_variant(logical)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "root_tag": local_name(root.tag),
        "operation": root.attrib.get("name", "") if local_name(root.tag) == "Operation" else "",
        "actions": actions,
    }
    return doc, findings


def parse_corpus(path: Path):
    entries, metadata, findings, artifact_model = read_entries(path)
    documents = {}
    for logical, data in entries.items():
        doc, doc_findings = parse_document(logical, data, metadata.get(logical))
        findings.extend(doc_findings)
        if doc:
            documents[logical] = doc
    return entries, documents, findings, artifact_model


def inspect_operation_targets(documents, findings):
    operations = {doc["operation"] for doc in documents.values() if doc["operation"]}
    if len(operations) <= 1:
        return
    for logical, doc in documents.items():
        for action in doc["actions"]:
            target = action["operationName"]
            if target and target not in operations:
                findings.append(finding(
                    "CLEVERENCE_OPERATION_TARGET_UNRESOLVED",
                    "REVIEW",
                    f"operationName={target!r} is absent from the supplied operation corpus",
                    logical,
                    action_id=action["id"],
                ))


def inspect_mirrors(entries, findings):
    normalized = set(entries)
    config = {name for name in normalized if name.startswith("Configuration/")}
    win = {name for name in normalized if name.startswith("WinClient/Configuration/")}
    if not config or not win:
        return
    for source in sorted(config):
        mirror = "WinClient/" + source
        if mirror not in entries:
            findings.append(finding(
                "CLEVERENCE_MIRROR_COUNTERPART_MISSING",
                "REVIEW",
                f"Mirror is absent for {source}",
                source,
            ))
        elif entries[source] != entries[mirror]:
            findings.append(finding(
                "CLEVERENCE_MIRROR_DRIFT",
                "HIGH",
                f"{source} and {mirror} differ",
                source,
            ))


def action_map(doc):
    return {row["id"]: row for row in doc["actions"] if row["id"]}


def canonical_documents(documents):
    grouped = defaultdict(list)
    for logical, doc in documents.items():
        grouped[doc.get("semantic_path", logical)].append((logical, doc))

    preference = {"MAIN": 0, "SUBSET": 1, "WINCLIENT": 2}
    result = {}
    for semantic, rows in grouped.items():
        result[semantic] = min(
            rows,
            key=lambda row: (preference.get(row[1].get("variant"), 9), row[0]),
        )[1]
    return result


def compare_to_baseline(candidate_docs, baseline_docs, findings):
    candidate_docs = canonical_documents(candidate_docs)
    baseline_docs = canonical_documents(baseline_docs)
    candidate_paths = set(candidate_docs)
    baseline_paths = set(baseline_docs)
    for semantic in sorted(candidate_paths - baseline_paths):
        doc = candidate_docs[semantic]
        findings.append(finding(
            "CLEVERENCE_FILE_ADDED",
            "REVIEW",
            "File is absent from baseline",
            doc["logical_path"],
            semantic_path=semantic,
        ))
    for semantic in sorted(baseline_paths - candidate_paths):
        doc = baseline_docs[semantic]
        findings.append(finding(
            "CLEVERENCE_FILE_REMOVED",
            "REVIEW",
            "Baseline file is absent from candidate",
            doc["logical_path"],
            semantic_path=semantic,
        ))
    for semantic in sorted(candidate_paths & baseline_paths):
        candidate_doc = candidate_docs[semantic]
        baseline_doc = baseline_docs[semantic]
        logical = candidate_doc["logical_path"]
        candidate = action_map(candidate_doc)
        baseline = action_map(baseline_doc)
        added = sorted(set(candidate) - set(baseline))
        removed = sorted(set(baseline) - set(candidate))
        if added or removed:
            findings.append(finding(
                "CLEVERENCE_ACTION_SET_CHANGED",
                "REVIEW",
                f"added={added}; removed={removed}",
                logical,
                semantic_path=semantic,
            ))
        for action_id in sorted(set(candidate) & set(baseline)):
            before, after = baseline[action_id], candidate[action_id]
            flow_fields = ("scope", "index", "predecessor", "successor")
            delta = {key: {"before": before[key], "after": after[key]} for key in flow_fields if before[key] != after[key]}
            if delta:
                findings.append(finding(
                    "CLEVERENCE_IMPLICIT_FLOW_CHANGED",
                    "REVIEW",
                    "Action physical scope/order/predecessor/successor changed",
                    logical,
                    semantic_path=semantic,
                    action_id=action_id,
                    delta=delta,
                ))
            if before["indent"] != after["indent"]:
                findings.append(finding(
                    "CLEVERENCE_INDENT_CHANGED",
                    "REVIEW",
                    "Serialized Action indent changed; branch/depth semantics require stock/runtime adjudication",
                    logical,
                    semantic_path=semantic,
                    action_id=action_id,
                    before=before["indent"],
                    after=after["indent"],
                ))
            boundary_fields = ("scopeEnd", "indentExit")
            boundary_delta = {
                key: {"before": before[key], "after": after[key]}
                for key in boundary_fields
                if before[key] != after[key]
            }
            if boundary_delta:
                findings.append(finding(
                    "CLEVERENCE_FORMER_END_CHANGED",
                    "REVIEW",
                    "Action ceased/became a physical scope end or indentation-exit boundary",
                    logical,
                    semantic_path=semantic,
                    action_id=action_id,
                    delta=boundary_delta,
                ))
            if before["directions"] != after["directions"]:
                findings.append(finding(
                    "CLEVERENCE_EXPLICIT_DIRECTION_CHANGED",
                    "REVIEW",
                    "Action direction attributes changed",
                    logical,
                    semantic_path=semantic,
                    action_id=action_id,
                    before=before["directions"],
                    after=after["directions"],
                ))
            if before["buttonDirections"] != after["buttonDirections"]:
                findings.append(finding(
                    "CLEVERENCE_BUTTON_DIRECTIONS_CHANGED",
                    "REVIEW",
                    "Ordered ButtonDirections slots changed",
                    logical,
                    semantic_path=semantic,
                    action_id=action_id,
                    before=before["buttonDirections"],
                    after=after["buttonDirections"],
                ))
            if before["operationName"] != after["operationName"]:
                findings.append(finding(
                    "CLEVERENCE_OPERATION_TARGET_CHANGED",
                    "REVIEW",
                    "Invoked operation changed",
                    logical,
                    semantic_path=semantic,
                    action_id=action_id,
                    before=before["operationName"],
                    after=after["operationName"],
                ))


def analyze(candidate: Path, baseline: Path | None = None):
    entries, documents, findings, artifact_model = parse_corpus(candidate)
    inspect_operation_targets(documents, findings)
    inspect_mirrors(entries, findings)
    baseline_documents = {}
    baseline_artifact_model = None
    if baseline:
        _, baseline_documents, baseline_findings, baseline_artifact_model = parse_corpus(baseline)
        for row in baseline_findings:
            row = dict(row)
            row["baseline"] = True
            findings.append(row)
        compare_to_baseline(documents, baseline_documents, findings)

    counts = Counter(row["severity"] for row in findings)
    types = Counter(row["type"] for row in findings)
    result = "FAIL" if counts.get("HIGH", 0) else "PASS"
    return {
        "result": result,
        "candidate": str(candidate),
        "baseline": str(baseline) if baseline else None,
        "artifact_model": artifact_model,
        "baseline_artifact_model": baseline_artifact_model,
        "files": len(documents),
        "semantic_files": len(canonical_documents(documents)),
        "actions": sum(len(doc["actions"]) for doc in documents.values()),
        "summary": {"by_severity": dict(sorted(counts.items())), "by_type": dict(sorted(types.items()))},
        "findings": findings,
        "rule": "Structural PASS is not runtime/semantic proof. Physical layout and semantic operation identity are separate; indent/up:/ButtonDirections/former-END findings require stock evidence and emulator/device adjudication.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate")
    parser.add_argument("--baseline")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = analyze(Path(args.candidate), Path(args.baseline) if args.baseline else None)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    print(output, end="")
    raise SystemExit(2 if report["result"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
