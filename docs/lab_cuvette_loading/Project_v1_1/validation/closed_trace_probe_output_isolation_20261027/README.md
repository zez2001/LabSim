# Closed-trace output-isolation final CPU check

This supersedes the earlier `closed_trace_probe_cpu_20261027` implementation checks for the added output-path protection. No GPU, provider/API call, environment modification, source H5 read or physical replay occurred.

- `native_python_focused_result.json` / log / JUnit: 50 focused cases passed, zero skipped/failed. Used existing LabUtopia Python with CUDA disabled and only the existing pytest framework site appended. Source SHA256 unchanged. Includes real normal-reader rejection of success and failure `control_diagnostic` CPU fixtures, without relabelling or changing their H5 hashes.
- `actual_gpt05_dry_run.json`: actual closed GPT05 source, 110 consumed hashed files, all 25 commands including the final error-row X+35mm/2s. A valid new Project_v1_1 output argument was checked but no output directory was created.
- `contracts_result.json` / log / JUnit: frozen repository CI selection ran on unchanged sources; 697 passed, 13 skipped, 2 failed in the concurrently added separate `test_lab_cuvette_project_v1_1_side_detail.py` tests. Their errors were a string-content `.get` fixture assumption and a duplicate public-observation-directory fixture write. Root was informed. These are retained as failures, not advertised as a passed full CI run.

The diagnostic launcher itself changes no shared task/controller/scorer/physics/config file. Future physical replay still needs an independently closed process proof, actual video, native contacts and its unchanged independent score.
