"""Bounded field-sensitive alias and callback candidate analysis."""
from collections import defaultdict

from .infrastructure.store import digest


def analyze(by_kind,functions,calls,call_targets,objects,types):
    object_ids={row['id'] for row in objects if '*' not in row.get('type','')};function_by_base=defaultdict(list)
    for function in functions:function_by_base[function['base_id']].append(function['id'])
    aliases=defaultdict(set);certainty={}
    relations=list(by_kind['alias_relation'].values())
    for relation in relations:
        key=(relation['owner'],relation['target_symbol'])
        if relation['relation']=='address_of':aliases[key].update(relation['source_symbols'])
        certainty[key]=relation['certainty']
    edges_by_call=defaultdict(list)
    for edge in call_targets:edges_by_call[edge['callsite']].append(edge)
    changed=True;iterations=0
    while changed and iterations<64:
        changed=False;iterations+=1
        for relation in relations:
            if relation['relation']!='pointer_copy':continue
            key=(relation['owner'],relation['target_symbol']);before=len(aliases[key])
            for source in relation['source_symbols']:
                aliases[key].update(aliases[(relation['owner'],source)])
                if source in object_ids:aliases[key].add(source)
            changed|=len(aliases[key])!=before
        for call in calls:
            for edge in edges_by_call[call['id']]:
                callee=next((row for row in functions if row['id']==edge['target']),None)
                if not callee:continue
                for argument,parameter in zip(call['arguments'],callee['parameters']):
                    key=(callee['id'],parameter['id']);before=len(aliases[key])
                    for source in argument['sources']:
                        aliases[key].update(aliases[(call['owner'],source)])
                        if source in object_ids:aliases[key].add(source)
                    if len(aliases[key])!=before:
                        changed=True;certainty[key]='exact' if edge['certainty']=='exact' and len(aliases[key])==1 else 'may'
    field_accesses=[]
    for seed in by_kind['field_access_seed'].values():
        targets=set()
        for source in seed['base_symbols']:
            if source in object_ids:targets.add(source)
            targets.update(aliases[(seed['owner'],source)])
        names={row['id']:row['name'] for row in objects}
        field_accesses.append(dict(id='field_'+digest([seed['id'],sorted(targets)])[:24],owner=seed['owner'],
            object_ids=sorted(targets),field_id=seed['field_id'],field_name=seed['field_name'],
            access_paths=[names.get(target,target)+'.'+seed['field_name'] for target in sorted(targets)],
            access=seed['access'],expression=seed['expression'],certainty='exact' if len(targets)==1 else 'may',
            evidence_ids=seed['evidence_ids'],limitations=[] if len(targets)==1 else ['unresolved_or_multiple_base_objects']))
    function_targets=defaultdict(set);function_target_certainty={}
    for call in calls:
        for edge in edges_by_call[call['id']]:
            callee=next((row for row in functions if row['id']==edge['target']),None)
            if not callee:continue
            for argument,parameter in zip(call['arguments'],callee['parameters']):
                key=(callee['id'],parameter['id'])
                for base_id in argument.get('function_sources',[]):function_targets[key].update(function_by_base[base_id])
                if argument.get('function_sources'):
                    function_target_certainty[key]='exact' if edge['certainty']=='exact' and len(function_targets[key])==1 else 'may'
    field_types={field['id']:field['type'] for row in types for field in row.get('fields',[])}
    seeds_by_owner_field=defaultdict(list)
    for access in field_accesses:seeds_by_owner_field[(access['owner'],access['field_id'])].append(access)
    callbacks=[]
    for flow in by_kind['flow'].values():
        if flow['relation'] not in ('assignment','initializer') or '(*' not in field_types.get(flow['target'],''):continue
        candidates=set();candidate_exact=True
        for base_id in flow.get('function_sources',[]):candidates.update(function_by_base[base_id])
        for source in flow['sources']:
            key=(flow['owner'],source);candidates.update(function_targets[key])
            if function_targets[key] and function_target_certainty.get(key)!='exact':candidate_exact=False
        objects_for_field={obj for access in seeds_by_owner_field[(flow['owner'],flow['target'])] for obj in access['object_ids']}
        callbacks.append(dict(id='callback_'+digest([flow['id'],sorted(candidates)])[:24],owner=flow['owner'],field_id=flow['target'],
            object_ids=sorted(objects_for_field),candidate_function_ids=sorted(candidates),certainty='exact' if len(candidates)==1 and candidate_exact else 'may',
            evidence_ids=flow['evidence_ids'],limitations=[] if len(candidates)==1 and candidate_exact else ['candidate_set_not_unique_or_empty']))
    ownership=[]
    events_by_owner=defaultdict(list)
    for event in by_kind['lock_event'].values():events_by_owner[event['owner']].append(event)
    for owner,events in sorted(events_by_owner.items()):
        acquired=set();released=set();unresolved=set()
        for event in events:
            resolved=set()
            for lock_id in event['lock_ids']:
                if lock_id in object_ids:resolved.add(lock_id)
                resolved.update(aliases[(owner,lock_id)])
                if lock_id not in object_ids and not aliases[(owner,lock_id)]:unresolved.add(lock_id)
            (acquired if event['action']=='acquire' else released).update(resolved)
        ownership.append(dict(function_id=owner,acquired_lock_ids=sorted(acquired),released_lock_ids=sorted(released),
                              unresolved_lock_symbols=sorted(unresolved),status='partial' if unresolved else 'ready',
                              limitations=['caller_critical_region_not_expanded']))
    summaries=[dict(owner=owner,symbol=symbol,object_ids=sorted(targets),certainty=certainty.get((owner,symbol),'may'))
               for (owner,symbol),targets in sorted(aliases.items()) if targets]
    return dict(alias_relations=relations,alias_summaries=summaries,field_accesses=field_accesses,
                callback_targets=callbacks,lock_ownership_summaries=ownership,alias_status=dict(status='ready',iterations=iterations,
                    limitations=['single_level_fields','flow_insensitive_local_aliases','casts_and_arrays_not_solved']))


def query(graph,object_name=None,function_name=None):
    functions={row['id']:row['name'] for row in graph.get('functions',[])}
    owners={fid for fid,name in functions.items() if not function_name or function_name in (fid,name)}
    objects={row['id'] for row in graph.get('objects',[]) if not object_name or object_name in (row['id'],row['name'])}
    fields=[row for row in graph.get('field_accesses',[]) if row['owner'] in owners and (not object_name or set(row['object_ids'])&objects)]
    return dict(status=graph.get('alias_status',{}),aliases=[row for row in graph.get('alias_summaries',[]) if row['owner'] in owners],
                field_accesses=fields,callback_targets=[row for row in graph.get('callback_targets',[]) if row['owner'] in owners],
                lock_ownership=[row for row in graph.get('lock_ownership_summaries',[]) if row['function_id'] in owners],
                selection=dict(object=object_name,function=function_name,matched_fields=len(fields)))
