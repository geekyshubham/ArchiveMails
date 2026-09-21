import os
"""Build standard MIME .eml files and a local archive from decoded snapshot data."""
import csv,json,hashlib,shutil,re,mimetypes,html,collections,datetime
from pathlib import Path
from email.message import EmailMessage, Message
from email.policy import SMTP
from email.utils import formataddr,format_datetime
from html.parser import HTMLParser
CODE_ROOT=Path(__file__).resolve().parents[1]
ROOT=Path(os.environ.get('MDUMP_WORK_ROOT',str(CODE_ROOT))).resolve();REC=ROOT/'recovery';OUT=ROOT/'MailArchive'
for d in ['emails','attachments','messages','data','unlinked']: (OUT/d).mkdir(parents=True,exist_ok=True)
def load(n):
 p=REC/(n+'.json');return json.loads(p.read_text()) if p.exists() else []
def latest(rs):
 out={}
 for r in sorted(rs,key=lambda r:r['seq']):out[str(r['key'])]=r
 return out
class Plain(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.skip=0
 def handle_starttag(self,t,a):
  if t in ['script','style','head']:self.skip+=1
  if t in ['br','p','div','tr','li']:self.parts.append('\n')
 def handle_endtag(self,t):
  if t in ['script','style','head']:self.skip=max(0,self.skip-1)
 def handle_data(self,d):
  if not self.skip:self.parts.append(d)
def plain(s):
 p=Plain();p.feed(s);return re.sub(r'\n[ \t\r]*\n+', '\n\n',''.join(p.parts)).strip()
def header(v):return re.sub(r'[\r\n\x00]+',' ',str(v or ''))
def addr(v):
 if not isinstance(v,dict):return ''
 m=v.get('Mailbox',v);email=m.get('EmailAddress','');name=m.get('Name','')
 # Keep legacy Exchange addresses in raw metadata; don't invent SMTP addresses.
 return formataddr((header(name),header(email))) if '@' in email and not email.startswith('/') else header(name or email)
def addrs(v):return ', '.join(filter(None,(addr(x) for x in v))) if isinstance(v,list) else ''
def safe_name(s):return re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',s or 'attachment')[:160].strip('. ') or 'attachment'
def store_file(data,name,folder='attachments'):
 sha=hashlib.sha256(data).hexdigest();path=f'{folder}/{sha[:16]}-{safe_name(name)}';p=OUT/path
 if not p.exists():p.write_bytes(data)
 return path,sha
folders={r['value']['id']:r['value'] for r in latest(load('folders')).values() if r['value']}
rows=latest(load('messages'));bodies=latest(load('messageBodies'));detached=[]
for r in load('detached-message-candidates'):
 if r['key'] and str(r['key']) not in bodies and str(r['key']) not in rows:
  bodies[str(r['key'])]=r;detached.append(str(r['key']))
# Match explicit IDs. Prefer original HTTP bytes; retain type 2 images as labelled cached renditions.
afiles={}
for r in load('http-attachments'):
 afiles.setdefault(r['attachmentId'],[]).append(r)
for r in load('images'):
 v=r['value']
 if v and v.get('thumbnailType') in ('2',2) and isinstance(v.get('image'),dict) and v['image'].get('binary'):
  afiles.setdefault(v['attachmentId'],[]).append(dict(v['image'],source='IndexedDB images',seq=r['seq']))
attachment_meta=collections.defaultdict(dict)
for r in load('attachments'):
 if r['value']:
  v=r['value'];attachment_meta[v['messageBodyId']][v['attachmentId']]=v
index=[];linked_hashes=set();warnings=[]
keys=set(rows)|set(bodies)
def sortkey(k):return (rows.get(k,{}).get('value') or bodies.get(k,{}).get('value') or {}).get('DateTimeReceived','')
for no,k in enumerate(sorted(keys,key=lambda k:(sortkey(k),k),reverse=True),1):
 rr=rows.get(k);br=bodies.get(k);rv=(rr or {}).get('value') or {};bv=(br or {}).get('value') or {}
 if not rv and not bv:continue
 # Row state is the latest folder/read-state evidence; body supplies content and recipients.
 v=dict(bv);v.update({a:b for a,b in rv.items() if b is not None})
 uid=hashlib.sha256(k.encode()).hexdigest()[:20];emailfile=f'emails/{no:06d}.eml'
 fid=(v.get('ParentFolderId') or {}).get('Id','');folder=folders.get(fid,{}).get('displayName','Unknown folder')
 body=bv.get('Body') or bv.get('NormalizedBody') or bv.get('UniqueBody') or {};bodyvalue=body.get('Value','');bodykind=next((x for x in ['Body','NormalizedBody','UniqueBody'] if bv.get(x)),None)
 is_html=body.get('BodyType','HTML').upper()=='HTML';textbody=plain(bodyvalue) if is_html else bodyvalue
 missing=[];notes=[];atts=[]
 if not body:notes.append('Full body was not present; only the cached preview is available.')
 if body.get('IsTruncated') or bv.get('QuotedBodyMissing'):notes.append('Cached body is flagged as truncated or missing quoted content.')
 descriptors={a.get('AttachmentId',{}).get('Id'):a for a in bv.get('Attachments') or []}
 for aid,a in attachment_meta[k].items():
  if aid not in descriptors:descriptors[aid]={'AttachmentId':{'Id':aid},'Name':a.get('fileName'),'Size':a.get('fileSize'),'IsInline':False}
 for aid,a in descriptors.items():
  if not aid:continue
  ar={'id':aid,'name':a.get('Name') or 'attachment','mime':a.get('ContentType') or 'application/octet-stream','size':a.get('Size'),'inline':a.get('IsInline',False),'cid':a.get('ContentId'),'path':None}
  candidates=afiles.get(aid,[])
  # Exchange Size includes metadata overhead; it is not a raw-byte length.
  # HTTP sources are complete status-200 GetFileAttachment bodies. Image store
  # type 2 (LargeOrOriginalFile) is retained as a cached image rendition, never a claimed original.
  exact=candidates
  if exact:
   source=max(exact,key=lambda x:(x.get('source')=='HTTP cache',x.get('seq',0),x['bytes']));data=(ROOT/source['binary']).read_bytes();ar['path'],sha=store_file(data,ar['name']);linked_hashes.add(sha);ar.update(sha256=sha,source=source['source'],size=len(data),declaredSize=a.get('Size'),cachedRendition=source['source']=='IndexedDB images')
   if ar['mime']=='application/octet-stream':ar['mime']=source.get('mime') or mimetypes.guess_type(ar['name'])[0] or ar['mime']
  else:missing.append(ar['name'])
  atts.append(ar)
 if v.get('HasAttachments') and not any(not a['inline'] for a in atts):notes.append('Outlook reports an attachment, but its complete attachment metadata was not cached.')
 if missing:notes.append(f'{len(missing)} attachment(s) missing from the snapshot.')
 if k in detached:notes.append('Recovered from a detached cache blob; folder/read state may be historical.')
 status='partial' if not body or body.get('IsTruncated') or bv.get('QuotedBodyMissing') else ('attachment_missing' if missing or (v.get('HasAttachments') and not any(not a['inline'] for a in atts)) else 'recovered')
 mail=EmailMessage(policy=SMTP)
 for h,x in [('Subject',v.get('Subject','')),('From',addr(bv.get('From') or v.get('From'))),('Sender',addr(bv.get('Sender'))),('To',addrs(bv.get('ToRecipients'))),('Cc',addrs(bv.get('CcRecipients'))),('Bcc',addrs(bv.get('BccRecipients'))),('Reply-To',addrs(bv.get('ReplyTo'))),('Message-ID',bv.get('InternetMessageId'))]:
  if x:mail[h]=header(x)
 dt=v.get('DateTimeSent') or v.get('DateTimeReceived')
 if dt:
  try:mail['Date']=format_datetime(datetime.datetime.fromisoformat(dt.replace('Z','+00:00')))
  except ValueError:warnings.append({'id':uid,'warning':'Unparseable Date'})
 mail['X-Recovery-Status']=status;mail['X-Recovery-Folder']=header(folder);mail['X-Recovery-Source']='Copied New Outlook cache';mail['X-Recovery-Body-Source']=bodykind or 'Preview'
 read=v.get('IsRead');mail['X-Recovery-Is-Read']='true' if read is True else 'false' if read is False else 'unknown'
 if read is not None:mail['Status']='RO' if read else 'O'
 if v.get('IsDraft'):mail['X-Unsent']='1'
 content=textbody if body else '[Recovery note: full body unavailable. Cached preview follows.]\n\n'+v.get('Preview','')
 mail.set_content(content)
 if is_html and body:mail.add_alternative(bodyvalue,subtype='html')
 for a in atts:
  if not a['path']:continue
  mime=a['mime'].split(';')[0];major,minor=mime.split('/',1) if '/' in mime else ('application','octet-stream')
  data=(OUT/a['path']).read_bytes()
  # Preserve attached .eml bytes verbatim as a downloadable file, avoiding
  # invalid base64 transfer encoding on a message/rfc822 MIME container.
  if major=='message':major,minor='application','octet-stream'
  if a['inline'] and is_html and body:
   part=mail.get_payload()[1];part.add_related(data,maintype=major,subtype=minor,cid='<'+a['cid'].strip('<>')+'>' if a['cid'] else None,filename=a['name'],disposition='inline')
  else:mail.add_attachment(data,maintype=major,subtype=minor,filename=a['name'],cid='<'+a['cid'].strip('<>')+'>' if a['cid'] else None)
 (OUT/emailfile).write_bytes(mail.as_bytes())
 item={'id':uid,'eml':emailfile,'subject':v.get('Subject') or '(No subject)','from':addr(bv.get('From') or v.get('From')),'to':addrs(bv.get('ToRecipients')) or v.get('DisplayTo',''),'cc':addrs(bv.get('CcRecipients')),'bcc':addrs(bv.get('BccRecipients')),'date':v.get('DateTimeReceived') or dt or '', 'sent':dt,'folder':folder,'folderId':fid,'read':read,'status':status,'bodySource':bodykind,'preview':v.get('Preview',''),'attachments':atts,'notes':notes,'internetMessageId':bv.get('InternetMessageId'),'conversationId':(v.get('ConversationId') or {}).get('Id'),'importance':v.get('Importance'),'historical':k in detached}
 detail=dict(item,bodyHtml=bodyvalue if is_html else '',bodyText=textbody or v.get('Preview',''),raw=bv,row=rv,provenance=[{a:r.get(a) for a in ['source','seq','blob','live']} for r in [rr,br] if r])
 (OUT/'messages'/f'{uid}.json').write_text(json.dumps(detail,ensure_ascii=False))
 item['searchText']=' '.join([item['subject'],item['from'],item['to'],item['cc'],item['bcc'],textbody]+[a['name'] for a in atts]).casefold();index.append(item)
# Preserve cached files that cannot be confidently associated, without guessing a message.
unlinked=[]
for p in (ROOT/'snapshot/Olk/Attachments').rglob('*'):
 if not p.is_file():continue
 data=p.read_bytes();sha=hashlib.sha256(data).hexdigest()
 if sha in linked_hashes:continue
 ext='.pdf' if data.startswith(b'%PDF') else '.png' if data.startswith(b'\x89PNG') else '.jpg' if data.startswith(b'\xff\xd8') else '.zip' if data.startswith(b'PK') else '.bin'
 path,_=store_file(data,sha[:12]+ext,'unlinked');unlinked.append({'path':path,'sha256':sha,'bytes':len(data),'source':str(p.relative_to(ROOT))})
# Preserve explicitly identified cached attachments whose parent message is absent.
for aid,candidates in afiles.items():
 for a in candidates:
  if a['sha256'] in linked_hashes:continue
  data=(ROOT/a['binary']).read_bytes()
  name=''
  if a.get('disposition'):
   h=Message();h['Content-Disposition']=a['disposition'][0];name=h.get_filename() or ''
  if not name:name=aid[-12:].replace('/','_')+(mimetypes.guess_extension(a.get('mime') or '') or '.bin')
  path,sha=store_file(data,name,'unlinked')
  unlinked.append({'path':path,'sha256':sha,'bytes':len(data),'source':a['source'],'attachmentId':aid,'cachedRendition':a['source']=='IndexedDB images'})
# Additional data stays available as JSON; it is not misrepresented as email.
datafiles=[]
for name in ['folders','contacts','events','calendars','calendarGroups','conversations','conversationNodes','offlineTombstones','store-inventory','service-worker-inventory','decode-errors']:
 src=REC/(name+'.json')
 if src.exists():
  dest=OUT/'data'/src.name;shutil.copyfile(src,dest);rs=load(name);datafiles.append({'name':name,'path':f'data/{src.name}','records':len(rs)})
(OUT/'index.json').write_text(json.dumps(index,ensure_ascii=False))
with (OUT/'index.csv').open('w',newline='',encoding='utf-8-sig') as f:
 fields=['id','eml','folder','subject','from','to','date','read','status','bodySource','internetMessageId'];wr=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');wr.writeheader()
 for x in index:wr.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in x.items()})
manifest={'created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'messages':len(index),'folders':[],'statuses':dict(collections.Counter(x['status'] for x in index)),'unread':sum(x['read'] is False for x in index),'attachmentsRecovered':sum(bool(a['path']) for x in index for a in x['attachments']),'attachmentsMissing':sum(not a['path'] for x in index for a in x['attachments']),'unlinkedFiles':list({x['sha256']:x for x in unlinked}.values()),'dataFiles':datafiles,'warnings':warnings,'detachedMessages':len(detached),'limitations':['EML files are reconstructed from cached Outlook objects, not original server MIME.','Normalized HTML may differ from the original message and may omit blocked external images.','Opening this viewer does not alter the captured read/unread state.','Folder totals are cached server metadata; the number and identity of uncached server-only messages cannot be verified offline.','No message is inferred from a folder total. Missing attachment bytes are never fabricated.'],'sourceArchives':[]}
for fid,f in folders.items():
 count=sum(x['folderId']==fid for x in index)
 manifest['folders'].append({'id':fid,'name':f['displayName'],'recovered':count,'cachedServerTotal':f.get('totalMessageCount'),'type':f.get('distinguishedFolderType')})
for fid in {x['folderId'] for x in index}-set(folders):
 manifest['folders'].append({'id':fid,'name':'Historical records','recovered':sum(x['folderId']==fid for x in index),'cachedServerTotal':None,'type':None})
manifest['cachedImageRenditions']=sum(a.get('cachedRendition',False) for x in index for a in x['attachments'])
for p in ROOT.glob('*.zip'):
 if p.name not in ['Olk.zip','Microsoft.OutlookForWindows_8wekyb3d8bbwe.zip']:continue
 sha=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):sha.update(b)
 manifest['sourceArchives'].append({'name':p.name,'bytes':p.stat().st_size,'sha256':sha.hexdigest()})
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
print(json.dumps({k:manifest[k] for k in ['messages','statuses','attachmentsRecovered','attachmentsMissing','detachedMessages']}));print('Unlinked files',len(manifest['unlinkedFiles']))
