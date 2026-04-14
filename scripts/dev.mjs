#!/usr/bin/env node
// One command to run Boop locally: server + convex + debug dashboard + ngrok.
// Prefixes each child's output so you can tell who's saying what.

import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");

// --- preflight: Convex types must exist ----------------------------------
if (!existsSync(resolve(root, "convex/_generated/api.js"))) {
  console.error(`
┌─────────────────────────────────────────────────────────────┐
│  Convex types haven't been generated yet.                   │
│                                                             │
│  Run this first:                                            │
│    npm run setup           (full interactive setup)         │
│    npx convex dev --once   (just generate types)            │
└─────────────────────────────────────────────────────────────┘
`);
  process.exit(1);
}

// --- read PORT from .env.local ------------------------------------------
function readEnv() {
  const p = resolve(root, ".env.local");
  if (!existsSync(p)) return {};
  const env = {};
  for (const line of readFileSync(p, "utf8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*?)(?:\s+#.*)?$/);
    if (m) env[m[1]] = m[2].trim();
  }
  return env;
}
const envVars = readEnv();
const port = envVars.PORT || "3456";

// --- binary detection ---------------------------------------------------
function hasBinary(name) {
  return new Promise((ok) => {
    const lookup = process.platform === "win32" ? "where" : "which";
    const child = spawn(lookup, [name], { stdio: "ignore" });
    child.on("exit", (code) => ok(code === 0));
    child.on("error", () => ok(false));
  });
}

// --- color-prefixed child runner ----------------------------------------
const C = {
  server: "\x1b[36m",
  convex: "\x1b[35m",
  debug: "\x1b[33m",
  ngrok: "\x1b[32m",
  banner: "\x1b[1;32m",
  dim: "\x1b[2m",
  reset: "\x1b[0m",
};

function run(name, cmd, args) {
  const child = spawn(cmd, args, {
    cwd: root,
    env: { ...process.env, FORCE_COLOR: "1" },
  });
  const prefix = `${C[name]}${name.padEnd(6)}${C.reset} │ `;
  let buf = "";
  const feed = (chunk) => {
    buf += chunk.toString();
    let i;
    while ((i = buf.indexOf("\n")) !== -1) {
      const line = buf.slice(0, i);
      if (line.trim()) process.stdout.write(prefix + line + "\n");
      buf = buf.slice(i + 1);
    }
  };
  child.stdout.on("data", feed);
  child.stderr.on("data", feed);
  return child;
}

// --- ngrok URL banner: poll local API after launch ----------------------
async function waitForNgrokUrl(timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch("http://127.0.0.1:4040/api/tunnels");
      if (res.ok) {
        const data = await res.json();
        const https = data.tunnels?.find((t) => t.proto === "https")?.public_url;
        if (https) return https;
      }
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return null;
}

function showBanner(url) {
  const line = "═".repeat(60);
  const webhook = `${url}/sendblue/webhook`;
  console.log(`
${C.banner}${line}
  ngrok tunnel is live.

  Public URL:        ${url}
  Sendblue webhook:  ${webhook}

  → Paste the webhook URL into your Sendblue dashboard.
${line}${C.reset}
`);
}

// --- main ---------------------------------------------------------------
const ngrokInstalled = await hasBinary("ngrok");
if (!ngrokInstalled) {
  console.log(`
${C.ngrok}! ngrok is not installed — running without a public tunnel.${C.reset}
${C.dim}  Install:   brew install ngrok         (macOS)
             or download from https://ngrok.com/download
  Auth:      ngrok config add-authtoken <token>
             (free token at https://dashboard.ngrok.com)
  Without ngrok you can still use the debug dashboard at http://localhost:5173
  — iMessage replies via Sendblue won't work until your server is reachable.${C.reset}
`);
}

console.log(`\nBoop dev starting on port ${port}. Ctrl-C to stop everything.\n`);

const children = [
  run("server", "npx", ["tsx", "watch", "server/index.ts"]),
  run("convex", "npx", ["convex", "dev"]),
  run("debug", "npx", ["vite", "--config", "debug/vite.config.ts"]),
];
if (ngrokInstalled) {
  children.push(
    run("ngrok", "ngrok", [
      "http",
      port,
      "--log=stdout",
      "--log-format=term",
      "--log-level=info",
    ]),
  );
  waitForNgrokUrl()
    .then((url) => {
      if (url) showBanner(url);
      else
        console.log(
          `${C.ngrok}ngrok${C.reset} │ could not read tunnel URL from http://127.0.0.1:4040 — check ngrok output above.`,
        );
    })
    .catch(() => {});
}

let shuttingDown = false;
const shutdown = (code = 0) => {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const c of children) {
    try {
      c.kill();
    } catch {
      /* ignore */
    }
  }
  setTimeout(() => process.exit(code), 500);
};
process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
for (const c of children) {
  c.on("exit", (code) => {
    if (!shuttingDown && code !== null && code !== 0) {
      console.error(`\nA child process exited with code ${code}. Shutting down.`);
      shutdown(code);
    }
  });
}
