# Formal15 completed-run acceptance

The audit explicitly selects fixed5, original random seeds8000–8007, and recovered random seeds8008/8009. Original interrupted seed8008 is preserved and excluded. Its H5 was not opened. Interruption is an unadjudicated tool termination; no physical-task-failure verdict was obtained (physical_failure_verdict=null). A physical fault has neither been confirmed nor ruled out.

`acceptance.json` and `formal_audit/audit.json` preserve all actual labels, source hashes, per-episode checks, assembly shifts, controller/terminal semantics and false native/calibration flags. `qualified_index/` uses external links to qualified original H5s. The loader reads a real batch through the existing MinimalPickDataset; no optimizer, model inference or training occurs.

The8D action is7absolute arm position targets(rad) plus1finger position target(m). Phase-dependent finger effort caps remain auxiliary physics records; this read does not verify complete8D-only replay. See the source action_scope.md.
