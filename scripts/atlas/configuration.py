"""CMake is the evaluator. This module records inputs and routes missing context."""
import os,re,shutil,subprocess
from pathlib import Path
from .infrastructure.store import digest, filehash, read


def discover(repo,rows,explicit=None):
    repo=Path(repo).resolve();chosen=Path(explicit).resolve() if explicit else repo
    parents=[]
    for parent in list(repo.parents)[:8]:
        cm=parent/'CMakeLists.txt'
        if not cm.is_file():continue
        relative=repo.relative_to(parent).as_posix()
        text=cm.read_text(errors='replace')
        linked=bool(re.search(r'add_subdirectory\s*\(\s*"?'+re.escape(relative)+r'"?(?:\s|\))',text,re.I))
        parents.append(dict(path=str(parent),direct_child_reference=linked))
        if linked and not explicit:chosen=parent;break
    files=[r for r in rows if Path(r['path']).name=='CMakeLists.txt' or Path(r['path']).suffix=='.cmake']
    if (chosen/'CMakeLists.txt').is_file() and not any(r['path']==str(chosen/'CMakeLists.txt') for r in files):
        files.append(dict(path=str(chosen/'CMakeLists.txt'),hash=filehash(chosen/'CMakeLists.txt')))
    vars={}
    for r in files:
        text=Path(r['path']).read_text(errors='replace')
        for match in re.finditer(r'\$\{([A-Za-z_][A-Za-z_0-9]*)\}',text):
            vars.setdefault(match[1],[]).append(dict(file=r['path'],line=text.count('\n',0,match.start())+1))
    return dict(entry=str(chosen),origin='explicit' if explicit else 'parent_add_subdirectory' if chosen!=repo else 'repository',parent_candidates=parents,files=files,variable_uses=vars,
                note='Variable references are candidates, not evidence that a value is missing.')


def parameters(args,store,entry):
    key='parameters:'+str(entry);previous=store.meta(key,{})
    supplied=read(args.params) if args.params else {}
    if 'payload' in supplied:supplied=supplied['payload']
    if not isinstance(supplied,dict) or any(not isinstance(v,(str,int,float,bool)) for v in supplied.values()):raise ValueError('--params requires a flat object of CMake variable values')
    values={**previous,**supplied}
    assumptions=read(args.assumptions) if getattr(args,'assumptions',None) else store.meta(key+':assumptions',[])
    if not isinstance(assumptions,list):raise ValueError('--assumptions must be a JSON array')
    for a in assumptions:
        if not all(k in a for k in ('name','value','reason','accepted_by')):raise ValueError('Assumption needs name/value/reason/accepted_by')
        if a['name'] not in values or values[a['name']]!=a['value']:raise ValueError('Accepted assumption must match explicit/cached parameter value')
    store.put('parameters.json',[dict(name=k,value=v,origin='user' if k in supplied else 'cached_user',status='confirmed') for k,v in sorted(values.items())])
    store.put('assumptions.json',assumptions)
    # Explicit answers persist even when another missing input blocks this attempt.
    store.setmeta(key,values);store.setmeta(key+':assumptions',assumptions)
    return values,assumptions


def questions(store,discovery,error,required=()):
    names=set(required)
    names.update(re.findall(r'uninitialized variable [\'\"]([^\'\"]+)',error,re.I))
    names.update(n for n in discovery['variable_uses'] if n in error and not n.startswith('CMAKE_'))
    items=[dict(id='param_'+n,name=n,status='needs_user_or_agent_context',uses=discovery['variable_uses'].get(n,[]),suggested_value=None,
                reason='Provide an evidenced value; semantic substitutions require explicit acceptance.') for n in sorted(names)]
    store.put('configuration_questions.json',dict(status='needs_configuration',items=items,diagnostic=error,
        entry=discovery['entry'],parent_candidates=discovery['parent_candidates'],next_action='inspect CMake evidence, supply --params / --cmake-root / --child-cmake-root; rerun'))


def file_api(build):
    reply=build/'.cmake/api/v1/reply';inputs={};targets=[]
    indexes=sorted(reply.glob('index-*.json'))
    if not indexes:return inputs,targets
    index=read(indexes[-1])
    for obj in index.get('objects',[]):
        data=read(reply/obj['jsonFile'])
        if obj['kind']=='cmakeFiles':
            for item in data.get('inputs',[]):
                p=Path(item['path']);p=p if p.is_absolute() else Path(data['paths']['source'])/p
                inputs[str(p.resolve())]=filehash(p)
        if obj['kind']=='codemodel':
            for config in data.get('configurations',[]):
                for t in config.get('targets',[]):
                    v=read(reply/t['jsonFile']);v['configuration']=config.get('name','');v['source_root']=data['paths']['source'];targets.append(v)
    return inputs,targets


def evaluate(entry,values,args,store,discovery,label='main'):
    entry=Path(entry).resolve();build=store.root/'build'/digest([str(entry),values])[:16]
    build.mkdir(parents=True,exist_ok=True)
    cachekey='configure:'+digest([str(entry),values]);previous=store.meta(cachekey,{})
    env={k:os.environ.get(k) for k in ('CC','CXX','CFLAGS','CXXFLAGS','LDFLAGS','PATH','CMAKE_PREFIX_PATH','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH')}
    from .build import tool as resolve_tool
    cmake=resolve_tool('cmake')
    if not cmake:raise RuntimeError('CMake missing; provide evaluated --compdb or install the bundled runtime')
    fingerprint=digest([env,filehash(cmake),filehash(Path(__file__))])
    tree_names=sorted(str(p) for p in entry.rglob('CMakeLists.txt') if not p.is_relative_to(store.root))
    # Also watch files for GLOB source discovery, even if no existing dependency points to a new file.
    source_names=[]
    for directory,dirs,files in os.walk(entry):
        dirs[:]=[d for d in dirs if d not in ('.git','runtime','.venv','__pycache__') and not (Path(directory)/d).resolve().is_relative_to(store.root)]
        source_names.extend(str(Path(directory)/n) for n in sorted(files))
    names_hash=digest([tree_names,source_names])
    if previous and previous.get('fingerprint')==fingerprint and previous.get('names_hash')==names_hash and all(filehash(p)==h for p,h in previous.get('inputs',{}).items()) and all(filehash(p)==h for p,h in previous.get('outputs',{}).items()):
        store.put('configure_result.json',dict(status='reused',build=str(build),label=label,inputs=previous['inputs']))
        return previous
    query=build/'.cmake/api/v1/query';query.mkdir(parents=True,exist_ok=True)
    for name in ('codemodel-v2','cmakeFiles-v1'):(query/name).touch()
    trace=store.run/(label+'.cmake-trace.jsonl')
    argv=[cmake,'-S',str(entry),'-B',str(build),'-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','--warn-uninitialized','--trace-expand','--trace-format=json-v1','--trace-redirect='+str(trace)]
    cache=build/'CMakeCache.txt'
    prior=re.search(r'^CMAKE_GENERATOR:INTERNAL=(.+)$',cache.read_text(errors='replace'),re.M) if cache.exists() else None
    generator=prior.group(1) if prior else 'Ninja' if resolve_tool('ninja') else 'Unix Makefiles' if os.name!='nt' else None
    if not generator:raise RuntimeError('Ninja required for compilation database generation on Windows')
    argv+=['-G',generator]+['-D'+k+'='+('ON' if v is True else 'OFF' if v is False else str(v)) for k,v in sorted(values.items())]
    store.put('configure_request.json',dict(argv=argv,cwd=str(entry),label=label))
    try:r=subprocess.run(argv,cwd=entry,capture_output=True,text=True,errors='replace',timeout=args.configure_timeout)
    except subprocess.TimeoutExpired as e:
        questions(store,discovery,'CMake configure timeout; inspect '+str(trace));raise RuntimeError('CMake configure timeout') from e
    prefix='configure' if label=='main' else label
    (store.run/(prefix+'.stdout.log')).write_text(r.stdout,encoding='utf-8');(store.run/(prefix+'.stderr.log')).write_text(r.stderr,encoding='utf-8')
    store.put('configure_result.json',dict(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr,build=str(build),label=label,status='evaluated'))
    if r.returncode:
        questions(store,discovery,r.stderr);raise RuntimeError('CMake configuration failed; see '+str(store.run/(prefix+'.stderr.log')))
    inputs,targets=file_api(build)
    relations=[];external=[]
    if trace.exists():
        import json
        for line in trace.read_text(errors='replace').splitlines():
            try:e=json.loads(line)
            except ValueError:continue
            if 'file' in e:inputs[e['file']]=filehash(e['file'])
            cmd=e.get('cmd','').lower()
            if cmd in ('add_subdirectory','include','configure_file','externalproject_add'):
                relations.append({k:e.get(k) for k in ('cmd','args','file','line')})
                if cmd=='externalproject_add':external.append(e.get('args',[]))
    inputs[str(entry/'CMakeLists.txt')]=filehash(entry/'CMakeLists.txt')
    dbs=[str(p) for p in sorted(build.rglob('compile_commands.json'))]
    outputs={p:filehash(p) for p in dbs};outputs[str(cache)]=filehash(cache)
    generated=[]
    for row in relations:
        if row['cmd'].lower()=='configure_file' and len(row['args'])>1:
            # Resolve from CMake File API's generated inputs where possible; trace relative output is only a candidate.
            generated.append(dict(arguments=row['args'],source=row['file'],line=row['line'],status='cmake_evaluated'))
    for p in sorted(build.rglob('*')):
        if p.is_file() and p.suffix in ('.h','.hpp','.c','.cpp','.inc'):
            outputs[str(p)]=filehash(p)
            generated.append(dict(path=str(p),hash=outputs[str(p)],status='available',origin='cmake_build_directory'))
    result=dict(inputs=inputs,outputs=outputs,databases=dbs,targets=targets,relations=relations,external_projects=external,generated=generated,fingerprint=fingerprint,names_hash=names_hash,entry=str(entry))
    store.setmeta(cachekey,result)
    return result
