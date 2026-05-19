# Resolve the user's topic input

The user is about to add an article in `{language}`. They typed:

    {topic}

The shelf already contains these articles in `{language}` (`slug — title`):

{inventory}

Slugs are language-independent identifiers. The user picks an input in whatever script they prefer (often ASCII English) regardless of the article's body language. **Never translate** the input across languages or scripts: an English input in a `ja` session is not a typo of its Japanese name, and a Japanese inventory entry titled `仏教` is not a duplicate of the English input `buddhism`. Translation is never a correction.

Decide which of the following best describes the user's input:

1. **typo** — the input is a clear, unambiguous misspelling of a known concept, in the same script as the user typed. Examples: `buddism` → `buddhism`, `einsteen` → `einstein`. The `corrected_topic` MUST be in the same script as the input. Do not "correct" valid alternate names, archaic forms, or proper-noun variants you are merely unsure about, and do not propose a translation as a correction (e.g., `buddhism` in a `ja` session is **not** a typo of `仏教` — return `new`).
2. **duplicate** — the input refers to the same concept as one of the existing inventory entries under a different name in the same script (abbreviation, expansion, synonym, alternate phrasing). Examples: `large-language-model` matches an existing `llm` entry; `JS` matches `javascript`. Matching purely by translation (e.g., English `buddhism` to a Japanese-titled `仏教` entry) does NOT count — return `new` so the user can refine via the language-independent slug.
3. **new** — the input is a genuinely new topic with no clear overlap with the inventory. This is also the correct answer whenever the only "match" would require translating across scripts.

Respond with a single JSON object — no preamble, no code fence, no trailing prose — matching this shape:

    {{"kind": "new" | "typo" | "duplicate",
      "corrected_topic": "<correctly-spelled topic, only when kind is 'typo'>",
      "matched_slug": "<slug from the inventory, only when kind is 'duplicate'>",
      "reason": "<one short sentence>"}}

Use `null` for fields that don't apply. When in doubt, return `new`.
