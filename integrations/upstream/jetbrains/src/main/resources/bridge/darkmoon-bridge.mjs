#!/usr/bin/env node
/*
 * darkmoon-bridge — thin adapter that exposes the FULL @darkmoon/client contract
 * surface as the JSON subcommand grammar the JetBrains plugin's CliDarkmoonClient
 * speaks. It ONLY calls the shipped @darkmoon/client library; it contains no
 * detection, normalization or redaction of its own (that lives once, in the TS
 * client). The portable `darkmoon-ci` binary is CI-oriented (detect/launch/
 * status/summary/findings/report/wait/run); this bridge adds the read surface a
 * GUI needs (campaigns list, single finding + evidence, streaming).
 *
 * Resolution of the library:
 *   DARKMOON_CLIENT_MODULE = path to @darkmoon/client (dist/index.js), else
 *   the bare specifier "@darkmoon/client" (must be installed/resolvable).
 *
 * Backend config comes from flags + env, mirroring darkmoon-ci:
 *   --mode auto|oss|pro
 *   --base-url <proBaseUrl>        DARKMOON_TOKEN (Pro JWT, never on argv)
 *   DARKMOON_OSS_DATA_DIR / DARKMOON_OSS_REPORTS_DIR (OSS)
 *
 * The bridge strips `raw` from every object before printing (contract §: raw is
 * internal-only and must never be emitted).
 */
const argv = process.argv.slice(2);
const flags = {};
const pos = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a.startsWith("--")) {
    const key = a.slice(2);
    const next = argv[i + 1];
    if (next !== undefined && !next.startsWith("--")) { flags[key] = next; i++; }
    else flags[key] = true;
  } else pos.push(a);
}

function stripRaw(o) {
  if (Array.isArray(o)) return o.map(stripRaw);
  if (o && typeof o === "object") {
    const { raw, ...rest } = o;
    for (const k of Object.keys(rest)) rest[k] = stripRaw(rest[k]);
    return rest;
  }
  return o;
}
function out(obj) { process.stdout.write(JSON.stringify(stripRaw(obj))); }
function readStdin() {
  return new Promise((resolve) => {
    let d = ""; process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (d += c));
    process.stdin.on("end", () => resolve(d));
    if (process.stdin.isTTY) resolve("");
  });
}

async function main() {
  const spec = process.env.DARKMOON_CLIENT_MODULE || "@darkmoon/client";
  const { DarkmoonClient } = await import(spec);

  const client = new DarkmoonClient({
    mode: flags.mode || process.env.DARKMOON_MODE || "auto",
    pro: {
      baseUrl: flags["base-url"] || process.env.DARKMOON_PRO_URL,
      token: process.env.DARKMOON_TOKEN,
      refuseInsecureDefault: false, // surface as a Capabilities.warning, don't throw
    },
    oss: {
      dataDir: process.env.DARKMOON_OSS_DATA_DIR,
      reportsDir: process.env.DARKMOON_OSS_REPORTS_DIR,
    },
  });

  const cmd = pos[0];
  const evidenceOpts = {
    includeEvidence: !!flags["include-evidence"],
    full: !!flags.full,
    private: !!flags.private,
  };

  if (cmd === "detect") {
    out(await client.detect());
  } else if (cmd === "campaigns" && pos[1] === "list") {
    const filter = {};
    if (flags.status) filter.status = flags.status;
    if (flags["target-id"]) filter.targetId = flags["target-id"];
    out(await client.listCampaigns(filter));
  } else if (cmd === "campaign" && pos[1] === "get") {
    out(await client.getCampaign(pos[2]));
  } else if (cmd === "campaign" && pos[1] === "status") {
    const ref = flags.correlation ? JSON.parse(flags.correlation) : pos[2];
    out(await client.getCampaignStatus(ref));
  } else if (cmd === "summary") {
    out(await client.getSeveritySummary(pos[1]));
  } else if (cmd === "findings" && pos[1] === "list") {
    const filter = {};
    if (flags.campaign) filter.campaignId = flags.campaign;
    if (flags.project) filter.projectId = flags.project;
    if (flags["target-id"]) filter.targetId = flags["target-id"];
    if (flags.severity) filter.severity = flags.severity;
    if (flags.category) filter.category = flags.category;
    if (flags.status) filter.status = flags.status;
    out(await client.listFindings(filter, evidenceOpts));
  } else if (cmd === "finding" && pos[1] === "get") {
    out(await client.getFinding(pos[2], evidenceOpts));
  } else if (cmd === "report") {
    const opts = { full: !!flags.full, private: !!flags.private };
    out(await client.getReport(pos[1], opts));
  } else if (cmd === "launch") {
    const input = JSON.parse((await readStdin()) || "{}");
    out(await client.launchCampaign(input));
  } else if (cmd === "stream") {
    for await (const ev of client.streamProgress(pos[1])) {
      process.stdout.write(JSON.stringify(stripRaw(ev)) + "\n");
    }
  } else {
    process.stderr.write("darkmoon-bridge: unknown command: " + pos.join(" ") + "\n");
    process.exit(2);
  }
}

main().catch((err) => {
  // Errors are secret-scrubbed by the library; print the code/message only.
  process.stderr.write("darkmoon-bridge error: " + (err && (err.code || err.message) || err) + "\n");
  process.exit(1);
});
