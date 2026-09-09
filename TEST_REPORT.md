# SDK Code Atlas 0.8 validation report

Date: 2026-09-10. Source under test includes the layered architecture,
repository-local runtime, bounded field/alias analysis, callback state, simple lock-wrapper projection and evidence-bounded virtual dispatch. Runtime payloads are ignored by Git.

## Windows x64

- Host: Windows 10/11 build 26200, AMD64.
- Isolated Python: repository `runtime/windows-x86_64/venv`, CPython 3.11.4.
- Pinned dependencies: libclang 18.1.1, CMake 4.4.3, Ninja 1.13.2 and
  requirements.txt validation dependencies.
- Viewer dependency: linkedom 0.18.12 below the same platform runtime; a pinned,
  integrity-checked npm CLI was bootstrapped locally because the host exposed
  Node without npm.
- Result: `doctor_exit=0`, 26 architecture/basic behavioral tests passed,
  14 native CFG tests skipped, 0 failed; viewer DOM test passed; platform
  status `passed`.

Windows fixes validated in this pass include explicit UTF-8 reads, GCC-style
response files with quoted paths, ExternalProject trace pseudo-path handling and
source-test independence from the historical release ZIP.

## Linux x86_64

- Host: Ubuntu 20.04 under WSL2, Linux 6.6, glibc 2.31.
- Isolated Python: repository `runtime/linux-x86_64/venv`, managed CPython
  3.12.14 bootstrapped by pinned uv 0.12.8.
- No `apt`, `sudo`, user-site package, shell profile or global pip mutation was
  used. uv caches, managed Python, packages and Node modules remain under the
  Skill runtime directory.
- Baseline platform result: `doctor_exit=0`, 22 architecture/basic tests passed,
  14 native CFG tests skipped, 0 failed; freshly generated HTML passed the DOM
  test; platform status `passed`.

Linux validation also covers explicit GCC builtin include discovery for PyPI
libclang, whose wheel does not provide Clang resource headers.

The host C/C++ compiler and target SDK/sysroot are deliberately not installed by
the Skill: they define the code being analyzed and are treated as read-only input.

## Native CFG boundary

The repository contains the `atlas-semantic` implementation and 14 real CFG /
scalar-flow tests. The current platform runtimes do not contain LLVM/Clang C++
development headers and `clang-cpp`, so these tests correctly report `skipped`
and are not counted as passes. Their prior Linux Clang 18 execution evidence is
preserved in `update/002_round2_changes.md`.

## Other gates

- Python compileall and AST parsing: passed.
- Layer dependency/compatibility facade tests: passed.
- Skill/document/version/link/capability-folder reconciliation: passed.
- CLI workflow contract serialization: passed.
- Git diff whitespace validation: passed at final review.

## Lock-analysis feature test

- Command: `runtime/windows-x86_64/venv/Scripts/python.exe scripts/run_feature_test.py lock-analysis`.
- Result: 1 test passed in 14.985 seconds on the first recorded local run.
- Final post-brief run, including object-by-lock filtering: 1 test passed in
  10.014 seconds.
- Covered: lock/unlock events, lexical regions, common-lock serialization,
  unprotected shared write and conservative `potential_race` query.
- Not covered: runtime thread overlap, complete happens-before, condition
  variables or interprocedural lock ownership.
- Linux/WSL isolated runtime: the same feature test passed in 50.042 seconds on
  2026-09-09; this was a focused feature run, not a repeat of the full Linux suite.
- v0.5 full Windows platform suite: 37 discovered, 23 passed, 14 native CFG
  tests skipped, 0 failed; Viewer DOM lock/shared-state interaction passed.

## Field-alias and callback feature test

- Command: `runtime/windows-x86_64/venv/Scripts/python.exe scripts/run_feature_test.py field-alias-analysis`.
- Final focused Windows result after the completed brief: 1 passed in 10.285 seconds.
- Focused Linux/WSL result using the repository-local runtime: 1 passed in
  67.393 seconds; no global dependency was installed.
- Full Windows platform suite: 38 discovered, 24 passed, 14 native CFG tests
  skipped, 0 failed; Viewer field/callback/lock interaction passed.
- A first failed attempt exposed test-state leakage and pointer-symbol/object
  conflation. Both were corrected before the recorded full pass.
- This v0.6 regression scope remains limited to one-level fields, finite
  address/copy/argument propagation, lock ownership summaries and callback
  registration candidates; v0.7 extensions are covered below.

## Advanced alias/concurrency feature test

- Command: `runtime/windows-x86_64/venv/Scripts/python.exe scripts/run_feature_test.py advanced-alias-concurrency`.
- Focused Windows result after final document reconciliation: 1 passed in 9.949 seconds.
- Focused Linux/WSL result: 1 passed in 66.386 seconds using the repository-local
  runtime after dependency synchronization through `setup.sh`.
- Full Windows platform suite: 39 discovered, 25 passed, 14 native CFG tests
  skipped, 0 failed; Viewer nested-field/callback-state/wrapper-lock interaction passed.
- Covered: conservative two-object alias set, nested `pair.left` path,
  same-function callback set then clear, and acquire/release wrapper projection
  onto the caller's shared-state access.
- Scope does not include branch feasibility, arrays/pointer arithmetic, callback
  lifecycle across functions, recursive/conditional lock wrappers or runtime
  thread reachability.

Per-feature commands and captured minimum outputs are under [do_func](do_func/README.md).

## Virtual dispatch feature test

- Command: `runtime/windows-x86_64/venv/Scripts/python.exe scripts/run_feature_test.py virtual-dispatch-analysis`.
- Initial focused Windows result: 1 passed in 9.920 seconds; final pure-virtual-inclusive run passed in 9.733 seconds.
- Focused Linux/WSL result after adding the pure virtual case: 1 passed in 63.694 seconds using the repository-local runtime.
- Full Windows platform suite: 40 discovered, 26 passed, 14 native CFG tests
  skipped, 0 failed; Viewer candidate-set and type-qualified-node interaction passed.
- Covered: three known Base/Derived method candidates remain `open_world/may`,
  a final receiver produces `closed_by_final/exact`, and an explicitly
  qualified base call produces `static_exact`; a pure virtual base call with
  one known concrete implementation remains `open_world/may`.
- Scope does not infer a closed world from repository enumeration and does not
  model templates, covariant returns, using-declaration edge cases or ABI-level
  devirtualization.
