"""Argument parsing and text serialization for the Atlas CLI."""
import argparse
import json

from ..application import AtlasApplication


def parser():
    root = argparse.ArgumentParser(description="SDK Code Atlas: deterministic C/C++ repository analysis Skill CLI.")
    commands = root.add_subparsers(dest="cmd", required=True)
    commands.add_parser("selftest")
    commands.add_parser("workflow")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--out")
    run = commands.add_parser("run")
    run.add_argument("--repo", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--root", action="append", help="Additional complete source root (repeatable)")
    run.add_argument("--compdb", action="append", help="Evaluated compile_commands.json (repeatable)")
    for name in ("child-cmake-root", "require-param", "linux-root", "glibc-root"):
        run.add_argument("--" + name, action="append")
    for name in ("assumptions", "select-function", "unit", "cmake-root", "params", "target", "interface"):
        run.add_argument("--" + name)
    run.add_argument("--direction", choices=["up", "down", "both"], default="down")
    run.add_argument("--clang-arg", action="append")
    run.add_argument("--dataflow", choices=["off", "cfg"], default="off")
    run.add_argument("--native-extractor")
    run.add_argument("--flow-steps", type=int, default=10000)
    run.add_argument("--summary-steps", type=int, default=128)
    run.add_argument("--max-tu", type=int, default=128)
    run.add_argument("--tu-timeout", type=int, default=120)
    run.add_argument("--configure-timeout", type=int, default=180)
    run.add_argument("--html")
    export = commands.add_parser("export")
    export.add_argument("--out", required=True)
    export.add_argument("--html", required=True)
    trace = commands.add_parser("trace")
    trace.add_argument("--out", required=True)
    trace.add_argument("--function", required=True)
    trace.add_argument("--direction", choices=["up", "down"], default="down")
    trace.add_argument("--depth", type=int, default=30)
    trace.add_argument("--budget", type=int, default=5000)
    flow = commands.add_parser("flow")
    flow.add_argument("--out", required=True)
    flow.add_argument("--symbol")
    flow.add_argument("--function")
    flow.add_argument("--parameter")
    flow.add_argument("--value")
    flow.add_argument("--direction", choices=["forward", "backward"], default="forward")
    flow.add_argument("--budget", type=int, default=2000)
    locks = commands.add_parser("locks")
    locks.add_argument("--out", required=True)
    locks.add_argument("--object")
    locks.add_argument("--lock")
    review = commands.add_parser("review-import")
    review.add_argument("--out", required=True)
    review.add_argument("--result", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--out", required=True)
    internal = commands.add_parser("_extract")
    internal.add_argument("input")
    internal.add_argument("output")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    app = AtlasApplication()
    if args.cmd == "selftest":
        return app.selftest()
    if args.cmd == "workflow":
        print(json.dumps(app.workflow(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "doctor":
        result = app.doctor(args.out)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ready"] else 2
    if args.cmd == "_extract":
        from pathlib import Path
        from ..extract import extract
        from ..infrastructure.store import read, write

        request = read(args.input)
        write(args.output, extract(request["unit"], [Path(path) for path in request["roots"]], request.get("rules")))
        return 0
    if args.cmd == "run":
        if args.flow_steps < 1 or args.summary_steps < 1:
            raise ValueError("Flow budgets must be positive")
        if args.max_tu < 1:
            raise ValueError("--max-tu must be positive")
        app.run(args)
        return 0
    if args.cmd == "export":
        print(app.export(args.out, args.html))
        return 0
    if args.cmd == "trace":
        result = app.trace(args.out, args.function, args.direction, args.depth, args.budget)
    elif args.cmd == "flow":
        result = app.flow(args.out, args.function, args.symbol, args.parameter, args.value, args.direction, args.budget)
    elif args.cmd == "locks":
        result = app.locks(args.out, args.object, args.lock)
    elif args.cmd == "validate":
        result = app.validate(args.out)
    elif args.cmd == "review-import":
        result, code = app.import_review(args.out, args.result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return code
    else:
        raise ValueError("Unsupported command: " + args.cmd)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0
