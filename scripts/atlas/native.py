"""Optional native CFG stage, isolated from the reusable libclang facts cache."""
import os, platform, shutil, subprocess, re
from pathlib import Path
from .infrastructure.store import digest, filehash, read, write


def executable(explicit=None):
    if explicit:
        p=Path(explicit).resolve()
        if not p.is_file():raise ValueError('Native extractor missing: '+str(p))
        return str(p)
    name='atlas-semantic.exe' if os.name=='nt' else 'atlas-semantic'
    root=Path(__file__).resolve().parents[2]
    p=root/'runtime'/('windows-x86_64' if os.name=='nt' else 'linux-x86_64')/'native'/name
    return str(p) if p.is_file() else shutil.which(name)


def identity(path):
    if not path:return None
    r=subprocess.run([path,'--version'],capture_output=True,text=True,timeout=10)
    if r.returncode:raise RuntimeError('Native extractor cannot start: '+r.stderr)
    libraries={}
    if platform.system()=='Linux' and shutil.which('ldd'):
        linked=subprocess.run(['ldd',path],capture_output=True,text=True,timeout=10)
        if 'not found' in linked.stdout:raise RuntimeError('Native shared library missing: '+linked.stdout)
        for p in re.findall(r'(?:=>\s+|^\s*)(/[^\s]+)',linked.stdout,re.M):
            libraries[str(Path(p).resolve())]=filehash(p)
    elif os.name=='nt':
        libraries={str(p):filehash(p) for p in Path(path).parent.glob('*.dll')}
    return dict(path=path,sha256=filehash(path),version=r.stdout.strip(),driver=filehash(__file__),libraries=libraries)


def extract_cfg(unit,result,store,tool,timeout):
    ev={e['id']:e for e in result['facts'] if e['kind']=='evidence'}
    functions=[]
    for f in result['facts']:
        if f['kind']=='function':
            e=ev[f['evidence_ids'][0]]
            functions.append(dict(id=f['id'],file=e['file'],start=e['start']))
    key=digest(dict(stage='native_cfg_v1',unit=unit,functions=functions,
                    dependencies=result['dependencies'],tool=tool))
    cached=store.cache_get(key)
    if cached:
        try:
            data=store.get(cached['ir']);store.entries.append(cached['ir'])
            return data,dict(unit=unit['id'],action='reuse',key=key)
        except (OSError,ValueError,KeyError):pass
    job=store.run/'native_jobs'/unit['id'];job.mkdir(parents=True,exist_ok=True)
    write(job/'request.json',dict(file=unit['file'],directory=unit['directory'],arguments=unit['arguments'],functions=functions))
    try:
        p=subprocess.run([tool['path'],str(job/'request.json'),str(job/'output.json')],capture_output=True,text=True,errors='replace',timeout=timeout)
        (job/'stderr.log').write_text(p.stderr,encoding='utf-8')
        if p.returncode:raise RuntimeError(p.stderr or 'Native extractor failed')
        data=read(job/'output.json')
        if data.get('protocol')!=1:raise ValueError('Unsupported native protocol')
        rows=data['functions']
        for f in rows:
            for n in f.get('nodes',[]):
                loc=n['location'];loc['hash']=result['dependencies'].get(loc['file']) or filehash(loc['file'])
        seen={f['id'] for f in rows}
        rows.extend(dict(id=f['id'],status='unsupported',reason='native_definition_not_matched') for f in functions if f['id'] not in seen)
        receipt=store.put('cfg_ir.jsonl',rows,unit['id'],'clang_native',key)
        store.cache_put(key,dict(ir=receipt))
        return rows,dict(unit=unit['id'],action='parse',key=key,reason='CFG_input_changed_or_missing')
    except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired) as e:
        rows=[dict(id=f['id'],status='failed',reason=str(e)) for f in functions]
        store.put('cfg_ir.jsonl',rows,unit['id'],'clang_native',key)
        return rows,dict(unit=unit['id'],action='failed',reason=str(e))
