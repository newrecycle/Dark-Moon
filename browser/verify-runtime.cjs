#!/usr/bin/env node

const fs = require("node:fs");
const { chromium } = require("playwright");
const { version } = require("playwright/package.json");

async function main() {
  const executable = chromium.executablePath();
  fs.accessSync(executable, fs.constants.X_OK);

  if (process.argv.includes("--launch")) {
    const browser = await chromium.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    });
    try {
      const page = await browser.newPage();
      await page.goto("data:text/html,<title>darkmoon-browser-ok</title>");
      if ((await page.title()) !== "darkmoon-browser-ok") {
        throw new Error("Chromium launch probe returned an unexpected page title");
      }
    } finally {
      await browser.close();
    }
  }

  process.stdout.write(
    `${JSON.stringify({ available: true, engine: "playwright-chromium", version })}\n`,
  );
}

main().catch((error) => {
  process.stdout.write(
    `${JSON.stringify({
      available: false,
      engine: "playwright-chromium",
      version,
      error: String(error?.message || error).slice(0, 500),
    })}\n`,
  );
  process.exitCode = 1;
});
