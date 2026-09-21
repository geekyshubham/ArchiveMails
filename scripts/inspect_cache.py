import sys,json,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/ccl_chromium_reader'))
from ccl_chromium_reader import ccl_chromium_indexeddb as idb
p=Path('snapshot/Olk/EBWebView/Default/IndexedDB/https_outlook.office.com_0.indexeddb.leveldb')
w=idb.WrappedIndexDB(p,p.with_suffix('.blob'))
for d in w.database_ids:
 db=w[d.dbid_no];print(d.dbid_no,db.name,list(db.object_store_names),flush=True)
for di,sn in [(3,'folders'),(3,'messages'),(3,'messageBodies'),(16,'attachments'),(14,'images')]:
 errs=[];records=[]
 for r in w[di][sn].iterate_records(bad_deserializer_data_handler=lambda k,v:errs.append(str(k))):
  records.append({'key':r.key.value,'value':r.value,'seq':r.ldb_seq_no,'live':r.is_live,'source':str(r.origin_file),'blob':r.external_value_path})
 Path(f'recovery/{sn}.json').write_text(json.dumps(records,default=str,ensure_ascii=False))
 vals=[r for r in records if r['value'] is not None]
 print(sn,'records',len(records),'values',len(vals),'errors',len(errs),flush=True)
 for r in vals[:1]:
  v=r['value'];print('sample key',str(r['key'])[:60],'shape',[(k,type(x).__name__,len(x) if isinstance(x,(str,list,dict)) else x) for k,x in v.items()] if isinstance(v,dict) else str(v)[:1000],flush=True)
 Path(f'recovery/{sn}-errors.json').write_text(json.dumps(errs))
