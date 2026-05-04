---
name: extract-study
description: >
  This skill should be used when the user asks to "extract a study", "summarize this research",
  "make notes from this paper", or provides an academic PDF or research paper. Also triggers
  when the user shares a DOI, PubMed link, or academic URL and wants structured notes.
---

# Extract Academic Study / Research Paper to Structured Markdown

Convert academic papers and research studies into clean, structured Markdown summaries optimized for understanding and reference. This is a **comprehension and synthesis** task — you are reading and interpreting scientific content, not just copying abstracts.

## When to Use

- User provides an academic PDF, DOI, or research paper URL
- User says "extract this study", "summarize this research", "make notes from this paper"
- User shares PubMed, arXiv, or journal links
- User wants a structured reference from scientific literature

**Use extract-book instead for:** non-academic books, business books, self-help, memoirs.

## What You Produce

A clean Markdown document with:
- **Citation** (full reference)
- **Plain-Language Summary** (what this study found, in plain English)
- **Background & Context** (why this research matters)
- **Methods** (how the study was conducted)
- **Key Findings** (the results, in clear language)
- **Limitations** (what the study can't tell us)
- **Implications** (what this means in practice)
- **Notable Quotes** (striking passages from the paper)

---

## Step 1: Get the Paper Content

### If user provides a PDF:

Run the helper script:

```bash
python3 .claude/skills/extract-study/scripts/extract_study_pdf.py <pdf_path>
```

Capture the output and proceed to Step 2.

### If user provides a URL or DOI:

Fetch the page using your web tools. Look for:
- The abstract
- Full text (if open access)
- PDF link to download

If only the abstract is available, extract what you can and note the limitation.

### If user pastes content directly:

Use it as-is.

---

## Step 2: Structure the Content

### Rules:

1. **Plain language first** — translate jargon into clear English
2. **Separate findings from interpretation** — what did they find vs. what does it mean
3. **Flag limitations honestly** — all studies have them; surface the important ones
4. **Preserve precision** — keep exact numbers, effect sizes, p-values where relevant
5. **Quote sparingly** — only use verbatim quotes for genuinely precise or important statements

### Section Template:

```markdown
# [Paper Title]

**Authors:** [Author list]
**Published:** [Journal, Year]
**DOI/Link:** [URL or DOI]

## Plain-Language Summary
[2–4 sentences. What did this study find, in plain English? Skip jargon.]

## Background & Context
[Why was this study done? What problem does it address?]

## Methods
- **Study type:** [RCT / observational / meta-analysis / etc.]
- **Sample:** [n=X, demographics]
- **Duration:** [if applicable]
- **Key measures:** [what they measured]

## Key Findings
- [Finding #1 with specific numbers where relevant]
- [Finding #2]
- [...]

## Limitations
- [Limitation #1]
- [Limitation #2]

## Implications
[What does this mean in practice? For whom? What should change?]

## Notable Quotes
> "[Verbatim quote]" — p. [page] or [section]
```

---

## Step 3: Save to Google Drive

### 3a. Create a Google Doc

- **Title:** `"[First Author] ([Year]) — [Short Title]"`  
  e.g., `"Walker et al. (2017) — Sleep and Memory Consolidation"`
- **Content:** The full structured Markdown from Step 2
- **Folder:** Save to the user's "Research Notes" folder in Drive (create if needed)

### 3b. Confirm with the user

```
Done! I've extracted and structured the study.

📄 **[Doc Title]**
🔗 [Google Doc link]
📁 Saved to: Research Notes/

Let me know if you'd like any section expanded or the methods explained further.
```

---

## Quality Checklist

- [ ] Citation is complete and accurate
- [ ] Plain-language summary is genuinely plain (no jargon)
- [ ] Methods section captures study design accurately
- [ ] Findings include specific numbers where available
- [ ] Limitations are honest and complete
- [ ] Implications are grounded (not overstated)
- [ ] Document saved to Drive and link confirmed

---

## Edge Cases

| Situation | Handling |
|---|---|
| Only abstract available | Extract it; note full text wasn't accessible |
| Paywalled paper | Extract from abstract + any visible content; tell user |
| Meta-analysis | Focus on pooled findings and forest plot results |
| Preprint (not peer reviewed) | Flag clearly: "Note: This is a preprint." |
| Non-English paper | Extract in original; offer translation summary |
| Very technical methods | Simplify; preserve key design elements |
