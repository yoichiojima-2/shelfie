# Resolve the user's topic input

The user is about to add an article in `{language}`. They typed:

    {topic}

The shelf already contains these articles in `{language}` (`slug — title`):

{inventory}

Decide which of the following best describes the user's input:

1. **typo** — the input is a clear, unambiguous misspelling of a known concept. Examples: `buddism` → `buddhism`, `einsteen` → `einstein`. Use this only when the intended spelling is obvious; do not "correct" valid alternate names, archaic forms, or proper-noun variants you are merely unsure about.
2. **duplicate** — the input refers to the same concept as one of the existing inventory entries under a different name (abbreviation, expansion, synonym, alternate phrasing). Examples: `large-language-model` matches an existing `llm` entry; `JS` matches `javascript`. Use this only when it is clearly the same concept, not just a related one.
3. **new** — the input is a genuinely new topic with no clear overlap with the inventory.

Respond with a single JSON object — no preamble, no code fence, no trailing prose — matching this shape:

    {{"kind": "new" | "typo" | "duplicate",
      "corrected_topic": "<correctly-spelled topic, only when kind is 'typo'>",
      "matched_slug": "<slug from the inventory, only when kind is 'duplicate'>",
      "reason": "<one short sentence>"}}

Use `null` for fields that don't apply. When in doubt, return `new`.
