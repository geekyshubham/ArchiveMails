"""Load immutable archive datasets and derive recipient account views."""
import json,copy,hashlib,collections,threading,csv,io
from pathlib import Path
from email.utils import getaddresses
from email.header import decode_header,make_header
from datetime import datetime,timezone
from urllib.parse import quote

def recipient_accounts(to):
 result={}
 for name,address in getaddresses([to or '']):
  address=address.strip().casefold()
  if '@' not in address or any(c.isspace() for c in address) or address.startswith('/'):continue
  try:name=str(make_header(decode_header(name))).strip()
  except (ValueError,LookupError):name=name.strip()
  result[address]=name or address
 return result

def datekey(value):
 try:return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
 except (ValueError,AttributeError):return 0

def message_identity(message_id):
 value=str(message_id or '').strip()
 return 'message-id:'+value if value and value not in ['<Undefined>','None'] else None

def content_identity(item,text):
 # Folder and read state intentionally excluded: moving or reading is not a new email.
 fields={'subject':' '.join(str(item.get('subject','')).split()),'from':sorted(recipient_accounts(item.get('from',''))),'to':sorted(recipient_accounts(item.get('to',''))),'date':datekey(item.get('sent') or item.get('date')),'body':' '.join(text.split()),'attachments':sorted(a.get('sha256','') for a in item.get('attachments',[]) if a.get('path'))}
 return 'content:'+hashlib.sha256(json.dumps(fields,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

class ArchiveStore:
 def __init__(self,root):
  self.root=Path(root);self.archive=self.root/'MailArchive';self.catalog_path=self.root/'imports/catalog.json';self.lock=threading.RLock();self.load()
 def load(self):
  with self.lock:
   catalog=json.loads(self.catalog_path.read_text()) if self.catalog_path.exists() else []
   datasets=[('',self.archive)]+[(x['id'],self.root/'imports'/x['id']/'work/MailArchive') for x in catalog]
   index=[];lookup={};roots={};accounts={};seen=set();hashes=set();identities=set();foldermap={};manifests=[];source_by_id={};unlinked=[];datafiles=[]
   for dataset,root in datasets:
    if not (root/'index.json').exists():continue
    roots[dataset]=root
    manifest=json.loads((root/'manifest.json').read_text());manifests.append(manifest)
    prefix=f'imports/{dataset}/' if dataset else ''
    for f in manifest.get('folders',[]):foldermap.setdefault(f['id'],dict(f,recovered=0))
    for original in json.loads((root/'index.json').read_text()):
     m=copy.deepcopy(original)
     if m['id'] in seen:continue
     seen.add(m['id']);m['accounts']=list(recipient_accounts(m.get('to','')))
     for address,name in recipient_accounts(m.get('to','')).items():
      a=accounts.setdefault(address,{'email':address,'name':name,'count':0,'unread':0,'folderCounts':{}})
      if a['name']==address and name!=address:a['name']=name
      a['count']+=1;a['unread']+=m.get('read') is False
      fid=m.get('folderId','');a['folderCounts'][fid]=a['folderCounts'].get(fid,0)+1
     try:sha=m.get('emlSha256') or hashlib.sha256((root/m['eml']).read_bytes()).hexdigest();hashes.add(sha);m['emlSha256']=sha
     except OSError:continue
     identity=message_identity(m.get('internetMessageId'))
     if not identity:
      detail=json.loads((root/'messages'/f"{m['id']}.json").read_text());identity=content_identity(m,detail.get('bodyText',''))
     identities.add(identity);m['dedupeIdentity']=identity
     m['eml']=prefix+m['eml'];m['dataset']=dataset
     for a in m.get('attachments',[]):
      if a.get('path'):a['path']=prefix+a['path']
     m['metadataPath']=prefix+'messages/'+m['id']+'.json';index.append(m);lookup[m['id']]=m;source_by_id[m['id']]=root
     f=foldermap.setdefault(m.get('folderId',''),{'id':m.get('folderId',''),'name':m.get('folder','Imported'),'recovered':0,'cachedServerTotal':None});f['recovered']+=1
    for a in manifest.get('unlinkedFiles',[]):a=copy.deepcopy(a);a['path']=prefix+a['path'];unlinked.append(a)
    for a in manifest.get('dataFiles',[]):a=copy.deepcopy(a);a['path']=prefix+a['path'];a['dataset']=dataset;datafiles.append(a)
   index.sort(key=lambda x:(datekey(x.get('date')),x['id']),reverse=True)
   base=copy.deepcopy(manifests[0]) if manifests else {'limitations':[]}
   base.update(messages=len(index),folders=list(foldermap.values()),accounts=sorted(accounts.values(),key=lambda a:(-a['count'],a['email'])),unread=sum(m.get('read') is False for m in index),statuses=dict(collections.Counter(m['status'] for m in index)),attachmentsRecovered=sum(bool(a.get('path')) for m in index for a in m.get('attachments',[])),attachmentsMissing=sum(not a.get('path') for m in index for a in m.get('attachments',[])),cachedImageRenditions=sum(a.get('cachedRendition',False) for m in index for a in m.get('attachments',[])),unlinkedFiles=unlinked,dataFiles=datafiles,imports=catalog)
   base['attachmentText']=dict(sum((collections.Counter(m.get('attachmentText',{})) for m in manifests),collections.Counter()))
   self.index=index;self.lookup=lookup;self.roots=roots;self.source_by_id=source_by_id;self.manifest=base;self.hashes=hashes;self.identities=identities;self.catalog=catalog
 def detail(self,uid):
  root=self.source_by_id.get(uid)
  if root is None:raise KeyError(uid)
  d=json.loads((root/'messages'/f'{uid}.json').read_text());d.update({k:v for k,v in self.lookup[uid].items() if k!='searchText'});return d
 def resolve(self,rel):
  parts=Path(rel).parts
  if parts and parts[0]=='imports':
   if len(parts)<3:raise FileNotFoundError(rel)
   root=self.roots.get(parts[1]);parts=parts[2:]
  else:root=self.archive
  if root is None:raise FileNotFoundError(rel)
  root=root.resolve();p=root.joinpath(*parts).resolve()
  if not p.is_relative_to(root) or not p.is_file():raise FileNotFoundError(rel)
  return p
 def add_dataset(self,job_id,summary):
  with self.lock:
   self.catalog_path.parent.mkdir(parents=True,exist_ok=True)
   entries=list(self.catalog);entries.append(dict(summary,id=job_id,created=datetime.now(timezone.utc).isoformat()))
   tmp=self.catalog_path.with_suffix('.tmp');tmp.write_text(json.dumps(entries,ensure_ascii=False,indent=2));tmp.replace(self.catalog_path)
   self.load()
 def csv_bytes(self):
  f=io.StringIO();fields=['id','eml','folder','subject','from','to','date','read','status'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
  for m in self.index:w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in m.items()})
  return ('\ufeff'+f.getvalue()).encode()
