# SDK Code Atlas 0.4 validation report

Date: 2026-09-08. Source under test includes the layered architecture and
repository-local runtime bootstrap. Runtime payloads are ignored by Git.

## Windows x64

- Host: Windows 10/11 build 26200, AMD64.
- Isolated Python: repository `runtime/windows-x86_64/venv`, CPython 3.11.4.
- Pinned dependencies: libclang 18.1.1, CMake 4.4.3, Ninja 1.13.2 and
  requirements.txt validation dependencies.
- Viewer dependency: linkedom 0.18.12 below the same platform runtime; a pinned,
  integrity-checked npm CLI was bootstrapped locally because the host exposed
  Node without npm.
- Result: `doctor_exit=0`, 22 architecture/basic behavioral tests passed,
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
- Result: `doctor_exit=0`, the same 22 architecture/basic tests passed,
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

Per-feature commands and captured minimum outputs are under `do_func/`.
