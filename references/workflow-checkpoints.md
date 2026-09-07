# Workflow and checkpoint proposal

Status: **awaiting owner confirmation before GitHub Actions are added**.

The CLI command `run.ps1 workflow` / `run.sh workflow` emits the same contract in
machine-readable JSON. Stage products are immutable artifacts unless explicitly
listed as a published pointer.

| Stage | Inputs | Outputs | Checkpoint |
|---|---|---|---|
| `environment` | process environment; runtime layout | `doctor.json` | `environment_ready` |
| `inventory` | workspace roots | `inventory.jsonl`; `workspace_manifest.json`; `change_set.json` | `inventory_recorded` |
| `configure` | CMake roots; parameters; compile databases | `build_context.json`; `compile_commands.json`; `configuration_questions.json` | `build_context_ready` |
| `semantic_extract` | build context; source dependencies | compiler facts; function IR; diagnostics; parse plan | `semantic_facts_ready` |
| `graph` | compiler facts; boundary policy | derived relations; issues; coverage | `graph_ready` |
| `dataflow` | compiler facts; CFG IR; budgets | value graph; summaries; dataflow plan | `dataflow_ready_or_not_requested` |
| `review` | graph; unresolved issues | review plan and per-issue requests | `review_requests_ready` |
| `publish` | graph; manifest | immutable snapshot plus atomic `current.json` | `snapshot_published` |
| `export` | published snapshot; viewer template | HTML, export bundle and validation | `export_validated` |

Proposed CI gates after confirmation:

1. documentation reconciliation and architecture tests on Windows and Linux;
2. basic Clang/CMake suite on both systems using repository-local runtimes;
3. native CFG suite on Linux Clang 18;
4. package manifest and offline viewer checks;
5. no release or publish job without an explicit versioned workflow dispatch.
