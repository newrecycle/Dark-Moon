"use strict";

// This function is deliberately self-contained: esbuild embeds it in the HPI's
// CLI, and a detached Node process executes its source without another file.
function producerWorker() {
  const { spawn } = require("node:child_process");
  let child, timer, root = null, streamRoot = null, failed = false;
  let line = Buffer.alloc(0), oversized = false;
  const session = /^ses_[A-Za-z0-9_-]{1,128}$/;
  const emit = (message, done = () => {}) => {
    if (process.connected) process.send(message, () => done());
    else done();
  };
  function terminate() {
    if (process.platform !== "win32") {
      try { process.kill(-process.pid, "SIGTERM"); return; } catch { /* own group only */ }
    }
    child?.kill("SIGTERM");
    process.exit(1);
  }
  function fail(reason) {
    if (failed) return;
    failed = true;
    clearTimeout(timer);
    emit({ type: "failed", reason }, terminate);
  }
  function event(bytes) {
    let item;
    try { item = JSON.parse(bytes.toString("utf8")); } catch { return; }
    if (!item || typeof item !== "object" || ![
      "step_start", "step_finish", "text", "tool_use", "error",
    ].includes(item.type)) return;
    if (!session.test(item.sessionID) || streamRoot && streamRoot !== item.sessionID ||
        (item.part?.sessionID !== undefined && item.part.sessionID !== item.sessionID)) {
      return fail("identity");
    }
    streamRoot = item.sessionID;
    if (item.type === "step_start") {
      if (!session.test(item.sessionID) || item.part?.type !== "step-start" ||
          item.part.sessionID !== item.sessionID) return fail("identity");
      if (root && root !== item.sessionID) return fail("identity");
      root = item.sessionID;
    } else if (root && (item.sessionID !== root ||
               (item.part?.sessionID !== undefined && item.part.sessionID !== root))) {
      return fail("identity");
    }
    if (item.type === "error") fail("producer");
  }
  process.once("message", ({ cmd, args, cwd, timeoutMs }) => {
    if (typeof cmd !== "string" || !Array.isArray(args) ||
        args.some(a => typeof a !== "string") || typeof cwd !== "string" ||
        !Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 86400000) {
      return fail("configuration");
    }
    timer = setTimeout(() => fail("timeout"), timeoutMs);
    child = spawn(cmd, args, { cwd, env: process.env, stdio: ["ignore", "pipe", "ignore"] });
    child.once("spawn", () => emit({ type: "started" }));
    child.once("error", () => fail("spawn"));
    child.stdout.on("data", chunk => {
      // Never persist or forward producer text/tool output. Retain at most one
      // 64-KiB JSON line and discard oversized lines through the next newline.
      let start = 0;
      while (start < chunk.length && !failed) {
        const newline = chunk.indexOf(10, start);
        const end = newline < 0 ? chunk.length : newline;
        const part = chunk.subarray(start, end);
        if (!oversized && line.length + part.length <= 65536) line = Buffer.concat([line, part]);
        else { oversized = true; line = Buffer.alloc(0); }
        if (newline < 0) break;
        if (!oversized) event(line);
        line = Buffer.alloc(0); oversized = false; start = newline + 1;
      }
    });
    child.once("close", code => {
      clearTimeout(timer);
      if (failed) return;
      if (line.length && !oversized) event(line);
      if (failed) return;
      if (code !== 0 || !root) return fail(code !== 0 ? "producer" : "identity");
      emit({ type: "completed", rootSessionId: root }, () => process.exit(0));
    });
  });
  process.once("disconnect", () => { if (!child) process.exit(1); });
}

function launchProducer({ cmd, args, cwd, timeoutMs = 1800000 }) {
  const { spawn } = require("node:child_process");
  const state = { status: "running", rootSessionId: null, reason: null };
  let finish, ready, bootTimer;
  state.done = new Promise(resolve => { finish = resolve; });
  state.ready = new Promise(resolve => { ready = resolve; });
  const release = () => {
    clearTimeout(bootTimer);
    ready(state);
    worker.unref();
    worker.channel?.unref();
  };
  const failed = reason => {
    if (state.status !== "running") return;
    state.status = "failed"; state.reason = reason; finish(state); release();
  };
  const worker = spawn(process.execPath, ["-e", `(${producerWorker.toString()})()`], {
    detached: true, stdio: ["ignore", "ignore", "ignore", "ipc"],
  });
  worker.on("message", message => {
    if (state.status !== "running") return;
    if (message?.type === "started") return release();
    if (message?.type === "completed" && /^ses_[A-Za-z0-9_-]{1,128}$/.test(message.rootSessionId)) {
      state.status = "completed"; state.rootSessionId = message.rootSessionId; finish(state); release();
    } else failed("identity");
  });
  worker.once("error", () => failed("spawn"));
  worker.once("close", () => failed("producer"));
  worker.once("disconnect", () => failed("channel"));
  worker.once("spawn", () => worker.send({ cmd, args, cwd, timeoutMs }, error => {
    if (error) failed("spawn");
  }));
  bootTimer = setTimeout(() => {
    failed("startup");
    try { process.kill(-worker.pid, "SIGTERM"); } catch { worker.kill("SIGTERM"); }
  }, 10000);
  return state;
}

module.exports = { launchProducer };
