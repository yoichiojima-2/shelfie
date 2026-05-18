# CLAUDE.md

Context for coding agents (Claude, Codex, etc.) working on this repo. Read it before making changes.

## What this project is

**`shelfie` is a CLI tool for building your own Wikipedia.**

You give it a topic. Claude runs an agentic research loop — searching the web (and optionally X) — and writes a single, well-cited Markdown article. The file lands in a folder you can browse in Obsidian, Logseq, or any plain Markdown editor.

Over time the folder becomes your personal encyclopedia: only the topics you care about, in your preferred structure and tone, owned by you.

The tool is **vault-agnostic**. It writes `.md` files to a configured directory. It does not depend on Obsidian, and never assumes a particular editor or sync mechanism.

## How it works

`shelfie` is a thin wrapper around the **Anthropic API with the `web_search` server tool** and (optionally) a custom **`x_search`** client tool. There is no per-source pipeline — Claude itself decides what to search for, fetches what it needs, and writes the final article. This mirrors how Claude Code or Codex would write a Wikipedia article if you asked them to.

The agentic loop is the entire architecture:

1. `cli.py` loads `shelfie.config.yaml` and `.env`, then calls `gen.run(topic, cfg)`.
2. `gen.run` resolves the canonical path for the topic: `output_dir/{language}/{slug}.md`. The slug is the language-independent identity — use the same topic input across languages so the cross-language link works.
3. Mode selection:
   - **Refine** — if the article exists in the target language, feed it back to the model as the previous version with instructions to update with the latest info.
   - **Translate** — if no in-language version exists but the same slug exists in another language, feed that source in with a translation directive (terminology verification, citation preservation).
   - **Fresh** — write a new article from scratch.
4. `gen.run` sends one user message with `web_search` (server tool) and, if X is enabled, `x_search` (client tool) attached.
5. Claude searches, may call `x_search` (in which case we execute it and return tweets), iterates as needed, and returns a final Markdown article with footnote citations.
6. The result is written to `output_dir/{language}/{slug}.md`, overwriting in place. Git is the revision history.

Prompts live in `src/shelfie/prompt.md` (base), `prompt_update.md` (refine directive), `prompt_translate.md` (translate directive). The Python in `gen.py` loads them via `importlib.resources` and `.format(...)`-substitutes placeholders.

## Design principles

These are non-negotiable. Preserve them when refactoring.

1. **One topic in, one Markdown file out.** No multi-page generation, no databases, no knowledge graphs.
2. **Citations are mandatory.** Every factual claim has an inline footnote pointing to a source URL.
3. **Agentic, not pipelined.** Claude does the research. We do not pre-fetch sources, we do not hand-craft per-source adapters. The only client-side tool is `x_search` (because the X API needs auth and Claude's server tools don't cover it).
4. **Personal but not opinionated.** Tone, language, and structure are configurable; sensible defaults ship in `example.yaml`.
5. **No silent failures.** Tool errors surface in tool_result and let the model decide; the CLI surfaces fatal errors clearly.
6. **Markdown is the universal output.** No HTML, no PDF.
7. **The CLI is the entire interface.** No web UI, no daemon, no server.

## Simplicity rules (read before adding anything)

- **Short names over descriptive ones.** `gen.py`, `cfg.py`, `tools.py`. `fetch()` not `fetch_documents_from_source()`. `cfg`, `topic`, `msgs` for locals.
- **Minimum viable implementation.** Build only what the current task strictly needs. No flags, providers, registries, retry layers, or fallbacks "just in case."
- **Collapse files.** Prefer one small module over a folder of one-function files.
- **No premature config.** Defaults are inline constants until a real user need turns them into config keys.

## Repository layout

```
shelfie/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .gitignore
├── example.yaml
├── src/shelfie/
│   ├── __init__.py
│   ├── cli.py          # typer entry point
│   ├── cfg.py          # YAML + .env loading
│   ├── tools.py        # x_search client tool
│   ├── gen.py          # agentic loop + write
│   ├── prompt.md       # base article prompt
│   ├── prompt_update.md     # refinement directive (appended on re-run)
│   └── prompt_translate.md  # translation directive (appended on cross-language)
└── tests/
    ├── test_cfg.py
    ├── test_tools.py
    └── test_gen.py
```

## How it runs

```bash
uv sync                                # local dev
# or: uv tool install shelfie

# In a directory with shelfie.config.yaml + .env
uv run shelfie add "tidal locking"
# -> ./articles/2026-05-17_tidal-locking.md
```

## Configuration

`shelfie.config.yaml`:

```yaml
output_dir: ./articles
language: en
tone: neutral
filename_format: "{date}_{slug}.md"

enable_x: false             # set true to give Claude the x_search tool

llm:
  model: claude-opus-4-7
  max_tokens: 8000
  max_searches: 10          # cap on web_search calls per article
  max_steps: 20             # cap on agentic loop iterations
```

`.env`:

```
ANTHROPIC_API_KEY=...
XAI_API_KEY=...             # only if enable_x: true
```

## Tools available to the model

- **`web_search`** — Anthropic server-managed. The model issues queries and gets back results with citations. We do not implement this; we just attach the tool.
- **`x_search(query, limit=15)`** — client tool. Optional, off by default. Calls xAI Grok Live Search restricted to X as the only source (`sources: [{"type": "x"}]`). Returns Grok's summary of recent X discussion plus citation URLs. Pay-per-use; no X developer account required. The prompt instructs the model to attribute X content as opinion / claim, not fact.

## Article prompt

Lives at `src/shelfie/prompt.md` (loaded via `importlib.resources`). It tells the model:

- The output is a Wikipedia-style Markdown article on `{topic}`.
- Required sections: frontmatter (YAML), `# Topic`, `## Overview`, `## Background`, `## Details`, `## Debates and Open Questions`, `## Related Topics`, `## References`.
- Every factual claim needs `[^N]` and a matching entry in `## References`.
- X content must be attributed ("According to @user on X, ..."), never presented as fact.
- Tone: `{tone}`. Language: `{language}`. Length: 400–1200 words.
- Return only the Markdown article — no preamble, no code fences wrapping the whole thing.

## Coding conventions

- Python 3.11+, type hints everywhere.
- `uv` for deps. `ruff` for lint/format. `pytest` for tests (mocked — no live API calls).
- `pydantic` for config. `httpx` for HTTP. `typer` for CLI. `anthropic` SDK for the API.
- No global state. Pass `cfg` explicitly. No `print()` in library code — use `logging`.

## What NOT to do

- Do not add per-source adapters (Wikipedia, Tavily, arXiv, etc.). The `web_search` tool subsumes them. The agentic principle is "let Claude search."
- Do not add a database, web UI, or daemon.
- Do not hardcode user-specific topics, names, or preferences.
- Do not break backward compatibility of the config schema without a major version bump.
- Do not require the vault to live in a specific path.

## Out of scope

- Maintaining a revision log inside the article (git is the history).
- Cross-article linking or knowledge graphs.
- Image generation.
- Hosting / publishing / syncing.
