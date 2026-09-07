# Engineering refactor v0.4

Date: 2026-09-08.

## Delivered

- Introduced domain, application, infrastructure and interface boundaries.
- Kept `atlas.core` and `scripts/sdk_atlas.py` as compatibility facades.
- Centralized tool version and executable workflow/checkpoint vocabulary.
- Added repository-local Windows/Linux runtime setup and platform test launchers.
- Decoupled source tests from the historical release archive layout.
- Fixed UTF-8 test reads, Windows response-file parsing, CMake trace pseudo paths,
  and Linux GCC builtin-header discovery.
- Added ten reproducible capability records under `do_func/`.
- Added document reconciliation and architecture regression tests.
- Updated current capabilities and validation report to v0.4.

## Explicitly deferred

GitHub Actions are not created until the owner confirms
`references/workflow-checkpoints.md`. Native LLVM C++ development payloads are
not silently downloaded by the base setup; current platform reports mark native
CFG tests as skipped and retain the prior verified evidence.
