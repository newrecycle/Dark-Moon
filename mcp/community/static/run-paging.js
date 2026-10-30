"use strict";
(function(root){
  class Pager {
    constructor(){this.reset();}
    reset(mode='cursor'){this.mode=mode;this.snapshot=null;this.cursors=new Map([[0,null]]);}
    query(offset){
      if(this.mode==='snapshot'){const q=new URLSearchParams({limit:'50',offset:String(offset),pagination:'snapshot'});if(this.snapshot)q.set('snapshot',this.snapshot);return q.toString();}
      if(this.mode==='offset')return `limit=50&offset=${offset}`;
      if(!this.cursors.has(offset))throw new Error('Run page position is no longer available; reset pages');
      const q=new URLSearchParams({limit:'50',pagination:'cursor'}),cursor=this.cursors.get(offset);
      if(cursor)q.set('cursor',cursor);
      return q.toString();
    }
    accept(page,offset){
      const invalid=()=>{throw new Error('Run collection did not match the expected metadata contract');};
      if(!page || !Array.isArray(page.data) || page.data.length>50 || page.limit!==50 ||
         !Number.isSafeInteger(page.total) || page.total<page.data.length ||
         typeof page.has_more!=='boolean' || typeof page.paging_limit_reached!=='boolean' ||
         page.ordering!=='created_at_desc,id_desc')invalid();
      if(page.data.some(row=>!row || typeof row.run_id!=='string' || !row.run_id || row.run_id.length>200 ||
         typeof row.state!=='string' || typeof row.status!=='string' ||
         !(row.campaign_id===null || typeof row.campaign_id==='string')) ||
         new Set(page.data.map(row=>row.run_id)).size!==page.data.length)invalid();
      if(page.page_consistency==='frozen_run_metadata'){
        const end=offset+page.data.length;
        if(this.mode!=='snapshot' || page.offset!==offset || page.total<end || page.has_more!==(end<page.total) || page.paging_limit_reached ||
           (page.has_more?page.next_offset!==end:page.next_offset!==null) ||
           typeof page.snapshot!=='string' || !/^rs_[a-f0-9]{32}$/.test(page.snapshot) || this.snapshot && this.snapshot!==page.snapshot ||
           !Number.isFinite(page.snapshot_expires_at))invalid();
        this.snapshot=page.snapshot;return;
      }
      if(page.page_consistency==='live_offset'){
        const end=offset+page.data.length;
        if(page.offset!==offset || page.data.length && page.total<end ||
           page.has_more!==(end<page.total && end<=100000) ||
           page.paging_limit_reached!==(end<page.total && !page.has_more) ||
           (page.has_more?page.next_offset!==end || end<=offset:page.next_offset!==null))invalid();
        // Explicit valid legacy metadata permits compatibility; transport/errors never trigger fallback.
        this.mode='offset';return;
      }
      if(this.mode!=='cursor' || page.page_consistency!=='live_keyset' || page.offset!==0 ||
         page.next_offset!==null || page.paging_limit_reached || !this.cursors.has(offset))invalid();
      if(page.has_more){
        if(page.data.length!==50 || typeof page.next_cursor!=='string' || !/^[A-Za-z0-9_-]{1,1022}={0,2}$/.test(page.next_cursor) ||
           page.next_cursor===this.cursors.get(offset))invalid();
      }else if(page.next_cursor!==null)invalid();
      for(const key of this.cursors.keys())if(key>offset)this.cursors.delete(key);
      if(page.has_more)this.cursors.set(offset+50,page.next_cursor);
    }
    label(name,page,offset){
      return this.mode==='snapshot'?`${name} frozen page ${Math.floor(offset/50)+1} · ${page.data.length} shown · ${page.total} captured matches`:this.mode==='cursor'?`${name} page ${Math.floor(offset/50)+1} · ${page.data.length} shown · ${page.total} matching now`:
        `${name} ${page.data.length?offset+1:0}–${page.data.length?offset+page.data.length:0} of ${page.total}`;
    }
  }
  if(typeof module!=='undefined')module.exports={Pager};else root.RunPaging={Pager};
})(globalThis);
