// Native extension host is allowed only inside an OS-isolated offline container.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
(async()=>{
 assert.ok(Object.values(os.networkInterfaces()).flat().every(address=>address.internal),'Use Docker --network none for native VS Code acceptance');
 const root=path.resolve(__dirname,'../../integrations/upstream/vscode');
 const {runTests}=require(path.join(root,'node_modules/@vscode/test-electron'));
 const state=fs.mkdtempSync(path.join(os.tmpdir(),'darkmoon-vscode-'));
 fs.mkdirSync(path.join(state,'User'));
 fs.writeFileSync(path.join(state,'User/settings.json'),JSON.stringify({'telemetry.telemetryLevel':'off','update.mode':'none','extensions.autoCheckUpdates':false,'extensions.autoUpdate':false,'workbench.enableExperiments':false,'security.workspace.trust.enabled':true,'darkmoon.growthCta.enabled':false}));
 await runTests({vscodeExecutablePath:fs.readFileSync('/opt/vscode-executable','utf8').trim(),extensionDevelopmentPath:root,extensionTestsPath:path.join(root,'out/test/nativeRunner.js'),extensionTestsEnv:{DARKMOON_TEST:'1',DARKMOON_DISABLE_GROWTH_CTA:'1'},launchArgs:['--no-sandbox','--disable-gpu','--disable-telemetry','--skip-welcome','--skip-release-notes','--disable-extensions','--user-data-dir='+state]});
 console.log('PASS actual pinned VS Code extension host, offline');
})().catch(error=>{console.error(error);process.exitCode=1});
