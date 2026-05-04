---
name: extract-transcript
description: >
  This skill should be used when the user asks to "extract a transcript", "summarize this video",
  "make a doc from this transcript", or provides a YouTube URL, podcast transcript, or timestamped
  spoken-word content. Also triggers when the user pastes a raw transcript, mentions "here's a video
  from Dr. [name]", or drops a YouTube link without explicitly asking for extraction.
---

# Extract Video/Podcast Transcript to Structured Markdown

Convert raw transcripts (YouTube, podcast, interview) into clean, structured Markdown summaries. Unlike study extraction, this is a reasoning task — the transcript is messy spoken-word content that needs to be understood, organized, and summarized, not just reformatted.

## When to Use

- User pastes a raw transcript (timestamped or plain)
- User shares a YouTube URL and wants a summary or notes
- User mentions a speaker/video and wants key points extracted
- User says "make a Google Doc from this transcript"
- User provides podcast content to be structured

## What You Produce

A clean Markdown document with:
- **Title** (inferred from content)
- **Source** (URL or speaker/show if known)
- **Summary** (2–4 sentences, the essence of the talk)
- **Key Insights** (5–10 bullets, each a single crisp idea)
- **Core Argument** (1 paragraph, the central thesis or throughline)
- **Supporting Points** (structured outline, grouped by topic)
- **Notable Quotes** (verbatim, only if genuinely striking)
- **Action Items / Takeaways** (if applicable)

---

## Step 1: Get the Transcript

### If user provides a YouTube URL:

Run the helper script to fetch the transcript automatically:

```bash
python3 .claude/skills/extract-transcript/scripts/get_transcript.py <youtube_url>
```

The script outputs the raw transcript to stdout. Capture it and proceed to Step 2.

**If the script fails** (no captions, private video, etc.):
- Tell the user: "I couldn't auto-fetch the transcript. Please paste it directly."
- Wait for the user to paste the transcript, then continue.

### If user pastes a transcript directly:

Use it as-is. No script needed.

---

## Step 2: Extract and Structure

This is **not** a find-and-replace task. You are reading and understanding the content, then writing a clean document.

### Rules:

1. **Remove all timestamps** — strip `[00:00]`, `(0:00)`, `00:00:00` etc.
2. **Merge fragmented sentences** — transcripts break mid-thought; reassemble them.
3. **Filter filler** — remove "um", "uh", "you know", "like", false starts, repeated words.
4. **Infer structure** — identify topic shifts and group content into logical sections.
5. **Preserve meaning** — never change what was said, only how it's presented.
6. **Quote sparingly** — only use verbatim quotes if they're genuinely memorable.

### Section Template:

```markdown
# [Title — inferred from content]

**Source:** [URL or "Speaker Name, Show/Podcast, Date"]

## Summary
[2–4 sentences. What is this about? What is the main takeaway?]

## Key Insights
- [Crisp insight #1]
- [Crisp insight #2]
- [...up to 10]

## Core Argument
[One paragraph. The central claim or thesis of the talk.]

## Supporting Points

### [Topic Group 1]
- [Point]
- [Point]

### [Topic Group 2]
- [Point]
- [Point]

## Notable Quotes
> "[Verbatim quote]" — [Speaker, if known]

## Takeaways / Action Items
- [If applicable]
```

---

## Step 3: Save to Google Drive

### 3a. Create a Google Doc

Use the Google Docs tool to create a new document:

- **Title:** Use the inferred title from the transcript (e.g., `"Why Sleep Matters — Dr. Matthew Walker"`)
- **Content:** The full structured Markdown from Step 2
- **Folder:** Save to the user's "Transcripts" folder in Drive (create it if it doesn't exist)

### 3b. Confirm with the user

After saving, reply with:

```
Done! I've extracted and structured the transcript.

📄 **[Doc Title]**
🔗 [Google Doc link]
📁 Saved to: Transcripts/

Let me know if you'd like any sections expanded or reformatted.
```

---

## Quality Checklist

Before saving, verify:
- [ ] All timestamps removed
- [ ] Filler words stripped
- [ ] Sentences are complete and grammatically clean
- [ ] Sections are logical and well-labeled
- [ ] Summary is accurate and concise
- [ ] Key Insights are distinct (no overlaps)
- [ ] Quotes are verbatim and worth including
- [ ] Document saved to Drive and link confirmed

---

## Edge Cases

| Situation | Handling |
|---|---|
| No captions on YouTube | Ask user to paste transcript |
| Auto-generated captions (garbled) | Do your best; flag uncertain sections |
| Very short clip (<5 min) | Still structure it, skip sections that don't apply |
| Long lecture (>1 hr) | Break into multiple sections; summarize each |
| Multiple speakers | Label speakers in quotes; merge otherwise |
| Non-English content | Extract in original language; offer translation if asked |
