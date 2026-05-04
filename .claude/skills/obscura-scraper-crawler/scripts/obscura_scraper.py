#!/usr/bin/env python3
"""Extract web page content to clean Markdown using the obscura headless browser.

Sister skill to extract-webpage. Same Markdown output format, same metadata
header, same crawl semantics -- but every fetch goes through `obscura fetch`
with stealth on by default. Use this when extract-webpage's static cascade
(trafilatura -> curl -> Playwright) returns a challenge page or empty content
on a Cloudflare/bot-walled site.

Single-page mode (default):
    python obscura_scraper.py "https://example.com/article" -o output.md

Multi-page crawl:
    python obscura_scraper.py "https://example.com/" --crawl -o output.md

Dry run (preview metadata only):
    python obscura_scraper.py "https://example.com/article" --dry-run
"""

import argparse
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

import trafilatura
from trafilatura.settings import use_config


# Below this word count, an extracted page is treated as too sparse to be
# meaningful. Used by the Readability fallback heuristic and by the dry-run
# reporter to flag suspect output.
RENDER_FALLBACK_THRESHOLD = 50

OBSCURA_RELEASES_URL = "https://github.com/h4ckf0r0day/obscura/releases"

# Curl ships on every macOS/Linux box and uses a TLS fingerprint Cloudflare
# doesn't block, unlike the Python `requests` library. We hand it a desktop UA
# so origins that gate on User-Agent return the full document. Used here only
# for sitemap.xml fetches -- routing static XML through obscura would mangle
# it through DOM rendering for no benefit.
_CURL_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_CURL_TIMEOUT_SECONDS = 30


def slugify(text: str) -> str:
    """Match GitHub's heading-anchor scheme: lowercase, drop non-word chars
    except spaces and hyphens, collapse spaces to hyphens."""
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s


def make_config():
    config = use_config()
    config.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")
    return config


# URL path segments that almost never contain article content.
# Used as default --exclude patterns when crawling.
_DEFAULT_EXCLUDE = [
    "/tag/", "/tags/", "/category/", "/categories/",
    "/author/", "/authors/", "/page/", "/feed/",
    "/wp-json/", "/wp-admin/", "/wp-login",
    "/cart", "/checkout", "/my-account",
    "/privacy-policy", "/terms-of-service", "/cookie-policy",
    "/search", "/login", "/register", "/signup",
]


def _default_exclude_patterns():
    return list(_DEFAULT_EXCLUDE)


class ObscuraMissing(Exception):
    """obscura binary not found on PATH or at --obscura-binary."""


class PlaywrightMissing(Exception):
    """playwright Python package not installed."""


class ObscuraServeFailed(Exception):
    """obscura serve died on startup or didn't accept connections in time."""


def _obscura_install_hint(binary_arg: str = "obscura") -> str:
    """Return a platform-specific install hint pointing at obscura's releases."""
    system = platform.system()
    machine = platform.machine().lower()
    lines = [
        f"ERROR: '{binary_arg}' binary not found on PATH.",
        "",
        "obscura-scraper-crawler requires the obscura headless browser binary.",
        f"Prebuilt releases: {OBSCURA_RELEASES_URL}",
        "",
    ]

    if system == "Darwin" and machine in ("arm64", "aarch64"):
        lines += [
            "Install (macOS Apple Silicon):",
            "  curl -LO https://github.com/h4ckf0r0day/obscura/releases/latest/download/obscura-aarch64-macos.tar.gz",
            "  tar xzf obscura-aarch64-macos.tar.gz",
            "  sudo mv obscura /usr/local/bin/",
        ]
    elif system == "Darwin":
        lines += [
            "Install (macOS Intel):",
            "  curl -LO https://github.com/h4ckf0r0day/obscura/releases/latest/download/obscura-x86_64-macos.tar.gz",
            "  tar xzf obscura-x86_64-macos.tar.gz",
            "  sudo mv obscura /usr/local/bin/",
        ]
    elif system == "Linux":
        lines += [
            "Install (Linux x86_64):",
            "  curl -LO https://github.com/h4ckf0r0day/obscura/releases/latest/download/obscura-x86_64-linux.tar.gz",
            "  tar xzf obscura-x86_64-linux.tar.gz",
            "  sudo mv obscura /usr/local/bin/",
        ]
    elif system == "Windows":
        lines += [
            "Install (Windows): download the .zip from the releases page above and",
            "place obscura.exe somewhere on PATH.",
        ]
    else:
        lines += [
            f"Detected platform: {system}/{machine}.",
            f"Download the matching binary from {OBSCURA_RELEASES_URL}.",
        ]

    lines += [
        "",
        "No-sudo alternative: drop the binary anywhere on PATH (e.g.,",
        "  ~/.local/bin/ or ~/bin/) or pass --obscura-binary /path/to/obscura.",
    ]
    if system == "Darwin":
        lines += [
            "",
            "If macOS kills the binary with no useful error (exit 137), clear",
            "the quarantine xattr that browsers apply on download:",
            "  xattr -d com.apple.quarantine /path/to/obscura",
            "(curl-installed binaries don't get this xattr; only browser",
            "downloads do.)",
        ]
    return "\n".join(lines)


def fetch_via_curl(url, timeout_seconds=_CURL_TIMEOUT_SECONDS,
                   user_agent=_CURL_USER_AGENT):
    """Fetch URL via subprocess curl. Returns response body or None.

    Used here only for sitemap.xml fetches. Cloudflare doesn't typically gate
    /sitemap.xml, and routing static XML through obscura would helpfully
    pretty-print it inside a <pre> tag that breaks the regex parser.

    --compressed handles servers that return gzip/brotli-encoded sitemaps
    without us asking. (Distinct from .xml.gz URLs, which curl writes through
    as binary; the regex parser handles those by ignoring non-text payloads.)
    """
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "--compressed", "--max-time", str(timeout_seconds),
             "-A", user_agent, url],
            capture_output=True, text=True, timeout=timeout_seconds + 5,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _port_in_use(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _pick_free_port():
    """Ask the kernel for an unused TCP port, return the number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ObscuraSession:
    """Manage a single long-lived `obscura serve` and a Playwright CDP
    connection to it.

    `obscura fetch <url>` (subprocess-per-page) was the original design, but
    spinning up Chromium-equivalent V8 + DOM for each URL means crawls pay
    cold-start cost N times AND each page sees a fresh stealth profile, so
    sites that lazily set CDN cookies treat every page as a new visitor.

    `obscura serve` exposes the Chrome DevTools Protocol on a TCP port.
    Playwright's `chromium.connect_over_cdp(...)` joins it the same way it
    would join a real Chrome with --remote-debugging-port. We get cookie
    persistence across pages, a single cold start per run, and Playwright's
    full API (auto-wait, selectors, evaluate, etc.) -- with obscura's
    stealth doing the bot-tell patching underneath.

    Use as a context manager:

        with ObscuraSession(binary="obscura", stealth=True) as session:
            html = session.fetch("https://example.com")
    """

    def __init__(self, *, binary="obscura", stealth=True, port=None,
                 ready_timeout=20):
        self.binary = binary
        self.stealth = stealth
        # If 9222 is busy or no port given, pick a free one.
        if port is None or _port_in_use(port):
            if port is not None:
                print(f"  (port {port} busy; picking a free one)",
                      file=sys.stderr)
            self.port = _pick_free_port()
        else:
            self.port = port
        self.ready_timeout = ready_timeout
        self._proc = None
        self._pw = None
        self._browser = None

    def __enter__(self):
        argv = [self.binary, "serve", "--port", str(self.port)]
        if self.stealth:
            argv.append("--stealth")
        try:
            self._proc = subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ObscuraMissing(self.binary) from exc

        # Wait for the port to start accepting connections, but bail early if
        # the process dies (e.g., binary error, port grab race).
        deadline = time.time() + self.ready_timeout
        while time.time() < deadline:
            if self._proc.poll() is not None:
                err = (self._proc.stderr.read() if self._proc.stderr
                       else b"").decode("utf-8", errors="ignore").strip()
                self._cleanup()
                raise ObscuraServeFailed(
                    f"obscura serve exited with code {self._proc.returncode}: "
                    f"{err or '(no stderr)'}"
                )
            if _port_in_use(self.port):
                break
            time.sleep(0.15)
        else:
            self._cleanup()
            raise ObscuraServeFailed(
                f"obscura serve didn't accept connections on port {self.port} "
                f"within {self.ready_timeout}s"
            )

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            self._cleanup()
            raise PlaywrightMissing() from exc

        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{self.port}"
            )
        except Exception:
            self._cleanup()
            raise

        stealth_state = "on" if self.stealth else "off"
        print(f"  (obscura serve started on port {self.port}, "
              f"stealth: {stealth_state})", file=sys.stderr)
        return self

    def fetch(self, url, *, wait_until="domcontentloaded", user_agent=None,
              selector=None, obscura_wait=None, timeout_seconds=60):
        """Fetch one URL via the running obscura. Returns HTML or None.

        Per-page failures (timeout, navigation error) return None so a crawl
        can continue. Session-level failures propagate.

        wait_until accepts Playwright's spelling. We translate `networkidle0`
        (obscura's spelling) to `networkidle` so users can pass either.
        """
        # Playwright's enum is "load" | "domcontentloaded" | "networkidle".
        # obscura's is "load" | "domcontentloaded" | "networkidle0". Accept
        # both.
        if wait_until == "networkidle0":
            wait_until = "networkidle"

        ctx_kwargs = {}
        if user_agent:
            ctx_kwargs["user_agent"] = user_agent

        ctx = self._browser.new_context(**ctx_kwargs)
        try:
            page = ctx.new_page()
            try:
                page.goto(url, wait_until=wait_until,
                          timeout=timeout_seconds * 1000)
                if selector:
                    try:
                        page.wait_for_selector(selector, timeout=5000)
                    except Exception:
                        pass
                if obscura_wait:
                    page.wait_for_timeout(int(obscura_wait * 1000))
                html = page.content()
                return html if html and html.strip() else None
            finally:
                page.close()
        except Exception as exc:
            print(f"  (fetch failed for {url}: {exc})", file=sys.stderr)
            return None
        finally:
            ctx.close()

    def __exit__(self, *args):
        self._cleanup()

    def _cleanup(self):
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None


def _extract_from_html(html, config, include_links, include_images, include_tables):
    metadata = trafilatura.extract_metadata(html)
    content = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=include_links,
        include_images=include_images,
        include_tables=include_tables,
        with_metadata=False,
        config=config,
    )
    return content, metadata


def _readability_extract(html, include_links=True):
    """Fallback extractor using Mozilla's Readability (via readability-lxml).

    Trafilatura is conservative: it discards anything that doesn't structurally
    look like an article (no <main>/<article>, low text density). Many SPAs
    render content into generic <div> containers that trafilatura rejects even
    though the prose is right there. Readability is greedy -- it scores every
    container for text density and picks the densest one. Returns Markdown.

    Returns None if either dependency is missing or extraction yields nothing.
    """
    try:
        from readability import Document
        from markdownify import markdownify as md
    except ImportError:
        return None

    try:
        doc = Document(html)
        content_html = doc.summary(html_partial=True)
    except Exception:
        return None

    if not content_html:
        return None

    strip_tags = ["div", "span"]
    if not include_links:
        strip_tags.append("a")
    markdown = md(content_html, heading_style="ATX", strip=strip_tags)
    return markdown.strip() or None


def _extract_with_readability_fallback(html, config, include_links,
                                       include_images, include_tables):
    """Run trafilatura on HTML and apply the Readability fallback when needed.

    Returns (content, metadata). Two failure modes Readability rescues:
      1. Trafilatura returns nothing -- page lacks any structure it recognizes.
      2. Trafilatura returns plenty of words but strips all headings/lists --
         the SPA's generic <div>s confuse its structure detection so it dumps
         a wall of paragraphs. Result is technically extracted but unreadable.
    Readability scores by text density rather than semantic tags, so it
    survives both. We prefer it only when it clearly does better, to avoid
    regressing on plain articles where trafilatura already wins.
    """
    extract_kwargs = dict(
        config=config, include_links=include_links,
        include_images=include_images, include_tables=include_tables,
    )
    content, metadata = _extract_from_html(html, **extract_kwargs)

    use_readability = False
    readability_md = None

    if not content or len(content.split()) < RENDER_FALLBACK_THRESHOLD:
        readability_md = _readability_extract(html, include_links=include_links)
        if readability_md and len(readability_md.split()) >= RENDER_FALLBACK_THRESHOLD:
            use_readability = True
    else:
        traf_headings = len(re.findall(r'^#{1,6} ', content, re.MULTILINE))
        if traf_headings == 0:
            readability_md = _readability_extract(html, include_links=include_links)
            if readability_md:
                read_headings = len(re.findall(r'^#{1,6} ', readability_md, re.MULTILINE))
                read_words = len(readability_md.split())
                traf_words = len(content.split())
                # Readability wins if it preserves multiple headings trafilatura
                # missed AND its word count is comparable (within 20%) -- guards
                # against Readability grabbing nav/sidebar in its dragnet.
                if read_headings >= 3 and read_words >= 0.8 * traf_words:
                    use_readability = True

    if use_readability:
        traf_words = len(content.split()) if content else 0
        print(f"  (using Readability fallback: trafilatura returned {traf_words} words "
              f"with no structure, Readability returned {len(readability_md.split())} words "
              f"with headings preserved)", file=sys.stderr)
        return readability_md, metadata

    return content, metadata


# File extensions obscura can't render (it triggers a download instead),
# and trafilatura can't parse as HTML. Filtered out of discovered URLs.
_BINARY_EXTENSIONS = (
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z",
    ".dmg", ".exe", ".msi", ".pkg", ".deb", ".rpm",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".mp3", ".mp4", ".mov", ".avi", ".webm", ".wav", ".ogg",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".csv", ".json", ".xml",
)


def _extract_same_domain_links(html, start_url, domain):
    """Parse HTML and return deduplicated same-domain hrefs (no query/fragment).

    Skips URLs whose path ends in a known binary extension -- obscura can't
    render those (it triggers a file download instead).
    """
    from lxml import html as lxml_html
    tree = lxml_html.fromstring(html)
    tree.make_links_absolute(start_url)

    urls = []
    for element, _attr, link, _pos in tree.iterlinks():
        if element.tag != "a" or urlparse(link).netloc != domain:
            continue
        clean = link.split("#")[0].split("?")[0].rstrip("/")
        if not clean:
            continue
        path_lower = urlparse(clean).path.lower()
        if path_lower.endswith(_BINARY_EXTENSIONS):
            continue
        if clean not in urls:
            urls.append(clean)
    return urls


def _path_prefix_for_scope(start_url):
    """Return the path prefix that other URLs must match to be in scope.

    "https://example.com/docs"        -> "/docs"
    "https://example.com/docs/"       -> "/docs"
    "https://example.com/docs/intro"  -> "/docs"
    "https://example.com/"            -> "" (no scoping)
    "https://example.com"             -> "" (no scoping)
    """
    path = urlparse(start_url).path.strip("/")
    if not path:
        return ""
    first_segment = path.split("/", 1)[0]
    return f"/{first_segment}"


_SITEMAP_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)


def _parse_sitemap_xml(xml, domain):
    """Pull URLs out of a sitemap.xml or sitemap-index payload via regex.

    Regex is good enough here -- sitemaps are flat <loc> lists. Filters to
    same-domain URLs.
    """
    if not xml:
        return []
    found = []
    for match in _SITEMAP_LOC_RE.finditer(xml):
        loc = match.group(1).strip()
        if not loc:
            continue
        if urlparse(loc).netloc == domain:
            found.append(loc)
    return found


def _fetch_sitemap_via_curl(start_url):
    """Try common sitemap locations via curl; expand sitemap-indexes one level.

    Sitemaps are static XML at well-known paths and almost always reachable via
    plain curl, even on Cloudflare-fronted sites. Returns deduplicated list of
    page URLs (sitemap-index entries are followed once, not recursively).
    """
    parsed = urlparse(start_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    domain = parsed.netloc
    candidates = [
        f"{base}/sitemap.xml",
        f"{base}/sitemap_index.xml",
        f"{base}/sitemap-index.xml",
        f"{base}/sitemap.xml.gz",
    ]

    for sitemap_url in candidates:
        xml = fetch_via_curl(sitemap_url)
        if not xml:
            continue
        entries = _parse_sitemap_xml(xml, domain)
        if not entries:
            continue
        page_urls = []
        seen = set()
        for entry in entries:
            path = urlparse(entry).path.lower()
            if path.endswith(".xml") or path.endswith(".xml.gz") or "sitemap" in path:
                sub = fetch_via_curl(entry)
                for u in _parse_sitemap_xml(sub, domain):
                    if u not in seen:
                        seen.add(u)
                        page_urls.append(u)
            else:
                if entry not in seen:
                    seen.add(entry)
                    page_urls.append(entry)
        if page_urls:
            return page_urls
    return []


def discover_pages(start_url, *, session, max_pages=50,
                   exclude_patterns=None, scope=True, fetch_kwargs=None):
    """Discover pages on the same domain starting from a URL.

    Sitemap (curl) -> session.fetch + link harvest. The whole point of this
    skill is the rendered DOM, so when the sitemap path fails we don't bother
    with a static curl pass on the start page -- we render it through obscura
    and harvest links from the resulting HTML.

    session:         live ObscuraSession (CDP-connected via Playwright)
    exclude_patterns: list of substrings to exclude from discovered URLs.
    scope:           when True (default), restrict discovery to URLs whose
                     path starts with the same top-level segment as start_url
                     (e.g. /docs/* when starting at /docs). Has no effect when
                     start_url is the site root.
    fetch_kwargs:    dict passed through to session.fetch for the start-page
                     fallback fetch (wait_until, selector, etc.).
    """
    domain = urlparse(start_url).netloc
    exclude_patterns = exclude_patterns or []
    scope_prefix = _path_prefix_for_scope(start_url) if scope else ""
    fetch_kwargs = fetch_kwargs or {}

    # Try sitemap first via curl. Static XML, bypasses Cloudflare TLS-fingerprint
    # blocks the requests library trips, and avoids the cost of rendering.
    urls = _fetch_sitemap_via_curl(start_url)

    if not urls:
        # No sitemap -- render the start page and harvest its DOM links.
        print("Rendering start page via obscura to discover links "
              "(no sitemap found)...", file=sys.stderr)
        rendered_html = session.fetch(start_url, **fetch_kwargs)
        if rendered_html:
            urls = _extract_same_domain_links(rendered_html, start_url, domain)

        if not urls:
            return [start_url]

    # Apply exclude patterns
    if exclude_patterns:
        before = len(urls)
        urls = [u for u in urls
                if not any(pat in u for pat in exclude_patterns)]
        excluded = before - len(urls)
        if excluded:
            print(f"Excluded {excluded} URLs matching patterns: {exclude_patterns}",
                  file=sys.stderr)

    # Apply path scoping: when starting at /docs, only crawl /docs/*. The start
    # URL itself is exempt (always kept). Pass --no-scope to disable when peer
    # sections (e.g. /security as a peer of /docs) hold related docs.
    if scope_prefix:
        start_clean = start_url.rstrip("/")
        before = len(urls)
        urls = [u for u in urls
                if u == start_clean
                or urlparse(u).path.startswith(scope_prefix)]
        scoped_out = before - len(urls)
        if scoped_out:
            print(f"Path-scoped to {scope_prefix}/* (excluded {scoped_out} URLs "
                  f"outside scope; use --no-scope to disable)",
                  file=sys.stderr)

    # Ensure start URL is first
    start_clean = start_url.rstrip("/")
    if start_clean in urls:
        urls.remove(start_clean)
    urls.insert(0, start_clean)

    if len(urls) > max_pages:
        print(f"Found {len(urls)} pages, limiting to {max_pages}", file=sys.stderr)
        urls = urls[:max_pages]

    return urls


def dry_run(url, *, session, crawl=False, scope=True, fetch_kwargs=None):
    """Preview metadata and (optionally) page list without writing output.

    One session.fetch + a trafilatura metadata pass. Same fetcher as real
    extraction, so the preview matches what the real run will see.
    """
    fetch_kwargs = fetch_kwargs or {}
    config = make_config()

    print("=== Dry Run ===")
    print(f"URL: {url}")
    print()

    html = session.fetch(url, **fetch_kwargs)
    if not html:
        print("ERROR: obscura returned no HTML. Try --wait-until networkidle0 "
              "or --obscura-wait 5 to give the page more time to settle.",
              file=sys.stderr)
        return

    metadata = trafilatura.extract_metadata(html)
    content = trafilatura.extract(html, output_format="markdown", config=config)
    word_count = len(content.split()) if content else 0

    stealth_state = "on" if session.stealth else "off"
    wait_until = fetch_kwargs.get("wait_until", "domcontentloaded")

    print(f"Stealth:     {stealth_state}")
    print(f"Wait until:  {wait_until}")
    print(f"Title:       {metadata.title if metadata and metadata.title else '(not detected)'}")
    print(f"Author:      {metadata.author if metadata and metadata.author else '(not detected)'}")
    print(f"Date:        {metadata.date if metadata and metadata.date else '(not detected)'}")
    print(f"Site name:   {metadata.sitename if metadata and metadata.sitename else '(not detected)'}")
    desc = (metadata.description or "(not detected)")[:200] if metadata else "(not detected)"
    print(f"Description: {desc}")
    print(f"Words:       {word_count}")
    print(f"Content:     {'Yes' if content else 'No extractable content'}")

    if word_count < RENDER_FALLBACK_THRESHOLD:
        print()
        print("Page looks sparse. Real extraction will try the Readability")
        print("fallback. If that also returns little, the page may be serving")
        print("an active interstitial that defeats stealth, or genuinely lack")
        print("readable prose.")

    if crawl:
        print()
        print("=== Discovered Pages ===")
        pages = discover_pages(
            url,
            session=session,
            exclude_patterns=_default_exclude_patterns(),
            scope=scope, fetch_kwargs=fetch_kwargs,
        )
        for i, page_url in enumerate(pages, 1):
            print(f"  {i:3d}. {page_url}")
        print(f"\nTotal: {len(pages)} pages")


def build_single_page_markdown(url, content, metadata):
    """Build Markdown for a single-page extraction."""
    lines = []

    title = metadata.title if metadata and metadata.title else urlparse(url).netloc
    lines.append(f"# {title}")
    lines.append("")

    if metadata:
        if metadata.author:
            lines.append(f"**Author:** {metadata.author}")
        if metadata.sitename:
            lines.append(f"**Site:** {metadata.sitename}")
        if metadata.date:
            lines.append(f"**Date:** {metadata.date}")
    lines.append(f"**Source:** {url}")
    if metadata and metadata.description:
        lines.append(f"**Description:** {metadata.description}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(content)
    lines.append("")

    return "\n".join(lines)


def build_multi_page_markdown(start_url, pages, site_metadata):
    """Build Markdown for a multi-page crawl.

    pages: list of (url, content, metadata) tuples
    site_metadata: metadata from the start page (used for the document title)
    """
    lines = []

    site_name = ""
    if site_metadata and site_metadata.sitename:
        site_name = site_metadata.sitename
    elif site_metadata and site_metadata.title:
        site_name = site_metadata.title
    else:
        site_name = urlparse(start_url).netloc

    lines.append(f"# {site_name}")
    lines.append("")
    lines.append(f"**Source:** {start_url}")
    if site_metadata and site_metadata.author:
        lines.append(f"**Author:** {site_metadata.author}")
    if site_metadata and site_metadata.description:
        lines.append(f"**Description:** {site_metadata.description}")
    lines.append("")

    # Table of contents
    lines.append("## Table of Contents")
    lines.append("")
    for i, (url, content, meta) in enumerate(pages, 1):
        page_title = meta.title if meta and meta.title else url
        anchor = slugify(page_title)
        lines.append(f"{i}. [{page_title}](#{anchor})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Each page as a section
    for url, content, meta in pages:
        page_title = meta.title if meta and meta.title else url
        lines.append(f"## {page_title}")
        lines.append("")
        lines.append(f"*URL: {url}*")
        lines.append("")
        if content:
            lines.append(content)
        else:
            lines.append("*(No extractable content)*")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extract web page content to Markdown via the obscura "
                    "headless browser (stealth on by default).",
    )
    parser.add_argument("url", help="URL to extract")
    parser.add_argument("-o", "--output", help="Output file path (default: stdout)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview metadata without extracting")
    parser.add_argument("--crawl", action="store_true",
                        help="Crawl the site and extract multiple pages")
    parser.add_argument("--max-pages", type=int, default=50,
                        help="Max pages to crawl (default: 50)")
    parser.add_argument("--no-links", action="store_true",
                        help="Strip hyperlinks from output")
    parser.add_argument("--include-images", action="store_true",
                        help="Include image references in output")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between requests when crawling (default: 1.0)")
    parser.add_argument("--exclude", nargs="*",
                        help="URL substrings to exclude when crawling "
                             "(e.g., /tag/ /category/). Defaults filter common "
                             "non-content paths; pass explicit patterns to override.")
    parser.add_argument("--no-exclude", action="store_true",
                        help="Disable default URL exclusion patterns when crawling")
    parser.add_argument("--no-scope", action="store_true",
                        help="Disable path-scoped crawling. By default, when "
                             "crawling from a non-root URL like /docs, only "
                             "URLs under /docs/* are followed. --no-scope "
                             "follows any same-domain link.")
    parser.add_argument("--no-stealth", action="store_true",
                        help="Disable obscura's --stealth pass-through. "
                             "Stealth is on by default since this skill exists "
                             "for bot-walled sites.")
    parser.add_argument("--wait-until",
                        choices=["load", "domcontentloaded", "networkidle0"],
                        default="domcontentloaded",
                        help="obscura wait condition (default: domcontentloaded). "
                             "networkidle0 is slower and unreliable on SPAs with "
                             "persistent connections; reserve for sites that "
                             "genuinely need late-loading content.")
    parser.add_argument("--obscura-wait", type=float, default=None,
                        help="Seconds to settle after wait_until fires "
                             "(passed to obscura --wait). Use when stealth "
                             "alone isn't clearing a slow-rendering challenge.")
    parser.add_argument("--obscura-selector", default=None,
                        help="CSS selector to wait for after wait_until "
                             "(passed to obscura --selector). Use to wait for "
                             "real content rather than the page shell.")
    parser.add_argument("--obscura-binary", default=None,
                        help="Path to the obscura binary. Defaults to "
                             "looking up 'obscura' on PATH.")
    parser.add_argument("--obscura-port", type=int, default=None,
                        help="Port for obscura serve (default: auto-pick a "
                             "free port). Override only when you need a "
                             "stable port for external connections.")

    args = parser.parse_args()

    binary = args.obscura_binary or "obscura"
    if shutil.which(binary) is None:
        print(_obscura_install_hint(binary), file=sys.stderr)
        sys.exit(1)

    config = make_config()
    include_links = not args.no_links

    fetch_kwargs = dict(
        wait_until=args.wait_until,
        selector=args.obscura_selector,
        obscura_wait=args.obscura_wait,
    )

    try:
        with ObscuraSession(binary=binary,
                            stealth=not args.no_stealth,
                            port=args.obscura_port) as session:
            _run(session, args, config, include_links, fetch_kwargs)
    except PlaywrightMissing:
        print("ERROR: the 'playwright' Python package is required for "
              "obscura-scraper-crawler.", file=sys.stderr)
        print("  pip install playwright", file=sys.stderr)
        print("(connect_over_cdp doesn't need `playwright install` -- we "
              "connect to obscura, not Chromium.)", file=sys.stderr)
        sys.exit(1)
    except ObscuraMissing:
        print(_obscura_install_hint(binary), file=sys.stderr)
        sys.exit(1)
    except ObscuraServeFailed as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def _run(session, args, config, include_links, fetch_kwargs):
    """Execute dry-run, single-page, or crawl mode against a live session."""
    if args.dry_run:
        dry_run(args.url, session=session, crawl=args.crawl,
                scope=not args.no_scope, fetch_kwargs=fetch_kwargs)
        return

    def _extract_one(url):
        html = session.fetch(url, **fetch_kwargs)
        if not html:
            return None, None
        return _extract_with_readability_fallback(
            html, config, include_links,
            args.include_images, include_tables=True,
        )

    if args.crawl:
        if args.no_exclude:
            exclude = []
        elif args.exclude:
            exclude = args.exclude
        else:
            exclude = _default_exclude_patterns()
        urls = discover_pages(args.url, session=session,
                              max_pages=args.max_pages,
                              exclude_patterns=exclude,
                              scope=not args.no_scope,
                              fetch_kwargs=fetch_kwargs)
        print(f"Extracting {len(urls)} pages via obscura...", file=sys.stderr)

        pages = []
        site_metadata = None

        for i, url in enumerate(urls):
            content, metadata = _extract_one(url)
            if i == 0:
                site_metadata = metadata
            if content:
                pages.append((url, content, metadata))
                words = len(content.split())
                print(f"  [{i+1}/{len(urls)}] {url} ({words} words)",
                      file=sys.stderr)
            else:
                print(f"  [{i+1}/{len(urls)}] {url} (skipped, no content)",
                      file=sys.stderr)

            if i < len(urls) - 1:
                time.sleep(args.delay)

        if not pages:
            print("ERROR: No content extracted from any page", file=sys.stderr)
            sys.exit(1)

        total_words = sum(len(c.split()) for _, c, _ in pages)
        output = build_multi_page_markdown(args.url, pages, site_metadata)
        print(f"\nExtracted {len(pages)} pages ({total_words} words total)",
              file=sys.stderr)

    else:
        # Single-page mode
        content, metadata = _extract_one(args.url)
        if not content:
            print(f"ERROR: Could not extract content from {args.url}",
                  file=sys.stderr)
            sys.exit(1)

        output = build_single_page_markdown(args.url, content, metadata)
        print(f"Extracted {len(content.split())} words via obscura",
              file=sys.stderr)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
