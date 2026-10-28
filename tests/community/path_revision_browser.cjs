// Real Chromium component acceptance against the production HTTP handler.
// Only app.js is replaced with a mount harness; paths.js, CSP and API are real.
const {chromium} = require((process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES + '/' : '') + 'playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs/promises'), path = require('node:path'), os = require('node:os');
const assert = require('node:assert/strict');
(async () => {
  const repo = path.resolve(__dirname, '../..'), root = await fs.mkdtemp(path.join(os.tmpdir(), 'darkmoon-path-browser-'));
  const child = spawn(process.env.DARKMOON_PYTHON || 'python3', [path.join(__dirname, 'path_revision_fixture.py')], {
    cwd:repo, env:{...process.env, PYTHONPATH:path.join(repo,'mcp'), DARKMOON_SHARED_DIR:root}});
  let browser;
  try {
    const fixture = await new Promise((resolve,reject) => {
      let output = '';
      const timer = setTimeout(() => reject(new Error('Path fixture startup timeout')),15000);
      child.stdout.on('data', chunk => {output += chunk; if (output.includes('\n')) {
        clearTimeout(timer); try {resolve(JSON.parse(output.split('\n')[0]));} catch(error) {reject(error);}
      }});
      child.stderr.on('data', chunk => process.stderr.write(chunk));
      child.once('exit', code => {clearTimeout(timer); reject(new Error('Path fixture exited '+code));});
    });
    browser = await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE} : {})});
    const page = await browser.newPage({viewport:{width:1280,height:1000}}), errors = [];
    page.setDefaultTimeout(12000);
    page.on('pageerror', error => errors.push(error.message));
    await page.clock.install();
    await page.route('**/app.js', route => route.fulfill({contentType:'text/javascript',body:`
      "use strict";
      const $ = selector => document.querySelector(selector);
      const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      let identity = {role:'admin'}, token = ${JSON.stringify(fixture.token)}, controller;
      const cid = ${JSON.stringify(fixture.campaign_id)};
      async function api(url,options={}) {
        const response = await fetch(url,{...options,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json',...options.headers}});
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || 'Request failed');
        return body;
      }
      async function grant() {return (await api('/api/v1/evidence/grants',{method:'POST',body:JSON.stringify({kind:'graph',id:cid,campaign_id:cid})})).grant;}
      async function rawGraph() {return (await api('/api/v1/evidence/graph/'+cid+'/reveal',{headers:{'X-Darkmoon-Evidence-Grant':await grant()}})).data;}
      window.remoteEdit = async id => {
        const current = (await rawGraph()).paths.find(p=>p.id===id);
        return api('/api/v1/campaigns/'+cid+'/paths/'+id,{method:'PUT',headers:{'X-Darkmoon-Evidence-Grant':await grant()},body:JSON.stringify({
          title:current.title,steps:current.steps.map(({edge_id,finding_id,rationale})=>({edge_id,finding_id,rationale})),reviewed:true,version:current.version})});
      };
      window.mountPaths = async (selected='') => {
        controller?.abort(); controller = new AbortController();
        document.body.innerHTML = '<main><section id="recorded-paths"></section><article id="path-card" hidden></article></main>';
        const graph = await api('/api/v1/campaigns/'+cid+'/graph');
        window.setupRecordedPaths({graph,cid,signal:controller.signal,card:$('#path-card'),
          stopLocationTour(){},highlight(){},selectStep(){}});
        if (selected) {$('#path-select').value=selected; $('#path-select').dispatchEvent(new Event('change'));}
      };
      document.addEventListener('DOMContentLoaded',()=>window.mountPaths());
    `}));
    for (const filename of ['workspace.js','finding-query.js','schedules.js','posture.js'])
      await page.route('**/'+filename, route => route.fulfill({contentType:'text/javascript',body:'"use strict";'}));
    await page.goto('http://127.0.0.1:'+fixture.port);
    await page.bringToFront();
    await page.locator('#path-reveal').waitFor();
    assert.equal(await page.locator('#path-form').count(),0);
    await page.locator('#path-reveal').click();
    await page.locator('#path-editor summary').click();
    await page.locator('#path-form [name="title"]').fill('Reviewed <script>window.injected=1</script> path');
    const select = async index => {
      for (const key of ['edge','finding']) {
        const control = page.locator('[data-path-'+key+'="'+index+'"]');
        await control.selectOption(await control.locator('option').nth(1).getAttribute('value'));
      }
      await page.locator('[data-path-rationale="'+index+'"]').fill('Review rationale '+index+' <script>window.injected=1</script>');
    };
    await select(0); await page.locator('#path-add-step').click(); await select(1);
    await page.locator('#path-form [name="reviewed"]').check();
    await page.locator('#path-form [type="submit"]').click();
    await page.locator('#path-status').filter({hasText:'Reviewed path saved'}).waitFor();
    const id = await page.locator('#path-select').inputValue(); assert.match(id,/^path_/);
    await page.locator('#path-edit').click();
    assert.equal(await page.locator('#path-form [name="reviewed"]').isChecked(),false);
    await page.locator('#path-form [name="title"]').fill('Second review');
    await page.locator('#path-form [name="reviewed"]').check();
    await page.locator('#path-form [type="submit"]').click();
    await page.locator('#path-status').filter({hasText:'revision 2'}).waitFor();
    await page.locator('#path-history-open').click();
    await page.locator('[data-path-revision="2"]').waitFor();
    assert.match(await page.locator('[data-path-revision="1"]').innerText(),/Reviewed <script>/);
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    await page.locator('#path-edit').click();
    await page.locator('#path-form [name="title"]').fill('Preserve this stale draft');
    await page.evaluate(id=>window.remoteEdit(id),id);
    await page.locator('#path-form [name="reviewed"]').check();
    await page.locator('#path-form [type="submit"]').click();
    await page.locator('#path-save-status').filter({hasText:'Path changed'}).waitFor();
    assert.equal(await page.locator('#path-form [name="title"]').inputValue(),'Preserve this stale draft');
    await page.evaluate(id=>window.mountPaths(id),id);
    await page.locator('#path-reveal').click();
    await page.locator('#path-play').click();
    await page.locator('#path-card').filter({hasText:'Step 1 of 2'}).waitFor();
    await page.evaluate(id=>window.remoteEdit(id),id);
    await page.locator('#path-next').click();
    await page.locator('#path-status').filter({hasText:'Recorded path changed'}).waitFor();
    assert.equal(await page.locator('#path-card').isVisible(),false);
    await page.locator('#path-play').click();
    await page.locator('#path-next').click();
    await page.locator('#path-card').filter({hasText:'Step 2 of 2'}).waitFor();
    await page.locator('#path-back').click();
    await page.locator('#path-card').filter({hasText:'Step 1 of 2'}).waitFor();
    const screenshots = process.env.DARKMOON_SCREENSHOTS || path.join(root,'screenshots');
    await fs.mkdir(screenshots,{recursive:true});
    await page.screenshot({path:path.join(screenshots,'path-revisions-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
    await page.screenshot({path:path.join(screenshots,'path-revisions-mobile.png'),fullPage:true});
    await page.locator('#path-free').click();
    await page.locator('#path-history-open').click();
    await page.locator('[data-path-revision="4"]').waitFor();
    await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
    assert.equal(await page.locator('[data-path-revision]').count(),0);
    assert.equal(await page.locator('#path-form').count(),0);
    assert.doesNotMatch(await page.locator('body').innerText(),/Review rationale|Second review/);
    await page.locator('#path-reveal').click();
    await page.locator('#path-history-open').click();
    await page.locator('[data-path-revision="4"]').waitFor();
    await page.clock.fastForward(45001);
    assert.equal(await page.locator('[data-path-revision]').count(),0);
    assert.equal(await page.locator('#path-form').count(),0);
    assert.equal(await page.locator('#path-play').isDisabled(),true);
    await page.locator('#path-reveal').click();
    await page.locator('#path-delete').click();
    await page.locator('#path-status').filter({hasText:'Recorded path deleted'}).waitFor();
    assert.equal(await page.locator('#path-select option').count(),1);
    assert.deepEqual(errors,[]);
    console.log('Path component browser: create/edit/history, stale save, revision-pinned playback, focus/expiry clearing and responsive layout passed.');
  } finally {
    if (browser) await browser.close();
    child.kill('SIGTERM');
    await new Promise(resolve => {if (child.exitCode !== null || child.signalCode) resolve(); else {
      const timer=setTimeout(()=>{child.kill('SIGKILL');resolve();},3000);
      child.once('exit',()=>{clearTimeout(timer);resolve();});
    }});
    await fs.rm(root,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
