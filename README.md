# shelfie

Build your own Wikipedia. One topic in, one cited Markdown article out.

`shelfie` is a thin wrapper around the Anthropic API with the `web_search` server tool. You give it a topic; Claude searches, fetches, and writes a Wikipedia-style article with footnote citations. Just like asking Claude Code or Codex to write a Wikipedia page — but as a CLI that drops the result into your notes folder.

## Quickstart

```bash
uv sync   # or: uv tool install shelfie

cp example.yaml shelfie.config.yaml
echo "ANTHROPIC_API_KEY=sk-..." > .env

uv run shelfie add "tidal locking"
# -> ./articles/2026-05-17_tidal-locking.md
```

## Flags

- `--config PATH` — use a config other than `./shelfie.config.yaml`.
- `--dry-run` — print the article to stdout instead of writing.
- `--force` — overwrite an existing file.

## Optional: X (Twitter)

Set `enable_x: true` in config and `XAI_API_KEY=...` in `.env`. Claude will get an `x_search` tool that uses xAI Grok Live Search (restricted to X as the only source) to pull recent posts. Cheaper than the X API — pay-per-use, no monthly floor. X content is always attributed in the article, never presented as fact.

See `CLAUDE.md` for design.
