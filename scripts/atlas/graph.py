"""Deterministic graph assembly; candidates never silently become exact."""
from collections import defaultdict,deque
from .infrastructure.store import digest

def merge(results):
    by_kind=defaultdict(dict)
    for result in results:
        for f in result['facts']:by_kind[f['kind']][f['id']]=dict(f)
    fs=list(by_kind['function'].values()); index=defaultdict(list)
    for f in fs:index[f['base_id']].append(f)
    calls=list(by_kind['callsite'].values());edges=[];issues=[];flows=list(by_kind['flow'].values());types=list(by_kind['type'].values())
    from .virtual_dispatch import analyze as analyze_virtual_dispatch
    virtual_resolutions=analyze_virtual_dispatch(fs,types,calls)
    def issue(c,kind,reason):
        row=dict(id='i_'+digest([c['id'],kind])[:24],kind=kind,subject_id=c['id'],uncertain_properties=['target'],reason=reason,
                 evidence_ids=c['evidence_ids'],affected_scope=c.get('owner'),blocking=False,next_action='review' if kind=='semantic_unresolved' else 'stop_at_boundary',status='unresolved',input_hash=digest(c))
        issues.append(row);return row['id']
    for c in calls:
        resolution=virtual_resolutions.get(c['id'])
        candidate_bases=resolution['candidate_base_ids'] if resolution else [c.get('target_base')]
        targets=[]
        for candidate_base in candidate_bases:
            variants=index.get(candidate_base,[])
            local=[f for f in variants if set(f.get('tu_ids',[]))&set(c.get('tu_ids',[]))]
            same_build=[f for f in variants if f.get('build_id')==c.get('build_id')]
            targets.extend(local or same_build or variants)
        if resolution:c.update(virtual_candidate_set=resolution['candidate_set_status'],unknown_target_possible=resolution['unknown_target_possible'],virtual_limitations=resolution['limitations'])
        if c.get('boundary_kind'):targets=[]
        if not targets:
            c['review_issue_ids']=[issue(c,'external_boundary' if c['dispatch']=='direct' else 'semantic_unresolved',
                'Stop at '+c['boundary_kind'] if c.get('boundary_kind') else 'Implementation not found in analyzed workspace' if c['dispatch']=='direct' else 'Indirect target requires registration/alias evidence')]
        elif c.get('virtual_candidate_set') in ('open_world','unresolved') or len(targets)>1:
            c['review_issue_ids']=[issue(c,'semantic_unresolved','Dispatch or definition variant has additional possible targets')]
        for f in targets:
            exact=len(targets)==1 and (c['dispatch']=='direct' or c.get('virtual_candidate_set')=='closed_by_final')
            edges.append(dict(id='edge_'+digest([c['id'],f['id']])[:24],callsite=c['id'],source=c['owner'],target=f['id'],
                              origin='deterministic_analysis',certainty='exact' if exact else 'may',
                              candidate_set_status=c.get('virtual_candidate_set','not_virtual'),evidence_ids=c['evidence_ids']))
            for a,p in zip(c['arguments'],f['parameters']):
                flows.append(dict(id='bind_'+digest([c['id'],f['id'],a['index']])[:24],owner=c['owner'],sources=a['sources'],target=p['id'],
                    expression=a['expression'],relation='argument_binding',certainty='may',origin='deterministic_analysis',evidence_ids=a['evidence_ids'],callsite=c['id'],limitations=['path_insensitive','alias_not_solved']))
    objects=list(by_kind['object'].values());objids={o['id'] for o in objects if o['lifetime']=='static'}
    states=[dict(id='state_'+f['id'],object_id=f['target'],owner=f['owner'],kind='write_or_initialize',evidence_ids=f['evidence_ids'],certainty='may') for f in flows if f['target'] in objids]
    states += [dict(id='state_'+r['id'],object_id=r['target'],owner=r['owner'],kind='reference',evidence_ids=r['evidence_ids'],certainty='exact') for r in by_kind['reference'].values() if r['target'] in objids]
    from .aliasing import analyze as analyze_aliases
    aliases=analyze_aliases(by_kind,fs,calls,edges,objects,types)
    return dict(functions=fs,types=types,objects=objects,callsites=calls,call_targets=edges,flow_edges=flows,state_events=states,
                annotations=[],evidence=list(by_kind['evidence'].values()),issues=issues,agent_supplements=[],**aliases)

def resolve(graph,name):
    found=[f for f in graph['functions'] if name in (f['id'],f['name'],f['display_name'])]
    if len(found)!=1:raise ValueError('Choose one function ID: '+str([dict(id=f['id'],name=f['display_name']) for f in found]))
    return found[0]['id']

def trace(graph,start,direction='down',depth=30,budget=5000):
    if depth<1 or budget<1:raise ValueError('depth and budget must be positive')
    start=resolve(graph,start);adj=defaultdict(list)
    for e in graph['call_targets']:
        a,b=(e['source'],e['target']) if direction=='down' else (e['target'],e['source'])
        adj[a].append((b,e['callsite']))
    paths=[];q=deque([((start,),())]);truncated=False
    boundaries=defaultdict(list)
    for boundary in graph.get('boundaries',[]):boundaries[boundary['owner']].append(boundary)
    while q and len(paths)<budget:
        path,sites=q.popleft();n=path[-1];targets=sorted(set(adj[n]))
        if direction=='down':
            for boundary in boundaries[n]:
                if len(paths)>=budget:truncated=True;break
                paths.append(dict(nodes=path,callsites=sites+(boundary['callsite'],),stop=boundary['kind'],boundary=boundary))
        if len(paths)>=budget:
            truncated|=bool(targets or q);break
        if len(path)>=depth and targets:
            paths.append(dict(nodes=path,callsites=sites,stop='depth'));truncated=True;continue
        if not targets:
            if direction=='up' or not boundaries[n]:paths.append(dict(nodes=path,callsites=sites,stop='no_known_callers' if direction=='up' else 'leaf_in_analyzed_graph'))
            continue
        for t,site in targets:
            if len(q)+len(paths)>=budget:truncated=True;continue
            if t in path:paths.append(dict(nodes=path+(t,),callsites=sites+(site,),stop='recursion'))
            else:q.append((path+(t,),sites+(site,)))
    truncated|=bool(q)
    prefix=[]
    if paths:
        for values in zip(*(p['nodes'] for p in paths)):
            if len(set(values))!=1:break
            prefix.append(values[0])
    choices=sorted({p['nodes'][len(prefix)] for p in paths if len(p['nodes'])>len(prefix)})
    return dict(start=start,direction=direction,paths=paths,common_prefix=prefix,first_divergence_choices=choices,truncated=truncated,
                top_functions=sorted({p['nodes'][-1] for p in paths if p['stop']=='no_known_callers'}),
                coverage=graph.get('coverage',{}),completeness='within_analyzed_graph_only',unknown_issue_ids=[i['id'] for i in graph['issues'] if i['kind']=='semantic_unresolved'])

def flow_trace(graph,symbol,budget=2000):
    adj=defaultdict(list)
    for e in graph['flow_edges']:
        for s in e['sources']:adj[s].append(e)
    q=deque([symbol]);seen={symbol};edges={}
    while q and len(edges)<budget:
        for e in adj[q.popleft()]:
            edges[e['id']]=e
            if e['target'] not in seen:seen.add(e['target']);q.append(e['target'])
    return dict(start=symbol,edges=list(edges.values()),truncated=bool(q),certainty='may',limitations=['path_insensitive','alias_not_solved','call_return_computation_partial'])
