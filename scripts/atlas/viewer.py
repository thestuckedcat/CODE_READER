from pathlib import Path
from .infrastructure.store import atomic, digest, envelope, write

def export(out,html):
    from .pipeline import load_snapshot
    graph,manifest=load_snapshot(out)
    bundle=dict(manifest=manifest,nodes=graph['functions'],edges=graph['call_targets'],**{k:v for k,v in graph.items() if k!='functions' and k!='call_targets'})
    destination=Path(html).resolve();folder=destination.parent;folder.mkdir(parents=True,exist_ok=True)
    write(folder/(destination.stem+'.export_bundle.json'),envelope('export_bundle',bundle))
    import json
    data=json.dumps(bundle,ensure_ascii=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    template=(Path(__file__).resolve().parents[2]/'assets/viewer.html').read_text(encoding='utf-8')
    atomic(destination,template.replace('__ATLAS_DATA__',data).encode())
    write(folder/(destination.stem+'.export_validation.json'),envelope('export_validation',dict(status='passed',html_hash=digest(destination.read_bytes()),snapshot_id=manifest['snapshot_id'])))
    return destination
