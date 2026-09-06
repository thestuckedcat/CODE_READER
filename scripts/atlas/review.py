"""File-based host-agent bridge. No hidden API keys or model calls."""
from pathlib import Path
from .core import digest,read,write,envelope,filehash

def requests(graph,store,snapshot):
    paths=[];ev={e['id']:e for e in graph['evidence']}
    for issue in graph['issues']:
        if issue['kind']!='semantic_unresolved':continue
        data=dict(task_id='review_'+issue['id'],task_kind='review_issues',snapshot_id=snapshot,input_hash=issue['input_hash'],
                  issue_ids=[issue['id']],issue=issue,context=[ev[e] for e in issue['evidence_ids'] if e in ev],
                  allowed_result_status=['resolved','candidates','needs_configuration','unresolved'],
                  budget=dict(max_files=20,max_searches=20),instructions='Read source. Propose candidate call targets only with evidence; keep unknown possible. Do not overwrite compiler facts.')
        entry=store.put('review_request.json',data,issue['id']);p=store.run/'reviews'/(issue['id']+'.request.json');write(p,envelope('review_request',data))
        paths.append(dict(issue_id=issue['id'],request=str(p),artifact=entry))
    store.put('review_plan.json',paths)
    return paths

def validate_review(graph,manifest,result_path):
    result=read(result_path)
    schema=read(Path(__file__).resolve().parents[2]/'schemas/review_result.schema.json')
    from jsonschema import Draft202012Validator
    Draft202012Validator(schema).validate(result)
    r=result['payload'];issues={i['id']:i for i in graph['issues']};fs={f['id'] for f in graph['functions']};calls={c['id']:c for c in graph['callsites']}
    if r['snapshot_id']!=manifest.get('analysis_id',manifest['snapshot_id']):raise ValueError('Stale analysis baseline')
    if r['task_id'] in manifest.get('imported_review_tasks',[]):raise ValueError('Review task already imported')
    for path,h in manifest.get('input_files',{}).items():
        if filehash(path)!=h:raise ValueError('Analysis source changed; rerun analysis before review import: '+path)
    if len(r['issue_ids'])!=1 or r['issue_ids'][0] not in issues:raise ValueError('Unknown issue')
    issue=issues[r['issue_ids'][0]]
    if r['task_id']!='review_'+issue['id'] or r['input_hash']!=issue['input_hash']:raise ValueError('Stale/wrong task input')
    evidence={}
    roots=[Path(p).resolve() for p in manifest['workspace_roots']]
    for e in r['read_set']:
        p=Path(e['file']).resolve()
        if not any(p.is_relative_to(root) for root in roots):raise ValueError('Read evidence outside workspace roots')
        if filehash(p)!=e['hash']:raise ValueError('Stale read evidence: '+str(p))
        size=p.stat().st_size
        if not 0<=e['start']<e['end']<=size:raise ValueError('Invalid source interval')
        evidence[e['id']]=dict(e,text=p.read_bytes()[e['start']:e['end']].decode('utf-8',errors='replace'))
    accepted=[]
    for p in r['relation_proposals']:
        if p['callsite']!=issue['subject_id'] or p['callsite'] not in calls or p['target'] not in fs:raise ValueError('Invalid proposal endpoint')
        if not p['evidence_ids'] or any(e not in evidence for e in p['evidence_ids']):raise ValueError('Missing proposal read evidence')
        accepted.append(dict(id='agent_'+digest(p)[:24],callsite=p['callsite'],source=calls[p['callsite']]['owner'],target=p['target'],
            origin='agent',certainty='may',unknown_target_possible=True,evidence_ids=p['evidence_ids'],reason=p['reason']))
    report=dict(status='validated_structure_and_current_evidence',semantic_proof=False,accepted=len(accepted),
                configuration_action='needs_reconfigure' if r['correction_proposals'] or r['status']=='needs_configuration' else None)
    return r,accepted,list(evidence.values()),report
