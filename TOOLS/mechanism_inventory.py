#!/usr/bin/env python3
"""Derived, non-authoritative SHAREABLE_CORE mechanism inventory and drift checker.

The Rule Registry remains the only semantic task-routability authority. This tool
only proves that the governed distribution surface is accounted for, that existing
owners make supporting material reachable, and that every Registry delivery
candidate has an explicit applicability disposition path.
"""
from __future__ import annotations

from collections import Counter, deque
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rule_registry import (
    load_registry,
    materialize_delivery_applicability,
    validate_delivery_bindings,
    validate_supporting_artifacts,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "DISTRIBUTION_MANIFEST.json"
CLASSES = {
    "ROUTED_DELIVERY",
    "PIPELINE_INTERNAL",
    "SUPPORTING",
    "GENERATED",
    "DEPRECATED",
    "ORPHAN_UNKNOWN",
}
NON_MECHANISM = {
    ".gitignore",
    "assets/icon.svg",
    "RIGHTS_NOTICE.md",
    "THIRD_PARTY/cc-1c-skills/LICENSE.txt",
    "THIRD_PARTY/cc-1c-skills/NOTICE.md",
}
GENERATED = {
    "DISTRIBUTION_MANIFEST.json": ("TOOLS/build_distribution_snapshot.py", None),
    "PROFILES/INDEX.json": ("TOOLS/generate_registry_views.py", "RULES/rule_registry.json"),
    "KNOWLEDGE/MECHANISM_REVIEW_PROFILES.json": ("TOOLS/generate_registry_views.py", "RULES/rule_registry.json"),
    "KNOWLEDGE/PROOF_POLICY_INDEX.json": ("TOOLS/generate_registry_views.py", "RULES/rule_registry.json"),
    "REQUIREMENTS/INDEX.json": ("TOOLS/generate_registry_views.py", "RULES/rule_registry.json"),
    "TESTS/SEMANTIC_REGRESSION_CLASSES.md": ("TOOLS/generate_registry_views.py", "RULES/rule_registry.json"),
    "TESTS/REQUIREMENTS_SEMANTIC_CLASSES.md": ("TOOLS/generate_registry_views.py", "RULES/rule_registry.json"),
}
DEPRECATED_EXPECTED = {
    "KNOWLEDGE/CLEVERENCE_COVERAGE_AUDIT.json",
    "TEMPLATES/PROJECT_SNAPSHOT_MANIFEST.json",
}
PIPELINE_INTERNAL_KNOWLEDGE = {
    "KNOWLEDGE/ANTIPATTERN_CATALOG.json",
    "KNOWLEDGE/EXECUTION_CHECKPOINT.md",
    "KNOWLEDGE/LLM_ADVERSARIAL_VALIDATION.md",
    "KNOWLEDGE/VALIDATION_ENGINE.md",
}
PIPELINE_INTERNAL_EXACT = {
    ".gitattributes",
    ".github/workflows/shareable-validation.yml",
    "agents/openai.yaml",
    "DISTRIBUTION.md",
    "README.md",
    "README_FIRST.md",
    "SKILL.md",
    "RULES/README.md",
    "RULES/rule_registry.json",
    "REQUIREMENTS/README.md",
    "WORKFLOW/DEVELOPMENT_PIPELINE.json",
    "WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json",
    "WORKFLOW/RESULT_DELIVERY_CONTRACT.json",
    "TOOLS/PUBLIC_CI_INVENTORY.json",
    "TOOLS/SHAREABLE_BINARY_REVIEW_POLICY.json",
    # Existing non-task-facing pipeline utilities with independent role evidence.
    # These are not legitimized by their regression tests.
    "TOOLS/capability_compliance_projection.py",
    "TOOLS/skill_freshness.py",
}
SOURCE_SUPPORT_TOOLS = {
    "TOOLS/reference_locator.py": "SKILL:SOURCE_DISCOVERY",
    "TOOLS/pattern_locator.py": "SKILL:PATTERN_DISCOVERY",
    "TOOLS/build_local_bsl_reference_index.py": "SKILL:SOURCE_DISCOVERY",
    "TOOLS/build_local_cleverence_reference_index.py": "SKILL:SOURCE_DISCOVERY",
}
OWNER_SEED_FILES = {
    "SKILL.md",
    "README.md",
    "README_FIRST.md",
    "DISTRIBUTION.md",
    "RULES/README.md",
    "REQUIREMENTS/README.md",
    "WORKFLOW/DEVELOPMENT_PIPELINE.json",
    "WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json",
    "WORKFLOW/RESULT_DELIVERY_CONTRACT.json",
    ".github/workflows/shareable-validation.yml",
    "TOOLS/PUBLIC_CI_INVENTORY.json",
}
ROOT_TASK_ENTRYPOINT_FILE = "SKILL.md"
INDEPENDENT_PIPELINE_SEED_FILES = {
    "WORKFLOW/DEVELOPMENT_PIPELINE.json",
    "WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json",
    "WORKFLOW/RESULT_DELIVERY_CONTRACT.json",
    ".github/workflows/shareable-validation.yml",
    "TOOLS/PUBLIC_CI_INVENTORY.json",
}
PATH_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:KNOWLEDGE|TEMPLATES|TOOLS|PROFILES|PATTERNS|REFERENCE|RULES|REQUIREMENTS|WORKFLOW|TESTS)/"
    r"[A-Za-z0-9_./-]+(?:\.md|\.json|\.py|\.bsl|\.mslx|\.xml|\.txt|\.bin)?)"
)
LOCAL_IMPORT_RE = re.compile(r"(?m)^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_surface(root: Path) -> tuple[list[str], dict[str, dict], list[dict]]:
    errors: list[dict] = []
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        return [], {}, [{"type": "INVENTORY_MANIFEST_MISSING", "path": MANIFEST}]
    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        return [], {}, [{"type": "INVENTORY_MANIFEST_INVALID", "error": str(exc)}]
    rows = manifest.get("files")
    if not isinstance(rows, list):
        return [], {}, [{"type": "INVENTORY_MANIFEST_FILES_INVALID"}]
    identities: dict[str, dict] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append({"type": "INVENTORY_MANIFEST_ROW_INVALID", "index": index})
            continue
        path = row.get("path")
        if not isinstance(path, str) or not path:
            errors.append({"type": "INVENTORY_MANIFEST_PATH_INVALID", "index": index})
            continue
        identities[path] = {"sha256": row.get("sha256"), "size": row.get("size")}
    manifest_bytes = manifest_path.read_bytes()
    identities[MANIFEST] = {
        "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "size": len(manifest_bytes),
    }
    return sorted(identities), identities, errors


def _extract_refs(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return set()
    return {match.group(1).rstrip(".,;:") for match in PATH_REF_RE.finditer(text)}


def _registry_support_owners(registry: dict) -> tuple[dict[str, str], list[dict]]:
    owners: dict[str, str] = {}
    errors: list[dict] = []
    for owner_kind, rows in (("RULE", registry.get("rules", [])), ("GATE", registry.get("gates", []))):
        for row in rows:
            owner_id = row.get("id")
            for rel in row.get("supporting_artifacts", []) or []:
                previous = owners.get(rel)
                owner = f"{owner_kind}:{owner_id}"
                if previous is not None and previous != owner:
                    errors.append({
                        "type": "SUPPORTING_ARTIFACT_MULTIPLE_SEMANTIC_OWNERS",
                        "path": rel,
                        "owners": [previous, owner],
                    })
                owners[rel] = owner
    return owners, errors


def _workflow_owner_fields(root: Path) -> dict[str, str]:
    owners: dict[str, str] = {}
    contracts = {
        "WORKFLOW/DEVELOPMENT_PIPELINE.json": (
            "handoff_contract",
            "functional_contract_template",
            "validation_ledger_template",
        ),
        "WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json": (
            "request_template",
            "collection_plan_template",
        ),
    }
    for rel, fields in contracts.items():
        path = root / rel
        if not path.is_file():
            continue
        doc = _read_json(path)
        for field in fields:
            value = doc.get(field)
            if isinstance(value, str) and value:
                owners[value] = f"WORKFLOW:{rel}:{field}"
    return owners


def _profile_support(root: Path) -> dict[str, str]:
    owners: dict[str, str] = {}
    path = root / "PROFILES/INDEX.json"
    if not path.is_file():
        return owners
    doc = _read_json(path)
    for profile_id, row in (doc.get("profiles") or {}).items():
        rel = row.get("file") if isinstance(row, dict) else None
        rule_id = row.get("rule_id") if isinstance(row, dict) else None
        if isinstance(rel, str):
            owners[rel] = f"RULE:{rule_id or profile_id}"
    return owners


def _pattern_support(root: Path) -> dict[str, str]:
    owners = {"PATTERNS/INDEX.json": "PATTERNS:INDEX", "PATTERNS/README.md": "PATTERNS:INDEX"}
    path = root / "PATTERNS/INDEX.json"
    if not path.is_file():
        return owners
    doc = _read_json(path)
    for row in doc.get("patterns", []) or []:
        pid = row.get("id", "?")
        for key in ("good", "bad", "files", "examples"):
            value = row.get(key)
            values = value if isinstance(value, list) else [value] if isinstance(value, str) else []
            for rel in values:
                if isinstance(rel, str) and rel.startswith("PATTERNS/"):
                    owners[rel] = f"PATTERN:{pid}"
        # Current schema nests concrete paths in arbitrary fields; scan the row canonically.
        for match in re.finditer(r"PATTERNS/[A-Za-z0-9_./-]+", json.dumps(row, ensure_ascii=False)):
            owners[match.group(0).rstrip('",}')] = f"PATTERN:{pid}"
    return owners


def _delivery_support_tools(registry: dict) -> dict[str, str]:
    owners = dict(SOURCE_SUPPORT_TOOLS)
    for rule in registry.get("rules", []):
        for binding in rule.get("delivery", []) or []:
            text = json.dumps(binding.get("executor_payload") or {}, ensure_ascii=False)
            for match in re.finditer(r"TOOLS/[A-Za-z0-9_./-]+\.py", text):
                owners[match.group(0)] = f"DELIVERY:{binding.get('capability_id')}:{rule.get('id')}"
    return owners


def _reference_support_closure(root: Path, registry_owners: dict[str, str], workflow_owners: dict[str, str]) -> dict[str, str]:
    """Resolve task-facing KNOWLEDGE/TEMPLATES support from existing owner references."""
    owners: dict[str, str] = {}
    queue: deque[tuple[str, str]] = deque()

    seed_paths = set(OWNER_SEED_FILES)
    seed_paths.update(f"PROFILES/{p.name}" for p in (root / "PROFILES").glob("*.md"))
    for rel in sorted(seed_paths):
        if (root / rel).is_file():
            queue.append((rel, f"OWNER:{rel}"))

    for rel, owner in {**registry_owners, **workflow_owners}.items():
        owners[rel] = owner
        if rel.startswith(("KNOWLEDGE/", "TEMPLATES/")) and (root / rel).is_file():
            queue.append((rel, owner))

    scanned: set[str] = set()
    while queue:
        source, source_owner = queue.popleft()
        if source in scanned:
            continue
        scanned.add(source)
        path = root / source
        if not path.is_file():
            continue
        for ref in sorted(_extract_refs(path)):
            if not ref.startswith(("KNOWLEDGE/", "TEMPLATES/")):
                continue
            if ref not in owners:
                owners[ref] = source_owner if source.startswith(("KNOWLEDGE/", "TEMPLATES/")) else f"REFERENCE:{source}"
            if ref not in scanned and (root / ref).is_file():
                queue.append((ref, owners[ref]))
    return owners


def _tool_closure(
    root: Path,
    support_tools: dict[str, str],
    seed_files: set[str],
    seed_tools: set[str] | None = None,
) -> set[str]:
    """Resolve executable-tool reachability from an explicit structural seed set."""
    module_paths = {p.stem: p.relative_to(root).as_posix() for p in (root / "TOOLS").glob("*.py")}
    internal: set[str] = set()
    queue: deque[str] = deque()

    def add(rel: str) -> None:
        if rel in support_tools or not rel.startswith("TOOLS/") or not rel.endswith(".py"):
            return
        if rel in module_paths.values() and rel not in internal:
            internal.add(rel)
            queue.append(rel)

    for rel in sorted(seed_tools or set()):
        add(rel)
    for seed in sorted(seed_files):
        path = root / seed
        if not path.is_file():
            continue
        for ref in _extract_refs(path):
            add(ref)

    while queue:
        rel = queue.popleft()
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            continue
        for ref in _extract_refs(path):
            add(ref)
        for module in LOCAL_IMPORT_RE.findall(text):
            mapped = module_paths.get(module)
            if mapped:
                add(mapped)
    return internal


def _internal_tool_closure(root: Path, support_tools: dict[str, str]) -> set[str]:
    """Preserve the existing broad file-classification reachability model."""
    return _tool_closure(root, support_tools, OWNER_SEED_FILES)


def _independent_pipeline_tool_closure(root: Path, support_tools: dict[str, str]) -> set[str]:
    """Pipeline ownership independent of SKILL/README/test prose reachability."""
    explicit_tools = {
        rel for rel in PIPELINE_INTERNAL_EXACT
        if rel.startswith("TOOLS/") and rel.endswith(".py")
    }
    return _tool_closure(
        root,
        support_tools,
        INDEPENDENT_PIPELINE_SEED_FILES,
        explicit_tools,
    )


def _root_task_entrypoints(root: Path) -> list[str]:
    path = root / ROOT_TASK_ENTRYPOINT_FILE
    if not path.is_file():
        return []
    return sorted(
        ref for ref in _extract_refs(path)
        if ref.startswith("TOOLS/") and ref.endswith(".py")
    )


def _root_task_entrypoint_owner(rel: str, context: dict) -> str | None:
    direct_owner = context.get("tool_owners", {}).get(rel)
    if direct_owner:
        return direct_owner
    if rel in PIPELINE_INTERNAL_EXACT:
        return "PIPELINE:STRUCTURAL_EXACT"
    if rel in context.get("independent_pipeline_tools", set()):
        return "PIPELINE:INDEPENDENT_REACHABILITY"
    return None


def _deprecated_metadata(root: Path, rel: str) -> tuple[bool, dict | None]:
    try:
        doc = _read_json(root / rel)
    except Exception:
        return False, None
    lifecycle = doc.get("_artifact_lifecycle")
    if not isinstance(lifecycle, dict):
        return False, lifecycle
    return lifecycle.get("status") == "DEPRECATED" and bool(lifecycle.get("superseded_by")), lifecycle


def build_classification_context(root: Path, registry: dict) -> dict:
    registry_owners, registry_owner_errors = _registry_support_owners(registry)
    workflow_owners = _workflow_owner_fields(root)
    profile_owners = _profile_support(root)
    pattern_owners = _pattern_support(root)
    tool_owners = _delivery_support_tools(registry)
    reference_owners = _reference_support_closure(root, registry_owners, workflow_owners)
    support_owners = {}
    for mapping in (reference_owners, registry_owners, workflow_owners, profile_owners, pattern_owners, tool_owners):
        support_owners.update(mapping)
    for path in (root / "REFERENCE" / "CATALOGS").glob("*.json"):
        support_owners[path.relative_to(root).as_posix()] = "SKILL:REFERENCE_LOCATOR"
    internal_tools = _internal_tool_closure(root, tool_owners)
    independent_pipeline_tools = _independent_pipeline_tool_closure(root, tool_owners)
    return {
        "support_owners": support_owners,
        "tool_owners": tool_owners,
        "internal_tools": internal_tools,
        "independent_pipeline_tools": independent_pipeline_tools,
        "registry_owner_errors": registry_owner_errors,
    }


def classify_candidate_path(path: str, context: dict) -> tuple[str | None, str | None]:
    if path in NON_MECHANISM:
        return None, "NON_MECHANISM"
    if path in GENERATED:
        return "GENERATED", f"GENERATOR:{GENERATED[path][0]}"
    if path in DEPRECATED_EXPECTED:
        return "DEPRECATED", "EXPLICIT_DEPRECATION"
    owner = context["support_owners"].get(path)
    if owner:
        return "SUPPORTING", owner
    if path in PIPELINE_INTERNAL_KNOWLEDGE or path in PIPELINE_INTERNAL_EXACT:
        return "PIPELINE_INTERNAL", "STRUCTURAL_PIPELINE_OWNER"
    if path.startswith("TESTS/"):
        return "PIPELINE_INTERNAL", "TEST_ONLY_SURFACE"
    if path in context["internal_tools"]:
        return "PIPELINE_INTERNAL", "PIPELINE_REACHABILITY"
    return "ORPHAN_UNKNOWN", None


def _kind(path: str) -> str:
    if path.startswith("TOOLS/"):
        return "EXECUTABLE_TOOL" if path.endswith(".py") else "TOOL_METADATA"
    if path.startswith("TESTS/"):
        return "TEST_OR_FIXTURE"
    if path.startswith("PROFILES/"):
        return "PROFILE"
    if path.startswith("KNOWLEDGE/"):
        return "KNOWLEDGE"
    if path.startswith("TEMPLATES/"):
        return "TEMPLATE"
    if path.startswith("WORKFLOW/"):
        return "WORKFLOW"
    if path.startswith("RULES/"):
        return "REGISTRY"
    if path.startswith("PATTERNS/"):
        return "PATTERN"
    if path.startswith("REFERENCE/"):
        return "REFERENCE"
    return "REPOSITORY_CONTROL"


def build_inventory(root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    registry = load_registry(root / "RULES" / "rule_registry.json")
    surface, identities, errors = _manifest_surface(root)
    errors.extend({"type": "REGISTRY_DELIVERY_INVALID", "detail": x} for x in validate_delivery_bindings(registry))
    errors.extend({"type": "REGISTRY_SUPPORT_INVALID", "detail": x} for x in validate_supporting_artifacts(registry))

    context = build_classification_context(root, registry)
    errors.extend(context["registry_owner_errors"])

    root_task_entrypoints = _root_task_entrypoints(root)
    root_task_entrypoint_owners: dict[str, str] = {}
    for rel in root_task_entrypoints:
        owner = _root_task_entrypoint_owner(rel, context)
        if owner:
            root_task_entrypoint_owners[rel] = owner
        else:
            errors.append({
                "type": "ROOT_TASK_ENTRYPOINT_WITHOUT_INDEPENDENT_OWNER",
                "path": rel,
                "declaration": ROOT_TASK_ENTRYPOINT_FILE,
            })

    rows: list[dict] = []
    support_without_owner = 0
    orphan_rows: list[str] = []

    for rel in surface:
        classification, owner = classify_candidate_path(rel, context)
        if classification is None:
            continue
        if classification == "DEPRECATED":
            ok, lifecycle = _deprecated_metadata(root, rel)
            if not ok:
                errors.append({"type": "DEPRECATED_METADATA_MISSING_OR_INVALID", "path": rel, "lifecycle": lifecycle})
        if classification == "GENERATED":
            generator, source = GENERATED[rel]
            for required in (generator, source):
                if required and required not in surface:
                    errors.append({"type": "GENERATED_PROVENANCE_MISSING", "path": rel, "required": required})
        if classification == "SUPPORTING" and not owner:
            support_without_owner += 1
            errors.append({"type": "SUPPORTING_WITHOUT_OWNER", "path": rel})
        if classification == "ORPHAN_UNKNOWN":
            orphan_rows.append(rel)
        identity = identities.get(rel) or {}
        rows.append({
            "row_id": f"FILE:{rel}",
            "path": rel,
            "stable_identity": {
                "sha256": identity.get("sha256"),
                "size": identity.get("size"),
            },
            "mechanism_kind": _kind(rel),
            "classification": classification,
            "canonical_owner": owner,
            "routed_capability_id": None,
            "applicability_owner": None,
            "ambiguity": "UNCLASSIFIED_GOVERNED_MECHANISM" if classification == "ORPHAN_UNKNOWN" else None,
        })

    # Owner links must exist on the governed surface and must not point to deprecated support.
    for rel, owner in sorted(context["support_owners"].items()):
        if rel not in surface:
            errors.append({"type": "SUPPORT_OWNER_TARGET_MISSING", "path": rel, "owner": owner})
        if rel in DEPRECATED_EXPECTED:
            errors.append({"type": "DEPRECATED_ARTIFACT_REACHABLE", "path": rel, "owner": owner})

    # Every approved deprecated artifact remains unreachable.
    for rel in sorted(DEPRECATED_EXPECTED):
        if rel not in surface:
            errors.append({"type": "DEPRECATED_ARTIFACT_MISSING", "path": rel})

    routed_without_owner = 0
    for rule in registry.get("rules", []):
        for binding in rule.get("delivery", []) or []:
            capability = binding.get("capability_id")
            if not rule.get("id"):
                routed_without_owner += 1
            rows.append({
                "row_id": f"CAP:{capability}",
                "path": None,
                "stable_identity": None,
                "mechanism_kind": "REGISTRY_DELIVERY_CAPABILITY",
                "classification": "ROUTED_DELIVERY",
                "canonical_owner": f"RULE:{rule.get('id')}",
                "routed_capability_id": capability,
                "applicability_owner": f"RULE:{rule.get('id')}:activation+delivery.condition",
                "ambiguity": None,
            })

    synthetic_routes = [
        {
            "id": rule.get("id"),
            "active": False,
            "tier": rule.get("tier", 1),
            "detected_by": [],
            "reason": "inventory applicability smoke",
        }
        for rule in registry.get("rules", [])
    ]
    applicability = materialize_delivery_applicability(registry, synthetic_routes, "ANALYSIS_ONLY")
    allowed_statuses = {"APPLICABLE", "NOT_APPLICABLE", "NOT_EVALUATED"}
    applicability_complete = (
        len(applicability) == sum(len(rule.get("delivery", []) or []) for rule in registry.get("rules", []))
        and all(row.get("status") in allowed_statuses for row in applicability)
        and all({"capability_id", "owner_rule_id", "reason", "condition_snapshot", "routing_evidence"} <= set(row) for row in applicability)
    )
    if not applicability_complete:
        errors.append({"type": "ALL_CANDIDATE_APPLICABILITY_CONTRACT_INCOMPLETE"})

    counts = Counter(row["classification"] for row in rows)
    silent_drop_paths = (
        len(orphan_rows)
        + support_without_owner
        + routed_without_owner
        + (0 if applicability_complete else 1)
    )
    result = "PASS" if not errors and not orphan_rows and not support_without_owner and not routed_without_owner and applicability_complete else "FAIL"
    return {
        "result": result,
        "governed_surface_files": len(surface),
        "non_mechanism_files": len([p for p in surface if p in NON_MECHANISM]),
        "discovered_mechanism_rows": len(rows),
        "classification_counts": {name: counts.get(name, 0) for name in sorted(CLASSES)},
        "orphan_unknown_rows": orphan_rows,
        "routed_without_applicability_owner": routed_without_owner,
        "supporting_without_owner": support_without_owner,
        "silent_drop_paths_remaining": silent_drop_paths,
        "all_candidate_applicability_complete": applicability_complete,
        "root_task_entrypoints": root_task_entrypoints,
        "root_task_entrypoint_owners": root_task_entrypoint_owners,
        "root_task_entrypoints_all_independently_owned": (
            len(root_task_entrypoint_owners) == len(root_task_entrypoints)
        ),
        "errors": errors,
        "rows": rows,
    }


def compact(report: dict) -> dict:
    return {key: report[key] for key in (
        "result",
        "governed_surface_files",
        "non_mechanism_files",
        "discovered_mechanism_rows",
        "classification_counts",
        "orphan_unknown_rows",
        "routed_without_applicability_owner",
        "supporting_without_owner",
        "silent_drop_paths_remaining",
        "all_candidate_applicability_complete",
        "root_task_entrypoints",
        "root_task_entrypoint_owners",
        "root_task_entrypoints_all_independently_owned",
        "errors",
    )}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = build_inventory(Path(args.root))
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report if args.full else compact(report), ensure_ascii=False, indent=2))
    if args.check and report["result"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
