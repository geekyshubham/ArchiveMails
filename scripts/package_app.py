"""Package the app, recovery code and committed archives, excluding credentials and staging data."""
from pathlib import Path
import zipfile,json
ROOT=Path(__file__).resolve().parents[1]
files=[ROOT/n for n in ['serve.py','archive_ai.py','archive_store.py','archive_import.py','README.md','requirements-recovery.txt','Open Mail Archive.command','Open Mail Archive.bat']]
for directory in ['viewer','MailArchive','scripts','tests','vendor/ccl_chromium_reader']:
 files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and not any(part in ['.git','__pycache__','build','ccl_chromium_reader.egg-info'] for part in p.parts) and p.suffix!='.pyc')
catalog=ROOT/'imports/catalog.json'
if catalog.exists():
 files.append(catalog)
 for item in json.loads(catalog.read_text()):files.extend(p for p in (ROOT/'imports'/item['id']/'work/MailArchive').rglob('*') if p.is_file())
target=ROOT/'Mail Archive - Portable.zip';temp=target.with_suffix('.tmp.zip')
with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
 for p in sorted(set(files)):z.write(p,Path('Mail Archive')/p.relative_to(ROOT))
with zipfile.ZipFile(temp) as z:
 bad=z.testzip()
 if bad:raise RuntimeError('Invalid ZIP entry: '+bad)
temp.replace(target);print(f'Packaged {len(set(files))} files; {target.stat().st_size:,} bytes')
