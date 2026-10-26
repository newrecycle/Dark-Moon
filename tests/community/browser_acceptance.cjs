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
        await page
          .locator("#surface-canvas")
          .dispatchEvent("wheel", { deltaY: -100 });
        await page.screenshot({
          path: path.join(screenshots, "surface.png"),
          fullPage: true,
        });
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
    await page.locator("#workspace-form input[name=provider]").fill("fixture");
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
    await page.locator("[data-prepare-fix]").click();
    await page
      .locator("#remediation-form input[name=repo]")
      .fill(fixture.source_repo);
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
    const downloadEvent = page.waitForEvent("download");
    await page.locator("[data-export=pdf]").click();
    const download = await downloadEvent;
    const pdf = await fs.readFile(await download.path());
    assert.equal(pdf.subarray(0, 4).toString(), "%PDF");
    await page.locator("#detail .close-dialog").click();
    await page.locator('nav a[href="#schedules"]').click();
    await page.locator("#new-schedule").click();
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
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify(
        {
          status: "passed",
          checks: [
            "all routes",
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
