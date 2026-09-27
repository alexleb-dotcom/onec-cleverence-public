#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from run_public_ci import execute_checks, load_public_check_sets

results = {}
errors = []


def record(case: str, ok: bool, details) -> None:
    key = f"public_ci:{case}"
    results[key] = {"pass": bool(ok), "details": details}
    if not ok:
        errors.append({"case": key, "details": details})


inventory = json.loads((ROOT / "TOOLS/PUBLIC_CI_INVENTORY.json").read_text(encoding="utf-8"))
loaded = load_public_check_sets(ROOT)
record("canonical_inventory_loads", loaded["result"] == "PASS", loaded.get("errors", []))

expected_fast_ids = [row["id"] for row in inventory["checks"] if row["phase"] == "FAST"]
expected_full_ids = [row["id"] for row in inventory["checks"]]
fast_ids = [row[0] for row in loaded.get("fast", [])]
full_ids = [row[0] for row in loaded.get("full", [])]
record("fast_is_exact_inventory_subset", fast_ids == expected_fast_ids, {"actual": fast_ids, "expected": expected_fast_ids})
record("full_is_exact_complete_inventory", full_ids == expected_full_ids, {"actual": full_ids, "expected": expected_full_ids})
record("fast_is_bounded_prefix_of_full", full_ids[:len(fast_ids)] == fast_ids and len(full_ids) > len(fast_ids), {"fast": len(fast_ids), "full": len(full_ids)})
record("shareable_profile_is_retained_inside_full_inventory", "shareable_profile" in full_ids and full_ids != ["shareable_profile"], full_ids)

forbidden_tokens = [
    "MAINTENANCE" + "/INTERNAL/",
    "REFERENCE" + "/SOURCES/",
    "REFERENCE" + "/INDEXES/",
    "COLLECTOR" + "/",
]
all_commands = loaded.get("full", [])
command_text = "\n".join(" ".join(command) for _, command in all_commands)
record("commands_have_no_private_inputs", not any(token in command_text for token in forbidden_tokens), [token for token in forbidden_tokens if token in command_text])
record("python_placeholder_is_fully_rendered", all("{python}" not in command for _, command in all_commands), all_commands[:3])

missing_paths = []
for _, command in all_commands:
    for token in command:
        if token.startswith("TOOLS/") or token.startswith("TESTS/"):
            if not (ROOT / token).is_file():
                missing_paths.append(token)
record("referenced_public_scripts_exist", not missing_paths, missing_paths)

profile_source = (ROOT / "TOOLS/validate_distribution_profile.py").read_text(encoding="utf-8")
collector_regression_tokens = [
    "run_project_snapshot_collection_regression.py",
    "run_project_snapshot_runtime_collector_regression.py",
    "run_project_snapshot_epf_source_regression.py",
    "run_project_snapshot_runtime_acceptance_regression.py",
    "run_project_snapshot_distribution_regression.py",
    "run_project_snapshot_package_validation_regression.py",
]
record(
    "shareable_profile_does_not_require_excluded_collector_regressions",
    not any(token in profile_source for token in collector_regression_tokens),
    [token for token in collector_regression_tokens if token in profile_source],
)

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    blocked = load_public_check_sets(root)
    record(
        "missing_inventory_blocks_before_execution",
        blocked["result"] == "FAIL"
        and any(row.get("type") == "PUBLIC_CI_INVENTORY_MISSING" for row in blocked.get("errors", []))
        and not blocked.get("fast")
        and not blocked.get("full"),
        blocked,
    )

    pass_report = execute_checks(
        [
            ("one", [sys.executable, "-c", "raise SystemExit(0)"]),
            ("two", [sys.executable, "-c", "raise SystemExit(0)"]),
        ],
        cwd=root,
    )
    record(
        "synthetic_pass_has_public_only_boundary",
        pass_report["result"] == "PASS"
        and pass_report["scope"] == "PUBLIC_SHAREABLE_CORE_ONLY"
        and pass_report["authoritative_private_acceptance"] is False
        and [row["id"] for row in pass_report["checks"]] == ["one", "two"],
        pass_report,
    )

    metric_payload = {
        "result": "PASS",
        "efficiency_metrics": {
            "skill_utf8_bytes": 100,
            "skill_lines": 10,
            "compact_plan_bytes": 20,
            "work_queue_bytes": 30,
            "combined_compact_bytes": 50,
            "active_profile_count": 1,
            "active_delivery_count": 2,
            "active_support_reference_count": 3,
        },
    }
    metric_report = execute_checks(
        [
            (
                "context_efficiency",
                [sys.executable, "-c", "import json; print(json.dumps(" + repr(metric_payload) + "))"],
            ),
        ],
        cwd=root,
    )
    metric_row = metric_report["checks"][0]
    record(
        "context_efficiency_metrics_are_exposed_in_public_run_report",
        metric_report["result"] == "PASS"
        and metric_row.get("efficiency_metrics") == metric_payload["efficiency_metrics"],
        metric_report,
    )

    fail_report = execute_checks(
        [
            ("first", [sys.executable, "-c", "raise SystemExit(0)"]),
            ("stop", [sys.executable, "-c", "raise SystemExit(7)"]),
            ("must_not_run", [sys.executable, "-c", "raise SystemExit(0)"]),
        ],
        cwd=root,
    )
    record(
        "synthetic_failure_is_fail_fast",
        fail_report["result"] == "FAIL"
        and fail_report["failed_check"] == "stop"
        and [row["id"] for row in fail_report["checks"]] == ["first", "stop"],
        fail_report,
    )

out = {"result": "PASS" if not errors else "FAIL", "errors": errors, "results": results}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
