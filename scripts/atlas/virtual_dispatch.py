"""Evidence-bounded C++ virtual target enumeration."""
from collections import defaultdict


def analyze(functions,types,calls):
    """Return candidate method base IDs and whether the set is language-closed.

    A non-final C++ class remains open even when every currently observed
    derived class is known.  This module never treats workspace enumeration as
    a whole-program proof.
    """
    type_rows={row['base_id']:row for row in types if row.get('base_id')}
    children=defaultdict(set)
    for row in type_rows.values():
        for parent in row.get('base_type_ids',[]):children[parent].add(row['base_id'])
    descendants={}
    for root in type_rows:
        seen=set();pending=list(children[root])
        while pending:
            child=pending.pop()
            if child in seen:continue
            seen.add(child);pending.extend(children[child])
        descendants[root]=seen
    methods_by_base=defaultdict(list)
    for function in functions:methods_by_base[function['base_id']].append(function)
    resolutions={}
    for call in calls:
        if call.get('dispatch')!='virtual':
            call['virtual_candidate_set']='static_exact' if call.get('virtual_qualified') else 'not_virtual'
            continue
        referenced=methods_by_base.get(call.get('target_base'),[])
        method=referenced[0] if referenced else None
        owner=call.get('static_receiver_type_base') or (method or {}).get('owning_type_base')
        method_name=(method or {}).get('name') or call.get('virtual_method_name')
        parameter_types=tuple(parameter['type'] for parameter in method['parameters']) if method else tuple(call.get('virtual_parameter_types',[]))
        if not method_name or not owner:
            resolutions[call['id']]=dict(candidate_base_ids=[call['target_base']] if call.get('target_base') else [],
                candidate_set_status='unresolved',unknown_target_possible=True,
                limitations=['virtual_method_or_receiver_type_not_resolved'])
            continue
        key=(method_name,parameter_types)
        allowed={owner}|descendants.get(owner,set())
        candidates={function['base_id'] for function in functions
                    if function.get('owning_type_base') in allowed and function.get('is_virtual')
                    and (function['name'],tuple(parameter['type'] for parameter in function['parameters']))==key}
        if method and not method.get('is_pure_virtual'):candidates.add(method['base_id'])
        closed=call.get('virtual_method_final') or (method or {}).get('is_final') or type_rows.get(owner,{}).get('is_final')
        status='closed_by_final' if closed else 'open_world'
        if closed and method:candidates={method['base_id']}
        resolutions[call['id']]=dict(candidate_base_ids=sorted(candidates),candidate_set_status=status,
            unknown_target_possible=not closed,
            limitations=[] if closed else ['external_or_unparsed_derived_types_may_add_targets','override_matching_is_signature_bounded'])
    return resolutions
