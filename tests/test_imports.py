import unittest,tempfile,json,io,zipfile,time,sys
from pathlib import Path
from email.message import EmailMessage
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from archive_store import ArchiveStore,recipient_accounts,content_identity
from archive_import import ImportManager,safe_path
from archive_ai import Corpus

def eml(mid='one@example.test',subject='Imported contract',to='Alex Example <alex@example.test>',newline='\n'):
 m=EmailMessage();m['Subject']=subject;m['From']='Sender <sender@example.test>';m['To']=to;m['Date']='Mon, 21 Sep 2026 10:00:00 -0400'
 if mid:m['Message-ID']='<'+mid+'>'
 m.set_content('Approved contract terms. The amount is 100 dollars.');m.add_attachment(b'proof',maintype='application',subtype='octet-stream',filename='contract.txt')
 return m.as_bytes().replace(b'\n',newline.encode())
class ImportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);a=self.root/'MailArchive';a.mkdir();(a/'index.json').write_text('[]');(a/'manifest.json').write_text(json.dumps({'folders':[],'limitations':[],'messages':0}));self.store=ArchiveStore(self.root);self.reloads=0
  def changed():self.reloads+=1
  self.im=ImportManager(self.root,self.store,changed);self.im.command=lambda j,script:None
 def tearDown(self):self.tmp.cleanup()
 def upload_run(self,files):
  j=self.im.new('test');uid=j['id']
  for path,data in files:self.im.upload(uid,path,io.BytesIO(data),len(data))
  self.im.start(uid)
  for _ in range(400):
   result=self.im.get(uid)
   if result['status'] in ['complete','failed']:return result
   time.sleep(.01)
  self.fail('Import timed out')
 def test_import_and_cross_import_message_id_dedupe(self):
  r=self.upload_run([('Emails/a.eml',eml()),('Emails/a-copy.eml',eml(newline='\r\n'))]);self.assertEqual(r['status'],'complete',r);self.assertEqual(r['added'],1);self.assertEqual(r['duplicates'],1)
  r=self.upload_run([('b.eml',eml(newline='\r\n'))]);self.assertEqual(r['added'],0);self.assertEqual(r['duplicates'],1);self.assertEqual(len(self.store.index),1)
  self.assertEqual(self.store.manifest['accounts'][0]['email'],'alex@example.test');self.assertEqual(self.store.manifest['accounts'][0]['count'],1)
  d=self.store.detail(self.store.index[0]['id']);self.assertEqual(d['bodyText'].strip(),'Approved contract terms. The amount is 100 dollars.');self.assertEqual(self.store.resolve(d['attachments'][0]['path']).read_bytes(),b'proof')
  reopened=ArchiveStore(self.root);self.assertEqual(len(reopened.index),1)
 def test_content_fallback_different_mime_boundaries(self):
  r=self.upload_run([('a.eml',eml(mid=None)),('b.eml',eml(mid=None))]);self.assertEqual(r['added'],1);self.assertEqual(r['duplicates'],1)
 def test_same_subject_distinct_message_ids_are_kept(self):
  r=self.upload_run([('a.eml',eml(mid='1@example.test')),('b.eml',eml(mid='2@example.test'))]);self.assertEqual(r['added'],2)
 def test_zip_import_and_account_scope(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr('Mail/a.eml',eml());z.writestr('Mail/b.eml',eml(mid='two@test',to='Other <other@example.test>'))
  r=self.upload_run([('mail.zip',b.getvalue())]);self.assertEqual(r['added'],2)
  c=Corpus(self.store.archive,self.store.index,self.store.manifest,store=self.store)
  self.assertEqual(c.stats(account='alex@example.test')['count'],1)
  other=next(d['id'] for d in c.docs.values() if 'other@example.test' in d.get('accounts',[]));self.assertIn('error',c.execute('read_source',{'id':other},account='alex@example.test'))
 def test_bad_zip_does_not_change_existing_archive(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr('../escaped.eml',eml())
  r=self.upload_run([('evil.zip',b.getvalue())]);self.assertEqual(r['status'],'failed');self.assertEqual(self.store.index,[]);self.assertFalse((self.root/'escaped.eml').exists())
 def test_invalid_eml_reports_failure(self):
  r=self.upload_run([('notmail.eml',b'no mail headers')]);self.assertEqual(r['status'],'failed');self.assertEqual(len(r['errors']),1)
 def test_paths_and_duplicate_upload(self):
  for path in ['../secret','/absolute','C:/bad','..\\bad']:
   with self.assertRaises(ValueError):safe_path(path)
  j=self.im.new('x');self.im.upload(j['id'],'a.eml',io.BytesIO(b'x'),1)
  with self.assertRaises(ValueError):self.im.upload(j['id'],'a.eml',io.BytesIO(b'x'),1)
 def test_attachment_indexing_with_real_worker(self):
  self.im.command=ImportManager.command.__get__(self.im,ImportManager)
  r=self.upload_run([('a.eml',eml())]);self.assertEqual(r['status'],'complete',r);self.assertEqual(r['errors'],[])
  c=Corpus(self.store.archive,self.store.index,self.store.manifest,store=self.store)
  result=c.search(query='proof',kind='file',account='alex@example.test');self.assertEqual(result['total'],1)
  source=result['items'][0];self.assertEqual(self.store.resolve(source['path']).read_bytes(),b'proof')
 def test_recipient_identity_case_and_names(self):self.assertEqual(recipient_accounts('Alex Example <ALEX@example.test>'),{'alex@example.test':'Alex Example'})
if __name__=='__main__':unittest.main()
