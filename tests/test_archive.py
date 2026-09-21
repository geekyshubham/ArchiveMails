import unittest,json,hashlib,sys,threading,urllib.request,urllib.error,tempfile
from pathlib import Path
from email import policy
from email.parser import BytesParser
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import serve,archive_ai
OUT=ROOT/'MailArchive'
@unittest.skipUnless((OUT/'index.json').exists(), 'Optional local archive data is not present')
class RecoveryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.index=json.loads((OUT/'index.json').read_text());cls.manifest=json.loads((OUT/'manifest.json').read_text())
 def test_every_eml_body_metadata_and_attachment_matches_export(self):
  self.assertEqual(len(self.index),self.manifest['messages']);self.assertEqual(len({x['id'] for x in self.index}),len(self.index))
  for item in self.index:
   with self.subTest(id=item['id']):
    mail=BytesParser(policy=policy.default).parsebytes((OUT/item['eml']).read_bytes())
    self.assertFalse(mail.defects);self.assertEqual(str(mail.get('Subject','')),item['subject'] if item['subject']!='(No subject)' else '')
    self.assertEqual(str(mail['X-Recovery-Is-Read']),str(item['read']).lower() if item['read'] is not None else 'unknown')
    self.assertEqual(str(mail['X-Recovery-Folder']),item['folder'])
    detail=json.loads((OUT/'messages'/f"{item['id']}.json").read_text())
    body=mail.get_body(preferencelist=('html','plain'));self.assertIsNotNone(body)
    original=detail['bodyHtml'] or detail['bodyText'];self.assertEqual(body.get_content().replace('\r\n','\n').rstrip('\n'),original.replace('\r\n','\n').rstrip('\n'))
    parts=[p for p in mail.walk() if p.get_filename()]
    actual=sorted(hashlib.sha256(p.get_payload(decode=True)).hexdigest() for p in parts)
    expected=sorted(a['sha256'] for a in item['attachments'] if a['path']);self.assertEqual(actual,expected)
 def test_manifest_counts_and_files(self):
  atts=[a for i in self.index for a in i['attachments']]
  self.assertEqual(sum(bool(a['path']) for a in atts),self.manifest['attachmentsRecovered']);self.assertEqual(sum(not a['path'] for a in atts),self.manifest['attachmentsMissing'])
  for a in atts:
   if a['path']:self.assertEqual(hashlib.sha256((OUT/a['path']).read_bytes()).hexdigest(),a['sha256'])
 def test_sanitizer_blocks_active_and_remote_content(self):
  d={'attachments':[{'cid':'ok','path':'attachments/test.png','mime':'image/png'}],'bodyHtml':'<script>alert(1)</script><meta http-equiv="refresh" content="0;url=https://bad"><iframe src="https://bad"></iframe><form><input></form><img src="https://bad/track" onerror="alert(2)"><img src="cid:ok"><a href="https://bad">hello</a><div style="background:url(https://bad)">safe</div><svg><script>x</script></svg>','bodyText':''}
  s=serve.body_html(d)
  self.assertNotIn('<script',s);self.assertNotIn('<iframe',s);self.assertNotIn('onerror',s);self.assertNotIn('src="https',s);self.assertNotIn('href="https',s);self.assertNotIn('<meta http-equiv',s);self.assertNotIn('background:url',s);self.assertIn('/archive/attachments/test.png',s)
@unittest.skipUnless((OUT/'index.json').exists(), 'Optional local archive data is not present')
class AITests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.index=json.loads((OUT/'index.json').read_text());cls.c=archive_ai.Corpus(OUT,cls.index,json.loads((OUT/'manifest.json').read_text()))
 def test_exact_counts_not_top_k(self):
  self.assertEqual(self.c.stats()['count'],len(self.index));self.assertEqual(self.c.stats(folder='Deleted Items')['count'],sum(m['folder']=='Deleted Items' for m in self.index))
 def test_search_filters_pagination_and_reads(self):
  r=self.c.search(query='',kind='mail',folder='Deleted Items',unread_only=True)
  self.assertEqual(r['total'],sum(m['folder']=='Deleted Items' and m['read'] is False for m in self.index))
  ids={x['id'] for x in r['items']};self.assertFalse(ids&{x['id'] for x in self.c.search(query='',kind='mail',folder='Deleted Items',unread_only=True,offset=20)['items']})
  d=self.c.read(next(iter(ids)));self.assertEqual(d['text'],self.c.docs[d['id']]['text'][:14000])
 def test_tool_loop_and_citations(self):
  uid='mail:'+self.index[0]['id'];calls=[]
  def fake(config,path,payload):
   calls.append(payload)
   if len(calls)==1:return {'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[{'id':'call-1','type':'function','function':{'name':'read_source','arguments':json.dumps({'id':uid})}}]}}]}
   self.assertEqual(payload['messages'][-1]['role'],'tool');return {'choices':[{'message':{'role':'assistant','content':'Evidence ['+uid+']'}}]}
  result=archive_ai.chat(self.c,{'question':'Find one message'},transport=fake);self.assertEqual(result['sources'][0]['id'],uid);self.assertEqual(len(calls),2)
 def test_attachment_and_calendar_corpus_present(self):
  self.assertTrue(any(d['kind']=='file' for d in self.c.docs.values()));self.assertTrue(any(d['kind']=='calendar' for d in self.c.docs.values()))
if __name__=='__main__':unittest.main()
