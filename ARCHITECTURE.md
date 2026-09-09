# SDK Code Atlas architecture

## Dependency rule

Dependencies point inward and never in the opposite direction:

```text
interfaces (CLI / future VS Code)
          |
          v
application (use-case coordination)
          |
          v
domain (versions, stage contracts, analysis vocabulary)

infrastructure (artifact store, CMake, Clang, native process) implements
technical capabilities consumed by application modules. Domain never imports it.
```

The current 0.6 architecture establishes enforceable boundaries for new work while
retaining the mature analysis modules as transitional components:

| Layer | Stable modules | Transitional modules |
|---|---|---|
| Interface | `atlas.interfaces.cli`, `scripts/sdk_atlas.py` shim | none |
| Application | `atlas.application.service` | `pipeline`, `graph`, `dataflow`, `concurrency`, `aliasing`, `review` |
| Domain | `atlas.domain.contracts` | dictionary payload shapes (schema 0.1) |
| Infrastructure | `atlas.infrastructure.store` | `build`, `configuration`, `extract`, `native`, `search` |
| Presentation | offline `viewer` adapter and `assets/viewer.html` | none |

`atlas.core` is a compatibility facade only. New code must import the owning
layer. Removing that facade requires a future schema/cache migration and is not
part of this compatibility-preserving refactor.

## Functional boundaries

Each externally observable capability has a reproducibility record under
`do_func/`. A capability owns its acceptance condition but may compose lower
layers. Tests enter through the application or stable CLI boundary; they do not
depend on a release archive layout.

## Runtime boundary

`setup.ps1` and `setup.sh` create a virtual environment below
`runtime/<platform>/venv`. Launchers use only that environment. The directory is
ignored by Git and no package is installed into the host Python. A wheelhouse can
be supplied for offline Python installation. Target compilers, SDK headers and
sysroots are read-only analysis inputs; setup never changes the host toolchain.

## Checkpoints

The executable checkpoint vocabulary lives in
`atlas.domain.contracts.stage_contracts`. The human-readable proposal is
`references/workflow-checkpoints.md`. GitHub Actions are intentionally deferred
until the owner confirms that proposal.
