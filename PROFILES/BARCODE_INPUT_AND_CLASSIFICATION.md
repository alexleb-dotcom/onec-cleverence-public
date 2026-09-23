# PROFILE — BARCODE_INPUT_AND_CLASSIFICATION

Read `KNOWLEDGE/DATA_STATE_VERSION_CONTRACTS.md`.

## Mandatory checks

- raw bytes/code points including control separators;
- one normalization owner;
- classifier specificity and precedence;
- full/shortened/transport representation contract;
- GTIN/individual mark/SSCC/container domain roles;
- emulator/manual input vs physical scanner runtime matrix;
- stage-specific diagnostics.

## Completion rule

Do not repair downstream business logic while raw input, normalization or classifier precedence is unresolved.
