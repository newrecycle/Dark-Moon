const assert=require('node:assert/strict');
const query=require('../../mcp/community/static/finding-query.js');
const base=query.read('#findings');
const rows=[
  {id:'b',campaign_id:'camp_a',target_id:'t1',severity:'high',status:'confirmed',category:'sqli',title:'SQL query',cvss_score:8.1},
  {id:'a',campaign_id:'camp_a',target_id:'t1',severity:'high',status:'confirmed',category:'sqli',title:'SQL query',cvss_score:8.1},
  {id:'c',campaign_id:'camp_b',target_id:'t2',severity:'low',status:'unconfirmed',category:'config',title:'Header',cvss_score:0},
  {id:'d',campaign_id:'camp_b',target_id:'t2',severity:'critical',status:'exploited',category:'sqli',title:'Critical query',cvss_score:null},
];
const state={...base,q:'SQL & <script> with space ',severity:'high',status:'confirmed',category:'sqli',campaign_id:'camp_a',target_id:'t1',sort:'cvss_asc',size:10,page:2};
assert.deepEqual(query.read(query.hash(state)),state);
for(const sort of query.sorts){
  const a=query.page(rows,{...base,sort}),b=query.page([...rows].reverse(),{...base,sort});
  assert.deepEqual(a.items,b.items);assert.ok(a.items.findIndex(f=>f.id==='a')<a.items.findIndex(f=>f.id==='b'));
}
assert.deepEqual(query.page(rows,{...base,sort:'cvss_asc'}).items.map(f=>f.id),['c','a','b','d']);
assert.deepEqual(query.page(rows,{...base,sort:'cvss_desc'}).items.map(f=>f.id),['a','b','c','d']);
const matches=query.page(rows,{...state,q:'SQL',page:1});assert.equal(matches.total,2);
const empty=query.page(rows,{...base,q:'absent',page:100});assert.equal(empty.total,0);assert.equal(empty.page,1);
const many=Array.from({length:20000},(_,i)=>({...rows[0],id:'f'+String(i).padStart(6,'0')}));
const last=query.page(many,{...base,size:25,page:99999});assert.equal(last.items.length,25);assert.equal(last.page,800);assert.equal(last.items[0].id,'f019975');
assert.equal(query.read('#findings?page=Infinity&size=999&sort=bad').page,1);
assert.equal(query.read('#findings?page=Infinity&size=999&sort=bad').size,50);
console.log('Finding query: URL round-trip, composed filters, stable ties, zero/missing CVSS and bounded 20k-record pages passed.');
