const assert = require('node:assert/strict');
const routes = require('../../mcp/community/static/resource-routes.js');
for (const [kind,id,cid] of [['campaign','camp_1'],['vulnerability','vuln_1','camp_1']]) {
  const parsed=routes.read(routes.link(kind,id,cid));
  assert.equal(parsed.kind,kind); assert.equal(parsed.id,id);
  if(cid) assert.equal(parsed.campaignId,cid);
}
for(const hash of ['#campaign/../secret','#campaign/camp_1?grant=secret',
  '#vulnerability/vuln_1','#vulnerability/vuln_1?campaign_id=a&campaign_id=b',
  '#vulnerability/vuln_1?campaign_id=a&token=secret','#campaign/%3Cscript%3E',
  '#campaign/camp_1/extra','#findings?q=normal']) assert.equal(routes.read(hash),null,hash);
assert.throws(()=>routes.link('campaign','<script>'));
console.log('PASS resource routes: exact scoped identities and secret-free strict links');
