import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import archive_ai as ai
class GatewayTests(unittest.TestCase):
 def setUp(self):
  self.config=dict(ai.CONFIG);self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'config.json';self.patch=patch.object(ai,'CONFIG_PATH',self.path);self.patch.start()
  ai.CONFIG.update(base_url='http://127.0.0.1:8318/v1',model='working',provider='openai',api_key='')
 def tearDown(self):ai.CONFIG.clear();ai.CONFIG.update(self.config);self.patch.stop();self.tmp.cleanup()
 def test_missing_model_does_not_replace_config(self):
  with self.assertRaises(ai.GatewayError):ai.configure({'base_url':ai.CONFIG['base_url'],'model':'gone','provider':'antigravity'},transport=lambda *a:{'data':[{'id':'working','owned_by':'openai'}]})
  self.assertEqual(ai.CONFIG['model'],'working');self.assertFalse(self.path.exists())
 def test_provider_auth_failure_preserves_current(self):
  def fake(c,p,payload=None):
   if p=='/models':return {'data':[{'id':'unavailable','owned_by':'antigravity'}]}
   raise ai.gateway_error(503,'{"error":{"message":"auth_unavailable: no auth available"}}',c['model'])
  with self.assertRaisesRegex(ai.GatewayError,'no active provider session'):ai.configure({'base_url':ai.CONFIG['base_url'],'model':'unavailable','provider':'antigravity'},transport=fake)
  self.assertEqual(ai.CONFIG['model'],'working')
 def test_successful_tool_roundtrip_saves_without_key(self):
  calls=[]
  def fake(c,p,payload=None):
   calls.append(payload)
   if p=='/models':return {'data':[{'id':'new-model','owned_by':'openai'}]}
   if len(calls)==2:return {'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[{'id':'probe','type':'function','function':{'name':'connection_check','arguments':'{"value":"ok"}'}}]}}]}
   self.assertEqual(payload['messages'][-1]['role'],'tool');return {'choices':[{'message':{'role':'assistant','content':'OK'}}]}
  ai.configure({'base_url':ai.CONFIG['base_url'],'model':'new-model','provider':'openai','api_key':'test-secret'},transport=fake)
  saved=json.loads(self.path.read_text());self.assertEqual(saved['model'],'new-model');self.assertNotIn('api_key',saved);self.assertIn('verified_at',saved)
 def test_non_tool_model_rejected(self):
  def fake(c,p,payload=None):return {'data':[{'id':'plain','owned_by':'openai'}]} if p=='/models' else {'choices':[{'message':{'content':'Hello'}}]}
  with self.assertRaisesRegex(ai.GatewayError,'usable tool call'):ai.configure({'base_url':ai.CONFIG['base_url'],'model':'plain'},transport=fake)
  self.assertEqual(ai.CONFIG['model'],'working')
if __name__=='__main__':unittest.main()
