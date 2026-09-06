"""CMake evaluation and explicit compilation-context normalization."""
import os, re, shlex, shutil, subprocess, sys
from pathlib import Path
from .core import digest,filehash,write,read
EXT={'.c','.cc','.cpp','.cxx','.h','.hh','.hpp','.hxx','.in','.cmake','.inc','.def','.s','.S'}
SKIP={'.git','.svn','node_modules','__pycache__','.venv'}
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
    for x in ('cmake','ninja','git','cc','c++'): checks[x]=shutil.which(x)
    try:
        from clang import cindex
        cindex.Index.create(); checks['libclang']='loaded'
        checks['libclang_path']=str(cindex.conf.get_filename())
        checks['libclang_hash']=filehash(cindex.conf.get_filename())
    except Exception as e:checks['libclang']=str(e)
    return dict(python=sys.version,platform=sys.platform,checks=checks,ready=checks['libclang']=='loaded',
                capabilities=dict(native_cfg=False,interprocedural_alias=False,clang_ast=True))

def configure(args,store,rows):
    import json
    parameters=read(args.params) if args.params else {}
    if 'payload' in parameters:parameters=parameters['payload']
    if not isinstance(parameters,dict) or any(not isinstance(v,(str,int,float,bool)) for v in parameters.values()):
        raise ValueError('--params expects a JSON object of explicit CMake variable values')
    store.put('parameters.json',[dict(name=k,value=v,origin='user',status='confirmed') for k,v in sorted(parameters.items())])
    store.put('assumptions.json',[])
    cmakes=[r for r in rows if Path(r['path']).name=='CMakeLists.txt' or Path(r['path']).suffix=='.cmake']
    store.put('cmake_discovery.json',dict(entry=str(args.cmake_root or args.repo),files=cmakes,status='candidates_until_evaluated'))
    dbs=[Path(p).resolve() for p in (args.compdb or [])]
    if not dbs:
        if not shutil.which('cmake'):raise RuntimeError('CMake missing. Run bootstrap, or supply --compdb.')
        entry=Path(args.cmake_root or args.repo).resolve()
        build=store.root/'build'/digest([str(entry),parameters])[:16];build.mkdir(parents=True,exist_ok=True)
        query=build/'.cmake/api/v1/query';query.mkdir(parents=True,exist_ok=True);(query/'codemodel-v2').touch()
        argv=['cmake','-S',str(entry),'-B',str(build),'-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']
        cache=build/'CMakeCache.txt'
        prior=re.search(r'^CMAKE_GENERATOR:INTERNAL=(.+)$',cache.read_text(errors='replace'),re.M) if cache.exists() else None
        if prior:argv+=['-G',prior.group(1)]
        elif shutil.which('ninja'):argv+=['-G','Ninja']
        elif os.name!='nt':argv+=['-G','Unix Makefiles']
        else:raise RuntimeError('Ninja required for Windows compilation database generation')
        argv += ['-D'+k+'='+('ON' if v is True else 'OFF' if v is False else str(v)) for k,v in sorted(parameters.items())]
        store.put('configure_request.json',dict(argv=argv,cwd=str(entry)))
        r=subprocess.run(argv,cwd=entry,capture_output=True,text=True,errors='replace',timeout=args.configure_timeout)
        (store.run/'configure.stdout.log').write_text(r.stdout,encoding='utf-8');(store.run/'configure.stderr.log').write_text(r.stderr,encoding='utf-8')
        store.put('configure_result.json',dict(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr,build=str(build)))
        if r.returncode:
            store.put('configuration_questions.json',dict(status='needs_configuration',message='Read CMake error, identify missing values; do not invent semantic defaults',diagnostic=r.stderr))
            raise RuntimeError('CMake configuration failed. See '+str(store.run/'configure.stderr.log'))
        dbs=sorted(build.rglob('compile_commands.json'))
        replies=sorted(build.rglob('reply/*.json'))
        for p in replies:store.put('cmake_reply.json',read(p),str(p))
        if not dbs:raise RuntimeError('No compile_commands.json. Superbuild may need child configuration; provide repeated --compdb for evaluated child builds.')
    units=[]
    for p in dbs:
        entries=read(p);store.put('compile_commands.json',entries,str(p),origin='cmake')
        for e in entries:
            cwd=Path(e['directory']).resolve();src=Path(e['file']);src=(cwd/src).resolve() if not src.is_absolute() else src.resolve()
            argv=e.get('arguments')
            if argv is None:
                if os.name=='nt':
                    # LLVM's compilation database reader handles Windows command-line quoting.
                    from clang.cindex import CompilationDatabase
                    commands=CompilationDatabase.fromDirectory(str(p.parent)).getCompileCommands(str(src))
                    if commands: argv=list(next(iter(commands)).arguments)
                    else:raise ValueError('No native compilation command for '+str(src))
                else:argv=shlex.split(e['command'])
            units.append(normalize(src,cwd,list(argv),args, e.get('output','')))
    units=list({u['id']:u for u in units}.values())
    store.put('build_context.json',dict(units=units,databases=[str(p) for p in dbs],configuration_id=digest(units)))
    return units

def normalize(src,cwd,argv,args,output):
    original=argv[:]
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
        if a.startswith('@'):raise ValueError('Response files need explicit expansion before analysis: '+a)
        result.append(a)
    resource=Path(__file__).resolve().parents[2]/'runtime/clang-resource'
    if resource.is_dir(): result+=['-resource-dir='+str(resource)]
    result+=args.clang_arg or []
    return dict(id=digest([str(src),str(cwd),result]),file=str(src),directory=str(cwd),arguments=result,
                original_arguments=original,compiler=compiler,removed_nonsemantic_flags=removed,output=output)
