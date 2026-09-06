"""Content-addressed artifacts and crash-safe single-writer checkpoints."""
import hashlib, json, os, sqlite3, uuid
from pathlib import Path
VERSION = '0.2.0'
SCHEMA = '0.1'
def encoded(x): return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def digest(x): return hashlib.sha256(x if isinstance(x, bytes) else encoded(x)).hexdigest()
def filehash(p):
    try: return digest(Path(p).read_bytes())
    except (FileNotFoundError, IsADirectoryError): return None

def atomic(p, data):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, p)

def write(p, data): atomic(p, encoded(data))
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def envelope(kind, payload, task='python', inputs='', origin='python'):
    return dict(schema_version=SCHEMA, record_kind=kind, record_id=digest([kind,payload]), payload=payload,
                provenance=dict(producer_kind=origin,producer_version=VERSION,task_id=task,input_hash=inputs,configuration_id=None,evidence_ids=[]))
def payload(p): return read(p)['payload']

class Store:
    def __init__(self, root):
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/'index.sqlite', timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, receipt TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);''')
        self.run_id=uuid.uuid4().hex; self.run=self.root/'runs'/self.run_id; self.run.mkdir(parents=True)
        self.entries=[]
    def put(self, name, data, scope='run', origin='python', inputs=''):
        if name.endswith('.jsonl'):
            raw=b''.join(encoded(envelope(name[:-6],x,scope,inputs,origin))+b'\n' for x in data)
        else: raw=encoded(envelope(name.rsplit('.',1)[0],data,scope,inputs,origin))
        h=digest(raw); p=self.root/'objects'/h[:2]/(h+Path(name).suffix)
        if not p.exists(): atomic(p,raw)
        entry=dict(logical_name=name,scope_key=scope,relative_path=str(p.relative_to(self.root)),sha256=h,bytes=len(raw))
        self.entries.append(entry)
        write(self.run/'artifacts.json',envelope('artifacts',dict(run_id=self.run_id,entries=self.entries)))
        return entry
    def get(self,e):
        p=self.root/e['relative_path']; raw=p.read_bytes()
        if digest(raw)!=e['sha256']: raise ValueError('Artifact hash mismatch: '+str(p))
        if p.suffix=='.jsonl': return [json.loads(l)['payload'] for l in raw.splitlines()]
        return json.loads(raw)['payload']
    def cache_get(self,key):
        r=self.db.execute('SELECT receipt FROM cache WHERE key=?',(key,)).fetchone()
        return json.loads(r[0]) if r else None
    def cache_put(self,key,receipt):
        with self.db:self.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?)',(key,json.dumps(receipt)))
        self.put('checkpoint.json',dict(task_key=key,receipt=receipt,status='succeeded'),key)
    def meta(self,key,default=None):
        r=self.db.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
        return json.loads(r[0]) if r else default
    def setmeta(self,key,value):
        with self.db:self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',(key,json.dumps(value)))
    def close(self): self.db.close()

class Lock:
    """OS advisory lock; released on process death, never stale-file deletion."""
    def __init__(self,root): self.path=Path(root)/'writer.lock'
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True); self.f=self.path.open('a+b'); self.f.write(b'0'); self.f.flush();self.f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt;msvcrt.locking(self.f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl;fcntl.flock(self.f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError: self.f.close();raise RuntimeError('Another writer is running for this output directory')
        return self
    def __exit__(self,*args): self.f.close()
