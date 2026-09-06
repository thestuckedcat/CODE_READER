#!/usr/bin/env python3
"""Build a portable distribution ZIP and SHA-256 runtime inventory."""
import argparse,hashlib,json,zipfile
from pathlib import Path
from atlas.core import VERSION
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--manifest-only',action='store_true');args=p.parse_args()
root=Path(__file__).resolve().parents[1];out=Path(args.out).resolve()
if out.is_relative_to(root):raise SystemExit('Put the release ZIP outside the skill folder')
rows=[]
for f in sorted((root/'runtime').rglob('*')):
    if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.pyc':rows.append(dict(path=str(f.relative_to(root)).replace('\\','/'),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size))
(root/'runtime-manifest.json').write_text(json.dumps(dict(version=VERSION,platforms=['linux-x86_64','windows-x86_64'],files=rows),indent=2),encoding='utf-8')
if args.manifest_only:
    print('Runtime manifest generated:',len(rows));raise SystemExit(0)
out.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
    for f in sorted(root.rglob('*')):
        if f.is_file() and '.git' not in f.parts and '__pycache__' not in f.parts and f.suffix!='.pyc':z.write(f,root.name+'/'+str(f.relative_to(root)))
print(json.dumps(dict(path=str(out),bytes=out.stat().st_size,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),runtime_files=len(rows)),indent=2))
