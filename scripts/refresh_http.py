"""Read copied Chromium stores without opening Outlook or a LevelDB writer."""
import sys,json,io,hashlib,datetime,collections,gzip,zlib
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/ccl_chromium_reader'))
from ccl_chromium_reader import ccl_chromium_indexeddb as idb,ccl_chromium_cache as cache
from ccl_chromium_reader.serialization_formats import ccl_blink_value_deserializer as blink,ccl_v8_value_deserializer as v8
REC=ROOT/'recovery';REC.mkdir(exist_ok=True);BIN=REC/'binary';BIN.mkdir(exist_ok=True)
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

errors=[]
c=cache.ChromiumBlockFileCache(PROFILE/'Cache/Cache_Data');attached=[];types=collections.Counter()
for key in c.keys():
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

print(len(attached),len(errors))
