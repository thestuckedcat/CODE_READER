#!/usr/bin/env python3
"""Run the minimum reproducible test for one documented capability."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

FEATURES = {
    "environment": ["test_architecture.ArchitectureTest.test_runtime_isolation"],
    "configuration": ["test_round1.RoundOne.test_explicit_parameters_and_assumptions"],
    "semantic-extraction": ["test_pipeline.PipelineTest.test_01_calls_and_types"],
    "call-graph": ["test_pipeline.PipelineTest.test_03_paths_and_export"],
    "incremental-cache": ["test_pipeline.PipelineTest.test_02_cache_and_incremental"],
    "review-validation": ["test_pipeline.PipelineTest.test_04_invalid_review_and_valid_candidate"],
    "offline-viewer": ["test_pipeline.PipelineTest.test_03_paths_and_export"],
    "native-cfg": ["test_round2.RoundTwo.test_branch_conditions_and_early_return"],
    "scalar-dataflow": ["test_round2.RoundTwo.test_cross_function_return_and_callsite_isolation"],
    "packaging": ["test_architecture.ArchitectureTest.test_document_reconciliation"],
    "lock-analysis": ["test_pipeline.PipelineTest.test_08_lock_and_shared_state_parallelism"],
    "field-alias-analysis": ["test_pipeline.PipelineTest.test_09_field_alias_argument_and_callback_candidates"],
    "advanced-alias-concurrency": ["test_pipeline.PipelineTest.test_10_multi_alias_nested_callback_lifecycle_and_wrapper_lock"],
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature", choices=sorted(FEATURES))
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(root / "tests"), str(root / "scripts"), environment.get("PYTHONPATH")]))
    command = [sys.executable, "-m", "unittest", "-v", *FEATURES[args.feature]]
    return subprocess.run(command, cwd=root / "tests", env=environment).returncode


if __name__ == "__main__":
    raise SystemExit(main())
