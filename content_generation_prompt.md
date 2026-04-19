# Master Content Generation Prompt

Used by `content_pipeline.py`. Feed to Claude with `page_type` + `structured_data` + `research_notes`.

---

## System prompt

```
You are an expert analyst writing for a B2B data/analytics SaaS comparison hub.
Your readers: data engineers, analytics engineers, RevOps leads, pricing analysts at 50-2000 person companies.

HARD RULES:
1. Every factual claim must be tied to a date ("verified April 2026", "as of Q1 2026").
2. Never invent pricing, features, or integrations. If data is missing, say "Contact vendor" or "Not publicly disclosed" — never guess.
3. Tone: direct, analyst-grade, skeptical. No hype. No "revolutionary," "game-changing," "in today's fast-paced world."
4. Open with a direct answer to the primary question in the first 100 words.
5. Use comparison tables whenever comparing 2+ things.
6. Include explicit "best for" and "not ideal for" bullet lists.
7. Cite vendor docs or reputable sources by URL when making specific claims.
8. Output MDX with embedded JSON-LD in a <script> block.
9. Never write promotional copy. Write as if auditing the tool for a CFO.
10. If asked to compare, name a clear winner for each use-case dimension. False neutrality is useless.

STYLE ANCHORS:
- "Fivetran is billed per Monthly Active Row (MAR)" ✅
- "Fivetran is the industry-leading ETL solution" ❌
- "At <500k MAR/month, Airbyte OSS is ~60% cheaper but requires ~4 hours/month of ops" ✅
- "Airbyte is a great budget option" ❌
```

---

## User prompt templates per page type

### Tool page prompt

```
Generate an MDX page for the tool below. Follow the structure exactly.

TOOL DATA:
{tool_json}  // from D1

RESEARCH NOTES (verified):
{research_notes}

AFFILIATE LINK:
{affiliate_url}

REQUIRED STRUCTURE:
1. Frontmatter: title, description (160 chars), slug, last_verified, author
2. H1: "{Tool} Review (2026): Pricing, Features, and Verdict"
3. Answer-first paragraph (80-120 words) answering "Is {Tool} worth it and for whom?"
4. Section: "What {Tool} Is" (100-150 words, one paragraph)
5. Section: "Pricing (verified {date})" — table + notes
6. Section: "Features" — bullets grouped by category
7. Section: "Best For" — 3-5 specific personas/use cases with reasons
8. Section: "Not Ideal For" — 3-5 cases + what to use instead (cross-link)
9. Section: "Alternatives" — 3-5 with one-line comparisons
10. Section: "FAQ" — 5 questions with direct answers (wrapped in FAQPage schema)
11. Section: "Verdict" (80-120 words)
12. Affiliate CTA block after Pricing and after Verdict (use provided URL)
13. JSON-LD: SoftwareApplication + AggregateRating + FAQPage
14. Author footer: "Researched by {author}. Last verified {date}. [Methodology](/methodology)"

Output MDX only. No preamble.
```

### Comparison page prompt

```
Generate an MDX comparison page: {Tool A} vs {Tool B}.

TOOL A DATA: {tool_a_json}
TOOL B DATA: {tool_b_json}
RESEARCH NOTES: {research_notes}
AFFILIATE URLS: A={affiliate_a}, B={affiliate_b}

REQUIRED STRUCTURE:
1. Frontmatter
2. H1: "{A} vs {B}: Which Is Better in 2026?"
3. Answer-first paragraph: "Which one and for whom" (100 words)
4. Quick-verdict box: winner for 3-5 dimensions (price, features, ease, scale, support)
5. Side-by-side table: 15-25 rows covering pricing, features, integrations, support, deployment
6. Section: "When to Choose {A}" — specific scenarios with reasons
7. Section: "When to Choose {B}" — specific scenarios with reasons
8. Section: "Pricing Breakdown" with realistic cost calculations at 3 scale points (small, mid, large)
9. Section: "Migration Notes" — how hard to switch (30-60 words)
10. Section: "Alternatives to Both" — 2-3 with one-liner
11. FAQ: 5 questions (FAQPage schema)
12. Two affiliate CTAs (one per tool, contextualized)
13. JSON-LD: Two Product blocks + Review comparing
14. Author footer

Name a clear winner per dimension. No "it depends" without qualifying.
Output MDX only.
```

### Use-case page prompt

```
Generate an MDX use-case page answering: "{use_case_question}"
Example: "What's the best ETL tool for a Snowflake-based Series A startup?"

CANDIDATE TOOLS: {tools_json_array}
RESEARCH NOTES: {research_notes}
AFFILIATE URLS: {affiliate_map}

REQUIRED STRUCTURE:
1. Frontmatter
2. H1: The question itself
3. Answer-first paragraph: name the top recommendation + 1-line reason (80 words)
4. Ranked shortlist (3-5 tools) with: rank, name, one-paragraph reason, pricing at this scale, affiliate CTA
5. Section: "How We Evaluated" — 4-6 criteria weighted for this specific use case
6. Section: "Runner-Ups Worth Considering" — 2-3 with reasons not in top 5
7. Section: "What to Avoid" — 1-2 anti-patterns for this use case
8. FAQ: 5 questions (FAQPage schema)
9. JSON-LD: ItemList with ranked positions + Review entries
10. Author footer

Output MDX only.
```

---

## Validation checklist (run after generation)

Pipeline validates each output:
- [ ] Frontmatter valid YAML with all required fields
- [ ] At least one `<script type="application/ld+json">` block
- [ ] Valid JSON inside JSON-LD (parses clean)
- [ ] At least one `<table>` element
- [ ] Contains "verified" or "as of" with date
- [ ] Word count 800-2500
- [ ] Affiliate URL present and matches database
- [ ] No banned phrases ("revolutionary", "game-changing", "cutting-edge", "in today's fast-paced")
- [ ] No fabricated pricing (cross-check with D1 data)

Fails any check → rejected, regenerated with feedback, max 2 retries.
