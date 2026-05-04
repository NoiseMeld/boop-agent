---
name: extract-book
description: >
  This skill should be used when the user asks to "convert a PDF", "extract a book",
  "make notes from this PDF", or provides a PDF file path or attachment. Also triggers
  when the user says "here's a book" or "can you summarize this PDF" with a file.
---

# Extract Book / PDF to Structured Markdown

Convert book PDFs into clean, structured Markdown with chapter-by-chapter notes, key insights, and actionable takeaways. This is a **reasoning and synthesis** task — you are reading and understanding the content, not just copying text.

## When to Use

- User provides a PDF file path or attachment
- User says "extract this book", "make notes from this PDF"
- User shares a book and wants chapter summaries
- User wants a structured reference document from a PDF

## What You Produce

A clean Markdown document with:
- **Title & Author**
- **Book Summary** (3–5 sentences, the essence of the book)
- **Core Thesis** (1 paragraph, the central argument)
- **Chapter-by-Chapter Notes** (structured summaries per chapter)
- **Key Insights** (10–20 bullets across the whole book)
- **Notable Quotes** (verbatim, only genuinely striking ones)
- **Action Items / Takeaways** (practical applications)

---

## Step 1: Extract Text from PDF

Run the helper script to extract text from the PDF:

```bash
python3 .claude/skills/extract-book/scripts/extract_book_pdf.py <pdf_path>
```

The script outputs structured text to stdout, with page numbers and chapter markers where detectable. Capture it and proceed to Step 2.

**If the script fails:**
- Check that the PDF path is correct and the file exists
- Some PDFs are image-based (scanned) — if so, tell the user: "This PDF appears to be scanned and I can't extract text from it directly."
- For image PDFs, suggest using an OCR tool or ask if they can provide a text version

---

## Step 2: Structure the Content

This is a **synthesis** task. You are reading the extracted text and writing a structured reference document.

### Rules:

1. **Identify chapters** — use the table of contents or chapter headings in the text
2. **Summarize each chapter** — 3–8 bullets per chapter, capturing the key ideas
3. **Extract the thesis** — what is the book's central argument?
4. **Pull key insights** — the most important, memorable, actionable ideas
5. **Quote sparingly** — only use verbatim quotes if they're genuinely memorable
6. **Preserve accuracy** — never change the author's meaning

### Section Template:

```markdown
# [Book Title]
**Author:** [Author Name]
**Year:** [Publication Year]

## Book Summary
[3–5 sentences. What is this book about? What is the main takeaway?]

## Core Thesis
[One paragraph. The central argument or claim of the book.]

## Key Insights
- [Crisp insight #1]
- [Crisp insight #2]
- [...up to 20]

## Chapter Notes

### Chapter 1: [Title]
- [Key point]
- [Key point]
- [Key point]

### Chapter 2: [Title]
- [Key point]
- [Key point]

[...continue for all chapters]

## Notable Quotes
> "[Verbatim quote]" — p. [page number]

## Takeaways / Action Items
- [Practical application]
- [Practical application]
```

---

## Step 3: Save to Google Drive

### 3a. Create a Google Doc

Use the Google Docs tool to create a new document:

- **Title:** `"[Book Title] — Notes"` (e.g., `"Atomic Habits — Notes"`)
- **Content:** The full structured Markdown from Step 2
- **Folder:** Save to the user's "Book Notes" folder in Drive (create it if it doesn't exist)

### 3b. Confirm with the user

After saving, reply with:

```
Done! I've extracted and structured the book.

📄 **[Doc Title]**
🔗 [Google Doc link]
📁 Saved to: Book Notes/

Let me know if you'd like any chapters expanded or sections added.
```

---

## Quality Checklist

Before saving, verify:
- [ ] Title and author are correct
- [ ] All chapters are covered
- [ ] Summary is accurate and concise
- [ ] Core thesis is clearly stated
- [ ] Key insights are distinct and valuable
- [ ] Quotes are verbatim and worth including
- [ ] Action items are practical
- [ ] Document saved to Drive and link confirmed

---

## Edge Cases

| Situation | Handling |
|---|---|
| Scanned/image PDF | Tell user; suggest OCR or text version |
| PDF with no chapter headings | Infer structure from content flow |
| Very long book (500+ pages) | Summarize at chapter level; don't skip chapters |
| Academic paper (not a book) | Use extract-study skill instead |
| Multiple PDFs | Process each separately; offer to combine notes |
