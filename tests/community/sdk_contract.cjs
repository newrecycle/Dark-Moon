// Exercise the imported, unmodified official SDK against OUR real HTTP server.
// The Python fixture uses a fake assessment launcher and disables webhook I/O.
const {
  DarkmoonClient,
} = require("../../integrations/upstream/client/dist/index.cjs");
const { spawn } = require("node:child_process");
const fs = require("node:fs/promises"),
  os = require("node:os"),
  path = require("node:path"),
  assert = require("node:assert/strict");
(async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "darkmoon-sdk-"));
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
        DARKMOON_DASHBOARD_TOKEN: "offline-sdk-fixture-token-123456789",
      },
    },
  );
  try {
    const fixture = await new Promise((resolve, reject) => {
      let text = "";
      const timer = setTimeout(
        () => reject(new Error("Fixture startup timed out")),
        15000,
      );
      child.stdout.on("data", (c) => {
        text += c;
        if (text.includes("\n")) {
          clearTimeout(timer);
          resolve(JSON.parse(text.split("\n")[0]));
        }
      });
      child.stderr.on("data", (c) => process.stderr.write(c));
      child.on("exit", (c) => reject(new Error("Fixture exited " + c)));
    });
    const baseUrl = `http://127.0.0.1:${fixture.port}`;
    const login = await fetch(baseUrl + "/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: "fixture-admin",
        password: "offline-fixture-password",
      }),
    });
    assert.equal(login.status, 200);
    const { token } = await login.json();
    const sdk = new DarkmoonClient({
      mode: "pro",
      pro: { baseUrl, token },
      logLevel: "silent",
    });
    const capabilities = await sdk.detect();
    assert.equal(capabilities.available, true);
    const campaigns = await sdk.listCampaigns();
    assert.equal(campaigns.length, 3);
    const campaign = await sdk.getCampaign(fixture.campaign_id);
    assert.equal(campaign.id, fixture.campaign_id);
    const findings = await sdk.listFindings({
      campaignId: fixture.campaign_id,
    });
    assert.equal(findings.length, 3);
    const finding = await sdk.getFinding(fixture.finding_id, {
      includeEvidence: true,
    });
    assert.equal(finding.id, fixture.finding_id);
    const report = await sdk.getReport(fixture.campaign_id);
    assert.ok(report.content.length > 500);
    const evidence = await sdk.getEvidenceMeta(fixture.finding_id);
    assert.equal(evidence.hasEvidence, true);
    const series = await sdk.getTimeseries({
      metric: "severity",
      group: "day",
    });
    assert.ok(series.series.length);
    const hook = await sdk.registerWebhook({
      url: "https://receiver.example/hook",
      events: ["campaign.completed"],
      secret: "offline-sdk-webhook-secret-123456",
    });
    assert.ok(hook.id);
    assert.equal((await sdk.listWebhooks()).length, 1);
    assert.equal(await sdk.deleteWebhook(hook.id), true);
    const retest = await sdk.launchRetest({ campaignId: fixture.campaign_id });
    assert.ok(retest.retestId);
    const state = await sdk.getRetest(retest.retestId);
    assert.equal(state.retestId, retest.retestId);
    const launch = await sdk.launchCampaign({
      target: "fixture.example",
      program: "SDK contract assessment",
      focus: ["sqli"],
    });
    assert.ok(launch.runId);
    const progress = [];
    for await (const event of sdk.streamProgress(launch)) {
      progress.push(event);
      if (event.terminal) break;
    }
    assert.ok(progress.some((e) => e.type === "run_completed"));
    // The Action/VS Code sources pin the older, differently named package.
    const { DarkmoonClient: LegacyClient } = require(
      "../../integrations/upstream/action/node_modules/@darkmoon/client/dist/index.cjs",
    );
    const legacy = new LegacyClient({
      mode: "pro",
      pro: { baseUrl, token },
      logLevel: "silent",
    });
    assert.equal((await legacy.detect()).available, true);
    assert.ok((await legacy.listCampaigns()).length >= 3);
    assert.equal((await legacy.listFindings({ campaignId: fixture.campaign_id })).length, 3);
    assert.ok((await legacy.getReport(fixture.campaign_id)).content.length > 500);
    console.log(
      JSON.stringify(
        {
          status: "passed",
          sdk: "official @darkmoon_ai/client 0.2.0",
          checks: [
            "login JWT",
            "capabilities",
            "campaign list/detail",
            "finding list/detail",
            "report",
            "evidence metadata",
            "timeseries",
            "webhook create/list/delete without delivery",
            "retest launch/status",
            "assessment queue",
            "real SSE progress with fake launcher",
            "legacy Action/VS Code SDK detect, campaigns, findings and report",
          ],
        },
        null,
        2,
      ),
    );
  } finally {
    child.kill("SIGTERM");
  }
})().catch((e) => {
  process.stderr.write(e.stack + "\n");
  process.exitCode = 1;
});
