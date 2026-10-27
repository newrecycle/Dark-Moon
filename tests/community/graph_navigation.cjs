// Exercise the actual graph controller with a minimal DOM/canvas adapter.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('mcp/community/static/app.js', 'utf8');
const controller = source.slice(source.indexOf('async function drawSurface('), source.indexOf('async function startVR('));
async function run(graph) {
  const elements = new Map(); let focused;
  function element(id) {
    const el = {hidden: id === '#surface-tour-card', disabled:false, value:'', events:{}, textContent:'',
      addEventListener(type, fn) { this.events[type] = fn; },
      focus() { focused = id; },
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
  const context = {api:async()=>graph, $:id=>elements.get(id),window:{devicePixelRatio:1},navigator:{},
    requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{},severityColors:{},esc:s=>String(s).replaceAll('<','&lt;'), badge:s=>s,empty:(s,t)=>s+' '+t,fail:e=>{throw e}};
  vm.createContext(context);vm.runInContext(controller,context);
  const abort = new AbortController(); await context.drawSurface('campaign-1',abort.signal);
  const el=id=>elements.get(id), click=id=>el(id).events.click();
  return {el,click,focus:()=>focused,abort};
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
  abort.abort();
  const empty=await run({nodes:[],edges:[],findings:[]});
  assert.equal(empty.el('#surface-node').disabled,true);assert.equal(empty.el('#surface-tour').disabled,true);
  empty.abort.abort();console.log('Graph navigation: multi-step, linkage, empty states and focus checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
