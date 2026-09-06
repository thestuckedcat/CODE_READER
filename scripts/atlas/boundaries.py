"""Stop by declaration provenance, never just a familiar function spelling."""
from pathlib import Path

def policy(args):
    return dict(linux_roots=[str(Path(p).resolve()) for p in (getattr(args,'linux_root',None) or [])],
                glibc_roots=[str(Path(p).resolve()) for p in (getattr(args,'glibc_root',None) or [])])

def classify(path,roots,rules,is_system=False):
    if not path:return None
    p=Path(path).resolve()
    for key,kind in (('linux_roots','linux'),('glibc_roots','glibc')):
        if any(p.is_relative_to(Path(r)) for r in rules.get(key,[])):return kind
    # An SDK directory passed with -isystem still belongs to the SDK.
    if any(p.is_relative_to(r) for r in roots):return None
    parts=p.parts
    if is_system:
        if 'linux' in parts or 'asm' in parts or 'asm-generic' in parts:return 'linux'
        if p.name in ('stdio.h','stdlib.h','string.h','unistd.h','pthread.h','time.h','errno.h','malloc.h','assert.h','wchar.h') or ('sys' in parts and p.suffix=='.h'):return 'glibc'
        return 'system_library'
    return None
