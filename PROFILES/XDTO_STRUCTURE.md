# XDTO_STRUCTURE

Activate for XDTO `Ext/Package.bin` or XDTOPackage metadata.

## Review

- Resolve package `targetNamespace`, imports and local/external type references from actual XML.
- Preserve top-level model declaration order required by the serialized package model.
- Verify unique local type/property structure and legal `name/ref` / inline-type combinations.
- `xs:anyType` in a package with foreign imports requires explicit review: prove it is intentional rather than unresolved-type degradation.
- When companion files are available, verify XDTOPackage metadata Name/Namespace and registration in `Configuration.xml`.
- Before changing an existing XDTO contract, inspect used-by/call sites and producer/consumer serialization expectations.
- Final acceptance requires configuration update/runtime serialization evidence when the package changes.
