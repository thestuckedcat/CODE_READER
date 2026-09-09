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
            object_ids=sorted(targets),field_id=seed['field_id'],field_name=seed['field_name'],field_path=seed.get('field_path',[seed['field_name']]),
            access_paths=[names.get(target,target)+'.'+'.'.join(seed.get('field_path',[seed['field_name']])) for target in sorted(targets)],
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
        candidates=set();candidate_exact=not bool(flow.get('guards'))
        for base_id in flow.get('function_sources',[]):candidates.update(function_by_base[base_id])
        for source in flow['sources']:
            key=(flow['owner'],source);candidates.update(function_targets[key])
            if function_targets[key] and function_target_certainty.get(key)!='exact':candidate_exact=False
        objects_for_field={obj for access in seeds_by_owner_field[(flow['owner'],flow['target'])] for obj in access['object_ids']}
        expression=flow.get('expression','').strip();action='clear' if expression in ('0','NULL','nullptr') else 'set'
        callbacks.append(dict(id='callback_'+digest([flow['id'],sorted(candidates)])[:24],owner=flow['owner'],field_id=flow['target'],
            object_ids=sorted(objects_for_field),action=action,expression=expression,guards=flow.get('guards',[]),candidate_function_ids=sorted(candidates),certainty='exact' if (action=='clear' or len(candidates)==1) and candidate_exact else 'may',
            evidence_ids=flow['evidence_ids'],limitations=[] if candidate_exact and (action=='clear' or len(candidates)==1) else ['candidate_set_not_unique_or_empty']))
    callback_states=[];callback_groups=defaultdict(list);evidence={row['id']:row for row in by_kind['evidence'].values()}
    callbacks.sort(key=lambda event:min((evidence[eid]['start'] for eid in event['evidence_ids'] if eid in evidence),default=0))
    for callback in callbacks:callback_groups[(callback['owner'],tuple(callback['object_ids']),callback['field_id'])].append(callback)
    for (owner,object_key,field_id),events in callback_groups.items():
        def callback_position(event):return min((evidence[eid]['start'] for eid in event['evidence_ids'] if eid in evidence),default=0)
        current=set();last=None;uncertain=False
        for event in sorted(events,key=callback_position):
            event['supersedes_event_id']=last if event['certainty']=='exact' else None
            if event['certainty']!='exact':uncertain=True;current.update(event['candidate_function_ids'])
            elif event['action']=='clear':current.clear()
            else:current=set(event['candidate_function_ids'])
            last=event['id']
        status='may_multiple' if uncertain else 'cleared' if not current else 'configured'
        callback_states.append(dict(owner=owner,object_ids=list(object_key),field_id=field_id,status=status,
                                    candidate_function_ids=sorted(current),last_event_id=last,
                                    certainty='may' if uncertain else 'exact'))
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
                              limitations=['simple_callsite_projection_only']))
    # Resolve parameter lock symbols and project net lock/unlock wrappers to
    # exact callsites. This is deliberately intraprocedural after projection:
    # no scheduler or whole-program happens-before relation is inferred.
    raw_events=list(by_kind['lock_event'].values());raw_regions=list(by_kind['lock_region'].values())
    raw_accesses=[dict(row) for row in by_kind['shared_access'].values()]
    def resolved(owner,symbol):
        targets=set(aliases[(owner,symbol)])
        if symbol in object_ids:targets.add(symbol)
        return targets or {symbol}
    normalized_events=[]
    for event in raw_events:
        row=dict(event);row['lock_ids']=sorted({target for symbol in event['lock_ids'] for target in resolved(event['owner'],symbol)})
        normalized_events.append(row)
    normalized_regions=[]
    for region in raw_regions:
        for lock_id in resolved(region['owner'],region['lock_id']):
            row=dict(region);row['id']=region['id']+'_'+digest(lock_id)[:8];row['lock_id']=lock_id;normalized_regions.append(row)
    for access in raw_accesses:
        access['held_lock_ids']=sorted({target for symbol in access['held_lock_ids'] for target in resolved(access['owner'],symbol)})
    raw_by_owner=defaultdict(list)
    for event in raw_events:raw_by_owner[event['owner']].append(event)
    net_actions=defaultdict(list)
    for owner,events in raw_by_owner.items():
        stacks=defaultdict(list)
        def position(event):
            return min((evidence[eid]['start'] for eid in event['evidence_ids'] if eid in evidence),default=0)
        for event in sorted(events,key=position):
            for symbol in event['lock_ids']:
                if event['action']=='acquire':stacks[symbol].append(event)
                elif stacks[symbol]:stacks[symbol].pop()
                else:net_actions[owner].append((symbol,'release',event['certainty']))
        for symbol,stack in stacks.items():
            for event in stack:net_actions[owner].append((symbol,'acquire',event['certainty']))
    functions_by_id={row['id']:row for row in functions};calls_by_id={row['id']:row for row in calls};propagated=[]
    for edge in call_targets:
        call=calls_by_id.get(edge['callsite']);callee=functions_by_id.get(edge['target'])
        if not call or not callee:continue
        parameter_index={row['id']:row['index'] for row in callee['parameters']}
        for symbol,action,summary_certainty in net_actions[callee['id']]:
            if symbol in parameter_index and parameter_index[symbol]<len(call['arguments']):
                argument=call['arguments'][parameter_index[symbol]];actual=set()
                for source in argument['sources']:
                    actual.update(resolved(call['owner'],source))
            elif symbol in object_ids:actual={symbol}
            else:continue
            if not actual:continue
            certainty_value='exact' if edge['certainty']=='exact' and summary_certainty=='exact' and len(actual)==1 else 'may'
            propagated.append(dict(id='lock_call_'+digest([call['id'],callee['id'],symbol,action,sorted(actual)])[:24],
                kind='lock_event',owner=call['owner'],action=action,api='summary:'+callee['display_name'],lock_ids=sorted(actual),
                certainty=certainty_value,guards=call.get('guards',[]),limitations=['projected_from_callee_net_lock_summary'],
                evidence_ids=call['evidence_ids'],propagated_from=callee['id']))
    propagated_regions=[];projected_by_owner=defaultdict(list)
    for event in propagated:projected_by_owner[event['owner']].append(event)
    for owner,events in projected_by_owner.items():
        stacks=defaultdict(list)
        def position(event):return min((evidence[eid]['start'] for eid in event['evidence_ids'] if eid in evidence),default=0)
        for event in sorted(events,key=position):
            offset=position(event)
            for lock_id in event['lock_ids']:
                if event['action']=='acquire':stacks[lock_id].append((event,offset))
                elif stacks[lock_id]:
                    start,start_offset=stacks[lock_id].pop();certainty_value='exact' if start['certainty']=='exact' and event['certainty']=='exact' else 'may'
                    propagated_regions.append(dict(id='region_call_'+digest([start['id'],event['id'],lock_id])[:24],kind='lock_region',
                        owner=owner,lock_id=lock_id,acquire_event_id=start['id'],release_event_id=event['id'],
                        start_offset=start_offset,end_offset=offset,certainty=certainty_value,
                        evidence_ids=sorted(set(start['evidence_ids']+event['evidence_ids'])),limitations=['projected_wrapper_region','no_happens_before_proof']))
    for access in raw_accesses:
        offset=min((evidence[eid]['start'] for eid in access['evidence_ids'] if eid in evidence),default=-1)
        access['held_lock_ids']=sorted(set(access['held_lock_ids'])|{region['lock_id'] for region in propagated_regions
            if region['owner']==access['owner'] and region['start_offset']<=offset<=region['end_offset']})
    from .concurrency import summarize as summarize_concurrency
    object_map={row['id']:row for row in objects}
    resolved_concurrency=summarize_concurrency(object_map,normalized_events+propagated,normalized_regions+propagated_regions,raw_accesses)
    summaries=[dict(owner=owner,symbol=symbol,object_ids=sorted(targets),certainty=certainty.get((owner,symbol),'may'))
               for (owner,symbol),targets in sorted(aliases.items()) if targets]
    return dict(alias_relations=relations,alias_summaries=summaries,field_accesses=field_accesses,
                callback_targets=callbacks,callback_states=callback_states,lock_ownership_summaries=ownership,alias_status=dict(status='ready',iterations=iterations,
                    limitations=['flow_insensitive_local_aliases','casts_arrays_and_pointer_arithmetic_not_solved']),
                **resolved_concurrency)


def query(graph,object_name=None,function_name=None):
    functions={row['id']:row['name'] for row in graph.get('functions',[])}
    owners={fid for fid,name in functions.items() if not function_name or function_name in (fid,name)}
    objects={row['id'] for row in graph.get('objects',[]) if not object_name or object_name in (row['id'],row['name'])}
    fields=[row for row in graph.get('field_accesses',[]) if row['owner'] in owners and (not object_name or set(row['object_ids'])&objects)]
    return dict(status=graph.get('alias_status',{}),aliases=[row for row in graph.get('alias_summaries',[]) if row['owner'] in owners],
                field_accesses=fields,callback_targets=[row for row in graph.get('callback_targets',[]) if row['owner'] in owners],
                callback_states=[row for row in graph.get('callback_states',[]) if row['owner'] in owners],
                lock_ownership=[row for row in graph.get('lock_ownership_summaries',[]) if row['function_id'] in owners],
                selection=dict(object=object_name,function=function_name,matched_fields=len(fields)))
