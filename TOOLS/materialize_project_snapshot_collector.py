#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import base64
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/ProjectSnapshotCollector.artifact.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1_bytes(data: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    return git_blob_sha1_bytes(path.read_bytes())


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("artifact manifest schema_version must be 1")
    return data


def materialize_payload(manifest: dict) -> tuple[bytes, list[dict]]:
    payload = manifest.get("payload") or {}
    if payload.get("encoding") != "base64_parts":
        raise ValueError(f"unsupported collector payload encoding: {payload.get('encoding')}")

    parts = payload.get("parts") or []
    if not parts:
        raise ValueError("collector payload parts are missing")

    encoded_parts: list[str] = []
    verified_parts: list[dict] = []
    for index, part in enumerate(parts, start=1):
        rel = str(part.get("path") or "")
        expected_blob = str(part.get("git_blob_sha1") or "")
        if not rel or not expected_blob:
            raise ValueError(f"collector payload part {index} is incomplete")
        path = ROOT / rel
        if not path.is_file():
            raise FileNotFoundError(f"collector payload part not found: {rel}")

        raw = path.read_bytes()
        actual_blob = git_blob_sha1_bytes(raw)
        if actual_blob != expected_blob:
            raise ValueError(
                f"collector payload part git blob mismatch: path={rel} "
                f"expected={expected_blob} actual={actual_blob}"
            )
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError(f"collector payload part is not ASCII base64: {rel}") from exc
        if text != text.strip() or any(char.isspace() for char in text):
            raise ValueError(f"collector payload part contains forbidden whitespace: {rel}")

        encoded_parts.append(text)
        verified_parts.append({"path": rel, "git_blob_sha1": actual_blob})

    encoded = "".join(encoded_parts)
    expected_encoded_size = payload.get("encoded_size_chars")
    if len(encoded) != expected_encoded_size:
        raise ValueError(
            f"collector payload encoded size mismatch: expected={expected_encoded_size} actual={len(encoded)}"
        )
    try:
        binary = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("collector payload is not strict base64") from exc
    return binary, verified_parts


def validate_artifact(manifest_path: Path) -> tuple[dict, bytes]:
    manifest = load_manifest(manifest_path)
    if manifest.get("status") != "READY":
        raise ValueError(f"collector artifact is not distributable: status={manifest.get('status')}")

    binary = manifest.get("binary") or {}
    source = manifest.get("source") or {}
    binary_bytes, verified_payload_parts = materialize_payload(manifest)

    actual_size = len(binary_bytes)
    actual_sha = sha256_bytes(binary_bytes)
    actual_blob_sha = git_blob_sha1_bytes(binary_bytes)
    expected_size = binary.get("size_bytes")
    expected_sha = binary.get("sha256")
    expected_blob_sha = binary.get("git_blob_sha1")
    if actual_size != expected_size:
        raise ValueError(f"collector binary size mismatch: expected={expected_size} actual={actual_size}")
    if actual_sha != expected_sha:
        raise ValueError(f"collector binary sha256 mismatch: expected={expected_sha} actual={actual_sha}")
    if actual_blob_sha != expected_blob_sha:
        raise ValueError(
            f"collector binary git blob mismatch: expected={expected_blob_sha} actual={actual_blob_sha}"
        )

    build_inputs = source.get("build_inputs") or {}
    if not build_inputs:
        raise ValueError("collector source build_inputs are missing")

    verified_inputs: list[dict] = []
    for rel, expected_git_blob in sorted(build_inputs.items()):
        path = ROOT / rel
        if not path.is_file():
            raise FileNotFoundError(f"collector build input not found: {rel}")
        actual_git_blob = git_blob_sha1(path)
        if actual_git_blob != expected_git_blob:
            raise ValueError(
                "collector build input changed after accepted binary build: "
                f"path={rel} expected={expected_git_blob} actual={actual_git_blob}"
            )
        verified_inputs.append({"path": rel, "git_blob_sha1": actual_git_blob})

    acceptance = manifest.get("build_acceptance") or {}
    if acceptance.get("epf_build_open_proven") is not True:
        raise ValueError("collector binary lacks EPF build/open acceptance")
    if acceptance.get("source_export_runtime_accepted") is not True:
        raise ValueError("collector binary lacks SOURCE_EXPORT runtime acceptance")

    filename = str(binary.get("filename") or "")
    if filename != "ProjectSnapshotCollector.epf":
        raise ValueError(f"collector binary filename mismatch: {filename}")

    return {
        "artifact": filename,
        "sha256": actual_sha,
        "size_bytes": actual_size,
        "git_blob_sha1": actual_blob_sha,
        "verified_payload_parts": verified_payload_parts,
        "source_commit": source.get("source_commit"),
        "verified_build_inputs": verified_inputs,
        "platform_version": acceptance.get("platform_version"),
        "acceptance_request_id": acceptance.get("acceptance_request_id"),
    }, binary_bytes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and materialize the repository-pinned ProjectSnapshotCollector.epf."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        result, binary_bytes = validate_artifact(args.manifest)
    except Exception as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(binary_bytes)
        result["materialized_to"] = str(args.output)

    print(json.dumps({"result": "PASS", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
