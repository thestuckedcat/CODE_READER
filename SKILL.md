---
name: sdk-code-atlas
description: Analyze C/C++ SDK repositories with Clang, generate evidence-backed calls, types, object and parameter-flow views, review unresolved relationships, and export offline HTML with incremental TU caching.
---

# SDK Code Atlas

Use the bundled launcher to analyze a local repository. The package is an executable **0.2 prototype**, not a claim that all v3.1 design capabilities are implemented. Read [current update](update/001_round1_changes.md) before reporting completeness; [v0.1 capabilities](update/000_v0.1_capabilities.md) is historical. Windows/Linux x64 runtimes are selected by the launcher; analysis of Linux SDKs should run on the Linux code host with its SDK headers and toolchain context.

## Run

Linux: `bash <skill>/run.sh doctor`

Windows: `& <skill>\run.ps1 doctor`

Then invoke the same launcher with:

```text
run --repo /path/to/repo --out /path/to/analysis --interface sdk_entry --html /path/to/overview.html
```

Omit `--interface` for repository scope. Use `--direction up` for caller discovery. Multiple definitions/overloads require choosing an ID returned by `trace`; do not silently choose one. Use repeated `--root` for additional source roots and repeated `--compdb` for independently configured superbuild children. CMake-provided business source/include paths are also discovered. Use `--child-cmake-root` for an existing independent child that needs configuration; inspect its required parameters first. Do not download/build ExternalProject dependencies automatically.

The launchers never upload source or call a model. The host Agent performs configuration investigation and review through the file protocol. Existing parameters and authorization persist; ask only for genuinely unknown semantic inputs such as TOP_DIR. See [workflow](references/workflow.md) for commands, CMake failure recovery, review imports and incremental updates.

## Analysis invariants

- Follow evaluated include path order; do not ask the user to choose between same-named headers.
- Stop downward exploration at Linux/glibc declarations and unavailable implementations. When their source is inside the workspace, specify evidenced `--linux-root` / `--glibc-root` paths. Do not identify system functions merely by their names.
- Stop upward at functions with no known callers and show them as the top of the current chain. Do not turn this into a claim of a unique SDK entry point.
- Prefer evaluated CMake commands. Do not infer confirmed calls from grep. Text search only locates candidate TUs.
- Do not replace missing configuration macros, generated headers or superbuild functions with invented stubs. Write explicit parameter JSON or ask the developer; rerun after correction.
- Read `configuration_questions.json` and `cmake_relations.json` after configuration failures. Group missing values into one question. Confirmed parameters persist per CMake entry; `--require-param` can register a discovered required value. Accepted semantic substitutes need `--assumptions` matching explicit parameter values.
- For ambiguous functions/TU variants, use `interface_choices.json` and rerun with `--select-function` or `--unit`.
- Inspect `doctor.json`, run summary, coverage and issues. Failed TUs contribute no facts. Partial results are useful only when labeled.
- Treat `review_request.json` as a task for the host Agent or a subagent if available. Review source, return schema-conforming `review_result.json`, import through `review-import`. Do not edit graph/Clang outputs directly. Read [review protocol](references/review.md).
- Indirect/virtual targets and data flow remain `may` unless an implemented deterministic analysis proves more. A successful JSON validator does not prove business semantics.
- Reuse the same `--out` on the next commit. The scripts validate per-TU dependencies and cache inputs; do not delete the cache to force a global scan.
- HTML consumes only a published bundle. Re-exporting does not reparse source.

## Delivery

Return the HTML and concise counts of parsed/reused/failed TUs, unresolved targets, truncation and remaining capabilities. Include original run logs only when needed for diagnosis. Do not report CFG, complete alias analysis, kernel registration rules, or universal cross-platform portability as implemented.

For development, run `selftest` through the launcher (requires a working C/C++ compiler for the fixture CMake project). Read [artifact mapping](references/artifacts.md) to locate intermediate files. The original detailed design is in [design-v3.1.md](references/design-v3.1.md); concrete prototype deviations are governed by capabilities.md.

A generated offline example is included at `examples/fixture-overview.html`. Open it directly to inspect the UI before analyzing your own project.
