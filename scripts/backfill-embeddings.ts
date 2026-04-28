#!/usr/bin/env tsx
// Re-embed memoryRecords that were saved before an embeddings provider was
// configured. Idempotent — only touches records whose embedding is missing
// or empty. Run after setting VOYAGE_API_KEY (or OPENAI_API_KEY) in
// .env.local:  npm run backfill-embeddings

import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Load .env.local before importing modules that read process.env at import
// time (server/convex-client.ts throws if CONVEX_URL is missing).
const here = dirname(fileURLToPath(import.meta.url));
const envPath = resolve(here, "..", ".env.local");
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*?)(?:\s+#.*)?$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim();
  }
}

const { api } = await import("../convex/_generated/api.js");
const { convex } = await import("../server/convex-client.js");
const { embed, embeddingsAvailable } = await import("../server/embeddings.js");

if (!embeddingsAvailable()) {
  console.error(
    "No embeddings provider configured. Set VOYAGE_API_KEY or OPENAI_API_KEY in .env.local first.",
  );
  process.exit(1);
}

const BATCH = 200;
let totalSucceeded = 0;
let totalFailed = 0;
let totalScanned = 0;

for (const lifecycle of ["active", "archived"] as const) {
  console.log(`\nScanning ${lifecycle} records for missing embeddings…`);
  // Loop until the query returns 0 — each pass refreshes since we patched
  // earlier rows out of the "no embedding" set.
  while (true) {
    const records = await convex.query(api.memoryRecords.withoutEmbedding, {
      lifecycle,
      limit: BATCH,
    });
    if (records.length === 0) break;
    totalScanned += records.length;
    console.log(`  batch: ${records.length} records`);

    for (const r of records) {
      try {
        const vec = await embed(r.content);
        if (!vec) {
          console.warn(`    ✗ ${r.memoryId}: embed() returned null`);
          totalFailed++;
          continue;
        }
        await convex.mutation(api.memoryRecords.setEmbedding, {
          memoryId: r.memoryId,
          embedding: vec,
        });
        totalSucceeded++;
      } catch (err) {
        console.warn(
          `    ✗ ${r.memoryId}:`,
          err instanceof Error ? err.message : String(err),
        );
        totalFailed++;
      }
    }
  }
}

console.log(
  `\nDone. scanned=${totalScanned} succeeded=${totalSucceeded} failed=${totalFailed}`,
);
process.exit(totalFailed > 0 ? 1 : 0);
