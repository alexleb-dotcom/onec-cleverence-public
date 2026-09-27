# ONEC_XML_STRUCTURE

Activate when changed/supplied artifacts include 1C source-dump XML or XDTO `Package.bin`.

## Contract

- Classify the actual artifact before drawing conclusions from XML.
- Parse the exact final bytes; malformed XML is blocking.
- Use structural summary/validation instead of manually inferring large XML shape.
- A machine structural PASS proves only covered XML invariants, not semantic correctness or Configurator/runtime acceptance.
- If the local analyzer does not cover the artifact type, use the actual source plus a maintained structural reference or Configurator evidence; do not invent XML grammar.

## Evidence

Run `TOOLS/analyze_onec_xml.py` on the smallest directory/ZIP that preserves relevant companion files.
