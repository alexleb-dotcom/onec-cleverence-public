#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "WORKFLOW" / "RESULT_DELIVERY_CONTRACT.json"

BINDING_PREFIX = "ONEC_RESULT_DELIVERY_BINDING_V1:"
BINDING_FIELDS = (
    "task_id",
    "candidate_sha256",
    "package_binding_sha256",
    "change_items_sha256",
    "result_mode",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FINAL_PHASE = "POST_RENDER_POST_PUBLISH_PRE_DELIVERY"
OOXML_REQUIRED_PARTS = (
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "docProps/core.xml",
)
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DC_NS = "http://purl.org/dc/elements/1.1/"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _is_sha256(value: object) -> bool:
    return bool(SHA256_RE.fullmatch(str(value or "")))


def _safe_relative_path(value: object) -> PurePosixPath | None:
    text = str(value or "")
    if not text or "\\" in text:
        return None
    rel = PurePosixPath(text)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        return None
    return rel


def _resolve_relative(package_root: Path, value: object) -> Path | None:
    rel = _safe_relative_path(value)
    if rel is None:
        return None
    root = package_root.resolve()
    resolved = (root / Path(*rel.parts)).resolve()
    if resolved != root and root not in resolved.parents:
        return None
    return resolved


def _canonical_filename_map(contract: dict) -> dict[str, str]:
    profiles = contract.get("profiles") or {}
    implementation = profiles.get("IMPLEMENTATION_DELIVERY") or {}
    requirements = profiles.get("REQUIREMENTS_ARTIFACT") or {}
    return {
        "implementation_notes": str((implementation.get("implementation_notes") or {}).get("filename_ru") or ""),
        "manual_transfer": str((implementation.get("manual_transfer_artifact_output") or {}).get("filename_ru") or ""),
        "requirements": str((requirements.get("artifact_output") or {}).get("filename_ru") or ""),
        "line_by_line": str((implementation.get("line_by_line_justification") or {}).get("filename_ru") or ""),
    }


def derive_required_kinds(context: dict, contract: dict) -> list[str]:
    required: list[str] = []
    if context.get("nontrivial_implementation") is True:
        required.append("implementation_notes")
    if context.get("result_mode") == "MANUAL_TRANSFER_INSTRUCTION":
        required.append("manual_transfer")
    if context.get("requirements_artifact_required") is True:
        required.append("requirements")
    if context.get("line_by_line_requested") is True:
        required.append("line_by_line")
    return required


def _parse_ooxml(path: Path) -> tuple[list[str], str | None]:
    errors: list[str] = []
    if not zipfile.is_zipfile(path):
        return ["DOCX_NOT_ZIP_CONTAINER"], None
    identifier: str | None = None
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            for part in OOXML_REQUIRED_PARTS:
                if part not in names:
                    errors.append(f"DOCX_MANDATORY_PART_MISSING:{part}")
            if errors:
                return errors, None

            try:
                content_types = ET.fromstring(zf.read("[Content_Types].xml"))
                overrides = content_types.findall(f"{{{CONTENT_TYPES_NS}}}Override")
                if not any(
                    row.attrib.get("PartName") == "/word/document.xml"
                    and "wordprocessingml.document.main+xml" in row.attrib.get("ContentType", "")
                    for row in overrides
                ):
                    errors.append("DOCX_MAIN_CONTENT_TYPE_MISSING")
            except (ET.ParseError, KeyError):
                errors.append("DOCX_CONTENT_TYPES_INVALID")

            try:
                rels = ET.fromstring(zf.read("_rels/.rels"))
                relationships = rels.findall(f"{{{REL_NS}}}Relationship")
                if not any(
                    row.attrib.get("Type", "").endswith("/officeDocument")
                    and row.attrib.get("Target", "").lstrip("/") == "word/document.xml"
                    for row in relationships
                ):
                    errors.append("DOCX_OFFICE_DOCUMENT_RELATION_MISSING")
            except (ET.ParseError, KeyError):
                errors.append("DOCX_ROOT_RELS_INVALID")

            try:
                document = ET.fromstring(zf.read("word/document.xml"))
                if not str(document.tag).endswith("}document"):
                    errors.append("DOCX_WORD_DOCUMENT_ROOT_INVALID")
            except (ET.ParseError, KeyError):
                errors.append("DOCX_WORD_DOCUMENT_INVALID")

            try:
                core = ET.fromstring(zf.read("docProps/core.xml"))
                node = core.find(f"{{{DC_NS}}}identifier")
                identifier = (node.text or "").strip() if node is not None else None
            except (ET.ParseError, KeyError):
                errors.append("DOCX_CORE_PROPERTIES_INVALID")
    except (OSError, zipfile.BadZipFile):
        errors.append("DOCX_CONTAINER_READ_FAILED")
    return errors, identifier


def _parse_binding(identifier: str | None) -> tuple[dict | None, str | None]:
    if not identifier or not identifier.startswith(BINDING_PREFIX):
        return None, "DOCX_DELIVERY_BINDING_MISSING"
    raw = identifier[len(BINDING_PREFIX):]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None, "DOCX_DELIVERY_BINDING_INVALID_JSON"
    if not isinstance(value, dict):
        return None, "DOCX_DELIVERY_BINDING_INVALID_SHAPE"
    return value, None


def _validate_context(context: dict, contract: dict, errors: list[dict]) -> None:
    if not isinstance(context, dict):
        errors.append({"type": "FINAL_DOCX_CONTEXT_INVALID"})
        return
    if context.get("phase") != FINAL_PHASE:
        errors.append({
            "type": "FINAL_DOCX_PHASE_INVALID",
            "expected": FINAL_PHASE,
            "actual": context.get("phase"),
        })
    for field in BINDING_FIELDS:
        if context.get(field) in (None, ""):
            errors.append({"type": "FINAL_DOCX_BINDING_FIELD_MISSING", "field": field})
    for field in ("candidate_sha256", "package_binding_sha256", "change_items_sha256"):
        if context.get(field) not in (None, "") and not _is_sha256(context.get(field)):
            errors.append({"type": "FINAL_DOCX_BINDING_SHA_INVALID", "field": field})
    implementation = ((contract.get("profiles") or {}).get("IMPLEMENTATION_DELIVERY") or {})
    allowed_modes = set(implementation.get("primary_result_modes") or [])
    if context.get("result_mode") not in allowed_modes:
        errors.append({
            "type": "FINAL_DOCX_RESULT_MODE_INVALID",
            "actual": context.get("result_mode"),
        })
    for field in (
        "nontrivial_implementation",
        "requirements_artifact_required",
        "line_by_line_requested",
        "combined_alternate_requested",
    ):
        if context.get(field) not in (True, False):
            errors.append({"type": "FINAL_DOCX_CONTEXT_BOOLEAN_INVALID", "field": field})


def _expected_binding(context: dict, kind: str) -> dict:
    binding = {field: str(context.get(field) or "") for field in BINDING_FIELDS}
    binding["artifact_kind"] = kind
    return binding


def _validate_publication(
    package_root: Path,
    publication: object,
    final_sha256: str,
    errors: list[dict],
    route_e2e_required: list[str],
    kind: str,
) -> dict:
    if not isinstance(publication, dict):
        errors.append({"type": "FINAL_DOCX_PUBLICATION_REFERENCE_MISSING", "kind": kind})
        return {"status": "INVALID"}
    publication_kind = publication.get("kind")
    if publication_kind == "LOCAL_FILE":
        path = _resolve_relative(package_root, publication.get("path"))
        if path is None:
            errors.append({"type": "FINAL_DOCX_PUBLICATION_PATH_INVALID", "kind": kind})
            return {"status": "INVALID"}
        try:
            mode = path.stat().st_mode
        except OSError:
            errors.append({"type": "FINAL_DOCX_PUBLICATION_FILE_MISSING", "kind": kind})
            return {"status": "INVALID", "path": publication.get("path")}
        if path.is_symlink() or not stat.S_ISREG(mode):
            errors.append({"type": "FINAL_DOCX_PUBLICATION_NOT_REGULAR_FILE", "kind": kind})
            return {"status": "INVALID", "path": publication.get("path")}
        published = path.read_bytes()
        published_sha = _sha256(published)
        if published_sha != final_sha256:
            errors.append({
                "type": "FINAL_DOCX_PUBLICATION_BYTES_MISMATCH",
                "kind": kind,
                "expected_sha256": final_sha256,
                "actual_sha256": published_sha,
            })
            return {
                "status": "INVALID",
                "kind": "LOCAL_FILE",
                "path": publication.get("path"),
                "sha256": published_sha,
            }
        return {
            "status": "VERIFIED_LOCAL_BYTES",
            "kind": "LOCAL_FILE",
            "path": publication.get("path"),
            "sha256": published_sha,
        }
    if publication_kind == "PLATFORM_ATTACHMENT":
        ref = str(publication.get("ref") or "")
        if not ref:
            errors.append({"type": "FINAL_DOCX_PLATFORM_ATTACHMENT_REF_MISSING", "kind": kind})
            return {"status": "INVALID", "kind": "PLATFORM_ATTACHMENT"}
        route_e2e_required.append(f"publication:{kind}")
        return {
            "status": "REQUIRES_ROUTE_E2E",
            "kind": "PLATFORM_ATTACHMENT",
            "ref": ref,
        }
    errors.append({
        "type": "FINAL_DOCX_PUBLICATION_KIND_INVALID",
        "kind": kind,
        "actual": publication_kind,
    })
    return {"status": "INVALID"}


def validate_final_docx_set(manifest: dict, package_root: Path, contract: dict | None = None) -> dict:
    contract = contract or _load_contract()
    errors: list[dict] = []
    route_e2e_required: list[str] = []
    context = manifest.get("context") if isinstance(manifest, dict) else None
    if not isinstance(manifest, dict):
        return {
            "schema_version": 1,
            "receipt_kind": "FINAL_DOCX_SET",
            "owner": "RESULT_DELIVERY",
            "result": "FAIL",
            "errors": [{"type": "FINAL_DOCX_MANIFEST_INVALID"}],
        }
    if manifest.get("schema_version") != 1:
        errors.append({
            "type": "FINAL_DOCX_MANIFEST_SCHEMA_INVALID",
            "actual": manifest.get("schema_version"),
        })
    _validate_context(context if isinstance(context, dict) else {}, contract, errors)
    context = context if isinstance(context, dict) else {}
    required_kinds = derive_required_kinds(context, contract)
    filenames = _canonical_filename_map(contract)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
        errors.append({"type": "FINAL_DOCX_ARTIFACT_MAP_INVALID"})

    package_root = package_root.resolve()
    artifact_receipts: dict[str, dict] = {}
    observed_paths: dict[str, str] = {}
    observed_hashes: dict[str, list[str]] = {}

    for kind in required_kinds:
        row = artifacts.get(kind)
        if not isinstance(row, dict):
            errors.append({"type": "FINAL_DOCX_REQUIRED_ARTIFACT_MISSING", "kind": kind})
            continue

        expected_filename = filenames.get(kind) or ""
        expected_rel = f"Output/{expected_filename}"
        actual_rel = row.get("path")
        if actual_rel != expected_rel:
            errors.append({
                "type": "FINAL_DOCX_KIND_PATH_MAPPING_INVALID",
                "kind": kind,
                "expected": expected_rel,
                "actual": actual_rel,
            })
        path = _resolve_relative(package_root, actual_rel)
        if path is None:
            errors.append({"type": "FINAL_DOCX_PATH_INVALID", "kind": kind, "path": actual_rel})
            continue

        try:
            mode = path.stat().st_mode
        except OSError:
            errors.append({"type": "FINAL_DOCX_FILE_MISSING", "kind": kind, "path": actual_rel})
            continue
        if path.is_symlink() or not stat.S_ISREG(mode):
            errors.append({"type": "FINAL_DOCX_NOT_REGULAR_FILE", "kind": kind, "path": actual_rel})
            continue
        if path.suffix.lower() != ".docx":
            errors.append({"type": "FINAL_DOCX_SUFFIX_INVALID", "kind": kind, "path": actual_rel})
            continue
        if path.stat().st_size <= 0:
            errors.append({"type": "FINAL_DOCX_ZERO_BYTE_FILE", "kind": kind, "path": actual_rel})
            continue

        first = path.read_bytes()
        first_sha = _sha256(first)
        second = path.read_bytes()
        second_sha = _sha256(second)
        if first != second or first_sha != second_sha:
            errors.append({"type": "FINAL_DOCX_READBACK_MISMATCH", "kind": kind, "path": actual_rel})

        ooxml_errors, identifier = _parse_ooxml(path)
        for item in ooxml_errors:
            errors.append({"type": item, "kind": kind, "path": actual_rel})
        binding, binding_error = _parse_binding(identifier)
        if binding_error:
            errors.append({"type": binding_error, "kind": kind, "path": actual_rel})
        expected_binding = _expected_binding(context, kind)
        if binding is not None and binding != expected_binding:
            errors.append({
                "type": "FINAL_DOCX_BINDING_MISMATCH",
                "kind": kind,
                "expected": expected_binding,
                "actual": binding,
            })

        publication = _validate_publication(
            package_root,
            row.get("publication"),
            first_sha,
            errors,
            route_e2e_required,
            kind,
        )
        artifact_receipts[kind] = {
            "relative_path": str(actual_rel),
            "size": len(first),
            "sha256": first_sha,
            "readback_sha256": second_sha,
            "ooxml_valid": not ooxml_errors,
            "binding_match": binding == expected_binding,
            "publication": publication,
        }
        observed_paths[kind] = str(path)
        observed_hashes.setdefault(first_sha, []).append(kind)

    reverse_paths: dict[str, list[str]] = {}
    for kind, path in observed_paths.items():
        reverse_paths.setdefault(path, []).append(kind)
    for path, kinds in reverse_paths.items():
        if len(kinds) > 1:
            errors.append({
                "type": "FINAL_DOCX_REQUIRED_KINDS_SHARE_FILE",
                "path": path,
                "kinds": sorted(kinds),
            })

    for sha256, kinds in observed_hashes.items():
        if len(kinds) > 1:
            errors.append({
                "type": "FINAL_DOCX_REQUIRED_KINDS_DUPLICATE_BYTES",
                "sha256": sha256,
                "kinds": sorted(kinds),
            })

    ignored_extra = sorted(set(artifacts) - set(required_kinds))
    result = "PASS" if not errors else "FAIL"
    attachment_boundary = "REQUIRES_ROUTE_E2E" if route_e2e_required else "VERIFIED_FOR_DECLARED_LOCAL_PUBLICATION"
    return {
        "schema_version": 1,
        "receipt_kind": "FINAL_DOCX_SET",
        "owner": "RESULT_DELIVERY",
        "verification_phase": FINAL_PHASE,
        "result": result,
        "binding": {field: context.get(field) for field in BINDING_FIELDS},
        "required_kinds": required_kinds,
        "combined_alternate_requested": context.get("combined_alternate_requested") is True,
        "artifacts": artifact_receipts,
        "ignored_extra_artifacts": ignored_extra,
        "route_e2e_required": sorted(set(route_e2e_required)),
        "proof_boundary": {
            "final_file_bytes_verified": result == "PASS",
            "ooxml_structure_verified": result == "PASS",
            "current_delivery_binding_verified": result == "PASS",
            "semantic_fidelity": "REQUIRES_SEMANTIC_REVIEW",
            "applied_target_observed": False,
            "deployment_or_import_observed": False,
            "runtime_behavior_observed": False,
            "platform_attachment_identity": attachment_boundary,
        },
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the actual final DOCX set after render/publish and before final user delivery."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    result = validate_final_docx_set(manifest, Path(args.package_root))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result.get("result") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
