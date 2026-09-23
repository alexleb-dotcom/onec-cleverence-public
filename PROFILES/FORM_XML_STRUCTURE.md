# FORM_XML_STRUCTURE

Activate for managed `Form.xml` (`http://v8.1c.ru/8.3/xcf/logform`).

## Review

- Treat controls, attributes, commands and per-attribute columns as distinct identity/name scopes.
- In an extension, do not mix the serialized `BaseForm` subtree with the overlay when validating IDs.
- Read the compact structural summary before reasoning about form-module handlers, DataPath, commands or elements.
- If `BaseForm`/event interception is present, prove the companion form metadata and actual base-form behavior; `callType` is a contract, not decoration.
- After XML modification, require structural validation and Configurator/form-open runtime evidence according to risk.

Do not generalize a corpus convention into a platform requirement without evidence.
