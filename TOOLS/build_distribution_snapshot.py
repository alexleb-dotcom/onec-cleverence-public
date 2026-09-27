#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import zipfile

from validate_distribution_privacy import ROOT, select_distribution_files, validate_distribution_paths
from validate_distribution_snapshot import build_distribution_manifest


ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_FILE_MODE = 0o100644


def _write_deterministic_file(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.create_system = 3
    info.external_attr = ZIP_FILE_MODE << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_distribution(output: Path, root: Path = ROOT) -> dict:
    selection = select_distribution_files(root)
    if selection.get("unsafe"):
        return {
            "result": "FAIL",
            "errors": [{"type": "MANIFEST_UNSAFE_SELECTED_PATH", "paths": selection["unsafe"]}],
            "selection": selection,
        }
    if selection["missing"]:
        return {
            "result": "FAIL",
            "errors": [{"type": "MANIFEST_SELECTED_FILE_MISSING", "paths": selection["missing"]}],
            "selection": selection,
        }

    privacy = validate_distribution_paths(root, selection["selected"])
    if privacy["result"] != "PASS":
        return {"result": "FAIL", "errors": privacy["errors"], "selection": selection, "privacy": privacy}

    rows = []
    for rel in sorted(selection["selected"]):
        data = (root / rel).read_bytes()
        rows.append({"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    distribution_manifest = build_distribution_manifest(rows)
    manifest_bytes = (json.dumps(distribution_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for row in rows:
            _write_deterministic_file(
                archive,
                f"onec-cleverence/{row['path']}",
                (root / row["path"]).read_bytes(),
            )
        _write_deterministic_file(
            archive,
            "onec-cleverence/DISTRIBUTION_MANIFEST.json",
            manifest_bytes,
        )

    return {
        "result": "PASS",
        "output": str(output),
        "file_count": len(rows),
        "snapshot_digest": distribution_manifest["snapshot_digest"],
        "archive_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "selection": selection,
        "privacy": privacy,
        "distribution_manifest": distribution_manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a privacy-validated SHAREABLE_CORE ZIP without Git history or restricted reference/project material.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    report = build_distribution(Path(args.output).resolve(), Path(args.root).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
