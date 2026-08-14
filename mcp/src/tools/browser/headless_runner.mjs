#!/usr/bin/env node

import dns from "node:dns/promises";
import { readFileSync } from "node:fs";
import fs from "node:fs/promises";
import net from "node:net";
import path from "node:path";
import { createRequire } from "node:module";
import { chromium } from "playwright";
import { projectPage } from "./projection.mjs";

const require = createRequire(import.meta.url);
const { version: playwrightVersion } = require("playwright/package.json");
const CAPABILITIES = JSON.parse(
  readFileSync(new URL("./capabilities.json", import.meta.url), "utf8"),
);
const MODES = new Set(Object.keys(CAPABILITIES.modes));
const WAIT_UNTIL = new Set(CAPABILITIES.wait_until);
const LIMITS = CAPABILITIES.limits;
const MINIMUMS = CAPABILITIES.minimums;
const ARTIFACT_ROOT = path.resolve(
  process.env.DARKMOON_BROWSER_ARTIFACT_ROOT || "/opt/darkmoon/out/headless-browser",
);

const MAX_TEXT = LIMITS.max_text_chars_per_page;
const MAX_LINKS = LIMITS.max_links_per_page;
const MAX_FORMS = LIMITS.max_forms_per_page;
const MAX_SCRIPTS = LIMITS.max_scripts_per_page;
const MAX_HEADINGS = LIMITS.max_headings_per_page;
const MAX_CONSOLE = LIMITS.max_console_messages;
const MAX_BLOCKED = LIMITS.max_blocked_requests;
const MAX_URL = 4096;
const MAX_SEMANTIC_NODES = LIMITS.max_semantic_nodes_per_page;

function redactText(value, limit = MAX_TEXT) {
  let text = String(value || "");
  text = text.replace(
    /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g,
    "[REDACTED_TOKEN]",
  );
  text = text.replace(/\bbearer\s+[A-Za-z0-9._~+/=-]{8,}/gi, "Bearer [REDACTED_TOKEN]");
  text = text.replace(/\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/g, "[REDACTED_ACCESS_KEY]");
  text = text.replace(
    /\b(?:sk-[A-Za-z0-9_-]{16,}|(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})\b/g,
    "[REDACTED_CREDENTIAL]",
  );
  text = text.replace(
    /\b(password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|api[_-]?key|secret|client[_-]?secret|authorization|session|session[_-]?id|sid)\s*[:=]\s*[^\s,;&]{3,}/gi,
    "$1=[REDACTED_SECRET]",
  );
  return text.length > limit ? `${text.slice(0, limit)}...[TRUNCATED]` : text;
}

function safeUrl(value) {
  try {
    const parsed = new URL(value);
    if (!["http:", "https:"].includes(parsed.protocol)) return "[NON_HTTP_URL]";
    parsed.username = "";
    parsed.password = "";
    parsed.hash = "";
    const queryKeys = [...new Set(parsed.searchParams.keys())].slice(0, 100);
    parsed.search = "";
    for (const key of queryKeys) {
      parsed.searchParams.append(redactText(key, 120), "[REDACTED]");
    }
    return redactText(parsed.toString(), MAX_URL);
  } catch {
    return "[INVALID_URL]";
  }
}

function canonicalUrl(value) {
  const parsed = new URL(value);
  parsed.hash = "";
  return parsed.toString();
}

function privateIpv4(address) {
  const parts = address.split(".").map(Number);
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return true;
  }
  const [a, b] = parts;
  return (
    a === 0 ||
    a === 10 ||
    a === 127 ||
    (a === 100 && b >= 64 && b <= 127) ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 0) ||
    (a === 192 && b === 168) ||
    (a === 198 && (b === 18 || b === 19)) ||
    a >= 224
  );
}

function privateIpv6(address) {
  const normalized = address.toLowerCase();
  if (normalized.startsWith("::ffff:")) {
    const mapped = normalized.slice("::ffff:".length);
    if (net.isIP(mapped) === 4) return privateIpv4(mapped);
    const groups = mapped.split(":");
    if (groups.length === 2 && groups.every((group) => /^[0-9a-f]{1,4}$/.test(group))) {
      const high = Number.parseInt(groups[0], 16);
      const low = Number.parseInt(groups[1], 16);
      return privateIpv4(
        `${high >> 8}.${high & 0xff}.${low >> 8}.${low & 0xff}`,
      );
    }
  }
  return (
    normalized === "::" ||
    normalized === "::1" ||
    normalized.startsWith("fc") ||
    normalized.startsWith("fd") ||
    normalized.startsWith("fe8") ||
    normalized.startsWith("fe9") ||
    normalized.startsWith("fea") ||
    normalized.startsWith("feb") ||
    normalized.startsWith("ff") ||
    normalized.startsWith("2001:db8")
  );
}

function privateAddress(address) {
  const family = net.isIP(address);
  if (family === 4) return privateIpv4(address);
  if (family === 6) return privateIpv6(address);
  return true;
}

const hostSafetyCache = new Map();

async function offTargetHostIsUnsafe(hostname, initialHostname) {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  const initial = initialHostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (host === initial) return false;
  if (hostSafetyCache.has(host)) return hostSafetyCache.get(host);

  let unsafe = false;
  if (host === "localhost" || host.endsWith(".localhost") || host === "metadata.google.internal") {
    unsafe = true;
  } else if (net.isIP(host)) {
    unsafe = privateAddress(host);
  } else {
    let timerId;
    try {
      const lookup = dns.lookup(host, { all: true, verbatim: true });
      const timer = new Promise((_, reject) => {
        timerId = setTimeout(
          () => reject(new Error("DNS lookup timeout")),
          1000,
        );
      });
      const records = await Promise.race([lookup, timer]);
      unsafe =
        records.length === 0 ||
        records.some((record) => privateAddress(record.address));
    } catch {
      unsafe = true;
    } finally {
      if (timerId) clearTimeout(timerId);
    }
  }
  hostSafetyCache.set(host, unsafe);
  return unsafe;
}

function validateRequest(request) {
  if (!request || typeof request !== "object") throw new Error("request must be an object");
  if (
    typeof request.url !== "string" ||
    request.url.length === 0 ||
    request.url.length > LIMITS.max_url_length ||
    /[\s\\]/.test(request.url)
  ) {
    throw new Error("url is missing or outside its allowed bounds");
  }
  const target = new URL(request.url);
  if (!new Set(["http:", "https:"]).has(target.protocol)) {
    throw new Error("url scheme must be http or https");
  }
  if (target.username || target.password) throw new Error("URL userinfo is forbidden");
  if (!MODES.has(request.mode)) throw new Error("unsupported browser mode");

  const integerBounds = {
    max_pages: [MINIMUMS.max_pages, LIMITS.max_pages],
    max_depth: [MINIMUMS.max_depth, LIMITS.max_depth],
    max_requests: [MINIMUMS.max_requests, LIMITS.max_requests],
    timeout: [MINIMUMS.timeout_seconds, LIMITS.max_timeout_seconds],
    settle_ms: [MINIMUMS.settle_ms, LIMITS.max_settle_ms],
  };
  for (const [key, [minimum, maximum]] of Object.entries(integerBounds)) {
    if (!Number.isInteger(request[key]) || request[key] < minimum || request[key] > maximum) {
      throw new Error(`${key} is outside its allowed bounds`);
    }
  }
  for (const key of ["same_origin", "screenshot", "ignore_https_errors", "follow_links"]) {
    if (typeof request[key] !== "boolean") throw new Error(`${key} must be a boolean`);
  }
  if (!WAIT_UNTIL.has(request.wait_until)) throw new Error("unsupported wait_until mode");

  const artifactDir = path.resolve(request.artifact_dir || "");
  if (!artifactDir.startsWith(`${ARTIFACT_ROOT}${path.sep}`)) {
    throw new Error("artifact directory is outside the browser artifact root");
  }
  return { target, artifactDir };
}

async function collectDom(page) {
  return page.evaluate(
    ({ maxText, maxLinks, maxForms, maxScripts, maxHeadings, maxSemantic }) => {
      const normalizedText = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
      const links = [...document.querySelectorAll("a[href]")]
        .slice(0, maxLinks)
        .map((element) => ({
          href: element.href,
          text: (element.textContent || "").replace(/\s+/g, " ").trim().slice(0, 200),
        }));
      const forms = [...document.forms].slice(0, maxForms).map((form) => ({
        action: form.action || document.URL,
        method: (form.method || "get").toUpperCase(),
        inputs: [...form.elements].slice(0, 200).map((element) => ({
          tag: element.tagName.toLowerCase(),
          type: String(element.type || "").toLowerCase(),
          name: String(element.name || "").slice(0, 120),
        })),
      }));
      const headings = [...document.querySelectorAll("h1,h2,h3")]
        .slice(0, maxHeadings)
        .map((element) => ({
          level: element.tagName.toLowerCase(),
          text: (element.textContent || "").replace(/\s+/g, " ").trim().slice(0, 300),
        }));

      const sinkPatterns = {
        inner_html: /\.innerHTML\s*=/,
        outer_html: /\.outerHTML\s*=/,
        insert_adjacent_html: /insertAdjacentHTML\s*\(/,
        document_write: /document\.(?:write|writeln)\s*\(/,
        eval: /\beval\s*\(/,
        function_constructor: /\bnew\s+Function\s*\(/,
        set_timeout_string: /setTimeout\s*\(\s*["'`]/,
      };
      const sourcePatterns = {
        location_search: /location\.search/,
        location_hash: /location\.hash/,
        document_url: /document\.(?:URL|documentURI)/,
        document_referrer: /document\.referrer/,
        post_message: /addEventListener\s*\(\s*["']message["']/,
        local_storage: /localStorage/,
        session_storage: /sessionStorage/,
      };
      const scripts = [...document.scripts].slice(0, maxScripts).map((script, index) => {
        const source = script.textContent || "";
        return {
          index,
          src: script.src || "inline",
          sinks: Object.entries(sinkPatterns)
            .filter(([, pattern]) => pattern.test(source))
            .map(([name]) => name),
          sources: Object.entries(sourcePatterns)
            .filter(([, pattern]) => pattern.test(source))
            .map(([name]) => name),
        };
      });
      const eventHandlers = [...document.querySelectorAll("*")]
        .flatMap((element) =>
          [...element.attributes]
            .filter((attribute) => attribute.name.toLowerCase().startsWith("on"))
            .map((attribute) => ({
              tag: element.tagName.toLowerCase(),
              id: String(element.id || "").slice(0, 120),
              attribute: attribute.name.toLowerCase(),
            })),
        )
        .slice(0, 500);

      const semantic = [
        ...document.querySelectorAll(
          "a,button,input,select,textarea,summary,[role],[tabindex],h1,h2,h3,h4,h5,h6",
        ),
      ]
        .slice(0, maxSemantic)
        .map((element) => {
          const labels = element.labels
            ? [...element.labels]
                .map((label) => label.textContent || "")
                .join(" ")
            : "";
          const name =
            element.getAttribute("aria-label") ||
            labels ||
            element.getAttribute("alt") ||
            element.getAttribute("title") ||
            element.textContent ||
            "";
          return {
            tag: element.tagName.toLowerCase(),
            role: element.getAttribute("role") || element.tagName.toLowerCase(),
            name: name.replace(/\s+/g, " ").trim().slice(0, 300),
            type: String(element.type || "").toLowerCase(),
            href: element instanceof HTMLAnchorElement ? element.href : "",
            disabled: Boolean(element.disabled),
            required: Boolean(element.required),
          };
        });

      const navigation = performance.getEntriesByType("navigation")[0];
      const paints = performance.getEntriesByType("paint").slice(0, 20);
      const resourceTypes = {};
      for (const resource of performance.getEntriesByType("resource")) {
        const kind = String(resource.initiatorType || "other").slice(0, 40);
        resourceTypes[kind] = (resourceTypes[kind] || 0) + 1;
      }
      const timing = navigation
        ? {
            response_start_ms: Math.round(navigation.responseStart),
            dom_interactive_ms: Math.round(navigation.domInteractive),
            dom_content_loaded_ms: Math.round(navigation.domContentLoadedEventEnd),
            load_event_ms: Math.round(navigation.loadEventEnd),
            duration_ms: Math.round(navigation.duration),
            transfer_size: Number(navigation.transferSize || 0),
            encoded_body_size: Number(navigation.encodedBodySize || 0),
            decoded_body_size: Number(navigation.decodedBodySize || 0),
          }
        : {};
      const performanceSummary = {
        navigation: timing,
        paints: paints.map((entry) => ({
          name: String(entry.name).slice(0, 80),
          start_ms: Math.round(entry.startTime),
        })),
        resource_types: resourceTypes,
        resource_count: performance.getEntriesByType("resource").length,
      };

      const secureDocument = location.protocol === "https:";
      const security = {
        insecure_form_actions: forms.filter(
          (form) => secureDocument && form.action.startsWith("http://"),
        ).length,
        password_forms_using_get: forms.filter(
          (form) =>
            form.method === "GET" &&
            form.inputs.some((input) => input.type === "password"),
        ).length,
        target_blank_without_noopener: [...document.querySelectorAll('a[target="_blank"]')]
          .filter((anchor) => {
            const rel = new Set(
              String(anchor.getAttribute("rel") || "")
                .toLowerCase()
                .split(/\s+/),
            );
            return !rel.has("noopener") && !rel.has("noreferrer");
          }).length,
        mixed_content_resources: secureDocument
          ? performance
              .getEntriesByType("resource")
              .filter((resource) => String(resource.name).startsWith("http://"))
              .length
          : 0,
        inline_event_handlers: eventHandlers.length,
      };

      return {
        url: document.URL,
        title: document.title,
        text_excerpt: normalizedText.slice(0, maxText),
        links,
        forms,
        headings,
        scripts,
        event_handlers: eventHandlers,
        accessibility: semantic,
        performance: performanceSummary,
        security,
      };
    },
    {
      maxText: MAX_TEXT,
      maxLinks: MAX_LINKS,
      maxForms: MAX_FORMS,
      maxScripts: MAX_SCRIPTS,
      maxHeadings: MAX_HEADINGS,
      maxSemantic: MAX_SEMANTIC_NODES,
    },
  );
}

function minimizeDom(raw) {
  return {
    url: safeUrl(raw.url),
    title: redactText(raw.title, 500),
    text_excerpt: redactText(raw.text_excerpt),
    links: raw.links.map((link) => ({
      url: safeUrl(link.href),
      text: redactText(link.text, 200),
    })),
    forms: raw.forms.map((form) => ({
      action: safeUrl(form.action),
      method: form.method,
      inputs: form.inputs,
    })),
    headings: raw.headings.map((heading) => ({
      level: heading.level,
      text: redactText(heading.text, 300),
    })),
    scripts: raw.scripts
      .filter((script) => script.src !== "inline" || script.sinks.length || script.sources.length)
      .map((script) => ({
        index: script.index,
        src: script.src === "inline" ? "inline" : safeUrl(script.src),
        sinks: script.sinks,
        sources: script.sources,
      })),
    event_handlers: raw.event_handlers,
    accessibility: raw.accessibility.map((item) => ({
      tag: item.tag,
      role: item.role,
      name: redactText(item.name, 300),
      type: item.type,
      url: item.href ? safeUrl(item.href) : undefined,
      disabled: item.disabled,
      required: item.required,
    })),
    performance: raw.performance,
    security: raw.security,
  };
}

async function run(request) {
  const { target, artifactDir } = validateRequest(request);
  const followLinks = request.follow_links || request.mode === "crawl";
  const captureScreenshots = request.screenshot || request.mode === "screenshot";
  const initialOrigin = target.origin;
  const initialHostname = target.hostname;
  const requestRecords = [];
  const responseRecords = [];
  const failureRecords = [];
  const blockedRequests = [];
  const consoleRecords = [];
  const artifacts = [];
  let requestCount = 0;
  let browser;

  try {
    browser = await chromium.launch({
      headless: true,
      args: [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-first-run",
      ],
    });
    const context = await browser.newContext({
      acceptDownloads: false,
      ignoreHTTPSErrors: request.ignore_https_errors,
      javaScriptEnabled: true,
      serviceWorkers: "block",
      viewport: { width: 1440, height: 900 },
    });

    await context.route("**/*", async (route) => {
      const browserRequest = route.request();
      requestCount += 1;
      if (requestCount > request.max_requests) {
        if (blockedRequests.length < MAX_BLOCKED) {
          blockedRequests.push({ url: safeUrl(browserRequest.url()), reason: "request_limit" });
        }
        await route.abort("blockedbyclient");
        return;
      }

      let candidate;
      try {
        candidate = new URL(browserRequest.url());
      } catch {
        await route.abort("blockedbyclient");
        return;
      }
      if (["data:", "blob:"].includes(candidate.protocol)) {
        await route.continue();
        return;
      }
      if (!["http:", "https:"].includes(candidate.protocol)) {
        if (blockedRequests.length < MAX_BLOCKED) {
          blockedRequests.push({ url: "[NON_HTTP_URL]", reason: "scheme" });
        }
        await route.abort("blockedbyclient");
        return;
      }
      if (request.same_origin && candidate.origin !== initialOrigin) {
        if (blockedRequests.length < MAX_BLOCKED) {
          blockedRequests.push({ url: safeUrl(candidate.toString()), reason: "cross_origin" });
        }
        await route.abort("blockedbyclient");
        return;
      }
      if (!request.same_origin && (await offTargetHostIsUnsafe(candidate.hostname, initialHostname))) {
        if (blockedRequests.length < MAX_BLOCKED) {
          blockedRequests.push({ url: safeUrl(candidate.toString()), reason: "off_target_private_host" });
        }
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    });

    const page = await context.newPage();
    page.on("request", (item) => {
      if (requestRecords.length < request.max_requests) {
        requestRecords.push({
          url: safeUrl(item.url()),
          method: item.method(),
          resource_type: item.resourceType(),
          navigation: item.isNavigationRequest(),
        });
      }
    });
    page.on("response", (item) => {
      if (responseRecords.length < request.max_requests) {
        responseRecords.push({
          url: safeUrl(item.url()),
          status: item.status(),
          resource_type: item.request().resourceType(),
        });
      }
    });
    page.on("requestfailed", (item) => {
      if (failureRecords.length < 100) {
        failureRecords.push({
          url: safeUrl(item.url()),
          resource_type: item.resourceType(),
          error: redactText(item.failure()?.errorText || "request failed", 300),
        });
      }
    });
    page.on("console", (message) => {
      if (consoleRecords.length < MAX_CONSOLE) {
        consoleRecords.push({
          type: message.type(),
          text: redactText(message.text(), 500),
        });
      }
    });
    page.on("download", (download) => void download.cancel().catch(() => {}));

    const pages = [];
    const queue = [{ url: target.toString(), depth: 0 }];
    const visited = new Set();
    const deadline = Date.now() + request.timeout * 1000;
    let timeLimitReached = false;
    const perPageTimeout = Math.max(
      2000,
      Math.floor((request.timeout * 1000) / Math.max(1, request.max_pages)) - 500,
    );

    while (queue.length && pages.length < request.max_pages) {
      const remaining = deadline - Date.now();
      if (remaining <= 500) {
        timeLimitReached = true;
        break;
      }
      const current = queue.shift();
      let canonical;
      try {
        canonical = canonicalUrl(current.url);
      } catch {
        continue;
      }
      if (visited.has(canonical)) continue;
      visited.add(canonical);

      try {
        const navigationTimeout = Math.max(
          250,
          Math.min(perPageTimeout, deadline - Date.now() - 250),
        );
        const navigation = await page.goto(canonical, {
          waitUntil: request.wait_until,
          timeout: navigationTimeout,
        });
        if (request.settle_ms) {
          const settleFor = Math.min(
            request.settle_ms,
            Math.max(0, deadline - Date.now() - 250),
          );
          if (settleFor > 0) await page.waitForTimeout(settleFor);
          if (settleFor < request.settle_ms) timeLimitReached = true;
        }
        const raw = await collectDom(page);
        const minimized = minimizeDom(raw);
        const responseHeaderNames = new Set(
          Object.keys(navigation?.headers() || {}).map((name) => name.toLowerCase()),
        );
        minimized.security.response_header_presence = {
          content_security_policy: responseHeaderNames.has("content-security-policy"),
          strict_transport_security: responseHeaderNames.has("strict-transport-security"),
          permissions_policy: responseHeaderNames.has("permissions-policy"),
          referrer_policy: responseHeaderNames.has("referrer-policy"),
          x_content_type_options: responseHeaderNames.has("x-content-type-options"),
          x_frame_options: responseHeaderNames.has("x-frame-options"),
          cross_origin_opener_policy: responseHeaderNames.has("cross-origin-opener-policy"),
          cross_origin_resource_policy: responseHeaderNames.has("cross-origin-resource-policy"),
        };
        const pageIndex = pages.length + 1;
        const pageResult = {
          ...minimized,
          depth: current.depth,
          status: navigation?.status() ?? null,
        };

        if (captureScreenshots) {
          await fs.mkdir(artifactDir, { recursive: true, mode: 0o700 });
          const screenshotPath = path.join(artifactDir, `page-${String(pageIndex).padStart(3, "0")}.png`);
          await page.screenshot({ path: screenshotPath, fullPage: false });
          artifacts.push({ type: "screenshot", path: screenshotPath, page: pageIndex });
        }
        pages.push(pageResult);

        if (followLinks && current.depth < request.max_depth) {
          for (const link of raw.links) {
            try {
              const next = new URL(link.href);
              if (!["http:", "https:"].includes(next.protocol)) continue;
              if (request.same_origin && next.origin !== initialOrigin) continue;
              queue.push({ url: next.toString(), depth: current.depth + 1 });
              if (queue.length >= request.max_pages * MAX_LINKS) break;
            } catch {
              // Ignore malformed links discovered in the DOM.
            }
          }
        }
      } catch (error) {
        pages.push({
          url: safeUrl(canonical),
          depth: current.depth,
          error: redactText(error instanceof Error ? error.message : String(error), 500),
        });
      }

      if (!followLinks) break;
      if (Date.now() >= deadline) timeLimitReached = true;
    }

    const sinkCount = pages.reduce(
      (count, item) =>
        count +
        (item.scripts || []).reduce((total, script) => total + script.sinks.length, 0) +
        (item.event_handlers || []).length,
      0,
    );
    const sourceCount = pages.reduce(
      (count, item) =>
        count + (item.scripts || []).reduce((total, script) => total + script.sources.length, 0),
      0,
    );
    const successful = pages.some((item) => !item.error);
    const networkModes = new Set(["snapshot", "crawl", "full", "network"]);
    const consoleModes = new Set(["snapshot", "crawl", "full", "console"]);
    const response = {
      ok: successful,
      engine: { name: "playwright-chromium", playwright_version: playwrightVersion },
      pages: pages.map((pageResult) => projectPage(pageResult, request.mode)),
      network: networkModes.has(request.mode)
        ? {
            requests: requestRecords,
            responses: responseRecords,
            failures: failureRecords,
          }
        : {},
      console: consoleModes.has(request.mode) ? consoleRecords : [],
      blocked_requests: blockedRequests,
      artifacts,
      summary: {
        pages_visited: pages.length,
        requests_observed: requestRecords.length,
        requests_blocked: blockedRequests.length,
        dom_sinks: sinkCount,
        dom_sources: sourceCount,
        time_limit_reached: timeLimitReached,
        truncated:
          requestCount > request.max_requests ||
          timeLimitReached ||
          (followLinks && queue.length > 0),
      },
    };
    if (!successful) {
      response.error = {
        code: timeLimitReached ? "browser_timeout" : "navigation_failed",
        message: timeLimitReached
          ? "Browser time limit reached before a page completed"
          : "No page completed successfully",
      };
    }
    return response;
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

async function main() {
  try {
    if (process.argv.length !== 3) throw new Error("expected one encoded request argument");
    const decoded = Buffer.from(process.argv[2], "base64url").toString("utf8");
    const request = JSON.parse(decoded);
    const result = await run(request);
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    const message = redactText(error instanceof Error ? error.message : String(error), 500);
    process.stdout.write(
      `${JSON.stringify({
        ok: false,
        engine: { name: "playwright-chromium", playwright_version: playwrightVersion },
        error: { code: "browser_runner_error", message },
        pages: [],
        network: { requests: [], responses: [], failures: [] },
        console: [],
        blocked_requests: [],
        artifacts: [],
        summary: { pages_visited: 0 },
      })}\n`,
    );
  }
}

await main();
