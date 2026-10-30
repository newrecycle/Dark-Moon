const assert=require('node:assert/strict'),{Pager}=require('../../mcp/community/static/run-paging.js');
const rows=Array.from({length:50},(_,i)=>({run_id:'job_'+i,campaign_id:'c_1',status:'running',state:'running'}));
const first={data:rows,total:51,limit:50,offset:0,has_more:true,next_offset:null,next_cursor:'cursor_one',paging_limit_reached:false,ordering:'created_at_desc,id_desc',page_consistency:'live_keyset'};
const p=new Pager();assert.match(p.query(0),/pagination=cursor/);p.accept(first,0);assert.match(p.query(50),/cursor=cursor_one/);
p.accept({...first,data:[],total:500,has_more:false,next_cursor:null},50);
assert.match(p.label('History',{data:[],total:500},50),/page 2/);
for(const change of [{next_cursor:null},{next_cursor:'invalid<script>'},{data:[rows[0],rows[0]]},{page_consistency:'unknown'}])assert.throws(()=>new Pager().accept({...first,...change},0));
p.reset();p.accept({...first,page_consistency:'live_offset',next_cursor:undefined,next_offset:50},0);assert.equal(p.query(50),'limit=50&offset=50');
console.log('PASS cursor consumer: exact continuation, independent reset, typed legacy compatibility and malformed-page rejection');

const frozen=new Pager();frozen.reset('snapshot');assert.match(frozen.query(0),/pagination=snapshot/);
const frozenPage={...first,page_consistency:'frozen_run_metadata',next_cursor:undefined,next_offset:50,snapshot:'rs_'+'a'.repeat(32),snapshot_expires_at:9999999999};
frozen.accept(frozenPage,0);assert.match(frozen.query(50),/snapshot=rs_/);
assert.throws(()=>frozen.accept({...frozenPage,offset:50,snapshot:'rs_'+'b'.repeat(32)},50));
