"""Stable domain vocabulary; this module has no infrastructure dependencies."""
from dataclasses import dataclass
from typing import Tuple

TOOL_VERSION = "0.7.0"
SCHEMA_VERSION = "0.1"


@dataclass(frozen=True)
class Stage:
    """A workflow checkpoint contract exposed to orchestration and documentation."""

    name: str
    inputs: Tuple[str, ...]
    outputs: Tuple[str, ...]
    checkpoint: str


def stage_contracts() -> Tuple[Stage, ...]:
    """Return the ordered, public pipeline contract in one authoritative place."""

    return (
        Stage("environment", ("process environment", "runtime layout"), ("doctor.json",), "environment_ready"),
        Stage("inventory", ("workspace roots",), ("inventory.jsonl", "workspace_manifest.json", "change_set.json"), "inventory_recorded"),
        Stage("configure", ("CMake roots", "parameters", "compile databases"), ("build_context.json", "compile_commands.json", "configuration_questions.json"), "build_context_ready"),
        Stage("semantic_extract", ("build_context.json", "source dependencies"), ("compiler_facts.jsonl", "function_ir.jsonl", "diagnostics.json", "parse_plan.json"), "semantic_facts_ready"),
        Stage("graph", ("compiler facts", "boundary policy"), ("derived_relations.jsonl", "lock_analysis.json", "issues.json", "coverage.json"), "graph_ready"),
        Stage("alias", ("compiler facts", "call graph", "lock analysis"), ("alias_analysis.json", "field_accesses.jsonl", "lock_ownership_summaries.jsonl", "callback_targets.jsonl", "callback_states.jsonl"), "alias_and_lock_ownership_ready_or_partial"),
        Stage("dataflow", ("compiler facts", "cfg_ir.jsonl", "flow budgets"), ("value_graph.jsonl", "function_summaries.jsonl", "dataflow_plan.json"), "dataflow_ready_or_not_requested"),
        Stage("review", ("graph", "unresolved issues"), ("review_plan.json", "review_request.json"), "review_requests_ready"),
        Stage("publish", ("graph", "manifest"), ("snapshots/<id>/graph.json", "snapshots/<id>/analysis_manifest.json", "current.json"), "snapshot_published"),
        Stage("export", ("published snapshot", "viewer template"), ("*.html", "*.export_bundle.json", "*.export_validation.json"), "export_validated"),
    )
