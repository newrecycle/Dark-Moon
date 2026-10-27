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
    await page.goto(`http://127.0.0.1:${fixture.port}`);
    await page.locator("#token").fill(fixture.token);
    await page.locator("#login-form button[type=submit]").click();
    await page.locator("#login").waitFor({ state: "hidden" });
    await page.getByText("Your security workspace").waitFor();
    const screenshots =
      process.env.DARKMOON_SCREENSHOTS || path.join(root, "screenshots");
    await fs.mkdir(screenshots, { recursive: true });
    await page.screenshot({
      path: path.join(screenshots, "overview.png"),
      fullPage: true,
    });
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
    await page.locator("#finding-search").fill("SQL injection");
    await page
      .locator(`[data-finding="${fixture.finding_id}"]`)
      .first()
      .click();
    await page.locator("#detail[open]").waitFor();
    assert.equal(
      await page.evaluate(() => window.injected),
      undefined,
      "Finding content must be escaped",
    );
    const responseEvidence = await page
      .locator('[data-evidence-field="raw_response"]')
      .textContent();
    assert.ok(
      responseEvidence.includes("HTTP/1.1 200 OK\nContent-Type: text/html"),
    );
    assert.ok(
      responseEvidence.includes("<script>window.injected=true</script>"),
    );
    assert.ok(!responseEvidence.includes("\x1b"));
    assert.equal(await page.locator("#detail-body script").count(), 0);
    await page.locator("[data-prepare-fix]").click();
    await page.locator("#remediation-dialog[open]").waitFor();
    assert.equal(
      await page.locator("#remediation-form input[name=repo]").inputValue(),
      fixture.source_repo,
    );
    assert.equal(
      await page
        .locator("#remediation-form select[name=source_files] option")
        .count(),
      1,
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
    assert.ok(
      await page.locator("#launch-form input[name=target]").inputValue(),
    );
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
    await page
      .locator("#launch-form input[name=first_run]")
      .fill("2099-01-01T12:00");
    await page.locator("#launch-submit").click();
    await page.locator("#launch-dialog").waitFor({ state: "hidden" });
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
    await page.locator("#launch-submit").click();
    await page.locator("#launch-dialog").waitFor({ state: "hidden" });
    await page
      .locator(".list-item")
      .filter({ hasText: "Fake launcher assessment" })
      .locator(".badge")
      .filter({ hasText: "succeeded" })
      .waitFor({ timeout: 10000 });
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
            "3D canvas",
            "local remediation via real subprocess",
            "original repo unchanged",
            "PDF download",
            "schedule create/pause/delete",
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
