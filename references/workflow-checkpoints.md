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
| `semantic_extract` | `build_context.json`; source dependencies | `compiler_facts.jsonl`; `function_ir.jsonl`; `diagnostics.json`; `parse_plan.json` | `semantic_facts_ready` |
| `graph` | compiler facts; boundary policy | `derived_relations.jsonl`; `lock_analysis.json`; `issues.json`; `coverage.json` | `graph_ready` |
| `alias` | compiler facts; call graph; lock analysis | `alias_analysis.json`; `field_accesses.jsonl`; `lock_ownership_summaries.jsonl`; `callback_targets.jsonl` | `alias_and_lock_ownership_ready_or_partial` |
| `dataflow` | compiler facts; `cfg_ir.jsonl`; flow budgets | `value_graph.jsonl`; `function_summaries.jsonl`; `dataflow_plan.json` | `dataflow_ready_or_not_requested` |
| `review` | graph; unresolved issues | `review_plan.json`; `review_request.json` | `review_requests_ready` |
| `publish` | graph; manifest | `snapshots/<id>/graph.json`; `snapshots/<id>/analysis_manifest.json`; `current.json` | `snapshot_published` |
| `export` | published snapshot; viewer template | `*.html`; `*.export_bundle.json`; `*.export_validation.json` | `export_validated` |

Proposed CI gates after confirmation:

1. documentation reconciliation and architecture tests on Windows and Linux;
2. basic Clang/CMake suite on both systems using repository-local runtimes;
3. native CFG suite on Linux Clang 18;
4. package manifest and offline viewer checks;
5. no release or publish job without an explicit versioned workflow dispatch.
