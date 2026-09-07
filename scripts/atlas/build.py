"""CMake evaluation and explicit compilation-context normalization."""
import os, re, shlex, shutil, subprocess, sys
from pathlib import Path
from .infrastructure.store import digest, filehash, read, write
EXT={'.c','.cc','.cpp','.cxx','.h','.hh','.hpp','.hxx','.in','.cmake','.inc','.def','.s','.S'}
SKIP={'.git','.svn','node_modules','__pycache__','.venv'}
def tool(name):
    local=Path(sys.executable).parent/(name+'.exe' if os.name=='nt' else name)
    return str(local) if local.is_file() else shutil.which(name)
def inventory(roots,exclude):
    rows=[]
    for root in roots:
        for directory,dirs,files in os.walk(root):
            dirs[:]=sorted(d for d in dirs if d not in SKIP and not (Path(directory)/d).resolve().is_relative_to(exclude))
            for name in sorted(files):
                p=Path(directory)/name
                if p.suffix in EXT or name in ('CMakeLists.txt','CMakePresets.json','CMakeUserPresets.json'):
                    rows.append(dict(path=str(p.resolve()),root=str(root),relative=str(p.relative_to(root)),hash=filehash(p)))
    return rows

def doctor():
    checks={}
    for x in ('cmake','ninja'):checks[x]=tool(x)
    for x in ('git','cc','c++'): checks[x]=shutil.which(x)
    try:
        from clang import cindex
        cindex.Index.create(); checks['libclang']='loaded'
        checks['libclang_path']=str(cindex.conf.get_filename())
        checks['libclang_hash']=filehash(cindex.conf.get_filename())
    except Exception as e:checks['libclang']=str(e)
    import platform
    from .native import executable,identity
    checks['native_extractor']=executable()
    try:checks['native_identity']=identity(checks['native_extractor'])
    except (OSError,RuntimeError,subprocess.SubprocessError) as e:checks['native_identity']=None;checks['native_error']=str(e)
    layers=dict(tools=dict(parse='ready' if checks['libclang']=='loaded' else 'blocked',configure='ready' if checks['cmake'] else 'needs_cmake_or_compdb'),project_configuration='checked_by_configure',source_dependencies='checked_per_TU')
    return dict(python=sys.version,platform=sys.platform,architecture=platform.machine(),layers=layers,checks=checks,ready=checks['libclang']=='loaded',
                capabilities=dict(native_cfg=bool(checks['native_identity']),interprocedural_alias=False,clang_ast=True))

def configure(args,store,rows):
    from .configuration import discover,parameters,evaluate,questions
    discovery=discover(args.repo,rows,args.cmake_root)
    store.put('cmake_discovery.json',discovery)
    entry=Path(discovery['entry']);values,assumptions=parameters(args,store,entry)
    missing=[n for n in getattr(args,'require_param',[]) or [] if n not in values]
    if missing:
        questions(store,discovery,'Required parameters were not supplied',missing)
        raise RuntimeError('Missing required configuration: '+', '.join(missing))
    dbs=[Path(p).resolve() for p in (args.compdb or [])];evaluations=[]
    if not dbs:
        evaluations.append(evaluate(entry,values,args,store,discovery))
    for i,child in enumerate(getattr(args,'child_cmake_root',[]) or []):
        evaluations.append(evaluate(child,values,args,store,discovery,'child'+str(i)))
    for evaluation in evaluations:
        dbs.extend(Path(p) for p in evaluation['databases'])
    dbs=sorted(set(dbs))
    relations=[r for ev in evaluations for r in ev['relations']]
    external=[e for ev in evaluations for e in ev['external_projects']]
    store.put('cmake_relations.json',dict(relations=relations,external_projects=external))
    store.put('generated_files.json',[f for ev in evaluations for f in ev['generated']])
    if not dbs:
        questions(store,discovery,'No compile database. Independently configure existing ExternalProject SOURCE_DIR with --child-cmake-root and explicit parameters, or supply --compdb. No downloads/builds are triggered automatically.')
        raise RuntimeError('No compilation database; independent child configuration is required')
    targets=[t for ev in evaluations for t in ev['targets']]
    units=[]
    for p in dbs:
        if not p.is_file():raise ValueError('Compilation database missing: '+str(p))
        entries=read(p);store.put('compile_commands.json',entries,str(p),origin='cmake')
        for e in entries:
            cwd=Path(e['directory']).resolve();src=Path(e['file']);src=(cwd/src).resolve() if not src.is_absolute() else src.resolve()
            argv=e.get('arguments')
            if argv is None:
                if os.name=='nt':
                    from clang.cindex import CompilationDatabase
                    commands=CompilationDatabase.fromDirectory(str(p.parent)).getCompileCommands(str(src))
                    if commands:argv=list(next(iter(commands)).arguments)
                    else:raise ValueError('No native compilation command for '+str(src))
                else:argv=shlex.split(e['command'])
            u=normalize(src,cwd,list(argv),args,e.get('output',''))
            u['database']=str(p);u['build_id']=digest(str(p.parent))
            u['target_names']=sorted(set(re.findall(r'CMakeFiles/([^/]+)\.dir/', ' '.join(argv).replace('\\','/'))))
            if not u['target_names']:
                u['target_names']=sorted({t['name'] for t in targets for f in t.get('sources',[]) if (Path(t['source_root'])/f['path']).resolve()==src})
            units.append(u)
    units=list({u['id']:u for u in units}.values())
    config_inputs={k:v for ev in evaluations for k,v in ev['inputs'].items()}
    store.setmeta('current_build_context',dict(assumptions=assumptions,parameters=values,inputs=config_inputs,external_projects=external,targets=targets))
    store.put('build_context.json',dict(units=units,databases=[str(p) for p in dbs],targets=targets,configuration_id=digest(units),assumptions=assumptions,parameters=values))
    store.put('configuration_questions.json',dict(status='ready',items=[],external_projects=external))
    return units

def normalize(src,cwd,argv,args,output):
    original=argv[:];response_inputs={}
    def expand(tokens,active=()):
        output=[]
        for token in tokens:
            if not token.startswith('@'):output.append(token);continue
            path=(cwd/token[1:]).resolve()
            if str(path) in active or len(active)>=8:raise ValueError('Cyclic/deep response file: '+str(path))
            response_inputs[str(path)]=filehash(path)
            text=path.read_text(encoding='utf-8')
            if os.name=='nt':
                tokens=shlex.split(text,posix=False)
                tokens=[token[1:-1] if len(token)>=2 and token[0]==token[-1] and token[0] in ('"', "'") else token for token in tokens]
            else:tokens=shlex.split(text)
            output.extend(expand(tokens,active+(str(path),)))
        return output
    argv=expand(argv)
    if Path(argv[0]).name in ('ccache','sccache'):argv=argv[1:]
    compiler=argv.pop(0)
    if Path(compiler).stem.lower() in ('cl','clang-cl'):
        raise ValueError('MSVC-style flags currently unsupported; use Clang/GCC-style compile database (Linux SDK on Linux recommended)')
    result=['-working-directory='+str(cwd)];removed=[];i=0
    while i<len(argv):
        a=argv[i];i+=1
        if a in ('-o','-MF','-MT','-MQ','-MJ'):
            removed.append(a);i+=1;continue
        if a in ('-c','-MD','-MMD','-MP'):removed.append(a);continue
        try:
            if not a.startswith('-') and (cwd/a).resolve()==src:continue
        except OSError:pass
        result.append(a)
    resource=Path(__file__).resolve().parents[2]/'runtime/clang-resource'
    if resource.is_dir(): result+=['-resource-dir='+str(resource)]
    elif os.name!='nt':
        # PyPI libclang ships the shared library but not Clang builtin headers.
        # Reuse the selected GCC-compatible toolchain's builtin include directory
        # as explicit parse context instead of changing the host installation.
        try:
            probe=subprocess.run([compiler,'-print-file-name=include'],cwd=cwd,capture_output=True,text=True,timeout=10)
            builtin=Path(probe.stdout.strip()).resolve()
            if probe.returncode==0 and builtin.is_dir():result+=['-isystem',str(builtin)]
        except (OSError,subprocess.SubprocessError):pass
    result+=args.clang_arg or []
    return dict(id=digest([str(src),str(cwd),result]),file=str(src),directory=str(cwd),arguments=result,
                original_arguments=original,compiler=compiler,removed_nonsemantic_flags=removed,output=output,response_inputs=response_inputs)
