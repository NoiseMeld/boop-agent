#!/usr/bin/env python3
"""Extract web page content to clean Markdown using trafilatura.

Single-page mode (default):
    python extract_webpage.py "https://example.com/article" -o output.md

Multi-page crawl:
    python extract_webpage.py "https://example.com/" --crawl -o output.md

Dry run (preview metadata only):
    python extract_webpage.py "https://example.com/article" --dry-run
"""

import argparse
import re
import subprocess
import sys
import time
from urllib.parse import urljoin, urlparse

import trafilatura
from trafilatura.settings import use_config


# Below this word count, the static fetch is treated as too sparse and we
# advance to the next fetcher in the cascade (covers React/Vue/Angular SPAs
# that render almost entirely client-side, and Cloudflare-fronted pages where
# the fetcher was served a challenge stub instead of the real HTML).
RENDER_FALLBACK_THRESHOLD = 50

# Curl ships on every macOS/Linux box and uses a TLS fingerprint Cloudflare
# doesn't block, unlike the Python `requests` library. We hand it a desktop UA
# so origins that gate on User-Agent return the full document.
_CURL_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_CURL_TIMEOUT_SECONDS = 30

PLAYWRIGHT_INSTALL_HINT = (
    "Install Playwright (one-time, ~300MB Chromium goes to ~/.cache/ms-playwright):\n"
    "    pip install playwright && playwright install chromium"
)

READABILITY_INSTALL_HINT = (
    "Install the Readability fallback so SPAs without semantic markup can be extracted:\n"
    "    pip install readability-lxml markdownify"
)


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


class PlaywrightMissing(Exception):
    """Playwright Python package is not installed."""


class ChromiumMissing(Exception):
    """Playwright is installed but Chromium browser binary is not."""


def fetch_via_curl(url, timeout_seconds=_CURL_TIMEOUT_SECONDS,
                   user_agent=_CURL_USER_AGENT):
    """Fetch URL via subprocess curl. Returns response body or None.

    Cloudflare blocks the Python `requests` library (and therefore
    `trafilatura.fetch_url`) by TLS fingerprint -- a browser UA isn't enough.
    Curl's TLS fingerprint isn't on the blocklist, so this path succeeds on
    Cloudflare-fronted Mintlify/GitBook/Docusaurus sites where requests gets
    a 403.

    --compressed asks curl to advertise `Accept-Encoding: gzip,deflate,br` and
    transparently decode the response. Without it, origins that default to
    Brotli/gzip return the raw compressed bytes, which trafilatura/Readability
    will dutifully "extract" as gibberish. Sannysoft and many CDN-fronted
    sites do this.
    """
    try:
        result = subprocess.run(
            ["curl", "-sL", "--compressed", "--max-time", str(timeout_seconds),
             "-A", user_agent, url],
            capture_output=True, text=True,
            timeout=timeout_seconds + 5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout or None


def fetch_rendered(url, timeout_ms=30000, wait_until="domcontentloaded"):
    """Fetch URL with headless Chromium and return fully-rendered HTML.

    wait_until:
        "domcontentloaded" (default) -- return as soon as the DOM is parsed,
            then poll briefly for a content selector. Mintlify/GitBook/Nextra
            keep long-lived analytics + websocket connections open, so
            "networkidle" never fires and Playwright times out at 30s with
            no content. domcontentloaded sidesteps that.
        "load"             -- wait for the load event.
        "networkidle"      -- wait until there are no network connections
            for 500ms. Slowest, and unreliable on SPAs with persistent
            connections; kept as a last resort.

    Raises PlaywrightMissing if the Python package isn't installed,
    ChromiumMissing if the browser binary isn't installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PlaywrightMissing() from exc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=_CURL_USER_AGENT)
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                # When we returned at domcontentloaded, the main content may
                # still be hydrating. Wait briefly for a common content
                # container so SPAs have a chance to render before we snapshot
                # the DOM. Failure here is expected on plain pages -- swallow.
                if wait_until == "domcontentloaded":
                    try:
                        page.wait_for_selector(
                            "main, article, [role='main'], #content, .content, "
                            ".prose, .markdown, .docs-content",
                            timeout=5000,
                        )
                    except Exception:
                        pass
                return page.content()
            finally:
                browser.close()
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            raise ChromiumMissing() from exc
        raise


def _looks_like_html(s):
    """Sanity-check that a fetcher returned decoded HTML, not raw compressed bytes.

    trafilatura.fetch_url uses urllib3 without enabling brotli decoding, so
    sites that serve `Content-Encoding: br` (sannysoft, many CDN-fronted
    pages) hand back raw brotli bytes that look superficially like content
    -- they have non-zero length, and Readability will dutifully "extract"
    nonsense words from them, clearing the cascade's word-count threshold.
    Result: the curl/Playwright steps never run.

    A real HTML response always contains angle brackets and is almost
    entirely printable. Compressed binary has neither property.
    """
    if not s:
        return False
    sample = s[:4000]
    if "<" not in sample or ">" not in sample:
        return False
    non_printable = sum(
        1 for c in sample
        if ord(c) < 32 and c not in "\n\r\t"
    )
    if non_printable > len(sample) * 0.02:
        return False
    return True


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


def _build_fetch_plan(fetcher, render, wait_until):
    """Return ordered list of (label, callable_taking_url) fetch attempts.

    fetcher:
        "auto"       - cascade trafilatura -> curl -> playwright(dcl) ->
                       playwright(networkidle), pruned by `render` setting
        "requests"   - trafilatura.fetch_url only
        "curl"       - subprocess curl only
        "playwright" - headless Chromium only

    render: "auto" | "always" (Playwright only) | "never" (no Playwright).
            Honored only when fetcher == "auto"; an explicit fetcher choice
            overrides it.
    """
    pw_wait = wait_until or "domcontentloaded"

    requests_step = ("requests",
                     lambda u: trafilatura.fetch_url(u, config=make_config()))
    curl_step = ("curl", fetch_via_curl)
    pw_dcl_step = ("playwright[domcontentloaded]",
                   lambda u: fetch_rendered(u, wait_until=pw_wait))
    pw_idle_step = ("playwright[networkidle]",
                    lambda u: fetch_rendered(u, wait_until="networkidle"))

    if fetcher == "requests":
        return [requests_step]
    if fetcher == "curl":
        return [curl_step]
    if fetcher == "playwright":
        # Honor an explicit --wait-until; otherwise try the fast path then
        # fall back to networkidle.
        if wait_until and wait_until != "domcontentloaded":
            return [("playwright[%s]" % wait_until,
                     lambda u: fetch_rendered(u, wait_until=wait_until))]
        return [pw_dcl_step, pw_idle_step]

    # fetcher == "auto"
    if render == "always":
        return [pw_dcl_step, pw_idle_step]
    if render == "never":
        return [requests_step, curl_step]
    return [requests_step, curl_step, pw_dcl_step, pw_idle_step]


def fetch_and_extract(url, config=None, include_links=True, include_images=False,
                      include_tables=True, render="auto", fetcher="auto",
                      wait_until=None):
    """Fetch a single URL and return (markdown_content, metadata, used_render).

    Walks a cascade of fetchers (trafilatura.fetch_url -> curl -> Playwright
    domcontentloaded -> Playwright networkidle) and returns the first result
    that clears RENDER_FALLBACK_THRESHOLD words. Falls back to the best
    sub-threshold result if nothing clears it.

    fetcher:    explicit fetcher to use, or "auto" for the cascade
    render:     for fetcher=="auto", whether Playwright is in the cascade
    wait_until: Playwright wait condition (default: domcontentloaded)
    """
    config = config or make_config()
    plan = _build_fetch_plan(fetcher, render, wait_until)

    best = None  # (content, metadata, used_render, words)
    last_pw_error = None

    for label, fetch_fn in plan:
        try:
            html = fetch_fn(url)
        except (PlaywrightMissing, ChromiumMissing) as exc:
            last_pw_error = exc
            # If the user explicitly asked for Playwright, surface it. Otherwise
            # skip the Playwright steps and let earlier fetchers' results stand.
            if fetcher == "playwright":
                raise
            continue
        except Exception as exc:
            print(f"  ({label} fetch failed: {exc})", file=sys.stderr)
            continue

        if not html:
            continue

        if not _looks_like_html(html):
            print(f"  ({label} returned non-HTML bytes -- likely brotli/gzip "
                  f"the fetcher couldn't decode; advancing cascade)",
                  file=sys.stderr)
            continue

        content, metadata = _extract_with_readability_fallback(
            html, config, include_links, include_images, include_tables,
        )
        words = len(content.split()) if content else 0
        used_render = label.startswith("playwright")

        if words >= RENDER_FALLBACK_THRESHOLD:
            return content, metadata, used_render

        if content and (best is None or words > best[3]):
            best = (content, metadata, used_render, words)

    if best is not None:
        return best[0], best[1], best[2]

    # Nothing produced content. Re-raise a Playwright error if that's the only
    # thing that went wrong, so the caller can surface the install hint.
    if last_pw_error is not None and fetcher == "auto":
        raise last_pw_error
    return None, None, False


# File extensions Playwright can't render (it triggers a download instead),
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

    Skips URLs whose path ends in a known binary extension -- Playwright
    can't render those (it triggers a file download instead).
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

    Only the top-level path segment is used. A start URL deep inside a
    section still scopes to the section root, so /docs/intro will still
    crawl /docs/api.
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
    plain curl, even on Cloudflare-fronted sites where requests is 403'd.
    Returns deduplicated list of page URLs (sitemap-index entries are followed
    once, not recursively, which is enough for ~99% of real sites).
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
        # If entries point at more sitemaps (sitemap index), expand one level.
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


def discover_pages(start_url, config=None, max_pages=50, exclude_patterns=None,
                   render="auto", scope=True):
    """Discover pages on the same domain starting from a URL.

    Tries the sitemap first (via trafilatura, then a curl-based fallback for
    Cloudflare-fronted sites where trafilatura's request gets 403'd). If no
    sitemap, falls back to static link extraction, then to a rendered fetch
    via Playwright -- the signature of a client-rendered SPA. Returns a
    deduplicated list of URLs including the start URL.

    render: "auto" (sitemap -> static -> rendered fallback),
            "always" (skip static, go straight to rendered),
            "never" (no rendered fallback even if static yields nothing).
    exclude_patterns: list of substrings to exclude from discovered URLs.
    scope: when True (default), restrict discovery to URLs whose path starts
           with the same top-level segment as start_url (e.g. /docs/* when
           starting at /docs). Has no effect when start_url is the site root.
    """
    config = config or make_config()
    domain = urlparse(start_url).netloc
    exclude_patterns = exclude_patterns or []
    scope_prefix = _path_prefix_for_scope(start_url) if scope else ""

    # Try sitemap first -- works regardless of how the site renders.
    # trafilatura's sitemap_search uses the requests library internally and is
    # blocked by Cloudflare; if it returns nothing, fall back to curl before
    # assuming there's no sitemap.
    from trafilatura import sitemaps
    sitemap_urls = sitemaps.sitemap_search(start_url)
    if sitemap_urls:
        urls = [u for u in sitemap_urls if urlparse(u).netloc == domain]
    else:
        urls = _fetch_sitemap_via_curl(start_url)
        if urls:
            print(f"Found {len(urls)} URLs via curl-fetched sitemap "
                  f"(trafilatura's sitemap_search returned nothing -- likely "
                  f"blocked by upstream WAF).", file=sys.stderr)

    if not urls:
        # No sitemap -- fall back to link discovery on the start page itself.
        # Cascade trafilatura -> curl -> rendered, mirroring fetch_and_extract.
        downloaded = None
        if render != "always":
            downloaded = trafilatura.fetch_url(start_url, config=config)
            if downloaded and _looks_like_html(downloaded):
                urls = _extract_same_domain_links(downloaded, start_url, domain)
            if not urls:
                downloaded = fetch_via_curl(start_url)
                if downloaded and _looks_like_html(downloaded):
                    urls = _extract_same_domain_links(downloaded, start_url, domain)

        # Static returned nothing useful: probably a JS-only shell. Render it.
        need_render = (render == "always") or (render == "auto" and not urls)
        if need_render:
            print("Rendering start page to discover links (sitemap and static "
                  "HTML had none)...", file=sys.stderr)
            rendered_html = fetch_rendered(start_url)
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
    # URL itself is exempt (always kept). A common surprise is when a sibling
    # section (e.g. /security as a peer of /docs) holds related docs -- the
    # user can disable scoping with --no-scope to capture those.
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


def dry_run(url, crawl=False, render="auto", scope=True, fetcher="auto",
            wait_until=None):
    """Preview metadata and page list without extracting full content.

    Walks the same fetcher cascade as fetch_and_extract so the preview matches
    what extraction would actually see -- if curl is the fetcher that succeeds
    on a Cloudflare-fronted page, the dry run shows that.
    """
    config = make_config()

    print("=== Dry Run ===")
    print(f"URL: {url}")
    print()

    # Walk the static-only portion of the cascade for the preview by default
    # -- skipping Playwright keeps the dry run fast. But honor the user's
    # explicit --render or --no-render choice, since the whole point of those
    # flags is to control whether the browser runs.
    plan_fetcher = fetcher if fetcher != "auto" else "auto"
    if plan_fetcher == "auto" and render == "auto":
        effective_render = "never"
    else:
        effective_render = render
    plan = _build_fetch_plan(plan_fetcher, render=effective_render,
                             wait_until=wait_until)

    downloaded = None
    used_label = None
    for label, fetch_fn in plan:
        try:
            html = fetch_fn(url)
        except (PlaywrightMissing, ChromiumMissing):
            continue
        except Exception as exc:
            print(f"  ({label} fetch failed: {exc})", file=sys.stderr)
            continue
        if html and _looks_like_html(html):
            downloaded = html
            used_label = label
            break
        elif html:
            print(f"  ({label} returned non-HTML bytes; advancing)",
                  file=sys.stderr)

    if not downloaded:
        print("ERROR: Could not fetch URL via any static fetcher "
              "(trafilatura, curl). Try --fetcher playwright.",
              file=sys.stderr)
        return

    metadata = trafilatura.extract_metadata(downloaded)
    content = trafilatura.extract(downloaded, output_format="markdown", config=config)
    word_count = len(content.split()) if content else 0

    print(f"Fetcher:     {used_label}")
    print(f"Title:       {metadata.title if metadata and metadata.title else '(not detected)'}")
    print(f"Author:      {metadata.author if metadata and metadata.author else '(not detected)'}")
    print(f"Date:        {metadata.date if metadata and metadata.date else '(not detected)'}")
    print(f"Site name:   {metadata.sitename if metadata and metadata.sitename else '(not detected)'}")
    desc = (metadata.description or "(not detected)")[:200] if metadata else "(not detected)"
    print(f"Description: {desc}")
    print(f"Words:       {word_count}")
    print(f"Content:     {'Yes' if content else 'No extractable content'}")

    # Only advise about the Playwright fallback when it would actually run
    # during real extraction. With --no-render or --fetcher requests/curl,
    # the cascade stops at the static fetcher and the message would mislead.
    playwright_in_real_extraction = (
        fetcher == "playwright"
        or (fetcher == "auto" and render != "never")
    )
    if word_count < RENDER_FALLBACK_THRESHOLD and playwright_in_real_extraction:
        print()
        print("Page looks sparse or JS-rendered. Extraction will continue the")
        print("cascade into Playwright. Pass --no-render to disable that.")

    if crawl:
        print()
        print("=== Discovered Pages ===")
        pages = discover_pages(url, config=config,
                               exclude_patterns=_default_exclude_patterns(),
                               render=render, scope=scope)
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
        description="Extract web page content to Markdown"
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
    render_group = parser.add_mutually_exclusive_group()
    render_group.add_argument("--render", action="store_const", dest="render",
                              const="always",
                              help="Always render with a headless browser "
                                   "(skip the fast static fetch)")
    render_group.add_argument("--no-render", action="store_const", dest="render",
                              const="never",
                              help="Never render; return whatever the static "
                                   "fetch produces (faster, may miss JS pages)")
    parser.set_defaults(render="auto")
    parser.add_argument("--fetcher", choices=["auto", "requests", "curl", "playwright"],
                        default="auto",
                        help="Force a specific fetcher (default: auto). The auto "
                             "cascade is trafilatura -> curl -> Playwright "
                             "(domcontentloaded) -> Playwright (networkidle). "
                             "Use 'curl' for Cloudflare-fronted sites that 403 "
                             "the requests library; use 'playwright' to skip "
                             "static fetchers entirely.")
    parser.add_argument("--wait-until",
                        choices=["domcontentloaded", "load", "networkidle"],
                        default=None,
                        help="Playwright wait condition (default: "
                             "domcontentloaded). Mintlify/GitBook/Nextra keep "
                             "long-lived connections open so 'networkidle' "
                             "times out at 30s with no content.")

    args = parser.parse_args()
    config = make_config()
    include_links = not args.no_links

    if args.dry_run:
        dry_run(args.url, crawl=args.crawl, render=args.render,
                scope=not args.no_scope, fetcher=args.fetcher,
                wait_until=args.wait_until)
        return

    def _extract_one(url, fatal_on_error=True):
        try:
            return fetch_and_extract(
                url, config=config, include_links=include_links,
                include_images=args.include_images, render=args.render,
                fetcher=args.fetcher, wait_until=args.wait_until,
            )
        except PlaywrightMissing:
            print(f"\nERROR: '{url}' looks JavaScript-rendered and Playwright "
                  "is not installed.", file=sys.stderr)
            print(PLAYWRIGHT_INSTALL_HINT, file=sys.stderr)
            sys.exit(1)
        except ChromiumMissing:
            print(f"\nERROR: '{url}' needs a headless browser but Chromium "
                  "isn't installed.", file=sys.stderr)
            print("    playwright install chromium", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            # Per-page failures (timeouts, downloads triggered by binary URLs,
            # transient network errors) shouldn't kill an in-progress crawl.
            if fatal_on_error:
                raise
            print(f"      (error: {exc})", file=sys.stderr)
            return None, None, False

    if args.crawl:
        # Multi-page mode
        if args.no_exclude:
            exclude = []
        elif args.exclude:
            exclude = args.exclude
        else:
            exclude = _default_exclude_patterns()
        try:
            urls = discover_pages(args.url, config=config,
                                  max_pages=args.max_pages,
                                  exclude_patterns=exclude, render=args.render,
                                  scope=not args.no_scope)
        except PlaywrightMissing:
            print(f"\nERROR: '{args.url}' has no static links to crawl and "
                  "Playwright is not installed.", file=sys.stderr)
            print(PLAYWRIGHT_INSTALL_HINT, file=sys.stderr)
            sys.exit(1)
        except ChromiumMissing:
            print(f"\nERROR: '{args.url}' needs a headless browser to discover "
                  "links but Chromium isn't installed.", file=sys.stderr)
            print("    playwright install chromium", file=sys.stderr)
            sys.exit(1)
        print(f"Extracting {len(urls)} pages...", file=sys.stderr)

        pages = []
        site_metadata = None

        for i, url in enumerate(urls):
            content, metadata, rendered = _extract_one(url, fatal_on_error=False)
            if i == 0:
                site_metadata = metadata
            if content:
                pages.append((url, content, metadata))
                words = len(content.split())
                tag = " [rendered]" if rendered else ""
                print(f"  [{i+1}/{len(urls)}] {url} ({words} words){tag}",
                      file=sys.stderr)
            else:
                print(f"  [{i+1}/{len(urls)}] {url} (skipped, no content)", file=sys.stderr)

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
        content, metadata, rendered = _extract_one(args.url)
        if not content:
            print(f"ERROR: Could not extract content from {args.url}",
                  file=sys.stderr)
            sys.exit(1)

        output = build_single_page_markdown(args.url, content, metadata)
        tag = " (rendered with headless browser)" if rendered else ""
        print(f"Extracted {len(content.split())} words{tag}", file=sys.stderr)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
