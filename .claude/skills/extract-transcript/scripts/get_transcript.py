#!/usr/bin/env python3
"""Fetch a YouTube video's transcript and metadata.

Default output is a single JSON object with transcript (plain + timestamped),
title, channel, description, duration, upload date, and chapters. Pair with
the extract-transcript skill's SKILL.md instructions.

Metadata sources, in order of preference:
  1. yt-dlp (if on PATH) — full metadata including chapters and description.
  2. Fallback: oembed for title/channel + watch-page scrape for description,
     duration, chapters, upload date. Watch-page scraping is brittle; any
     field that can't be resolved is null.

Usage:
    python3 scripts/get_transcript.py <youtube-url-or-id>
    python3 scripts/get_transcript.py <url> -o bundle.json
    python3 scripts/get_transcript.py <url> --plain       # plain transcript only
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url_or_id: str) -> str:
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pat in patterns:
        m = re.search(pat, url_or_id)
        if m:
            return m.group(1)
    return url_or_id


def fetch_transcript(video_id: str) -> tuple[str, list[dict[str, Any]]]:
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id)
    plain = "\n".join(s.text for s in transcript)
    timed = [
        {
            "start": round(s.start, 2),
            "duration": round(s.duration, 2),
            "text": s.text,
        }
        for s in transcript
    ]
    return plain, timed


def fetch_metadata_ytdlp(url: str) -> dict[str, Any] | None:
    if not shutil.which("yt-dlp"):
        return None
    try:
        result = subprocess.run(
            ["yt-dlp", "--skip-download", "--dump-single-json", "--no-warnings", url],
            capture_output=True,
            text=True,
            timeout=45,
            check=True,
        )
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    chapters = data.get("chapters") or []
    return {
        "title": data.get("title"),
        "channel": data.get("uploader") or data.get("channel"),
        "channel_url": data.get("uploader_url") or data.get("channel_url"),
        "description": data.get("description"),
        "duration_seconds": data.get("duration"),
        "upload_date": _format_ytdlp_date(data.get("upload_date")),
        "chapters": [
            {
                "title": c.get("title"),
                "start_seconds": c.get("start_time"),
            }
            for c in chapters
            if c.get("title")
        ]
        or None,
        "metadata_source": "yt-dlp",
    }


def _format_ytdlp_date(d: str | None) -> str | None:
    if not d or len(d) != 8:
        return d
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def fetch_metadata_fallback(url: str, video_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "title": None,
        "channel": None,
        "channel_url": None,
        "description": None,
        "duration_seconds": None,
        "upload_date": None,
        "chapters": None,
        "metadata_source": "fallback",
    }

    # oembed — reliable source of title + channel
    try:
        with urllib.request.urlopen(
            f"https://www.youtube.com/oembed?url={url}&format=json", timeout=10
        ) as r:
            oembed = json.loads(r.read())
        result["title"] = oembed.get("title")
        result["channel"] = oembed.get("author_name")
        result["channel_url"] = oembed.get("author_url")
    except Exception as e:
        print(f"warning: oembed fetch failed: {e}", file=sys.stderr)

    # Watch-page scrape for everything else. This is brittle — YouTube changes
    # its embedded JSON structure occasionally.
    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/watch?v={video_id}",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"warning: watch page fetch failed: {e}", file=sys.stderr)
        return result

    player_json = _extract_json_blob(html, "ytInitialPlayerResponse")
    if player_json:
        details = player_json.get("videoDetails", {})
        if not result["title"]:
            result["title"] = details.get("title")
        if not result["channel"]:
            result["channel"] = details.get("author")
        desc = details.get("shortDescription")
        if desc:
            result["description"] = desc
        dur = details.get("lengthSeconds")
        if dur:
            try:
                result["duration_seconds"] = int(dur)
            except (TypeError, ValueError):
                pass
        microformat = player_json.get("microformat", {}).get(
            "playerMicroformatRenderer", {}
        )
        upload = microformat.get("uploadDate") or microformat.get("publishDate")
        if upload:
            result["upload_date"] = upload[:10]

    initial_data = _extract_json_blob(html, "ytInitialData")
    if initial_data:
        chapters = _extract_chapters(initial_data)
        if chapters:
            result["chapters"] = chapters

    return result


def _extract_json_blob(html: str, var_name: str) -> dict[str, Any] | None:
    # Match either `var X = {...};` or `X = {...};` — the trailing guard
    # stops at `;</script>` or `;var` to bound the greedy object match.
    pattern = re.compile(
        rf"{re.escape(var_name)}\s*=\s*(\{{.+?\}})\s*;\s*(?:</script>|var\s)",
        re.DOTALL,
    )
    m = pattern.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _extract_chapters(initial_data: dict[str, Any]) -> list[dict[str, Any]] | None:
    panels = initial_data.get("engagementPanels") or []
    for panel in panels:
        section = panel.get("engagementPanelSectionListRenderer") or {}
        content = section.get("content") or {}
        marker_list = content.get("macroMarkersListRenderer") or {}
        items = marker_list.get("contents") or []
        chapters: list[dict[str, Any]] = []
        for item in items:
            marker = item.get("macroMarkersListItemRenderer")
            if not marker:
                continue
            title_blob = marker.get("title") or {}
            title = title_blob.get("simpleText")
            if not title and title_blob.get("runs"):
                title = "".join(r.get("text", "") for r in title_blob["runs"])
            time_blob = marker.get("timeDescription") or {}
            time_text = time_blob.get("simpleText")
            if title and time_text is not None:
                chapters.append(
                    {"title": title, "start_display": time_text, "start_seconds": _parse_time(time_text)}
                )
        if chapters:
            return chapters
    return None


def _parse_time(display: str) -> int | None:
    parts = display.strip().split(":")
    try:
        parts_int = [int(p) for p in parts]
    except ValueError:
        return None
    if len(parts_int) == 2:
        return parts_int[0] * 60 + parts_int[1]
    if len(parts_int) == 3:
        return parts_int[0] * 3600 + parts_int[1] * 60 + parts_int[2]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a YouTube transcript and metadata as JSON."
    )
    parser.add_argument("url", help="YouTube URL or 11-char video ID")
    parser.add_argument("-o", "--output", help="Write to this path instead of stdout")
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Output only the plain-text transcript (legacy behavior; no metadata)",
    )
    args = parser.parse_args()

    video_id = extract_video_id(args.url)
    url = f"https://www.youtube.com/watch?v={video_id}"

    plain, timed = fetch_transcript(video_id)

    if args.plain:
        payload = plain
    else:
        meta = fetch_metadata_ytdlp(url) or fetch_metadata_fallback(url, video_id)
        bundle = {
            "video_id": video_id,
            "url": url,
            **meta,
            "transcript_plain": plain,
            "transcript_timestamped": timed,
        }
        payload = json.dumps(bundle, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w") as f:
            f.write(payload)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
