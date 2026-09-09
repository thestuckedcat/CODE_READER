"""Application boundary for CLI, future VS Code, and tests."""
import subprocess
import sys
import uuid
from pathlib import Path

from ..domain.contracts import stage_contracts
from ..infrastructure.store import Lock, Store


class AtlasApplication:
    """Coordinates use cases without knowing argparse or shell conventions."""

    def __init__(self, package_root=None):
        self.package_root = Path(package_root or Path(__file__).resolve().parents[3])

    def selftest(self):
        return subprocess.run([sys.executable, str(self.package_root / "tests" / "run_tests.py")]).returncode

    def doctor(self, output=None):
        from ..build import doctor
        from ..infrastructure.store import envelope, write

        result = doctor()
        if output:
            write(Path(output) / "doctor.json", envelope("doctor", result))
        return result

    def workflow(self):
        return [
            {"stage": item.name, "inputs": list(item.inputs), "outputs": list(item.outputs), "checkpoint": item.checkpoint}
            for item in stage_contracts()
        ]

    def run(self, args):
        from ..pipeline import run

        return run(args)

    def export(self, output, html):
        from ..viewer import export

        return export(output, html)

    def trace(self, output, function, direction="down", depth=30, budget=5000):
        from ..graph import trace
        from ..pipeline import load_snapshot

        graph, _ = load_snapshot(output)
        return trace(graph, function, direction, depth, budget)

    def locks(self, output, object_name=None, lock_name=None):
        from ..concurrency import query
        from ..pipeline import load_snapshot

        graph, _ = load_snapshot(output)
        return query(graph, object_name, lock_name)

    def flow(self, output, function=None, symbol=None, parameter=None, value=None, direction="forward", budget=2000):
        from ..pipeline import load_snapshot

        graph, _ = load_snapshot(output)
        if function:
            from ..dataflow import trace

            return trace(graph, function, parameter, value, direction, budget)
        if symbol and graph.get("value_nodes"):
            from ..dataflow import trace

            owners = {node["owner"] for node in graph["value_nodes"] if node["kind"] == "parameter" and node["symbol"] == symbol}
            if len(owners) != 1:
                raise ValueError("Choose --function and --parameter for this symbol")
            return trace(graph, next(iter(owners)), symbol, direction=direction, budget=budget)
        if symbol:
            from ..graph import flow_trace

            return flow_trace(graph, symbol, budget)
        raise ValueError("Use --function for CFG flow or --symbol for legacy flow")

    def validate(self, output):
        from ..pipeline import load_snapshot

        graph, manifest = load_snapshot(output)
        return {"status": "passed", "snapshot_id": manifest["snapshot_id"], "functions": len(graph["functions"])}

    def import_review(self, output, result):
        from ..pipeline import load_snapshot, publish
        from ..review import validate_review

        with Lock(output):
            graph, manifest = load_snapshot(output)
            store = Store(output)
            try:
                review, accepted, evidence, report = validate_review(graph, manifest, result)
                store.put("review_result.json", review, origin="agent")
                store.put("validation_report.json", report)
                if report["configuration_action"]:
                    store.put("configuration_patch.json", review["correction_proposals"])
                    return report, 2
                graph["agent_supplements"] += accepted
                graph["call_targets"] += accepted
                graph["evidence"] += evidence
                for issue in graph["issues"]:
                    if issue["id"] in review["issue_ids"]:
                        issue["review_status"] = review["status"]
                        issue["status"] = "reviewed_candidates" if accepted else "unresolved"
                store.put("agent_supplements.jsonl", accepted)
                manifest.setdefault("imported_review_tasks", []).append(review["task_id"])
                manifest["parent_id"] = manifest["snapshot_id"]
                manifest["snapshot_id"] = uuid.uuid4().hex
                publish(store, graph, manifest)
                return report, 0
            finally:
                store.close()
