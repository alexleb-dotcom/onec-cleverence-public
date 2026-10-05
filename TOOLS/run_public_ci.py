#!/usr/bin/env python3
"""Public-only CI runner backed by the canonical SHAREABLE_CORE inventory."""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

from validate_public_ci_inventory import INVENTORY_ID, INVENTORY_REL, INVENTORY_SCOPE, validate_inventory

ROOT = Path(__file__).resolve().parents[1]


def _render_command(command: list[str]) -> list[str]:
    return [sys.executable if token == "{python}" else token for token in command]


def load_public_check_sets(root: Path = ROOT) -> dict:
    root = root.resolve()
    validation = validate_inventory(root)
    if validation.get("result") != "PASS":
        return {
            "result": "FAIL",
            "scope": INVENTORY_SCOPE,
            "inventory_id": INVENTORY_ID,
            "errors": validation.get("errors", []),
            "inventory_validation": validation,
            "fast": [],
            "full": [],
        }

    payload = json.loads((root / INVENTORY_REL).read_text(encoding="utf-8"))
    full: list[tuple[str, list[str]]] = []
    fast: list[tuple[str, list[str]]] = []
    for row in payload["checks"]:
        rendered = (row["id"], _render_command(row["command"]))
        full.append(rendered)
        if row["phase"] == "FAST":
            fast.append(rendered)

    if full[:len(fast)] != fast:
        return {
            "result": "FAIL",
            "scope": INVENTORY_SCOPE,
            "inventory_id": INVENTORY_ID,
            "errors": [{"type": "PUBLIC_CI_FAST_NOT_PREFIX_OF_FULL"}],
            "inventory_validation": validation,
            "fast": fast,
            "full": full,
        }

    return {
        "result": "PASS",
        "scope": INVENTORY_SCOPE,
        "inventory_id": INVENTORY_ID,
        "inventory_validation": validation,
        "fast": fast,
        "full": full,
    }


def execute_checks(checks: list[tuple[str, list[str]]], cwd: Path = ROOT) -> dict:
    rows = []
    started = time.perf_counter()
    env = os.environ.copy()
    env["CI"] = "true"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # Keep compileall/import bytecode outside the governed snapshot tree. This is
    # required for deterministic validation on Windows as well as POSIX hosts.
    with tempfile.TemporaryDirectory(prefix="onec-public-ci-pycache-") as cache_root:
        env["PYTHONPYCACHEPREFIX"] = cache_root
        for check_id, command in checks:
            check_started = time.perf_counter()
            process = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            row = {
                "id": check_id,
                "outcome": "PASS" if process.returncode == 0 else "FAIL",
                "returncode": process.returncode,
                "elapsed_ms": round((time.perf_counter() - check_started) * 1000, 2),
            }
            if check_id == "context_efficiency" and process.returncode == 0:
                try:
                    payload = json.loads(process.stdout)
                except json.JSONDecodeError:
                    payload = {}
                metrics = payload.get("efficiency_metrics") if isinstance(payload, dict) else None
                if isinstance(metrics, dict):
                    row["efficiency_metrics"] = metrics
            rows.append(row)
            if process.returncode != 0:
                return {
                    "result": "FAIL",
                    "scope": INVENTORY_SCOPE,
                    "authoritative_private_acceptance": False,
                    "failed_check": check_id,
                    "checks": rows,
                    "stdout_tail": (process.stdout or "")[-8000:],
                    "stderr_tail": (process.stderr or "")[-8000:],
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                }
    return {
        "result": "PASS",
        "scope": INVENTORY_SCOPE,
        "authoritative_private_acceptance": False,
        "checks": rows,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def main() -> int:
    # Windows terminals may default to a legacy code page. Public CI reports are
    # UTF-8 JSON and must remain printable even when a child diagnostic contains
    # characters outside that code page.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Run public-only SHAREABLE_CORE CI checks from the canonical public-safe inventory.")
    parser.add_argument("--mode", required=True, choices=("FAST", "FULL"))
    args = parser.parse_args()

    loaded = load_public_check_sets(ROOT)
    if loaded["result"] != "PASS":
        report = {
            "result": "FAIL",
            "scope": INVENTORY_SCOPE,
            "authoritative_private_acceptance": False,
            "mode": args.mode,
            "inventory_id": INVENTORY_ID,
            "failed_check": "public_ci_inventory_contract",
            "checks": [],
            "errors": loaded.get("errors", []),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    checks = loaded["fast"] if args.mode == "FAST" else loaded["full"]
    report = execute_checks(checks)
    report["mode"] = args.mode
    report["inventory_id"] = INVENTORY_ID
    report["inventory_check_count"] = len(loaded["full"])
    report["selected_check_count"] = len(checks)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
