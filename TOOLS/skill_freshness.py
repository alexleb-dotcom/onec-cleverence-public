#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath

CORE_EXECUTION = {
    "README_FIRST.md",
    "README.md",
    "SKILL.md",
    "KNOWLEDGE/SKILL_FRESHNESS.md",
}

ROUTING_EXACT = {
    "PROFILES/INDEX.json",
    "REQUIREMENTS/INDEX.json",
    "WORKFLOW/DEVELOPMENT_PIPELINE.json",
    "TOOLS/rule_registry.py",
    "TOOLS/build_requirements_contract.py",
    "TOOLS/requirements_gate.py",
    "TOOLS/build_review_plan.py",
    "TOOLS/build_validation_ledger.py",
    "TOOLS/release_gate.py",
}

ON_DEMAND_PREFIXES = ("REFERENCE/", "ARCHIVE/", "THIRD_PARTY/")
MAINTENANCE_PREFIXES = ("TESTS/", ".github/")

MINIMAL_BOOTSTRAP = [
    "README_FIRST.md",
    "README.md",
    "SKILL.md",
    "KNOWLEDGE/SKILL_FRESHNESS.md",
    "RULES/rule_registry.json",
]


def _norm(path: str) -> str:
    return str(PurePosixPath(path.replace("\\", "/")))


def classify_path(path: str) -> str:
    path = _norm(path)
    if path in CORE_EXECUTION:
        return "CORE_EXECUTION"
    if path == "RULES/rule_registry.json" or path.startswith("RULES/") or path in ROUTING_EXACT:
        return "ROUTING_GATES"
    if path.startswith("TOOLS/"):
        return "EXECUTION_TOOLING"
    if path.startswith("PROFILES/") or path.startswith("KNOWLEDGE/") or path.startswith("REQUIREMENTS/"):
        return "ROUTED_CONTENT"
    if path.startswith(ON_DEMAND_PREFIXES):
        return "ON_DEMAND_EVIDENCE"
    if path.startswith(MAINTENANCE_PREFIXES) or path in {"manifest.txt", ".gitattributes", ".gitignore"}:
        return "MAINTENANCE_ONLY"
    return "OTHER_ACTIVE"


def plan_freshness(
    loaded_sha: str | None,
    current_sha: str | None,
    *,
    history_comparable: bool = True,
    changed_files: list[str] | None = None,
    skill_maintenance: bool = False,
) -> dict:
    loaded_sha = (loaded_sha or "").strip()
    current_sha = (current_sha or "").strip()
    changed = sorted({_norm(p) for p in (changed_files or []) if p and p.strip()})

    base = {
        "loaded_sha": loaded_sha or None,
        "current_sha": current_sha or None,
        "history_comparable": bool(history_comparable),
        "changed_files": changed,
        "full_repository_reload_required": False,
        "minimal_bootstrap_files": MINIMAL_BOOTSTRAP,
    }

    if not current_sha:
        base.update({
            "status": "UNVERIFIED",
            "diff_required": False,
            "minimal_bootstrap_required": not bool(loaded_sha),
            "reroute_required": False,
            "machine_revalidation_required": False,
            "proof_revalidation_required": False,
            "task_relevance_review_required": False,
            "on_demand_evidence_review_required": False,
            "reload_candidates": [],
            "loaded_sha_update_allowed": False,
            "reason": "Current tracked ref SHA is unavailable; do not claim the skill is current/latest.",
        })
        return base

    if not loaded_sha:
        base.update({
            "status": "BOOTSTRAP_REQUIRED",
            "diff_required": False,
            "minimal_bootstrap_required": True,
            "reroute_required": True,
            "machine_revalidation_required": False,
            "proof_revalidation_required": True,
            "task_relevance_review_required": True,
            "on_demand_evidence_review_required": False,
            "reload_candidates": MINIMAL_BOOTSTRAP,
            "loaded_sha_update_allowed": False,
            "reason": "No exact loaded skill SHA is recorded; establish the minimal execution/routing core first.",
        })
        return base

    if loaded_sha == current_sha:
        base.update({
            "status": "FRESH",
            "diff_required": False,
            "minimal_bootstrap_required": False,
            "reroute_required": False,
            "machine_revalidation_required": False,
            "proof_revalidation_required": False,
            "task_relevance_review_required": False,
            "on_demand_evidence_review_required": False,
            "reload_candidates": [],
            "loaded_sha_update_allowed": True,
            "reason": "Loaded and tracked skill commits match; no repository reread is required.",
        })
        return base

    if not history_comparable:
        base.update({
            "status": "REBOOTSTRAP_REQUIRED",
            "diff_required": False,
            "minimal_bootstrap_required": True,
            "reroute_required": True,
            "machine_revalidation_required": True,
            "proof_revalidation_required": True,
            "task_relevance_review_required": True,
            "on_demand_evidence_review_required": True,
            "reload_candidates": MINIMAL_BOOTSTRAP,
            "loaded_sha_update_allowed": False,
            "reason": "The old loaded SHA cannot be safely compared with the tracked ref; rebuild the minimal skill core instead of inventing a partial diff.",
        })
        return base

    classified = {path: classify_path(path) for path in changed}
    classes = set(classified.values())
    routing = "ROUTING_GATES" in classes
    tooling = "EXECUTION_TOOLING" in classes
    routed_content = bool(classes & {"CORE_EXECUTION", "ROUTED_CONTENT", "OTHER_ACTIVE"})
    on_demand = "ON_DEMAND_EVIDENCE" in classes

    reload_candidates = []
    for path in changed:
        kind = classified[path]
        if kind in {"CORE_EXECUTION", "ROUTING_GATES", "EXECUTION_TOOLING", "ROUTED_CONTENT", "OTHER_ACTIVE"}:
            reload_candidates.append(path)
        elif kind == "MAINTENANCE_ONLY" and skill_maintenance:
            reload_candidates.append(path)
        # ON_DEMAND_EVIDENCE remains dependency-driven and is never bulk-loaded merely because it changed.

    base.update({
        "status": "REFRESH_REQUIRED",
        "diff_required": True,
        "diff_inventory_required": not bool(changed),
        "minimal_bootstrap_required": False,
        "reroute_required": routing,
        "machine_revalidation_required": tooling,
        "proof_revalidation_required": routing or tooling,
        "task_relevance_review_required": routed_content or routing or tooling,
        "on_demand_evidence_review_required": on_demand,
        "reload_candidates": reload_candidates,
        "classified_changes": classified,
        "loaded_sha_update_allowed": False,
        "reason": "Tracked skill commit changed. Inspect the diff and apply only task-relevant execution impact before advancing loaded_sha.",
    })
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan a fail-closed, diff-first refresh of the universal skill in a long-lived chat.")
    parser.add_argument("--loaded-sha")
    parser.add_argument("--current-sha")
    parser.add_argument("--history-comparable", choices=["true", "false"], default="true")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--skill-maintenance", action="store_true")
    args = parser.parse_args()

    out = plan_freshness(
        args.loaded_sha,
        args.current_sha,
        history_comparable=args.history_comparable == "true",
        changed_files=args.changed_file,
        skill_maintenance=args.skill_maintenance,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
