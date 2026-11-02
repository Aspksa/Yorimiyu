const $ = id => document.getElementById(id);
let currentAgent = '';
let useSQLiteGraph = true;
let graphQuery = '';
const graphIndexedThisSession=new Set();
const preference=(key,defaultValue)=>{try{const v=localStorage.getItem('yorimiyu:'+key);return v===null?defaultValue:v==='true';}catch(_){return defaultValue;}};
const savePreference=(key,value)=>{try{localStorage.setItem('yorimiyu:'+key,String(value));}catch(_){}};
async function api(path, options) {
  const response = await fetch(path, {credentials:'same-origin', ...options});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Ошибка сервера');
  return result;
}
function node(tag, text) { const element = document.createElement(tag); element.textContent = text; return element; }
async function refresh() {
  try {
    const [status, agents, graphiti, runtimes] = await Promise.all([api('/api/status'),api('/api/agents'),api('/api/graphiti/status'),api('/api/runtime')]);
    $('letta-state').textContent = runtimes.letta.state;
    $('sqliteGraph-state').textContent = runtimes.neo4j?.state || 'offline';
    $('llm-state').textContent = runtimes.llm.state;
    $('chat-model-indicator').textContent='Модель: '+(runtimes.llm.state==='configured'?'подключена':'не настроена');
    $('graphiti-state').textContent = graphiti.state + ' · очередь: ' + graphiti.queued;
    $('connection-status').textContent = 'Локальная память работает';
    $('memory-count').textContent = String(status.memories);
    $('agent-count').textContent = String(status.agents);
    $('agent-list').replaceChildren();
    for (const agent of agents.agents) {
      const button = node('button',agent.name);
      button.type = 'button';
      button.className = 'agent-button' + (agent.id === currentAgent ? ' selected' : '');
      button.onclick = () => { currentAgent = agent.id; refresh(); };
      $('agent-list').append(button);
    }
    if (!currentAgent && agents.agents.length) currentAgent = agents.agents[0].id;
    $('selected-agent').textContent = agents.agents.find(a=>a.id===currentAgent)?.name || 'Выберите агента';
    $('chat-agent-indicator').textContent='Агент: '+$('selected-agent').textContent;
    $('graph-metric-agent').textContent=$('selected-agent').textContent;
    const memories = currentAgent ? await api('/api/memories?agent_id='+encodeURIComponent(currentAgent)) : {memories:[]};
    $('memory-list').replaceChildren(...memories.memories.map(m=>node('li',m.content)));
    filterMemories();
    if(currentAgent && memories.memories.length && $('graph-auto-index').checked && !graphIndexedThisSession.has(currentAgent)){
      graphIndexedThisSession.add(currentAgent);
      try {await api('/api/sqlite-graph/index',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:currentAgent})});}
      catch(error){graphIndexedThisSession.delete(currentAgent);$('graph-action-state').textContent='Автоиндексация: '+error.message;}
    }
    await refreshWorkspace();
  } catch (error) { $('connection-status').textContent = 'API недоступен: '+error.message; }
}
$('agent-form').onsubmit = async event => {
  event.preventDefault();
  try {
    const data=await api('/api/agents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('agent-name').value})});
    currentAgent=data.agent.id; $('agent-name').value=''; await refresh();
  } catch(error) { alert(error.message); }
};
$('memory-form').onsubmit = async event => {
  event.preventDefault();
  if (!currentAgent) { alert('Сначала создайте агента'); return; }
  try {
    await api('/api/memories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:currentAgent,content:$('memory-content').value})});
    $('memory-content').value=''; await refresh();
  } catch(error) { alert(error.message); }
};
refresh();

$('graphiti-deliver').onclick = async () => {
  if (!confirm('Передать следующую локальную запись в Graphiti? Это отправит текст в настроенный локальный сервис.')) return;
  const button = $('graphiti-deliver');
  button.disabled = true;
  try {
    const result = await api('/api/graphiti/deliver', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true})});
    $('graphiti-delivery-result').textContent = result.delivery.state === 'accepted_not_indexed' ? 'Graphiti принял запись в очередь; индексация не подтверждена.' : 'Очередь пуста.';
    await refresh();
  } catch(error) { $('graphiti-delivery-result').textContent = 'Передача не удалась: '+error.message; }
  finally { button.disabled = false; }
};

async function refreshWorkspace() {
  if (!currentAgent) return;
  const [chat, graphData, learning] = await Promise.all([
    api('/api/chat?agent_id='+encodeURIComponent(currentAgent)),
    api((useSQLiteGraph ? '/api/sqlite-graph/graph?agent_id=' : '/api/graph?agent_id=')+encodeURIComponent(currentAgent)+(useSQLiteGraph?'&q='+encodeURIComponent(graphQuery):'')),
    api('/api/learning?agent_id='+encodeURIComponent(currentAgent))
  ]);
  const messages=chat.messages;
  $('chat-message-count').textContent=messages.length+' сообщений';
  $('chat-history').replaceChildren(...(messages.length?messages.map(m=>{
    const p=node('div',m.content); p.className='chat-message '+m.role; p.setAttribute('data-role',m.role); return p;
  }):[Object.assign(node('p','История пока пуста. Напишите первое сообщение.'),{className:'empty-state'})]));
  $('chat-history').scrollTop=$('chat-history').scrollHeight;
  $('graph-canvas').replaceChildren();
  const nodes=graphData.nodes, edges=graphData.edges;
  window.yorimiyuGraphData={nodes,edges};
  const map=new Map(nodes.map((n,i)=>[n.id,i]));
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 800 420'); svg.setAttribute('role','img'); svg.setAttribute('aria-label','Граф локальной памяти');
  const pos=nodes.map((n,i)=>({x:400+320*Math.cos(i*2.399963),y:210+175*Math.sin(i*2.399963)}));
  const layer=document.createElementNS(svg.namespaceURI,'g');layer.setAttribute('id','graph-layer');svg.append(layer);
  for (const e of edges) {
    if (!map.has(e.source)||!map.has(e.target)) continue;
    const a=pos[map.get(e.source)],b=pos[map.get(e.target)];
    const line=document.createElementNS(svg.namespaceURI,'line');
    for (const [k,v] of Object.entries({x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:'#b58a48','stroke-opacity':'0.5','stroke-width':Math.min(e.weight,4)})) line.setAttribute(k,v);
    layer.append(line);
  }
  nodes.forEach((n,i)=>{
    const circle=document.createElementNS(svg.namespaceURI,'circle');
    for (const [k,v] of Object.entries({cx:pos[i].x,cy:pos[i].y,r:n.kind==='entity'?10:7,fill:n.kind==='entity'?'#b65057':'#c7a15b'})) circle.setAttribute(k,v);
    circle.setAttribute('tabindex','0');circle.setAttribute('role','button');circle.setAttribute('focusable','true');circle.setAttribute('aria-label',n.label||'Узел графа');
    circle.dataset.nodeId=String(n.id);
    const select=()=>{$('graph-selected').textContent=n.label||n.id;$('graph-node-id').textContent=String(n.id);$('graph-node-degree').textContent=String(edges.filter(e=>e.source===n.id||e.target===n.id).length);$('graph-focus-node').disabled=false;$('graph-focus-node').onclick=()=>{graphView={scale:1.5,x:400-pos[i].x,y:210-pos[i].y};const layer=svg.querySelector('#graph-layer');layer.setAttribute('transform',`translate(${graphView.x} ${graphView.y}) translate(400 210) scale(${graphView.scale}) translate(-400 -210)`);};layer.querySelectorAll('circle').forEach(el=>el.classList.remove('is-selected'));circle.classList.add('is-selected');};
    circle.addEventListener('click',select);circle.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});
    const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=n.label;circle.append(title);layer.append(circle);
    const label=document.createElementNS(svg.namespaceURI,'text');label.textContent=String(n.label||'').slice(0,25);label.setAttribute('x',pos[i].x+12);label.setAttribute('y',pos[i].y+4);label.setAttribute('class','graph-node-label');layer.append(label);
  });
  if(nodes.length){$('graph-canvas').append(svg);}else{$('graph-canvas').append(Object.assign(node('p','Пока нет узлов. Добавьте запись памяти — граф обновится автоматически.'),{className:'empty-state'}));}
  if(nodes.length)initGraphInteractions(svg);
  filterGraphNodes();
  $('graph-summary').textContent=nodes.length+' узлов · '+edges.length+' связей · '+graphData.kind+(nodes.length>=300?' · показана первая часть данных':'');
  $('graph-metric-nodes').textContent=String(nodes.length);
  $('graph-metric-edges').textContent=String(edges.length);
  $('graph-metric-source').textContent=graphData.kind==='sqlite_local'?'SQLite':'Лексический';
  $('learning-list').replaceChildren(...learning.suggestions.map(s=>{
    const box=document.createElement('div');box.className='suggestion';
    box.append(node('p',s.content),node('small',s.state));
    if(s.state==='pending') for(const [approve,label] of [[true,'Принять'],[false,'Отклонить']]) {
      const button=node('button',label);button.onclick=async()=>{
        try {await api('/api/learning/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:currentAgent,id:s.id,approve})});await refresh();}
        catch(e){alert(e.message);}
      };box.append(button);
    }
    return box;
  }));
}
$('chat-form').onsubmit=async event=>{
  event.preventDefault();if(!currentAgent)return alert('Создайте агента');
  const button=event.target.querySelector('button');button.disabled=true;
  $('chat-state').textContent='Ожидаем ответ модели…';
  try{await api('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:currentAgent,content:$('chat-input').value})});$('chat-input').value='';$('chat-state').textContent='Ответ получен';await refresh();}
  catch(e){$('chat-state').textContent='Ошибка: '+e.message;await refresh();}
  finally{button.disabled=false;}
};
$('search-form').onsubmit=async event=>{
  event.preventDefault();if(!currentAgent)return;
  try{const result=await api('/api/search?agent_id='+encodeURIComponent(currentAgent)+'&q='+encodeURIComponent($('search-query').value));
    $('search-results').replaceChildren(...result.matches.map(m=>node('li',m.content)));
  }catch(e){alert(e.message);}
};
$('learning-scan').onclick=async()=>{
  if(!currentAgent)return;
  try{await api('/api/learning/propose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:currentAgent})});await refresh();}
  catch(e){alert(e.message);}
};
$('letta-bind-form').onsubmit=async event=>{
  event.preventDefault();if(!currentAgent)return alert('Создайте агента');
  try{await api('/api/letta/bind',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:currentAgent,letta_agent_id:$('letta-agent-id').value})});$('letta-result').textContent='ID агента Letta сохранён';}
  catch(e){$('letta-result').textContent=e.message;}
};
$('letta-form').onsubmit=async event=>{
  event.preventDefault();if(!currentAgent)return;
  if(!confirm('Letta может выполнять инструменты и изменять файлы. Запустить команду?'))return;
  const button=event.target.querySelector('button');button.disabled=true;
  try{const result=await api('/api/letta/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:currentAgent,content:$('letta-input').value,confirm:true})});$('letta-result').textContent=result.answer||'Пустой ответ';}
  catch(e){$('letta-result').textContent=e.message;}
  finally{button.disabled=false;}
};

const jsonPost = (path,body) => api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
async function fetchCloudModels({autoSelect=false}={}) {
 const button=$('cloud-test');button.disabled=true;
 $('cloud-diagnostics').textContent='Загружаем доступные модели Cloud.ru…';
 try {
   const result=await api('/api/cloud/models');
   const ids=Array.isArray(result.models)?result.models:[];
   $('cloud-model-select').replaceChildren(new Option('Выберите модель',''),...ids.map(id=>new Option(id,id)));
   const saved=$('cloud-model').value||result.selected_model||'';
   const choice=ids.includes(saved)?saved:(autoSelect?ids[0]||'':'');
   if(choice){$('cloud-model-select').value=choice;$('cloud-model').value=choice;}
   $('cloud-diagnostics').textContent=ids.length?'Загружено моделей: '+result.total+'. Выберите модель для чата.':'Список моделей пуст. Проверьте права API-ключа.';
   if(autoSelect&&choice&&choice!==result.selected_model) {
     await jsonPost('/api/cloud/settings',{model:choice});
     $('cloud-state').textContent='Модель выбрана и сохранена: '+choice;
   }
 }catch(err){$('cloud-diagnostics').textContent='Не удалось загрузить модели: '+err.message;}
 finally{button.disabled=false;}
}
async function loadCloud() {
 const config=await api('/api/cloud/settings');
 $('cloud-model').value=config.model||'';
 $('cloud-model-select').replaceChildren(new Option('Модели загрузятся после сохранения ключа',''));
 $('cloud-state').textContent=config.has_key?'Ключ сохранён локально':'Ключ ещё не сохранён';
 if(config.has_key)await fetchCloudModels({autoSelect:true});
}
$('cloud-form').onsubmit=async e=>{
 e.preventDefault();
 try {
   const config=await jsonPost('/api/cloud/settings',{model:$('cloud-model').value,api_key:$('cloud-key').value});
   $('cloud-key').value='';
   $('cloud-state').textContent=config.has_key?'Cloud.ru сохранён локально':'Настройки сохранены, ключ отсутствует';
   if(config.has_key)await fetchCloudModels({autoSelect:true});
   await refresh();
 }catch(err){$('cloud-state').textContent=err.message;}
};
$('cloud-model-select').addEventListener('change',async()=>{
 const model=$('cloud-model-select').value;
 if(!model)return;
 $('cloud-model').value=model;
 try{await jsonPost('/api/cloud/settings',{model});$('cloud-state').textContent='Модель сохранена: '+model;}
 catch(err){$('cloud-state').textContent='Не удалось сохранить модель: '+err.message;}
});
$('cloud-test').addEventListener('click',()=>fetchCloudModels({autoSelect:true}));
$('graph-search-form').onsubmit=async e=>{
  e.preventDefault();if(!currentAgent)return;
  graphQuery=$('graph-query').value;useSQLiteGraph=true;
  try{await refreshWorkspace();$('graph-action-state').textContent='Граф SQLite загружен';}
  catch(err){$('graph-action-state').textContent='SQLite: '+err.message;}
};
$('graph-index').onclick=async()=>{
  if(!currentAgent)return alert('Выберите агента');
  $('graph-index').disabled=true;
  try{
    const result=await jsonPost('/api/sqlite-graph/index',{agent_id:currentAgent});
    $('graph-action-state').textContent='Индексировано: '+result.indexed;
    useSQLiteGraph=true;await refreshWorkspace();
  }catch(err){$('graph-action-state').textContent=err.message;}
  finally{$('graph-index').disabled=false;}
};
async function loadBackups(){
  const data=await api('/api/backups');
  $('backup-list').replaceChildren(...data.backups.map(b=>{
    const row=node('div',b.name+' · '+b.bytes+' байт ');
    const button=node('button','Восстановить');
    button.type='button';button.onclick=async()=>{
      if(!confirm('Восстановление заменит текущую SQLite память. Перед операцией будет создана копия. Продолжить?'))return;
      try{await jsonPost('/api/backup/restore',{name:b.name,confirm:true});$('backup-state').textContent='Восстановлено: '+b.name;await refresh();}
      catch(err){$('backup-state').textContent=err.message;}
    };row.append(button);return row;
  }));
}
$('backup-create').onclick=async()=>{
  try{const b=await jsonPost('/api/backup',{});$('backup-state').textContent='Создана копия: '+b.name;await loadBackups();}
  catch(err){$('backup-state').textContent=err.message;}
};
loadCloud().catch(err=>{$('cloud-state').textContent=err.message;});
loadBackups().catch(err=>{$('backup-state').textContent=err.message;});


/* Browser-only appearance preferences: never include credentials. */
(()=>{
 const keys=['theme','accent','radius','size'];
 const defaults={theme:'light',accent:'red',radius:'soft',size:'normal'};
 function apply(){
   for(const key of keys){
     const el=document.getElementById('appearance-'+key);
     if(!el)continue;
     let saved=defaults[key];
     try{saved=localStorage.getItem('yorimiyu-appearance-'+key)||saved}catch(_){}
     if(![...el.options].some(o=>o.value===saved))saved=defaults[key];
     el.value=saved;
     document.body.dataset[key]=key==='theme'&&saved==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):saved;
     el.addEventListener('change',()=>{
       try{localStorage.setItem('yorimiyu-appearance-'+key,el.value)}catch(_){}
       applyValues();
     });
   }
   try{document.body.classList.toggle('sidebar-collapsed',localStorage.getItem('yorimiyu-sidebar')==='collapsed')}catch(_){}
 }
 function applyValues(){for(const key of keys){const el=document.getElementById('appearance-'+key);if(el)document.body.dataset[key]=key==='theme'&&el.value==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):el.value}}
 function init(){
   apply();
   const toggle=document.getElementById('sidebar-toggle');
   if(toggle)toggle.addEventListener('click',()=>{document.body.classList.toggle('sidebar-collapsed');try{localStorage.setItem('yorimiyu-sidebar',document.body.classList.contains('sidebar-collapsed')?'collapsed':'expanded')}catch(_){}});
   const form=document.getElementById('appearance-form');if(form)form.addEventListener('submit',e=>e.preventDefault());
   document.querySelectorAll('.sidebar nav a').forEach(a=>a.addEventListener('click',()=>{document.querySelectorAll('.sidebar nav a').forEach(x=>x.classList.remove('active'));a.classList.add('active')}));
   window.addEventListener('hashchange',()=>{document.querySelectorAll('.sidebar nav a').forEach(a=>a.classList.toggle('active',a.hash===location.hash))});
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();


/* Distinct app views: hash navigation never scrolls through other modules. */
const viewMeta={
 overview:['Главная','Ваш локальный центр управления памятью и интеллектом.'],
 chat:['Чат','Диалог с выбранным агентом и поиск по памяти.'],
 memory:['Память','Записи, эпизоды и состояние локального хранилища.'],
 graph:['Граф знаний','Интерактивная карта реальных связей с масштабированием и исследованием.'],
 agents:['Агенты','Управление профилями агентов и сохранёнными записями.'],
 learning:['Развитие','Проверка и подтверждение предложений для памяти.'],
 services:['Подключения','Cloud.ru, SQLite, Graphiti, Letta и резервные копии.'],
 settings:['Настройки','Внешний вид, размер интерфейса и персонализация.']
};
function navigateWorkspace(){
 const requested=decodeURIComponent(location.hash.slice(1));
 const page=Object.prototype.hasOwnProperty.call(viewMeta,requested)?requested:'overview';
 document.querySelectorAll('[data-view]').forEach(el=>{el.hidden=el.dataset.view!==page;});
 document.querySelectorAll('[data-page-link]').forEach(el=>{const active=el.dataset.pageLink===page;el.classList.toggle('active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
 $('page-title').textContent=viewMeta[page][0];$('page-description').textContent=viewMeta[page][1];
 document.title='Yorimiyu — '+viewMeta[page][0];
 window.scrollTo({top:0,behavior:'instant'});
}
window.addEventListener('hashchange',navigateWorkspace);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',navigateWorkspace);else navigateWorkspace();

let graphView={scale:1,x:0,y:0};
function initGraphInteractions(svg){
 const layer=svg.querySelector('#graph-layer');if(!layer)return;
 graphView={scale:1,x:0,y:0};
 const update=()=>layer.setAttribute('transform',`translate(${graphView.x} ${graphView.y}) translate(400 210) scale(${graphView.scale}) translate(-400 -210)`);
 const zoom=(factor)=>{graphView.scale=Math.max(.35,Math.min(4,graphView.scale*factor));update();};
 $('graph-zoom-in').onclick=()=>zoom(1.25);$('graph-zoom-out').onclick=()=>zoom(.8);
 $('graph-reset').onclick=()=>{graphView={scale:1,x:0,y:0};update();};
 $('graph-fit').onclick=()=>{const nodes=[...layer.querySelectorAll('circle')];if(!nodes.length){graphView={scale:1,x:0,y:0};update();return;}const xs=nodes.map(n=>Number(n.getAttribute('cx'))),ys=nodes.map(n=>Number(n.getAttribute('cy')));const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);graphView.scale=Math.min(3,700/Math.max(1,maxX-minX+48),340/Math.max(1,maxY-minY+48));graphView.x=graphView.scale*(400-(minX+maxX)/2);graphView.y=graphView.scale*(210-(minY+maxY)/2);update();};
 $('graph-labels').onchange=e=>svg.classList.toggle('hide-labels',!e.target.checked);
 svg.classList.toggle('hide-labels',!$('graph-labels').checked);
 svg.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1.1:.9);},{passive:false});
 let dragging=false,previous=null;
 svg.addEventListener('pointerdown',e=>{if(e.target.tagName.toLowerCase()==='circle')return;dragging=true;previous={x:e.clientX,y:e.clientY};svg.setPointerCapture(e.pointerId);});
 svg.addEventListener('pointermove',e=>{if(!dragging||!previous)return;const rect=svg.getBoundingClientRect();graphView.x+=(e.clientX-previous.x)*800/rect.width;graphView.y+=(e.clientY-previous.y)*420/rect.height;previous={x:e.clientX,y:e.clientY};update();});
 svg.addEventListener('pointerup',()=>{dragging=false;previous=null;});
 svg.addEventListener('pointercancel',()=>{dragging=false;previous=null;});
 update();
}

/* Yorimiyu 0.4: independent settings categories and safe client-side exploration. */
function filterMemories(){
 const query=($('memory-filter')?.value||'').trim().toLocaleLowerCase('ru');
 const rows=[...$('memory-list').querySelectorAll('li')];
 let shown=0;
 rows.forEach(row=>{row.hidden=!!query&&!row.textContent.toLocaleLowerCase('ru').includes(query);if(!row.hidden)shown++;});
 if($('memory-visible-count'))$('memory-visible-count').textContent=shown+' из '+rows.length;
}
$('memory-filter').addEventListener('input',filterMemories);

const settingsInfo={
 ai:['Cloud.ru и модели ИИ','Адрес модели, её ID и API-ключ настраиваются в разделе «Подключения». Ключ хранится локально в файле настроек сервера, не в браузере.'],
 memory:['Память и данные','Записи хранятся локально. Используйте раздел «Память» для просмотра, фильтрации и добавления знаний.'],
 graph:['Граф и SQLite','Индексирование в SQLite запускается вручную в «Подключениях». Граф показывает реальные ответы локального API.'],
 backup:['Резервные копии','Создание и восстановление резервных копий SQLite доступны в «Подключениях». Перед восстановлением требуется подтверждение.'],
 safety:['Безопасность','Не публикуйте файл data/cloudru-settings.json, каталог .runtime или резервные копии. Действия Letta требуют подтверждения.']
};
function selectSettingsTab(tab){
 const appearance=tab==='appearance';
 $('appearance-section').hidden=!appearance;
 const content=$('settings-category-content');
 content.replaceChildren();
 if(!appearance){
   const [heading,description]=settingsInfo[tab]||settingsInfo.safety;
   const h=node('h3',heading),p=node('p',description);
   content.append(h,p);
   const link=node('a',tab==='memory'?'Перейти в память →':'Открыть подключения →');
   link.href=tab==='memory'?'#memory':'#services';link.className='primary';content.append(link);
 }
 document.querySelectorAll('[data-settings-tab]').forEach(button=>{const selected=button.dataset.settingsTab===tab;button.setAttribute('aria-selected',String(selected));button.classList.toggle('selected',selected);});
 try{sessionStorage.setItem('yorimiyu-settings-tab',tab)}catch(_){}
}
document.querySelectorAll('[data-settings-tab]').forEach(button=>button.addEventListener('click',()=>selectSettingsTab(button.dataset.settingsTab)));
let savedTab='appearance';try{savedTab=sessionStorage.getItem('yorimiyu-settings-tab')||savedTab}catch(_){}
selectSettingsTab(savedTab in settingsInfo||savedTab==='appearance'?savedTab:'appearance');

function filterGraphNodes(){
 const svg=$('graph-canvas').querySelector('svg');
 if(!svg)return;
 const query=($('graph-local-search').value||'').trim().toLocaleLowerCase('ru');
 const filter=$('graph-cluster-filter').value;
 const data=window.yorimiyuGraphData||{nodes:[],edges:[]};
 const degrees=new Map(data.nodes.map(n=>[String(n.id),0]));
 for(const edge of data.edges){for(const id of [edge.source,edge.target])degrees.set(String(id),(degrees.get(String(id))||0)+1);}
 const circles=[...svg.querySelectorAll('circle')];
 circles.forEach((circle,i)=>{
   const item=data.nodes[i];if(!item)return;
   const degree=degrees.get(String(item.id))||0;
   const visible=(!query||String(item.label||'').toLocaleLowerCase('ru').includes(query))&&(filter==='all'||(filter==='connected'?degree>0:degree===0));
   circle.style.opacity=visible?'1':'.12';
   const label=svg.querySelectorAll('.graph-node-label')[i];if(label)label.style.opacity=visible?'1':'.12';
 });
}
$('graph-local-search').addEventListener('input',filterGraphNodes);
$('graph-cluster-filter').addEventListener('change',filterGraphNodes);
$('chat-new').addEventListener('click',()=>{
 if(!confirm('Создать новый диалог? История чата агента останется в локальной памяти; разделение диалогов сервером пока не поддерживается.'))return;
 $('chat-input').focus();
 $('chat-state').textContent='Готово к новому сообщению. История агента не удалена.';
});
$('chat-export').addEventListener('click',()=>{
 const lines=[...$('chat-history').querySelectorAll('.chat-message')].map(el=>(el.dataset.role||'message')+': '+el.textContent);
 const blob=new Blob([lines.join('\n\n')],{type:'text/plain;charset=utf-8'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='yorimiyu-chat.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});

/* Connection center: read-only automatic health checks; never submit secrets or start external tools. */
let connectionBusy=false;
async function checkConnections(){
 if(connectionBusy||document.hidden)return;
 connectionBusy=true;
 const button=$('connections-refresh');button.disabled=true;
 try{
   const [runtime,graphiti,cloud]=await Promise.allSettled([
     api('/api/runtime'),api('/api/graphiti/status'),api('/api/cloud/settings')
   ]);
   const show=(id,value)=>{if($(id))$(id).textContent=value;};
   if(runtime.status==='fulfilled'){
     const r=runtime.value;
     show('sqliteGraph-state',r.neo4j?.state||'неизвестно');
     show('letta-state',r.letta?.state||'неизвестно');
     show('llm-state',r.llm?.state||'неизвестно');
     show('chat-model-indicator','Модель: '+(r.llm?.state==='configured'?'подключена':'не настроена'));
   }else show('sqliteGraph-state','Ошибка проверки');
   if(graphiti.status==='fulfilled')show('graphiti-state',graphiti.value.state+' · очередь: '+graphiti.value.queued);
   if(cloud.status==='fulfilled')show('cloud-state',cloud.value.has_key?'API-ключ сохранён локально':'API-ключ не настроен');
   show('connections-last-check','Проверено в '+new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit'}));
 }catch(error){$('connections-last-check').textContent='Ошибка проверки: '+error.message;}
 finally{connectionBusy=false;button.disabled=false;}
}
$('connections-refresh').addEventListener('click',checkConnections);
$('connections-auto').checked=preference('connections-auto',true);
$('graph-auto-index').checked=preference('graph-auto-index',true);
$('connections-auto').addEventListener('change',e=>{savePreference('connections-auto',e.target.checked);if(e.target.checked)checkConnections();});
$('graph-auto-index').addEventListener('change',e=>{savePreference('graph-auto-index',e.target.checked);if(e.target.checked)refresh();});
setInterval(()=>{if($('connections-auto').checked)checkConnections();},30000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&$('connections-auto').checked)checkConnections();});
checkConnections();
$('chat-input').addEventListener('keydown',event=>{
 if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){
   event.preventDefault();$('chat-form').requestSubmit();
 }
});

/* Keyboard navigation: lightweight local command palette, no external dependencies. */
const quickPages=[
 ['overview','Главная','Обзор и состояние'],
 ['chat','Чат','Диалог с агентом'],
 ['memory','Память','Локальная библиотека'],
 ['graph','Граф знаний','Узлы и связи'],
 ['agents','Агенты','Профили агентов'],
 ['learning','Развитие','Предложения памяти'],
 ['services','Подключения','Автоматизация и Cloud.ru'],
 ['settings','Настройки','Оформление и параметры']
];
let quickActive=0,quickMatches=quickPages,quickPreviousFocus=null;
function renderQuick(){
 const q=$('quick-search').value.trim().toLocaleLowerCase('ru');
 quickMatches=quickPages.filter(p=>p.slice(1).join(' ').toLocaleLowerCase('ru').includes(q));
 quickActive=Math.min(quickActive,Math.max(0,quickMatches.length-1));
 $('quick-results').replaceChildren(...quickMatches.map((p,i)=>{
   const b=node('button',p[1]+' — '+p[2]);b.type='button';b.className='quick-result'+(i===quickActive?' selected':'');
   b.setAttribute('aria-current',i===quickActive?'true':'false');
   b.onclick=()=>{location.hash='#'+p[0];closeQuick();};
   return b;
 }));
 if(!quickMatches.length)$('quick-results').append(node('p','Разделы не найдены'));
}
function openQuick(){
 quickPreviousFocus=document.activeElement;
 $('quick-dialog').hidden=false;quickActive=0;$('quick-search').value='';renderQuick();$('quick-search').focus();
}
function closeQuick(){
 $('quick-dialog').hidden=true;
 if(quickPreviousFocus?.isConnected)quickPreviousFocus.focus();
}
$('quick-open').addEventListener('click',openQuick);
$('quick-dialog').querySelector('[data-quick-close]').addEventListener('click',closeQuick);
$('quick-search').addEventListener('input',()=>{quickActive=0;renderQuick();});
document.addEventListener('keydown',event=>{
 if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){
   event.preventDefault();$('quick-dialog').hidden?openQuick():closeQuick();return;
 }
 if($('quick-dialog').hidden)return;
 if(event.key==='Escape'){event.preventDefault();closeQuick();}
 if(event.key==='Tab'){
   const focusables=[$('quick-search'),...$('quick-results').querySelectorAll('button')];
   const index=focusables.indexOf(document.activeElement);
   if(event.shiftKey&&index===0){event.preventDefault();focusables[focusables.length-1].focus();}
   else if(!event.shiftKey&&index===focusables.length-1){event.preventDefault();focusables[0].focus();}
 }
 if(event.key==='ArrowDown'||event.key==='ArrowUp'){
   event.preventDefault();if(!quickMatches.length)return;
   quickActive=(quickActive+(event.key==='ArrowDown'?1:-1)+quickMatches.length)%quickMatches.length;renderQuick();
 }
 if(event.key==='Enter'&&document.activeElement===$('quick-search')&&quickMatches.length){
   event.preventDefault();location.hash='#'+quickMatches[quickActive][0];closeQuick();
 }
});
