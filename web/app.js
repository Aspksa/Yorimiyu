const $ = id => document.getElementById(id);
let currentAgent = '';
let useNeo4j = false;
let graphQuery = '';
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
    $('neo4j-state').textContent = runtimes.neo4j?.state || 'offline';
    $('llm-state').textContent = runtimes.llm.state;
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
    const memories = currentAgent ? await api('/api/memories?agent_id='+encodeURIComponent(currentAgent)) : {memories:[]};
    $('memory-list').replaceChildren(...memories.memories.map(m=>node('li',m.content)));
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
    api((useNeo4j ? '/api/neo4j/graph?agent_id=' : '/api/graph?agent_id=')+encodeURIComponent(currentAgent)+(useNeo4j?'&q='+encodeURIComponent(graphQuery):'')),
    api('/api/learning?agent_id='+encodeURIComponent(currentAgent))
  ]);
  $('chat-history').replaceChildren(...chat.messages.map(m=>{
    const p=node('div',m.content); p.className='chat-message '+m.role; p.setAttribute('data-role',m.role); return p;
  }));
  $('graph-canvas').replaceChildren();
  const nodes=graphData.nodes.slice(0,150), edges=graphData.edges;
  const map=new Map(nodes.map((n,i)=>[n.id,i]));
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 800 420'); svg.setAttribute('role','img'); svg.setAttribute('aria-label','Граф локальной памяти');
  const pos=nodes.map((n,i)=>({x:400+320*Math.cos(i*2.399963),y:210+175*Math.sin(i*2.399963)}));
  for (const e of edges) {
    if (!map.has(e.source)||!map.has(e.target)) continue;
    const a=pos[map.get(e.source)],b=pos[map.get(e.target)];
    const line=document.createElementNS(svg.namespaceURI,'line');
    for (const [k,v] of Object.entries({x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:'#b58a48','stroke-opacity':'0.5','stroke-width':Math.min(e.weight,4)})) line.setAttribute(k,v);
    svg.append(line);
  }
  nodes.forEach((n,i)=>{
    const circle=document.createElementNS(svg.namespaceURI,'circle');
    for (const [k,v] of Object.entries({cx:pos[i].x,cy:pos[i].y,r:7,fill:'#e3c080'})) circle.setAttribute(k,v);
    const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=n.label;circle.append(title);svg.append(circle);
  });
  $('graph-canvas').append(svg);
  $('graph-summary').textContent=nodes.length+' узлов · '+edges.length+' связей · '+graphData.kind;
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
async function loadCloud() {
  const config=await api('/api/cloud/settings');
  $('cloud-endpoint').value=config.endpoint||'';
  $('cloud-model').value=config.model||'';
  $('cloud-state').textContent=config.has_key?'Ключ сохранён локально':'Ключ ещё не сохранён';
}
$('cloud-form').onsubmit=async e=>{
  e.preventDefault();
  try{
    const config=await jsonPost('/api/cloud/settings',{endpoint:$('cloud-endpoint').value,model:$('cloud-model').value,api_key:$('cloud-key').value});
    $('cloud-key').value='';
    $('cloud-state').textContent=config.has_key?'Cloud.ru сохранён локально':'Настройки сохранены, ключ отсутствует';
    await refresh();
  }catch(err){$('cloud-state').textContent=err.message;}
};
$('graph-search-form').onsubmit=async e=>{
  e.preventDefault();if(!currentAgent)return;
  graphQuery=$('graph-query').value;useNeo4j=true;
  try{await refreshWorkspace();$('graph-action-state').textContent='Граф Neo4j загружен';}
  catch(err){$('graph-action-state').textContent='Neo4j: '+err.message;}
};
$('graph-index').onclick=async()=>{
  if(!currentAgent)return alert('Выберите агента');
  $('graph-index').disabled=true;
  try{
    const result=await jsonPost('/api/neo4j/index',{agent_id:currentAgent});
    $('graph-action-state').textContent='Индексировано: '+result.indexed;
    useNeo4j=true;await refreshWorkspace();
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
