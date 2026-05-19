# Translate an existing article

A version of this article exists in `{source_lang}` (shown below). Translate it into {language}, preserving fidelity to the original:

- Keep all facts, dates, names, and citation markers `[^N]` intact.
- Preserve the reference list with the same URLs (sources don't change with translation).
- Preserve `created:` from the source frontmatter. Add `updated: {today}`.
- Set the frontmatter `language:` field to `{language}`.
- Translate the `title:` field appropriately for {language}.
- Translate section headers into {language} (e.g. "Overview" → "概要" in Japanese, "Aperçu" in French).

Verify before you translate:

- Use your tools to confirm the standard {language} forms of proper nouns, technical terms, and naming conventions.
- If authoritative {language} sources exist (e.g. {language} Wikipedia), add them to the reference list.
- Do not invent new claims, restructure sections, or omit content. Translate, with verification — not a rewrite.

Output a complete article in the structure required above.

## Source article (in `{source_lang}`)

```markdown
{translate_from}
```
