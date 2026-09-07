"""Native Clang CFG acceptance. No mocked control-flow graphs."""
import json,os,shutil,subprocess,tempfile,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from support import source_cli
from atlas.native import executable
from atlas.pipeline import load_snapshot
from atlas.dataflow import trace

@unittest.skipUnless(executable(),'native extractor required: build scripts/build_native.py')
class RoundTwo(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='atlas round2 ');self.work=Path(self.tmp.name)
  self.repo=self.work/'repo';self.repo.mkdir();self.out=self.work/'analysis'
  self.launch=source_cli()
 def tearDown(self):self.tmp.cleanup()
 def put(self,name,text):(self.repo/name).write_text(text)
 def setup(self,code,other=None,cpp=False):
  extension='cpp' if cpp else 'c';self.source='api.'+extension
  self.put(self.source,code)
  if other:self.put('other.'+extension,other)
  self.put('CMakeLists.txt','cmake_minimum_required(VERSION 3.16)\nproject(flow '+('CXX' if cpp else 'C')+')\nadd_library(sdk STATIC '+self.source+(' other.'+extension if other else '')+')\n')
 def run_repo(self,*args,out=None):
  r=subprocess.run(self.launch+['run','--repo',str(self.repo),'--out',str(out or self.out),'--dataflow','cfg',*args],capture_output=True,text=True,timeout=180)
  self.assertEqual(r.returncode,0,r.stdout+'\n'+r.stderr)
  return load_snapshot(out or self.out)[0]
 def fn(self,g,name):return next(f for f in g['functions'] if f['name']==name)
 def values(self,g,name):return [v for v in g['value_nodes'] if v['owner']==self.fn(g,name)['id']]
 def deps(self,g,name):return next(s for s in g['return_summaries'] if s['function_id']==self.fn(g,name)['id'])['parameter_dependencies']
 def test_overwritten_assignment_and_two_callsites(self):
  self.setup('int send(int); int top(int input) {int x=input; x=0; send(x); return send(input);}')
  g=self.run_repo();t=trace(g,'top','input')
  args=[v for v in t['values'] if v['kind']=='call_argument']
  self.assertEqual(len(args),1);self.assertIn('send(input)',args[0]['expression'])
  self.assertEqual(self.deps(g,'top'),[0])
 def test_branch_conditions_and_early_return(self):
  self.setup('int choose(int a,int flag){int x; if(flag) x=a+2; else x=7; return x;} int early(int a,int flag){if(flag)return 0; return a*2;}')
  g=self.run_repo();self.assertEqual(self.deps(g,'choose'),[0,1]);self.assertEqual(self.deps(g,'early'),[0,1])
  fid=self.fn(g,'choose')['id'];cfg=next(c for c in g['cfgs'] if c['function_id']==fid)
  branches=[b for b in cfg['blocks'] if b['terminator']=='IfStmt']
  self.assertEqual(len(branches),1);self.assertEqual([e['ordinal'] for e in branches[0]['successors']],[0,1])
  ret=trace(g,'choose');self.assertTrue(any(v.get('expression')=='7' for v in ret['values']))
 def test_loop_switch_goto_fixed_point(self):
  self.setup('int loops(int a,int n){int x=a; for(int i=0;i<n;i++){if(i==2)continue; x+=i; if(x>20)break;} while(n>0){--n;x++;} do{x--;}while(x>30); switch(n){case 0:x+=2;break; default:x+=3;} if(x<0)goto out; x+=1; out:return x;}')
  g=self.run_repo();s=next(s for s in g['return_summaries'] if s['function_id']==self.fn(g,'loops')['id'])
  self.assertTrue(s['converged']);self.assertEqual(s['parameter_dependencies'],[0,1])
  terms={b['terminator'] for c in g['cfgs'] for b in c.get('blocks',[])}
  self.assertTrue({'ForStmt','WhileStmt','DoStmt','SwitchStmt','GotoStmt'}<=terms)
 def test_cross_function_return_and_callsite_isolation(self):
  self.setup('int scale(int); int top(int input){int a=scale(input); int b=scale(7); return b;}', 'int twice(int x){return x*2;} int scale(int y){return twice(y)+3;}')
  g=self.run_repo();self.assertEqual(self.deps(g,'scale'),[0]);self.assertEqual(self.deps(g,'top'),[])
  reached=trace(g,'top','input')['values'];self.assertFalse(any(v['kind']=='return' for v in reached))
  backward=trace(g,'top');self.assertTrue(any(v.get('summary_function')==self.fn(g,'scale')['id'] for v in backward['values']))
 def test_short_circuit_and_ternary(self):
  self.setup('int pick(int a,int b,int flag){int x=flag?a:b; if(flag && a) x+=1; return x;}')
  g=self.run_repo();self.assertEqual(self.deps(g,'pick'),[0,1,2])
 def test_pointer_effect_is_unknown(self):
  self.setup('void mutate(int*); int effect(int a){int x=a; mutate(&x); return x;} int unknown(int *p){return *p;}')
  g=self.run_repo();s=next(s for s in g['return_summaries'] if s['function_id']==self.fn(g,'effect')['id'])
  self.assertEqual(s['status'],'partial');self.assertIn('call_memory_effect',s['limitations'])
 def test_recursive_summary_budget_and_unknown(self):
  self.setup('int rec(int x){if(x<=0)return 0; return rec(x-1)+1;}')
  g=self.run_repo();s=g['return_summaries'][0]
  self.assertTrue(s['converged']);self.assertIn('recursive_value_not_proven',s['limitations'])
  g=self.run_repo('--flow-steps','1');self.assertFalse(g['return_summaries'][0]['converged'])
 def test_cache_and_callee_change_incremental_matches_fresh(self):
  self.setup('int leaf(int); int top(int x){return leaf(x)+1;} int unrelated(int z){return z-2;}', 'int leaf(int x){return x*2;}')
  g=self.run_repo();again=self.run_repo();self.assertEqual(again['coverage']['parsed'],0);self.assertEqual(again['dataflow_status']['summary_iterations'],0)
  self.put('other.c','int leaf(int x){return 7;}')
  updated=self.run_repo();self.assertEqual(updated['coverage']['parsed'],1)
  self.assertEqual(self.deps(updated,'top'),[])
  fresh=self.run_repo(out=self.work/'fresh')
  def logical(graph):
   names={f['id']:f['name'] for f in graph['functions']}
   return {names[s['function_id']]:(s['parameter_dependencies'],s['status'],s['limitations']) for s in graph['return_summaries']}
  self.assertEqual(logical(updated),logical(fresh))
  self.assertEqual(self.deps(updated,'unrelated'),[0])
  run=max((self.out/'runs').iterdir(),key=lambda p:p.stat().st_mtime)
  entries=json.loads((run/'artifacts.json').read_text(encoding='utf-8'))['payload']['entries']
  e=next(e for e in entries if e['logical_name']=='dataflow_plan.json')
  plan=json.loads((self.out/e['relative_path']).read_text(encoding='utf-8'))['payload']
  by={(p['function_id'],p['stage']):p['action'] for p in plan}
  self.assertEqual(by[self.fn(updated,'unrelated')['id'],'return_summary'],'reuse')
  self.assertEqual(by[self.fn(updated,'top')['id'],'return_summary'],'solve')
 def test_unreachable_after_return(self):
  self.setup('int f(int a){return 0; return a;}')
  g=self.run_repo();self.assertEqual(self.deps(g,'f'),[])
 def test_cpp_scalar_and_destructor_limit(self):
  self.setup('struct Guard { ~Guard(); }; int clean(int x){Guard g; return x+1;} int simple(int x){return x+1;}',cpp=True)
  g=self.run_repo();self.assertEqual(self.deps(g,'simple'),[0])
  s=next(s for s in g['return_summaries'] if s['function_id']==self.fn(g,'clean')['id'])
  self.assertEqual(s['status'],'partial')
 def test_native_failure_and_query_budget(self):
  self.setup('int f(int a){return a+1;}')
  g=self.run_repo();t=trace(g,'f','a',budget=1);self.assertTrue(t['truncated']);self.assertEqual(len(t['values']),1)
  bad=self.work/'bad-native';bad.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo fake-test-version; exit 0; fi\necho intentional-parser-failure >&2\nexit 2\n');bad.chmod(0o755)
  g=self.run_repo('--native-extractor',str(bad))
  self.assertTrue(g['functions']);self.assertEqual(g['dataflow_status']['status'],'partial')
  self.assertFalse(g['value_nodes']);self.assertFalse(g['return_summaries'][0]['converged'])
 def test_void_callee_parameter_expansion(self):
  self.setup('void consume(int); void relay(int x){consume(x+1);} void top(int input){relay(input);}')
  g=self.run_repo();t=trace(g,'top','input')
  self.assertTrue(t['call_expansions']);e=t['call_expansions'][0]
  self.assertEqual(e['function_id'],self.fn(g,'relay')['id'])
  self.assertTrue(any(v['kind']=='call_argument' for v in e['values']));self.assertTrue(e['bindings'])
 def test_short_circuit_side_effect_and_constant_branch(self):
  self.setup('int branch(int input){int x=0; if(0 && (x=input)){} return x;} int live(int flag,int input){int x=0; if(flag && (x=input)){} return x;}')
  g=self.run_repo();self.assertEqual(self.deps(g,'branch'),[]);self.assertEqual(self.deps(g,'live'),[0,1])
 def test_cli_backward_flow_and_html_export(self):
  self.setup('int simple(int x){return x+4;}')
  html=self.work/'view.html';g=self.run_repo('--html',str(html))
  r=subprocess.run(self.launch+['flow','--out',str(self.out),'--function','simple'],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['direction'],'backward')
  self.assertIn('value_nodes',html.read_text(encoding='utf-8'));self.assertIn('参数计算链',html.read_text(encoding='utf-8'))
