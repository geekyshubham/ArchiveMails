"""Background imports. Uploaded data stays local, separate from original snapshots."""
import json,os,sys,re,uuid,threading,zipfile,shutil,subprocess,hashlib,datetime,collections
from pathlib import Path,PurePosixPath
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from archive_store import recipient_accounts,message_identity,content_identity
MAX_FILE=2*1024**3;MAX_TOTAL=8*1024**3;MAX_FILES=60000
class Text(HTMLParser):
 def __init__(self):super().__init__();self.out=[];self.skip=0
 def handle_starttag(self,t,a):
  if t in ['script','style','head']:self.skip+=1
  if t in ['p','div','br','li','tr']:self.out.append('\n')
 def handle_endtag(self,t):
  if t in ['script','style','head']:self.skip=max(0,self.skip-1)
 def handle_data(self,s):
  if not self.skip:self.out.append(s)
def plain(s):
 p=Text();p.feed(s);return re.sub(r'\n\s*\n','\n\n',''.join(p.out)).strip()
def safe_path(name):
 name=name.replace('\\','/');p=PurePosixPath(name)
 if not name or p.is_absolute() or any(x in ('..','') for x in p.parts) or ':' in p.parts[0] or '\x00' in name:raise ValueError('Invalid file path')
 return Path(*p.parts)
def safe_name(name):return re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name or 'attachment')[:160].strip('. ') or 'attachment'
def eml_into(path,root,uid,folder):
 raw=path.read_bytes();msg=BytesParser(policy=policy.default).parsebytes(raw)
 if not any(msg.get(h) for h in ('From','To','Subject','Date','Message-ID')):raise ValueError('No recognizable email headers')
 htmlpart=msg.get_body(preferencelist=('html',));textpart=msg.get_body(preferencelist=('plain',));bh=htmlpart.get_content() if htmlpart else '';bt=textpart.get_content() if textpart else plain(bh)
 attachments=[]
 for part in msg.walk():
  if part is msg:continue
  if not part.get_filename() and part.get_content_disposition()!='attachment' and not part.get('Content-ID'):continue
  if part.get_content_type()=='message/rfc822':
   payload=part.get_payload();data=payload[0].as_bytes(policy=policy.SMTP) if isinstance(payload,list) and payload else part.get_payload(decode=True)
  elif part.is_multipart():continue
  else:data=part.get_payload(decode=True)
  if data is None:continue
  name=part.get_filename() or ('inline-'+str(len(attachments)+1));sha=hashlib.sha256(data).hexdigest();rel='attachments/'+sha[:16]+'-'+safe_name(name);(root/rel).write_bytes(data)
  attachments.append({'id':sha,'name':name,'mime':part.get_content_type(),'size':len(data),'inline':part.get_content_disposition()=='inline' or bool(part.get('Content-ID')),'cid':str(part.get('Content-ID','')).strip('<>') or None,'path':rel,'sha256':sha,'source':'Imported EML','cachedRendition':False})
 date=''
 try:
  d=parsedate_to_datetime(str(msg.get('Date','')))
  if d.tzinfo is None:d=d.replace(tzinfo=datetime.timezone.utc)
  date=d.isoformat()
 except (ValueError,TypeError,OverflowError):pass
 read_header=str(msg.get('X-Recovery-Is-Read','')).casefold();read=True if read_header=='true' else False if read_header=='false' else ('R' in str(msg['Status']) if msg.get('Status') is not None else None)
 folder=str(msg.get('X-Recovery-Folder') or folder or 'Imported');fid='imported-folder:'+hashlib.sha256(folder.encode()).hexdigest()[:16]
 status=str(msg.get('X-Recovery-Status','recovered'))
 if status not in ['recovered','attachment_missing','partial']:status='recovered'
 eml='emails/'+uid+'.eml';(root/eml).write_bytes(raw)
 item={'id':uid,'eml':eml,'emlSha256':hashlib.sha256(raw).hexdigest(),'subject':str(msg.get('Subject','')) or '(No subject)','from':str(msg.get('From','')),'to':str(msg.get('To','')),'cc':str(msg.get('Cc','')),'bcc':str(msg.get('Bcc','')),'date':date,'sent':date,'folder':folder,'folderId':fid,'read':read,'status':status,'bodySource':'Imported EML','preview':bt[:255],'attachments':attachments,'notes':(['The source EML reports incomplete recovery. Missing attachment details may not be available.'] if status!='recovered' else []),'internetMessageId':str(msg.get('Message-ID','')) or None,'conversationId':None,'importance':str(msg.get('Importance','Normal')),'historical':False}
 detail=dict(item,bodyHtml=bh,bodyText=bt,raw={'headers':list(msg.raw_items()),'parserDefects':[str(x) for x in msg.defects]},row={},provenance=[{'source':str(path.name),'type':'EML import','sha256':item['emlSha256']}])
 (root/'messages'/f'{uid}.json').write_text(json.dumps(detail,ensure_ascii=False));item['searchText']=' '.join([item['subject'],item['from'],item['to'],item['cc'],item['bcc'],bt]+[a['name'] for a in attachments]).casefold();return item
class ImportManager:
 def __init__(self,root,store,on_commit):self.root=Path(root);self.code_root=Path(__file__).resolve().parent;self.store=store;self.on_commit=on_commit;self.jobs={};self.lock=threading.RLock();self.run_lock=threading.Lock()
 def new(self,name):
  with self.lock:
   if any(j['status'] in ['uploading','processing'] for j in self.jobs.values()):raise ValueError('An import is already active. Finish or cancel it before starting another.')
   uid=uuid.uuid4().hex;work=self.root/'imports'/uid/'work';(work/'input').mkdir(parents=True)
   job={'id':uid,'name':str(name)[:160],'status':'uploading','message':'Waiting for files','files':0,'bytes':0,'uploaded':set(),'work':work,'activeUploads':0,'errors':[]};self.jobs[uid]=job;self.persist(job)
   return self.public(job)
 def persist(self,job):
  path=self.root/'imports'/job['id']/'status.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(self.public(job),ensure_ascii=False));tmp.replace(path)
 def public(self,job):return {k:v for k,v in job.items() if k not in ['uploaded','work','activeUploads']}
 def get(self,uid):
  with self.lock:
   if uid not in self.jobs:
    if not re.fullmatch('[a-f0-9]{32}',uid):raise ValueError('Import not found')
    path=self.root/'imports'/uid/'status.json'
    if not path.exists():raise ValueError('Import not found')
    saved=json.loads(path.read_text())
    if saved['status'] in ['uploading','processing']:saved.update(status='failed',message='The server restarted during this import. Choose the files again; existing mail is unchanged.')
    return saved
   return self.public(self.jobs[uid])
 def upload(self,uid,name,stream,length):
  rel=safe_path(name)
  with self.lock:
   j=self.jobs.get(uid)
   if not j or j['status']!='uploading':raise ValueError('Import is not accepting files')
   if not 0<=length<=MAX_FILE or j['bytes']+length>MAX_TOTAL:raise ValueError('Import exceeds the 2 GB per-file or 8 GB total limit')
   if name in j['uploaded']:raise ValueError('This file was already uploaded')
   if j['files']>=MAX_FILES:raise ValueError('Too many files')
   j['uploaded'].add(name);j['bytes']+=length;j['files']+=1;j['activeUploads']+=1;p=j['work']/'input'/rel
  try:
   p.parent.mkdir(parents=True,exist_ok=True)
   with p.open('xb') as out:
    remaining=length
    while remaining:
     b=stream.read(min(1024*1024,remaining))
     if not b:raise ValueError('Upload ended early')
     out.write(b);remaining-=len(b)
  except Exception:
   with self.lock:j['uploaded'].discard(name);j['bytes']-=length;j['files']-=1
   if p.exists():p.unlink()
   raise
  finally:
   with self.lock:j['activeUploads']-=1
  return {'ok':True}
 def cancel(self,uid):
  with self.lock:
   j=self.jobs.get(uid)
   if not j:raise ValueError('Import not found')
   if j['status']!='uploading':raise ValueError('Only uploads can be cancelled; processing continues safely in the background.')
   if j['activeUploads']:raise ValueError('Wait for current uploads to finish before cancelling.')
   j['status']='cancelled';j['message']='Import cancelled. Existing mail is unchanged.';self.persist(j);return self.public(j)
 def start(self,uid):
  with self.lock:
   j=self.jobs.get(uid)
   if not j or j['status']!='uploading':raise ValueError('Import cannot be started')
   if j['activeUploads']:raise ValueError('Wait for all files to finish uploading')
   j['status']='processing';j['message']='Inspecting uploaded files';self.persist(j)
  threading.Thread(target=self.run,args=(j,),daemon=True).start();return self.public(j)
 def command(self,j,script):
  py=self.code_root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python');py=str(py) if py.exists() else sys.executable
  env=dict(os.environ,MDUMP_WORK_ROOT=str(j['work']))
  with (j['work']/(script+'.log')).open('w') as log:
   result=subprocess.run([py,str(self.code_root/'scripts'/script)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
  if result.returncode:
   logtext=(j['work']/(script+'.log')).read_text(errors='replace')
   if 'ModuleNotFoundError' in logtext:raise ValueError('Outlook import dependencies are missing. Run python3 -m pip install -r requirements-recovery.txt, then retry.')
   raise ValueError(f'{script} could not process this snapshot. The import log is saved locally; existing mail is unchanged.')
 def unpack(self,j):
  inp=j['work']/'input';expanded=0;count=0
  # Only top-level selected ZIPs are expanded; attachment archives remain attachments.
  for zpath in list(inp.rglob('*.zip')):
   if 'Attachments' in zpath.parts:continue
   dest=inp/('unpacked-'+hashlib.sha256(str(zpath).encode()).hexdigest()[:12]);dest.mkdir(exist_ok=True)
   with zipfile.ZipFile(zpath) as z:
    for info in z.infolist():
     rel=safe_path(info.filename)
     if ((info.external_attr>>16)&0o170000)==0o120000:raise ValueError('Symbolic links in ZIP imports are not supported')
     count+=1;expanded+=info.file_size
     if count>MAX_FILES or expanded>MAX_TOTAL:raise ValueError('Expanded ZIP exceeds the import size limit')
     p=dest/rel
     if info.is_dir():p.mkdir(parents=True,exist_ok=True);continue
     p.parent.mkdir(parents=True,exist_ok=True)
     with z.open(info) as src,p.open('wb') as out:shutil.copyfileobj(src,out,1024*1024)
 def run(self,j):
  with self.run_lock:
   try:
    self.unpack(j);inp=j['work']/'input';profiles=[p.parent for p in inp.rglob('IndexedDB') if p.is_dir() and any(p.glob('*outlook*.indexeddb.leveldb'))]
    if profiles:
     if len(profiles)>1:raise ValueError('This import contains multiple browser profiles. Import each OLK profile separately.')
     profile=profiles[0];j['message']='Decoding Outlook messages, bodies and attachments';snap=j['work']/'snapshot/Olk';snap.parent.mkdir(parents=True,exist_ok=True)
     if profile.name=='Default' and profile.parent.name=='EBWebView':shutil.move(str(profile.parent.parent),snap)
     else:
      (snap/'EBWebView').mkdir(parents=True);shutil.move(str(profile),snap/'EBWebView/Default')
     self.command(j,'decode_snapshot.py');j['message']='Creating EML files';self.command(j,'export_mail.py')
    else:
     files=sorted(p for p in inp.rglob('*') if p.is_file() and p.suffix.casefold()=='.eml')
     if not files:raise ValueError('No .eml files or supported Outlook IndexedDB cache found. Select the Olk folder, Olk.zip, or an EML folder. The Outlook package folder alone contains no mail.')
     out=j['work']/'MailArchive'
     for d in ['emails','messages','attachments','unlinked','data']:(out/d).mkdir(parents=True,exist_ok=True)
     index=[];seen=set(self.store.hashes);identities=set(self.store.identities);duplicates=0
     for n,p in enumerate(files):
      j['message']=f'Reading email {n+1:,} of {len(files):,}';sha=hashlib.sha256(p.read_bytes()).hexdigest()
      if sha in seen:duplicates+=1;continue
      seen.add(sha);uid='eml'+sha[:20]
      try:
       header=BytesParser(policy=policy.default).parsebytes(p.read_bytes(),headersonly=True);identity=message_identity(header.get('Message-ID'))
       if identity and identity in identities:duplicates+=1;continue
       item=eml_into(p,out,uid,p.parent.name if p.parent!=inp else 'Imported')
       if not identity:
        detail=json.loads((out/'messages'/f'{uid}.json').read_text());identity=content_identity(item,detail.get('bodyText',''))
       if identity in identities:duplicates+=1;continue
       identities.add(identity);item['dedupeIdentity']=identity;index.append(item)
      except Exception as e:j['errors'].append({'file':str(p.relative_to(inp)),'error':type(e).__name__})
     folders={}
     for m in index:
      f=folders.setdefault(m['folderId'],{'id':m['folderId'],'name':m['folder'],'recovered':0,'cachedServerTotal':None});f['recovered']+=1
     manifest={'messages':len(index),'folders':list(folders.values()),'unlinkedFiles':[],'dataFiles':[],'limitations':['Imported EML files retain their original bytes. Account views are derived only from To recipients.'],'created':datetime.datetime.now(datetime.timezone.utc).isoformat()}
     (out/'index.json').write_text(json.dumps(index,ensure_ascii=False));(out/'manifest.json').write_text(json.dumps(manifest,indent=2));j['duplicates']=duplicates
    out=j['work']/'MailArchive';idx=json.loads((out/'index.json').read_text());before=len(idx);unique=[];identities=set(self.store.identities)
    for m in idx:
     identity=m.get('dedupeIdentity') or message_identity(m.get('internetMessageId'))
     if not identity:
      detail=json.loads((out/'messages'/f"{m['id']}.json").read_text());identity=content_identity(m,detail.get('bodyText',''))
     if m['id'] in self.store.lookup or m.get('emlSha256') in self.store.hashes or identity in identities:continue
     identities.add(identity);unique.append(m)
    idx=unique
    j['duplicates']=j.get('duplicates',0)+before-len(idx)
    if not idx:
     if j['errors'] and not j['duplicates']:raise ValueError('None of the selected messages could be read. Existing mail is unchanged.')
     shutil.rmtree(j['work']);j.update(status='complete',message='All messages were already imported; no duplicates added.',added=0);return
    (out/'index.json').write_text(json.dumps(idx,ensure_ascii=False));j['message']='Indexing attachment text'
    try:self.command(j,'index_attachment_text.py')
    except ValueError as e:j['errors'].append({'file':'attachment index','error':str(e)})
    j['message']='Updating accounts, search and AI index';self.store.add_dataset(j['id'],{'name':j['name'],'added':len(idx),'duplicates':j['duplicates']});j['committed']=True;self.on_commit()
    j.update(status='complete',message=f'Imported {len(idx):,} messages. Accounts and AI search are ready.',added=len(idx))
   except Exception as e:j.update(status='failed',message='Messages were saved, but search could not refresh. Restart the app to reload them.' if j.get('committed') else str(e) if isinstance(e,ValueError) else f'Import failed ({type(e).__name__}). Existing mail is unchanged.')
   finally:self.persist(j)
