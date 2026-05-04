---
name: obscura-scraper-crawler
description: >
  Extract web pages into structured Markdown using the obscura headless-browser
  binary with stealth on by default. Use when the user says "use obscura,"
  "scrape with stealth," "this site has a bot wall," "Cloudflare blocks the
  normal scraper," or when the default extract-webpage skill returned a
  challenge page or empty content. Single pages or full-site crawls. For
  default URL extraction, prefer extract-webpage. For YouTube use
  extract-transcript. For PDFs use extract-book or extract-study.
---

# Obscura-rendered Web Page to Structured Markdown

Sister skill to extract-webpage. Same Markdown output format, same metadata block, same crawl semantics -- but every fetch goes through the [obscura](https://github.com/h4ckf0r0day/obscura) headless browser with stealth on by default. There is no fetcher cascade: obscura renders every page, period.

The script runs `obscura serve --stealth` once at the top of a run and connects to it via Playwright's `chromium.connect_over_cdp(...)`. One obscura process backs the whole crawl, cookies persist across pages, and Playwright provides the navigation API (auto-wait, selectors). Stealth's bot-tell patches happen inside obscura before Playwright touches the page, verified -- `navigator.webdriver` is `undefined`, the UA reports `Chrome/145.0.0.0` with no "HeadlessChrome", and `window.chrome` is present.

Use this when extract-webpage's static cascade (trafilatura -> curl -> Playwright) returned a Cloudflare challenge page, an empty SPA shell, or sparse content. Obscura's stealth mode patches the rendered browser to avoid the most common bot tells (`navigator.webdriver = undefined`, realistic `navigator.userAgentData`, per-session fingerprint randomization, native-function masking) and blocks 3,520 known tracker domains. It defeats most passive client-side bot checks. It does NOT defeat active interstitials with behavioral analysis (Cloudflare Turnstile, hCaptcha, JS challenges).

The output is byte-compatible with extract-webpage's so the two can be A/B compared on the same URL.

## When to Use

- The user explicitly says "use obscura," "scrape with stealth," "try the obscura skill"
- A previous extract-webpage run returned a "checking your browser" stub, a Turnstile shell, or word counts well below what the page actually contains
- The user mentions a site behind Cloudflare or another WAF with bot-blocking
- The user is hitting a JS-rendered SPA where extract-webpage's Playwright path returns the unhydrated app shell

Do NOT use for:
- Default URL extraction (use `extract-webpage` -- it's faster and lighter, and most pages don't need stealth)
- YouTube videos (use `extract-transcript`)
- PDF files (use `extract-book` or `extract-study`)
- Pages behind login walls or paywalls (stealth doesn't bypass authentication)

## Setup

The script needs both Python packages and the obscura binary.

```bash
source .venv/bin/activate && pip install trafilatura readability-lxml markdownify lxml playwright
```

`playwright` connects to obscura over CDP, so you do NOT need to run `playwright install` -- there's no Chromium download. The Python wrapper uses a small Node.js driver that ships with the pip package; that's enough to talk WebSocket to obscura.

Then download the obscura binary from https://github.com/h4ckf0r0day/obscura/releases and put it on PATH:

```bash
# macOS Apple Silicon
curl -LO https://github.com/h4ckf0r0day/obscura/releases/latest/download/obscura-aarch64-macos.tar.gz
tar xzf obscura-aarch64-macos.tar.gz && sudo mv obscura /usr/local/bin/

# macOS Intel
curl -LO https://github.com/h4ckf0r0day/obscura/releases/latest/download/obscura-x86_64-macos.tar.gz
tar xzf obscura-x86_64-macos.tar.gz && sudo mv obscura /usr/local/bin/

# Linux x86_64
curl -LO https://github.com/h4ckf0r0day/obscura/releases/latest/download/obscura-x86_64-linux.tar.gz
tar xzf obscura-x86_64-linux.tar.gz && sudo mv obscura /usr/local/bin/

# Windows: download the .zip from the releases page and put obscura.exe on PATH.
```

Verify with `obscura --help` (obscura has no `--version` flag; `--help` should print the usage banner with `serve`, `fetch`, and `scrape` subcommands). No Playwright, no Chromium -- obscura ships its own browser.

**No-sudo alternative:** if you don't want to `sudo mv` to `/usr/local/bin/`, drop the binary anywhere on your PATH (e.g., `~/.local/bin/` or `~/bin/`), or pass `--obscura-binary /path/to/obscura` to the script every invocation.

**macOS Gatekeeper:** if you downloaded the tarball via a browser instead of `curl`, the binary picks up the `com.apple.quarantine` extended attribute and macOS will kill it on first launch (exit 137, no useful error). Clear it with `xattr -d com.apple.quarantine /path/to/obscura`. The `curl -LO` install above sidesteps this -- curl doesn't apply quarantine.

If the binary isn't on PATH when the script runs, it exits at second 0 with the platform-matching install command. Pass `--obscura-binary /path/to/obscura` to point at a non-PATH location.

## Process

### Step 1: Dry Run

Always start with a dry run to confirm obscura can fetch the page and that stealth flags are set as expected:

```bash
source .venv/bin/activate && python {SKILL_DIR}/scripts/obscura_scraper.py "<url>" --dry-run
```

Reports detected title, author, date, site name, description, word count, and the stealth/wait-until state. For crawl mode, add `--crawl` to also list the discovered pages.

If the dry run reports under 50 words, the real run will try the Readability fallback. If that also returns little, the page may be serving an active interstitial that defeats stealth (Turnstile, hCaptcha) or genuinely lack readable prose.

### Step 2: Extract

**Single page:**
```bash
source .venv/bin/activate && python {SKILL_DIR}/scripts/obscura_scraper.py "<url>" -o "<output-path>.md"
```

**Full site:**
```bash
source .venv/bin/activate && python {SKILL_DIR}/scripts/obscura_scraper.py "<url>" --crawl -o "<output-path>.md"
```

The `--crawl` flag discovers pages on the same domain (sitemap via curl first, then -- if no sitemap -- a rendered fetch of the start page and DOM link harvest) and extracts each one through obscura, combining them into a single document with a table of contents. 1-second delay between requests by default (`--delay` to adjust). `--max-pages` caps the crawl (default: 50).

**Path scoping (default):** when the start URL has a non-root path like `/docs` or `/blog`, the crawl follows only links whose path starts with the same top-level segment. Crawling `https://example.com/docs` discovers `/docs/intro` and `/docs/api` but ignores `/about` or `/pricing`. Pass `--no-scope` to follow any same-domain link.

The script also filters out generic non-content URLs when crawling (tag pages, category pages, login pages, etc.). Override with `--exclude /pattern1/ /pattern2/` or disable with `--no-exclude`.

Other flags:
- `--no-stealth` opt out of stealth (rare -- the whole point of this skill is stealth on)
- `--wait-until {load,domcontentloaded,networkidle0}` obscura wait condition (default: `domcontentloaded`). Use `networkidle0` for sites that need late-loading content; it's slower and may time out on SPAs with persistent connections
- `--obscura-wait N` extra seconds to settle after `wait_until` fires (obscura's `--wait`). Use when stealth alone isn't clearing a slow-rendering challenge
- `--obscura-selector CSS` wait for a CSS selector to appear after `wait_until` (obscura's `--selector`). Use to wait for the real content container rather than the page shell
- `--obscura-binary PATH` override the `obscura` PATH lookup
- `--obscura-port N` override the auto-picked CDP port. Default behavior: pick a free port at runtime, no need to set this. Override only when something external needs to connect to the same obscura process
- `--no-links` strip hyperlinks from the output (cleaner for archival)
- `--include-images` add image references
- `--delay N` seconds between crawl requests (default: 1.0)
- `--exclude /path/ /path/` custom URL patterns to exclude when crawling
- `--no-exclude` disable default URL filtering (include everything)
- `--no-scope` disable path-scoped crawling; follow any same-domain link

### Step 3: Post-Process

After extraction, read the output and check:

1. **Title**: Auto-detected titles sometimes grab the site name instead of the article title, or include " | Site Name" suffixes. Fix the `# Title` line.

2. **Metadata block**: Verify the source URL, author, date, and site name. Fill in anything missing. The metadata block should contain:
   - **Author** (if identifiable)
   - **Site** (domain or publication name)
   - **Date** (publication date if detectable)
   - **Source** (the original URL -- mandatory)
   - **Scraped** (today's date)
   - **Description** (if the page has a meta description)

3. **Content quality**: Trafilatura strips boilerplate well, but occasionally keeps cookie banners, newsletter signup text, or related-article links. Remove these. Conversely, it sometimes strips content that looks like boilerplate but isn't (sidebars with relevant data, footnotes). Visit the URL to check whether anything important is missing.

4. **Structure**: The script preserves the page's heading hierarchy. If the original page had poor structure (all flat text, no headings), add section headings based on topic shifts. For multi-page crawls, each page becomes a `## Section` with its source URL noted.

5. **For multi-page crawls**: Review the table of contents. Remove pages that aren't useful (privacy policies, contact forms, 404s that slipped through). Reorder sections if the crawl order doesn't match logical reading order.

### Step 4: File It

Ask the user where to save it unless the project's CLAUDE.md or an existing folder convention makes it obvious. Match the filing pattern of neighboring documents if there is one.

**Filename:** Lowercase kebab-case -- `<author-or-site>-<short-slug>.md`.

- **`<author-or-site>`** is the named author when available, otherwise the site brand. "Peter Attia" -> `peter-attia`. When no named author, use the domain brand (e.g., `glyphosate-facts`).
- **`<short-slug>`** is a 3-6 word descriptive title. Keep the full page title in the `# H1` heading inside the file.
- **Normalize names:** strip to ASCII, lowercase, replace spaces with `-`, drop middle initials and apostrophes.

Examples: `peter-attia-metabolic-health-framework.md`, `glyphosate-facts-full-site.md`.

### Step 5: Cross-Reference

If the extracted page references studies, books, or videos already extracted in the project, add links in both directions. If it cites a study worth extracting, offer to run `extract-study` on it.

### Step 6: Commit

Add and commit with a descriptive message.

## Target Output Format

**Single page:**

```markdown
# Article Title

**Author:** Author Name
**Site:** Site Name
**Date:** 2026-01-15
**Source:** https://example.com/article
**Scraped:** 2026-04-21
**Description:** Brief description from meta tags

---

[clean article content in Markdown]
```

**Multi-page crawl:**

```markdown
# Site Name

**Source:** https://example.com/
**Author:** Author Name (if site-wide)
**Scraped:** 2026-04-21
**Description:** Site description

## Table of Contents

1. [Page Title](#page-title)
2. [Another Page](#another-page)
...

---

## Page Title

*URL: https://example.com/page-1*

[extracted content]

---

## Another Page

*URL: https://example.com/page-2*

[extracted content]

---
```

## Limitations

- **Authentication**: Cannot access pages behind login walls, paywalls, or CAPTCHAs. The session starts cold with no saved cookies; pages behind interactive auth are out of reach.
- **Active bot challenges**: Stealth defeats passive client-side fingerprint checks. It does not defeat Turnstile, hCaptcha, or any challenge that runs behavioral or server-side checks (mouse movement timing, JS challenges, IP/TLS reputation). If a site serves an active interstitial, the rendered HTML will be the challenge page and extraction will be sparse.
- **Rate limiting**: Some sites block rapid requests. The `--delay` flag helps; aggressive crawling may still get blocked. If extraction fails partway through a crawl, the script outputs what it collected.
- **Dynamic content**: Infinite-scroll pages and content that only loads on user interaction won't be captured. The rendered fetch waits for `wait_until` (and optionally a selector) but does not scroll or click. Try `--obscura-wait 5` or `--wait-until networkidle0` for late-loading content.
- **Speed**: Every page renders -- no static fast path. A 50-page crawl makes 50 page-load round-trips through one obscura process. If the target site is mostly static, extract-webpage is meaningfully faster.
- **One obscura per run**: A single `obscura serve` backs the whole run. A hang in obscura halts the whole crawl until Playwright's per-page timeout fires (60s default). Cookies and storage persist across pages within a run, so sites that set CDN routing cookies, A/B cohort assignments, or similar treat the crawl as one consistent visitor. (Earlier subprocess-per-page implementations had the inverse trade-off.)

## Troubleshooting

- **"obscura binary not found on PATH"**: Install from https://github.com/h4ckf0r0day/obscura/releases. The script's error message includes the platform-specific `curl` command. Or pass `--obscura-binary /path/to/obscura`.
- **macOS: obscura runs and immediately exits with code 137 (no other error)**: Gatekeeper killed it because the binary has the `com.apple.quarantine` extended attribute. Happens when you download via a browser instead of `curl`. Clear with `xattr -d com.apple.quarantine /path/to/obscura` and run again. The binary's existing ad-hoc signature satisfies the kernel; only quarantine triggers the kill.
- **"the 'playwright' Python package is required"**: Run `pip install playwright`. Do NOT run `playwright install` -- this skill connects to obscura over CDP, not to a local Chromium download.
- **"obscura serve didn't accept connections on port N within Ms"**: obscura started but didn't open the CDP port in time. Causes: the binary hangs (try a fresh download from releases), port conflict (the script auto-picks a free port by default; only specify `--obscura-port` if you have a reason), or stealth init crashed (try `--no-stealth` to isolate).
- **"obscura serve exited with code N"**: obscura died on startup with a stderr message in the error. Usually means the binary is corrupted, the wrong platform variant, or quarantined (see Gatekeeper note above).
- **obscura fetch timeout**: The page is loading too slowly for `domcontentloaded`. Try `--obscura-wait 5` (settle longer) or `--wait-until networkidle0` (wait for network silence). networkidle0 may itself time out on Mintlify/GitBook/Nextra sites that keep analytics websockets open forever.
- **Stealth still got blocked**: The site likely runs an active behavioral challenge that stealth doesn't defeat. Try `--obscura-wait 5 --obscura-selector "<real-content-selector>"` to give the challenge time to clear. If still blocked, the site is beyond what this skill can handle without a real browser session.
- **Empty extraction despite render**: Page may genuinely lack readable prose (single-app shell with no content), or be serving an interstitial. Check the URL in a real browser. If the obscura HTML is non-empty but extraction returns nothing, the page may have unusual structure -- the Readability fallback should catch it.
- **Crawl too slow**: Expected. Every page renders. Reduce `--max-pages`, raise `--delay` (counterintuitively reduces per-page wall time when sites rate-limit), or use extract-webpage if static fetching works for the target site.
- **Garbled text**: Encoding issues. trafilatura handles most cases, but some older sites with mixed encodings may produce artifacts. Check the original page's charset.
- **Missing sections on crawl**: The sitemap may not list all pages, and link discovery only follows `<a>` tags on the start page. For sites with deep navigation, run the script on specific sub-pages individually.
