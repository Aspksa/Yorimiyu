import React,{useCallback,useEffect,useMemo,useState} from 'react';
import {createRoot} from 'react-dom/client';
import ReactFlow,{Background,Controls,MiniMap,MarkerType,type Node,type Edge} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import ReactECharts from 'echarts-for-react';
import {Canvas} from '@react-three/fiber';
import {OrbitControls,Stars} from '@react-three/drei';
import './studio.css';

type Agent={id:string;name:string};
type GraphNode={id:string;label:string;kind?:string};
type GraphEdge={source:string;target:string;weight?:number};
type Graph={nodes:GraphNode[];edges:GraphEdge[];kind?:string};
type Message={id:number;role:string;content:string};
type Memory={id:number;content:string};
type Page='graph'|'insights'|'galaxy'|'chat';
async function api<T>(path:string,init?:RequestInit):Promise<T>{
 const r=await fetch(path,{cache:'no-store',...init});
 const raw=await r.text();let data:any;
 try{data=JSON.parse(raw)}catch{throw Error('Некорректный ответ локального API');}
 if(!r.ok)throw Error(data.error||'Ошибка API '+r.status);
 return data as T;
}
function Galaxy({nodes}:{nodes:GraphNode[]}){
 const visible=nodes.slice(0,80);
 return <div className="galaxy" aria-label="Трёхмерная визуализация знаний"><Canvas camera={{position:[0,0,22],fov:55}} dpr={[1,1.5]}>
 <ambientLight intensity={1.8}/><pointLight position={[8,8,8]} intensity={100}/><Stars radius={90} depth={40} count={800} factor={3} fade speed={0.3}/>
 {visible.map((n,i)=>{const angle=i*2.39996;const radius=Math.sqrt(i)*1.1;const x=Math.cos(angle)*radius;const y=Math.sin(angle)*radius;const z=Math.sin(i*0.7)*2.2;return <group key={n.id} position={[x,y,z]}><mesh><sphereGeometry args={[n.kind==='entity'?.26:.16,12,12]}/><meshStandardMaterial color={n.kind==='entity'?'#b84b58':'#e7b86e'} emissive={n.kind==='entity'?'#5c1e29':'#785523'} emissiveIntensity={.3}/></mesh></group>})}
 <OrbitControls enablePan enableZoom minDistance={5} maxDistance={60}/></Canvas><span className="galaxy-caption">Перетаскивайте для вращения · колесо — масштаб · до 80 узлов</span></div>;
}
function App(){
 const [page,setPage]=useState<Page>('graph');
 const [agents,setAgents]=useState<Agent[]>([]);
 const [agent,setAgent]=useState('');
 const [graph,setGraph]=useState<Graph>({nodes:[],edges:[]});
 const [messages,setMessages]=useState<Message[]>([]);
 const [memories,setMemories]=useState<Memory[]>([]);
 const [query,setQuery]=useState('');
 const [selected,setSelected]=useState<GraphNode|null>(null);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [draft,setDraft]=useState('');
 const loadAgents=useCallback(async()=>{try{const r=await api<{agents:Agent[]}>('/api/agents');setAgents(r.agents);setAgent(old=>r.agents.some(a=>a.id===old)?old:r.agents[0]?.id||'');setError('')}catch(e){setError(String(e))}},[]);
 useEffect(()=>{void loadAgents()},[loadAgents]);
 const refresh=useCallback(async()=>{if(!agent){setGraph({nodes:[],edges:[]});setMessages([]);setMemories([]);return;}setBusy(true);try{
 const [g,m,h]=await Promise.all([api<Graph>('/api/sqlite-graph/graph?agent_id='+encodeURIComponent(agent)),api<{memories:Memory[]}>('/api/memories?agent_id='+encodeURIComponent(agent)),api<{messages:Message[]}>('/api/chat?agent_id='+encodeURIComponent(agent))]);
 setGraph(g);setMemories(m.memories);setMessages(h.messages);setError('');
 }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}},[agent]);
 useEffect(()=>{void refresh()},[refresh]);
 const filtered=useMemo(()=>graph.nodes.filter(n=>n.label.toLocaleLowerCase('ru').includes(query.toLocaleLowerCase('ru'))),[graph.nodes,query]);
 const visible=filtered.slice(0,250);const ids=new Set(visible.map(n=>n.id));
 const flowNodes:Node[]=useMemo(()=>visible.map((n,i)=>{const angle=i*2.399963;const radius=Math.sqrt(i)*52;return{id:n.id,position:{x:Math.cos(angle)*radius,y:Math.sin(angle)*radius},data:{label:n.label.slice(0,75)},style:{background:n.kind==='entity'?'#fff0ed':'#fff',color:'#37343a',border:'1px solid '+(n.kind==='entity'?'#bd6571':'#d9c4a7'),borderRadius:14,padding:10,fontSize:12,maxWidth:210,boxShadow:'0 4px 16px #4b342012'}}}),[visible]);
 const flowEdges:Edge[]=useMemo(()=>graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).slice(0,1000).map((e,i)=>({id:String(i)+'-'+e.source+'-'+e.target,source:e.source,target:e.target,style:{stroke:'#bda27d',strokeWidth:Math.min(3,Math.max(1,e.weight||1))},markerEnd:{type:MarkerType.ArrowClosed,color:'#bda27d'}})),[graph.edges,query,graph.nodes]);
 const types=useMemo(()=>{const counts=new Map<string,number>();for(const n of graph.nodes)counts.set(n.kind||'unknown',(counts.get(n.kind||'unknown')||0)+1);return [...counts].map(([name,value])=>({name,value}))},[graph.nodes]);
 const chart={backgroundColor:'transparent',tooltip:{trigger:'item'},grid:{left:50,right:20,top:20,bottom:40},xAxis:{type:'category',data:types.map(x=>x.name),axisLabel:{color:'#736c6d'}},yAxis:{type:'value',axisLabel:{color:'#736c6d'}},series:[{type:'bar',data:types.map(x=>x.value),itemStyle:{color:'#b64e5a',borderRadius:[8,8,0,0]},barMaxWidth:90}]};
 async function send(event:React.FormEvent){event.preventDefault();if(!agent||!draft.trim()||busy)return;setBusy(true);try{await api('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:agent,content:draft.trim()})});setDraft('');await refresh()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 return <div className="studio-shell"><aside className="studio-sidebar"><a className="studio-logo" href="/">✦ YORIMIYU <small>VISUAL STUDIO</small></a><div className="studio-nav">{([['graph','Граф знаний','◇'],['insights','Аналитика','▥'],['galaxy','3D-галактика','✧'],['chat','Чат','◉']] as const).map(([id,name,icon])=><button key={id} onClick={()=>setPage(id)} className={page===id?'active':''}><span>{icon}</span>{name}</button>)}</div><a className="back-link" href="/">← Основной интерфейс</a></aside>
 <main className="studio-main"><header className="studio-header"><div><span className="eyebrow">ЛОКАЛЬНОЕ ПРОСТРАНСТВО</span><h1>{page==='graph'?'Атлас знаний':page==='insights'?'Аналитика памяти':page==='galaxy'?'Галактика знаний':'Диалог с агентом'}</h1><p>Интерактивный интерфейс · реальные данные Yorimiyu</p></div><div className="studio-actions"><select aria-label="Выберите агента" value={agent} onChange={e=>setAgent(e.target.value)}><option value="">Выберите агента</option>{agents.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select><button onClick={()=>void refresh()} disabled={busy}>{busy?'Загрузка…':'Обновить'}</button></div></header>
 {error&&<div className="error" role="alert">{error}</div>}
 <div className="kpis"><div><small>УЗЛЫ</small><strong>{graph.nodes.length}</strong></div><div><small>СВЯЗИ</small><strong>{graph.edges.length}</strong></div><div><small>ЗАПИСИ ПАМЯТИ</small><strong>{memories.length}</strong></div><div><small>СООБЩЕНИЯ</small><strong>{messages.length}</strong></div></div>
 {page==='graph'&&<div className="graph-grid"><section className="visual-panel"><div className="panel-title"><h2>Карта связей</h2><input aria-label="Поиск узла" placeholder="Найти узел…" value={query} onChange={e=>setQuery(e.target.value)}/></div><div className="flow-wrap">{visible.length?<ReactFlow nodes={flowNodes} edges={flowEdges} onNodeClick={(_,n)=>setSelected(graph.nodes.find(x=>x.id===n.id)||null)} fitView minZoom={.08} maxZoom={2} proOptions={{hideAttribution:true}}><Background gap={22} color="#eee5da"/><Controls/><MiniMap pannable zoomable nodeColor={n=>n.style?.background==='#fff0ed'?'#b64e5a':'#c49a5d'}/></ReactFlow>:<div className="empty">Нет узлов для отображения. Добавьте записи памяти или измените поиск.</div>}</div><p className="hint">Показано {visible.length} из {graph.nodes.length} узлов · поиск, перемещение и масштабирование</p></section><aside className="visual-panel inspector"><h2>Инспектор</h2>{selected?<><span className="eyebrow">{selected.kind||'узел'}</span><p>{selected.label}</p><button onClick={()=>setSelected(null)}>Сбросить выбор</button></>:<p>Нажмите на узел графа, чтобы увидеть подробности.</p>}<h3>Типы узлов</h3>{types.map(x=><div className="type-row" key={x.name}><span>{x.name}</span><strong>{x.value}</strong></div>)}</aside></div>}
 {page==='insights'&&<div className="visual-panel insights"><h2>Состав графа знаний</h2>{types.length?<ReactECharts option={chart} style={{height:440}} notMerge lazyUpdate/>:<p className="empty">Пока нет данных для анализа.</p>}<p className="hint">Данные берутся из локальной SQLite. Это статистика узлов, не статистика токенов Cloud.ru.</p></div>}
 {page==='galaxy'&&<section className="visual-panel"><h2>Трёхмерная карта знаний</h2>{graph.nodes.length?<Galaxy nodes={graph.nodes}/>:<div className="empty">Нет узлов для трёхмерной визуализации.</div>}</section>}
 {page==='chat'&&<section className="visual-panel chat-studio"><div className="chat-stream">{messages.length?messages.map(m=><div key={m.id} className={'bubble '+(m.role==='user'?'user':'assistant')}><small>{m.role==='user'?'Вы':'Yorimiyu'}</small><p>{m.content}</p></div>):<div className="empty">Выберите агента и отправьте первое сообщение.</div>}</div><form onSubmit={send}><textarea value={draft} onChange={e=>setDraft(e.target.value)} maxLength={8000} placeholder="Напишите сообщение агенту…"/><button disabled={busy||!agent||!draft.trim()}>Отправить</button></form><p className="hint">Сообщения сохраняются локально. Ошибки и лимиты Cloud.ru сообщает основной Python API.</p></section>}
 </main></div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
