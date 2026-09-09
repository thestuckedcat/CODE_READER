"""Clang C API extraction. No regex is used to establish a call target."""
from pathlib import Path
from .infrastructure.store import digest, filehash
FUNCTIONS={'FUNCTION_DECL','CXX_METHOD','CONSTRUCTOR','DESTRUCTOR','CONVERSION_FUNCTION','FUNCTION_TEMPLATE'}
TYPES={'STRUCT_DECL','CLASS_DECL','UNION_DECL','ENUM_DECL','TYPEDEF_DECL','TYPE_ALIAS_DECL'}
BRANCHES={'IF_STMT','SWITCH_STMT','FOR_STMT','WHILE_STMT','DO_STMT','CONDITIONAL_OPERATOR'}
LOCK_ACQUIRE_NAMES={'lock','try_lock','pthread_mutex_lock','pthread_mutex_trylock','mtx_lock','spin_lock','read_lock','write_lock'}
LOCK_RELEASE_NAMES={'unlock','pthread_mutex_unlock','mtx_unlock','spin_unlock','read_unlock','write_unlock'}

def extract(unit,roots,rules=None):
    from .boundaries import classify
    rules=rules or {}
    from clang import cindex as cx
    tu=cx.Index.create().parse(unit['file'],args=unit['arguments'],options=cx.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
    diagnostics=[dict(severity=d.severity,message=d.spelling,file=str(d.location.file) if d.location.file else None,
                      line=d.location.line,column=d.location.column) for d in tu.diagnostics]
    # A parse with errors cannot contribute compiler-exact relationships.
    if any(d['severity']>=3 for d in diagnostics):
        return dict(facts=[],ir=[],diagnostics=diagnostics,dependencies={unit['file']:filehash(unit['file'])},status='failed')
    sources={};hashes={};facts=[];ir=[];evidence={};seen=set()
    def inside(c):
        if not c.location.file:return False
        p=Path(str(c.location.file)).resolve()
        return not classify(p,roots,rules) and any(p.is_relative_to(r) for r in roots)
    def raw(c):
        if not c.extent.start.file:return ''
        p=str(Path(str(c.extent.start.file)).resolve())
        if p not in sources:
            try:sources[p]=Path(p).read_bytes()
            except OSError:sources[p]=b''
        return sources[p][c.extent.start.offset:c.extent.end.offset].decode('utf-8',errors='replace')
    def anchor(c):
        p=str(Path(str(c.location.file)).resolve()) if c.location.file else unit['file']
        if p not in hashes:hashes[p]=filehash(p)
        a=dict(file=p,hash=hashes[p],start=c.extent.start.offset,end=c.extent.end.offset,line=c.location.line,column=c.location.column)
        key='e_'+digest(a)[:24]
        evidence[key]=dict(id=key,**a,text=raw(c)[:16000]);return key
    def base(c):
        u=c.get_usr()
        return 's_'+digest(u or [str(c.location.file),c.location.offset,c.kind.name,c.spelling])[:24]
    def var(c):return base(c)
    def put(kind,c,**kw):
        rec=dict(kind=kind,evidence_ids=[anchor(c)],origin='compiler',tu_ids=[unit['id']],build_id=unit.get('build_id'),**kw)
        if rec.get('id') not in seen: facts.append(rec);seen.add(rec.get('id'))
        return rec
    def refs(c):
        result=set()
        def walk(n):
            if n.kind.name in ('DECL_REF_EXPR','MEMBER_REF_EXPR') and n.referenced:
                if n.referenced.kind.name not in FUNCTIONS:result.add(var(n.referenced))
            for ch in n.get_children():walk(ch)
        walk(c);return sorted(result)
    def function_refs(c):
        result=set()
        def walk(n):
            if n.kind.name in ('DECL_REF_EXPR','MEMBER_REF_EXPR') and n.referenced and n.referenced.kind.name in FUNCTIONS:
                result.add(base(n.referenced))
            for child in n.get_children():walk(child)
        walk(c);return sorted(result)
    def descendants(c):
        for child in c.get_children():
            yield child
            yield from descendants(child)
    def shared_decl(c):
        ref=c.referenced
        if not ref or ref.kind.name!='VAR_DECL':return None
        parent=ref.semantic_parent
        return ref if ref.storage_class.name=='STATIC' or not parent or parent.kind.name not in FUNCTIONS else None
    def lock_decl(c):
        ref=c.referenced
        return ref if ref and ref.kind.name in ('VAR_DECL','PARM_DECL') else None
    def lock_action(c):
        ref=c.referenced
        name=(ref.spelling if ref else c.spelling or '').lower()
        if name in LOCK_RELEASE_NAMES or name.endswith(('_mutex_unlock','_spin_unlock')):return 'release',name
        if name in LOCK_ACQUIRE_NAMES or name.endswith(('_mutex_lock','_mutex_trylock','_spin_lock')):return 'acquire',name
        return None,name
    def analyze_concurrency(function,owner):
        """Extract lexical lock regions and shared accesses from compiler cursors.

        This deliberately proves only a common lexical lock.  It does not infer
        thread creation, scheduler ordering, condition-variable semantics, or a
        whole-program happens-before relation.
        """
        nodes=list(descendants(function));events=[];lock_call_ranges=[];lock_ids=set()
        for call in (n for n in nodes if n.kind.name=='CALL_EXPR'):
            action,api=lock_action(call)
            if not action:continue
            referenced={}
            for node in descendants(call):
                declaration=lock_decl(node)
                if declaration is not None:referenced[var(declaration)]=declaration
            if not referenced:continue
            lids=sorted(referenced);lock_ids.update(lids)
            eid='lock_'+digest([owner,anchor(call),action,lids])[:24]
            event_certainty='may' if 'try' in api else 'exact'
            put('lock_event',call,id=eid,owner=owner,action=action,api=api,lock_ids=lids,
                certainty=event_certainty,guards=[],limitations=['lexical_lockset_only'])
            events.append(dict(id=eid,cursor=call,action=action,locks=lids,offset=call.extent.start.offset,certainty=event_certainty))
            lock_call_ranges.append((call.extent.start.offset,call.extent.end.offset))
        # Recognize common C++ RAII guards. Their destructor is represented as a
        # scope-end release rather than an invented source call.
        for decl in (n for n in nodes if n.kind.name=='VAR_DECL' and any(x in n.type.spelling for x in ('lock_guard<','unique_lock<','scoped_lock<'))):
            referenced={}
            for node in descendants(decl):
                declaration=lock_decl(node)
                if declaration is not None:referenced[var(declaration)]=declaration
            for lid in list(referenced):
                if lid==var(decl):referenced.pop(lid)
            if not referenced:continue
            lids=sorted(referenced);lock_ids.update(lids);eid='lock_'+digest([owner,anchor(decl),'raii',lids])[:24]
            put('lock_event',decl,id=eid,owner=owner,action='acquire',api=decl.type.spelling,lock_ids=lids,
                certainty='exact',guards=[],limitations=['raii_release_at_lexical_scope_end'])
            scopes=[node.extent.end.offset for node in nodes if node.kind.name=='COMPOUND_STMT' and node.extent.start.offset<=decl.extent.start.offset<node.extent.end.offset]
            events.append(dict(id=eid,cursor=decl,action='acquire',locks=lids,offset=decl.extent.start.offset,
                               raii=True,implicit_end=min(scopes) if scopes else function.extent.end.offset))
        events.sort(key=lambda row:row['offset']);stacks={};regions=[]
        for event in events:
            for lid in event['locks']:
                stack=stacks.setdefault(lid,[])
                if event['action']=='acquire':stack.append(event)
                elif stack:
                    start=stack.pop();regions.append((lid,start,event,start.get('certainty','exact'),event['offset']))
        for lid,stack in stacks.items():
            for start in stack:regions.append((lid,start,None,'exact' if start.get('raii') else 'may',start.get('implicit_end',function.extent.end.offset)))
        function_end=function.extent.end.offset
        for lid,start,end,certainty,end_offset in regions:
            rid='region_'+digest([owner,lid,start['id'],end['id'] if end else end_offset])[:24]
            put('lock_region',start['cursor'],id=rid,owner=owner,lock_id=lid,acquire_event_id=start['id'],
                release_event_id=end['id'] if end else None,start_offset=start['offset'],
                end_offset=end_offset,certainty=certainty,
                limitations=['lexical_region','no_happens_before_proof'])
        write_ranges=[]
        for operation in nodes:
            if operation.kind.name in ('BINARY_OPERATOR','COMPOUND_ASSIGNMENT_OPERATOR'):
                children=list(operation.get_children())
                if len(children)<2:continue
                start=children[0].extent.end.offset;end=children[1].extent.start.offset
                tokens=[t.spelling for t in operation.get_tokens() if start<=t.location.offset<end]
                if any(x in ('=','+=','-=','*=','/=','|=','&=','^=','<<=','>>=','%=') for x in tokens):
                    write_ranges.append((children[0].extent.start.offset,children[0].extent.end.offset))
            elif operation.kind.name=='UNARY_OPERATOR':
                tokens={t.spelling for t in operation.get_tokens()}
                if tokens&{'++','--'}:write_ranges.append((operation.extent.start.offset,operation.extent.end.offset))
        seen_access=set()
        for refnode in (n for n in nodes if n.kind.name in ('DECL_REF_EXPR','MEMBER_REF_EXPR')):
            declaration=shared_decl(refnode)
            if declaration is None:continue
            oid=var(declaration);offset=refnode.extent.start.offset
            if oid in lock_ids or any(start<=offset<=end for start,end in lock_call_ranges):continue
            key=(oid,refnode.extent.start.offset,refnode.extent.end.offset)
            if key in seen_access:continue
            seen_access.add(key)
            held=sorted({lid for lid,start,end,_,end_offset in regions if start['offset']<=offset<=end_offset})
            access='write' if any(start<=offset<=end for start,end in write_ranges) else 'read'
            put('shared_access',refnode,id='access_'+digest([owner,anchor(refnode),oid,access])[:24],owner=owner,
                object_id=oid,access=access,held_lock_ids=held,certainty='may' if not held else 'exact',
                limitations=['lexical_lockset_only','thread_reachability_not_proven'])
    def analyze_aliases(function,owner):
        """Record bounded pointer copies and single-level field access seeds."""
        nodes=list(descendants(function));write_ranges=[]
        def variables(node):
            found={}
            for item in (node,*descendants(node)):
                ref=item.referenced
                if ref and ref.kind.name in ('VAR_DECL','PARM_DECL'):found[var(ref)]=ref
            return found
        def pointer(declaration):
            return declaration is not None and ('*' in declaration.type.spelling or declaration.type.kind.name in ('POINTER','BLOCKPOINTER','MEMBERPOINTER'))
        def addresses(node):
            found={}
            for item in (node,*descendants(node)):
                if item.kind.name!='UNARY_OPERATOR' or '&' not in {token.spelling for token in item.get_tokens()}:continue
                found.update(variables(item))
            return found
        for operation in nodes:
            if operation.kind.name in ('BINARY_OPERATOR','COMPOUND_ASSIGNMENT_OPERATOR'):
                children=list(operation.get_children())
                if len(children)<2:continue
                between=[t.spelling for t in operation.get_tokens() if children[0].extent.end.offset<=t.location.offset<children[1].extent.start.offset]
                if any(token in ('=','+=','-=','*=','/=','|=','&=','^=','<<=','>>=','%=') for token in between):
                    write_ranges.append((children[0].extent.start.offset,children[0].extent.end.offset))
                if '=' in between:
                    left=variables(children[0]);target=next((symbol for symbol,declaration in left.items() if pointer(declaration)),None)
                    if target:
                        direct=addresses(children[1]);sources=sorted(direct or variables(children[1]))
                        put('alias_relation',operation,id='alias_'+digest([owner,anchor(operation),target,sources])[:24],owner=owner,
                            target_symbol=target,source_symbols=sources,relation='address_of' if direct else 'pointer_copy',
                            certainty='exact' if len(sources)==1 else 'may',limitations=['flow_insensitive_within_function'])
            elif operation.kind.name=='UNARY_OPERATOR' and {t.spelling for t in operation.get_tokens()}&{'++','--'}:
                write_ranges.append((operation.extent.start.offset,operation.extent.end.offset))
        for declaration in (node for node in nodes if node.kind.name=='VAR_DECL' and pointer(node)):
            children=list(declaration.get_children())
            if not children:continue
            initializer=children[-1];direct=addresses(initializer);sources=sorted(direct or variables(initializer))
            if sources:
                put('alias_relation',declaration,id='alias_'+digest([owner,anchor(declaration),var(declaration),sources])[:24],owner=owner,
                    target_symbol=var(declaration),source_symbols=sources,relation='address_of' if direct else 'pointer_copy',
                    certainty='exact' if len(sources)==1 else 'may',limitations=['flow_insensitive_within_function'])
        for member in (node for node in nodes if node.kind.name=='MEMBER_REF_EXPR' and node.referenced and node.referenced.kind.name=='FIELD_DECL'):
            bases=variables(member);field=member.referenced;offset=member.extent.start.offset
            access='write' if any(start<=offset<=end for start,end in write_ranges) else 'read'
            put('field_access_seed',member,id='field_seed_'+digest([owner,anchor(member),base(field),sorted(bases),access])[:24],owner=owner,
                base_symbols=sorted(bases),field_id=base(field),field_name=field.spelling,access=access,
                expression=raw(member),certainty='may',limitations=['single_level_field_path'])
    def flow(c,owner,destination,expression,kind,guards):
        rid='flow_'+digest([owner,anchor(c),destination,kind])[:24]
        inputs=refs(expression)
        # Function calls are an opaque value unless matched by argument/return bindings later.
        put('flow',c,id=rid,owner=owner,sources=inputs,target=destination,expression=raw(expression),
            function_sources=function_refs(expression),relation=kind,certainty='may',guards=guards,limitations=['path_insensitive','alias_not_solved'])
    def walk(c,owner=None,guards=None):
        guards=guards or []
        if c.location.file and not inside(c):return
        kind=c.kind.name
        if kind in FUNCTIONS and c.is_definition() and inside(c):
            identity=base(c);fid='f_'+digest([identity,c.type.spelling,unit['id']])[:24]
            params=[]
            for i,p in enumerate(c.get_arguments() or []):
                pid=var(p);params.append(dict(id=pid,name=p.spelling,type=p.type.spelling,index=i))
            put('function',c,id=fid,base_id=identity,name=c.spelling,display_name=c.displayname,
                signature=c.type.spelling,parameters=params,return_type=c.result_type.spelling,
                storage=c.storage_class.name,summary=c.brief_comment or '功能简介待审阅；可查看签名与已提取的调用。',summary_origin='source_comment' if c.brief_comment else 'missing')
            owner=fid
            ir.append(dict(id=fid,format='clang_cursor_operations',cfg_status='unsupported',operations=[]))
            analyze_concurrency(c,fid)
            analyze_aliases(c,fid)
        elif kind in TYPES and inside(c) and c.spelling:
            fields=[dict(id=var(f),name=f.spelling,type=f.type.spelling,offset_bits=f.get_field_offsetof()) for f in c.get_children() if f.kind.name=='FIELD_DECL']
            put('type',c,id=base(c)+'_'+unit['id'][:12],name=c.spelling,type_kind=kind,fields=fields,size_bytes=c.type.get_size(),layout_configuration=unit['id'])
        elif kind=='VAR_DECL' and inside(c):
            vid=var(c);put('object',c,id=vid,name=c.spelling,type=c.type.spelling,owner=owner,
                          storage=c.storage_class.name,lifetime='static' if not owner or c.storage_class.name=='STATIC' else 'automatic')
            children=list(c.get_children())
            expressions=[x for x in children if x.kind.is_expression()]
            if expressions:flow(c,owner,vid,expressions[-1],'initializer',guards)
        elif kind=='CALL_EXPR' and owner:
            ref=c.referenced;target=base(ref) if ref and ref.kind.name in FUNCTIONS else None
            virtual=bool(ref and ref.kind.name=='CXX_METHOD' and ref.is_virtual_method())
            cid='c_'+digest([owner,anchor(c)])[:24]
            ref_path=str(Path(str(ref.location.file)).resolve()) if ref and ref.location.file else None
            stop=classify(ref_path,roots,rules,bool(ref and ref.location.is_in_system_header))
            if not stop and ref and ref.kind.name in ('CONSTRUCTOR','DESTRUCTOR','CXX_METHOD') and ref.is_default_method():stop='implicit_special_member'
            definition=ref.get_definition() if ref else None
            definition_path=str(Path(str(definition.location.file)).resolve()) if definition and definition.location.file else None
            args=[]
            for i,a in enumerate(c.get_arguments()):args.append(dict(index=i,expression=raw(a),sources=refs(a),function_sources=function_refs(a),evidence_ids=[anchor(a)]))
            put('callsite',c,id=cid,owner=owner,callee=c.spelling or raw(c).split('(')[0],target_base=target,
                dispatch='virtual' if virtual else 'direct' if target else 'indirect',arguments=args,guards=guards,
                expression=raw(c),target_declaration=ref_path,target_definition=definition_path,boundary_kind=stop,unknown_target_possible=virtual or not bool(target))
        elif kind in ('BINARY_OPERATOR','COMPOUND_ASSIGNMENT_OPERATOR') and owner:
            ch=list(c.get_children())
            if len(ch)>=2:
                # Tokens between AST operands identify the operator, never a call target.
                start=ch[0].extent.end.offset;end=ch[1].extent.start.offset
                ops=[t.spelling for t in c.get_tokens() if start<=t.location.offset<end]
                if any(x in ('=','+=','-=','*=','/=','|=','&=','^=','<<=','>>=','%=') for x in ops):
                    dest=refs(ch[0]);
                    for d in dest:flow(c,owner,d,ch[1],'assignment',guards)
        elif kind=='RETURN_STMT' and owner:
            for ch in c.get_children():flow(c,owner,owner+':return',ch,'return',guards)
        elif kind in ('DECL_REF_EXPR','MEMBER_REF_EXPR') and owner and c.referenced and c.referenced.kind.name not in FUNCTIONS:
            put('reference',c,id='r_'+digest([owner,anchor(c),var(c.referenced)])[:24],owner=owner,target=var(c.referenced),access='reference_not_classified')
        if owner and kind in ('CALL_EXPR','RETURN_STMT','BINARY_OPERATOR','COMPOUND_ASSIGNMENT_OPERATOR'):
            for record in reversed(ir):
                if record['id']==owner:
                    record['operations'].append(dict(kind=kind,expression=raw(c),evidence_ids=[anchor(c)]));break
        child_guards=guards+[dict(kind=kind,expression=raw(c)[:300],branch_polarity='not_solved')] if kind in BRANCHES else guards
        for ch in c.get_children():walk(ch,owner,child_guards)
    walk(tu.cursor)
    deps={unit['file']:filehash(unit['file']),**unit.get('response_inputs',{})}
    for inc in tu.get_includes():
        p=str(Path(str(inc.include)).resolve());deps[p]=filehash(p)
    facts += [dict(kind='evidence',**e) for e in evidence.values()]
    return dict(facts=facts,ir=ir,diagnostics=diagnostics,dependencies=deps,status='succeeded')
