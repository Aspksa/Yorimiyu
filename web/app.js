const $ = id => document.getElementById(id);
let currentAgent = '';
async function api(path, options) {
  const response = await fetch(path, {credentials:'same-origin', ...options});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Ошибка сервера');
  return result;
}
function node(tag, text) { const element = document.createElement(tag); element.textContent = text; return element; }
async function refresh() {
  try {
    const [status, agents] = await Promise.all([api('/api/status'),api('/api/agents')]);
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
    $('memory-list').replaceChildren(...memories.memories.map(m=>{ const li=node('li',m.content); return li; }));
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
