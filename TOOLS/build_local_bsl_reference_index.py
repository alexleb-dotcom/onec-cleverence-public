#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json

from check_bsl_call_signatures import load_definitions


def _fingerprint(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def build_index(zips: list[Path], files: list[Path]) -> dict:
    signatures = load_definitions(zips, files)
    rows = []
    for _, sig in sorted(signatures.items(), key=lambda item: (item[1]["module"].casefold(), item[1]["name"].casefold())):
        rows.append({
            "module": sig["module"],
            "name": sig["name"],
            "kind": sig["kind"],
            "required_params": sig["required"],
            "total_params": sig["total"],
            "params": sig["params"],
            "interface_comment": sig.get("interface_comment", ""),
            "source": sig["source"],
            "line": sig["line"],
        })

    return {
        "schema_version": 2,
        "role": "LOCAL_EXACT_SOURCE_INDEX",
        "source_inputs": {
            "zips": [_fingerprint(x) for x in zips],
            "files": [_fingerprint(x) for x in files],
        },
        "definitions": rows,
        "definition_count": len(rows),
        "rule": "This index is generated from exact user/target/authorized BSL source for the current task. Signatures and interface comments are exact-source evidence for that source snapshot, not reusable public reference data, and the generated index should not be committed into the universal shareable skill.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an ephemeral exact exported-BSL API index from user/target/authorized source.")
    parser.add_argument("--source-zip", action="append", default=[])
    parser.add_argument("--source-file", action="append", default=[])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    zips = [Path(x) for x in args.source_zip]
    files = [Path(x) for x in args.source_file]
    if not zips and not files:
        parser.error("at least one --source-zip or --source-file is required")
    missing = [str(x) for x in [*zips, *files] if not x.is_file()]
    if missing:
        print(json.dumps({"result": "FAIL", "errors": [{"type": "SOURCE_MISSING", "paths": missing}]}, ensure_ascii=False, indent=2))
        return 2

    report = build_index(zips, files)
    out = Path(args.output)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "output": str(out), "definition_count": report["definition_count"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())