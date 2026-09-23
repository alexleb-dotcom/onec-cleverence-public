# CFE_EXTENSION_STRUCTURE

Activate for configuration-extension XML: extension `Configuration.xml`, adopted objects/subitems, `ExtendedConfigurationObject`, `BaseForm` or extension event interception.

## Review

- Distinguish extension-owned vs adopted objects from actual XML.
- For adopted metadata objects that require base binding, prove `ExtendedConfigurationObject` and compare with the actual base configuration when available.
- Configuration root and special metadata kinds may have different binding semantics; never apply one adopted-object rule globally without type evidence.
- For borrowed forms, verify companion metadata, `BaseForm`, event `callType`, and base-form compatibility using actual base source.
- When moving/rewriting extension behavior, review interceptor closure and actual deployed base/caller state, not only the extension diff.
- Configurator extension load/update remains runtime/platform evidence; static XML validation cannot replace it.
