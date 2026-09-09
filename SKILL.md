---
name: sdk-code-atlas
description: Analyze C/C++ SDK repositories with evaluated CMake/Clang evidence, bounded call and scalar-flow views, incremental checkpoints, review validation, and offline HTML. Use for local SDK code understanding; not for proving arbitrary runtime behavior.
---

# SDK Code Atlas

Use the repository-local launcher. Version **0.6.0** establishes layered
application/domain/infrastructure/interface boundaries while preserving schema
0.1 compatibility. It is a prototype; do not generalize fixture evidence to
unsupported C/C++ semantics.

## Prepare and run

Create the isolated runtime once with `setup.ps1` on Windows or `setup.sh` on
Linux. This installs below `runtime/<platform>/` and does not modify host Python.
Then run `run.ps1 doctor` / `run.sh doctor` and:

```text
run --repo /path/to/repo --out /path/to/analysis --interface sdk_entry --html /path/to/overview.html
```

Prefer evaluated CMake or supplied `compile_commands.json`. Use repeated `--root`
and `--compdb` for additional repositories/builds. Do not invent missing product
configuration, generated headers, or call targets. Read
[workflow](references/workflow.md) when configuration, recovery, review import,
or incremental update is needed.

## Interpret results

- Compiler facts outrank lexical candidates and Agent proposals. Failed TUs
  contribute no facts.
- Preserve exact/may certainty, unknown targets, failed/pending coverage, and
  budget truncation.
- Stop at evidenced Linux/glibc/system boundaries and unavailable
  implementations; a topmost known caller is not necessarily a runtime entry.
- Resolve overloads or configuration variants through returned choices; never
  select silently.
- Use `--dataflow cfg` only when `doctor` reports the separate Clang 18 native
  extractor. It supports scalar reaching definitions and bounded summaries, not
  field-sensitive aliases, pointer side effects, path feasibility, or full
  exception semantics. See [round 2 limits](update/002_round2_changes.md).
- Treat review imports as current-evidence `may` supplements. Read the
  [review protocol](references/review.md) before producing one.
- Lock analysis uses Clang-resolved lock calls and lexical critical regions.
  `serialized_by_common_lock` proves a common lock for the two source sites;
  `potential_race` is a conservative warning and does not prove runtime thread
  overlap or a complete happens-before relation. Query it with `locks --out`.
- Field/alias analysis resolves bounded `&object -> pointer -> pointer-copy`
  chains, one-level field paths, argument-to-parameter objects, lock ownership
  summaries, and callback-field candidates. Query it with `aliases --out`.
  Treat casts, arrays, pointer arithmetic, multiple targets, and caller critical
  region expansion as `may/unknown`; see the numbered capability brief.

## Delivery and maintenance

Report the snapshot ID, parsed/reused/failed/pending TU counts, unresolved
boundaries, dataflow mode and limitations. HTML consumes a published snapshot
and can be re-exported without parsing again.

For implementation work, follow [architecture](ARCHITECTURE.md). Use the
[capability catalog](do_func/README.md) to reproduce one feature and
[artifact map](references/artifacts.md) to inspect files. Run `selftest` plus
`scripts/check_docs.py` after changes. The document check traverses every project
Markdown file, validates all local links, current-version documents, ordered
capability records, and the executable stage contract. The proposed stage/checkpoint contract is
in [workflow checkpoints](references/workflow-checkpoints.md) and must be owner
confirmed before CI workflows are created.

At the end of every development round, reconcile all current documents against
the executable behavior, update the affected numbered `do_func` brief and its
append-only test log, then run the documented minimum test locally. Do not carry
forward stale success counts or rewrite a skipped capability as passed.
