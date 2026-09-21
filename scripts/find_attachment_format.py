import gzip,zlib,brotli,re
from pathlib import Path
from ccl_chromium_reader import ccl_chromium_cache as cc
c=cc.ChromiumBlockFileCache(Path('snapshot/Olk/EBWebView/Default/Cache/Cache_Data'))
count=0
for k in c.keys():
 if not k.endswith('.js'):continue
 try:
  d=c.get_cachefile(k)[0];m=c.get_metadata(k)[0]
  enc=(m.get_attribute('content-encoding') or [''])[0]
  if enc=='gzip':d=gzip.decompress(d)
  elif enc=='br':d=brotli.decompress(d)
  if not d or b'thumbnailType' not in d:continue
  s=d.decode('utf-8','replace')
  for match in re.finditer('thumbnailType',s):
   context=s[max(0,match.start()-180):match.end()+250]
   if any(x in context for x in ['"0"','"2"','Thumbnail','thumbnailType:', 'thumbnailType=']):print(context)
  count+=1
 except Exception:pass
print('files',count)
