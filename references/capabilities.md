# 0.4 current capabilities and limits

This file is the current summary. Historical snapshots remain under `update/`.

| Capability | Current state |
|---|---|
| Isolated Windows/Linux runtime | Implemented and platform-tested for Python dependencies, CMake, Ninja, libclang and viewer DOM dependency |
| CMake/compdb intake | Implemented for tested parent, child, target closure, generated-header and response-file scenarios |
| Clang semantic extraction | Implemented with exact/may provenance and parse-failure isolation |
| Bounded call graph | Implemented for direct, virtual/indirect boundary, overload, recursion and caller/callee fixtures |
| TU incremental cache | Implemented for source/header/environment/negative-search invalidation fixtures |
| Agent review import | Implemented with snapshot, endpoint and source-read freshness validation |
| Offline HTML | Implemented; DOM behavior tested, real browser layout and large-graph performance not yet accepted |
| Native Clang CFG | Implemented source and historically verified on Linux Clang 18; current Windows/WSL runtime does not bundle the C++ development toolchain, so those tests report skipped |
| Scalar dataflow summaries | Implemented only when native CFG is available; field/alias/path feasibility remain unsupported |
| VS Code extension | Not implemented |

## Non-negotiable limits

The tool does not prove runtime frequency, thread interleaving, arbitrary pointer
effects, exact virtual targets, complete path feasibility, kernel registration
semantics, or a unique top-level entry. Missing configuration and parse failures
remain visible rather than being replaced with textual guesses.

For per-capability reproduction, use `do_func/`. For current platform evidence,
use `TEST_REPORT.md`.
