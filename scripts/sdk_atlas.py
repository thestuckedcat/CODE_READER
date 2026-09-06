#!/usr/bin/env python3
"""SDK Code Atlas: deterministic C/C++ repository analysis Skill CLI."""
import argparse,json,sys
from pathlib import Path
# Optional unpacked dependency payload selected by bootstrap.
package=Path(__file__).resolve().parent.parent
if (package/'runtime/site').is_dir():sys.path.insert(0,str(package/'runtime/site'))
from atlas.core import read,write,envelope,Store,Lock

def main():
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='cmd',required=True)
    subs.add_parser('selftest')
    d=subs.add_parser('doctor');d.add_argument('--out')
    r=subs.add_parser('run');r.add_argument('--repo',required=True);r.add_argument('--out',required=True)
    r.add_argument('--root',action='append',help='Additional complete source root (repeatable)')
    r.add_argument('--compdb',action='append',help='Evaluated compile_commands.json (repeatable)')
    r.add_argument('--child-cmake-root',action='append');r.add_argument('--require-param',action='append');r.add_argument('--assumptions');r.add_argument('--linux-root',action='append');r.add_argument('--glibc-root',action='append');r.add_argument('--select-function');r.add_argument('--unit');r.add_argument('--cmake-root');r.add_argument('--params');r.add_argument('--target');r.add_argument('--interface')
    r.add_argument('--direction',choices=['up','down','both'],default='down');r.add_argument('--clang-arg',action='append')
    r.add_argument('--max-tu',type=int,default=128);r.add_argument('--tu-timeout',type=int,default=120);r.add_argument('--configure-timeout',type=int,default=180);r.add_argument('--html')
    e=subs.add_parser('export');e.add_argument('--out',required=True);e.add_argument('--html',required=True)
    t=subs.add_parser('trace');t.add_argument('--out',required=True);t.add_argument('--function',required=True);t.add_argument('--direction',choices=['up','down'],default='down');t.add_argument('--depth',type=int,default=30);t.add_argument('--budget',type=int,default=5000)
    f=subs.add_parser('flow');f.add_argument('--out',required=True);f.add_argument('--symbol',required=True)
    a=subs.add_parser('review-import');a.add_argument('--out',required=True);a.add_argument('--result',required=True)
    v=subs.add_parser('validate');v.add_argument('--out',required=True)
    x=subs.add_parser('_extract');x.add_argument('input');x.add_argument('output')
    args=p.parse_args()
    if args.cmd=='selftest':
        import subprocess
        return subprocess.run([sys.executable,str(package/'tests/run_tests.py')]).returncode
    if args.cmd=='doctor':
        from atlas.build import doctor
        result=doctor()
        if args.out:write(Path(args.out)/'doctor.json',envelope('doctor',result))
        print(json.dumps(result,indent=2));return 0 if result['ready'] else 2
    if args.cmd=='_extract':
        from atlas.extract import extract
        d=read(args.input);write(args.output,extract(d['unit'],[Path(p) for p in d['roots']],d.get('rules')));return 0
    if args.cmd=='run':
        from atlas.pipeline import run
        if args.max_tu<1:raise ValueError('--max-tu must be positive')
        run(args);return 0
    from atlas.pipeline import load_snapshot,publish
    graph,manifest=load_snapshot(args.out)
    if args.cmd=='export':
        from atlas.viewer import export
        print(export(args.out,args.html))
    elif args.cmd=='trace':
        from atlas.graph import trace
        print(json.dumps(trace(graph,args.function,args.direction,args.depth,args.budget),indent=2,ensure_ascii=False))
    elif args.cmd=='flow':
        from atlas.graph import flow_trace
        print(json.dumps(flow_trace(graph,args.symbol),indent=2,ensure_ascii=False))
    elif args.cmd=='validate': print(json.dumps(dict(status='passed',snapshot_id=manifest['snapshot_id'],functions=len(graph['functions']))))
    elif args.cmd=='review-import':
        from atlas.review import validate_review
        import uuid
        with Lock(args.out):
            # Re-read after acquiring writer lock.
            graph,manifest=load_snapshot(args.out);s=Store(args.out)
            try:
                r,accepted,evidence,report=validate_review(graph,manifest,args.result)
                s.put('review_result.json',r,origin='agent');s.put('validation_report.json',report)
                if report['configuration_action']:
                    s.put('configuration_patch.json',r['correction_proposals']);print(json.dumps(report));return 2
                graph['agent_supplements']+=accepted;graph['call_targets']+=accepted;graph['evidence']+=evidence
                for i in graph['issues']:
                    if i['id'] in r['issue_ids']:i['review_status']=r['status'];i['status']='reviewed_candidates' if accepted else 'unresolved'
                s.put('agent_supplements.jsonl',accepted)
                manifest.setdefault('imported_review_tasks',[]).append(r['task_id'])
                manifest['parent_id']=manifest['snapshot_id'];manifest['snapshot_id']=uuid.uuid4().hex
                publish(s,graph,manifest);print(json.dumps(report))
            finally:s.close()
    return 0
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:print('ERROR: '+str(e),file=sys.stderr);sys.exit(2)
