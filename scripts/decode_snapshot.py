import os
"""Read copied Chromium stores without opening Outlook or a LevelDB writer."""
import sys,json,io,hashlib,datetime,collections,gzip,zlib
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
CODE_ROOT=Path(__file__).resolve().parents[1]
ROOT=Path(os.environ.get('MDUMP_WORK_ROOT',str(CODE_ROOT))).resolve()
sys.path.insert(0,str(CODE_ROOT/'vendor/ccl_chromium_reader'))
from ccl_chromium_reader import ccl_chromium_indexeddb as idb,ccl_chromium_cache as cache
from ccl_chromium_reader.serialization_formats import ccl_blink_value_deserializer as blink,ccl_v8_value_deserializer as v8
# V8 kOneByteString is Latin-1, not arbitrary binary. The upstream reader
# returns bytes for non-ASCII strings; decode this tag without touching ArrayBuffers.
def _one_byte_string(self):
 length=self._read_le_varint()[0]
 return self._read_raw(length).decode('latin-1')
v8.Deserializer._read_one_byte_string=_one_byte_string
REC=ROOT/'recovery';REC.mkdir(parents=True,exist_ok=True);BIN=REC/'binary';BIN.mkdir(exist_ok=True)
PROFILE=ROOT/'snapshot/Olk/EBWebView/Default'
def savebinary(data):
 sha=hashlib.sha256(data).hexdigest();p=BIN/sha
 if not p.exists():p.write_bytes(data)
 return {'binary':str(p.relative_to(ROOT)),'sha256':sha,'bytes':len(data)}
def clean(v,record=None):
 if isinstance(v,blink.BlobIndex):
  try:
   info=record.resolve_blob_index(v)
   with record.get_blob_stream(v) as f:r=savebinary(f.read())
   return dict(r,mime=getattr(info,'mime_type',None))
  except Exception as e:return {'blob_error':type(e).__name__}
 if isinstance(v,dict):return {str(k):clean(x,record) for k,x in v.items() if type(x).__name__!='_Undefined'}
 if isinstance(v,(list,tuple)):return [clean(x,record) for x in v]
 if isinstance(v,bytes):return savebinary(v)
 if isinstance(v,(datetime.datetime,datetime.date)):return v.isoformat()
 if isinstance(v,idb.IdbKey):return clean(v.value,record)
 if v is None or isinstance(v,(str,int,float,bool)):return v
 return str(v)
def dump(name,rs): (REC/(name+'.json')).write_text(json.dumps(rs,ensure_ascii=False,default=str))
errors=[];inventory=[]
allstores={};orphans=[];blobtypes=collections.Counter()
databases=list((PROFILE/'IndexedDB').glob('*outlook*.indexeddb.leveldb'))
if not databases:raise SystemExit('No Outlook IndexedDB database found in the selected snapshot.')
for database_path in databases:
 w=idb.WrappedIndexDB(database_path,database_path.with_suffix('.blob'))
 for di in w.database_ids:
  db=w[di.dbid_no]
  if not any(s in db.name for s in ['owa-offline-data-','owa-image-data-','owa-attachment-data-']):continue
  for store in db:
   if store.name in ['syncLogs','syncState','settings','pgal','pgalTags','directoryHandles']:continue
   rs=[]
   def bad(k,v):errors.append({'store':store.name,'key':str(k),'error':'record could not be decoded','bytes':len(v)})
   for r in store.iterate_records(bad_deserializer_data_handler=bad):
    rs.append({'key':clean(r.key.value),'value':clean(r.value,r),'seq':r.ldb_seq_no,'live':r.is_live,'source':str(Path(r.origin_file).relative_to(ROOT)),'blob':r.external_value_path})
   allstores.setdefault(store.name,[]).extend(rs);inventory.append({'database':di.dbid_no,'store':store.name,'records':len(rs)})
   print(store.name,len(rs),flush=True)
 # Check detached blob payloads too; preserve candidates separately as historical evidence.
 for p in database_path.with_suffix('.blob').rglob('*'):
  if not p.is_file():continue
  data=p.read_bytes()
  if not data.startswith(b'\xff'):continue
  try:
   result=w._raw_db.read_record_precursor(None,0,0,data,None)
   if not result:continue
   value=v8.Deserializer(result[1],host_object_delegate=blink.BlinkV8Deserializer().read).read()
   if isinstance(value,dict):
    blobtypes[value.get('__typename','other')]+=1
    if isinstance(value.get('ItemId'),dict) and any(value.get(k) for k in ['Body','NormalizedBody']):
     orphans.append({'key':value['ItemId'].get('Id'),'value':clean(value),'seq':-1,'live':False,'source':str(p.relative_to(ROOT)),'blob':None})
  except Exception:pass # Non-serialized image/file blobs are expected here.
 w.close()
for name,rs in allstores.items():dump(name,rs)
dump('detached-message-candidates',orphans)
print('detached candidates',len(orphans),flush=True)
# Resolve attachment bytes through their explicit cached request IDs.
c=cache.ChromiumBlockFileCache(PROFILE/'Cache/Cache_Data') if (PROFILE/'Cache/Cache_Data/index').exists() else None
attached=[];types=collections.Counter()
for key in c.keys() if c else []:
 try:
  md=c.get_metadata(key)[0]
  mime=(md.get_attribute('content-type') or [''])[0] if md else ''
  types[mime.split(';')[0]]+=1
  if 'GetFileAttachment' not in key:continue
  q=parse_qs(urlsplit(key).query);aid=q.get('id',[''])[0]
  data=c.get_cachefile(key)[0]
  if not data:continue
  decl=list(md.http_header_declarations) if md else []
  if not any(x.split()[1:2] == ['200'] for x in decl):continue
  if mime.startswith(('text/html','application/json')):continue
  enc=(md.get_attribute('content-encoding') or [''])[0]
  if enc=='gzip':data=gzip.decompress(data)
  elif enc=='br':
   import brotli;data=brotli.decompress(data)
  attached.append(dict(savebinary(data),attachmentId=aid,mime=mime.split(';')[0],disposition=md.get_attribute('content-disposition'),source='HTTP cache',location=[str(x) for x in c.get_location_for_cachefile(key)]))
 except Exception as e:errors.append({'store':'HTTP cache','error':type(e).__name__})
dump('http-attachments',attached)
# Service Worker stores: inventory cache keys to distinguish application assets from mail data.
sw=[]
for directory in (PROFILE/'Service Worker/CacheStorage').glob('*/*'):
 if not directory.is_dir():continue
 try:
  sc=cache.ChromiumSimpleFileCache(directory);keys=list(sc.keys())
  sw.append({'path':str(directory.relative_to(ROOT)),'entries':len(keys),'paths':dict(collections.Counter(urlsplit(k).path.split('/')[-1].split('.')[0] for k in keys))})
 except Exception as e:errors.append({'store':'Service Worker','error':type(e).__name__,'path':str(directory.relative_to(ROOT))})
dump('service-worker-inventory',sw);dump('decode-errors',errors);dump('store-inventory',inventory)
print('HTTP attachments',len(attached),'errors',len(errors),'HTTP types',dict(types),flush=True)
