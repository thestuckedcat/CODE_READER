"""Incremental candidate discovery. Tokens are hints; only Clang creates calls."""
import os,re
from pathlib import Path
from .core import digest,filehash
from .boundaries import classify


def include_dirs(unit):
    ordinary=[];quoted=[];system=[];args=unit['arguments'];i=0
    while i<len(args):
        arg=args[i];i+=1;value=None;kind=None
        for prefix,group in (('-isystem',system),('-iquote',quoted),('-idirafter',system),('-I',ordinary)):
            if arg==prefix and i<len(args):value=args[i];i+=1;kind=group;break
            if arg.startswith(prefix) and len(arg)>len(prefix):value=arg[len(prefix):];kind=group;break
        if value is not None:
            p=Path(value);kind.append((Path(unit['directory'])/p).resolve() if not p.is_absolute() else p.resolve())
    for variable,group in (('CPATH',ordinary),('C_INCLUDE_PATH',system),('CPLUS_INCLUDE_PATH',system)):
        group.extend(Path(p).resolve() for p in os.environ.get(variable,'').split(os.pathsep) if p)
    return quoted,ordinary,system


class CandidateIndex:
    def __init__(self,store,units,roots,rules):
        self.store=store;self.units=units;self.roots=roots;self.rules=rules
        self.files={};self.entries={};self.reused=0;self.scanned=0;self.queries=[]
        scanner_hash=filehash(Path(__file__))
        previous=store.meta('candidate_files',{}) if store.meta('candidate_scanner')==scanner_hash else {}
        def scan(path):
            path=str(path)
            if path in self.files:return self.files[path]
            h=filehash(path);cached=previous.get(path)
            if cached and cached['hash']==h:self.reused+=1;result=cached
            else:
                self.scanned+=1
                try:text=Path(path).read_text(errors='replace')
                except OSError:text=''
                # Remove comments only for hints. No semantic claims are based on this scanner.
                clean=re.sub(r'/\*.*?\*/|//[^\n]*',' ',text,flags=re.S)
                tokens=sorted(set(re.findall(r'\b[A-Za-z_]\w*\b',clean)))
                defs=sorted(set(re.findall(r'\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:(?:const|noexcept|override|final)\s*)*\{',clean)))
                includes=re.findall(r'^\s*#\s*include\s*([<"])([^>"\n]+)[>"]',clean,re.M)
                opaque=bool(re.search(r'^\s*#\s*include\s+[^<"\s]',clean,re.M))
                result=dict(hash=h,tokens=tokens,definition_hints=defs,includes=includes,opaque_include=opaque)
            self.files[path]=result;return result
        for u in units:
            quoted,normal,system=include_dirs(u);seen=set();todo=[Path(u['file'])];tokens=set();defs=set();opaque=False
            while todo:
                p=todo.pop().resolve()
                if str(p) in seen or classify(p,roots,rules):continue
                seen.add(str(p));f=scan(p);tokens.update(f['tokens']);defs.update(f['definition_hints']);opaque|=f['opaque_include']
                for delim,name in f['includes']:
                    dirs=([p.parent]+quoted if delim=='"' else [])+normal+system
                    for directory in dirs:
                        target=directory/name
                        if target.is_file():
                            if any(target.resolve().is_relative_to(r) for r in roots):todo.append(target)
                            break
            self.entries[u['id']]=dict(tokens=tokens,definitions=defs,files=seen,opaque=opaque)
        store.setmeta('candidate_files',self.files)
        store.setmeta('candidate_scanner',scanner_hash)
        store.put('candidate_index.json',dict(scanned_files=self.scanned,reused_files=self.reused,units=[dict(unit_id=k,files=sorted(v['files']),opaque_include=v['opaque']) for k,v in self.entries.items()]))

    def candidates(self,names,definitions=False):
        names={n for n in names if n};ranked=[]
        for u in self.units:
            e=self.entries[u['id']]
            hint=bool(names&e['definitions']);match=bool(names&e['tokens'])
            if hint or match or e['opaque']:ranked.append((0 if hint else 1 if match else 2,u))
        ranked.sort(key=lambda pair:(pair[0],pair[1]['file'],pair[1]['id']))
        # Definition mode favors but does not trust hints: callers remain fallback candidates.
        result=[u for _,u in ranked]
        self.queries.append(dict(names=sorted(names),intent='definitions' if definitions else 'references',candidate_units=[u['id'] for u in result],certainty='lexical_candidates_only'))
        return result

    def definition_candidates(self,name):
        hints=[u for u in self.units if name in self.entries[u['id']]['definitions']]
        return sorted(hints,key=lambda u:(u['file'],u['id'])) or self.candidates([name],True)

    def save(self):self.store.put('search_queries.json',self.queries)
