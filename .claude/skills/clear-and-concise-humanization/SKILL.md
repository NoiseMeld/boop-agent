---
name: clear-and-concise-humanization
description: >
  Write and edit prose so it is clear, concise, and human. Merges Strunk's
  composition rules with a ten-pass system for stripping AI tells. Use this
  skill whenever drafting, writing, revising, polishing, or rewriting ANY
  prose — documents, proposals, emails, blog posts, reports, memos, LinkedIn
  posts, Slack messages, case studies, cover letters, newsletters,
  presentations, or any long-form writing — even when the user doesn't
  explicitly ask to humanize or strip AI-isms. Apply automatically to any
  writing task producing more than a few sentences. Trigger phrases include
  "draft", "write", "revise", "polish", "rewrite", "edit", "tighten",
  "un-ai this", "make it sound human", "make it sound less like AI",
  "humanize", "clean up this copy", "fix this writing", "proofread",
  "make this clearer", "make this more concise", or any prose creation or
  revision request. Also trigger when reviewing a document that appears to
  have been AI-generated, regardless of whether the user explicitly requested
  humanization.
---

# Clear and concise humanization

Write prose that is clear, forceful, and unrecognizable as machine-generated. This skill combines two things: William Strunk's composition rules (what good prose does) and a structured editing pass system (what AI prose does wrong and how to fix it).

This is an editing pass, not a rewrite from scratch. Preserve the author's meaning, structure, and level of formality. Only change what makes the text weak, vague, or machine-sounding.

## When to use this

Apply to the final draft of any prose output before presenting it. Also apply retroactively when a user hands you a document and says some version of "this sounds like AI wrote it" or "clean this up."

Signals:
- The user asks for a document, email, proposal, post, or any prose deliverable.
- The user says "polish this," "revise this," "clean this up," or "make this clearer."
- The user mentions AI tells, or says "sound less like AI."
- A document was produced earlier in the conversation and is about to go to a real human reader.

Do not apply to: bullet-point notes the user is clearly keeping for themselves, code comments, technical API documentation, or highly templated legal language where deviation would be incorrect.

## The Strunk foundation

Every pass below builds on Strunk's core principles. You do not need to memorize them; they are summarized here and the full text with examples lives in `references/elements-of-style/`. When in doubt about a specific rule, read the relevant section file.

### The rules that matter most

These six rules do most of the work. The passes below apply them:

- **Use active voice** (Rule 10). "Dead leaves covered the ground" not "There were a great number of dead leaves lying on the ground."
- **Put statements in positive form** (Rule 11). "He usually came late" not "He was not very often on time." Use *not* for denial or antithesis, never evasion.
- **Use definite, specific, concrete language** (Rule 12). "It rained every day for a week" not "A period of unfavorable weather set in."
- **Omit needless words** (Rule 13). A sentence should contain no unnecessary words, a paragraph no unnecessary sentences, for the same reason that a drawing should have no unnecessary lines. This does not mean all sentences should be short, but that every word should tell.
- **Keep related words together** (Rule 16). The subject and verb should not be split by a clause that could move to the beginning.
- **Place emphatic words at the end** (Rule 18). The end of the sentence is its strongest position. Put the new or important information there.

### The supporting rules

- **One paragraph per topic** (Rule 8). Each paragraph signals a new step for the reader.
- **Begin paragraphs with a topic sentence** (Rule 9). The reader should know the purpose of each paragraph as it begins.
- **Avoid a succession of loose sentences** (Rule 14). Sentences strung together with "and," "but," "so," "which" become monotonous fast.
- **Express coordinate ideas in similar form** (Rule 15). Parallel content gets parallel structure.
- **Keep to one tense in summaries** (Rule 17).

### Reference files

| Section | File | When to consult |
|---------|------|-----------------|
| Grammar and punctuation | `references/elements-of-style/02-elementary-rules-of-usage.md` | Comma questions, possessives, participial phrases |
| Composition principles | `references/elements-of-style/03-elementary-principles-of-composition.md` | Active voice examples, concision examples, paragraph structure |
| Formatting matters | `references/elements-of-style/04-a-few-matters-of-form.md` | Headings, quotations, references |
| Commonly misused words | `references/elements-of-style/05-words-and-expressions-commonly-misused.md` | Specific word-choice questions |
| AI-tell word lists | `references/ai-tells.md` | Pass 3 (vocabulary) and Pass 9 (promotional language) |
| Wikipedia AI detection research | `references/signs-of-ai-writing.md` | Pass 2, 8, 9 (regression to the mean, participials, promotional) |

For most editing tasks, you only need `03-elementary-principles-of-composition.md` and `ai-tells.md`.

## The ten passes

Run these in order. Each pass has a single focus. Don't try to do them all at once.

### Pass 1 — Structure

Look at the shape of the piece. AI writing tends toward uniform paragraphs of 3-5 sentences, heavy subheading use, and triadic structures ("X, Y, and Z" repeated throughout).

Do this:
- Break overly uniform paragraphs. Mix short (1-2 sentences) with longer (5-7). **(Strunk Rule 8: one paragraph per topic.)**
- Kill subheadings that aren't load-bearing. A subheading every 150 words is a tell.
- Look for triadic lists ("smooth, fast, and reliable") and vary them. Two items or four items sometimes.
- If every paragraph starts the same way (topic sentence, explanation, example), break the pattern. **(Strunk Rule 9: begin with a topic sentence, but don't let the pattern become mechanical.)**
- Watch for **bold-header list format** (**Term:** description, repeated down the page). Wikipedia editors specifically flag this. Real writers use paragraphs. Convert to flowing prose unless the content genuinely needs a list.
- Check heading capitalization. LLMs default to Title Case. Use sentence case unless the style guide says otherwise.

### Pass 2 — Significance inflation

The single biggest AI tell. LLMs over-announce importance. They say "crucially," "importantly," "it's worth noting," and frame obvious claims as insights. This is the "regression to the mean" problem described in `references/signs-of-ai-writing.md`: specifics fade into generic importance claims.

Do this:
- Delete sentences that exist only to say "this is important." If something is important, make it important through placement (Strunk Rule 18: emphatic words at the end), not through labeling.
- Kill "it's worth noting that," "importantly," "crucially," "fundamentally," "it should be emphasized that," "notably."
- Cut clauses that restate the obvious. If you just said "the system tracks dumpsters," you don't also need "this enables tracking of dumpsters." **(Strunk Rule 13: omit needless words.)**
- Watch for the setup-payoff pattern where the setup is a platitude: "In today's fast-paced world, X matters." Cut the setup.
- Watch for undue emphasis on symbolism, legacy, and importance. "Stands as a testament to," "plays a vital role in," "reflects the broader" are all AI puffery. **(Strunk Rule 12: use specific, concrete language instead.)**

### Pass 3 — Vocabulary

A specific set of words is heavily overused by LLMs. See `references/ai-tells.md` for the full tiered lists. Cut or replace Tier 1 (red flag) words first. Replace Tier 2 (cluster) words when they appear together in close proximity. One alone is fine; three in a paragraph is AI-speak.

Quick hit list to always interrogate:
- **Tier 1 (almost never keep):** delve, leverage, harness, landscape, tapestry, navigate, realm, myriad, plethora, multifaceted, groundbreaking, revolutionize, synergy, ecosystem, resonate, streamline, testament, interplay, meticulous, nestled, vibrant, showcasing, garner, boasts, spearheaded
- **Tier 2 (OK alone, bad in clusters):** robust, seamless, cutting-edge, innovative, comprehensive, pivotal, nuanced, compelling, transformative, bolster, underscore, fostering, imperative, intricate, overarching, unprecedented, diverse, rich, notable, significant, highlight, valuable, key, align, commitment

Substitution heuristic: if you can replace the word with a plainer synonym without losing meaning, do it. **(Strunk Rule 13: omit needless words. Strunk Rule 12: prefer the concrete to the abstract.)** "Leverage our relationships" becomes "use our relationships." "A robust pipeline" becomes "a reliable pipeline" or just "a pipeline."

Note: AI vocabulary shifts with each model generation. Always interrogate any word that feels like it's decorating rather than communicating.

### Pass 4 — Grammar patterns

LLMs have structural tics separate from vocabulary. Strunk covers most of them:

- **Nominalization**: turning verbs into nouns. "The implementation of the solution" becomes "we built the solution." **(Strunk Rule 13.)**
- **Passive voice by default**: "The report was generated" becomes "I generated the report." **(Strunk Rule 10: use the active voice.)** The passive is fine when the receiver of the action is more important than the actor, but AI defaults to it reflexively.
- **Copula stacking**: "It is important that we are able to ensure that..." becomes "we need to..." **(Strunk Rule 13.)**
- **Superficial -ing phrases**: "Leveraging X, we..." becomes "We used X to..." **(Strunk Rule 7: participial phrase at beginning must refer to the grammatical subject.)**
- **Empty parallelism**: "both in theory and in practice," "both short-term and long-term." Often fluff. **(Strunk Rule 15: express coordinate ideas in similar form, but only when the parallelism carries real content.)**
- **Absent first person**: AI defaults to the passive impersonal. A real writer uses "I," "we," "you." If the piece should have a voice, put the voice in.
- **Copulative avoidance**: LLMs dodge "is" by substituting fancier verbs: "serves as," "stands as," "functions as," "features," "offers." One or two is fine. When every sentence avoids "is," it's a tell. "The dashboard serves as a central hub" becomes "The dashboard is where the team checks analytics."
- **Negative form as evasion**: "He was not very often on time" becomes "He usually came late." **(Strunk Rule 11: put statements in positive form.)**

### Pass 5 — Rhythm and sentence variety

Read the piece aloud in your head. If every sentence has the same length and cadence, break it. **(Strunk Rule 14: avoid a succession of loose sentences.)**

Do this:
- Let some sentences be short. Very short. Three words is fine.
- Let some be long and branching, with subordinate clauses that add real information rather than padding.
- Occasionally start a sentence with "And" or "But."
- Break long sentences into two when they're connected by "and" doing nothing.
- Place the word or phrase you want to land hardest at the end of the sentence. **(Strunk Rule 18.)**

### Pass 6 — Hedging and filler

LLMs hedge excessively: "might," "could potentially," "in some cases," "often," "typically." Some hedging is honest; most is defensive reflex.

Do this:
- For each hedge, ask: is this earning its keep, or is it reflex?
- Delete empty filler phrases: "In essence," "At the end of the day," "When all is said and done," "For all intents and purposes," "It goes without saying," "Needless to say."
- Watch for redundant qualifiers: "very unique," "absolutely essential," "completely finished."
- Watch for doubled hedging: "might potentially," "could perhaps," "may possibly." Pick one hedge or none.
- Put remaining statements in positive form. **(Strunk Rule 11.)** "He did not think that studying Latin was much use" becomes "He thought the study of Latin useless."

Keep hedges that reflect real uncertainty. "Probably" and "I think" are honest. "It might be worth considering that perhaps" is cowardice.

### Pass 7 — Connective tissue

The most visible AI tell in longer prose is em dashes used as all-purpose connectors. LLMs love them.

Do this:
- **Kill em dashes aggressively.** Replace with periods, commas, colons, parentheses, or by rewriting the sentence. One em dash in a 1,000-word document is fine. Ten is a tell.
- Similarly reduce en dashes in ranges when words work: "10-12 weeks" becomes "10 to 12 weeks."
- Vary connectives. Instead of "X, which Y, which Z," break into separate sentences. **(Strunk Rule 16: keep related words together, but don't stack relative clauses.)**
- Avoid "Moreover," "Furthermore," "In addition," "Additionally" at sentence starts. They signal a machine outlining, not a person thinking.

### Pass 8 — Trailing participial clauses

Wikipedia editors specifically watch for this. LLMs end sentences with present participial clauses (", creating...", ", enabling...", ", ensuring...", ", making it...", ", contributing to...", ", providing...") as a crutch to link cause and effect without writing a new sentence.

Do this:
- Count how many sentences end with ", [verb]-ing...". More than one per page is suspicious. More than two is a tell.
- Replace by splitting into two sentences, or rewrite the cause-effect relationship.
- "The team redesigned the interface, creating a more intuitive experience." becomes "The team redesigned the interface. Users found it more intuitive."
- "We automated the pipeline, reducing errors by 40%." Fine as a one-off. Bad when every other sentence ends this way.

Also watch for **negative parallelisms** as a repeated device: "Not just X, but Y" / "Not only X, but also Y." Humans use this occasionally. LLMs lean on it hard. If you see it more than once in a piece, cut at least one instance.

### Pass 9 — Promotional language and vague attribution

Wikipedia editors developed this detection category because LLMs produce writing that reads like tourism brochures or press releases. This pass catches puffery and unsupported claims. See `references/signs-of-ai-writing.md` for the full research.

Do this:
- **Kill promotional phrasing.** "A diverse array of," "a unique blend of," "continues to thrive," "commitment to excellence," "rich cultural heritage," "natural beauty." Replace with specifics or delete. **(Strunk Rule 12: definite, specific, concrete.)**
- **Kill elegant variation.** If you're writing about a building, call it "the building" every time. Don't cycle through "the structure," "the edifice," "the facility," "the property." Real writers repeat key nouns. LLMs rotate through thesaurus entries.
- **Fix vague attributions.** "Experts argue," "industry reports suggest," "several sources indicate," "research suggests" without citing specific research. Either cite a real source or cut the attribution. "Studies show" with no citation is worse than just stating the claim.
- **Kill the challenge/future formula.** "Despite its [positive qualities], [subject] faces challenges such as [list]. Looking ahead, [subject] is poised to [optimistic verb]." This conclusion template appears in almost all AI descriptive writing. Cut it or rewrite with actual specific information.
- **Kill broader-topic linking.** "Contributes to the broader," "reflects the rich cultural heritage of," "plays a crucial role in," "remains a cornerstone of" are filler that connects a specific topic to a vague larger theme. Make the connection concrete or delete. **(Strunk Rule 12.)**

### Pass 10 — Soul

The previous nine passes remove what's wrong. This pass adds what's right.

Do this:
- Find one or two places where the author would naturally add a specific detail, aside, or opinion. Add it.
- Look for abstractions and replace them with concrete nouns. "Stakeholders" becomes "Bill and Tony." "The system" becomes "the admin dashboard." **(Strunk Rule 12.)**
- If the piece should feel warm, put a warm sentence in. If confident, let one sentence land a confident claim without hedging.
- Ask: does this read like it came from a human who cares about the topic and the reader? If not, something is still mechanical.

Don't overdo this pass. One or two human moments per page is plenty.

## Editing mode vs. drafting mode

When **drafting**, keep all ten passes and the Strunk rules in the back of your mind but write first, revise second. Don't try to write humanized prose from the start; it makes output stiff. Write naturally, then apply the passes.

When **editing** an existing document, work through the passes explicitly. Read the piece once for each pass.

## Output format

When the user asks for a humanized or edited version, also produce a short **Changes** table:

| Pass | Changes made |
|---|---|
| Structure | (bulleted summary) |
| Significance inflation | (bulleted summary) |
| ... | ... |

Only include passes where you actually made changes. If a pass had nothing to fix, leave it out.

## What this skill is not

This skill is **not** about making writing casual, slangy, or chatty. A legal contract can be humanized without becoming informal. A board memo can be humanized and still be appropriate for a board.

This skill is **not** about inserting personality where there wasn't any. If the author's voice is understated, keep it understated. Humanization means removing the AI residue, not applying a new flavor.

This skill is **not** about length. Humanized writing can be shorter or longer than the AI version. Don't pad, don't compress. Let the prose be the length the argument needs. As Strunk says: this requires not that the writer make all sentences short, but that every word tell.
