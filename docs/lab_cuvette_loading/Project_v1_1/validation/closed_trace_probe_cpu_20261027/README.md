# Closed-trace probe CPU validation

No GPU, simulation, or provider/API request was executed. No environment was installed or modified.

- `contracts_result.json`: actual supported frozen CI contract selection, 669 passed / 13 skipped; all recorded source hashes unchanged during the run.
- `native_python_focused_junit.xml`: all 41 focused cases passed using the existing LabUtopia Python with CUDA disabled and only the existing pytest framework directory appended. Includes normal success/failure reader rejection of `control_diagnostic`, preserving task labels and H5 SHA.
- `actual_gpt05_dry_run.json`: read-only validation of the actual closed GPT05 trace: 25 commands and 110 hashed consumed files; final error-row X+35mm/2s preserved. It created no diagnostic output or physical episode.
- `focused.txt`: light CI Python, 39 passed / 2 normal-reader dependency skips.
- `full_cpu.txt`: initial unsupported unfiltered legacy-suite attempt could not collect 12 files because the small CI environment lacks h5py/cv2/trimesh. The supported CI selection above subsequently passed. This was a CPU dependency mismatch, not a simulator run or a physical failure.

The source metadata, score, public images, and original trace were read without modification. A future physical replay needs its own process-exit proof, video and independent result.
