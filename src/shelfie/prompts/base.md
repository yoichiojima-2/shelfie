Write an encyclopedia article on **{topic}** for the user's personal knowledge library — their own Wikipedia. Research the topic using the tools provided, then write a single Markdown page that reads like a Wikipedia article: neutral, structured, well-cited, self-contained.

# Research

- Use `web_search` to gather facts. Issue multiple queries from different angles (history, key figures, technical details, current state, debates).
- If `x_search` is available, use it sparingly — only for recent opinion, news reactions, or first-hand accounts. Always attribute X content.
- Do not invent facts. If a claim has no source, leave it out.

# Output

Return **only** the Markdown article. No preamble, no postscript, no code fences wrapping the whole thing.

## Required structure

Omit any section that has no content rather than padding it.

1. YAML frontmatter with: `title`, `created: {today}`, `sources_count`, `tags` (3–7 lowercase).
2. `# {topic}` (H1).
3. `## Overview` — 2–4 sentence lead.
4. `## Background` — origin, history, prerequisites.
5. `## Details` — substantive body, H2/H3 as needed.
6. `## Debates and Open Questions` — contested claims.
7. `## Related Topics` — bulleted list of adjacent topics as Obsidian wikilinks (`[[slug]]`). Prefer linking to articles listed under "Existing articles in this vault" (below) when relevant; ghost wikilinks to not-yet-written topics are encouraged.
8. `## References` — numbered list of all cited sources with URLs.

## Citation rules

- Every factual claim has an inline `[^N]` citation matching an entry in `## References`.
- Reputable web sources and Wikipedia → cite as fact.
- X posts → attribute: "According to @user on X, ...". Never present as fact.
- Conflicting sources → present both views explicitly.
- Single-source claim from X, blog, or forum → mark as "reportedly" or "according to".

## Language and tone

- Language: {language}.
- Tone: {tone}. Neutral, third person, encyclopedic. No first person. No editorializing.
- Define jargon on first use.

## Length

- 400–1200 words depending on source richness. Do not pad.
- Thin sources → write a short article and add "Coverage is limited; few sources available." near the top.

## What NOT to do

- No invented facts, dates, names, or quotes.
- No long verbatim passages. Paraphrase. Direct quotes only when wording matters, under 15 words.
- No meta-commentary ("Source 1 says... Source 2 says..."). Write the article.
- No inline external links in the body — use `[^N]` and put URLs in `## References`.
