const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function app(){
  const html=fs.readFileSync(path.join(__dirname,'../static/index.html'),'utf8');
  const source=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/boot\(\);\s*$/,'');
  const values=new Map(),elements=new Map(),events=new Map(),timers=[];
  function element(id){if(!elements.has(id))elements.set(id,{id,textContent:'',className:'',disabled:false,
    classList:{contains:()=>false,remove(){},add(){}},setAttribute(name,value){this[name]=value},querySelectorAll:()=>[]});return elements.get(id)}
  const context=vm.createContext({console,AbortController,URL,Date,localStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)},
    document:{getElementById:element,querySelectorAll:()=>[],addEventListener(){}},
    window:{addEventListener:(name,callback)=>events.set(name,callback),scrollTo(){}},location:{hash:''},history:{},setTimeout:(callback,ms)=>{timers.push({callback,ms});return timers.length},clearTimeout(){}});
  vm.runInContext(source,context);
  return {run:code=>vm.runInContext(code,context),context,values,elements,events,timers};
}

test('completion messages distinguish success, partial, failure and unknown',()=>{
  const a=app();
  for(const outcome of ['partial','failed','idle'])assert.equal(a.run(`completionInfo({outcome:'${outcome}'}).error`),true);
  assert.equal(a.run("completionInfo({outcome:'success'}).error"),false);
  assert.equal(a.run("completionInfo({last_result:{outcome:'partial'}}).error"),true);
  assert.equal(a.run("completionInfo({outcome:'success',error:'failed'}).error"),true);
});

test('pending work is shown with its count instead of a source failure',()=>{
  const a=app();
  a.run(`showConnectionState({roku:{connected:true},data:{outcome:'pending',pending_offers:462,incomplete:true,last_result:{outcome:'pending'}}})`);
  assert.match(a.elements.get('dataHealth').title,/462/);
  assert.doesNotMatch(a.elements.get('dataHealth').title,/parcial|falhou/);
  assert.equal(a.run(`completionInfo({outcome:'pending',pending_offers:462}).error`),false);
});

test('live progress wins over an old failure but a completed failure stays visible',()=>{
  const a=app();
  a.run(`showConnectionState({roku:{connected:true},data:{running:true,outcome:'running',done:27,total:462,last_result:{outcome:'failed'}}})`);
  assert.match(a.elements.get('dataHealth').title,/27\/462/);
  a.run(`showConnectionState({roku:{connected:true},data:{running:false,outcome:'failed',incomplete:true,last_result:{outcome:'failed'}}})`);
  assert.equal(a.elements.get('dataHealth').className,'bad');
  assert.match(a.elements.get('dataHealth').title,/falhou/);
});

test('successful completion clears the warning and real source failures remain partial',()=>{
  const a=app();
  a.run(`showConnectionState({roku:{connected:true},data:{outcome:'success',pending_offers:0,incomplete:false,synced_at:1792864744,last_result:{outcome:'success'}}})`);
  assert.equal(a.elements.get('dataHealth').className,'good');
  a.run(`showConnectionState({roku:{connected:true},data:{outcome:'partial',pending_offers:0,incomplete:true,last_result:{outcome:'partial',problems:['Lista indisponível']}}})`);
  assert.equal(a.elements.get('dataHealth').className,'warn');
  assert.match(a.elements.get('dataHealth').title,/fontes/);
});

test('an open connection panel updates progress and clears obsolete problems on completion',()=>{
  const a=app();
  a.run(`updateConnectionDetails({running:true,done:1,total:3,step:'Consultando',pending_offers:2,coverage:{fresh:8,total:10,max_age_days:3},last_result:{problems:['Fonte indisponível']}})`);
  assert.match(a.elements.get('connectionProgress').textContent,/1\/3/);
  assert.match(a.elements.get('connectionCoverage').textContent,/8 de 10/);
  assert.equal(a.elements.get('connectionProblems').hidden,false);
  a.run(`updateConnectionDetails({running:false,pending_offers:0,coverage:{fresh:10,total:10,max_age_days:3},last_result:{problems:[]}})`);
  assert.equal(a.elements.get('connectionProgress').hidden,true);
  assert.equal(a.elements.get('connectionProblems').hidden,true);
  assert.match(a.elements.get('connectionCoverage').textContent,/10 de 10/);
  assert.doesNotMatch(a.elements.get('connectionCoverage').textContent,/Faltam/);
});

test('patches preserve other device fields and empty queues stay empty',()=>{
  const a=app();
  assert.equal(a.run('JSON.stringify(mergePrefs({},{}))'),'{}');
  assert.equal(a.run('JSON.stringify(mergePrefs({lists:{watchlist:{sort:7,genre:"Drama"}}},{lists:{watchlist:{focus_id:"tt1"}}}).lists.watchlist)'),
    '{"sort":7,"genre":"Drama","focus_id":"tt1"}');
  assert.equal(a.run('mergePrefs({lists:{watchlist:{seen:0}}},{unseen:true}).lists.watchlist.seen'),1);
});

test('new edits while a save is in flight survive the response',async()=>{
  const a=app();
  a.run('queuePrefs({lists:{watchlist:{sort:7}}}); api=()=>new Promise(resolve=>{globalThis.finishSave=resolve}); globalThis.saving=flushPrefs(); queuePrefs({lists:{watchlist:{genre:"Drama"}}});');
  a.run('finishSave({revision:1,unseen:false,lists:{watchlist:{sort:7}}})');
  await a.context.saving;
  assert.equal(a.run('PREFS.lists.watchlist.genre'),'Drama');
  assert.equal(a.run('PENDING.lists.watchlist.genre'),'Drama');
  assert.equal(JSON.parse(a.values.get('pendingPrefs')).lists.watchlist.genre,'Drama');
});

test('failed save retains edits for retry and reload',async()=>{
  const a=app();
  a.run('queuePrefs({lists:{watchlist:{sort:6}}});api=async()=>{throw Error("offline")};toast=()=>{}');
  await a.run('flushPrefs()');
  assert.equal(a.run('PENDING.lists.watchlist.sort'),6);
  assert.equal(JSON.parse(a.values.get('pendingPrefs')).lists.watchlist.sort,6);
});

test('a response to a position save also applies the other device global filter',async()=>{
  const a=app();
  a.run('queuePrefs({lists:{watchlist:{focus_id:"tt1"}}});api=async()=>({revision:2,unseen:true,lists:{watchlist:{focus_id:"tt1"}}})');
  await a.run('flushPrefs()');
  assert.equal(a.run('UNSEEN'),true);
  assert.equal(a.elements.get('unseen').checked,true);
});

test('a delayed response from the previous sync cannot report success for the current sync',async()=>{
  const a=app();
  a.run(`syncWatching=true;syncTarget=200;HOME={};globalThis.messages=[];toast=(m)=>messages.push(m);loadHome=async()=>{};refreshPrefs=async()=>{};
    api=async(path)=>path==='/api/status'?{running:false,started_at:100,completed_at:101,outcome:'success'}:{roku:{connected:true},data:{},computer:{}};`);
  await a.run('pollStatus()');
  assert.equal(a.run('messages.length'),0);
  assert.equal(a.run('syncWatching'),true);
});

test('a slow list response cannot replace the page after the user goes back',async()=>{
  const a=app();
  a.run(`HOME={rows:[{id:'watchlist',name:'Watchlist'}]};header=()=>{};globalThis.paints=[];
    showHome=()=>paints.push('home');showList=()=>paints.push('list');restoreHomePosition=()=>{};
    loadList=()=>new Promise(resolve=>globalThis.finishList=resolve);location.hash='#l/watchlist';globalThis.firstRoute=route();`);
  a.run("location.hash='';route();finishList({id:'watchlist',award:false,items:[]})");
  await a.context.firstRoute;
  assert.equal(a.run('JSON.stringify(paints)'),'["home"]');
});

test('layout and programmatic scrolling do not overwrite the selected title',()=>{
  const a=app();
  a.run('ACTIVE_LIST="watchlist";queuePrefs({lists:{watchlist:{focus_id:"tt6333056"}}});');
  const before=a.timers.length;
  a.events.get('scroll')();
  assert.equal(a.timers.length,before);
  assert.equal(a.run('PENDING.lists.watchlist.focus_id'),'tt6333056');
  a.events.get('wheel')();
  a.events.get('scroll')();
  assert.equal(a.timers.length,before+1);
});

test('series poster displays only its authoritative TV award strip',()=>{
  const a=app();
  const markup=a.run(`poster({id:'tt1',series:true,title:'Show',strips:[{t:'Emmy · Drama',w:true,i:'trophy'},{t:'Golden Globe',w:true,i:'trophy'}]},[{t:'Wrong movie award',w:true,i:'trophy'}],'')`);
  assert.equal((markup.match(/class="strip /g)||[]).length,1);
  assert.match(markup,/Emmy/);
  assert.doesNotMatch(markup,/Golden Globe|Wrong movie award/);
});

test('award pages cannot add a second movie award strip to a series',()=>{
  const a=app();
  assert.equal(a.run(`JSON.stringify(awardStrips({t:'Oscar'}, {series:true,strips:[{t:'Emmy'},{t:'BAFTA'}]},''))`),'[{"t":"Emmy"}]');
});
