# AI-tell word lists

These are words and phrases that are statistically overused by current large language models. Use this file as a reference during Pass 3 (Vocabulary) and Pass 9 (Wikipedia editor patterns) of the humanize skill.

## Tier 1 — Red flag words

Almost always an AI tell. Cut or replace these on sight. Rare exceptions exist (e.g., "ecosystem" when literally discussing biology, "navigate" when literally describing map use), but default to removing them.

- delve
- delving
- tapestry
- leverage (as verb)
- leveraging
- harness (as verb)
- harnessing
- navigate (metaphorical)
- navigating
- realm
- myriad
- plethora
- multifaceted
- groundbreaking
- revolutionize
- revolutionary
- synergy
- synergistic
- ecosystem (metaphorical)
- resonate
- resonating
- streamline
- streamlining
- paradigm
- paradigm shift
- elevate
- elevating
- unlock (metaphorical)
- unleash
- landscape (metaphorical)
- testament (as in "stands as a testament to")
- interplay
- meticulous
- meticulously
- nestled
- vibrant
- pivotal
- enduring
- showcasing
- showcase (as verb)
- garner
- garnered
- boasts (as in "the city boasts")
- spearheaded

**Replacement patterns:**
- "leverage our network" -> "use our network"
- "harness the power of X" -> "use X"
- "a myriad of options" -> "many options" or "dozens of options"
- "delve into" -> "look at" or "examine"
- "streamline the process" -> "simplify the process" or "speed up the process"
- "navigate complexity" -> "deal with complexity" or "work through the complexity"
- "unlock value" -> "create value" or just describe the value
- "the tapestry of X" -> just describe X
- "stands as a testament to" -> "shows" or just delete
- "the city boasts" -> "the city has"
- "garnered attention" -> "got attention" or "drew attention"
- "nestled in the hills" -> "in the hills" or "set in the hills"
- "showcasing X" -> "showing X" or just describe X directly

## Tier 2 — Cluster words

OK on their own. Bad in clusters. If two or more appear within the same paragraph, replace one or more.

- robust
- seamless
- seamlessly
- cutting-edge
- state-of-the-art
- innovative
- innovation
- comprehensive
- nuanced
- compelling
- transformative
- bolster
- bolstering
- underscore
- underscoring
- evolving
- ever-evolving
- fostering
- foster (as verb)
- imperative (as noun, "It is imperative...")
- intricate
- overarching
- unprecedented
- holistic
- holistically
- dynamic (as adjective)
- robustness
- synergize
- empower
- empowering
- facilitate
- facilitating
- diverse (when used as filler adjective)
- rich (metaphorical: "rich history," "rich cultural heritage")
- broader (as in "contributes to the broader")
- notable
- notably
- significant
- significantly
- highlight
- highlighting
- valuable
- key (as adjective, overused)
- align (as in "align with goals")
- commitment (as in "commitment to excellence/sustainability")

## Tier 3 — Red flag phrases

Specific multi-word constructions that signal LLM output:

### Opening/transition filler
- "In today's fast-paced world"
- "In the modern era"
- "In an ever-changing landscape"
- "It is important to note that"
- "It is worth noting that"
- "It goes without saying"
- "Needless to say"
- "At the end of the day"
- "When all is said and done"
- "For all intents and purposes"
- "In essence"
- "Essentially"
- "Fundamentally"
- "Ultimately" (when used as filler)
- "It's no secret that"
- "The fact of the matter is"
- "Let's dive in"
- "Let's delve into"
- "Buckle up"
- "Without further ado"
- "In conclusion" (in anything under 2,000 words)
- "To sum up"
- "All things considered"
- "That being said"
- "With that said"
- "Moving forward" (when used as filler)
- "Going forward" (when used as filler)

### Promotional/puffery phrases
- "a diverse array of"
- "a wide range of"
- "a unique blend of"
- "natural beauty"
- "rich cultural heritage"
- "rich history"
- "commitment to excellence"
- "commitment to sustainability"
- "commitment to innovation"
- "continues to thrive"
- "continues to evolve"

### Broader-topic linking phrases
- "stands as a testament to"
- "serves as a testament to"
- "contributes to the broader"
- "reflects the rich cultural heritage"
- "setting the stage for"
- "paving the way for"
- "plays a crucial role in"
- "plays a vital role in"
- "remains a cornerstone of"

### Vague attributions
- "experts argue"
- "experts say"
- "industry reports suggest"
- "several sources indicate"
- "according to various sources"
- "research suggests" (without citing specific research)
- "studies have shown" (without citing specific studies)

### Challenge/future formula
- "Despite its [positive noun], [subject] faces challenges..."
- "While challenges remain, [subject] continues to..."
- "Looking ahead, [subject] is poised to..."
- "As [subject] continues to grow..."
- "The future of [subject] looks promising"

## Tier 4 — Structural tells

Not words but patterns:

- **Triadic constructions**: "X, Y, and Z" repeated through a piece. Vary with pairs, quartets, or single items.
- **Parallel opening phrases**: every bullet starting with the same part of speech ("Understanding X, Identifying Y, Implementing Z").
- **Recap before conclusion**: "In summary, we've discussed X, Y, and Z..." -- a hallmark of LLM output.
- **Hedge + hedge**: "might potentially," "could possibly," "perhaps might."
- **Quantity without specificity**: "a number of," "several," "various" when an actual number is knowable.
- **Rhetorical questions the writer immediately answers**: "But what does this really mean? It means..."
- **Em dash as universal connector**: using -- everywhere a comma, period, colon, or rewrite would serve.
- **Bold-header list format**: Using **Term:** followed by a description, repeated down the page. Real writers use paragraphs, not definition-list formatting.
- **Title case in every heading**: Wikipedia editors flag excessive title-casing in section headings as an AI marker.

## Tier 5 — Sentence-level construction tells

Patterns at the sentence and clause level that are distinctly machine-generated:

### Trailing present participial clauses
Sentences that end with ", creating...", ", enabling...", ", ensuring...", ", making it...", ", contributing to...". One per page is fine. Three per page is an AI tell. LLMs use these as a crutch to link cause and effect without writing a new sentence.

**Examples:**
- "The team redesigned the interface, creating a more intuitive experience." -> "The team redesigned the interface. Users found it more intuitive."
- "We automated the pipeline, reducing errors by 40%." -> Fine on its own. Bad when every other sentence ends this way.

### Negative parallelisms
"Not just X, but Y" / "Not only X, but also Y" used repeatedly. Humans use this construction occasionally. LLMs lean on it hard, especially in persuasive writing.

### Copulative avoidance
LLMs avoid "is" and "are" by substituting fancier verbs: "serves as," "stands as," "functions as," "operates as," "features," "offers." One or two is fine. When every sentence dodges "is," it's a tell.

**Example:**
- "The dashboard serves as a central hub for analytics." -> "The dashboard is where the team checks analytics."

### Elegant variation
Cycling through synonyms for the same concept within a few paragraphs instead of repeating the plain term. A building becomes "the structure," then "the edifice," then "the facility." Real writers repeat key nouns; LLMs rotate through thesaurus entries.

### Doubled hedging
"It might potentially," "could perhaps," "may possibly." Pick one hedge or none.

## Safe replacements

General-purpose substitutions that tend to humanize prose:

| AI-ish | More human |
|---|---|
| utilize | use |
| in order to | to |
| at this point in time | now |
| due to the fact that | because |
| a large number of | many, dozens of, hundreds of |
| in the event that | if |
| for the purpose of | for, to |
| with regard to | about, on |
| in spite of | despite |
| prior to | before |
| subsequent to | after |
| at the present time | now |
| in close proximity to | near |
| in the vicinity of | near |
| a majority of | most |
| on a daily basis | daily |
| on a regular basis | regularly |
| in the process of | (often delete entirely) |
| it should be noted that | (delete) |
| serves as | is |
| stands as | is |
| a diverse array of | many, several |
| a wide range of | many, various |
| plays a crucial role in | matters for, helps with |
| remains a cornerstone of | is central to, is key to |
