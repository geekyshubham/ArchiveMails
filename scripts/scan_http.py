import sys,json,collections,gzip,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/ccl_chromium_reader'))
from ccl_chromium_reader import ccl_chromium_cache as cc
from urllib.parse import urlsplit,parse_qs,unquote
p=Path('snapshot/Olk/EBWebView/Default')
c=cc.ChromiumBlockFileCache(p/'Cache/Cache_Data')
keys=list(c.keys());print('HTTP cache entries',len(keys),flush=True)
print('endpoints',collections.Counter(urlsplit(k[k.find('http'):]).path for k in keys).most_common(20),flush=True)
out=[];errors=[]
for i,k in enumerate(keys):
 try:
  if any(s in k.lower() for s in ['attachment','getfile','service.svc']):
   m=c.get_metadata(k);data=c.get_cachefile(k)
   out.append({'key':k,'headers':[list(x.http_header_attributes) if x else [] for x in m],'sizes':[len(x) if x else 0 for x in data],'locations':[str(x) for x in c.get_location_for_cachefile(k)]})
 except Exception as e:errors.append({'index':i,'error':str(e)})
Path('recovery/http-index.json').write_text(json.dumps(out,default=str));print('interesting',len(out),'errors',len(errors),flush=True)
print('samples',[(urlsplit(x['key'][x['key'].find('http'):]).path,list(parse_qs(urlsplit(x['key']).query)),x['sizes']) for x in out[:10]],flush=True)
print('service worker dirs',[(str(d.relative_to(p)),len(list(d.iterdir()))) for d in (p/'Service Worker/CacheStorage').glob('*/*') if d.is_dir()][:30],flush=True)
