// Launch actual Chromium with each agent-prescribed argument list.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
  ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES + '/playwright' : 'playwright');
(async () => {
  const text=fs.readFileSync('conf/agents/headless-browser.md','utf8');
  const examples=[...text.matchAll(/chromium\.launch\(\{\s*headless:\s*true,\s*args:\s*(\[[^\]]+\])/g)];
  assert.equal(examples.length,2,'Both mandated launch examples must be exercised');
  for (const example of examples) {
    const args=[...example[1].matchAll(/['"](--[a-z-]+)['"]/g)].map(m=>m[1]);
    for (const flag of ['--no-sandbox','--disable-dev-shm-usage','--single-process','--no-zygote','--disable-gpu']) {
      assert.ok(args.includes(flag),`Missing mandatory flag ${flag}`);
    }
    const browser=await chromium.launch({headless:true,args,
      ...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
    try {
      const page=await browser.newPage();
      page.setDefaultTimeout(8000);
      await page.setContent('<button>Agent browser ready</button>');
      await page.getByRole('button',{name:'Agent browser ready'}).click();
      assert.equal(await page.locator('button').textContent(),'Agent browser ready');
    } finally {await browser.close()}
  }
  console.log('Actual Chromium launch/render/interaction/close passed with both prescribed agent flag lists.');
})().catch(error=>{console.error(error);process.exitCode=1});
