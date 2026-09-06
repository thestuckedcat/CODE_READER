# Bundled third-party runtime notices

This archive redistributes unmodified runtime components except relocation of wheel `.data/platlib` / executable files and Python path configuration for portable loading. Applicable upstream license files and package metadata remain beside their components.

- CPython Linux 3.12.14: Astral python-build-standalone distribution obtained using uv 0.12.10, PSF and bundled dependency licenses retained in runtime/linux-x86_64/python.
- CPython Windows 3.12.10 embeddable x64: https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip ; license retained.
- LLVM libclang 18.1.1 and Python bindings: PyPI libclang wheel; Apache-2.0 with LLVM exceptions, upstream package license retained.
- Clang builtin resource headers: llvm-project tag llvmorg-18.1.8, commit 3b5b5c1ec4a3095ab096dd780e84d7ab81f3d7ff, clang/lib/Headers. Upstream LICENSE.TXT retained. Patch-level header version differs from libclang; tested C/C++ host subset, target-specific generated headers are not promised.
- CMake 4.4.3, Ninja 1.13.2, jsonschema 4.26.0 and dependencies: versions in requirements.txt; license notices in each `.dist-info` directory and CMake share directory.

No llama.cpp repository checkout is redistributed in the runtime. The test report identifies the external reference revision. Fixture C/C++ code and SDK Code Atlas scripts were created for this prototype. Runtime file hashes are listed in runtime-manifest.json.
