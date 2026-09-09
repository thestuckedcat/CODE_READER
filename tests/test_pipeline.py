"""Behavioral tests with the real bundled Clang, not mocked AST fixtures."""
import json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from support import source_cli
class PipelineTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='atlas test ');cls.work=Path(cls.tmp.name)
  cls.repo=cls.work/'source';shutil.copytree(ROOT/'tests/fixture',cls.repo);cls.out=cls.work/'analysis'
  cls.launch=source_cli()
  cls.base=['run','--repo',str(cls.repo),'--out',str(cls.out)]
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 @classmethod
 def cli(cls,*args,ok=True):
  r=subprocess.run(cls.launch+list(args),capture_output=True,text=True,timeout=120)
  if ok and r.returncode:raise AssertionError(r.stdout+'\n'+r.stderr)
  if not ok and not r.returncode:raise AssertionError('Expected rejection: '+r.stdout)
  return r
 @classmethod
 def graph(cls):
  c=json.loads((cls.out/'current.json').read_text(encoding='utf-8'));folder=cls.out/'snapshots'/c['snapshot_id']
  return json.loads((folder/'graph.json').read_text(encoding='utf-8'))['payload'],json.loads((folder/'analysis_manifest.json').read_text(encoding='utf-8'))['payload']
 def test_01_calls_and_types(self):
  self.cli(*self.base);g,m=self.graph();fs={f['id']:f for f in g['functions']}
  edges={(fs[e['source']]['name'],fs[e['target']]['name']) for e in g['call_targets']}
  self.assertIn(('sdk_entry','leaf'),edges);self.assertIn(('alternate','leaf'),edges)
  overloads=[f for f in fs.values() if f['name']=='overload'];self.assertEqual(len(overloads),2)
  self.assertEqual(len({f['id'] for f in overloads}),2)
  self.assertTrue(any(t['name']=='Config' and len(t['fields'])==2 for t in g['types']))
  self.assertTrue(any(o['name']=='settings' and o['lifetime']=='static' for o in g['objects']))
  virtual=[c for c in g['callsites'] if c['dispatch']=='virtual'];self.assertTrue(virtual)
  self.assertTrue(all(e['certainty']=='may' for c in virtual for e in g['call_targets'] if e['callsite']==c['id']))
  self.assertTrue(any(i['kind']=='semantic_unresolved' for i in g['issues']))
  self.assertTrue(any(f['relation']=='argument_binding' for f in g['flow_edges']))
 def test_02_cache_and_incremental(self):
  self.cli(*self.base);g,_=self.graph();self.assertEqual(g['coverage']['parsed'],0);self.assertEqual(g['coverage']['reused'],3)
  p=self.repo/'other.c';p.write_text(p.read_text().replace('n + 1','n + 2'))
  self.cli(*self.base);g,_=self.graph();self.assertEqual(g['coverage']['parsed'],1);self.assertEqual(g['coverage']['reused'],2)
  (self.repo/'sdk.h').write_text((self.repo/'sdk.h').read_text()+'\n/* changed header */\n')
  self.cli(*self.base);g,_=self.graph();self.assertEqual(g['coverage']['parsed'],2);self.assertEqual(g['coverage']['reused'],1)
 def test_03_paths_and_export(self):
  r=self.cli('trace','--out',str(self.out),'--function','leaf','--direction','up')
  t=json.loads(r.stdout);self.assertEqual(len(t['first_divergence_choices']),2)
  self.cli('trace','--out',str(self.out),'--function','overload',ok=False)
  html=self.work/'offline'/'overview.html';self.cli('export','--out',str(self.out),'--html',str(html))
  s=html.read_text(encoding='utf-8');self.assertIn('application/json',s);self.assertNotIn('__ATLAS_DATA__',s)
  self.assertNotIn('src="http',s);self.assertNotIn('fetch(',s)
  self.cli('validate','--out',str(self.out))
 def test_04_invalid_review_and_valid_candidate(self):
  g,m=self.graph();issue=next(i for i in g['issues'] if i['kind']=='semantic_unresolved');ev=next(e for e in g['evidence'] if e['id'] in issue['evidence_ids'])
  target=next(f for f in g['functions'] if f['name']=='leaf')
  p=dict(task_id='review_'+issue['id'],snapshot_id=m['snapshot_id'],input_hash=issue['input_hash'],issue_ids=[issue['id']],status='candidates',limitations=['test-only candidate; does not claim actual callback registration'],search_set=[],correction_proposals=[],read_set=[{k:ev[k] for k in ('id','file','hash','start','end')}],relation_proposals=[dict(callsite=issue['subject_id'],target=target['id'],evidence_ids=[ev['id']],reason='Test protocol acceptance only')])
  f=self.work/'review.json';body=dict(schema_version='0.1',record_kind='review_result',payload=p)
  p['input_hash']='stale';f.write_text(json.dumps(body));before=(self.out/'current.json').read_bytes()
  self.cli('review-import','--out',str(self.out),'--result',str(f),ok=False);self.assertEqual(before,(self.out/'current.json').read_bytes())
  p['input_hash']=issue['input_hash'];f.write_text(json.dumps(body))
  original=(self.repo/'sdk.c').read_bytes();(self.repo/'sdk.c').write_bytes(original+b'\n/* changed after snapshot */\n')
  self.cli('review-import','--out',str(self.out),'--result',str(f),ok=False);self.assertEqual(before,(self.out/'current.json').read_bytes())
  (self.repo/'sdk.c').write_bytes(original)
  self.cli('review-import','--out',str(self.out),'--result',str(f))
  g,_=self.graph();self.assertTrue(all(e['certainty']=='may' for e in g['agent_supplements']));self.assertTrue(all(e['unknown_target_possible'] for e in g['agent_supplements']))
  self.cli('review-import','--out',str(self.out),'--result',str(f),ok=False)
  second=next(i for i in g['issues'] if i['kind']=='semantic_unresolved' and i['id']!=issue['id'])
  p.update(task_id='review_'+second['id'],issue_ids=[second['id']],input_hash=second['input_hash'],relation_proposals=[],read_set=[],status='unresolved')
  f.write_text(json.dumps(body));self.cli('review-import','--out',str(self.out),'--result',str(f))
 def test_05_parse_failure_does_not_reuse_old_facts(self):
  p=self.repo/'other.c';original=p.read_text();p.write_text('#include "missing_business_header.h"\n'+original)
  try:
   self.cli(*self.base);g,_=self.graph();self.assertTrue(g['coverage']['failed']);self.assertFalse(any(f['name']=='leaf' for f in g['functions']))
  finally:p.write_text(original)
 def test_06_negative_dependency(self):
  (self.repo/'header_without_extension').write_text('#define NEW 1\n')
  self.cli(*self.base);g,_=self.graph();self.assertEqual(g['coverage']['reused'],0)
 def test_07_semantic_environment_invalidates_cache(self):
  from unittest.mock import patch
  directory=self.work/'env_headers';directory.mkdir()
  with patch.dict(os.environ,{'CPATH':str(directory)}):
   self.cli(*self.base);g,_=self.graph();self.assertEqual(g['coverage']['reused'],0)
 def test_08_lock_and_shared_state_parallelism(self):
  self.cli(*self.base);g,_=self.graph()
  lock=next(row for row in g['locks'] if row['name']=='shared_gate')
  shared=next(row for row in g['shared_state_summaries'] if row['name']=='shared_counter')
  self.assertGreaterEqual(len([row for row in g['lock_events'] if lock['id'] in row['lock_ids']]),4)
  self.assertTrue(any(row['held_lock_ids']==[lock['id']] and row['access']=='write' for row in g['shared_accesses'] if row['object_id']==shared['object_id']))
  self.assertTrue(any(not row['held_lock_ids'] for row in g['shared_accesses'] if row['object_id']==shared['object_id']))
  self.assertEqual(shared['status'],'potential_race')
  self.assertTrue(any(row['relation']=='serialized_by_common_lock' for row in g['concurrency_findings'] if row['object_id']==shared['object_id']))
  self.assertTrue(any(row['relation']=='potentially_parallel_conflict' for row in g['concurrency_findings'] if row['object_id']==shared['object_id']))
  result=json.loads(self.cli('locks','--out',str(self.out),'--object','shared_counter').stdout)
  self.assertEqual(result['shared_state'][0]['status'],'potential_race')
  by_lock=json.loads(self.cli('locks','--out',str(self.out),'--lock','shared_gate').stdout)
  self.assertEqual({row['name'] for row in by_lock['shared_state']},{'shared_counter'})
 def test_09_field_alias_argument_and_callback_candidates(self):
  self.cli(*self.base);g,_=self.graph();functions={row['id']:row for row in g['functions']}
  pair=next(row for row in g['objects'] if row['name']=='shared_pair')
  local=[row for row in g['field_accesses'] if functions[row['owner']]['name']=='alias_write' and row['field_name']=='left']
  self.assertTrue(local);self.assertEqual(local[0]['object_ids'],[pair['id']]);self.assertEqual(local[0]['certainty'],'exact')
  crossed=[row for row in g['field_accesses'] if functions[row['owner']]['name']=='set_pair_left' and row['field_name']=='left']
  self.assertTrue(crossed);self.assertEqual(crossed[0]['access_paths'],['shared_pair.left'])
  right=[row for row in g['field_accesses'] if row['field_name']=='right' and pair['id'] in row['object_ids']]
  self.assertTrue(right);self.assertNotEqual(local[0]['field_id'],right[0]['field_id'])
  callback=next(row for row in g['callback_targets'] if functions[row['owner']]['name']=='register_callback')
  self.assertEqual({functions[fid]['name'] for fid in callback['candidate_function_ids']},{'leaf'})
  ownership=next(row for row in g['lock_ownership_summaries'] if functions[row['function_id']]['name']=='parameter_locked_write')
  gate=next(row for row in g['objects'] if row['name']=='shared_gate')
  self.assertEqual(ownership['acquired_lock_ids'],[gate['id']]);self.assertEqual(ownership['released_lock_ids'],[gate['id']])
  result=json.loads(self.cli('aliases','--out',str(self.out),'--object','shared_pair').stdout)
  self.assertTrue(result['field_accesses']);self.assertTrue(all(pair['id'] in row['object_ids'] for row in result['field_accesses']))
 def test_10_multi_alias_nested_callback_lifecycle_and_wrapper_lock(self):
  self.cli(*self.base);g,_=self.graph();functions={row['id']:row for row in g['functions']};objects={row['name']:row for row in g['objects']}
  nested=next(row for row in g['field_accesses'] if functions[row['owner']]['name']=='multi_nested_write' and row['field_path']==['pair','left'])
  self.assertEqual(set(nested['object_ids']),{objects['nested_a']['id'],objects['nested_b']['id']});self.assertEqual(nested['certainty'],'may')
  self.assertEqual(set(nested['access_paths']),{'nested_a.pair.left','nested_b.pair.left'})
  lifecycle=next(row for row in g['callback_states'] if functions[row['owner']]['name']=='callback_lifecycle')
  events=[row for row in g['callback_targets'] if row['owner']==lifecycle['owner']]
  self.assertEqual(lifecycle['status'],'cleared');self.assertEqual([row['action'] for row in events],['set','clear'])
  self.assertEqual(events[1]['supersedes_event_id'],events[0]['id'])
  wrapper=next(fid for fid,row in functions.items() if row['name']=='wrapper_locked_write');gate=objects['shared_gate']['id'];counter=objects['shared_counter']['id']
  projected=[row for row in g['lock_events'] if row['owner']==wrapper and row.get('propagated_from')]
  self.assertEqual([row['action'] for row in projected],['acquire','release'])
  access=next(row for row in g['shared_accesses'] if row['owner']==wrapper and row['object_id']==counter)
  self.assertIn(gate,access['held_lock_ids'])
  result=json.loads(self.cli('aliases','--out',str(self.out),'--function','multi_nested_write').stdout)
  self.assertEqual(result['field_accesses'][0]['certainty'],'may')
if __name__=='__main__':unittest.main(verbosity=2)
