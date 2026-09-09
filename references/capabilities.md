# 0.6 current capabilities and limits

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
| Lock and shared-state analysis | Implemented for Clang-resolved common lock APIs, lexical regions, static/global accesses and conservative conflict pairs |
| Field alias and callback candidates | Implemented for address-of/pointer-copy chains, one-level fields, argument bindings, lock ownership summaries and callback-field candidates in tested fixtures |
| VS Code extension | Not implemented |

## Non-negotiable limits

The tool does not prove runtime frequency, thread reachability or interleaving, a
complete happens-before relation, condition-variable ordering, arbitrary pointer
effects, exact virtual targets, complete path feasibility, kernel registration
semantics, or a unique top-level entry. Missing configuration and parse failures
remain visible rather than being replaced with textual guesses.

For per-capability reproduction, use the [capability catalog](../do_func/README.md).
For current platform evidence, use [TEST_REPORT.md](../TEST_REPORT.md).
