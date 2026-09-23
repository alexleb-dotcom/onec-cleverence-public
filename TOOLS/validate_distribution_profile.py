#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path = ROOT) -> dict:
    process = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return {
        "command": command,
        "returncode": process.returncode,
        "stdout": process.stdout[-12000:],
        "stderr": process.stderr[-12000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate onec-cleverence using an explicit distribution/runtime profile without weakening INTERNAL_FULL validation.")
    parser.add_argument("--profile", required=True, choices=("INTERNAL_FULL", "SHAREABLE_CORE"))
    args = parser.parse_args()

    errors = []
    checks = []
    private_paths = (ROOT / "REFERENCE/SOURCES", ROOT / "REFERENCE/INDEXES", ROOT / "MAINTENANCE/INTERNAL")

    if args.profile == "INTERNAL_FULL":
        missing = [str(path.relative_to(ROOT)) for path in private_paths[:2] if not path.exists()]
        if missing:
            errors.append({"type": "INTERNAL_PRIVATE_REFERENCE_MISSING", "paths": missing})
        for command in (
            [sys.executable, str(ROOT / "TOOLS/validate_skill.py")],
            [sys.executable, str(ROOT / "TESTS/run_pattern_regression.py")],
            [sys.executable, str(ROOT / "TESTS/run_evidence_source_policy_regression.py")],
            [sys.executable, str(ROOT / "TESTS/run_bootstrap_capability_regression.py")],
        ):
            result = run(command)
            checks.append({"id": " ".join(command[1:]), "returncode": result["returncode"]})
            if result["returncode"] != 0:
                errors.append({"type": "INTERNAL_VALIDATION_FAILED", "details": result})
    else:
        present = [str(path.relative_to(ROOT)) for path in private_paths if path.exists()]
        if present:
            errors.append({"type": "SHAREABLE_PRIVATE_PATH_PRESENT", "paths": present})

        required = [
            ".github/workflows/shareable-validation.yml",
            "SKILL.md",
            "DISTRIBUTION_MANIFEST.json",
            "PATTERNS/README.md",
            "PATTERNS/INDEX.json",
            "REFERENCE/CATALOGS/bsp_discovery.json",
            "REFERENCE/CATALOGS/typical_onec_discovery.json",
            "REFERENCE/CATALOGS/cleverence_discovery.json",
            "TOOLS/pattern_locator.py",
            "TOOLS/validate_patterns.py",
            "TOOLS/reference_locator.py",
            "TOOLS/build_local_bsl_reference_index.py",
            "TOOLS/build_local_cleverence_reference_index.py",
            "TOOLS/evidence_source_policy.py",
            "TOOLS/release_gate.py",
            "TOOLS/release_gate_core.py",
            "TOOLS/validation_work_queue.py",
            "TOOLS/evidence_receipt.py",
            "TESTS/run_pattern_regression.py",
            "TESTS/run_context_efficiency_regression.py",
            "TESTS/run_semantic_proof_phase1_regression.py",
            "TESTS/benchmark_context_efficiency.py",
            "TESTS/run_reference_discovery_regression.py",
            "TESTS/run_reference_discovery_equivalence.py",
            "TESTS/run_cleverence_exact_contract_regression.py",
            "TESTS/run_evidence_source_policy_regression.py",
            "TESTS/run_bootstrap_capability_regression.py",
        ]
        missing = [rel for rel in required if not (ROOT / rel).is_file()]
        if missing:
            errors.append({"type": "SHAREABLE_REQUIRED_FILE_MISSING", "paths": missing})

        restricted_runtime_refs = ("REFERENCE/SOURCES/", "REFERENCE/INDEXES/", "MAINTENANCE/INTERNAL/")
        for rel in (
            "SKILL.md",
            "KNOWLEDGE/CLEVERENCE_RUNTIME_INTEGRATION.md",
            ".github/workflows/shareable-validation.yml",
        ):
            path = ROOT / rel
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8-sig")
            found = [token for token in restricted_runtime_refs if token in text]
            if found:
                errors.append({"type": "SHAREABLE_RUNTIME_DEPENDS_ON_PRIVATE_PATH", "path": rel, "tokens": found})

        freshness = ROOT / "KNOWLEDGE/SKILL_FRESHNESS.md"
        if freshness.is_file():
            freshness_text = freshness.read_text(encoding="utf-8-sig")
            if re.search(r"(?m)^\s*repository\s*=\s*[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\s*$", freshness_text):
                errors.append({"type": "SHAREABLE_FRESHNESS_HARDCODES_REPOSITORY", "path": str(freshness.relative_to(ROOT))})

        commands = [
            [sys.executable, "-m", "compileall", "-q", "TOOLS", "TESTS"],
            [sys.executable, "TOOLS/generate_registry_views.py", "--check"],
            [sys.executable, "TESTS/run_cold_start_regression.py"],
            [sys.executable, "TESTS/run_pattern_regression.py"],
            [sys.executable, "TESTS/run_evidence_source_policy_regression.py"],
            [sys.executable, "TESTS/run_skill_freshness_regression.py"],
            [sys.executable, "TESTS/run_project_context_lifecycle_regression.py"],
            [sys.executable, "TESTS/run_distribution_privacy_regression.py"],
            [sys.executable, "TESTS/run_public_ci_regression.py"],
            [sys.executable, "TESTS/run_reference_discovery_regression.py"],
            [sys.executable, "TESTS/run_llm_bypass_regression.py"],
            [sys.executable, "TESTS/run_context_efficiency_regression.py"],
            [sys.executable, "TESTS/run_semantic_proof_phase1_regression.py"],
            [sys.executable, "TESTS/benchmark_context_efficiency.py"],
            [sys.executable, "TESTS/run_artifact_bootstrap_regression.py"],
            [sys.executable, "TESTS/run_bootstrap_capability_regression.py"],
            [sys.executable, "TESTS/run_external_source_regression.py"],
            [sys.executable, "TESTS/run_review_regression.py"],
        ]
        for command in commands:
            result = run(command)
            checks.append({"id": " ".join(command[1:]), "returncode": result["returncode"]})
            if result["returncode"] != 0:
                errors.append({"type": "SHAREABLE_CHECK_FAILED", "details": result})

    report = {
        "result": "PASS" if not errors else "FAIL",
        "profile": args.profile,
        "checks": checks,
        "errors": errors,
        "rule": "INTERNAL_FULL remains the strict private development validator. SHAREABLE_CORE contains bounded guidance/discovery layers with no proof role and no private reference/source/internal-maintenance paths. Non-proof artifacts are mechanically rejected as evidence by the canonical release gate; exact-source and runtime proof remain separate gates.",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
