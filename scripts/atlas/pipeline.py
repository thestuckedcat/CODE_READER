import json, os, re, subprocess, sys, uuid
from pathlib import Path
from .core import Store,Lock,read,write,payload,envelope,digest,filehash,VERSION
from .build import doctor,inventory,configure
from .graph import merge,resolve
from .review import requests

def code_hash():
    return digest([(p.name,filehash(p)) for p in [Path(__file__).parent/'extract.py',Path(__file__).parent/'build.py',Path(__file__).parent/'boundaries.py']])
def revision(root):
    try:return subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],stderr=subprocess.DEVNULL,text=True).strip()
    except (OSError,subprocess.CalledProcessError):return None

def dependencies_valid(d):return all(filehash(p)==h for p,h in d.items())
def search_stamp(unit,roots,rows,exclude):
    # Conservative negative lookup dependency: all filenames in roots/include search trees.
    argv=unit['arguments'];dirs=set(str(r) for r in roots)
    for name in ('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH'):
        dirs.update(p for p in os.environ.get(name,'').split(os.pathsep) if p)
    for i,a in enumerate(argv):
        if a in ('-I','-isystem','-iquote','-idirafter','--sysroot','-isysroot','-resource-dir') and i+1<len(argv):dirs.add(argv[i+1])
        else:
            for prefix in ('-isystem','-iquote','-idirafter','--sysroot=','-isysroot','-resource-dir=','-I'):
                if a.startswith(prefix) and len(a)>len(prefix):dirs.add(a[len(prefix):]);break
    if os.name!='nt':dirs.update(('/usr/include','/usr/local/include'))
    paths=set()
    for d in dirs:
        p=Path(d);p=(Path(unit['directory'])/p).resolve() if not p.is_absolute() else p.resolve()
        paths.add(str(p))
        if p.exists():
            for directory,subdirs,names in os.walk(p):
                subdirs[:]=[n for n in subdirs if n not in ('.git','__pycache__','.venv','node_modules') and not (Path(directory)/n).resolve().is_relative_to(exclude)]
                # Analysis output is excluded by caller; normally kept outside roots.
                paths.update(str(Path(directory)/n) for n in names if not n.endswith('.pyc'))
    return digest(sorted(paths))

def run(args):
    root=Path(args.repo).resolve()
    if not root.is_dir():raise ValueError('Repository directory does not exist')
    args.repo=root
    roots=list(dict.fromkeys([root]+[Path(p).resolve() for p in (args.root or [])]))
    with Lock(args.out):
        store=Store(args.out)
        try:return analyze(args,store,roots)
        except Exception as e:
            store.put('run_summary.json',dict(status='blocked',reason=str(e),run_id=store.run_id))
            raise
        finally:store.close()

def analyze(args,store,roots):
    request={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items() if k!='handler'}
    store.put('request.json',request)
    env=doctor();store.put('doctor.json',env)
    if not env['ready']:raise RuntimeError('libclang unavailable. Run scripts/bootstrap.py first. '+env['checks']['libclang'])
    rows=inventory(roots,store.root);old=store.meta('inventory',{})
    now={r['path']:r['hash'] for r in rows}
    changed=[p for p in sorted(set(old)|set(now)) if old.get(p)!=now.get(p)]
    store.put('inventory.jsonl',rows)
    store.put('change_set.json',dict(initial=not bool(old),changed=changed,workspace_revisions={str(r):revision(r) for r in roots}))
    store.put('workspace_manifest.json',dict(roots=[str(r) for r in roots],revisions={str(r):revision(r) for r in roots},source_manifest_hash=digest(now)))
    units=configure(args,store,rows)
    from .boundaries import policy,classify
    from .search import CandidateIndex,include_dirs
    rules=policy(args)
    units=[u for u in units if not classify(u['file'],roots,rules)]
    if args.target:
        targets=store.meta('current_build_context',{}).get('targets',[])
        by_id={t['id']:t for t in targets};names={args.target};todo=[t for t in targets if t['name']==args.target];visited=set()
        while todo:
            target=todo.pop()
            if target['id'] in visited:continue
            visited.add(target['id']);names.add(target['name'])
            todo.extend(by_id[d['id']] for d in target.get('dependencies',[]) if d['id'] in by_id)
        requested=[u for u in units if names&set(u.get('target_names',[]))]
        if not requested:raise ValueError('No exact CMake target matched '+args.target)
        units=requested
    if getattr(args,'unit',None):
        units=[u for u in units if u['id']==args.unit]
        if not units:raise ValueError('Unknown TU variant ID')
    # CMake-provided business source/include paths are explicit workspace evidence.
    for u in units:
        quote,normal,system=include_dirs(u)
        for extra in [Path(u['file']).parent]+quote+normal+system:
            extra=extra.resolve()
            if not extra.is_dir() or classify(extra,roots,rules):continue
            if any(extra.is_relative_to(Path(p)) for p in ('/usr','/lib','/lib64')):continue
            if 'clang-resource' in extra.parts:continue
            sysroots=[]
            for i,flag in enumerate(u['arguments']):
                if flag.startswith('--sysroot='):sysroots.append(Path(flag.split('=',1)[1]).resolve())
                elif flag in ('--sysroot','-isysroot') and i+1<len(u['arguments']):sysroots.append(Path(u['arguments'][i+1]).resolve())
            if any(extra.is_relative_to(p) for p in sysroots):continue
            if not any(extra.is_relative_to(r) for r in roots):roots.append(extra)
    rows=inventory(roots,store.root)
    now={r['path']:r['hash'] for r in rows};changed=[p for p in sorted(set(old)|set(now)) if old.get(p)!=now.get(p)]
    store.put('inventory.jsonl',rows)
    store.put('workspace_manifest.json',dict(roots=[str(r) for r in roots],revisions={str(r):revision(r) for r in roots},source_manifest_hash=digest(now)))
    store.put('change_set.json',dict(initial=not bool(old),changed=changed,workspace_revisions={str(r):revision(r) for r in roots}))
    all_units=units[:];search=CandidateIndex(store,units,roots,rules)
    seed_candidates=search.definition_candidates(args.interface) if args.interface else units[:]
    pending=seed_candidates[:] if args.interface else units[:]
    if not pending:raise ValueError('Interface implementation not found in candidate source/header index')
    results=[];processed=set();parsed=0;reused=0;failed=[];plan=[]
    while pending and len(processed)<args.max_tu:
        u=pending.pop(0)
        if u['id'] in processed:continue
        processed.add(u['id']);stamp=search_stamp(u,roots,rows,store.root)
        parse_inputs=dict(unit=u['id'],arguments=u['arguments'],parser=env['checks'].get('libclang_hash'),code=code_hash(),search=stamp,rules=rules,roots=[str(r) for r in roots])
        semantic_env={k:os.environ.get(k) for k in ('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH','SDKROOT','MACOSX_DEPLOYMENT_TARGET','CCC_OVERRIDE_OPTIONS')}
        parse_inputs['environment']=semantic_env
        key=digest(parse_inputs)
        previous=store.meta('tu_latest:'+u['id'])
        reasons=[]
        if not previous:reasons.append('first_seen_TU_or_command_variant')
        else:
            reasons.extend('changed_'+k for k in parse_inputs if previous.get('inputs',{}).get(k)!=parse_inputs[k])
            reasons.extend('dependency_changed:'+p for p,h in previous.get('dependencies',{}).items() if filehash(p)!=h)
        cached=store.cache_get(key)
        if cached and dependencies_valid(cached['dependencies']):
            try:
                result={k:store.get(cached[k]) for k in ('facts','ir','diagnostics')};result['dependencies']=cached['dependencies'];result['status']='succeeded'
                reused+=1
                for k in ('facts','ir','diagnostics'):store.entries.append(cached[k])
                plan.append(dict(unit=u['id'],file=u['file'],action='reuse'))
            except (OSError,ValueError,KeyError):cached=None
        else:cached=None
        if not cached:
            print('Parsing '+u['file'],flush=True)
            job=store.run/'jobs'/u['id'];job.mkdir(parents=True,exist_ok=True)
            write(job/'input.json',dict(unit=u,roots=[str(r) for r in roots],rules=rules))
            try:
                proc=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'sdk_atlas.py'),'_extract',str(job/'input.json'),str(job/'output.json')],capture_output=True,text=True,errors='replace',timeout=args.tu_timeout)
                (job/'stderr.log').write_text(proc.stderr,encoding='utf-8')
                if proc.returncode:raise RuntimeError(proc.stderr or 'Native parser exited '+str(proc.returncode))
                result=read(job/'output.json')
            except (subprocess.TimeoutExpired,RuntimeError) as e:result=dict(facts=[],ir=[],diagnostics=[dict(severity=4,message=str(e))],dependencies={},status='failed')
            facts=store.put('facts.jsonl',result['facts'],u['id'],'clang_extractor',key)
            ir=store.put('function_ir.jsonl',result['ir'],u['id'],'clang_extractor',key)
            diagnostics=store.put('diagnostics.json',result['diagnostics'],u['id'],'clang_extractor',key)
            store.put('dependencies.json',dict(files=result['dependencies'],negative_search_stamp=stamp),u['id'])
            receipt=dict(facts=facts,ir=ir,diagnostics=diagnostics,dependencies=result['dependencies'],status=result['status'])
            store.put('receipt.json',receipt,u['id'])
            if result['status']=='succeeded':
                store.cache_put(key,receipt)
                store.setmeta('tu_latest:'+u['id'],dict(inputs=parse_inputs,dependencies=result['dependencies']))
            parsed+=1;plan.append(dict(unit=u['id'],file=u['file'],action='parse',reasons=reasons or ['cache_missing_or_corrupt']))
        if result['status']=='failed':failed.append(dict(file=u['file'],diagnostics=result['diagnostics']))
        results.append(result)
        if args.interface and not pending:
            g=merge(results)
            seeds={f['id'] for f in g['functions'] if f['name']==args.interface and (not getattr(args,'select_function',None) or f['id']==args.select_function)}
            if not seeds:
                pending=[v for v in search.candidates([args.interface],True) if v['id'] not in processed][:1]
                continue
            if len(seeds)>1:
                choices=[dict(id=f['id'],name=f['display_name'],tu_ids=f['tu_ids'],evidence_ids=f['evidence_ids']) for f in g['functions'] if f['id'] in seeds]
                store.put('interface_choices.json',choices)
                raise ValueError('Choose --select-function ID or --unit TU variant from '+str(choices))
            reachable=set(seeds)
            while True:
                before=len(reachable)
                for edge in g['call_targets']:
                    if args.direction in ('down','both') and edge['source'] in reachable:reachable.add(edge['target'])
                    if args.direction in ('up','both') and edge['target'] in reachable:reachable.add(edge['source'])
                if len(reachable)==before:break
            required=[]
            if args.direction in ('down','both'):
                for call in g['callsites']:
                    if call['owner'] not in reachable or call.get('boundary_kind') or not call['target_base']:continue
                    if any(e['callsite']==call['id'] for e in g['call_targets']):continue
                    required.extend(search.candidates([call['callee']],True))
            if args.direction in ('up','both'):
                required.extend(search.candidates({f['name'] for f in g['functions'] if f['id'] in reachable}))
            pending=list({v['id']:v for v in required if v['id'] not in processed}.values())[:1]
    graph=merge(results)
    if args.interface:
        selected={f['id'] for f in graph['functions'] if f['name']==args.interface and (not getattr(args,'select_function',None) or f['id']==args.select_function)}
        if not selected and not failed:raise ValueError('Interface name found textually but no Clang definition was found')
        while True:
            before=len(selected)
            for edge in graph['call_targets']:
                if args.direction in ('down','both') and edge['source'] in selected:selected.add(edge['target'])
                if args.direction in ('up','both') and edge['target'] in selected:selected.add(edge['source'])
            if len(selected)==before:break
        graph['functions']=[f for f in graph['functions'] if f['id'] in selected]
        graph['callsites']=[c for c in graph['callsites'] if c['owner'] in selected]
        cids={c['id'] for c in graph['callsites']}
        graph['call_targets']=[e for e in graph['call_targets'] if e['source'] in selected and e['target'] in selected]
        graph['flow_edges']=[e for e in graph['flow_edges'] if e['owner'] in selected or e['owner'] is None]
        graph['issues']=[i for i in graph['issues'] if i['subject_id'] in cids]
        graph['state_events']=[e for e in graph['state_events'] if e['owner'] in selected or e['owner'] is None]
    search.save()
    graph['boundaries']=[]
    for call in graph['callsites']:
        if any(e['callsite']==call['id'] for e in graph['call_targets']):continue
        kind=call.get('boundary_kind')
        if not kind:
            if call['dispatch']!='direct':kind='indirect_unresolved'
            elif pending:kind='budget_pending'
            elif failed:kind='implementation_unavailable_with_parse_failures'
            else:kind='implementation_not_found'
        call['stop_reason']=kind
        graph['boundaries'].append(dict(owner=call['owner'],callsite=call['id'],callee=call['callee'],kind=kind,declaration=call.get('target_declaration'),evidence_ids=call['evidence_ids']))
    for f in failed:
        graph['issues'].append(dict(id='parse_'+digest(f)[:24],kind='environment_blocker',subject_id=f['file'],uncertain_properties=['translation_unit'],reason='Clang parse failed; no facts imported',evidence_ids=[],affected_scope=f['file'],blocking=False,next_action='fix_configuration',status='unresolved',input_hash=digest(f),diagnostics=f['diagnostics']))
    scope=dict(mode='interface' if args.interface else 'target' if args.target else 'repository',interface=args.interface,target=args.target,direction=args.direction)
    coverage=dict(selected_scope=scope,total_available_units=len(all_units),processed_units=len(processed),parsed=parsed,reused=reused,failed=failed,pending_units=[u['file'] for u in pending],
                  boundary_policy=rules,candidate_index=dict(scanned_files=search.scanned,reused_files=search.reused),capabilities=dict(direct_calls='ready',types='ready',global_objects='ready',data_flow='partial_path_insensitive',cfg='unsupported',alias='unsupported',kernel_boundary_rules='not_implemented'),
                  complete_call_chain=False,completed_requested_search=not bool(pending or failed),truncated=bool(pending))
    graph['coverage']=coverage;graph['scope']=scope
    store.put('parse_plan.json',plan);store.put('invalidation_plan.json',dict(changed=changed,units=plan,policy='per_TU_dependencies_and_negative_search_inventory'))
    store.put('compiler_facts.jsonl',[f for r in results for f in r['facts']])
    store.put('derived_relations.jsonl',graph['call_targets']+graph['flow_edges'])
    store.put('function_summaries.jsonl',[dict(function_id=f['id'],status='partial',flow_ids=[e['id'] for e in graph['flow_edges'] if e['owner']==f['id']],limitations=['no_CFG_fixed_point']) for f in graph['functions']])
    store.put('issues.json',graph['issues']);store.put('coverage.json',coverage)
    if not graph['functions'] and failed:raise RuntimeError('All selected function analysis failed; previous published snapshot retained')
    build_context=store.meta('current_build_context',{})
    source_inputs={**now,**build_context.get('inputs',{})}
    for result in results:source_inputs.update(result['dependencies'])
    manifest=dict(snapshot_id=uuid.uuid4().hex,input_files=source_inputs,workspace_roots=[str(r) for r in roots],workspace_revisions={str(r):revision(r) for r in roots},source_manifest_hash=digest(now),scope=scope,coverage=coverage,assumptions=build_context.get('assumptions',[]),parameters=build_context.get('parameters',{}),schema_version='0.1',tool_version=VERSION)
    manifest['analysis_id']=manifest['snapshot_id']
    publish(store,graph,manifest)
    reviews=requests(graph,store,manifest['snapshot_id'])
    store.setmeta('inventory',now)
    summary=dict(status='partial' if failed or any(i['kind']!='external_boundary' for i in graph['issues']) or pending else 'succeeded',snapshot_id=manifest['snapshot_id'],functions=len(graph['functions']),calls=len(graph['call_targets']),parsed=parsed,reused=reused,review_tasks=len(reviews),output=str(store.root/'snapshots'/manifest['snapshot_id']),run=str(store.run))
    store.put('run_summary.json',summary)
    if args.html:
        from .viewer import export
        summary['html']=str(export(store.root,args.html))
    print(json.dumps(summary,ensure_ascii=False,indent=2));return summary

def publish(store,graph,manifest):
    ids={f['id'] for f in graph['functions']}
    for edge in graph['call_targets']:
        if edge['source'] not in ids or edge['target'] not in ids:raise ValueError('Dangling call endpoint')
    ev={e['id'] for e in graph['evidence']}
    for edge in graph['call_targets']:
        if not set(edge['evidence_ids'])<=ev:raise ValueError('Missing evidence')
    snap=store.root/'snapshots'/manifest['snapshot_id'];snap.mkdir(parents=True,exist_ok=False)
    write(snap/'graph.json',envelope('graph',graph));manifest['graph_hash']=filehash(snap/'graph.json')
    write(snap/'analysis_manifest.json',envelope('analysis_manifest',manifest))
    store.put('snapshot_validation.json',dict(status='passed',snapshot_id=manifest['snapshot_id'],checks=['call_endpoints','evidence_references']))
    with store.db:store.db.execute('INSERT INTO snapshots VALUES (?,?)',(manifest['snapshot_id'],str(snap/'analysis_manifest.json')))
    write(store.root/'current.json',dict(snapshot_id=manifest['snapshot_id'],manifest_hash=filehash(snap/'analysis_manifest.json')))

def load_snapshot(out):
    root=Path(out).resolve();current=read(root/'current.json');folder=root/'snapshots'/current['snapshot_id']
    if filehash(folder/'analysis_manifest.json')!=current['manifest_hash']:raise ValueError('Manifest integrity failure')
    m=payload(folder/'analysis_manifest.json')
    if filehash(folder/'graph.json')!=m['graph_hash']:raise ValueError('Graph integrity failure')
    return payload(folder/'graph.json'),m
