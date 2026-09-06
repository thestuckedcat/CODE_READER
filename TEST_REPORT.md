# SDK Code Atlas 0.1 validation report

Date: 2026-09-06. Runtime actually tested: Linux x86_64, bundled CPython 3.12.14, libclang 18.1.1, CMake 4.4.3. Windows x64 payload assembled and launcher paths statically checked; Windows execution not tested.

## Automated integration tests

Command: `runtime/linux-x86_64/python/bin/python3.12 tests/test_pipeline.py`

7 test groups passed using real Clang and CMake in temporary directories (including paths containing spaces):

1. Direct SDK calls, C++ overloaded functions, virtual `may` edges, struct layout, global objects and argument bindings.
2. Repeat run: parsed=0/reused=3. One implementation changed: parsed=1/reused=2. Shared header changed: parsed=2/reused=1.
3. Reverse caller paths and first-divergence IDs; ambiguous overload rejection; offline HTML export and snapshot integrity.
4. Invalid/stale review rejection, source changes after analysis rejection, candidate remains agent/may, replay rejection, independent same-baseline review imports.
5. Missing header: affected TU fails; previous definition is not silently retained in new snapshot.
6. Newly created extensionless header invalidates negative include lookup assumptions conservatively.
7. CPATH change invalidates affected parse context rather than reusing a stale AST.

Independent Agent forward test also confirmed first-run/repeat/local-update counts, interface scope limiting to two relevant fixture TUs, overload selection and missing-header failure behavior. Concrete review and cache issues found during that pass were fixed and covered by the tests above.

## Real repository exercise

Repository: https://github.com/ggml-org/llama.cpp
Reference commit: 73a43d1f69345aee8bb186ef4b3172cef892f2e5 (local checkout revision verified).

Final interface run: `llama_model_load_from_file`, max_tu=8, explicit CPU-disabled analysis configuration listed in references/workflow.md. Parsed eight TU contexts without parse errors; interface slice exported 18 functions, 38 call target edges and 14 review tasks. Coverage is partial and records pending exploration; this is not full-repository or complete-call-chain validation.

Earlier repository-level extraction exercise on eight TU contexts produced 1,177 functions and 2,450 edges before interface slicing was narrowed. These numbers describe that broader exploratory run, not the final lightweight view.

## Viewer and packaging checks

Viewer JavaScript passed Node syntax checking. Offline HTML generated with embedded data and no CDN/fetch dependency. Chromium browser execution could not be completed in this environment because the browser payload download timed out; browser interaction is not claimed verified.

Skill frontmatter/naming passed skill-creator quick_validate.py. Runtime payload hashes are in runtime-manifest.json. The ZIP retains third-party license files. Source history is carried in source-history.bundle; it does not contain third-party binary payloads.

## Remaining limits

See references/capabilities.md and references/artifacts.md for explicit implementation differences from the v3.1 target design. In particular, this version uses libclang bindings instead of a dedicated C++ LibTooling extractor; CFG/alias fixed-point and kernel lifecycle rules are not implemented. The included Windows runtime is not a substitute for Linux target headers/sysroot/SDK configuration.
