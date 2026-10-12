# Changelog

## 2026-10-12 — Focus on GPU passthrough

- Remove USB receiver and keyboard/mouse instructions, script operations,
  verification output and configuration examples.
- Keep GPU initialization, PCI placement, memory, backup and rollback workflows.

## 2026-10-12 — Initial publication

- Document the 2026-10-07 N150 / PVE 9.2 / Windows 10 hardware test and its limits.
- Separate native Stage 1, evidence-based ROM initialization and PCI placement.
- Publish the tested ROM, fixed source versions, N150 patch and a portable build script.
- Add explicit configuration operations, per-action backups and guarded rollback.
- Add fake-host workflow tests and CI source builds; exclude private connection details.
