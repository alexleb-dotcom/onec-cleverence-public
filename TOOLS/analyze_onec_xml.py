#!/usr/bin/env python3
"""Structural analyzer for XML artifacts from 1C:Enterprise source dumps.

This tool deliberately proves only structural facts that can be derived from the
supplied bytes. It does not replace Configurator/runtime validation and does not
invent undocumented XML semantics.

Supported high-value artifacts:
- managed Form.xml;
- metadata object XML (including extension/adopted objects);
- configuration-extension root metadata;
- XDTO Ext/Package.bin (XML model) plus companion metadata/configuration when
  those files are present in the same directory/ZIP input.

The implementation is original for this skill. Its scope was informed by the
public MIT-licensed cc-1c-skills project; see KNOWLEDGE/EXTERNAL_1C_STRUCTURAL_REFERENCE.md.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import argparse
import hashlib
import io
import json
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET

MD_NS = "http://v8.1c.ru/8.3/MDClasses"
FORM_NS = "http://v8.1c.ru/8.3/xcf/logform"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
RIGHTS_NS = "http://v8.1c.ru/8.2/roles"
XS_NS = "http://www.w3.org/2001/XMLSchema"
PLATFORM_XDTO_NS = {
    "http://v8.1c.ru/8.1/data/core",
    "http://v8.1c.ru/8.1/data/enterprise",
    "http://v8.1c.ru/8.1/data/enterprise/current-config",
    "http://v8.1c.ru/8.1/data-composition-system/settings",
    "http://v8.1c.ru/8.3/data/ext",
    XS_NS,
}
TEXT_NAMES = {"package.bin"}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def ns(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") and "}" in tag else ""


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def is_candidate(name: str) -> bool:
    p = PurePosixPath(name.replace("\\", "/"))
    return p.suffix.lower() == ".xml" or p.name.lower() in TEXT_NAMES


def read_entries(path: Path):
    if path.is_dir():
        for item in sorted(path.rglob("*")):
            if item.is_file() and is_candidate(item.name):
                yield item.relative_to(path).as_posix(), item.read_bytes(), str(item)
        return
    if path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if not info.is_dir() and is_candidate(info.filename):
                    yield info.filename.replace("\\", "/"), z.read(info), f"{path}!/{info.filename}"
        return
    if path.is_file() and is_candidate(path.name):
        yield path.name, path.read_bytes(), str(path)
        return
    raise FileNotFoundError(f"Unsupported/missing XML source: {path}")


def parse_nsmap(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        for event, pair in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
            prefix, uri = pair
            result[prefix or ""] = uri
    except ET.ParseError:
        pass
    return result


def text_of(parent: ET.Element | None, child_name: str) -> str | None:
    if parent is None:
        return None
    for child in parent:
        if local(child.tag) == child_name:
            return (child.text or "").strip()
    return None


def child(parent: ET.Element | None, child_name: str) -> ET.Element | None:
    if parent is None:
        return None
    for item in parent:
        if local(item.tag) == child_name:
            return item
    return None


def metadata_payload(root: ET.Element) -> ET.Element | None:
    if local(root.tag) != "MetaDataObject":
        return None
    for item in root:
        if isinstance(item.tag, str):
            return item
    return None


def is_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value.strip())
        return True
    except Exception:
        return False


def classify(root: ET.Element, name: str) -> str:
    root_local = local(root.tag)
    root_ns = ns(root.tag)
    if root_local == "Form" and root_ns == FORM_NS:
        return "FORM"
    if root_local == "Rights" and root_ns == RIGHTS_NS:
        return "ROLE_RIGHTS"
    if root_local == "MetaDataObject" and root_ns == MD_NS:
        payload = metadata_payload(root)
        if payload is not None and local(payload.tag) == "Configuration":
            props = child(payload, "Properties")
            if text_of(props, "ConfigurationExtensionPurpose"):
                return "CFE_CONFIGURATION"
        return "METADATA"
    if root_local == "package":
        return "XDTO_PACKAGE"
    # Other known 1C XML remains useful as a classified structural artifact even
    # when this compact analyzer has no specialized semantic checks for it yet.
    if "v8.1c.ru" in root_ns or "1c.ru" in root_ns:
        return "ONEC_XML"
    return "OTHER_XML"


def finding(kind: str, severity: str, path: str, message: str, **extra):
    row = {"type": kind, "severity": severity, "path": path, "message": message}
    row.update(extra)
    return row


def relative_companion_form_metadata(name: str) -> str | None:
    p = PurePosixPath(name)
    parts = list(p.parts)
    if len(parts) >= 3 and parts[-2:] == ["Ext", "Form.xml"]:
        # .../Forms/<FormName>/Ext/Form.xml -> .../Forms/<FormName>.xml
        form_dir = PurePosixPath(*parts[:-2])
        return (form_dir.parent / f"{form_dir.name}.xml").as_posix()
    return None



def role_metadata_companion(name: str) -> tuple[str | None, str | None]:
    p = PurePosixPath(name)
    parts = list(p.parts)
    if len(parts) >= 4 and parts[-2:] == ["Ext", "Rights.xml"]:
        role_dir = PurePosixPath(*parts[:-2])
        return (role_dir.parent / f"{role_dir.name}.xml").as_posix(), role_dir.name
    return None, None


def bool_text(value: str | None) -> bool:
    return value in {"true", "false"}


def analyze_role_rights(name: str, root: ET.Element, entries: dict[str, dict], findings: list, details: dict):
    version = (root.get("version") or "").strip()
    details["version"] = version or None

    flags = {}
    for flag in ("setForNewObjects", "setForAttributesByDefault", "independentRightsOfChildObjects"):
        value = text_of(root, flag)
        flags[flag] = value
        if value is None:
            findings.append(finding("ROLE_RIGHTS_FLAG_MISSING", "HIGH", name, f"Required Rights flag {flag} is missing.", flag=flag))
        elif not bool_text(value):
            findings.append(finding("ROLE_RIGHTS_FLAG_INVALID", "HIGH", name, f"Rights flag {flag} must be true or false.", flag=flag, value=value))
    details["flags"] = flags

    def version_tuple(v):
        try:
            return tuple(int(x) for x in v.split("."))
        except Exception:
            return ()
    vt = version_tuple(version)
    details["omitted_rights_default_semantics"] = bool(vt and vt >= (2, 19))
    if version and not vt:
        findings.append(finding("ROLE_RIGHTS_VERSION_UNPARSED", "REVIEW", name, "Rights.xml version is not a dotted numeric version; version-specific omission semantics cannot be inferred.", version=version))

    object_names = set()
    object_count = 0
    rights_count = 0
    rls_count = 0
    for obj in root:
        if local(obj.tag) != "object":
            continue
        object_count += 1
        obj_name = text_of(obj, "name")
        if not obj_name:
            findings.append(finding("ROLE_RIGHTS_OBJECT_NAME_MISSING", "HIGH", name, "Role object block has no metadata object name."))
            obj_name = f"(object#{object_count})"
        elif obj_name in object_names:
            findings.append(finding("ROLE_RIGHTS_DUPLICATE_OBJECT", "HIGH", name, f"Duplicate role object block: {obj_name}.", object=obj_name))
        object_names.add(obj_name)

        seen_rights = set()
        for right in obj:
            if local(right.tag) != "right":
                continue
            rights_count += 1
            right_name = text_of(right, "name")
            value = text_of(right, "value")
            if not right_name:
                findings.append(finding("ROLE_RIGHTS_RIGHT_NAME_MISSING", "HIGH", name, f"Right without name for {obj_name}.", object=obj_name))
            elif right_name in seen_rights:
                findings.append(finding("ROLE_RIGHTS_DUPLICATE_RIGHT", "HIGH", name, f"Duplicate right {right_name} for {obj_name}.", object=obj_name, right=right_name))
            if right_name:
                seen_rights.add(right_name)
            if not bool_text(value):
                findings.append(finding("ROLE_RIGHTS_VALUE_INVALID", "HIGH", name, f"Right value must be true or false for {obj_name}/{right_name or '(unnamed)'}.", object=obj_name, right=right_name, value=value))
            restriction = child(right, "restrictionByCondition")
            if restriction is not None:
                rls_count += 1
                condition = text_of(restriction, "condition")
                if not condition:
                    findings.append(finding("ROLE_RLS_CONDITION_MISSING", "HIGH", name, f"restrictionByCondition has no condition for {obj_name}/{right_name or '(unnamed)'}.", object=obj_name, right=right_name))

    template_names = set()
    template_count = 0
    for templ in root:
        if local(templ.tag) != "restrictionTemplate":
            continue
        template_count += 1
        tname = text_of(templ, "name")
        condition = text_of(templ, "condition")
        if not tname:
            findings.append(finding("ROLE_RLS_TEMPLATE_NAME_MISSING", "HIGH", name, "restrictionTemplate has no name."))
        elif tname in template_names:
            findings.append(finding("ROLE_RLS_DUPLICATE_TEMPLATE", "HIGH", name, f"Duplicate RLS restriction template: {tname}.", template=tname))
        if tname:
            template_names.add(tname)
        if condition is None:
            findings.append(finding("ROLE_RLS_TEMPLATE_CONDITION_MISSING", "HIGH", name, f"RLS restriction template {tname or '(unnamed)'} has no condition element.", template=tname))

    details.update({"objects": object_count, "rights": rights_count, "rls_restrictions": rls_count, "rls_templates": template_count})

    md_name, role_dir_name = role_metadata_companion(name)
    if md_name:
        details["metadata_companion"] = md_name
        if md_name in entries and entries[md_name].get("root") is not None:
            md_root = entries[md_name]["root"]
            payload = metadata_payload(md_root)
            if payload is None or local(payload.tag) != "Role":
                findings.append(finding("ROLE_METADATA_COMPANION_INVALID", "HIGH", name, "Companion metadata XML is not a Role object.", companion=md_name))
            else:
                props = child(payload, "Properties")
                md_role_name = text_of(props, "Name")
                details["metadata_role_name"] = md_role_name
                if md_role_name and role_dir_name and md_role_name != role_dir_name:
                    findings.append(finding("ROLE_METADATA_NAME_MISMATCH", "HIGH", name, "Role metadata Name does not match the Rights.xml role directory.", companion=md_name, metadata_name=md_role_name, directory_name=role_dir_name))
        else:
            findings.append(finding("ROLE_METADATA_COMPANION_NOT_SUPPLIED", "REVIEW", name, "Role metadata companion is not present in supplied corpus; role identity binding cannot be fully proven.", companion=md_name))


def analyze_form(name: str, root: ET.Element, entries: dict[str, dict], findings: list, details: dict):
    """Validate the ID/name domains that are actually separate in Form.xml.

    Form controls, form attributes and form commands use separate identifier pools.
    Columns use a pool local to their owning Attribute. BaseForm is a separate
    serialized baseline subtree and is intentionally not mixed with the extension
    overlay during duplicate detection.
    """
    element_ids: dict[str, str] = {}
    element_names: dict[str, str] = {}
    elements = []

    def collect_elements(container: ET.Element | None, parent_name: str):
        if container is None:
            return
        for item in container:
            if not isinstance(item.tag, str):
                continue
            item_name = item.get("name", "")
            item_id = item.get("id", "")
            if item_name and item_id:
                elements.append({"name": item_name, "id": item_id, "tag": local(item.tag), "parent": parent_name})
                if item_id != "-1":
                    if item_id in element_ids:
                        findings.append(finding("FORM_DUPLICATE_ELEMENT_ID", "HIGH", name,
                                                f"Duplicate form-element id={item_id}: {item_name} / {element_ids[item_id]}", id=item_id))
                    else:
                        element_ids[item_id] = item_name
                    if item_name in element_names:
                        findings.append(finding("FORM_DUPLICATE_ELEMENT_NAME", "HIGH", name,
                                                f"Duplicate form-element name={item_name}.", element=item_name))
                    else:
                        element_names[item_name] = item_id
                collect_elements(child(item, "ChildItems"), item_name)

    collect_elements(child(root, "ChildItems"), "(root)")
    acb = child(root, "AutoCommandBar")
    if acb is not None:
        collect_elements(child(acb, "ChildItems"), acb.get("name") or "AutoCommandBar")

    attr_ids: dict[str, str] = {}
    attr_names: set[str] = set()
    attr_types: dict[str, list[str]] = {}
    attrs = child(root, "Attributes")
    if attrs is not None:
        for attr in attrs:
            if local(attr.tag) != "Attribute":
                continue
            aname, aid = attr.get("name", ""), attr.get("id", "")
            type_node = child(attr, "Type")
            types = []
            if type_node is not None:
                for type_item in type_node.iter():
                    if type_item is type_node or local(type_item.tag) not in {"Type", "TypeSet"}:
                        continue
                    raw_type = (type_item.text or "").strip()
                    if raw_type:
                        types.append(raw_type)
            if aname:
                attr_types[aname] = list(dict.fromkeys(types))
            if aname in attr_names:
                findings.append(finding("FORM_DUPLICATE_ATTRIBUTE_NAME", "HIGH", name, f"Duplicate form attribute name={aname}."))
            if aname:
                attr_names.add(aname)
            if aid:
                if aid in attr_ids:
                    findings.append(finding("FORM_DUPLICATE_ATTRIBUTE_ID", "HIGH", name,
                                            f"Duplicate form attribute id={aid}: {aname} / {attr_ids[aid]}", id=aid))
                else:
                    attr_ids[aid] = aname
            columns = child(attr, "Columns")
            col_ids: dict[str, str] = {}
            col_names: set[str] = set()
            if columns is not None:
                for col in columns:
                    if local(col.tag) != "Column":
                        continue
                    cname, cid = col.get("name", ""), col.get("id", "")
                    if cid:
                        if cid in col_ids:
                            findings.append(finding("FORM_DUPLICATE_COLUMN_ID", "HIGH", name,
                                                    f"Duplicate column id={cid} inside attribute {aname}.", attribute=aname, id=cid))
                        else:
                            col_ids[cid] = cname
                    if cname:
                        if cname in col_names:
                            findings.append(finding("FORM_DUPLICATE_COLUMN_NAME", "HIGH", name,
                                                    f"Duplicate column name={cname} inside attribute {aname}.", attribute=aname))
                        col_names.add(cname)

    cmd_ids: dict[str, str] = {}
    cmd_names: set[str] = set()
    commands = child(root, "Commands")
    if commands is not None:
        for cmd in commands:
            if local(cmd.tag) != "Command":
                continue
            cname, cid = cmd.get("name", ""), cmd.get("id", "")
            if cname in cmd_names:
                findings.append(finding("FORM_DUPLICATE_COMMAND_NAME", "HIGH", name, f"Duplicate form command name={cname}."))
            if cname:
                cmd_names.add(cname)
            if cid:
                if cid in cmd_ids:
                    findings.append(finding("FORM_DUPLICATE_COMMAND_ID", "HIGH", name,
                                            f"Duplicate form command id={cid}: {cname} / {cmd_ids[cid]}", id=cid))
                else:
                    cmd_ids[cid] = cname

    param_names: set[str] = set()
    params = child(root, "Parameters")
    if params is not None:
        for param in params:
            if local(param.tag) != "Parameter":
                continue
            pname = param.get("name", "")
            if pname and pname in param_names:
                findings.append(finding("FORM_DUPLICATE_PARAMETER_NAME", "HIGH", name, f"Duplicate form parameter name={pname}."))
            if pname:
                param_names.add(pname)

    events = []
    for elem in root.iter():
        if local(elem.tag) == "Event":
            events.append({"name": elem.get("name"), "callType": elem.get("callType"), "handler": (elem.text or "").strip()})
    base_form = next((e for e in root if local(e.tag) == "BaseForm"), None)

    # DataPath is a runtime data-shape contract. Keep the structural analyzer factual:
    # summarize roots/types and ConstantsSet nested bindings, but do not guess whether
    # a provider-backed member exists when the producer/composition is outside Form.xml.
    base_attr_names: set[str] = set()
    if base_form is not None:
        base_attrs = child(base_form, "Attributes")
        if base_attrs is not None:
            for attr in base_attrs:
                if local(attr.tag) == "Attribute" and attr.get("name"):
                    base_attr_names.add(attr.get("name"))

    data_path_tags = {"DataPath", "TitleDataPath", "FooterDataPath", "HeaderDataPath", "RowPictureDataPath"}
    data_paths = []
    def collect_data_paths(node: ET.Element, owner: str = "(root)"):
        for item in node:
            if item is base_form:
                continue
            if not isinstance(item.tag, str):
                continue
            item_owner = item.get("name") or owner
            if local(item.tag) in data_path_tags:
                raw = (item.text or "").strip()
                if raw:
                    data_paths.append({"kind": local(item.tag), "path": raw, "root": raw.split(".", 1)[0], "owner": owner})
            collect_data_paths(item, item_owner)
    collect_data_paths(root)

    constants_set_attributes = sorted(name_ for name_, types in attr_types.items() if "cfg:ConstantsSet" in types)
    constants_set_bindings = [row for row in data_paths if row["root"] in constants_set_attributes and "." in row["path"]]

    companion = relative_companion_form_metadata(name)
    details.update({
        "element_count": len(elements), "element_id_count": len(element_ids),
        "attribute_count": len(attr_names), "attributes": [{"name": n, "types": attr_types.get(n, [])} for n in sorted(attr_names)],
        "base_attribute_names": sorted(base_attr_names), "command_count": len(cmd_names),
        "data_path_count": len(data_paths), "data_paths": data_paths[:100],
        "constants_set_attributes": constants_set_attributes, "constants_set_bindings": constants_set_bindings[:100],
        "event_count": len(events), "events": events[:50], "base_form": base_form is not None,
        "companion_metadata": companion,
    })
    if companion and companion not in entries:
        findings.append(finding("FORM_COMPANION_METADATA_NOT_SUPPLIED", "REVIEW", name,
                                "Companion form metadata XML is not present in the supplied corpus; extension/base ownership cannot be fully proven.", companion=companion))
    if base_form is not None:
        intercepted = [e for e in events if e.get("callType")]
        if intercepted:
            details["intercepted_events"] = intercepted
        no_call_type = [e for e in events if e.get("handler") and not e.get("callType")]
        if no_call_type:
            findings.append(finding("CFE_FORM_EVENT_CALLTYPE_REVIEW", "REVIEW", name,
                                    "BaseForm is present and some event handlers have no callType; classify each as inherited interception vs extension-owned event using actual base-form evidence.", events=no_call_type[:20]))


def analyze_metadata(name: str, root: ET.Element, findings: list, details: dict):
    payload = metadata_payload(root)
    if payload is None:
        findings.append(finding("METADATA_PAYLOAD_MISSING", "HIGH", name, "MetaDataObject has no metadata payload element."))
        return
    obj_type = local(payload.tag)
    props = child(payload, "Properties")
    obj_name = text_of(props, "Name")
    belonging = text_of(props, "ObjectBelonging")
    extended = text_of(props, "ExtendedConfigurationObject")
    details.update({"metadata_type": obj_type, "name": obj_name, "object_belonging": belonging, "extended_configuration_object": extended, "uuid": payload.get("uuid")})
    if not obj_name and obj_type != "Configuration":
        findings.append(finding("METADATA_NAME_MISSING", "HIGH", name, f"{obj_type} metadata has no Properties/Name."))
    if payload.get("uuid") and not is_uuid(payload.get("uuid")):
        findings.append(finding("METADATA_UUID_INVALID", "HIGH", name, f"{obj_type} uuid is not a valid UUID.", value=payload.get("uuid")))
    # Extension root and Language are special: stock/typical extension dumps may mark
    # them Adopted without an ExtendedConfigurationObject. Other adopted metadata
    # objects require the base-object UUID binding.
    if belonging == "Adopted" and obj_type not in {"Configuration", "Language"}:
        if not extended:
            findings.append(finding("CFE_ADOPTED_OBJECT_WITHOUT_BASE_UUID", "HIGH", name,
                                    "Adopted metadata object has no ExtendedConfigurationObject; binding to the extended configuration is unproven."))
        elif not is_uuid(extended):
            findings.append(finding("CFE_EXTENDED_OBJECT_UUID_INVALID", "HIGH", name,
                                    "ExtendedConfigurationObject is not a valid UUID.", value=extended))
    child_objects = child(payload, "ChildObjects")
    if child_objects is not None:
        seen: set[tuple[str, str]] = set()
        duplicates = []
        for item in child_objects:
            key = (local(item.tag), (item.text or "").strip())
            if key[1] and key in seen:
                duplicates.append({"type": key[0], "name": key[1]})
            seen.add(key)
        if duplicates:
            findings.append(finding("METADATA_DUPLICATE_CHILD_OBJECT", "HIGH", name,
                                    "ChildObjects contains duplicate entries of the same metadata type/name.", duplicates=duplicates[:20]))


def analyze_cfe_configuration(name: str, root: ET.Element, findings: list, details: dict):
    analyze_metadata(name, root, findings, details)
    payload = metadata_payload(root)
    props = child(payload, "Properties") if payload is not None else None
    details["extension_purpose"] = text_of(props, "ConfigurationExtensionPurpose")
    details["name_prefix"] = text_of(props, "NamePrefix")
    details["extension_compatibility_mode"] = text_of(props, "ConfigurationExtensionCompatibilityMode")


def resolve_xdto_ref(raw: str, element: ET.Element, nsmap: dict[str, str], target_ns: str | None):
    if not raw:
        return None, None
    if raw.startswith("{") and "}" in raw:
        close = raw.find("}")
        return raw[1:close], raw[close + 1:]
    if ":" in raw:
        prefix, loc = raw.split(":", 1)
        return nsmap.get(prefix), loc
    return None, raw


def xdto_context_paths(name: str):
    p = PurePosixPath(name)
    parts = list(p.parts)
    if len(parts) >= 4 and parts[-2:] == ["Ext", "Package.bin"] and parts[-4] == "XDTOPackages":
        pkg_name = parts[-3]
        root = PurePosixPath(*parts[:-4]) if len(parts) > 4 else PurePosixPath("")
        md = (root / "XDTOPackages" / f"{pkg_name}.xml").as_posix()
        cfg = (root / "Configuration.xml").as_posix()
        return pkg_name, md.lstrip("./"), cfg.lstrip("./")
    return None, None, None


def analyze_xdto(name: str, data: bytes, root: ET.Element, nsmap: dict[str, str], entries: dict[str, dict], findings: list, details: dict):
    target_ns = root.get("targetNamespace")
    details["target_namespace"] = target_ns
    if not target_ns:
        findings.append(finding("XDTO_TARGET_NAMESPACE_MISSING", "HIGH", name, "XDTO <package> has no targetNamespace."))

    top = [local(x.tag) for x in root if isinstance(x.tag, str)]
    details["top_level_sequence"] = top
    order = ["import", "property", "valueType", "objectType"]
    last = -1
    for item in top:
        if item not in order:
            continue
        rank = order.index(item)
        if rank < last:
            findings.append(finding("XDTO_TOP_LEVEL_ORDER_INVALID", "HIGH", name,
                                    "XDTO top-level order must remain import -> property -> valueType -> objectType.", sequence=top))
            break
        last = rank

    imports = [x.get("namespace") for x in root if local(x.tag) == "import" and x.get("namespace")]
    local_types: dict[str, str] = {}
    globals_: set[str] = set()
    for item in root:
        ln = local(item.tag)
        nm = item.get("name")
        if ln in {"objectType", "valueType"} and nm:
            if nm in local_types:
                findings.append(finding("XDTO_DUPLICATE_TYPE", "HIGH", name, f"Duplicate XDTO type name: {nm}", type_name=nm))
            else:
                local_types[nm] = ln
        elif ln == "property" and nm:
            globals_.add(nm)
    details.update({"imports": imports, "type_count": len(local_types), "global_property_count": len(globals_)})

    any_type_nodes = []
    ref_attrs = ("type", "base", "ref", "itemType")
    for elem in root.iter():
        if not isinstance(elem.tag, str):
            continue
        for attr in ref_attrs:
            raw = elem.get(attr)
            if not raw:
                continue
            ref_ns, ref_name = resolve_xdto_ref(raw, elem, nsmap, target_ns)
            if ref_ns in {XS_NS, XSI_NS}:
                if ref_name == "anyType":
                    any_type_nodes.append({"element": local(elem.tag), "name": elem.get("name") or elem.get("ref"), "reference": raw})
                continue
            if ref_ns == target_ns:
                if attr == "ref":
                    if ref_name not in globals_:
                        findings.append(finding("XDTO_LOCAL_PROPERTY_REF_UNRESOLVED", "HIGH", name, f"XDTO ref does not resolve to a global property: {raw}", reference=raw))
                elif ref_name not in local_types:
                    findings.append(finding("XDTO_LOCAL_TYPE_REF_UNRESOLVED", "HIGH", name, f"XDTO type reference does not resolve locally: {raw}", reference=raw))
            elif ref_ns:
                if ref_ns not in imports and ref_ns not in PLATFORM_XDTO_NS:
                    findings.append(finding("XDTO_IMPORT_MISSING_FOR_REFERENCE", "HIGH", name, f"Reference {raw} uses namespace not declared by <import>.", namespace=ref_ns))
        members = (elem.get("memberTypes") or "").split()
        for raw in members:
            ref_ns, ref_name = resolve_xdto_ref(raw, elem, nsmap, target_ns)
            if ref_ns and ref_ns not in {target_ns, XS_NS, XSI_NS} and ref_ns not in imports and ref_ns not in PLATFORM_XDTO_NS:
                findings.append(finding("XDTO_IMPORT_MISSING_FOR_REFERENCE", "HIGH", name, f"memberTypes reference {raw} uses namespace not declared by <import>.", namespace=ref_ns))

    for type_el in root.iter():
        if local(type_el.tag) not in {"objectType", "typeDef"}:
            continue
        prop_names = set()
        for item in type_el:
            if local(item.tag) != "property":
                continue
            pname = item.get("name")
            if pname and pname in prop_names:
                findings.append(finding("XDTO_DUPLICATE_PROPERTY", "HIGH", name,
                                        f"Duplicate property {pname} inside XDTO type {type_el.get('name') or '(anonymous)'}.", property=pname))
            if pname:
                prop_names.add(pname)
            if item.get("name") is not None and item.get("ref") is not None:
                findings.append(finding("XDTO_PROPERTY_NAME_AND_REF", "HIGH", name, f"Property {pname or item.get('ref')} has both name and ref."))
            inline = next((c for c in item if local(c.tag) == "typeDef"), None)
            if inline is not None and item.get("type") is not None:
                findings.append(finding("XDTO_PROPERTY_TYPE_AND_INLINE_TYPE", "HIGH", name,
                                        f"Property {pname or item.get('ref')} has both type and inline typeDef."))

    if any_type_nodes and imports:
        findings.append(finding("XDTO_ANYTYPE_WITH_IMPORTS_REVIEW", "REVIEW", name,
                                "xs:anyType is present while external namespaces are imported. Prove that anyType is intentional and not a silently degraded unresolved foreign type.", nodes=any_type_nodes[:20]))

    pkg_name, md_name, cfg_name = xdto_context_paths(name)
    details.update({"package_name": pkg_name, "metadata_companion": md_name, "configuration_companion": cfg_name})
    if pkg_name and md_name:
        if md_name in entries and entries[md_name].get("root") is not None:
            mdroot = entries[md_name]["root"]
            payload = metadata_payload(mdroot)
            props = child(payload, "Properties") if payload is not None else None
            md_pkg_name = text_of(props, "Name")
            md_ns = text_of(props, "Namespace")
            if md_pkg_name != pkg_name:
                findings.append(finding("XDTO_METADATA_NAME_MISMATCH", "HIGH", name,
                                        "XDTO metadata Name does not match package directory name.", metadata_name=md_pkg_name, package_name=pkg_name))
            if target_ns and md_ns and md_ns != target_ns:
                findings.append(finding("XDTO_METADATA_NAMESPACE_MISMATCH", "HIGH", name,
                                        "XDTO metadata Namespace does not match Package.bin targetNamespace.", metadata_namespace=md_ns, target_namespace=target_ns))
        else:
            findings.append(finding("XDTO_METADATA_COMPANION_NOT_SUPPLIED", "REVIEW", name,
                                    "XDTO metadata companion is not present in supplied corpus; metadata/package binding cannot be fully proven.", companion=md_name))
        if cfg_name in entries and entries[cfg_name].get("root") is not None:
            cfgroot = entries[cfg_name]["root"]
            payload = metadata_payload(cfgroot)
            child_objects = child(payload, "ChildObjects") if payload is not None else None
            registered = bool(child_objects is not None and any(local(x.tag) == "XDTOPackage" and (x.text or "").strip() == pkg_name for x in child_objects))
            if not registered:
                findings.append(finding("XDTO_NOT_REGISTERED_IN_CONFIGURATION", "HIGH", name,
                                        "XDTO package is absent from Configuration/ChildObjects in the supplied configuration.", package_name=pkg_name))
        elif cfg_name:
            findings.append(finding("XDTO_CONFIGURATION_NOT_SUPPLIED", "REVIEW", name,
                                    "Configuration.xml is not present in supplied corpus; XDTO registration cannot be proven.", companion=cfg_name))


def analyze(source: Path | str):
    source = Path(source)
    raw_entries: dict[str, dict] = {}
    findings: list[dict] = []
    artifacts = []

    for name, data, origin in read_entries(source):
        record = {"data": data, "origin": origin, "root": None, "nsmap": {}, "parse_error": None}
        raw_entries[name] = record
        try:
            record["nsmap"] = parse_nsmap(data)
            record["root"] = ET.fromstring(data)
        except ET.ParseError as exc:
            record["parse_error"] = str(exc)
            findings.append(finding("XML_PARSE_ERROR", "HIGH", name, f"XML parse error: {exc}"))

    # Namespace uniqueness across XDTO packages in the same supplied corpus.
    xdto_ns: dict[str, list[str]] = {}

    for name in sorted(raw_entries):
        rec = raw_entries[name]
        root = rec["root"]
        if root is None:
            artifacts.append({"path": name, "origin": rec["origin"], "kind": "INVALID_XML", "sha256": hashlib.sha256(rec["data"]).hexdigest(), "details": {}})
            continue
        kind = classify(root, name)
        details: dict = {"root": local(root.tag), "namespace": ns(root.tag)}
        if kind == "FORM":
            analyze_form(name, root, raw_entries, findings, details)
        elif kind == "ROLE_RIGHTS":
            analyze_role_rights(name, root, raw_entries, findings, details)
        elif kind == "METADATA":
            analyze_metadata(name, root, findings, details)
        elif kind == "CFE_CONFIGURATION":
            analyze_cfe_configuration(name, root, findings, details)
        elif kind == "XDTO_PACKAGE":
            analyze_xdto(name, rec["data"], root, rec["nsmap"], raw_entries, findings, details)
            tns = root.get("targetNamespace")
            if tns:
                xdto_ns.setdefault(tns, []).append(name)
        artifacts.append({"path": name, "origin": rec["origin"], "kind": kind, "sha256": hashlib.sha256(rec["data"]).hexdigest(), "details": details})

    for namespace, paths in xdto_ns.items():
        if len(paths) > 1:
            for path in paths:
                findings.append(finding("XDTO_TARGET_NAMESPACE_DUPLICATE", "HIGH", path,
                                        "Multiple XDTO packages in the supplied configuration use the same targetNamespace.", namespace=namespace, packages=paths))

    summary = {"HIGH": 0, "REVIEW": 0, "INFO": 0}
    for row in findings:
        summary[row["severity"]] = summary.get(row["severity"], 0) + 1
    kinds = {}
    for art in artifacts:
        kinds[art["kind"]] = kinds.get(art["kind"], 0) + 1
    return {
        "result": "FAIL" if summary.get("HIGH", 0) else "PASS",
        "source": str(source),
        "files": len(artifacts),
        "artifact_kinds": kinds,
        "summary": summary,
        "findings": findings,
        "artifacts": artifacts,
        "scope_note": "Structural evidence only. Configurator/platform/runtime and semantic project validation remain separate gates.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    args = ap.parse_args()
    result = analyze(args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2 if result["result"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
