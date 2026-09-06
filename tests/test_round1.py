"""Round 1 acceptance: real CMake/Clang, independent temporary workspaces."""
import json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class RoundOne(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='atlas round1 ');self.work=Path(self.tmp.name);self.repo=self.work/'repo';self.repo.mkdir();self.out=self.work/'analysis'
  self.launch=['powershell','-NoProfile','-File',str(ROOT/'run.ps1')] if os.name=='nt' else ['bash',str(ROOT/'run.sh')]
 def tearDown(self):self.tmp.cleanup()
 def put(self,p,text):
  path=self.repo/p;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);return path
 def cli(self,*args,ok=True):
  r=subprocess.run(self.launch+list(args),capture_output=True,text=True,timeout=90)
  if ok:self.assertEqual(r.returncode,0,r.stdout+'\n'+r.stderr)
  else:self.assertNotEqual(r.returncode,0,r.stdout)
  return r
 def run_repo(self,*args,ok=True):return self.cli('run','--repo',str(self.repo),'--out',str(self.out),*args,ok=ok)
 def graph(self):
  c=json.loads((self.out/'current.json').read_text());folder=self.out/'snapshots'/c['snapshot_id'];return json.loads((folder/'graph.json').read_text())['payload']
 def artifacts(self,name):
  results=[]
  for run in sorted((self.out/'runs').iterdir(),key=lambda p:p.stat().st_mtime):
   for e in json.loads((run/'artifacts.json').read_text())['payload']['entries']:
    if e['logical_name']==name:results.append(json.loads((self.out/e['relative_path']).read_text())['payload'])
  return results
 def simple(self,sources):
  self.put('CMakeLists.txt','cmake_minimum_required(VERSION 3.16)\nproject(test C)\nadd_library(sdk STATIC '+sources+')\n')
 def test_parent_configuration_parameters_and_generated_header(self):
  self.put('CMakeLists.txt','''cmake_minimum_required(VERSION 3.16)
project(parent C)
if(NOT DEFINED TOP_DIR)
 message(FATAL_ERROR "TOP_DIR is required")
endif()
function(make_sdk)
 add_library(sdk STATIC api.c)
 target_include_directories(sdk PRIVATE "${TOP_DIR}/headers" "${CMAKE_CURRENT_BINARY_DIR}")
 configure_file("${TOP_DIR}/config.in" "${CMAKE_CURRENT_BINARY_DIR}/config.h" @ONLY)
endfunction()
add_subdirectory(child)
''')
  self.put('child/CMakeLists.txt','make_sdk()\n');self.put('child/api.c','#include "config.h"\n#include "value.h"\nint entry(void) { return VALUE + CONFIG; }\n')
  self.put('headers/value.h','#define VALUE 3\n');self.put('config.in','#define CONFIG 7\n')
  common=['run','--repo',str(self.repo/'child'),'--out',str(self.out)]
  self.cli(*common,ok=False);self.assertTrue(self.artifacts('configuration_questions.json'))
  params=self.work/'params.json';params.write_text(json.dumps({'TOP_DIR':str(self.repo)}))
  self.cli(*common,'--params',str(params),'--interface','entry');self.assertEqual(len(self.graph()['functions']),1)
  self.cli(*common,'--interface','entry');self.assertEqual(self.graph()['coverage']['parsed'],0)
  self.assertEqual(self.artifacts('configure_result.json')[-1]['status'],'reused')
  relations=self.artifacts('cmake_relations.json')[-1]['relations'];self.assertTrue(any(r['cmd']=='add_subdirectory' for r in relations))
 def test_independent_externalproject_child(self):
  self.put('CMakeLists.txt','''cmake_minimum_required(VERSION 3.16)
project(super NONE)
include(ExternalProject)
ExternalProject_Add(child SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/child" DOWNLOAD_COMMAND "" INSTALL_COMMAND "")
''')
  self.put('child/CMakeLists.txt','cmake_minimum_required(VERSION 3.16)\nproject(child C)\nadd_library(child STATIC child.c)\n')
  self.put('child/child.c','int child_entry(int x){ return x; }\n')
  self.run_repo(ok=False)
  self.assertTrue(self.artifacts('cmake_relations.json')[-1]['external_projects'])
  self.run_repo('--child-cmake-root',str(self.repo/'child'),'--interface','child_entry')
  self.assertEqual([f['name'] for f in self.graph()['functions']],['child_entry'])
 def test_same_named_headers_variants_and_response_file(self):
  self.put('a/config.h','struct Selected { int from_a; };\n')
  self.put('b/config.h','struct Selected { long from_b; };\n')
  src=self.put('api.c','#include <config.h>\nint entry(void){return sizeof(struct Selected);}\n')
  db=self.work/'compile_commands.json';response=self.work/'flags.rsp';response.write_text('-I "'+str(self.repo/'a')+'" -I "'+str(self.repo/'b')+'"')
  db.write_text(json.dumps([dict(directory=str(self.repo),file=str(src),arguments=['cc','@'+str(response),'-c',str(src)])]))
  self.run_repo('--compdb',str(db),'--interface','entry');types=self.graph()['types'];self.assertTrue(any(t['fields'] and t['fields'][0]['name']=='from_a' for t in types))
  response.write_text('-I "'+str(self.repo/'b')+'" -I "'+str(self.repo/'a')+'"')
  self.run_repo('--compdb',str(db),'--interface','entry');self.assertTrue(any(t['fields'] and t['fields'][0]['name']=='from_b' for t in self.graph()['types']))
  entries=[dict(directory=str(self.repo),file=str(src),arguments=['cc','-I'+str(self.repo/which),'-c',str(src)]) for which in ('a','b')]
  db.write_text(json.dumps(entries));self.run_repo('--compdb',str(db),'--interface','entry',ok=False)
  choices=self.artifacts('interface_choices.json')[-1];self.assertEqual(len(choices),2)
  self.run_repo('--compdb',str(db),'--interface','entry','--select-function',choices[0]['id']);self.assertEqual(len(self.graph()['functions']),1)
 def test_lightweight_boundaries_topmost_and_callsite_paths(self):
  self.simple('api.c leaf.c unrelated.c')
  self.put('api.c','#include <stdio.h>\nint leaf(int); int unavailable(int);\nint entry(int v){puts("hello"); leaf(v); return leaf(v+1)+unavailable(v);}\nint top(int v){return entry(v);}\n')
  self.put('leaf.c','int leaf(int v){return v+2;}\n');self.put('unrelated.c','int unused(void){return 9;}\n')
  self.run_repo('--interface','entry');g=self.graph();self.assertEqual(g['coverage']['processed_units'],2)
  self.assertTrue(any(b['kind']=='glibc' and b['callee']=='puts' for b in g['boundaries']))
  self.assertTrue(any(b['kind']=='implementation_not_found' and b['callee']=='unavailable' for b in g['boundaries']))
  down=json.loads(self.cli('trace','--out',str(self.out),'--function','entry').stdout)
  paths=[p for p in down['paths'] if p['stop']=='leaf_in_analyzed_graph'];self.assertEqual(len(paths),2);self.assertNotEqual(paths[0]['callsites'],paths[1]['callsites'])
  self.run_repo('--interface','leaf','--direction','up');g=self.graph();up=json.loads(self.cli('trace','--out',str(self.out),'--function','leaf','--direction','up').stdout)
  self.assertEqual({f['name'] for f in g['functions'] if f['id'] in up['top_functions']},{'top'})
  self.run_repo('--interface','leaf','--direction','up');self.assertEqual(self.graph()['coverage']['parsed'],0);self.assertEqual(self.graph()['coverage']['candidate_index']['scanned_files'],0)
 def test_system_source_roots_stop_even_if_implementation_available(self):
  self.simple('api.c linux/kernel.c')
  self.put('api.c','#include "linux/kernel.h"\nint entry(int x){return kernel_call(x);}\n')
  self.put('linux/kernel.h','int kernel_call(int);\n');self.put('linux/kernel.c','#include "kernel.h"\nint kernel_call(int x){return x;}\n')
  self.run_repo('--interface','entry','--linux-root',str(self.repo/'linux'));g=self.graph()
  self.assertEqual(g['coverage']['processed_units'],1);self.assertEqual(g['boundaries'][0]['kind'],'linux')
 def test_cross_repository_header_dependency_and_exact_target(self):
  other=self.work/'dep';other.mkdir();(other/'dep.c').write_text('#include "dep.h"\nint dep(int x){return x+OFFSET;}\n');(other/'dep.h').write_text('#define OFFSET 1\nint dep(int);\n')
  self.put('CMakeLists.txt','cmake_minimum_required(VERSION 3.16)\nproject(cross C)\nadd_library(sdk STATIC api.c "'+str(other/'dep.c')+'")\ntarget_include_directories(sdk PRIVATE "'+str(other)+'")\nadd_library(sdk_extra STATIC extra.c)\n')
  self.put('api.c','#include "dep.h"\nint entry(int x){return dep(x);}\n');self.put('extra.c','int extra(void){return 8;}\n')
  self.run_repo('--target','sdk','--interface','entry');g=self.graph();self.assertEqual({f['name'] for f in g['functions']},{'entry','dep'})
  self.assertEqual(g['coverage']['total_available_units'],2)
  (other/'dep.h').write_text('#define OFFSET 2\nint dep(int);\n');self.run_repo('--target','sdk','--interface','entry');self.assertEqual(self.graph()['coverage']['parsed'],2)
  plans=self.artifacts('invalidation_plan.json')[-1]['units'];self.assertTrue(all(any('dependency_changed:' in r for r in p.get('reasons',[])) for p in plans))
 def test_header_inline_discovery_and_budget(self):
  self.simple('a.c b.c')
  self.put('inline.h','static inline int in_header(int v){return v+1;}\n')
  self.put('a.c','#include "inline.h"\nint entry(int x){return in_header(x);}\n');self.put('b.c','int other(void){return 0;}\n')
  self.run_repo('--interface','in_header');self.assertEqual(self.graph()['coverage']['processed_units'],1)
  self.run_repo('--max-tu','1');g=self.graph();self.assertTrue(g['coverage']['truncated']);self.assertTrue(g['coverage']['pending_units'])
 def test_explicit_parameters_and_assumptions(self):
  self.simple('api.c');self.put('api.c','int entry(void){return 1;}\n')
  self.run_repo('--require-param','TOP_DIR',ok=False)
  self.assertEqual(self.artifacts('configuration_questions.json')[-1]['items'][0]['name'],'TOP_DIR')
  params=self.work/'p.json';params.write_text(json.dumps({'TOP_DIR':str(self.repo)}))
  assumptions=self.work/'a.json';assumptions.write_text(json.dumps([dict(name='TOP_DIR',value=str(self.repo),reason='test configuration',accepted_by='fixture user')]))
  self.run_repo('--params',str(params),'--assumptions',str(assumptions));self.assertEqual(self.artifacts('assumptions.json')[-1][0]['accepted_by'],'fixture user')
 def test_interface_matches_full_reference_and_recursion(self):
  self.simple('a.c b.c spare.c')
  self.put('a.c','int b(int); int entry(int x){return b(x)+b(x+1); }\n')
  self.put('b.c','int b(int x){return x?b(x-1):0;}\n');self.put('spare.c','int spare(void){return 0;}\n')
  self.run_repo('--interface','entry');part=self.graph();self.assertEqual(part['coverage']['processed_units'],2)
  snapshot_edges={(e['source'],e['target'],e['callsite'],e['certainty']) for e in part['call_targets']}
  self.run_repo();full=self.graph();selected={f['id'] for f in part['functions']}
  self.assertEqual(snapshot_edges,{(e['source'],e['target'],e['callsite'],e['certainty']) for e in full['call_targets'] if e['source'] in selected})
  paths=json.loads(self.cli('trace','--out',str(self.out),'--function','entry').stdout)['paths'];self.assertTrue(any(p['stop']=='recursion' for p in paths))
 def test_business_symbol_name_is_not_system_boundary(self):
  self.simple('api.c')
  self.put('api.c','int malloc(int x){return x;} int entry(int x){return malloc(x);}\n')
  self.run_repo('--interface','entry','--clang-arg=-fno-builtin');g=self.graph()
  self.assertEqual({f['name'] for f in g['functions']},{'entry','malloc'});self.assertFalse(g['boundaries'])
 def test_target_dependency_closure(self):
  self.put('CMakeLists.txt','cmake_minimum_required(VERSION 3.16)\nproject(targets C)\nadd_library(dep STATIC dep.c)\nadd_library(sdk STATIC api.c)\ntarget_link_libraries(sdk PRIVATE dep)\nadd_library(unrelated STATIC unrelated.c)\n')
  self.put('api.c','int dep(int); int entry(int x){return dep(x);}\n');self.put('dep.c','int dep(int x){return x;}\n');self.put('unrelated.c','int spare(void){return 1;}\n')
  self.run_repo('--target','sdk','--interface','entry');g=self.graph();self.assertEqual({f['name'] for f in g['functions']},{'entry','dep'});self.assertEqual(g['coverage']['total_available_units'],2)
if __name__=='__main__':unittest.main(verbosity=2)
