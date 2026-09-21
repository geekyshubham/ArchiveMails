#!/usr/bin/env python3
"""Local, read-only mail archive viewer. Python standard library only."""
import argparse,json,mimetypes,re,html,threading,webbrowser
import archive_ai
from archive_store import ArchiveStore
from archive_import import ImportManager
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs,unquote,quote
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parent;ARCHIVE=ROOT/'MailArchive';ASSETS=ROOT/'viewer'
INDEX=[];LOOKUP={};MANIFEST={};CORPUS=None;STORE=None;IMPORTS=None
class SafeMail(HTMLParser):
 allowed=set('html body div span p br hr a b strong em i u s strike small big font center blockquote pre code ul ol li table thead tbody tfoot tr td th h1 h2 h3 h4 h5 h6 img sub sup section article header footer dl dt dd'.split())
 void={'br','hr','img'}
 blocked={'script','style','head','iframe','object','embed','form','svg','math','template','noscript'}
 def __init__(self,cids):super().__init__(convert_charrefs=True);self.out=[];self.skip=[];self.cids=cids
 def handle_starttag(self,tag,attrs):
  if tag in self.blocked:self.skip.append(tag);return
  if self.skip or tag not in self.allowed:return
  out=[]
  for k,v in attrs:
   if v is None:continue
   if k in ['title','alt','colspan','rowspan','align','valign','width','height','cellpadding','cellspacing','border','color','size','face','dir','lang']:
    out.append((k,v))
   elif k=='style':
    # Strip all URL-bearing and active CSS constructs; preserve ordinary typography/layout.
    if not re.search(r'url\s*\(|@import|expression\s*\(|behavior\s*:|\\',v,re.I):out.append((k,v))
   elif tag=='img' and k=='src':
    if v.lower().startswith('cid:'):
     path=self.cids.get(unquote(v[4:]).strip('<>'))
     if path:out.append(('src','/archive/'+quote(path)))
    elif re.match(r'^data:image/(png|jpeg|gif|webp);base64,',v,re.I):out.append(('src',v))
   elif tag=='a' and k=='href':out.append(('title',v))
  self.out.append('<'+tag+''.join(' '+k+'="'+html.escape(v,quote=True)+'"' for k,v in out)+'>')
 def handle_startendtag(self,t,a):self.handle_starttag(t,a)
 def handle_endtag(self,tag):
  if self.skip:
   if tag==self.skip[-1]:self.skip.pop()
   return
  if tag in self.allowed and tag not in self.void:self.out.append('</'+tag+'>')
 def handle_data(self,data):
  if not self.skip:self.out.append(html.escape(data))
def body_html(d):
 cids={a['cid'].strip('<>'):a['path'] for a in d['attachments'] if a.get('cid') and a.get('path') and a['mime'].split(';')[0] in ['image/png','image/jpeg','image/gif','image/webp']}
 parser=SafeMail(cids)
 if d.get('bodyHtml'):parser.feed(d['bodyHtml']);body=''.join(parser.out)
 else:body='<pre>'+html.escape(d.get('bodyText',''))+'</pre>'
 return '<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><style>body{margin:24px;color:#202733;background:#fff;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;overflow-wrap:anywhere}img{max-width:100%;height:auto}table{max-width:100%}pre{white-space:pre-wrap}a{color:#315baa}blockquote{margin-left:12px;padding-left:16px;border-left:2px solid #ddd}</style></head><body>'+body+'</body></html>'
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def send(self,body,mime='application/json',code=200,download=None,mail=False):
  if isinstance(body,str):body=body.encode()
  self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
  csp="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; sandbox" if mail else "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
  self.send_header('Content-Security-Policy',csp)
  if download:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(download))
  self.end_headers();self.wfile.write(body)
 def json(self,d,code=200):self.send(json.dumps(d,ensure_ascii=False),code=code)
 def do_GET(self):
  # Loopback binding and host validation also prevent DNS rebinding access to private mail.
  if self.headers.get('Host','').split(':')[0] not in ['127.0.0.1','localhost']:
   return self.json({'error':'Invalid host'},403)
  path=unquote(urlsplit(self.path).path);q=parse_qs(urlsplit(self.path).query)
  if path=='/api/manifest':return self.json(MANIFEST)
  if path=='/api/accounts':return self.json({'accounts':MANIFEST.get('accounts',[])})
  if path.startswith('/api/imports/'):
   try:return self.json(IMPORTS.get(path.rsplit('/',1)[-1]))
   except ValueError as e:return self.json({'error':str(e)},404)
  if path=='/api/ai/config':return self.json(archive_ai.config_status())
  if path=='/api/messages':
   account=q.get('account',[''])[0].casefold();terms=q.get('q',[''])[0].casefold().split();folder=q.get('folder',[''])[0];state=q.get('state',['all'])[0];status=q.get('status',['all'])[0]
   rows=[x for x in INDEX if (not account or account in x.get('accounts',[])) and (not folder or x['folderId']==folder) and (state!='unread' or x['read'] is False) and (state!='attachments' or x['attachments']) and (status=='all' or x['status']==status) and all(t in x['searchText'] for t in terms)]
   if q.get('sort',['newest'])[0]=='oldest':rows=list(reversed(rows))
   try:offset=max(0,int(q.get('offset',['0'])[0]));limit=min(100,max(1,int(q.get('limit',['60'])[0])))
   except ValueError:return self.json({'error':'Invalid pagination'},400)
   return self.json({'total':len(rows),'items':[{k:v for k,v in x.items() if k!='searchText'} for x in rows[offset:offset+limit]]})
  if path.startswith('/api/message/') or path.startswith('/body/'):
   uid=path.rsplit('/',1)[-1]
   if uid not in LOOKUP:return self.json({'error':'Message not found'},404)
   d=STORE.detail(uid)
   if path.startswith('/body/'):return self.send(body_html(d),'text/html; charset=utf-8',mail=True)
   return self.json(d)
  if path.startswith('/archive/'):
   rel=path[len('/archive/'):]
   if rel=='manifest.json':return self.send(json.dumps(MANIFEST,ensure_ascii=False,indent=2),download='manifest.json')
   if rel=='index.csv':return self.send(STORE.csv_bytes(),'text/csv; charset=utf-8',download='index.csv')
   try:p=STORE.resolve(rel)
   except FileNotFoundError:return self.json({'error':'File not found'},404)
   mime=mimetypes.guess_type(p.name)[0] or 'application/octet-stream';inline='download' not in q and rel.startswith('attachments/') and mime in ['image/png','image/jpeg','image/gif','image/webp']
   return self.send(p.read_bytes(),mime,download=None if inline else p.name)
  assets={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/tokens.css':'tokens.css'}
  if path in assets:
   p=ASSETS/assets[path]
   return self.send(p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'text/plain')
  self.json({'error':'Not found'},404)
 def do_POST(self):
  host=self.headers.get('Host','')
  if host.split(':')[0] not in ['127.0.0.1','localhost'] or self.headers.get('Origin')!='http://'+host or self.headers.get('X-Archive-Request')!='1':
   return self.json({'error':'Only requests from the local archive app are accepted.'},403)
  if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.json({'error':'JSON required'},415)
  try:
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=200000:raise ValueError('Invalid request size')
   data=json.loads(self.rfile.read(length))
   if not isinstance(data,dict):raise ValueError('Expected a JSON object')
   path=urlsplit(self.path).path
   if path=='/api/ai/config':result=archive_ai.configure(data)
   elif path=='/api/ai/models':result=archive_ai.models()
   elif path=='/api/ai/chat':result=archive_ai.chat(CORPUS,data)
   elif path=='/api/imports':result=IMPORTS.new(data.get('name','Imported folder'))
   elif path.startswith('/api/imports/') and path.endswith('/start'):result=IMPORTS.start(path.split('/')[3])
   elif path.startswith('/api/imports/') and path.endswith('/cancel'):result=IMPORTS.cancel(path.split('/')[3])
   else:return self.json({'error':'Not found'},404)
   self.json(result)
  except archive_ai.GatewayError as e:self.json({'error':str(e),'code':e.code,'action':'change_model'},502)
  except (ValueError,TypeError) as e:self.json({'error':str(e)},400)
  except Exception:self.json({'error':'Request failed. Check the local server and try again.'},502)

 def do_PUT(self):
  host=self.headers.get('Host','')
  if host.split(':')[0] not in ['127.0.0.1','localhost'] or self.headers.get('Origin')!='http://'+host or self.headers.get('X-Archive-Request')!='1':return self.json({'error':'Only the local app can upload files.'},403)
  path=urlsplit(self.path).path;query=parse_qs(urlsplit(self.path).query)
  if not re.fullmatch(r'/api/imports/[a-f0-9]{32}/file',path):return self.json({'error':'Not found'},404)
  try:
   result=IMPORTS.upload(path.split('/')[3],query.get('path',[''])[0],self.rfile,int(self.headers.get('Content-Length','-1')));self.json(result)
  except (ValueError,OSError) as e:self.close_connection=True;self.json({'error':str(e)},400)

def reload_archive():
 global INDEX,LOOKUP,MANIFEST,CORPUS
 new_corpus=archive_ai.Corpus(ARCHIVE,STORE.index,STORE.manifest,store=STORE)
 INDEX,LOOKUP,MANIFEST,CORPUS=STORE.index,STORE.lookup,STORE.manifest,new_corpus

def main():
 global INDEX,LOOKUP,MANIFEST,CORPUS,STORE,IMPORTS
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--open',action='store_true');args=parser.parse_args()
 ARCHIVE.mkdir(parents=True,exist_ok=True)  # Fresh installations start empty; import through the UI.
 STORE=ArchiveStore(ROOT);reload_archive();IMPORTS=ImportManager(ROOT,STORE,reload_archive)
 server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);url=f'http://127.0.0.1:{args.port}'
 print(f'Mail Archive: {url} — {len(INDEX):,} messages. Press Ctrl+C to stop.',flush=True)
 if args.open:threading.Timer(.4,lambda:webbrowser.open(url)).start()
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
if __name__=='__main__':main()
