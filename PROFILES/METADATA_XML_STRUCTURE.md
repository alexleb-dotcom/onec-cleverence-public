# METADATA_XML_STRUCTURE

Activate for `MetaDataObject` XML from a 1C source dump.

## Review

- Identify the actual metadata payload/type and `Properties/Name` from XML, not from path guesses alone.
- Validate UUID syntax where UUID bindings are present.
- Validate `ChildObjects` structural consistency before assuming forms, attributes, tabular sections or other children exist.
- For architectural conclusions, combine metadata structure with the object's real modules/forms and call graph; XML structure alone is not business behavior.
