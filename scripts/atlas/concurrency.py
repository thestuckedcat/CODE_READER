"""Conservative lockset comparison for shared-state access sites."""
from collections import defaultdict
from itertools import combinations

from .infrastructure.store import digest


def summarize(objects,events,regions,accesses):
    lock_ids={lock for event in events for lock in event['lock_ids']}
    locks=[]
    for lock_id in sorted(lock_ids):
        obj=objects.get(lock_id,{})
        locks.append(dict(id=lock_id,name=obj.get('name',lock_id),type=obj.get('type'),
                          evidence_ids=obj.get('evidence_ids',[])))
    grouped=defaultdict(list)
    for access in accesses:grouped[access['object_id']].append(access)
    findings=[];summaries=[]
    for object_id,sites in sorted(grouped.items()):
        conflicts=[]
        for left,right in combinations(sites,2):
            if left['access']=='read' and right['access']=='read':continue
            common=sorted(set(left['held_lock_ids'])&set(right['held_lock_ids']))
            relation='serialized_by_common_lock' if common else 'potentially_parallel_conflict'
            row=dict(id='parallel_'+digest([left['id'],right['id']])[:24],object_id=object_id,
                     left_access_id=left['id'],right_access_id=right['id'],relation=relation,
                     common_lock_ids=common,certainty='exact' if common else 'may',
                     evidence_ids=sorted(set(left['evidence_ids']+right['evidence_ids'])),
                     limitations=['thread_reachability_not_proven','no_happens_before_proof'])
            findings.append(row);conflicts.append(row)
        unprotected=[row for row in conflicts if row['relation']=='potentially_parallel_conflict']
        status='potential_race' if unprotected else 'protected_by_common_lock' if conflicts else 'insufficient_multiple_access_sites'
        obj=objects.get(object_id,{})
        summaries.append(dict(object_id=object_id,name=obj.get('name',object_id),access_count=len(sites),
                              conflict_pair_count=len(conflicts),unprotected_pair_count=len(unprotected),status=status,
                              certainty='may' if unprotected or not conflicts else 'exact',
                              limitations=['static_analysis_does_not_prove_runtime_parallelism']))
    return dict(locks=locks,lock_events=events,lock_regions=regions,shared_accesses=accesses,
                concurrency_findings=findings,shared_state_summaries=summaries,
                concurrency_status=dict(status='ready',model='lexical_common_lock',
                    limitations=['thread_reachability_not_proven','no_happens_before_proof','condition_variables_not_modeled']))


def analyze(by_kind):
    return summarize(by_kind['object'],list(by_kind['lock_event'].values()),
                     list(by_kind['lock_region'].values()),list(by_kind['shared_access'].values()))


def query(graph,object_name=None,lock_name=None):
    object_ids={row['object_id'] for row in graph.get('shared_state_summaries',[])
                if not object_name or object_name in (row['object_id'],row.get('name'))}
    lock_ids={row['id'] for row in graph.get('locks',[])
              if not lock_name or lock_name in (row['id'],row.get('name'))}
    if lock_name:
        protected={row['object_id'] for row in graph.get('shared_accesses',[]) if set(row['held_lock_ids'])&lock_ids}
        object_ids&=protected
    return dict(
        status=graph.get('concurrency_status',{}),
        locks=[row for row in graph.get('locks',[]) if row['id'] in lock_ids],
        lock_events=[row for row in graph.get('lock_events',[]) if set(row['lock_ids'])&lock_ids],
        lock_regions=[row for row in graph.get('lock_regions',[]) if row['lock_id'] in lock_ids],
        shared_state=[row for row in graph.get('shared_state_summaries',[]) if row['object_id'] in object_ids],
        accesses=[row for row in graph.get('shared_accesses',[]) if row['object_id'] in object_ids],
        findings=[row for row in graph.get('concurrency_findings',[]) if row['object_id'] in object_ids],
        selection=dict(object=object_name,lock=lock_name,matched_objects=len(object_ids),matched_locks=len(lock_ids)),
    )
