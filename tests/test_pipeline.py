"""Behavioral tests with the real bundled Clang, not mocked AST fixtures."""
import json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class PipelineTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='atlas test ');cls.work=Path(cls.tmp.name)
  cls.repo=cls.work/'source';shutil.copytree(ROOT/'tests/fixture',cls.repo);cls.out=cls.work/'analysis'
  cls.launch=['powershell','-NoProfile','-File',str(ROOT/'run.ps1')] if os.name=='nt' else ['bash',str(ROOT/'run.sh')]
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
  c=json.loads((cls.out/'current.json').read_text());folder=cls.out/'snapshots'/c['snapshot_id']
  return json.loads((folder/'graph.json').read_text())['payload'],json.loads((folder/'analysis_manifest.json').read_text())['payload']
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
  s=html.read_text();self.assertIn('application/json',s);self.assertNotIn('__ATLAS_DATA__',s)
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
  p=self.repo/'other.c';p.write_text('#include "missing_business_header.h"\n'+p.read_text())
  self.cli(*self.base);g,_=self.graph();self.assertTrue(g['coverage']['failed']);self.assertFalse(any(f['name']=='leaf' for f in g['functions']))
 def test_06_negative_dependency(self):
  (self.repo/'header_without_extension').write_text('#define NEW 1\n')
  self.cli(*self.base);g,_=self.graph();self.assertEqual(g['coverage']['reused'],0)
 def test_07_semantic_environment_invalidates_cache(self):
  from unittest.mock import patch
  directory=self.work/'env_headers';directory.mkdir()
  with patch.dict(os.environ,{'CPATH':str(directory)}):
   self.cli(*self.base);g,_=self.graph();self.assertEqual(g['coverage']['reused'],0)
if __name__=='__main__':unittest.main(verbosity=2)
