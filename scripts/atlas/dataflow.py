"""Finite reaching definitions over Clang CFG; callsite-specific return summaries.

Values are definitions, never just variable names. Conditions remain CFG predicates:
no SAT feasibility, alias, overflow or loop-termination proof is claimed.
"""
from collections import defaultdict, deque
from copy import deepcopy
from .infrastructure.store import digest, filehash


def symbol(usr):
    return 's_'+digest(usr)[:24]


def union(states):
    result={}
    for state in states:
        for k,vs in state.items():result.setdefault(k,set()).update(vs)
    return result


class Solver:
    def __init__(self,ir,function,calls,evidence,step_budget):
        self.ir=ir;self.f=function;self.fid=function['id'];self.raw={n['id']:n for n in ir.get('nodes',[])}
        self.blocks={b['id']:b for b in ir.get('blocks',[])};self.limit=step_budget
        self.values={};self.returns=set();self.conditions=set();self.limitations=set()
        self.all_ops={x for b in self.blocks.values() for x in b['operations']}
        self.callmap={}
        for c in calls:
            for e in c['evidence_ids']:
                loc=evidence[e];self.callmap[(loc['file'],loc['start'])]=c
        self.parameters={symbol(p['usr']):i for i,p in enumerate(ir.get('parameters',[]))}
        self.address_taken=set()
        for n in self.raw.values():
            if n.get('operator')=='&' and len(n['children'])==1:
                v=self.lvalue(n['children'][0])
                if v:self.address_taken.add(symbol(v['usr']))

    def vid(self,n):return self.fid+':'+n

    def put(self,key,kind,sources=(),**kw):
        row=dict(id=key,owner=self.fid,kind=kind,sources=sorted(set(sources)),certainty='may',**kw)
        self.values[key]=row;return {key}

    def unknown(self,reason,n='',**kw):
        self.limitations.add(reason)
        return self.put(self.vid('unknown:'+reason+':'+n),'unknown',reason=reason,**kw)

    def readvar(self,v,state):
        sid=symbol(v['usr'])
        if v.get('function'):return self.put(self.vid('function:'+sid),'function_reference',symbol=sid)
        if not v['local'] or not v['scalar'] or v['volatile']:
            return self.unknown('memory_or_non_scalar',sid,symbol=sid)
        return state.get(sid,self.unknown_value('uninitialized',sid))

    def unknown_value(self,reason,sid):
        # Merely constructing a fallback must not mark it as used/unsupported.
        key=self.vid('unknown:'+reason+':'+sid)
        self.put(key,'unknown',reason=reason,symbol=sid)
        return {key}

    def lvalue(self,n):
        r=self.raw[n]
        if r['kind']=='DeclRefExpr':return r.get('variable')
        if r['kind'] in ('ParenExpr','ImplicitCastExpr') and r['children']:return self.lvalue(r['children'][0])
        return None

    def evaluate(self,n,state,block,force=False):
        if not n:return self.unknown('missing_expression')
        if not force and n in self.all_ops and '@'+n in state:return state['@'+n]
        r=self.raw[n];kind=r['kind'];children=r['children'];key=self.vid(n)
        common=dict(expression=r['text'],block=block,location=r['location'],native_id=n)
        def child(x):return self.evaluate(x,state,block)
        def add(k,sources=(),**kw):return self.put(key,k,sources,**common,**kw)
        def assign(v,value):
            if v and v['local'] and v['scalar'] and not v['volatile']:state[symbol(v['usr'])]=set(value)
            else:
                self.limitations.add('alias_or_global_write_not_solved')
                for sid in self.address_taken:state[sid]=self.unknown('possible_indirect_write',n)
        if kind=='DeclRefExpr':
            v=r['variable'];result=add('read',self.readvar(v,state),symbol=symbol(v['usr']),name=v['name'])
        elif kind in ('IntegerLiteral','FloatingLiteral','CharacterLiteral','CXXBoolLiteralExpr','CXXNullPtrLiteralExpr','StringLiteral'):
            result=add('constant')
        elif kind in ('ImplicitCastExpr','CStyleCastExpr','CXXStaticCastExpr','ParenExpr','ConstantExpr','ExprWithCleanups'):
            result=add('cast',child(children[-1]) if children else self.unknown('empty_cast',n))
            if kind=='ExprWithCleanups':self.limitations.add('implicit_cleanup_not_solved')
        elif kind in ('BinaryOperator','CompoundAssignOperator'):
            op=r['operator']
            if op=='=' or kind=='CompoundAssignOperator':
                v=self.lvalue(children[0]);rhs=child(children[1])
                if kind=='CompoundAssignOperator':rhs|=self.readvar(v,state) if v else self.unknown('indirect_read',n)
                result=add('assignment',rhs,operator=op,target_symbol=symbol(v['usr']) if v else None)
                assign(v,result)
            else:
                sources=set().union(*(child(c) for c in children))
                result=add('compute',sources,operator=op)
        elif kind=='UnaryOperator':
            op=r['operator'];v=self.lvalue(children[0])
            if op in ('++','--'):
                before=self.readvar(v,state) if v else self.unknown('indirect_read',n)
                updated=self.put(key+':write','assignment',before,**common,operator=op,target_symbol=symbol(v['usr']) if v else None)
                assign(v,updated);result=add('compute',before if r.get('postfix') else updated,operator=op)
            elif op in ('&','*'):
                result=add('opaque',self.unknown('pointer_operation',n),operator=op)
            else:result=add('compute',child(children[0]),operator=op)
        elif kind=='DeclStmt':
            sources=set()
            for v in r.get('declarations',[]):
                src=child(v['initializer']) if v['initializer'] else self.unknown_value('uninitialized',symbol(v['usr']))
                val=self.put(key+':'+symbol(v['usr']),'initializer',src,**common,target_symbol=symbol(v['usr']),name=v['name'])
                assign(v,val);sources|=val
            result=add('declaration',sources)
        elif kind in ('CallExpr','CXXMemberCallExpr','CXXOperatorCallExpr'):
            call=self.callmap.get((r['location']['file'],r['location']['start']))
            args=[]
            for i,a in enumerate(r.get('arguments',[])):
                aid=key+':arg'+str(i)
                self.put(aid,'call_argument',child(a),**common,callsite=call['id'] if call else None,index=i)
                args.append(aid)
            result=add('call_result',(),arguments=args,callsite=call['id'] if call else None,target_usr=r.get('target_usr'),unknown_target_possible=not call or call['dispatch']!='direct')
            for sid in self.address_taken:state[sid]=self.unknown('call_memory_effect',n,symbol=sid)
        elif kind=='ReturnStmt':
            result=add('return',child(children[0]) if children else ())
            self.returns.add(key)
        elif kind in ('ConditionalOperator','BinaryConditionalOperator'):
            # Clang evaluates each arm on its own CFG path. Only join available temps.
            values=set()
            for c in children[1:]:values.update(state.get('@'+c,()))
            result=add('conditional',values or self.unknown('conditional_value_unavailable',n))
        elif kind in ('BreakStmt','ContinueStmt','GotoStmt','NullStmt'):
            result=add('control')
        else:
            result=add('opaque',self.unknown('unsupported:'+kind,n))
        state['@'+n]=result
        return result

    def solve(self):
        if self.ir.get('status')!='ready':
            return dict(function_id=self.fid,status=self.ir.get('status','unsupported'),values=[],returns=[],conditions=[],cfg=self.ir,limitations=[self.ir.get('reason','CFG unavailable')])
        initial={}
        for p in self.ir['parameters']:
            sid=symbol(p['usr']);key=self.vid('param:'+sid)
            self.put(key,'parameter',symbol=sid,name=p['name'],index=self.parameters[sid])
            initial[sid]={key}
        preds=defaultdict(set)
        for b in self.blocks.values():
            for e in b['successors']:
                if e['reachable']:preds[e['target']].add(b['id'])
        entry=self.ir['entry'];states={};ins={};todo=deque([entry]);queued={entry};steps=0
        while todo and steps<self.limit:
            bid=todo.popleft();queued.discard(bid);steps+=1
            state=union([states[p] for p in sorted(preds[bid]) if p in states]+([initial] if bid==entry else []))
            ins[bid]=deepcopy(state);b=self.blocks[bid]
            for n in b['operations']:self.evaluate(n,state,bid,True)
            if b['condition']:
                vals=self.evaluate(b['condition'],state,bid)
                self.conditions.update(vals)
            if state!=states.get(bid):
                states[bid]=state
                for e in b['successors']:
                    if e['reachable'] and e['target'] not in queued:todo.append(e['target']);queued.add(e['target'])
        # Re-emit values once using converged IN states, not intermediate worklist states.
        self.values={};self.returns=set();self.conditions=set();self.limitations=set()
        for p in self.ir['parameters']:
            sid=symbol(p['usr']);self.put(self.vid('param:'+sid),'parameter',symbol=sid,name=p['name'],index=self.parameters[sid])
        for bid in sorted(ins):
            b=self.blocks[bid];state=deepcopy(ins[bid])
            for n in b['operations']:self.evaluate(n,state,bid,True)
            if b['condition']:self.conditions.update(self.evaluate(b['condition'],state,bid))
            if b['opaque_elements']:self.limitations.add('implicit_CFG_elements_not_solved')
        if todo:self.limitations.add('fixed_point_budget_exhausted')
        # Control dependence is deliberately conservative; keep separate from value edges.
        for rid in self.returns:self.values[rid]['control_sources']=sorted(self.conditions)
        return dict(function_id=self.fid,status='partial' if self.limitations else 'ready',values=list(self.values.values()),
                    returns=sorted(self.returns),conditions=sorted(self.conditions),cfg=self.ir,
                    limitations=sorted(self.limitations),iterations=steps,converged=not bool(todo))


def slice_values(values,starts,include_control=True):
    seen=set();q=list(starts)
    while q:
        n=q.pop()
        if n in seen:continue
        seen.add(n);r=values.get(n,{})
        q.extend(r.get('sources',[]))
        if include_control:q.extend(r.get('control_sources',[]))
    return seen


def analyze(graph,irs,store,step_budget=10000,summary_budget=128):
    ev={e['id']:e for e in graph['evidence']};functions={f['id']:f for f in graph['functions']}
    code=filehash(__file__);local={};plan=[];native_by_id={i['id']:i for i in irs}
    for fid,f in functions.items():
        ir=native_by_id.get(fid,dict(id=fid,status='not_requested',reason='CFG absent'))
        calls=[c for c in graph['callsites'] if c['owner']==fid]
        key=digest(dict(stage='reaching_defs',ir=ir,calls=calls,code=code,budget=step_budget))
        cached=store.cache_get(key)
        try:
            if not cached:raise KeyError()
            result=store.get(cached['result']);store.entries.append(cached['result']);action='reuse'
        except (KeyError,OSError,ValueError):
            result=Solver(ir,f,calls,ev,step_budget).solve()
            receipt=store.put('reaching_definitions.json',result,fid,'python_cfg_solver',key)
            if result.get('converged'):store.cache_put(key,dict(result=receipt))
            action='solve'
        local[fid]=result;plan.append(dict(function_id=fid,stage='reaching_definitions',action=action))
    values={v['id']:deepcopy(v) for r in local.values() for v in r['values']}
    targets=defaultdict(list)
    for e in graph['call_targets']:
        if e['certainty']=='exact':targets[e['callsite']].append(e['target'])
    callvalues=[v for v in values.values() if v['kind']=='call_result']
    adj={fid:set() for fid in functions}
    for v in callvalues:
        ts=targets.get(v['callsite'],[])
        if len(ts)==1 and not v['unknown_target_possible']:
            v['summary_function']=ts[0];adj[v['owner']].add(ts[0])
    # Iterative Kosaraju, then consume sink components first (callees before callers).
    visited=set();order=[]
    for start in sorted(functions):
        stack=[(start,False)]
        while stack:
            n,done=stack.pop()
            if done:order.append(n);continue
            if n in visited:continue
            visited.add(n);stack.append((n,True))
            stack.extend((t,False) for t in sorted(adj[n],reverse=True) if t not in visited)
    reverse=defaultdict(set)
    for a,ts in adj.items():
        for b in ts:reverse[b].add(a)
    visited=set();components=[]
    for start in reversed(order):
        if start in visited:continue
        members=set();todo=[start]
        while todo:
            n=todo.pop()
            if n in visited:continue
            visited.add(n);members.add(n);todo.extend(reverse[n]-visited)
        components.append(sorted(members))
    summaries_by_id={};total_iterations=0
    for component in reversed(components):
        members=set(component);external=set().union(*(adj[f] for f in members))-members
        dep_hashes={t:summaries_by_id[t]['calculation_hash'] for t in sorted(external)}
        component_calls=[v for v in callvalues if v['owner'] in members]
        key=digest(dict(stage='summary_component',locals={f:local[f] for f in component},targets={f:sorted(adj[f]) for f in component},dependencies=dep_hashes,code=code,budget=summary_budget))
        cached=store.cache_get(key)
        try:
            if not cached:raise KeyError()
            saved=store.get(cached['result']);store.entries.append(cached['result'])
            for row in saved['summaries']:summaries_by_id[row['function_id']]=row
            for row in saved['calls']:values[row['id']].update(row)
            for fid in component:plan.append(dict(function_id=fid,stage='return_summary',action='reuse',callee_hashes=dep_hashes))
            continue
        except (KeyError,OSError,ValueError):pass
        dependencies={f:set() for f in component};unknowns={f:set(local[f]['limitations']) for f in component}
        recursive=len(component)>1 or any(f in adj[f] for f in component)
        if recursive:
            for f in component:unknowns[f].add('recursive_value_not_proven')
        converged=False
        for iteration in range(summary_budget):
            total_iterations+=1
            for v in component_calls:
                src=set();reasons=set();target=v.get('summary_function')
                if not target:
                    src.update(v['arguments']);reasons.add('external_or_unresolved_return')
                elif not local[target].get('converged'):
                    src.update(v['arguments']);reasons.add('callee_CFG_unavailable')
                else:
                    deps=dependencies[target] if target in members else summaries_by_id[target]['parameter_dependencies']
                    limits=unknowns[target] if target in members else summaries_by_id[target]['limitations']
                    src.update(v['arguments'][i] for i in deps if i<len(v['arguments']))
                    reasons.update(limits)
                v['sources']=sorted(src);v['unknown_reasons']=sorted(reasons)
            changed=False
            for fid in component:
                r=local[fid];reached=slice_values(values,r['returns'])
                deps={values[n]['index'] for n in reached if n in values and values[n]['kind']=='parameter' and values[n]['owner']==fid}
                unknown={values[n].get('reason','unknown') for n in reached if n in values and values[n]['kind']=='unknown'}
                unknown.update(reason for n in reached if n in values for reason in values[n].get('unknown_reasons',[]))
                unknown.update(r['limitations'])
                if recursive:unknown.add('recursive_value_not_proven')
                if not r['returns'] and functions[fid]['return_type']!='void':unknown.add('no_return_value')
                if deps!=dependencies[fid] or unknown!=unknowns[fid]:changed=True
                dependencies[fid]=deps;unknowns[fid]=unknown
            if not changed:converged=True;break
        local_public={}
        for fid in component:
            reached=slice_values(values,local[fid]['returns'])
            local_public[fid]=digest([dict(kind=values[n]['kind'],expression=values[n].get('expression'),sources=values[n].get('sources'),control=values[n].get('control_sources'),reasons=values[n].get('unknown_reasons')) for n in sorted(reached) if n in values])
        component_hash=digest(dict(locals=local_public,callees=dep_hashes,converged=converged))
        rows=[]
        for fid in component:
            r=local[fid];limits=set(unknowns[fid])
            if not converged:limits.add('summary_budget_exhausted')
            row=dict(function_id=fid,status='partial' if limits or r['status']!='ready' else 'ready',parameter_dependencies=sorted(dependencies[fid]),
                return_values=r['returns'],calculation_hash=digest([fid,component_hash]),limitations=sorted(limits),
                converged=converged and r.get('converged',False),dependencies=dep_hashes)
            rows.append(row);summaries_by_id[fid]=row
            plan.append(dict(function_id=fid,stage='return_summary',action='solve',callee_hashes=dep_hashes,component=component))
        receipt=store.put('summary_component.json',dict(summaries=rows,calls=component_calls),digest(component),'python_cfg_solver',key)
        if all(r['converged'] for r in rows):store.cache_put(key,dict(result=receipt))
    summaries=[summaries_by_id[f] for f in sorted(functions)]
    graph['value_nodes']=list(values.values());graph['return_summaries']=summaries
    graph['cfgs']=[dict(function_id=fid,**{k:v for k,v in r['cfg'].items() if k not in ('nodes','id')},limitations=r['limitations']) for fid,r in local.items()]
    graph['dataflow_status']=dict(mode='clang_cfg',status='partial' if any(s['status']!='ready' for s in summaries) else 'ready',
      limitations=['path_feasibility_not_proven','control_dependencies_conservative','alias_not_solved','C_CPP_evaluation_order_not_exhaustive'],summary_iterations=total_iterations,converged=all(s['converged'] for s in summaries))
    store.put('dataflow_plan.json',plan);store.put('value_graph.jsonl',graph['value_nodes'])
    store.put('function_summaries.jsonl',summaries)
    return graph['dataflow_status']


def trace(graph,function,parameter=None,value=None,direction='forward',budget=2000):
    from .graph import resolve
    if budget<1:raise ValueError('budget must be positive')
    fid=resolve(graph,function);nodes={v['id']:v for v in graph.get('value_nodes',[])}
    if not nodes:raise ValueError('CFG data flow not available; run with --dataflow cfg first')
    if value:
        if value not in nodes or nodes[value]['owner']!=fid:raise ValueError('Unknown value in selected function')
        starts=[value]
    elif parameter is not None:
        starts=[v['id'] for v in nodes.values() if v['owner']==fid and v['kind']=='parameter' and parameter in (v['name'],str(v['index']),v['symbol'])]
        if len(starts)!=1:raise ValueError('Choose a unique parameter name, index or symbol')
    else:
        starts=[v['id'] for v in nodes.values() if v['owner']==fid and v['kind']=='return'];direction='backward'
    adj=defaultdict(set)
    for v in nodes.values():
        for src in v.get('sources',[])+v.get('control_sources',[]):adj[src].add(v['id'])
    callresults={v['callsite']:v for v in nodes.values() if v['kind']=='call_result' and v.get('callsite')}
    used=0;truncated=False
    def walk(seeds):
        nonlocal used,truncated
        seen=set();q=deque(seeds)
        while q and used<budget:
            n=q.popleft()
            if n in seen:continue
            seen.add(n);used+=1
            v=nodes.get(n,{})
            q.extend(sorted(adj[n] if direction=='forward' else set(v.get('sources',[])+v.get('control_sources',[]))))
        truncated|=bool(q)
        return [nodes[n] for n in sorted(seen) if n in nodes]
    selected=walk(starts);expansions=[];pending=deque();seen_tasks=set()
    def enqueue(rows,path):
        for v in rows:
            if direction=='forward' and v['kind']=='call_argument':
                call=callresults.get(v.get('callsite'));index=v['index']
            elif direction=='backward' and v['kind']=='call_result':call=v;index=None
            else:continue
            if call and call.get('summary_function'):
                key=(tuple(path),call['id'],index)
                if key not in seen_tasks:seen_tasks.add(key);pending.append((call,index,path))
    enqueue(selected,[])
    while pending and used<budget:
        call,index,path=pending.popleft();target=call['summary_function'];context=path+[call['id']]
        params=[v for v in nodes.values() if v['owner']==target and v['kind']=='parameter']
        bindings=[dict(parameter=v['id'],actual=call['arguments'][v['index']]) for v in params if v['index']<len(call['arguments'])]
        seeds=[v['id'] for v in params if v['index']==index] if direction=='forward' else [v['id'] for v in nodes.values() if v['owner']==target and v['kind']=='return']
        stop='recursion' if call['id'] in path else None
        sub=walk(seeds) if not stop else [];used+=bool(stop)
        expansions.append(dict(context=context,callsite=call.get('callsite'),function_id=target,bindings=bindings,values=sub,stop=stop,direction=direction))
        if not stop:enqueue(sub,context)
    scope={fid}|{e['function_id'] for e in expansions}
    return dict(function_id=fid,start=starts,direction=direction,values=selected,call_expansions=expansions,truncated=truncated or bool(pending),
                summaries=[s for s in graph.get('return_summaries',[]) if s['function_id'] in scope],
                status=graph.get('dataflow_status'),certainty='may',
                cfg=[c for c in graph.get('cfgs',[]) if c['function_id'] in scope],
                note='Each expansion has its own call context and formal-to-actual bindings; no alias/path-feasibility proof')
