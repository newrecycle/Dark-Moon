// Actual packaged app in native Grafana, served only on the private fixture network.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
(async () => {
  const origin = process.env.GRAFANA_URL || 'http://dm-grafana:3000';
  const browser = await chromium.launch({headless:true});
  let page;
  const errors = [];
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      return url.origin === origin ? route.continue() : route.abort();
    });
    const login = await context.request.post(origin + '/login', {
      data:{user:'admin',password:process.env.GRAFANA_ADMIN}
    });
    assert.equal(login.status(),200,'synthetic Grafana login must succeed');
    page = await context.newPage();
    page.setDefaultTimeout(30000);
    page.on('pageerror', error=>errors.push(error.message));
    const root = origin + '/a/darkmoon-securityposture-app/';
    const views = [['overview','Overview'],['campaigns','Campaigns'],['findings','Findings'],
      ['targets','Targets'],['timeseries','Trends'],['pullrequests','Published PRs'],
      ['remediation','Local proposals'],['retest','Retests']];
    for (const [view,label] of views) {
      await page.goto(root+view+'?datasource=darkmoon-fixture');
      await page.getByRole('heading',{name:'Darkmoon · '+label,exact:true}).waitFor();
      if(view==='retest') await page.getByLabel('Retest ID').fill('retest_demo_1');
      await page.getByRole('table').first().waitFor();
      assert.equal(await page.getByText('Reading current metadata…',{exact:true}).count(),0);
      assert.doesNotMatch(await page.locator('body').innerText(),/PRIVATE-EVIDENCE|fixture-only/);
      if(view==='findings') {
        await page.getByLabel('Severity',{exact:true}).selectOption('critical');
        await page.getByRole('table').getByText('SQL Injection in /product?id',{exact:true}).first().waitFor();
        // Wait for the response corresponding to this filter, not the prior rows.
        await page.waitForFunction(()=>!document.body.textContent.includes('Reading current metadata…'));
        assert.doesNotMatch(await page.getByRole('table').innerText(),/Reflected XSS/);
      }
      if(view==='retest') assert.match(await page.getByRole('table').allTextContents().then(x=>x.join(' ')),/completed/);
      if(['overview','findings','retest'].includes(view)) {
        await page.screenshot({path:'/evidence/'+view+'.png',fullPage:true});
      }
    }
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:'/evidence/retest-mobile.png',fullPage:true});
    await page.goto(root+'overview?datasource=unavailable-fixture');
    await page.getByRole('alert').filter({hasText:'The selected datasource is unavailable'}).waitFor();
    assert.equal(await page.getByRole('table').count(),0,'unavailable explicit source must not fall back');
    assert.deepEqual(errors,[],'native app must not emit uncaught page errors');
    console.log(JSON.stringify({native_browser:true,views:views.map(x=>x[0]),filter:true,
      retest:true,unavailable_source_denied:true,protected_content_absent:true}));
  } finally {
    if(page) await page.screenshot({path:'/evidence/final-state.png',fullPage:true}).catch(()=>{});
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
