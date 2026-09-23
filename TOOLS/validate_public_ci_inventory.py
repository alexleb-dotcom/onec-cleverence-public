#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re

from validate_distribution_privacy import select_distribution_files

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_REL = "TOOLS/PUBLIC_CI_INVENTORY.json"
INVENTORY_ID = "public-safe-ci-v1"
INVENTORY_SCOPE = "PUBLIC_SHAREABLE_CORE_ONLY"
PHASES = ("FAST", "FULL")
CHECK_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
FORBIDDEN_COMMAND_PREFIXES = (
    "MAINTENANCE/INTERNAL/",
    "REFERENCE/SOURCES/",
    "REFERENCE/INDEXES/",
    "COLLECTOR/",
)
TOP_LEVEL_KEYS = frozenset({"schema_version", "inventory_id", "scope", "phases", "checks", "rule"})
CHECK_KEYS = frozenset({"id", "order", "phase", "scope", "command"})
COMPILE_COMMAND = ["{python}", "-m", "compileall", "-q", "TOOLS", "TESTS"]


def _finding(finding_type: str, **details) -> dict:
    return {"type": finding_type, **details}


def _safe_script_target(value: str) -> bool:
    if not value or "\\" in value or value.startswith("/") or value.startswith("./"):
        return False
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return False
    return value.endswith(".py") and (value.startswith("TOOLS/") or value.startswith("TESTS/"))


def _command_findings(root: Path, selected: set[str], check_id: str, command: object) -> list[dict]:
    errors: list[dict] = []
    if not isinstance(command, list) or not command or not all(isinstance(token, str) and token for token in command):
        return [_finding("PUBLIC_CI_COMMAND_SCHEMA_MISMATCH", id=check_id)]

    normalized_tokens = [token.replace("\\", "/") for token in command]
    forbidden = [prefix for prefix in FORBIDDEN_COMMAND_PREFIXES if any(prefix in token for token in normalized_tokens)]
    if forbidden:
        errors.append(_finding("PUBLIC_CI_FORBIDDEN_COMMAND_DEPENDENCY", id=check_id, prefixes=forbidden))

    if command == COMPILE_COMMAND:
        for rel in ("TOOLS", "TESTS"):
            if not (root / rel).is_dir():
                errors.append(_finding("PUBLIC_CI_COMMAND_TARGET_MISSING", id=check_id, target=rel))
        return errors

    if command[0] != "{python}" or len(command) < 2 or command[1] == "-m":
        errors.append(_finding("PUBLIC_CI_UNKNOWN_COMMAND", id=check_id))
        return errors

    target = command[1]
    if not _safe_script_target(target):
        errors.append(_finding("PUBLIC_CI_UNKNOWN_COMMAND", id=check_id, target=target))
        return errors
    if not (root / target).is_file():
        errors.append(_finding("PUBLIC_CI_COMMAND_TARGET_MISSING", id=check_id, target=target))
    if target not in selected:
        errors.append(_finding("PUBLIC_CI_COMMAND_TARGET_NOT_SHAREABLE", id=check_id, target=target))
    return errors


def validate_inventory(root: Path = ROOT, inventory_path: Path | None = None) -> dict:
    root = root.resolve()
    inventory_path = (inventory_path or (root / INVENTORY_REL)).resolve()
    errors: list[dict] = []

    try:
        inventory_path.relative_to(root)
    except ValueError:
        return {"result": "FAIL", "errors": [_finding("PUBLIC_CI_INVENTORY_OUTSIDE_ROOT")], "checks": 0}

    if not inventory_path.is_file():
        return {"result": "FAIL", "errors": [_finding("PUBLIC_CI_INVENTORY_MISSING", path=INVENTORY_REL)], "checks": 0}

    try:
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"result": "FAIL", "errors": [_finding("PUBLIC_CI_INVENTORY_INVALID_JSON", error=str(exc))], "checks": 0}

    if not isinstance(payload, dict) or set(payload) != TOP_LEVEL_KEYS:
        return {
            "result": "FAIL",
            "errors": [_finding("PUBLIC_CI_INVENTORY_SCHEMA_MISMATCH", keys=sorted(payload) if isinstance(payload, dict) else None)],
            "checks": 0,
        }

    if payload.get("schema_version") != 1:
        errors.append(_finding("PUBLIC_CI_INVENTORY_SCHEMA_VERSION_MISMATCH"))
    if payload.get("inventory_id") != INVENTORY_ID:
        errors.append(_finding("PUBLIC_CI_INVENTORY_ID_MISMATCH"))
    if payload.get("scope") != INVENTORY_SCOPE:
        errors.append(_finding("PUBLIC_CI_INVENTORY_SCOPE_MISMATCH"))
    if payload.get("phases") != list(PHASES):
        errors.append(_finding("PUBLIC_CI_PHASES_MISMATCH"))
    if not isinstance(payload.get("rule"), str) or not payload["rule"].strip():
        errors.append(_finding("PUBLIC_CI_RULE_MISSING"))

    try:
        selection = select_distribution_files(root)
    except Exception as exc:
        return {
            "result": "FAIL",
            "errors": errors + [_finding("PUBLIC_CI_SHAREABLE_SELECTION_UNAVAILABLE", error=str(exc))],
            "checks": 0,
        }
    selected = set(selection.get("selected") or [])
    inventory_rel = inventory_path.relative_to(root).as_posix()
    if inventory_rel not in selected:
        errors.append(_finding("PUBLIC_CI_INVENTORY_NOT_SHAREABLE", path=inventory_rel))

    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append(_finding("PUBLIC_CI_CHECKS_NOT_LIST"))
        checks = []

    seen_ids: set[str] = set()
    seen_commands: set[str] = set()
    previous_order = -1
    previous_phase_index = -1
    phase_counts = {phase: 0 for phase in PHASES}

    for index, row in enumerate(checks):
        if not isinstance(row, dict) or set(row) != CHECK_KEYS:
            errors.append(_finding("PUBLIC_CI_CHECK_SCHEMA_MISMATCH", index=index))
            continue

        check_id = row.get("id")
        if not isinstance(check_id, str) or not CHECK_ID_RE.fullmatch(check_id):
            errors.append(_finding("PUBLIC_CI_INVALID_CHECK_ID", index=index))
            check_id = f"invalid_{index}"
        elif check_id in seen_ids:
            errors.append(_finding("PUBLIC_CI_DUPLICATE_CHECK_ID", id=check_id))
        seen_ids.add(check_id)

        order = row.get("order")
        if not isinstance(order, int) or isinstance(order, bool) or order <= previous_order:
            errors.append(_finding("PUBLIC_CI_ORDER_NOT_STRICT", id=check_id, order=order, previous=previous_order))
        if isinstance(order, int) and not isinstance(order, bool):
            previous_order = max(previous_order, order)

        phase = row.get("phase")
        if phase not in PHASES:
            errors.append(_finding("PUBLIC_CI_INVALID_PHASE", id=check_id, phase=phase))
        else:
            phase_index = PHASES.index(phase)
            phase_counts[phase] += 1
            if phase_index < previous_phase_index:
                errors.append(_finding("PUBLIC_CI_PHASE_ORDER_INVALID", id=check_id, phase=phase))
            previous_phase_index = max(previous_phase_index, phase_index)

        if row.get("scope") != INVENTORY_SCOPE:
            errors.append(_finding("PUBLIC_CI_SCOPE_MISMATCH", id=check_id))

        command = row.get("command")
        if isinstance(command, list) and all(isinstance(token, str) for token in command):
            command_key = json.dumps(command, ensure_ascii=False, separators=(",", ":"))
            if command_key in seen_commands:
                errors.append(_finding("PUBLIC_CI_DUPLICATE_COMMAND", id=check_id))
            seen_commands.add(command_key)
        errors.extend(_command_findings(root, selected, check_id, command))

    for phase, count in phase_counts.items():
        if count == 0:
            errors.append(_finding("PUBLIC_CI_PHASE_EMPTY", phase=phase))

    return {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checks": len(checks),
        "fast_checks": phase_counts["FAST"],
        "full_only_checks": phase_counts["FULL"],
        "scope": INVENTORY_SCOPE,
        "inventory_id": INVENTORY_ID,
        "rule": "The canonical public-safe CI inventory has stable ids, strict order, FAST/FULL phase ownership, public-only scope, known Python commands, and command targets present in SHAREABLE_CORE.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the canonical public-safe CI inventory contract.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--inventory")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    inventory = Path(args.inventory).resolve() if args.inventory else None
    report = validate_inventory(root, inventory)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
