#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORM_XML = ROOT / "COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/ProjectSnapshotCollector/Forms/MainForm/Ext/Form.xml"
FORM_MODULE = ROOT / "COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/ProjectSnapshotCollector/Forms/MainForm/Ext/Form/Module.bsl"
LF = {"f": "http://v8.1c.ru/8.3/xcf/logform"}


def main() -> int:
    errors: list[str] = []

    module = FORM_MODULE.read_text(encoding="utf-8-sig")
    form_root = ET.parse(FORM_XML).getroot()

    if "Документ.Прочитать(Диалог.ПолноеИмяФайла, КодировкаТекста.UTF8);" not in module:
        errors.append("collection_plan_must_be_read_as_explicit_utf8")

    if "ПользовательDesigner = ИмяПользователя();" not in module:
        errors.append("designer_user_must_default_to_current_infobase_user")

    for anchor in [
        '" /N " + ЭкранироватьАргумент(ПользовательDesigner)',
        '" /P " + ЭкранироватьАргумент(ПарольDesigner)',
        'ПарольDesigner = "";',
    ]:
        if anchor not in module:
            errors.append(f"designer_auth_contract_missing:{anchor}")

    attrs = {node.attrib.get("name") for node in form_root.findall("f:Attributes/f:Attribute", LF)}
    for required in {"ПользовательDesigner", "ПарольDesigner"}:
        if required not in attrs:
            errors.append(f"designer_auth_form_attribute_missing:{required}")

    password_field = None
    for node in form_root.findall(".//f:InputField", LF):
        data_path = node.findtext("f:DataPath", namespaces=LF)
        if data_path == "ПарольDesigner":
            password_field = node
            break
    if password_field is None:
        errors.append("designer_password_input_missing")
    elif password_field.findtext("f:PasswordMode", namespaces=LF) != "true":
        errors.append("designer_password_input_must_use_password_mode")

    manifest_match = re.search(
        r"Функция\s+СформироватьМанифестПакета\b.*?КонецФункции",
        module,
        re.IGNORECASE | re.DOTALL,
    )
    if manifest_match is None:
        errors.append("manifest_function_missing")
    elif "ПарольDesigner" in manifest_match.group(0):
        errors.append("designer_password_must_not_be_persisted_in_manifest")

    if errors:
        print("ProjectSnapshot runtime acceptance regression: FAIL")
        for error in errors:
            print(f"- {error}")
        return 2

    print("ProjectSnapshot runtime acceptance regression: PASS")
    print("- CollectionPlan file loading is explicitly UTF-8")
    print("- Designer authentication uses current user plus optional password")
    print("- Designer password field is masked and excluded from manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
