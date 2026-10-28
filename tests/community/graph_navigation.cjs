// Exercise the actual graph controller with a minimal DOM/canvas adapter.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('mcp/community/static/app.js', 'utf8');
const controller = source.slice(source.indexOf('async function drawSurface('), source.indexOf('async function startVR('));
async function run(graph, options = {}) {
  const elements = new Map(); let focused;
  function element(id) {
    const el = {hidden: id === '#surface-tour-card', disabled:false, value:'', events:{}, textContent:'', classList:{add(){},remove(){}},
      addEventListener(type, fn) { this.events[type] = fn; },
      focus() { focused = id; },
      querySelectorAll() { return []; },
      getBoundingClientRect() { return {width:900,height:500,left:0,top:0}; },
      getContext() { return new Proxy({}, {get:()=>()=>{}}); },
      set innerHTML(value) {
        this.html = value;
        for (const tag of value.matchAll(/<[^>]*id="([^"]+)"[^>]*>/g)) {
          const child = element('#' + tag[1]); child.disabled = /\bdisabled\b/.test(tag[0]);
        }
      }, get innerHTML() { return this.html || ''; }
    }; elements.set(id,el); return el;
  }
  for (const id of ['#surface-canvas','#map-info','#surface-controls','#surface-tour-card','#surface-tour','#vr-button']) element(id);
  const requests = [];
  const context = {api:async path=>{
    requests.push(path);
    if (path.endsWith('/graph')) return graph;
    if (path.includes('/pull-requests')) return {data:options.proposals || []};
    return options.campaign ? await options.campaign() : {findings:graph.findings};
  }, $:id=>elements.get(id),window:{devicePixelRatio:1},navigator:{},
    requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{},severityColors:{},esc:s=>String(s).replaceAll('<','&lt;'), badge:s=>s,empty:(s,t)=>s+' '+t,fail:e=>{throw e}};
  vm.createContext(context);vm.runInContext(controller,context);
  const abort = new AbortController(); await context.drawSurface('campaign-1',abort.signal);
  const el=id=>elements.get(id), click=id=>el(id).events.click();
  const finding = id=>el('#map-info').events.click({target:{closest:()=>({dataset:{surfaceFinding:id}})}});
  return {el,click,finding,requests,focus:()=>focused,abort};
}
(async()=>{
  const graph={nodes:[{id:'a',label:'Asset A',node_type:'service',ip_address:'192.0.2.1',technology:'<script>test</script>'},{id:'b',label:'Asset B'},{id:'c',label:'Empty asset'}],edges:[],findings:[{id:'f1',node_id:'a',title:'Finding A',severity:'high',cvss_score:0,category:'test-category',status:'confirmed'},{id:'f2',node_id:'b',title:'Finding B',severity:'low'}]};
  const {el,click,focus,abort}=await run(graph);
  el('#surface-node').value='c'; el('#surface-node').events.change();
  assert.match(el('#map-info').innerHTML,/No linked findings/);
  click('#surface-close');assert.equal(focus(),'#surface-node');
  click('#surface-tour');assert.equal(el('#surface-tour-card').hidden,false);
  assert.match(el('#surface-tour-card').innerHTML,/Step 1 of 2/);
  assert.match(el('#map-info').innerHTML,/Finding A/);assert.doesNotMatch(el('#map-info').innerHTML,/Finding B/);
  assert.equal(el('#surface-prev').disabled,true);
  assert.match(el('#map-info').innerHTML,/192.0.2.1/);assert.match(el('#map-info').innerHTML,/CVSS 0/);assert.match(el('#map-info').innerHTML,/test-category/);assert.doesNotMatch(el('#map-info').innerHTML,/<script>/);
  click('#surface-next');assert.match(el('#surface-tour-card').innerHTML,/Step 2 of 2/);
  assert.match(el('#surface-tour-card').innerHTML,/>Finish<\/button>/);assert.equal(focus(),'#surface-next');
  click('#surface-prev');assert.match(el('#surface-tour-card').innerHTML,/Step 1 of 2/);
  click('#surface-free');assert.equal(el('#surface-tour-card').hidden,true);assert.equal(focus(),'#surface-tour');
  click('#surface-tour');click('#surface-next');click('#surface-next');assert.equal(el('#surface-tour-card').hidden,true);assert.equal(focus(),'#surface-tour');
  click('#surface-tour');
  el('#surface-node').value='c';el('#surface-node').events.change();
  assert.equal(el('#surface-tour-card').hidden,true);
  assert.equal(el('#surface-tour').textContent,'Tour finding locations');
  assert.match(el('#map-info').innerHTML,/Empty asset/);
  click('#surface-tour');click('#surface-close');
  assert.equal(el('#surface-tour-card').hidden,true);assert.equal(focus(),'#surface-node');
  click('#surface-tour');el('#surface-node').value='';el('#surface-node').events.change();
  assert.equal(el('#surface-tour-card').hidden,true);
  assert.match(el('#map-info').innerHTML,/Select an asset/);
  assert.equal(focus(),'#surface-node');
  abort.abort();
  const panel=await run(graph,{proposals:[
    {id:'p1',campaign_id:'campaign-1',finding_ids:['f1'],title:'Actual fix',status:'validated'},
    {id:'other',campaign_id:'campaign-2',finding_ids:['f1'],title:'Wrong campaign'},
  ]});
  panel.el('#surface-node').value='a';panel.el('#surface-node').events.change();
  assert.match(panel.el('#map-info').innerHTML,/Proposal recorded/);
  await panel.finding('f1');
  assert.match(panel.el('#map-info').innerHTML,/Back to Asset A/);
  assert.match(panel.el('#map-info').innerHTML,/Actual fix/);
  assert.doesNotMatch(panel.el('#map-info').innerHTML,/Wrong campaign/);
  assert.match(panel.el('#map-info').innerHTML,/data-report-preview="campaign-1"/);
  assert.match(panel.el('#map-info').innerHTML,/data-proposal-finding="f1"/);
  assert.equal(panel.focus(),'#surface-finding-title');
  panel.click('#surface-back');assert.match(panel.el('#map-info').innerHTML,/Finding A/);
  panel.el('#surface-node').value='b';panel.el('#surface-node').events.change();
  await panel.finding('f2');assert.match(panel.el('#map-info').innerHTML,/No proposal recorded/);
  panel.abort.abort();
  const missing=await run(graph,{campaign:async()=>({findings:[]})});
  missing.el('#surface-node').value='a';missing.el('#surface-node').events.change();
  await missing.finding('f1');assert.match(missing.el('#map-info').innerHTML,/Finding unavailable/);
  missing.abort.abort();
  let resolveCampaign;
  const stale=await run(graph,{campaign:()=>new Promise(resolve=>{resolveCampaign=resolve})});
  stale.el('#surface-node').value='a';stale.el('#surface-node').events.change();
  const pending=stale.finding('f1');
  stale.el('#surface-node').value='c';stale.el('#surface-node').events.change();
  resolveCampaign({findings:graph.findings});await pending;
  assert.match(stale.el('#map-info').innerHTML,/Empty asset/);
  assert.doesNotMatch(stale.el('#map-info').innerHTML,/Back to Asset A/);
  stale.abort.abort();
  const empty=await run({nodes:[],edges:[],findings:[]});
  assert.equal(empty.el('#surface-node').disabled,true);assert.equal(empty.el('#surface-tour').disabled,true);
  empty.abort.abort();console.log('Graph navigation: multi-step, linkage, empty states and focus checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
