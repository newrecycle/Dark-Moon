// Local acceptance test. Requires Playwright and a Chromium executable.
// No real scans, cloud changes, model calls, Git pushes or PR creation.
const { chromium } = require(
  process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
    ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES + "/playwright"
    : "playwright",
);
const { spawn } = require("node:child_process");
const fs = require("node:fs/promises"),
  os = require("node:os"),
  path = require("node:path");
const assert = require("node:assert/strict");

(async () => {
  const root = await fs.mkdtemp(
    path.join(os.tmpdir(), "darkmoon-browser-test-"),
  );
  const repo = path.resolve(__dirname, "../..");
  const child = spawn(
    process.env.DARKMOON_PYTHON || "python3",
    [path.join(__dirname, "browser_fixture.py")],
    {
      cwd: repo,
      env: {
        ...process.env,
        PYTHONPATH: path.join(repo, "mcp"),
        DARKMOON_SHARED_DIR: root,
        DARKMOON_FIXTURE_NO_ACCOUNTS: "1",
        DARKMOON_DASHBOARD_TOKEN: "offline-browser-fixture-token-123456789",
      },
    },
  );
  let browser, fixture;
  const errors = [];
  try {
    fixture = await new Promise((resolve, reject) => {
      let output = "";
      const timer = setTimeout(
        () => reject(new Error("Fixture startup timed out")),
        15000,
      );
      child.stdout.on("data", (chunk) => {
        output += chunk;
        if (output.includes("\n")) {
          clearTimeout(timer);
          try {
            resolve(JSON.parse(output.split("\n")[0]));
          } catch (e) {
            reject(e);
          }
        }
      });
      child.stderr.on("data", (chunk) => process.stderr.write(chunk));
      child.on("exit", (code) => {
        clearTimeout(timer);
        reject(new Error(`Fixture exited ${code}`));
      });
    });
    browser = await chromium.launch({
      headless: true,
      ...(process.env.CHROMIUM_EXECUTABLE
        ? { executablePath: process.env.CHROMIUM_EXECUTABLE }
        : {}),
    });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      timezoneId: "America/Edmonton",
    });
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("dialog", (dialog) => {
      errors.push("Unexpected browser dialog");
      dialog.dismiss();
    });
    const screenshots =
      process.env.DARKMOON_SCREENSHOTS || path.join(root, "screenshots");
    await fs.mkdir(screenshots, { recursive: true });
    await page.goto(`http://127.0.0.1:${fixture.port}`);
    await page.locator("#token").fill(fixture.token);
    await page.locator("#login-form button[type=submit]").click();
    await page.locator("#login").waitFor({ state: "hidden" });
    await page.getByText("Your security workspace").waitFor();
    await page.locator('#setup-account[open]').waitFor();
    await page.screenshot({path:path.join(screenshots,'first-use.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
    await page.screenshot({path:path.join(screenshots,'first-use-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    await page.locator('#setup-account-skip').click();
    await page.locator('#setup-account').waitFor({state:'hidden'});
    await page.locator('#logout').click();
    await page.locator('#token').fill(fixture.token);
    await page.locator('#login-form button[type=submit]').click();
    await page.locator('#setup-account[open]').waitFor();
    await page.locator('#setup-account-form [name=username]').fill('fixture-admin');
    await page.locator('#setup-account-form [name=password]').fill('offline-fixture-password');
    await page.locator('#setup-account-form [name=confirmation]').fill('mismatched-fixture-password');
    await page.locator('#setup-account-form [type=submit]').click();
    assert.match(await page.locator('#setup-account-error').innerText(),/do not match/);
    await page.locator('#setup-account-form [name=confirmation]').fill('offline-fixture-password');
    await page.locator('#setup-account-form [type=submit]').click();
    await page.locator('#setup-account').waitFor({state:'hidden'});
    await page.getByText('OpenCode providers and logins',{exact:true}).waitFor();
    // Run/log consumer: no worker is launched. Mock only the protected
    // collection/detail responses after verifying the fixture's empty queue.
    await page.locator('nav a[href="#campaigns"]').click();
    await page.getByText('Queue is empty', {exact:false}).waitFor();
    const mockRun = {id:'job_mock',run_id:'job_mock',campaign_id:fixture.campaign_id,
      status:'running',state:'running',kind:'assessment',created_at:'2026-10-28T09:00:00Z'};
    const mockOld = {...mockRun,id:'job_old',run_id:'job_old',status:'succeeded',state:'succeeded'};
    const routeActive = url => url.pathname === '/api/v1/run/active';
    const routeLogs = url => url.pathname === '/api/v1/run/logs';
    const routeDetail = url => url.pathname === '/api/v1/run/job_mock';
    const routeLogDetail = url => url.pathname === '/api/v1/run/logs/job_mock';
    const fulfill = (route, body) => route.fulfill({
      status:200,contentType:'application/json',body:JSON.stringify(body)});
    const activeHandler = route => fulfill(route, {data:[mockRun],total:1,
      limit:50,offset:0,has_more:false,next_offset:null,paging_limit_reached:false,
      ordering:'created_at_desc,id_desc',page_consistency:'live_offset',
      active_states:['queued','running','cancelling']});
    const historyHandler = route => {
      const offset = Number(new URL(route.request().url()).searchParams.get('offset') || 0);
      const data = offset ? [mockOld] :
        [{...mockRun,log_status:'missing',log_bytes:0},
         ...Array.from({length:49},(_,i)=>({...mockOld,id:'job_history_'+i,
            run_id:'job_history_'+i,log_status:'missing',log_bytes:0}))];
      return fulfill(route, {data,total:51,limit:50,offset,
        has_more:offset === 0,next_offset:offset === 0 ? 50 : null,
        paging_limit_reached:false,ordering:'created_at_desc,id_desc',
        page_consistency:'live_offset',content_policy:'metadata_only'});
    };
    const detailHandler = route => fulfill(route, {...mockRun,log_status:'available',log_bytes:22});
    const logDetailHandler = route => {
      const raw = new URL(route.request().url()).searchParams.get('raw') === 'true';
      return fulfill(route,{run_id:'job_mock',campaign_id:fixture.campaign_id,
        status:'running',state:'running',log_status:'available',log_bytes:22,
        raw,content_policy:raw?'untrusted_admin_opt_in':'structured_lifecycle_only',
        data:[{type:raw?'untrusted_raw':'lifecycle',
          message:raw?'PRIVATE-MOCK-OUTPUT':'Run started'}]});
    };
    const grantHandler = route => fulfill(route, {grant:"mock-admin-grant-only",grant_id:"eg_mock",expires_in:45});
    const routeGrant = url => url.pathname === "/api/v1/evidence/grants";
    const mockRoutes = [[routeActive,activeHandler],[routeLogs,historyHandler],
      [routeDetail,detailHandler],[routeLogDetail,logDetailHandler],[routeGrant,grantHandler]];
    for (const [matcher,handler] of mockRoutes) await page.route(matcher,handler);
    await page.locator('nav a[href="#overview"]').click();
    await page.locator('nav a[href="#campaigns"]').click();
    await page.locator('[data-job="job_mock"]').waitFor();
    assert.match(await page.locator('#run-queue').innerText(),/Active run|running/);
    await page.locator('[data-run-page="50"]').click();
    await page.locator('[data-job="job_old"]').waitFor();
    await page.locator('[data-run-page="0"]').click();
    await page.locator('[data-job="job_mock"]').first().click();
    await page.locator('#job-log').waitFor();
    assert.match(await page.locator('#job-log').innerText(),/Run started/);
    assert.doesNotMatch(await page.locator('#job-log').innerText(),/PRIVATE-MOCK-OUTPUT/);
    await page.locator('[data-raw-job="job_mock"]').click();
    await page.waitForTimeout(300);
    assert.match(await page.locator('#job-log').innerText(), /PRIVATE-MOCK-OUTPUT/);
    await page.locator('#detail .close-dialog').click();
    for (const [matcher,handler] of mockRoutes) await page.unroute(matcher,handler);
    // High-cardinality live paging: each pager moves independently. Live
    // totals can shrink after a page has been selected; only that pager rewinds.
    const activeRecords = Array.from({length:122},(_,i)=>({
      id:'job_series_'+String(i).padStart(3,'0'),run_id:'job_series_'+String(i).padStart(3,'0'),
      campaign_id:fixture.campaign_id,status:i%2?'running':'queued',
      state:i%2?'running':'queued',created_at:'2026-10-28T09:00:00Z'}));
    const historyRecords = Array.from({length:121},(_,i)=>({
      ...activeRecords[i],log_status:'missing',log_bytes:0}));
    let activeTotal = 122, historyTotal = 121, malformedActive = false;
    const pageOf = (records,total,request) => {
      const offset = Number(new URL(request.url()).searchParams.get('offset') || 0);
      const data = records.slice(0,total).slice(offset,offset+50);
      const end = offset+data.length;
      const has_more = end < total && end <= 100000;
      return {data,total,limit:50,offset,has_more,
        next_offset:has_more?end:null,paging_limit_reached:end<total&&!has_more,
        ordering:'created_at_desc,id_desc',page_consistency:'live_offset'};
    };
    const manyActive = route => {
      if (malformedActive) return fulfill(route,{data:{},total:'invalid'});
      return fulfill(route,{...pageOf(activeRecords,activeTotal,route.request()),
        active_states:['queued','running','cancelling']});
    };
    const manyHistory = route => fulfill(route,{
      ...pageOf(historyRecords,historyTotal,route.request()),
      content_policy:'metadata_only'});
    await page.route(routeActive,manyActive);
    await page.route(routeLogs,manyHistory);
    await page.locator('nav a[href="#overview"]').click();
    await page.locator('nav a[href="#campaigns"]').click();
    await page.getByText('Active 1–50 of 122',{exact:true}).waitFor();
    await page.getByText('History 1–50 of 121',{exact:true}).waitFor();
    assert.equal(await page.locator('[data-job="job_series_000"]').count(),1);
    await page.locator('[data-active-run-page="50"]').click();
    await page.getByText('Active 51–100 of 122',{exact:true}).waitFor();
    await page.getByText('History 1–50 of 121',{exact:true}).waitFor();
    await page.locator('[data-run-page="50"]').click();
    await page.getByText('History 51–100 of 121',{exact:true}).waitFor();
    await page.getByText('Active 51–100 of 122',{exact:true}).waitFor();
    await page.locator('[data-active-run-page="100"]').click();
    await page.getByText('Active 101–122 of 122',{exact:true}).waitFor();
    activeTotal = 7; historyTotal = 8;
    await page.evaluate(() => loadRunQueue(viewControl.signal));
    await page.getByText('Active 1–7 of 7',{exact:true}).waitFor();
    await page.getByText('History 1–8 of 8',{exact:true}).waitFor();
    assert.deepEqual(await page.evaluate(()=>[runActiveOffset,runQueueOffset]),[0,0]);
    // Inconsistent metadata must not be rendered as trusted run links.
    malformedActive = true;
    await page.evaluate(() => loadRunQueue(viewControl.signal));
    await page.getByText('Run history unavailable: Run collection did not match the expected metadata contract',{exact:true}).waitFor();
    malformedActive = false;
    await page.evaluate(() => loadRunQueue(viewControl.signal));
    await page.getByText('Active 1–7 of 7',{exact:true}).waitFor();
    // Superseded page loads must not overwrite the current page.
    await page.evaluate(() => {
      runActiveOffset=50;loadRunQueue(viewControl.signal);
      runActiveOffset=0;loadRunQueue(viewControl.signal);
    });
    await page.getByText('Active 1–7 of 7',{exact:true}).waitFor();
    assert.equal(await page.locator('[data-active-run-page="50"]').isDisabled(),true);
    await page.unroute(routeActive,manyActive);
    await page.unroute(routeLogs,manyHistory);
    const failActive = route => route.fulfill({status:503,contentType:'application/json',
      body:JSON.stringify({error:'Fixture discovery unavailable'})});
    await page.route(routeActive,failActive);
    await page.locator('nav a[href="#overview"]').click();
    await page.locator('nav a[href="#campaigns"]').click();
    await page.getByText('Run history unavailable: Fixture discovery unavailable').waitFor();
    await page.unroute(routeActive,failActive);
    assert.deepEqual(await page.evaluate(() => {
      runActiveOffset=50;runQueueOffset=50;lock();
      return [runActiveOffset,runQueueOffset,runQueueRequest>0];
    }),[0,0,true]);
    await page.locator('#token').fill(fixture.token);
    await page.locator('#login-form button[type=submit]').click();
    await page.locator('#login').waitFor({state:'hidden'});
    await page.locator('nav a[href="#overview"]').click();
    assert.equal(await page.locator('#setup-account-form [name=password]').inputValue(),'');
    assert.equal(await page.locator('#token').inputValue(),'');
    await page.locator('nav a[href="#overview"]').click();
    await page.getByText('Your security workspace').waitFor();
    await page.screenshot({
      path: path.join(screenshots, "overview.png"),
      fullPage: true,
    });
    // Dashboard counts and every new drill-down use the same retained-record cohort.
    const posture = await page.evaluate(() => snapshot.posture);
    assert.equal(posture.totals.findings, 9);
    assert.equal(posture.totals.projects, 3);
    assert.equal(posture.totals.targets, 3);
    assert.equal(posture.totals.active, 9);
    assert.deepEqual(await page.locator('#posture-totals .number').allTextContents(), ['3','3','3','9']);
    const targetRow = page.locator('#posture-targets tbody tr').first();
    const targetUrl = await targetRow.locator('a').first().getAttribute('href');
    const targetId = new URLSearchParams(targetUrl.split('?')[1]).get('target_id');
    await targetRow.locator('a').first().focus();
    await page.keyboard.press('Enter');
    await page.locator('#finding-target_id-filter').waitFor();
    assert.equal(await page.locator('#finding-target_id-filter').inputValue(), targetId);
    for (const severity of ['critical','high','medium','low','info']) assert.equal(await page.locator('#severity-filter option[value='+severity+']').count(),1);
    assert.equal(await page.locator('#finding-triage-filter').inputValue(), 'active');
    assert.match(await page.locator('#finding-count').innerText(), /of 3 matching findings/);
    await page.reload();
    await page.locator('#token').fill(fixture.token);
    await page.locator('#login-form button[type=submit]').click();
    await page.locator('#finding-target_id-filter').waitFor();
    assert.equal(await page.locator('#finding-target_id-filter').inputValue(), targetId);
    await page.locator('nav a[href="#overview"]').click();
    await page.locator('#posture-mitre a').first().click();
    await page.locator('#finding-mitre_attack_id-filter').waitFor();
    assert.equal(await page.locator('#finding-mitre_attack_id-filter').inputValue(), 'T1190');
    assert.match(await page.locator('#finding-count').innerText(), /of 9 matching findings/);
    await page.locator('#finding-project_id-filter').selectOption(await page.evaluate(() => snapshot.projects[0].id));
    assert.match(await page.locator('#finding-count').innerText(), /of 3 matching findings/);
    await page.locator('#findings-clear').click();
    assert.equal(await page.locator('#finding-mitre_attack_id-filter').inputValue(), '');
    assert.equal(await page.locator('#finding-project_id-filter').inputValue(), '');
    assert.equal(await page.locator('#finding-triage-filter').inputValue(), '');
    await page.locator('nav a[href="#overview"]').click();
    const changedFinding = await page.evaluate(async () => {
      const f=snapshot.findings[0];
      await api(`/api/v1/campaigns/${f.campaign_id}/findings/${f.id}`,{method:'PATCH',body:JSON.stringify({status:'false_positive'})});
      await refresh();
      return {id:f.id,cid:f.campaign_id};
    });
    assert.match(await page.locator('#content').innerText(), /8 \/ 9 \(88\.9%\)/);
    await page.getByRole('link',{name:'false positive: 1',exact:true}).click();
    await page.locator('#finding-status-filter').waitFor();
    assert.equal(await page.locator('#finding-status-filter').inputValue(),'false_positive');
    assert.match(await page.locator('#finding-count').innerText(), /of 1 matching findings/);
    await page.evaluate(async f => {
      await api(`/api/v1/campaigns/${f.cid}/findings/${f.id}`,{method:'PATCH',body:JSON.stringify({status:'confirmed'})});
      await refresh();
    },changedFinding);
    await page.locator('nav a[href="#overview"]').click();
    await page.locator('#posture-targets tbody button[data-campaign]').first().click();
    await page.locator('#detail[open]').waitFor();
    await page.locator('#detail .close-dialog').click();
    const idleTargets = await page.evaluate(async () => {
      const ids=[];
      for (let i=0;i<8;i++) ids.push((await api('/api/v1/targets',{method:'POST',body:JSON.stringify({host:'idle-'+i+'.example.invalid'})})).data.id);
      await refresh();
      return ids;
    });
    assert.equal(await page.locator('#posture-targets tbody tr').count(),10);
    await page.getByRole('link',{name:'Show all targets',exact:true}).click();
    await page.getByRole('link',{name:'Show top 10',exact:true}).waitFor();
    assert.equal(await page.locator('#posture-targets tbody tr').count(),11);
    await page.getByRole('link',{name:'Show top 10',exact:true}).click();
    await page.getByRole('link',{name:'Show all targets',exact:true}).waitFor();
    assert.equal(await page.locator('#posture-targets tbody tr').count(),10);
    await page.evaluate(async ids => {
      for (const id of ids) await api('/api/v1/targets/'+id,{method:'DELETE'});
      await refresh();
    },idleTargets);
    await page.locator('#posture-remediation a').first().click();
    await page.getByText('Local remediation proposals',{exact:true}).waitFor();
    assert.match(await page.locator('#content').innerText(), /0 matching proposals/);
    await page.locator('nav a[href="#overview"]').click();
    await page.locator('nav a[href="#findings"]').click();
    await page.locator('#findings-clear').click();
    await page.locator('nav a[href="#overview"]').click();
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
    await page.screenshot({path:path.join(screenshots,'posture-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:path.join(screenshots,'posture-desktop.png'),fullPage:true});
    for (const route of [
      "campaigns",
      "findings",
      "surface",
      "schedules",
      "remediation",
      "integrations",
      "projects",
      "retests",
      "credentials",
      "webhooks",
      "settings",
    ]) {
      await page.locator(`nav a[href="#${route}"]`).click();
      await page.locator(`nav a[href="#${route}"].active`).waitFor();
      assert.equal(
        await page.locator("#error").isVisible(),
        false,
        `Error on ${route}`,
      );
      if (route === "surface") {
        await page.locator("#map-info h3").waitFor();
        const asset = page.locator("#surface-node option").nth(1);
        await page.locator("#surface-node").selectOption(await asset.getAttribute("value"));
        await page.locator("#surface-node").selectOption("");
        assert.match(await page.locator("#map-info").innerText(), /Select an asset/);
        await page.locator("#surface-node").selectOption(await asset.getAttribute("value"));
        await page.locator("#surface-close").click();
        await page.locator("#surface-node").evaluate(el => {
          if (document.activeElement !== el) throw new Error("Inspector did not return focus");
        });
        await page.locator("#surface-tour").click();
        await page.locator("#surface-tour-card").getByRole("status").waitFor();
        assert.match(await page.locator("#surface-tour-card").innerText(), /Step 1 of/);
        assert.equal(await page.locator("#surface-prev").isDisabled(), true);
        if ((await page.locator("#surface-next").innerText()) === "Next") {
          await page.locator("#surface-next").click();
          assert.match(await page.locator("#surface-tour-card").innerText(), /Step 2 of/);
          await page.locator("#surface-prev").click();
          assert.match(await page.locator("#surface-tour-card").innerText(), /Step 1 of/);
        }
        await page.locator("#surface-free").click();
        assert.equal(await page.locator("#surface-tour-card").isVisible(), false);
        assert.equal(await page.locator("#surface-tour").evaluate(el => document.activeElement === el), true);
        await page.locator("#surface-tour").click();
        await page.locator("#surface-node").selectOption(await asset.getAttribute("value"));
        assert.equal(await page.locator("#surface-tour-card").isVisible(), false);
        await page.locator("#surface-tour").click();
        await page.locator("#surface-close").click();
        assert.equal(await page.locator("#surface-tour-card").isVisible(), false);


        await page.locator("#surface-node").selectOption(await asset.getAttribute("value"));
        const linked = page.locator("#map-info [data-surface-finding]").first();
        if (await linked.count()) {
          await linked.click();
          await page.locator("#surface-finding-title").waitFor();
          assert.equal(await page.locator("#detail").isVisible(), false);
          assert.equal(await page.locator("#map-info [data-report-preview]").getAttribute("data-report-preview"), await page.locator("#campaign-select").inputValue());
          await page.screenshot({path:path.join(screenshots,"surface-finding.png"),fullPage:true});
          await page.locator("#surface-back").click();
          assert.equal(await page.locator("#map-info [data-surface-finding]").first().evaluate(el=>document.activeElement === el),true);
        }
        await page.screenshot({path:path.join(screenshots,"surface-inspector.png"),fullPage:true});
        await page.locator("#surface-tour").click();
        await page.screenshot({path:path.join(screenshots,"surface-tour.png"),fullPage:true});
        await page.locator("#surface-free").click();
        await page.locator("#recorded-paths h3").waitFor();
        await page.locator("#path-reveal").click();
        await page.locator("#path-editor summary").click();
        await page.locator('#path-form [name="title"]').fill('Reviewed <script>path</script>');
        const firstEdge = await page.locator('[data-path-edge="0"] option').nth(1).getAttribute('value');
        await page.locator('[data-path-edge="0"]').selectOption(firstEdge);
        await page.locator('[data-path-finding="0"]').selectOption(await page.locator('[data-path-finding="0"] option').nth(1).getAttribute('value'));
        await page.locator('[data-path-rationale="0"]').fill('Fixture entry response supports the recorded service connection.');
        await page.locator('#path-add-step').click();
        await page.locator('[data-path-edge="1"]').selectOption(await page.locator('[data-path-edge="1"] option').nth(1).getAttribute('value'));
        await page.locator('[data-path-finding="1"]').selectOption(await page.locator('[data-path-finding="1"] option').nth(1).getAttribute('value'));
        await page.locator('[data-path-rationale="1"]').fill('Fixture service evidence supports the recorded database connection.');
        await page.locator('#path-form [name="reviewed"]').check();
        await page.locator('#path-form [type="submit"]').click();
        await page.locator('#path-status').filter({hasText:'Reviewed path saved'}).waitFor();
        const recordedPathId = await page.locator('#path-select').inputValue();
        assert.ok(recordedPathId.startsWith('path_'));
        await page.locator('#path-play').click();
        await page.locator('#surface-tour-card').filter({hasText:'Recorded path · Step 1 of 2'}).waitFor();
        assert.equal(await page.locator('#path-back').isDisabled(),true);
        await page.locator('#surface-tour-card summary').click();
        assert.match(await page.locator('#surface-tour-card').innerText(),/Fixture entry response/);
        assert.equal(await page.locator('#surface-tour-card [data-finding]').getAttribute('data-cid'),await page.locator('#campaign-select').inputValue());
        assert.equal(await page.evaluate(()=>window.injected),undefined);
        await page.screenshot({path:path.join(screenshots,'recorded-path.png'),fullPage:true});
        await page.locator('#path-next').click();
        await page.locator('#surface-tour-card').filter({hasText:'Step 2 of 2'}).waitFor();
        await page.locator('#path-back').click();
        await page.locator('#surface-tour-card').filter({hasText:'Step 1 of 2'}).waitFor();
        await page.locator('#path-free').click();
        assert.equal(await page.locator('#path-play').evaluate(el=>document.activeElement===el),true);
        await page.locator('#path-play').click();
        await page.locator('#path-next').waitFor();
        await page.locator('#path-next').click();
        await page.locator('#path-next').filter({hasText:'Finish'}).waitFor();
        await page.locator('#path-next').click();
        assert.equal(await page.locator('#surface-tour-card').isVisible(),false);
        await page.locator('#path-play').click();
        await page.locator('#path-next').waitFor();
        await page.locator('#surface-node').selectOption(await asset.getAttribute('value'));
        assert.equal(await page.locator('#surface-tour-card').isVisible(),false);
        await page.locator('nav a[href="#findings"]').click();
        await page.locator('nav a[href="#surface"]').click();
        await page.locator('#path-select').selectOption(recordedPathId);
        await page.locator('#path-reveal').click();
        await page.waitForFunction(() => document.querySelector('#path-play')?.disabled === false,
          undefined, {timeout:6000});
        assert.equal(await page.locator('#path-play').isDisabled(),false);
        // Exercise playback's own freshness check independently of SSE rerender.
        await page.evaluate(() => streamControl.abort());
        await page.locator('#path-play').click();
        await page.locator('#path-next').waitFor();
        const pathCampaign = await page.locator('#campaign-select').inputValue();
        const staleFinding = await page.evaluate(async cid => (await grantedRequest('graph',cid)).data.paths[0].steps[1].finding_id, pathCampaign);
        await page.evaluate(async ({cid, finding}) => api(`/api/v1/campaigns/${cid}/findings/${finding}`, {method:'PATCH',body:JSON.stringify({status:'false_positive'})}), {cid:pathCampaign,finding:staleFinding});
        await page.locator('#path-next').click();
        await page.locator('#path-status').filter({hasText:'Path unavailable'}).waitFor();
        assert.equal(await page.locator('#surface-tour-card').isVisible(),false);
        assert.equal(await page.locator('#path-play').isDisabled(),true);
        await page.evaluate(async ({cid, finding}) => api(`/api/v1/campaigns/${cid}/findings/${finding}`, {method:'PATCH',body:JSON.stringify({status:'confirmed'})}), {cid:pathCampaign,finding:staleFinding});
        await page.locator('nav a[href="#findings"]').click();
        await page.locator('nav a[href="#surface"]').click();
        await page.locator('#path-select').selectOption(recordedPathId);
        await page.locator('#path-reveal').click();
        await page.emulateMedia({reducedMotion:'reduce'});
        await page.setViewportSize({width:390,height:844});
        await page.locator('#path-play').click();
        await page.locator('#path-free').waitFor();
        await page.locator('#surface-tour-card').scrollIntoViewIfNeeded();
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
        await page.screenshot({path:path.join(screenshots,'recorded-path-mobile.png'),fullPage:true});
        await page.locator('#path-free').click();
        await page.emulateMedia({reducedMotion:'no-preference'});
        await page.setViewportSize({width:1440,height:1000});
        await page.locator('#surface-close').click();
        await page.locator('#path-delete').click();
        await page.locator('#path-status').filter({hasText:'Recorded path deleted'}).waitFor();
        // Reconnect emits an initial revision and replaces the graph. Wait for
        // that real refresh before testing another inspector selection.
        await page.evaluate(() => { window.testPriorView = viewControl; connect(); });
        await page.waitForFunction(() => viewControl !== window.testPriorView && document.querySelector('#surface-node'));
        await page.evaluate(() => { delete window.testPriorView; });
        await page.setViewportSize({width:390,height:844});
        await page.locator("#surface-node").selectOption(await asset.getAttribute("value"));
        assert.equal(await page.locator("#surface-close").isVisible(),true);
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
        await page.screenshot({path:path.join(screenshots,"surface-mobile.png"),fullPage:true});
        await page.locator("#surface-close").click();
        await page.setViewportSize({width:1440,height:1000});

        await page
          .locator("#surface-canvas")
          .dispatchEvent("wheel", { deltaY: -100 });
        await page.screenshot({
          path: path.join(screenshots, "surface.png"),
          fullPage: true,
        });
      }
      if (route === "integrations") {
        await page
          .getByText("Connect your workflow", { exact: true })
          .waitFor();
        await page
          .locator('a[href="https://github.com/ASCIT31/darkmoon-n8n"]')
          .waitFor();
        assert.ok(
          (await page.locator("#content").textContent()).includes(
            "POST /api/v1/auth/login",
          ),
        );
      }
    }
    await page.locator('nav a[href="#projects"]').click();
    await page.locator("[data-project-analytics]").first().click();
    await page.locator("#project-chart").waitFor();
    await page.locator("#detail .close-dialog").click();
    await page.locator('nav a[href="#credentials"]').click();
    await page.locator("[data-workspace=credential]").click();
    await page
      .locator("#workspace-form input[name=name]")
      .fill("Fixture vault key");
    await page
      .locator("#workspace-form select[name=provider]")
      .selectOption("generic");
    await page
      .locator("#workspace-form input[name=secret]")
      .fill("this-private-fixture-key-must-be-hidden");
    await page.locator("#workspace-form button[type=submit]").click();
    await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
    await page
      .locator(".list-item")
      .filter({ hasText: "Fixture vault key" })
      .waitFor();
    assert.equal(
      (await page.locator("body").innerText()).includes(
        "this-private-fixture-key-must-be-hidden",
      ),
      false,
    );
    await page.locator("[data-delete-credential]").click();
    await page.getByText("No saved credentials", { exact: true }).waitFor();
    await page.locator('nav a[href="#settings"]').click();
    await page.locator("[data-workspace=account]").click();
    await page
      .locator("#workspace-form input[name=username]")
      .fill("fixture-reader");
    await page
      .locator("#workspace-form input[name=password]")
      .fill("correct-fixture-reader-password");
    await page.locator("#workspace-form button[type=submit]").click();
    await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
    await page.getByText("fixture-reader", { exact: true }).first().waitFor();
    await page.locator("[data-doctor]").click();
    await page.locator("#detail[open]").waitFor();
    await page.locator("#detail .close-dialog").click();
    // The saved OpenCode OAuth login and actual catalog models populate the UI.
    await page.locator('nav a[href="#settings"]').click();
    await page
      .getByText("OpenCode providers and logins", { exact: true })
      .waitFor();
    assert.equal(
      (await page.locator("body").innerText()).includes(
        "fixture-native-refresh-not-for-ui",
      ),
      false,
    );
    await page.locator("[data-workspace=provider]").click();
    assert.equal(
      await page.locator("#workspace-form select[name=provider]").inputValue(),
      "openai",
    );
    assert.equal(
      await page.locator("#workspace-form select[name=model] option").count(),
      3,
    );
    await page
      .locator("#workspace-form select[name=model]")
      .selectOption("fixture-second");
    await page.locator("#workspace-form button[type=submit]").click();
    await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
    await page.locator("[data-apply-provider]").click();
    await page.getByText("OpenCode updated live.", { exact: true }).waitFor();
    await page.locator("#detail .close-dialog").click();
    // OAuth starts/finishes through the native API, never a fake UI session.
    await page.locator("[data-workspace=opencode_connect]").click();
    await page
      .locator("#workspace-form select[name=auth_method]")
      .selectOption("1");
    await page.locator("#workspace-form button[type=submit]").click();
    await page
      .getByRole("heading", { name: "Finish OpenCode sign-in" })
      .waitFor();
    await page.locator("#workspace-form button[type=submit]").click();
    await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
    await page.locator("[data-sync-opencode]").click();
    await page.locator("[data-updates]").click();
    await page.getByText("Image update status", { exact: true }).waitFor();
    await page.locator("#detail .close-dialog").click();
    await page.screenshot({
      path: path.join(screenshots, "settings.png"),
      fullPage: true,
    });
    // Dynamic campaign/finding selectors, including a real queued retest.
    await page.locator('nav a[href="#retests"]').click();
    await page.locator("[data-workspace=retest]").click();
    await page
      .locator("#workspace-form select[name=campaign_id]")
      .selectOption(fixture.campaign_id);
    assert.equal(
      await page
        .locator("#workspace-form select[name=finding_ids] option")
        .count(),
      4,
    );
    await page
      .locator("#workspace-form select[name=finding_ids]")
      .selectOption(fixture.finding_id);
    await page.locator("#workspace-form button[type=submit]").click();
    await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
    await page.locator("[data-retest-detail]").first().click();
    await page.getByText("Retest verdicts", { exact: true }).waitFor();
    await page.locator("#detail .close-dialog").click();
    // Register/list deliveries/delete; fixture delivery transport cannot egress.
    await page.locator('nav a[href="#webhooks"]').click();
    await page.locator("[data-workspace=webhook]").click();
    await page
      .locator("#workspace-form input[name=url]")
      .fill("https://receiver.example.invalid/test");
    await page
      .locator("#workspace-form select[name=events]")
      .selectOption("campaign.completed");
    await page
      .locator("#workspace-form input[name=secret]")
      .fill("offline-signing-secret-at-least-24-characters");
    await page.locator("#workspace-form button[type=submit]").click();
    await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
    await page.locator("[data-webhook-deliveries]").click();
    await page.getByText("Delivery history", { exact: true }).waitFor();
    await page.locator("#detail .close-dialog").click();
    await page.locator("[data-delete-webhook]").click();
    await page.getByText("No subscriptions", { exact: true }).waitFor();
    // API-key logins are saved once, shared with OpenCode, and disconnectable.
    await page.locator('nav a[href="#settings"]').click();
    await page.locator("[data-workspace=opencode_connect]").click();
    await page
      .locator("#workspace-form select[name=provider]")
      .selectOption("openrouter");
    await page
      .locator("#workspace-form input[name=secret]")
      .fill("offline-browser-api-key-no-real-provider");
    await page.locator("#workspace-form button[type=submit]").click();
    await page
      .getByText("Provider connected in OpenCode.", { exact: true })
      .waitFor();
    await page.locator("#detail .close-dialog").click();
    await page.locator("[data-disconnect-opencode=openrouter]").click();
    await page.getByText("Provider disconnected.", { exact: true }).waitFor();
    await page.locator("#detail .close-dialog").click();
    assert.equal(
      (await page.locator("body").innerText()).includes(
        "offline-browser-api-key-no-real-provider",
      ),
      false,
    );
    await page.locator('nav a[href="#settings"]').click();
    await page.locator("[data-bridge-health]").click();
    await page.getByText("OpenCode bridge health", { exact: true }).waitFor();
    assert.match(await page.locator("#detail-body").innerText(), /healthy/);
    await page.locator("#detail .close-dialog").click();
    await page.locator("[data-workspace=provider]").click();
    await page
      .locator("#workspace-form input[name=name]")
      .fill("Discovered local profile");
    await page
      .locator("#workspace-form select[name=provider]")
      .selectOption("__custom__");
    await page
      .locator("#workspace-form input[name=custom_provider]")
      .fill("validation-local");
    await page
      .locator("#workspace-form select[name=mode]")
      .selectOption("local");
    await page
      .locator("#workspace-form input[name=base_url]")
      .fill(fixture.model_endpoint);
    await page.locator("[data-discover-models]").click();
    await page
      .locator("#model-discovery-status")
      .filter({ hasText: "2 models found" })
      .waitFor();
    assert.equal(
      await page.locator("#workspace-form select[name=model]").inputValue(),
      "available-one",
    );
    await page
      .locator("#workspace-form input[name=base_url]")
      .fill(fixture.model_endpoint + "/missing");
    await page.locator("[data-discover-models]").click();
    await page
      .locator("#model-discovery-status")
      .filter({ hasText: "HTTP 404" })
      .waitFor();
    assert.equal(
      await page.locator("#workspace-form select[name=model] option").count(),
      3,
    );
    await page
      .locator("#workspace-form input[name=base_url]")
      .fill(fixture.model_endpoint);
    await page.screenshot({
      path: path.join(screenshots, "provider-discovery.png"),
      fullPage: true,
    });
    await page.locator("#workspace-form button[type=submit]").click();
    await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
    let profileRow = page
      .locator(".provider-profile")
      .filter({ hasText: "Discovered local profile" });
    await profileRow.locator("[data-check-provider]").click();
    await page.getByText("Provider check", { exact: true }).waitFor();
    assert.match(
      await page.locator("#detail-body").innerText(),
      /model_listed/,
    );
    assert.match(
      await page.locator("#detail-body").innerText(),
      /"inference_performed": false/,
    );
    await page.locator("#detail .close-dialog").click();
    await profileRow.locator("[data-edit-provider]").click();
    assert.equal(
      await page.locator("#workspace-form input[name=name]").inputValue(),
      "Discovered local profile",
    );
    assert.equal(
      await page.locator("#workspace-form input[name=base_url]").inputValue(),
      fixture.model_endpoint,
    );
    await page
      .locator("#workspace-form input[name=name]")
      .fill("Edited local profile");
    await page
      .locator("#workspace-form select[name=model]")
      .selectOption("available-two");
    await page.locator("#workspace-form button[type=submit]").click();
    await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
    profileRow = page
      .locator(".provider-profile")
      .filter({ hasText: "Edited local profile" });
    await profileRow.locator("[data-copy-provider]").click();
    await page
      .locator("#workspace-form input[name=name]")
      .fill("Duplicate local profile");
    await page.locator("#workspace-form button[type=submit]").click();
    await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
    await page
      .locator(".provider-profile")
      .filter({ hasText: "Duplicate local profile" })
      .waitFor();
    assert.equal(await page.locator(".provider-profile").count(), 3);
    for (const name of ["Duplicate local profile", "Edited local profile"]) {
      await page
        .locator(".provider-profile")
        .filter({ hasText: name })
        .locator("[data-delete-provider]")
        .click();
      await page
        .getByRole("heading", { name: "Delete saved profile" })
        .waitFor();
      await page.locator("#workspace-form button[type=submit]").click();
      await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
      await page
        .locator(".provider-profile")
        .filter({ hasText: name })
        .waitFor({ state: "hidden" });
    }
    await page.locator("[data-workspace=provider]").click();
    await page
      .locator("#workspace-form select[name=mode]")
      .selectOption("local");
    await page
      .locator("#workspace-form input[name=base_url]")
      .fill(fixture.model_endpoint.replace("/v1", "/slow"));
    const discoveryFinished = page.waitForResponse((r) =>
      r.url().endsWith("/api/v1/system/provider-models"),
    );
    await page.locator("[data-discover-models]").click();
    await page.locator("#workspace-dialog .close-dialog").click();
    await (await discoveryFinished).finished();
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
    assert.equal(await page.locator("#workspace-dialog").isVisible(), false);
    await page.locator('nav a[href="#findings"]').click();
    await page.locator("#severity-filter").selectOption("high");
    assert.equal(await page.locator("tbody tr").count(), 3);
    assert.equal(await page.locator('#severity-filter').evaluate(el=>document.activeElement===el),true);
    await page.locator('#finding-status-filter').selectOption('confirmed');
    await page.locator('#finding-category-filter').selectOption('sqli');
    const filteredCampaign = await page.locator('#finding-campaign_id-filter option').nth(1).getAttribute('value');
    await page.locator('#finding-campaign_id-filter').selectOption(filteredCampaign);
    const filteredTarget = await page.evaluate(cid=>snapshot.campaigns.find(c=>c.id===cid).target_id,filteredCampaign);
    await page.locator('#finding-target_id-filter').selectOption(filteredTarget);
    await page.locator('#finding-sort').selectOption('cvss_desc');
    assert.equal(await page.locator('tbody tr').count(),1);
    const findingViewURL = page.url();
    assert.ok(findingViewURL.includes('campaign_id='));
    await page.locator('nav a[href="#overview"]').click();
    await page.locator('nav a[href="#findings"]').click();
    assert.equal(page.url(),findingViewURL);
    assert.equal(await page.locator('#finding-target_id-filter').inputValue(),filteredTarget);
    await page.screenshot({path:path.join(screenshots,'finding-filters.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
    await page.screenshot({path:path.join(screenshots,'finding-filters-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    await page.locator('#findings-clear').click();
    await page.locator('#finding-size').selectOption('5');
    assert.equal(await page.locator('tbody tr').count(),5);
    const firstPageIDs = await page.locator('tbody tr').evaluateAll(rows=>rows.map(r=>r.dataset.finding));
    await page.getByRole('button',{name:'Next page',exact:true}).click();
    assert.equal(await page.locator('tbody tr').count(),4);
    assert.equal(await page.locator('#finding-count').evaluate(el=>document.activeElement===el),true);
    const secondPageIDs = await page.locator('tbody tr').evaluateAll(rows=>rows.map(r=>r.dataset.finding));
    assert.equal(secondPageIDs.some(id=>firstPageIDs.includes(id)),false);
    await page.getByRole('button',{name:'Previous page',exact:true}).click();
    await page.goBack();
    await page.waitForFunction(()=>location.hash.includes('page=2'));
    assert.equal(await page.locator('tbody tr').count(),4);
    await page.goBack();
    await page.waitForFunction(()=>!location.hash.includes('page=2'));
    assert.equal(await page.locator('tbody tr').count(),5);
    await page.locator('#finding-search').fill('no such fixture result');
    assert.equal(await page.locator('tbody tr').count(),0);
    assert.match(await page.locator('#finding-count').innerText(),/0–0 of 0 matching/);
    await page.locator('#findings-clear').click();
    await page.locator('#severity-filter').selectOption('high');
    await page.locator("#finding-search").fill(fixture.finding_id);
    const reloadedFindingURL = page.url();
    await page.reload();
    await page.locator('#token').fill(fixture.token);
    await page.locator('#login-form button[type="submit"]').click();
    await page.locator('#finding-search').waitFor();
    assert.equal(page.url(),reloadedFindingURL);
    assert.equal(await page.locator('#finding-search').inputValue(),fixture.finding_id);
    assert.equal(await page.locator('#severity-filter').inputValue(),'high');
    await page.locator(`button[data-finding="${fixture.finding_id}"]`).focus();
    await page.keyboard.press('Enter');
    await page.locator("#detail[open]").waitFor();
    assert.equal(
      await page.evaluate(() => window.injected),
      undefined,
      "Finding content must be escaped",
    );
    assert.equal(await page.locator('[data-evidence-field="raw_response"]').count(),0,
      'default finding detail must not contain evidence');
    await page.locator('[data-reveal-finding]').click();
    const responseEvidence = await page
      .locator('[data-revealed-content] [data-evidence-field="raw_response"]')
      .textContent();
    assert.ok(
      responseEvidence.includes("HTTP/1.1 200 OK\nContent-Type: text/html"),
    );
    assert.ok(
      responseEvidence.includes("<script>window.injected=true</script>"),
    );
    assert.ok(!responseEvidence.includes("\x1b"));
    assert.equal(await page.locator("#detail-body script").count(), 0);
    await page.locator("#detail .close-dialog").click();
    assert.equal(await page.locator('[data-revealed-content]').count(), 0,
      'revealed content must be cleared on close');
    await page.locator(`button[data-finding="${fixture.finding_id}"]`).first().click();
    await page.locator("#detail[open]").waitFor();
    assert.equal(await page.locator('[data-evidence-field="raw_response"]').count(), 0);
    await page.locator('[data-reveal-finding]').click();
    await page.locator('[data-revealed-content]').waitFor();
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('[data-revealed-content]').count(), 0,
      'Escape must clear revealed content before the deferred close event');
    await page.locator(`button[data-finding="${fixture.finding_id}"]`).first().click();
    await page.locator("#detail[open]").waitFor();
    assert.equal(await page.locator('[data-evidence-field="raw_response"]').count(), 0);
    // Before remediation exists, the exact finding lookup must return a valid empty result.
    await page.getByText("Linked remediation records", {exact:true}).waitFor();
    assert.match(await page.locator("#detail-body").innerText(), /No linked remediation records/);
    await page.locator("[data-prepare-fix]").click();
    await page.locator("#remediation-dialog[open]").waitFor();
    // Repository paths are no longer sent in default workspace choices.
    // A local administrator supplies the known owned fixture path explicitly.
    assert.equal(await page.locator("#remediation-form input[name=repo]").inputValue(), "");
    await page.locator("#remediation-form input[name=repo]").fill(fixture.source_repo);
    assert.equal(
      await page.locator("#remediation-form select[name=source_files] option").count(), 0,
      "Unscoped source-file enumeration must remain unavailable",
    );
    await page
      .locator("#remediation-form textarea[name=edits]")
      .fill(
        JSON.stringify([{ path: "app.py", old: "vulnerable", new: "fixed" }]),
      );
    await page.locator("#remediation-form button[type=submit]").click();
    await page.locator("#remediation-dialog").waitFor({ state: "hidden" });
    await page
      .locator("#content .badge")
      .filter({ hasText: "proposed" })
      .waitFor({ timeout: 15000 });
    assert.match(
      await fs.readFile(path.join(fixture.source_repo, "app.py"), "utf8"),
      /vulnerable/,
    );
    await page.locator("[data-remediation]").click();
    const patchDownload = page.waitForEvent("download");
    await page.locator("[data-patch]").click();
    const patch = await patchDownload;
    assert.match(
      await fs.readFile(await patch.path(), "utf8"),
      /\+message = 'fixed'/,
    );
    await page.locator("#detail .close-dialog").click();
    // A persisted proposal must be linked to its exact finding/campaign pair.
    await page.locator('nav a[href="#findings"]').click();
    await page.locator("#findings-clear").click();
    await page.locator(`button[data-finding="${fixture.finding_id}"]`).first().click();
    const linkedButton = page.locator(`#detail-body [data-proposal-finding="${fixture.finding_id}"]`);
    await linkedButton.waitFor();
    assert.equal(await linkedButton.count(), 1);
    assert.match(await page.locator("#detail-body").innerText(), /Local proposal/);
    await page.locator("#detail .close-dialog").click();
    await page.route('**/api/v1/pull-requests/finding/**', route => route.fulfill({
      status:503,contentType:'application/json',body:JSON.stringify({error:'unavailable'})}));
    await page.locator(`button[data-finding="${fixture.finding_id}"]`).first().click();
    await page.getByText("Linked remediation records unavailable.", {exact:true}).waitFor();
    await page.locator("#detail .close-dialog").click();
    await page.unroute('**/api/v1/pull-requests/finding/**');
    await page.locator('nav a[href="#overview"]').click();
    assert.match(await page.locator('#posture-remediation').innerText(), /0 \/ 1 \(0\.0%\)/);
    await page.locator('#posture-remediation').getByRole('link',{name:'proposed: 1',exact:true}).click();
    await page.getByText('Local remediation proposals',{exact:true}).waitFor();
    assert.match(await page.locator('#content').innerText(), /1 matching proposals/);
    assert.equal(await page.locator('#content [data-remediation]').count(),1);
    await page.locator('nav a[href="#campaigns"]').click();
    await page.locator(`[data-campaign="${fixture.campaign_id}"]`).click();
    await page.locator("[data-report-preview]").click();
    await page.locator(".report-preview").waitFor();
    const section = page.locator('.report-sections button').last();
    const sectionId = await section.getAttribute('aria-controls');
    await section.click();
    assert.equal(await page.locator('#'+sectionId).evaluate(el=>document.activeElement===el),true);
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    await page.screenshot({path:path.join(screenshots,'report-navigation.png'),fullPage:true});
    await page.locator("#detail .close-dialog").click();
    await page.locator(`[data-campaign="${fixture.campaign_id}"]`).click();
    await page.locator("[data-protected-pdf]").click();
    await page
      .locator("#workspace-form input[name=password]")
      .fill("private-browser-report-password");
    const protectedDownload = page.waitForEvent("download");
    await page.locator("#workspace-form button[type=submit]").click();
    const protectedReport = await protectedDownload;
    const protectedBytes = await fs.readFile(await protectedReport.path());
    assert.ok(protectedBytes.includes(Buffer.from("/Encrypt")));
    await page.locator("#workspace-dialog").waitFor({ state: "hidden" });
    await page.locator(`[data-campaign="${fixture.campaign_id}"]`).click();
    for (const format of ["md", "json"]) {
      const event = page.waitForEvent("download");
      await page.locator(`[data-export=${format}]`).click();
      assert.ok((await fs.readFile(await (await event).path())).length > 100);
    }
    const downloadEvent = page.waitForEvent("download");
    await page.locator("[data-export=pdf]").click();
    const download = await downloadEvent;
    const pdf = await fs.readFile(await download.path());
    assert.equal(pdf.subarray(0, 4).toString(), "%PDF");
    await page.locator("#detail .close-dialog").click();
    await page.locator('nav a[href="#schedules"]').click();
    await page.locator("#new-schedule").click();
    await page.locator("#launch-dialog[open]").waitFor();
    assert.ok(
      (await page
        .locator("#launch-form select[name=known_target] option")
        .count()) >= 4,
    );
    // An ungranted workspace options response does not reveal saved hostnames.
    assert.equal(await page.locator("#launch-form input[name=target]").inputValue(), "");
    await page.locator("#launch-form input[name=target]").fill("test.example");
    await page
      .locator("#launch-form select[name=preset]")
      .selectOption("bounty");
    assert.equal(
      await page.locator("#launch-form select[name=noise]").inputValue(),
      "low",
    );
    assert.equal(
      await page.locator("#launch-form select[name=format]").inputValue(),
      "h1",
    );
    assert.ok(
      await page
        .locator("#launch-form select[name=exclude]")
        .evaluate((e) => [...e.selectedOptions].some((o) => o.value === "H1")),
    );
    assert.equal(
      await page
        .locator("#launch-form select[name=severity]")
        .getAttribute("multiple"),
      null,
    );
    await page.locator("#launch-form input[name=focus_extra]").fill("CWE-89");
    await page
      .locator("#launch-form select[name=safe_harbor_applies]")
      .selectOption("yes");
    assert.match(
      await page.locator("#launch-preview").textContent(),
      /SAFE_HARBOR=yes/,
    );
    assert.match(await page.locator("#launch-preview").textContent(), /CWE-89/);
    await page
      .locator("#launch-form select[name=focus]")
      .selectOption(["sqli", "xss"]);
    await page
      .locator("#launch-form select[name=severity]")
      .selectOption("high");
    assert.ok(
      (await page
        .locator("#launch-form select[name=assessment_token_id] option")
        .count()) >= 2,
    );
    await page.screenshot({
      path: path.join(screenshots, "launch.png"),
      fullPage: true,
    });
    await page.locator("#launch-form input[name=name]").fill("Future fixture");
    await page.locator("#launch-form input[name=target]").fill("test.example");
    await page.locator('#launch-form [name=schedule_name]').fill('Month-end review');
    await page.locator('#launch-form [name=schedule_kind]').selectOption('monthly');
    await page.locator('#launch-form [name=schedule_every]').fill('2');
    await page.locator('#launch-form [name=schedule_timezone]').fill('America/Edmonton');
    await page
      .locator("#launch-form input[name=first_run]")
      .fill("2099-01-31T12:00");
    await page.locator('#schedule-preview-button').click();
    await page.locator('#schedule-preview li').first().waitFor();
    assert.equal(await page.locator('#schedule-preview li').count(),5);
    assert.match(await page.locator('#schedule-preview').innerText(),/America\/Edmonton/);
    const previewTimes=(await page.locator('#schedule-preview li').first().innerText()).split('\n');
    assert.match(previewTimes[0],/2099-01-31T12:00:00[+-]\d{2}:\d{2}/);
    assert.equal(Date.parse(previewTimes[0]),Date.parse(previewTimes[1].replace('UTC ','')));
    await page.screenshot({path:path.join(screenshots,'calendar-preview.png'),fullPage:true});
    await page.locator("#launch-submit").click();
    await page.locator("#launch-dialog").waitFor({ state: "hidden" });
    await page.locator('[data-edit-schedule]').waitFor();
    assert.match(await page.locator('#content').innerText(),/Every 2 month/);
    const scheduleId=await page.locator('[data-edit-schedule]').getAttribute('data-edit-schedule');
    await page.locator('[data-edit-schedule]').click();
    await page.locator('#launch-dialog[open]').waitFor();
    await page.evaluate(async id=>api('/api/v1/schedules/'+id,{method:'PATCH',body:JSON.stringify({version:1,display_name:'Concurrent schedule edit'})}),scheduleId);
    await page.locator('#launch-submit').click();
    await page.locator('#launch-error').filter({hasText:'Schedule changed'}).waitFor();
    assert.equal(await page.locator('#launch-dialog').isVisible(),true);
    await page.locator('#launch-dialog .close-dialog').click();
    await page.evaluate(()=>refresh());
    await page.locator('[data-edit-schedule]').click();
    assert.equal(await page.locator('#launch-form [name=name]').inputValue(),'Future fixture');
    assert.equal(await page.locator('#launch-form [name=target]').inputValue(),'test.example');
    await page.locator('#launch-form [name=schedule_kind]').selectOption('once');
    await page.locator('#launch-form [name=first_run]').fill('2026-03-08T02:30');
    await page.locator('#schedule-preview-button').click();
    await page.locator('#schedule-preview').filter({hasText:'does not exist'}).waitFor();
    await page.locator('#launch-form [name=first_run]').fill('2099-01-31T12:00');
    await page.locator('#launch-form [name=schedule_name]').fill('One-time fixture');
    await page.locator('#schedule-preview-button').click();
    await page.locator('#schedule-preview li').waitFor();
    assert.equal(await page.locator('#schedule-preview li').count(),1);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
    await page.locator('#schedule-fields').evaluate(el=>el.scrollIntoView({block:'start'}));
    await page.screenshot({path:path.join(screenshots,'calendar-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    await page.locator('#launch-submit').click();
    await page.locator('#launch-dialog').waitFor({state:'hidden'});
    await page.locator('tbody tr').filter({hasText:'One-time fixture'}).waitFor();
    await page.locator('[data-duplicate-schedule]').click();
    const duplicate=page.locator('tbody tr').filter({hasText:'(copy)'});
    await duplicate.waitFor();
    assert.match(await duplicate.innerText(),/Disabled/);
    await duplicate.locator('[data-schedule-history]').click();
    await page.getByText('No run history yet',{exact:true}).waitFor();
    await page.locator('#detail .close-dialog').click();
    await duplicate.locator('[data-delete-schedule]').click();
    await page.waitForFunction(()=>document.querySelectorAll('[data-delete-schedule]').length===1);
    await page.locator("[data-toggle-schedule]").click();
    await page.getByRole("button", { name: "Resume", exact: true }).waitFor();
    await page.locator("[data-delete-schedule]").click();
    await page.getByText("No scheduled assessments", { exact: true }).waitFor();
    await page.locator("#new-campaign").click();
    await page.locator("#launch-dialog[open]").waitFor();
    await page
      .locator("#launch-form input[name=name]")
      .fill("Fake launcher assessment");
    await page
      .locator("#launch-form input[name=target]")
      .fill("fixture.example");
    const [launchResponse] = await Promise.all([
      page.waitForResponse(response =>
        new URL(response.url()).pathname === '/api/v1/campaigns' &&
        response.request().method() === 'POST'),
      page.locator("#launch-submit").click(),
    ]);
    assert.equal(launchResponse.status(), 202);
    const launchedRun = await launchResponse.json();
    assert.match(launchedRun.run_id, /^job_[a-zA-Z0-9_-]+$/);
    await page.locator("#launch-dialog").waitFor({ state: "hidden" });
    await page
      .locator("#run-queue .list-item")
      .filter({ has: page.locator(`[data-job="${launchedRun.run_id}"]`) })
      .locator(".badge")
      .filter({ hasText: "succeeded" })
      .waitFor({ timeout: 10000 });
    assert.ok(!(await page.locator('#run-queue').innerText()).includes('Fake launcher assessment'),
      'run discovery must use the returned identity without restoring withheld campaign names');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('nav a[href="#overview"]').click();
    await page.getByText("Your security workspace").waitFor();
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
    await page.screenshot({
      path: path.join(screenshots, "mobile.png"),
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth,
      ),
      false,
      "Mobile page overflows horizontally",
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator("#logout").click();
    await page.locator("#login[open]").waitFor();
    await page.locator("#login-username").fill("fixture-reader");
    await page.locator("#token").fill("correct-fixture-reader-password");
    await page.locator("#login-form button[type=submit]").click();
    await page.locator("#login").waitFor({ state: "hidden" });
    assert.equal(await page.locator("#new-campaign").isVisible(), false);
    assert.equal(
      await page.locator('nav a[href="#credentials"]').isVisible(),
      false,
    );
    await page.locator('nav a[href="#settings"]').click();
    await page.getByText("My account", { exact: true }).waitFor();
    await page.locator("[data-workspace=password]").click();
    await page
      .locator("#workspace-form input[name=old_password]")
      .fill("correct-fixture-reader-password");
    await page
      .locator("#workspace-form input[name=new_password]")
      .fill("rotated-fixture-reader-password");
    await page.locator("#workspace-form button[type=submit]").click();
    await page.locator("#login[open]").waitFor();
    await page.locator("#token").fill("rotated-fixture-reader-password");
    await page.locator("#login-form button[type=submit]").click();
    await page.locator("#login").waitFor({ state: "hidden" });
    await page.getByText("My account", { exact: true }).waitFor();
    await page.locator("#logout").click();
    await page.locator("#login[open]").waitFor();
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify(
        {
          status: "passed",
          checks: [
            "all routes",
            "custom model discovery, bridge health, named profile edit/duplicate/check/delete",
            "native provider catalog, OAuth, API-key connect/disconnect and live apply",
            "dynamic targets, checks, severity, credentials, campaigns, findings and source selectors",
            "webhook and retest lifecycle with offline transports",
            "literal evidence/XSS",
            "filters",
            "record-backed dashboard totals, exact drill-downs, triage changes, target expansion and local proposal cohorts",
            "composed finding filters, URL/history restoration, stable pages and keyboard detail opening",
            "3D canvas",
            "recorded path create/persist/tour/delete, stale-evidence stop, reduced motion and mobile layout",
            "local remediation via real subprocess",
            "original repo unchanged",
            "PDF download",
            "schedule create/pause/delete",
            "calendar preview, named timezone, DST rejection, stale edit protection, edit, paused duplicate and history",
            "fake launcher queue",
            "responsive layout",
          ],
          screenshots,
        },
        null,
        2,
      ),
    );
  } finally {
    if (browser) await browser.close();
    child.kill("SIGTERM");
  }
})().catch((error) => {
  process.stderr.write(error.stack + "\n");
  process.exitCode = 1;
});
