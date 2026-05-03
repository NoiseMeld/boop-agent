#!/usr/bin/env tsx
import prompts from "prompts";
import { spawn } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Use fileURLToPath, not URL.pathname — pathname stays URL-encoded, so a repo
// path containing spaces (e.g. "/Volumes/Dock SSD/...") becomes "Dock%20SSD"
// and any spawn() with cwd: ROOT fails ENOENT before exec.
const ROOT = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const ENV_PATH = resolve(ROOT, ".env.local");
const EXAMPLE_PATH = resolve(ROOT, ".env.example");

function readEnv(path: string): Record<string, string> {
  if (!existsSync(path)) return {};
  const lines = readFileSync(path, "utf8").split("\n");
  const env: Record<string, string> = {};
  for (const line of lines) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m) env[m[1]] = m[2];
  }
  return env;
}

function writeEnv(path: string, env: Record<string, string>): void {
  const example = existsSync(EXAMPLE_PATH) ? readFileSync(EXAMPLE_PATH, "utf8") : "";

  let out = "";
  const seen = new Set<string>();
  const sections = example.split(/\n(?=# ----)/);

  for (const section of sections) {
    const sectionKeys = [...section.matchAll(/^([A-Z0-9_]+)=/gm)].map((m) => m[1]);
    let s = section;
    for (const k of sectionKeys) {
      // Remove ALL existing occurrences of this key in the section (dedupe).
      const pattern = new RegExp(`^${k}=.*(\\r?\\n)?`, "gm");
      const matches = [...s.matchAll(pattern)];
      if (matches.length === 0) continue;

      if (seen.has(k)) {
        // Already written in an earlier section — just strip any re-occurrences.
        s = s.replace(pattern, "");
        continue;
      }

      const v = env[k] ?? "";
      // Replace first occurrence, remove the rest.
      let replaced = false;
      s = s.replace(pattern, (match) => {
        if (!replaced) {
          replaced = true;
          return `${k}=${v}` + (match.endsWith("\n") ? "\n" : "");
        }
        return "";
      });
      seen.add(k);
    }
    out += s + "\n";
  }
  writeFileSync(path, out.trim() + "\n");
}

function cleanConvexUrlEnv(path: string): void {
  const envContent = readFileSync(path, "utf8");
  const updated = envContent.replace(/^VITE_CONVEX_URL=.*(\r?\n)?/gm, "");
  writeFileSync(path, updated);
}

function banner(s: string) {
  console.log("\n" + "━".repeat(60));
  console.log("  " + s);
  console.log("━".repeat(60));
}

// Resolve how to invoke an npm-published CLI without depending on `npx` being on PATH.
// Node's spawn() does a direct PATH lookup (no shell), which breaks for:
//   - Windows users (npx is npx.cmd, not findable without shell:true)
//   - Volta/fnm/asdf shims and zsh function aliases
// When we're running under `npm run`, npm sets npm_execpath to the absolute path of
// its CLI — invoking that with the current node binary sidesteps PATH entirely.
function npxInvoker(): { cmd: string; leading: string[] } {
  const npmCli = process.env.npm_execpath;
  if (npmCli) return { cmd: process.execPath, leading: [npmCli, "exec", "--yes", "--"] };
  return {
    cmd: process.platform === "win32" ? "npx.cmd" : "npx",
    leading: ["-y"],
  };
}

async function runConvexDev(): Promise<void> {
  // If CONVEX_DEPLOYMENT is already set, `convex dev` reuses that deployment.
  // Only pass --configure new if this is a first-time setup — otherwise re-running
  // setup would silently create a new project and abandon all existing data.
  const existing = readEnv(ENV_PATH);
  const convexArgs = existing.CONVEX_DEPLOYMENT
    ? ["convex", "dev", "--once"]
    : ["convex", "dev", "--once", "--configure", "new"];

  console.log(`\nLaunching \`npx ${convexArgs.join(" ")}\` to configure your deployment.`);
  console.log("Convex will open a browser window if you're not logged in.");
  if (existing.CONVEX_DEPLOYMENT) {
    console.log(`Reusing existing deployment: ${existing.CONVEX_DEPLOYMENT}`);
  }

  const { cmd, leading } = npxInvoker();
  await new Promise<void>((resolvePromise, reject) => {
    const child = spawn(cmd, [...leading, ...convexArgs], { stdio: "inherit", cwd: ROOT });
    child.on("exit", (code) =>
      code === 0 ? resolvePromise() : reject(new Error(`convex dev exited ${code}`)),
    );
    child.on("error", reject);
  });
}

function hasBinary(name: string): Promise<boolean> {
  return new Promise((ok) => {
    const lookup = process.platform === "win32" ? "where" : "which";
    const child = spawn(lookup, [name], { stdio: "ignore" });
    child.on("exit", (code) => ok(code === 0));
    child.on("error", () => ok(false));
  });
}

// ngrok stores its config (including the authtoken) at a platform-specific path.
function ngrokConfigPath(): string {
  const home = process.env.HOME ?? process.env.USERPROFILE ?? "";
  if (process.platform === "darwin")
    return resolve(home, "Library/Application Support/ngrok/ngrok.yml");
  if (process.platform === "win32")
    return resolve(process.env.LOCALAPPDATA ?? home, "ngrok/ngrok.yml");
  return resolve(home, ".config/ngrok/ngrok.yml");
}

function ngrokHasAuthtoken(): boolean {
  const p = ngrokConfigPath();
  if (!existsSync(p)) return false;
  return /^\s*authtoken:\s*\S+/m.test(readFileSync(p, "utf8"));
}

// Install ngrok if missing. macOS uses Homebrew; other platforms get
// printed instructions since there's no consistent package manager. Returns
// true if ngrok is available on PATH after this call.
async function installNgrokIfNeeded(): Promise<boolean> {
  if (await hasBinary("ngrok")) return true;

  console.log(`\nngrok isn't installed.`);
  if (process.platform === "darwin" && (await hasBinary("brew"))) {
    const { proceed } = await prompts({
      type: "confirm",
      name: "proceed",
      message: "Install ngrok now via Homebrew (brew install ngrok)?",
      initial: true,
    });
    if (proceed) {
      try {
        await runInherit("brew", ["install", "ngrok"]);
      } catch (err) {
        console.log(`\n⚠ brew install failed: ${err}`);
      }
      if (await hasBinary("ngrok")) return true;
    }
  } else if (process.platform === "darwin") {
    console.log(`Homebrew isn't installed either. Install Homebrew from https://brew.sh, then re-run setup.`);
  } else {
    console.log(`Download ngrok for your platform: https://ngrok.com/download`);
    console.log(`After installing, re-run setup.`);
  }
  return false;
}

// Authenticate ngrok with a free token if not already done.
async function setupNgrokAuthtokenIfNeeded(): Promise<void> {
  if (ngrokHasAuthtoken()) {
    console.log(`✓ ngrok already authenticated.`);
    return;
  }
  console.log(`\nngrok needs a free authtoken to start tunnels.`);
  const { proceed } = await prompts({
    type: "confirm",
    name: "proceed",
    message: "Open the ngrok dashboard and paste a token now?",
    initial: true,
  });
  if (!proceed) {
    console.log(
      `\nSkipped. Get a free token at https://dashboard.ngrok.com/get-started/your-authtoken\n  then run: ngrok config add-authtoken <token>`,
    );
    return;
  }
  const url = "https://dashboard.ngrok.com/get-started/your-authtoken";
  console.log(`\nOpening ${url}`);
  openInBrowser(url);
  const { token } = await prompts({
    type: "password",
    name: "token",
    message: "Paste your ngrok authtoken (leave blank to skip):",
    initial: "",
  });
  if (!token) {
    console.log(
      `\nSkipped. Run \`ngrok config add-authtoken <token>\` later when you have one.`,
    );
    return;
  }
  try {
    await runInherit("ngrok", ["config", "add-authtoken", String(token).trim()]);
    console.log(`✓ ngrok authtoken saved.`);
  } catch (err) {
    console.log(`\n⚠ Failed to save authtoken: ${err}`);
  }
}

function openInBrowser(url: string): void {
  const cmd =
    process.platform === "darwin"
      ? "open"
      : process.platform === "win32"
        ? "start"
        : "xdg-open";
  try {
    spawn(cmd, [url], { stdio: "ignore", detached: true }).unref();
  } catch {
    /* ignore — fall back to the printed URL */
  }
}

function runInherit(cmd: string, args: string[]): Promise<void> {
  return new Promise((ok, fail) => {
    const child = spawn(cmd, args, { stdio: "inherit", cwd: ROOT });
    child.on("exit", (code) =>
      code === 0 ? ok() : fail(new Error(`${cmd} ${args.join(" ")} exited ${code}`)),
    );
    child.on("error", fail);
  });
}

function runCapture(cmd: string, args: string[]): Promise<string> {
  return new Promise((ok, fail) => {
    const child = spawn(cmd, args, { stdio: ["inherit", "pipe", "pipe"], cwd: ROOT });
    let out = "";
    child.stdout.on("data", (d) => {
      const s = d.toString();
      out += s;
      process.stdout.write(s);
    });
    child.stderr.on("data", (d) => process.stderr.write(d));
    child.on("exit", (code) =>
      code === 0 ? ok(out) : fail(new Error(`${cmd} exited ${code}`)),
    );
    child.on("error", fail);
  });
}

async function sendblueInvoker(): Promise<{ cmd: string; leading: string[] }> {
  if (await hasBinary("sendblue")) return { cmd: "sendblue", leading: [] };
  const { cmd, leading } = npxInvoker();
  return { cmd, leading: [...leading, "@sendblue/cli"] };
}

interface SendblueKeys {
  apiKey?: string;
  apiSecret?: string;
  fromNumber?: string;
}

function parseSendblueKeys(output: string): SendblueKeys {
  const clean = output.replace(/\x1b\[[0-9;]*m/g, "");
  const keys: SendblueKeys = {};

  try {
    const json = JSON.parse(clean);
    if (json.api_key_id || json.apiKeyId) keys.apiKey = json.api_key_id ?? json.apiKeyId;
    if (json.api_secret_key || json.apiSecretKey)
      keys.apiSecret = json.api_secret_key ?? json.apiSecretKey;
    if (json.phone_number || json.phoneNumber)
      keys.fromNumber = json.phone_number ?? json.phoneNumber;
    if (keys.apiKey && keys.apiSecret) return keys;
  } catch {
    /* not json, fall through to text parsing */
  }

  const idMatch = clean.match(
    /(?:API[- ]?Key[- ]?ID|sb[- ]?api[- ]?key[- ]?id|api_key_id|Key Id|API[- ]?Key)[:\s]+\"?([A-Za-z0-9_-]{16,})/i,
  );
  const secretMatch = clean.match(
    /(?:Secret[- ]?Key|API[- ]?Secret|sb[- ]?api[- ]?secret[- ]?key|api_secret|Secret)[:\s]+\"?([A-Za-z0-9_-]{16,})/i,
  );
  const numMatch = clean.match(
    /(?:Phone[- ]?Number|From[- ]?Number|number)[:\s]+\"?(\+?\d{10,15})/i,
  );

  if (idMatch) keys.apiKey = idMatch[1];
  if (secretMatch) keys.apiSecret = secretMatch[1];
  if (numMatch) keys.fromNumber = numMatch[1];
  return keys;
}

function parseSendbluePhones(output: string): string[] {
  const clean = output.replace(/\x1b\[[0-9;]*m/g, "");
  const seen = new Set<string>();
  const numbers: string[] = [];

  try {
    const json = JSON.parse(clean);
    const lines = Array.isArray(json) ? json : (json.lines ?? json.numbers ?? []);
    for (const entry of lines) {
      const n = entry?.phone_number ?? entry?.phoneNumber ?? entry?.number ?? entry;
      if (typeof n === "string" && /^\+?\d{10,15}$/.test(n.replace(/[^\d+]/g, ""))) {
        const norm = n.startsWith("+") ? n : `+${n}`;
        if (!seen.has(norm)) {
          seen.add(norm);
          numbers.push(norm);
        }
      }
    }
    if (numbers.length) return numbers;
  } catch {
    /* not JSON, fall through to text parsing */
  }

  // `sendblue lines` formats like "+1 (305) 336-9541".
  for (const rawLine of clean.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line.startsWith("+")) continue;
    const match = line.match(/^\+[\d ()\-.]{9,25}/);
    if (!match) continue;
    const e164 = "+" + match[0].replace(/\D/g, "");
    if (/^\+\d{10,15}$/.test(e164) && !seen.has(e164)) {
      seen.add(e164);
      numbers.push(e164);
    }
  }
  return numbers;
}

async function importSendblueFromCli(): Promise<SendblueKeys | null> {
  const { method } = await prompts(
    {
      type: "select",
      name: "method",
      message: "How do you want to configure Sendblue?",
      choices: [
        { title: "Use the Sendblue CLI (I'll run it — fastest)", value: "cli" },
        { title: "Paste my API keys manually", value: "manual" },
        { title: "Skip for now", value: "skip" },
      ],
      initial: 0,
    },
    {
      onCancel: () => {
        console.log("Setup cancelled.");
        process.exit(1);
      },
    },
  );

  if (method === "manual") return null;
  if (method === "skip") return { apiKey: "", apiSecret: "", fromNumber: "" };

  const { account } = await prompts({
    type: "select",
    name: "account",
    message: "Do you already have a Sendblue account?",
    choices: [
      { title: "Yes — log in", value: "login" },
      { title: "No — create one with `sendblue setup`", value: "setup" },
    ],
    initial: 0,
  });

  const { cmd, leading } = await sendblueInvoker();

  banner("Sendblue CLI");
  try {
    await runInherit(cmd, [...leading, account === "setup" ? "setup" : "login"]);
    console.log("\nFetching your Sendblue keys…\n");
    const output = await runCapture(cmd, [...leading, "show-keys"]);
    const parsed = parseSendblueKeys(output);
    if (!parsed.apiKey || !parsed.apiSecret) {
      console.log(
        `\nCouldn't auto-parse keys from the CLI output. I'll ask for them below — copy/paste from the output above.`,
      );
      return null;
    }
    console.log(`\n✓ Pulled your Sendblue keys from the CLI.`);

    // `show-keys` doesn't include the phone number — it lives in `sendblue lines`.
    if (!parsed.fromNumber) {
      try {
        console.log("\nFetching your provisioned number…\n");
        const linesOutput = await runCapture(cmd, [...leading, "lines"]);
        const phones = parseSendbluePhones(linesOutput);
        if (phones.length === 1) {
          parsed.fromNumber = phones[0];
          console.log(`\n✓ Using ${phones[0]} as SENDBLUE_FROM_NUMBER.`);
        } else if (phones.length > 1) {
          const { pickedNumber } = await prompts({
            type: "select",
            name: "pickedNumber",
            message: "You have multiple Sendblue numbers — which one should Boop reply from?",
            choices: phones.map((p) => ({ title: p, value: p })),
            initial: 0,
          });
          if (pickedNumber) parsed.fromNumber = pickedNumber;
        } else {
          console.log(
            `\n⚠ No provisioned numbers found in \`sendblue lines\`. I'll ask for one below.`,
          );
        }
      } catch (err) {
        console.log(`\n⚠ \`sendblue lines\` failed: ${err}. I'll ask for the number below.`);
      }
    }
    return parsed;
  } catch (err) {
    console.log(`\n⚠ Sendblue CLI failed: ${err}`);
    console.log(`Falling back to manual prompts.`);
    return null;
  }
}

async function main() {
  banner("boop-agent setup");

  console.log(`
What this does:
  1. Pulls your Sendblue keys (via their CLI, or you paste them)
  2. Asks about your Claude model preference
  3. Runs \`npx convex dev\` to create a Convex project
  4. Writes .env.local

Before you start:
  • A Claude Code subscription:    https://claude.com/code
  • Convex account (free tier):    https://convex.dev
  • Sendblue (free on agent plan): https://sendblue.com
`);

  const existing = readEnv(ENV_PATH);
  const cli = await importSendblueFromCli();

  const sendblueDefaults = {
    SENDBLUE_API_KEY: cli?.apiKey ?? existing.SENDBLUE_API_KEY ?? "",
    SENDBLUE_API_SECRET: cli?.apiSecret ?? existing.SENDBLUE_API_SECRET ?? "",
    SENDBLUE_FROM_NUMBER: cli?.fromNumber ?? existing.SENDBLUE_FROM_NUMBER ?? "",
  };

  const sendbluePrompts = [] as any[];
  if (!sendblueDefaults.SENDBLUE_API_KEY) {
    sendbluePrompts.push({
      type: "text",
      name: "SENDBLUE_API_KEY",
      message: "Sendblue API key id (sb-api-key-id value)",
      initial: "",
    });
  }
  if (!sendblueDefaults.SENDBLUE_API_SECRET) {
    sendbluePrompts.push({
      type: "password",
      name: "SENDBLUE_API_SECRET",
      message: "Sendblue API secret",
      initial: "",
    });
  }
  if (!sendblueDefaults.SENDBLUE_FROM_NUMBER) {
    sendbluePrompts.push({
      type: "text",
      name: "SENDBLUE_FROM_NUMBER",
      message:
        "Your Sendblue-provisioned number (the one people text TO, e.g. +14695551234). Required by Sendblue.",
      initial: "",
    });
  }

  const answers = await prompts(
    [
      ...sendbluePrompts,
      {
        type: "select",
        name: "BOOP_MODEL",
        message: "Which Claude model should the agent use?",
        choices: [
          { title: "claude-sonnet-4-6 (recommended)", value: "claude-sonnet-4-6" },
          { title: "claude-opus-4-6 (slowest, most capable)", value: "claude-opus-4-6" },
          { title: "claude-haiku-4-5 (fastest, cheapest)", value: "claude-haiku-4-5" },
        ],
        initial: 0,
      },
      {
        type: "text",
        name: "PORT",
        message: "Local server port",
        initial: existing.PORT ?? "3456",
      },
      {
        type: "confirm",
        name: "runConvex",
        message: "Run `convex dev` now to configure your Convex deployment?",
        initial: true,
      },
    ],
    {
      onCancel: () => {
        console.log("Setup cancelled.");
        process.exit(1);
      },
    },
  );

  // Merge CLI-sourced defaults with what the user answered (answer wins).
  Object.assign(answers, {
    SENDBLUE_API_KEY: answers.SENDBLUE_API_KEY ?? sendblueDefaults.SENDBLUE_API_KEY,
    SENDBLUE_API_SECRET: answers.SENDBLUE_API_SECRET ?? sendblueDefaults.SENDBLUE_API_SECRET,
    SENDBLUE_FROM_NUMBER: answers.SENDBLUE_FROM_NUMBER ?? sendblueDefaults.SENDBLUE_FROM_NUMBER,
  });

  // ---- Composio API key ---------------------------------------------------
  banner("Composio — integrations (Gmail, Slack, GitHub, Linear, 1000+ more)");
  const composioSettingsUrl = "https://platform.composio.dev/settings";
  const existingComposio = existing.COMPOSIO_API_KEY ?? "";
  const { composioMode } = await prompts(
    {
      type: "select",
      name: "composioMode",
      message: existingComposio
        ? "Composio API key detected. Keep it or replace?"
        : "Configure Composio now? (needed to connect any integration)",
      choices: existingComposio
        ? [
            { title: "Keep existing key", value: "keep" },
            { title: "Replace (opens the Composio dashboard)", value: "replace" },
            { title: "Skip", value: "skip" },
          ]
        : [
            { title: "Yes — open the Composio dashboard and paste my key", value: "replace" },
            { title: "Skip for now", value: "skip" },
          ],
      initial: 0,
    },
    {
      onCancel: () => {
        console.log("Setup cancelled.");
        process.exit(1);
      },
    },
  );

  if (composioMode === "replace") {
    console.log(`\nOpening ${composioSettingsUrl} — grab your API key there.`);
    console.log(`(If the browser doesn't open, copy the URL above.)\n`);
    openInBrowser(composioSettingsUrl);
    const { COMPOSIO_API_KEY } = await prompts(
      {
        type: "password",
        name: "COMPOSIO_API_KEY",
        message: "Paste your Composio API key (leave blank to skip):",
        initial: "",
      },
      {
        onCancel: () => {
          console.log("Setup cancelled.");
          process.exit(1);
        },
      },
    );
    (answers as any).COMPOSIO_API_KEY = COMPOSIO_API_KEY || existingComposio;
  } else if (composioMode === "keep") {
    (answers as any).COMPOSIO_API_KEY = existingComposio;
  } else {
    (answers as any).COMPOSIO_API_KEY = existingComposio;
    console.log(
      `\nSkipped. Add COMPOSIO_API_KEY to .env.local later to enable integrations.`,
    );
  }

  // ---- Embedding provider --------------------------------------------------
  banner("Memory search — embedding provider");
  const existingVoyage = existing.VOYAGE_API_KEY ?? "";
  const existingOpenai = existing.OPENAI_API_KEY ?? "";
  const inferredCurrent = existingVoyage
    ? "voyage"
    : existingOpenai
      ? "openai"
      : "local";
  console.log(`
Boop's recall() searches your stored memories by semantic similarity. Pick
how you want to generate embeddings:

  • Local  — free, runs in-process via @huggingface/transformers
            (Xenova/bge-large-en-v1.5, 1024-dim). First run downloads
            ~440MB and caches forever. No API key.
  • Voyage — paid, ~$0.06/M tokens. Slightly stronger English retrieval.
  • OpenAI — paid, ~$0.13/M tokens. Comparable to Voyage.

All three produce 1024-dim vectors (compatible with the same Convex index)
so you can switch later by adding/removing the API key.
`);
  const { embeddingProvider } = await prompts(
    {
      type: "select",
      name: "embeddingProvider",
      message: "Which embedding provider should boop use?",
      choices: [
        { title: "Local (free, recommended)", value: "local" },
        { title: "Voyage (paid — I have a key)", value: "voyage" },
        { title: "OpenAI (paid — I have a key)", value: "openai" },
      ],
      initial:
        inferredCurrent === "voyage" ? 1 : inferredCurrent === "openai" ? 2 : 0,
    },
    {
      onCancel: () => {
        console.log("Setup cancelled.");
        process.exit(1);
      },
    },
  );

  if (embeddingProvider === "voyage") {
    const { VOYAGE_API_KEY } = await prompts({
      type: "password",
      name: "VOYAGE_API_KEY",
      message: "Paste your Voyage API key (https://dash.voyageai.com):",
      initial: existingVoyage,
    });
    (answers as any).VOYAGE_API_KEY = VOYAGE_API_KEY || "";
    (answers as any).OPENAI_API_KEY = "";
    if (VOYAGE_API_KEY) {
      console.log(`\n  Heads up: Voyage's free tier rate-limits accounts WITHOUT a payment
  method on file to 3 RPM / 10K TPM — fine for chat, but bulk operations
  hit it instantly. Adding a card at
  https://dashboard.voyageai.com/organization/billing keeps you on the
  200M free tokens but unlocks normal rate limits.`);
    }
  } else if (embeddingProvider === "openai") {
    const { OPENAI_API_KEY } = await prompts({
      type: "password",
      name: "OPENAI_API_KEY",
      message: "Paste your OpenAI API key:",
      initial: existingOpenai,
    });
    (answers as any).OPENAI_API_KEY = OPENAI_API_KEY || "";
    (answers as any).VOYAGE_API_KEY = "";
  } else {
    // Local — clear any stale paid keys so embeddings.ts falls through to
    // the local provider on next start.
    (answers as any).VOYAGE_API_KEY = "";
    (answers as any).OPENAI_API_KEY = "";

    const { preload } = await prompts({
      type: "confirm",
      name: "preload",
      message:
        "Pre-download the local model now? (~440MB, ~30s on broadband — saves the wait on first recall)",
      initial: true,
    });
    if (preload) {
      console.log("\nDownloading Xenova/bge-large-en-v1.5… (Ctrl+C to skip)\n");
      try {
        await runInherit("npx", ["tsx", "scripts/preload-embeddings.ts"]);
        console.log("✓ Local model cached.");
      } catch (err) {
        console.warn(
          "Preload failed — model will download on first recall instead.",
          err instanceof Error ? err.message : err,
        );
      }
    }
  }

  // ---- Tunnel configuration ------------------------------------------------
  banner("Tunnel — public URL for Sendblue to reach your server");
  console.log(`
ngrok's FREE plan gives you a NEW public URL every restart, which means
re-pasting into Sendblue every time. For a stable URL, pick one of:

  1. Free ngrok             (fine for testing / demos — re-paste each restart)
  2. ngrok RESERVED domain  (paid — stays the same across restarts)
  3. Cloudflare Tunnel / other static tunnel you set up yourself
`);

  const { tunnelChoice } = await prompts(
    {
      type: "select",
      name: "tunnelChoice",
      message: "Which option are you using?",
      choices: [
        { title: "Free ngrok — I'll paste a new URL each restart", value: "free" },
        { title: "ngrok reserved domain (paid)", value: "ngrok-domain" },
        { title: "Cloudflare Tunnel or another stable URL", value: "static" },
      ],
      initial: 0,
    },
    {
      onCancel: () => {
        console.log("Setup cancelled.");
        process.exit(1);
      },
    },
  );

  if (tunnelChoice === "ngrok-domain") {
    const { NGROK_DOMAIN } = await prompts({
      type: "text",
      name: "NGROK_DOMAIN",
      message: "Your ngrok reserved domain (e.g. boop.ngrok.app, no https://):",
      initial: existing.NGROK_DOMAIN ?? "",
    });
    const clean = (NGROK_DOMAIN ?? "").replace(/^https?:\/\//, "").replace(/\/$/, "");
    if (clean) {
      (answers as any).NGROK_DOMAIN = clean;
      (answers as any).PUBLIC_URL = `https://${clean}`;
    }
  } else if (tunnelChoice === "static") {
    const { PUBLIC_URL } = await prompts({
      type: "text",
      name: "PUBLIC_URL",
      message: "Your stable public URL (e.g. https://boop.mydomain.com):",
      initial: existing.PUBLIC_URL ?? "",
    });
    if (PUBLIC_URL) {
      (answers as any).PUBLIC_URL = PUBLIC_URL.replace(/\/$/, "");
      (answers as any).NGROK_DOMAIN = "";
    }
  } else {
    // free ngrok — clear any stale domain and keep PUBLIC_URL at the localhost default
    (answers as any).NGROK_DOMAIN = "";
  }

  // Install + authenticate ngrok now if the user picked an ngrok-based tunnel.
  // Without this, `npm run dev` would print install hints and run without a
  // public URL, breaking iMessage replies until the user fixes it manually.
  if (tunnelChoice === "free" || tunnelChoice === "ngrok-domain") {
    banner("ngrok — install + authenticate");
    const installed = await installNgrokIfNeeded();
    if (installed) await setupNgrokAuthtokenIfNeeded();
  }

  const env: Record<string, string> = { ...existing, ...answers };
  delete (env as any).runConvex;
  if (!env.PUBLIC_URL) env.PUBLIC_URL = `http://localhost:${env.PORT ?? "3456"}`;
  // Clear stale / stub Convex values so `convex dev` can populate them freshly.
  // (`convex dev` uses .convex/ to identify the deployment, not these env vars.)
  if (env.CONVEX_URL?.includes("example.convex.cloud")) delete env.CONVEX_URL;
  if (env.VITE_CONVEX_URL?.includes("example.convex.cloud")) delete env.VITE_CONVEX_URL;
  writeEnv(ENV_PATH, env);

  // Convex's CLI bails with "Found multiple ... environment variables in
  // .env.local" when more than one key from its expected set
  // (CONVEX_URL, VITE_CONVEX_URL, NEXT_PUBLIC_CONVEX_URL, ...) is present —
  // even if all are empty. Our .env.example lists both CONVEX_URL and
  // VITE_CONVEX_URL, so writeEnv emits both as empty placeholders. Strip
  // VITE_CONVEX_URL before `convex dev` runs so it sees a single matching
  // key; the post-convex sync below restores VITE_CONVEX_URL with the real
  // deployment URL.
  if (answers.runConvex) cleanConvexUrlEnv(ENV_PATH);

  banner("Claude authentication");
  console.log(`This project uses your Claude Code subscription — no Anthropic API key needed.

If you haven't already:
  • Install Claude Code:  npm install -g @anthropic-ai/claude-code
  • Run once:              claude
  • Sign in when prompted

The Claude Agent SDK reads the credentials Claude Code saves on disk.
You can override with ANTHROPIC_API_KEY in .env.local if you'd rather use an API key.
`);

  if (answers.runConvex) {
    await runConvexDev();
    const after = readEnv(ENV_PATH);

    // CONVEX_URL or VITE_CONVEX_URL is written to .env.local as part of `convex dev`; derive CONVEX_URL from it
    // if not available, fallback to deriving from CONVEX_DEPLOYMENT.
    const deploymentMatch =
      after.CONVEX_DEPLOYMENT?.match(/^([a-z]+):([\w-]+)/);

    if (deploymentMatch) {
      const url =
        after.CONVEX_URL ||
        after.VITE_CONVEX_URL ||
        `https://${deploymentMatch[2]}.convex.cloud`;
      if (after.CONVEX_URL !== url || after.VITE_CONVEX_URL !== url) {
        writeEnv(ENV_PATH, {
          ...after,
          CONVEX_URL: url,
          VITE_CONVEX_URL: url,
        });
        console.log(`\n✓ Synced CONVEX_URL + VITE_CONVEX_URL → ${url}`);
      }
    }
  } else {
    console.log("\nSkipped Convex. Run `npx convex dev` yourself when ready.");
  }

  const port = answers.PORT ?? "3456";
  banner("You're set up. Here's how to actually run it.");
  console.log(`
Run ONE command:

  npm run dev

That starts the server, Convex watcher, debug dashboard, AND ngrok all
together — color-prefixed output so you can tell who's saying what. Once
the tunnel is live, you'll see a banner with your public URL${
    tunnelChoice === "free"
      ? ", and the\nSendblue inbound webhook gets registered automatically."
      : "."
  }

Test it:
  • Open http://localhost:5173 for the debug dashboard (Chat tab works
    without Sendblue).
  • Or text your Sendblue number from a different phone. The agent replies.

${
  tunnelChoice === "free"
    ? `⚠ Free ngrok gives you a NEW URL every restart. The webhook auto-registers
  with Sendblue each time, so it Just Works for dev — but for anything
  beyond a demo, use a stable URL (\`npm run setup\` → ngrok reserved
  domain, or Cloudflare Tunnel).

`
    : ""
}Gotcha to double-check:
  SENDBLUE_FROM_NUMBER in .env.local must be your Sendblue-provisioned
  number (the one people text TO), NOT your personal cell. Sendblue
  rejects sends with "Cannot send messages to self" or "missing required
  parameter: from_number" otherwise.

Integrations (via Composio):
  1. Open http://localhost:5173 → Connections tab once dev is running.
  2. Click Connect on any toolkit (Gmail, Slack, GitHub, Linear, Notion, …).
  3. Composio handles OAuth; the toolkit becomes available to the agent.

Memory backfill (if you switch embedding providers later, the debug UI's
EmbeddingBanner will offer to re-embed records that have stale or
missing vectors):

  http://localhost:5173 → Memory tab
`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
