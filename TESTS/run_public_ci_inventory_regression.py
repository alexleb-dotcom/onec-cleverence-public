#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from validate_public_ci_inventory import INVENTORY_ID, INVENTORY_SCOPE, validate_inventory


def base_inventory() -> dict:
    return {
        "schema_version": 1,
        "inventory_id": INVENTORY_ID,
        "scope": INVENTORY_SCOPE,
        "phases": ["FAST", "FULL"],
        "checks": [
            {"id": "inventory", "order": 10, "phase": "FAST", "scope": INVENTORY_SCOPE, "command": ["{python}", "TOOLS/validate_public_ci_inventory.py"]},
            {"id": "fast", "order": 20, "phase": "FAST", "scope": INVENTORY_SCOPE, "command": ["{python}", "TESTS/fast.py"]},
            {"id": "full", "order": 30, "phase": "FULL", "scope": INVENTORY_SCOPE, "command": ["{python}", "TESTS/full.py"]},
        ],
        "rule": "synthetic public-safe inventory",
    }


def prepare_root(root: Path, payload: dict) -> None:
    (root / "TOOLS").mkdir(parents=True, exist_ok=True)
    (root / "TESTS").mkdir(parents=True, exist_ok=True)
    for rel in ("TOOLS/validate_public_ci_inventory.py", "TESTS/fast.py", "TESTS/full.py"):
        (root / rel).write_text("raise SystemExit(0)\n", encoding="utf-8")
    (root / "TOOLS" / "PUBLIC_CI_INVENTORY.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (root / "manifest.txt").write_text(
        "TOOLS/PUBLIC_CI_INVENTORY.json\n"
        "TOOLS/validate_public_ci_inventory.py\n"
        "TESTS/fast.py\n"
        "TESTS/full.py\n",
        encoding="utf-8",
    )


def finding_types(report: dict) -> set[str]:
    return {row.get("type") for row in report.get("errors", [])}


def run_case(mutator=None) -> dict:
    payload = base_inventory()
    if mutator is not None:
        mutator(payload)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        prepare_root(root, payload)
        return validate_inventory(root)


def require(case: str, report: dict, finding: str) -> None:
    if finding not in finding_types(report):
        raise AssertionError(f"{case}: expected {finding}, got {report!r}")


def main() -> int:
    clean = run_case()
    if clean.get("result") != "PASS" or clean.get("fast_checks") != 2 or clean.get("full_only_checks") != 1:
        raise AssertionError(f"clean inventory should pass: {clean!r}")

    require("duplicate-id", run_case(lambda p: p["checks"].__setitem__(2, {**p["checks"][2], "id": "fast"})), "PUBLIC_CI_DUPLICATE_CHECK_ID")
    require("unknown-command", run_case(lambda p: p["checks"][1].__setitem__("command", ["bash", "TESTS/fast.py"])), "PUBLIC_CI_UNKNOWN_COMMAND")
    require("unknown-target", run_case(lambda p: p["checks"][1].__setitem__("command", ["{python}", "TESTS/missing.py"])), "PUBLIC_CI_COMMAND_TARGET_MISSING")
    require("bad-order", run_case(lambda p: p["checks"][1].__setitem__("order", 5)), "PUBLIC_CI_ORDER_NOT_STRICT")
    require("bad-phase", run_case(lambda p: p["checks"][1].__setitem__("phase", "SLOW")), "PUBLIC_CI_INVALID_PHASE")
    def reverse_phase_order(payload: dict) -> None:
        payload["checks"][1]["phase"] = "FULL"
        payload["checks"][2]["phase"] = "FAST"
    require("phase-order", run_case(reverse_phase_order), "PUBLIC_CI_PHASE_ORDER_INVALID")
    require("bad-scope", run_case(lambda p: p["checks"][1].__setitem__("scope", "PRIVATE")), "PUBLIC_CI_SCOPE_MISMATCH")
    require("private-dependency", run_case(lambda p: p["checks"][1].__setitem__("command", ["{python}", "TESTS/fast.py", "REFERENCE/SOURCES/private.zip"])), "PUBLIC_CI_FORBIDDEN_COMMAND_DEPENDENCY")

    def malformed(payload: dict) -> None:
        payload.pop("phases")
    require("schema", run_case(malformed), "PUBLIC_CI_INVENTORY_SCHEMA_MISMATCH")

    def duplicate_command(payload: dict) -> None:
        payload["checks"][2]["command"] = copy.deepcopy(payload["checks"][1]["command"])
    require("duplicate-command", run_case(duplicate_command), "PUBLIC_CI_DUPLICATE_COMMAND")

    print(json.dumps({"result": "PASS", "cases": 11}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
