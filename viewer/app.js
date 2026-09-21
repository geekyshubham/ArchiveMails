'use strict';
const $=id=>document.getElementById(id);
const state={manifest:null,account:'',folder:'',name:'All mail',q:'',filter:'all',sort:'newest',offset:0,total:0,items:[],selected:null,version:0,detailVersion:0};
const fmt=n=>Number(n).toLocaleString();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const size=n=>n==null?'Size unknown':n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';
const shortDate=d=>d?new Date(d).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'2-digit'}):'No date';
const longDate=d=>d?new Date(d).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):'Unknown';
const labels={recovered:'Body & cached attachments recovered',attachment_missing:'Body recovered · attachment missing',partial:'Partial recovery'};
const download=p=>'/archive/'+p.split('/').map(encodeURIComponent).join('/');
function error(e){$('error').textContent=e.message||String(e);$('error').hidden=false;setTimeout(()=>$('error').hidden=true,8000)}
async function api(path){const r=await fetch(path);if(!r.ok)throw Error('Could not load the archive. Check that the local server is running.');return r.json()}
function folderNav(){
 const icons={'Inbox':'▣','Sent Items':'↗','Deleted Items':'⌫','Junk Email':'⊘','Archive':'▤'};
 const account=(state.manifest.accounts||[]).find(a=>a.email===state.account);
 const folders=state.manifest.folders.map(f=>({...f,recovered:account?(account.folderCounts[f.id]||0):f.recovered})).filter(x=>x.recovered).sort((a,b)=>['Inbox','Sent Items','Deleted Items','Archive','Junk Email'].indexOf(a.name)-['Inbox','Sent Items','Deleted Items','Archive','Junk Email'].indexOf(b.name));
 $('folders').innerHTML=[{id:'',name:'All mail',recovered:account?account.count:state.manifest.messages},...folders].map(f=>`<button class="nav-button ${state.folder===f.id?'active':''}" data-folder="${esc(f.id)}" data-name="${esc(f.name)}" ${state.folder===f.id?'aria-current="page"':''}><span class="folder-icon" aria-hidden="true">${icons[f.name]||'▦'}</span>${esc(f.name)}<span class="nav-count">${fmt(f.recovered)}</span></button>`).join('');
 $('folders').querySelectorAll('button').forEach(b=>b.onclick=()=>{state.folder=b.dataset.folder;state.name=b.dataset.name;state.offset=0;document.body.classList.remove('folders-open','message-open');$('menu').setAttribute('aria-expanded','false');folderNav();loadList()});
}
async function loadList(){
 const version=++state.version;$('list').setAttribute('aria-busy','true');$('folder-title').textContent=state.q?'Search results':state.name;
 const q=new URLSearchParams({q:state.q,account:state.account,folder:state.folder,state:state.filter,sort:state.sort,offset:state.offset,limit:60});
 try{const result=await api('/api/messages?'+q);if(version!==state.version)return;state.items=result.items;state.total=result.total;renderList();}
 catch(e){if(version===state.version){error(e);$('list').innerHTML='<div class="list-empty"><strong>Unable to load messages</strong><p>Check your local server, then reload this page.</p><button id="retry">Try again</button></div>';$('retry').onclick=loadList;}}
 finally{if(version===state.version)$('list').setAttribute('aria-busy','false')}
}
function renderList(){
 $('result-count').textContent=fmt(state.total);$('clear').hidden=!state.q;
 $('list').innerHTML=state.items.map(m=>`<button class="mail-row ${m.read===false?'unread':''} ${m.id===state.selected?'selected':''}" data-id="${m.id}" aria-label="${esc((m.read===false?'Unread: ':'')+m.subject)}" aria-pressed="${m.id===state.selected}"><div class="row-top"><span class="row-sender">${m.read===false?'<span class="unread-dot"></span>':''}${esc(m.from.split('<')[0].trim().replace(/^"|"$/g,'')||'Unknown sender')}</span><time class="row-date">${esc(shortDate(m.date))}</time></div><div class="row-subject">${esc(m.subject)}</div><div class="row-preview">${esc(m.preview||'Open recovered message')}</div><div class="row-bottom"><span class="row-folder">${esc(m.folder)}</span>${m.historical?'<span>Historical record</span>':''}${m.status!=='recovered'?'<span>Missing attachments</span>':''}${m.attachments.length?`<span class="row-att">↳ ${m.attachments.length}</span>`:''}</div></button>`).join('')||'<div class="list-empty"><strong>No messages found</strong><p>Try another search or change the filters.</p></div>';
 $('list').querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>openMessage(b.dataset.id));$('list').scrollTop=0;
 $('page-info').textContent=state.total?`${fmt(state.offset+1)}–${fmt(Math.min(state.offset+60,state.total))} of ${fmt(state.total)}`:'0 messages';$('prev').disabled=state.offset===0;$('next').disabled=state.offset+60>=state.total;
}
async function openMessage(id){
 const version=++state.detailVersion;state.selected=id;
 $('list').querySelectorAll('[data-id]').forEach(b=>{b.classList.toggle('selected',b.dataset.id===id);b.setAttribute('aria-pressed',String(b.dataset.id===id))});
 try{const d=await api('/api/message/'+id);if(version!==state.detailVersion)return;
 $('empty-reader').hidden=true;$('message').hidden=false;document.body.classList.add('message-open');
 $('subject').textContent=d.subject;$('from').textContent=d.from||'Unknown sender';$('to').textContent='To: '+(d.to||'Not cached');$('date').textContent=longDate(d.date);$('date').dateTime=d.date;$('message-folder').textContent=d.folder;
 $('avatar').textContent=(d.from.replace(/^"/,'').match(/\b[A-Za-z]/g)||['?']).slice(0,2).join('').toUpperCase();$('message-status').textContent=labels[d.status];$('message-status').className='status '+(d.status!=='recovered'?'warning':'');$('download-eml').href=download(d.eml);
 const details={'From':d.from,'To':d.to,'Cc':d.cc,'Bcc':d.bcc,'Received':longDate(d.date),'Sent':longDate(d.sent),'Snapshot state':d.read===true?'Read':d.read===false?'Unread':'Unknown','Message ID':d.internetMessageId||'Not cached','Body source':d.bodySource||'Preview only','Importance':d.importance||'Unknown'};
 $('details').innerHTML=Object.entries(details).filter(([,v])=>v).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')+`<dt>Source data</dt><dd><a href="${download(d.metadataPath||'messages/'+d.id+'.json')}" download>Download metadata & provenance</a></dd>`;
 $('notes').innerHTML=d.notes.map(n=>`<p class="note">${esc(n)}</p>`).join('');
 $('attachments').innerHTML=d.attachments.map(a=>a.path?`<a class="attachment" href="${download(a.path)}?download=1" download="${esc(a.name)}"><span aria-hidden="true">↳</span><div><strong>${esc(a.name)}</strong><small>${size(a.size)}${a.inline?' · inline image':''}${a.cachedRendition?' · cached rendition':''} · Download</small></div></a>`:`<div class="attachment missing"><span>↳</span><div><strong>${esc(a.name)}</strong><small>${size(a.size)} · Not cached</small></div></div>`).join('');
 $('body-frame').src='/body/'+id;$('body-text').textContent=d.bodyText||'No body available.';bodyTab('html');document.querySelector('.reading-pane').scrollTop=0;
 }catch(e){error(e)}
}
function bodyTab(tab){const formatted=tab==='html';$('body-frame').hidden=!formatted;$('body-text').hidden=formatted;$('html-tab').setAttribute('aria-pressed',String(formatted));$('text-tab').setAttribute('aria-pressed',String(!formatted))}
function dialog(title,body){$('dialog-title').textContent=title;$('dialog-body').innerHTML=body;$('dialog').showModal()}
function report(){const m=state.manifest;dialog('Recovery report',`<div class="metrics"><div class="metric"><strong>${fmt(m.messages)}</strong><span>recovered messages</span></div><div class="metric"><strong>${fmt(m.attachmentsRecovered)}</strong><span>attachment instances recovered</span></div><div class="metric"><strong>${fmt(m.attachmentsMissing)}</strong><span>attachment instances missing</span></div></div><p>This is a reconstruction of locally cached Outlook data. A recovered body can differ from the original server message. Folder totals below came from cached Outlook metadata.</p><div class="table-wrap"><table class="report-table"><thead><tr><th>Folder</th><th>Recovered</th><th>Cached server total</th></tr></thead><tbody>${m.folders.filter(f=>f.recovered||f.cachedServerTotal).map(f=>`<tr><td>${esc(f.name)}</td><td>${fmt(f.recovered)}</td><td>${f.cachedServerTotal==null?'Unknown':fmt(f.cachedServerTotal)}</td></tr>`).join('')}</tbody></table></div><p>${fmt(m.cachedImageRenditions||0)} recovered attachment instances are cached image renditions; their original files could differ. ${fmt(m.unlinkedFiles.length)} additional files were preserved without a confident message match.</p><p>${fmt(m.unread)} messages were unread in the snapshot. Opening them here does not change that state.</p>${m.limitations.map(x=>`<p>• ${esc(x)}</p>`).join('')}<div class="report-links"><a href="${download('manifest.json')}" download>Download manifest</a><a href="${download('index.csv')}" download>Download email index (CSV)</a></div>`)}
async function files(){
 dialog('Attachment library','<p role="status">Loading attachment library…</p>');
 try{
  // Fetch all metadata pages; bodies are never needed for the library.
  const account=(state.manifest.accounts||[]).find(a=>a.email===state.account);let items=[];for(let offset=0;offset<(account?account.count:state.manifest.messages);offset+=100){const r=await api('/api/messages?limit=100&offset='+offset+'&account='+encodeURIComponent(state.account));items.push(...r.items)}
  const unique=new Map();for(const m of items)for(const a of m.attachments)if(a.path&&!unique.has(a.path))unique.set(a.path,{...a,subject:m.subject});
  const all=[...unique.values()];const unlinked=state.account?[]:state.manifest.unlinkedFiles;$('dialog-body').innerHTML=`<p>${fmt(all.length)} distinct recovered files. Inline images are included. Files without a confident message match are listed separately below.</p><input class="library-search" id="file-search" aria-label="Search attachments" placeholder="Search filenames or message subjects"><div id="file-results"></div><h3>Unlinked cached files</h3><p>${state.account?'Switch to All accounts to see files without a known recipient.':fmt(unlinked.length)+' files preserved without guessing which message they belong to.'}</p><div>${unlinked.map(f=>`<div class="file-entry"><a download href="${download(f.path)}">${esc(f.path.split('/').pop())}</a><span>${size(f.bytes)}</span></div>`).join('')}</div>`;
  const render=()=>{const q=$('file-search').value.toLowerCase();const matches=all.filter(a=>(a.name+' '+a.subject).toLowerCase().includes(q));$('file-results').innerHTML=matches.map(a=>`<div class="file-entry"><div><a href="${download(a.path)}?download=1" download="${esc(a.name)}">${esc(a.name)}</a><p>${esc(a.subject)}</p></div><span>${size(a.size)}</span></div>`).join('')||'<p>No matching files.</p>'};$('file-search').oninput=render;render();
 }catch(e){error(e)}
}
function otherData(){dialog('Other recovered data',`<p>These records were cached alongside the mail. Calendar entries and supporting metadata are available as JSON, preserving their original fields and record versions. Counts include historical versions.</p>${state.manifest.dataFiles.map(f=>`<div class="file-entry"><a href="${download(f.path)}" download>${esc(f.name)}.json ↓</a><span>${fmt(f.records)} records</span></div>`).join('')}`)}
let debounce;$('search').oninput=()=>{clearTimeout(debounce);debounce=setTimeout(()=>{state.q=$('search').value.trim();state.offset=0;loadList()},180)};
$('state').onchange=()=>{state.filter=$('state').value;state.offset=0;loadList()};$('sort').onchange=()=>{state.sort=$('sort').value;state.offset=0;loadList()};$('clear').onclick=()=>{$('search').value='';state.q='';state.offset=0;loadList()};
$('prev').onclick=()=>{state.offset=Math.max(0,state.offset-60);loadList()};$('next').onclick=()=>{state.offset+=60;loadList()};$('back').onclick=()=>document.body.classList.remove('message-open');
$('menu').onclick=()=>{const on=document.body.classList.toggle('folders-open');$('menu').setAttribute('aria-expanded',String(on))};$('html-tab').onclick=()=>bodyTab('html');$('text-tab').onclick=()=>bodyTab('text');$('report').onclick=report;$('data').onclick=otherData;$('files').onclick=files;$('close-dialog').onclick=()=>$('dialog').close();
$('dialog').addEventListener('click',e=>{if(e.target===$('dialog')){const r=$('dialog').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('dialog').close()}});
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('search').focus()}if(e.key==='Escape')document.body.classList.remove('folders-open');});
(async()=>{try{state.manifest=await api('/api/manifest');renderAccounts();folderNav();$('archive-count').textContent=fmt(state.manifest.messages)+' messages · saved locally';await loadList()}catch(e){error(e)}})();

let aiHistory=[],aiBusy=false,aiConfig=null;
async function post(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Archive-Request':'1'},body:JSON.stringify(data)});const result=await r.json();if(!r.ok){const e=Error(result.error||'Request failed');e.action=result.action;e.code=result.code;throw e}return result}
async function aiStatus(){aiConfig=await api('/api/ai/config');$('ai-connection').textContent=aiConfig.configured?(providerName(aiConfig.provider)?providerName(aiConfig.provider)+' · ':'')+aiConfig.model+' · VibeRouter':'Configure VibeRouter to start';return aiConfig}
async function openChat(){
 $('chat-panel').hidden=false;document.body.classList.remove('folders-open');$('menu').setAttribute('aria-expanded','false');
 for(const id of ['ask-ai','ask-ai-top'])$(id).setAttribute('aria-expanded','true');
 $('chat-input').focus();try{await aiStatus()}catch(e){error(e)}
}
function closeChat(){
 $('chat-panel').hidden=true;for(const id of ['ask-ai','ask-ai-top'])$(id).setAttribute('aria-expanded','false');
 if(location.hash==='#chat')history.replaceState(null,'',location.pathname+location.search);
}
$('ask-ai').onclick=openChat;$('ask-ai-top').onclick=openChat;
$('close-chat').onclick=()=>{closeChat();$('ask-ai-top').focus()};
$('report-sidebar').onclick=report;
window.addEventListener('hashchange',()=>{if(location.hash==='#chat')openChat()});
if(location.hash==='#chat')openChat();
$('clear-chat').onclick=()=>{if(aiBusy)return;aiHistory=[];$('chat-log').innerHTML='<div class="chat-welcome"><h3>A fresh conversation.</h3><p>Ask about anything in the recovered archive.</p></div>'};
function chatBubble(role,text){const node=document.createElement('div');node.className='chat-bubble '+role;const speaker=document.createElement('div');speaker.className='speaker';speaker.textContent=role==='user'?'YOU':'ARCHIVE ASSISTANT';const answer=document.createElement('div');answer.className='chat-answer';answer.textContent=text;node.append(speaker,answer);$('chat-log').append(node);$('chat-log').scrollTop=$('chat-log').scrollHeight;return node}
function sourceElement(source,label){let node;if(source.mailId){node=document.createElement('button');node.onclick=()=>{openMessage(source.mailId);closeChat()}}else{node=document.createElement('a');node.href=download(source.path||'manifest.json');node.download=''}node.className=label?'source-link':'source-entry';node.textContent=label||source.title||source.id;if(!label){const sub=document.createElement('small');sub.textContent=[source.kind,source.folder,source.date?shortDate(source.date):''].filter(Boolean).join(' · ');node.append(sub)}return node}
async function ask(question){if(aiBusy)return;const welcome=$('chat-log').querySelector('.chat-welcome');if(welcome)welcome.remove();chatBubble('user',question);const bubble=chatBubble('assistant','Searching the archive and reading relevant sources…');const content=bubble.querySelector('.chat-answer');aiBusy=true;$('account-select').disabled=true;$('account-search').disabled=true;$('chat-submit').disabled=true;$('clear-chat').disabled=true;$('chat-submit').textContent='Reading…';
 try{await aiStatus();const result=await post('/api/ai/chat',{question,history:aiHistory,account:state.account});content.textContent='';const sources=new Map(result.sources.map(s=>[s.id,s]));const parts=result.answer.split(/(\[[a-z]+:[a-zA-Z0-9_-]+\])/g);for(const part of parts){const key=part.slice(1,-1);if(sources.has(key))content.append(sourceElement(sources.get(key),'[source]'));else if(key==='archive:statistics'){const b=document.createElement('button');b.className='source-link';b.textContent='[archive statistics]';b.onclick=report;content.append(b)}else appendRichText(content,part)}
 if(result.sources.length){const list=document.createElement('div');list.className='sources';for(const s of result.sources)list.append(sourceElement(s));bubble.append(list)}
 const log=document.createElement('details');log.className='research-log';const summary=document.createElement('summary');summary.textContent=result.trace.length+' archive operations · '+fmt(result.tokens)+' tokens';log.append(summary);const ol=document.createElement('ol');for(const t of result.trace){const li=document.createElement('li');li.textContent=t.tool+(t.arguments.query?' — '+t.arguments.query:'')+(t.matches!=null?' ('+fmt(t.matches)+' matches)':'');ol.append(li)}log.append(ol);bubble.append(log);aiHistory.push({role:'user',content:question},{role:'assistant',content:result.answer});
 }catch(e){content.textContent=e.message;const retry=document.createElement('button');retry.className='text-button';retry.textContent='Try again';retry.onclick=()=>ask(question);bubble.append(retry);if(e.action==='change_model'){const change=document.createElement('button');change.className='text-button';change.textContent='Change model';change.onclick=()=>$('ai-settings').click();bubble.append(change)}}finally{aiBusy=false;$('account-select').disabled=false;$('account-search').disabled=false;$('chat-submit').disabled=false;$('clear-chat').disabled=false;$('chat-submit').textContent='Ask ↑';$('chat-log').scrollTop=$('chat-log').scrollHeight}
}
$('chat-form').onsubmit=e=>{e.preventDefault();const q=$('chat-input').value.trim();if(q&&!aiBusy){$('chat-input').value='';ask(q)}};
$('chat-input').onkeydown=e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();$('chat-form').requestSubmit()}};
document.querySelectorAll('.suggestion').forEach(b=>b.onclick=()=>ask(b.textContent));
const providerNames={openai:'OpenAI',anthropic:'Anthropic',xai:'xAI',antigravity:'Antigravity', 'opencode-go':'OpenCode Go'};
function providerName(id){return providerNames[id]||id||''}
$('change-model').onclick=()=>$('ai-settings').click();
$('ai-settings').onclick=async()=>{
 try{
  const c=await aiStatus();dialog('Choose provider & model',`<div class="ai-settings"><p>Models come from the VibeRouter app on this Mac. Selecting a provider filters the available models; VibeRouter routes the selected model.</p><label for="ai-provider">Provider</label><select id="ai-provider" disabled><option>Loading providers…</option></select><label for="ai-model">Model</label><select id="ai-model" disabled><option>${esc(c.model)}</option></select><details class="connection-details"><summary>Connection settings</summary><label for="ai-base">Local API endpoint</label><input id="ai-base" value="${esc(c.base_url)}" readonly><label for="ai-key">API key (only if required by the local gateway)</label><input id="ai-key" type="password" autocomplete="off" placeholder="Leave blank to keep the current connection"><p>Keys stay in server memory. Provider and model preferences are saved locally.</p></details><div class="ai-settings-actions"><button id="ai-load-models">Refresh models</button><button id="ai-save" disabled>Use this model</button></div><p id="ai-settings-status" class="ai-settings-status" role="status">Loading models from VibeRouter…</p></div>`);
  let catalog=[];
  const fillModels=()=>{const list=catalog.filter(m=>m.provider===$('ai-provider').value);$('ai-model').innerHTML=list.map(m=>`<option value="${esc(m.id)}">${esc(m.id)}</option>`).join('');if(list.some(m=>m.id===c.model))$('ai-model').value=c.model;$('ai-model').disabled=!list.length;$('ai-save').disabled=!list.length};
  const load=async()=>{const button=$('ai-load-models');button.disabled=true;try{const key=$('ai-key').value;if(key){await post('/api/ai/config',{base_url:c.base_url,model:c.model,provider:c.provider,api_key:key});$('ai-key').value=''}const r=await post('/api/ai/models',{});if(!$('ai-provider'))return;catalog=r.items.filter(m=>!/(?:image|video|auto-review)/i.test(m.id));const providers=[...new Set(catalog.map(m=>m.provider))];$('ai-provider').innerHTML=providers.map(p=>`<option value="${esc(p)}">${esc(providerName(p))}</option>`).join('');const active=catalog.find(m=>m.id===c.model);if(active)$('ai-provider').value=active.provider;$('ai-provider').disabled=false;fillModels();$('ai-settings-status').textContent=catalog.length+' text models across '+providers.length+' providers. The selected model will be tested before saving.'}catch(e){if($('ai-settings-status'))$('ai-settings-status').textContent=e.message}finally{if(button.isConnected)button.disabled=false}};
  $('ai-provider').onchange=fillModels;$('ai-load-models').onclick=load;
  $('ai-save').onclick=async()=>{const button=$('ai-save');button.disabled=true;button.textContent='Testing…';$('ai-settings-status').textContent='Testing the model and archive tool support before saving…';$('ai-provider').disabled=true;$('ai-model').disabled=true;try{await post('/api/ai/config',{base_url:$('ai-base').value,model:$('ai-model').value,provider:$('ai-provider').value,api_key:$('ai-key').value});if($('ai-key'))$('ai-key').value='';await aiStatus();$('dialog').close()}catch(e){if($('ai-settings-status'))$('ai-settings-status').textContent=e.message+' Your previous model has been kept.'}finally{if(button.isConnected){button.disabled=false;button.textContent='Use this model';$('ai-provider').disabled=false;$('ai-model').disabled=false}}};
  await load();
 }catch(e){error(e)}
};

function appendRichText(parent,text){
 for(const part of text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)){
  if(part.startsWith('**')&&part.endsWith('**')){const n=document.createElement('strong');n.textContent=part.slice(2,-2);parent.append(n)}
  else if(part.startsWith('`')&&part.endsWith('`')){const n=document.createElement('code');n.textContent=part.slice(1,-1);parent.append(n)}
  else parent.append(document.createTextNode(part));
 }
}

function renderAccounts(){
 const query=$('account-search').value.toLowerCase();const accounts=(state.manifest.accounts||[]).filter(a=>!query||(a.name+' '+a.email).toLowerCase().includes(query)||a.email===state.account);
 $('account-select').innerHTML='<option value="">All accounts · '+fmt(state.manifest.messages)+'</option>'+accounts.map(a=>`<option value="${esc(a.email)}">${esc(a.name===a.email?a.email:a.name+' · '+a.email)} (${fmt(a.count)})</option>`).join('');$('account-select').value=state.account;
 $('account-label').textContent=state.account?'TO: '+state.account:'ALL ACCOUNTS';$('account-note').textContent=state.account?'Shows messages addressed To this account':'Grouped by the To address';
 document.querySelector('.chat-scope').textContent=state.account?'Searching messages addressed To '+state.account+' and their recovered documents.':'Searches all accounts, calendar records and extracted document text. Answers link to sources.';
}
$('account-search').oninput=renderAccounts;
$('account-select').onchange=()=>{state.account=$('account-select').value;state.folder='';state.name='All mail';state.offset=0;state.selected=null;$('message').hidden=true;$('empty-reader').hidden=false;document.body.classList.remove('message-open');aiHistory=[];$('chat-log').innerHTML='<div class="chat-welcome"><h3>Ask about this account.</h3><p>The conversation now uses the selected recipient account.</p></div>';renderAccounts();folderNav();loadList()};
let activeImport=null,importPoll=null,importUploading=false;
function importDialog(){
 dialog('Import emails',`<div class="import-ui"><p>Choose a copied <strong>Olk folder</strong>, an <strong>EML folder</strong>, or ZIP / EML files. Files are processed locally and added to this archive.</p><div class="import-actions"><button id="choose-folder">Choose folder</button><button id="choose-files">Choose ZIP / EML</button><input id="folder-input" type="file" webkitdirectory multiple hidden><input id="files-input" type="file" accept=".zip,.eml" multiple hidden></div><p class="import-help">Duplicates are skipped using file hashes, Message-ID, and a content fingerprint when no Message-ID is available. Accounts are created from To recipients.</p><div id="import-progress" role="status"><p id="import-status">Ready to import.</p><progress id="import-bar" max="100" value="0" hidden></progress><p id="import-counts"></p></div><button id="cancel-import" hidden>Cancel upload</button><details><summary>Supported Outlook folder</summary><p>The folder should contain EBWebView/Default/IndexedDB. Include Attachments and Cache when available. The Microsoft.OutlookForWindows package folder alone does not contain mail.</p></details></div>`);
 $('choose-folder').onclick=()=>$('folder-input').click();$('choose-files').onclick=()=>$('files-input').click();$('folder-input').onchange=e=>uploadImport([...e.target.files]);$('files-input').onchange=e=>uploadImport([...e.target.files]);
 $('cancel-import').onclick=async()=>{if(importUploading)return;try{await post('/api/imports/'+activeImport+'/cancel',{});activeImport=null;sessionStorage.removeItem('archive-import');setImportStatus('Import cancelled. Existing mail is unchanged.');$('cancel-import').hidden=true;$('choose-folder').disabled=false;$('choose-files').disabled=false}catch(e){error(e)}};
 if(activeImport)pollImport();
}
function setImportStatus(message,percent){if($('import-status'))$('import-status').textContent=message;if($('import-bar')){ $('import-bar').hidden=false;if(percent==null)$('import-bar').removeAttribute('value');else $('import-bar').value=percent} $('import-folder').textContent=activeImport?'Import in progress…':'+ Import folder'}
async function uploadImport(files){
 if(!files.length||activeImport)return;
 importUploading=true;$('choose-folder').disabled=true;$('choose-files').disabled=true;
 try{
  const name=files[0].webkitRelativePath?.split('/')[0]||files[0].name;const job=await post('/api/imports',{name});activeImport=job.id;sessionStorage.setItem('archive-import',activeImport);
  let cursor=0,done=0,bytes=0,failed=null;const total=files.reduce((n,f)=>n+f.size,0);
  const worker=async()=>{while(cursor<files.length&&!failed){const f=files[cursor++];const path=f.webkitRelativePath||f.name;try{const r=await fetch('/api/imports/'+activeImport+'/file?path='+encodeURIComponent(path),{method:'PUT',headers:{'X-Archive-Request':'1','Content-Type':'application/octet-stream'},body:f});if(!r.ok){const result=await r.json();throw Error(result.error||'Upload failed')}done++;bytes+=f.size;setImportStatus('Copying files locally: '+fmt(done)+' / '+fmt(files.length),Math.round(100*(total?bytes/total:done/files.length)))}catch(e){failed=e}}};
  await Promise.all([worker(),worker(),worker()]);if(failed)throw failed;importUploading=false;await post('/api/imports/'+activeImport+'/start',{});setImportStatus('Files copied. Reading messages…');pollImport();
 }catch(e){importUploading=false;setImportStatus(e.message,0);if($('cancel-import')){$('cancel-import').hidden=false;$('cancel-import').disabled=false}if(!activeImport){$('choose-folder').disabled=false;$('choose-files').disabled=false}}
}
async function pollImport(){
 if(!activeImport)return;clearTimeout(importPoll);
 try{const job=await api('/api/imports/'+activeImport);if(job.status==='uploading'&&!importUploading&&$('cancel-import')){$('cancel-import').hidden=false;$('cancel-import').disabled=false;job.message='Upload is incomplete. Cancel it and select the files again.'}setImportStatus(job.message,job.status==='complete'?100:undefined);
 if(job.status==='complete'||job.status==='failed'||job.status==='cancelled'){
  const completed=job.status==='complete';activeImport=null;sessionStorage.removeItem('archive-import');$('import-folder').textContent='+ Import folder';
  if($('choose-folder')){$('choose-folder').disabled=false;$('choose-files').disabled=false;$('import-counts').textContent=(job.added!=null?fmt(job.added)+' new messages · '+fmt(job.duplicates||0)+' duplicates skipped. ':'')+(job.errors.length?job.errors.length+' file(s) could not be fully processed.':'');if(job.errors.length){const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='Import details';pre.textContent=job.errors.map(e=>e.file+': '+e.error).join('\n');details.append(summary,pre);$('import-progress').append(details)}}
  if(completed){state.manifest=await api('/api/manifest');renderAccounts();folderNav();$('archive-count').textContent=fmt(state.manifest.messages)+' messages · saved locally';await loadList()}return;
 }
 importPoll=setTimeout(pollImport,1500);
 }catch(e){setImportStatus(e.message);importPoll=setTimeout(pollImport,4000)}
}
$('import-folder').onclick=importDialog;
if(sessionStorage.getItem('archive-import')){activeImport=sessionStorage.getItem('archive-import');pollImport()}

$('import-top').onclick=importDialog;
$('account-label').onclick=()=>{if(innerWidth<=960){document.body.classList.add('folders-open');$('menu').setAttribute('aria-expanded','true')}$('account-search').focus()};
