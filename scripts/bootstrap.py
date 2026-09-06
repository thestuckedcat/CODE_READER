#!/usr/bin/env python3
"""Verify the bundled payload; optionally install pinned packages for a source checkout."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify',action='store_true');p.add_argument('--install',action='store_true');a=p.parse_args()
if a.verify:
    manifest=json.loads((root/'runtime-manifest.json').read_text());bad=[]
    for item in manifest['files']:
        f=root/item['path']
        if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=item['sha256']:bad.append(item['path'])
    print(json.dumps({'verified':not bad,'invalid_files':bad,'files':len(manifest['files'])},indent=2));sys.exit(bool(bad))
if a.install:
    subprocess.run([sys.executable,'-m','pip','install','-r',str(root/'requirements.txt')],check=True)
else:print('Full distribution: run.sh / run.ps1 uses bundled dependencies. --verify checks hashes; --install installs pinned packages into the current Python environment for source development.')
