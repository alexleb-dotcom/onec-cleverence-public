# PROFILE — VERSION_GATED_CAPABILITY

Read `KNOWLEDGE/DATA_STATE_VERSION_CONTRACTS.md`.

## Mandatory checks

- exact target product/version/environment;
- newer/neighboring release is discovery only;
- visible/read-only status is separated from runtime-effective capability;
- feature gates/settings/predicates/migrations are traced in target source;
- absent/different capability has an explicit fallback decision.

## Completion rule

A newer-version analog cannot close target-version evidence. Missing target behavior remains `EVIDENCE_REQUIRED`.
