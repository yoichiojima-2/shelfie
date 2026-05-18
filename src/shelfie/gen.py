import logging
import os
import sys
from datetime import date
from importlib.resources import files
from pathlib import Path

import anthropic
import yaml
from slugify import slugify

from .cfg import Config
from .tools import X_SEARCH_SCHEMA, x_search

log = logging.getLogger(__name__)

_SLUG_REPLACEMENTS = [("++", " plus plus "), ("#", " sharp "), ("&", " and ")]


def _load(name: str) -> str:
    return (files("shelfie") / name).read_text()


def _prompt(
    cfg: Config,
    topic: str,
    *,
    existing: str | None = None,
    translate_from: str | None = None,
    source_lang: str | None = None,
    instructions: str | None = None,
) -> str:
    today = date.today().isoformat()
    parts = [_load("prompt.md").format(
        topic=topic, today=today, language=cfg.language, tone=cfg.tone,
    )]
    if existing is not None:
        parts.append(_load("prompt_update.md").format(today=today, existing=existing))
    elif translate_from is not None:
        parts.append(_load("prompt_translate.md").format(
            today=today,
            language=cfg.language,
            source_lang=source_lang,
            translate_from=translate_from,
        ))
    if instructions:
        parts.append(_load("prompt_instructions.md").format(instructions=instructions))
    return "\n\n---\n\n".join(parts)


def _title(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    parts = text.split("\n---\n", 2)
    if len(parts) < 2:
        return None
    front = yaml.safe_load(parts[0][4:]) or {}
    return front.get("title")


def _pick(dirs: list[Path], slug: str, exclude: Path | None = None) -> tuple[Path, str] | None:
    matches: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        canonical = d / f"{slug}.md"
        if canonical.is_file() and canonical != exclude:
            matches.append(canonical)
        matches.extend(p for p in d.glob(f"*_{slug}.md") if p.is_file() and p != exclude)
    if not matches:
        return None
    chosen = max(matches, key=lambda p: p.stat().st_mtime)
    return chosen, chosen.read_text()


def _existing(cfg: Config, slug: str, target: Path) -> tuple[Path, str] | None:
    if target.exists():
        return target, target.read_text()
    dirs = [target.parent]
    if target.parent != cfg.output_dir:
        dirs.append(cfg.output_dir)
    return _pick(dirs, slug, exclude=target)


def _translation_source(cfg: Config, slug: str, target_parent: Path) -> tuple[Path, str] | None:
    if not cfg.output_dir.exists():
        return None
    siblings = [d for d in cfg.output_dir.iterdir() if d.is_dir() and d != target_parent]
    return _pick(siblings, slug)


def _build_tools(cfg: Config) -> list[dict]:
    tools: list[dict] = [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": cfg.llm.max_searches,
    }]
    if cfg.enable_x:
        if not os.environ.get("XAI_API_KEY"):
            log.warning("enable_x is true but XAI_API_KEY is missing; x_search will return errors")
        tools.append(X_SEARCH_SCHEMA)
    return tools


def _run_tool(name: str, tool_input: dict) -> str:
    if name == "x_search":
        return x_search(tool_input["query"], tool_input.get("limit", 10))
    return f"Error: unknown tool {name}"


def _agentic_loop(prompt: str, cfg: Config) -> str:
    client = anthropic.Anthropic()
    tools = _build_tools(cfg)
    msgs: list[dict] = [{"role": "user", "content": prompt}]

    for step in range(cfg.llm.max_steps):
        with client.messages.stream(
            model=cfg.llm.model,
            max_tokens=cfg.llm.max_tokens,
            tools=tools,
            messages=msgs,
        ) as stream:
            for text in stream.text_stream:
                sys.stderr.write(text)
                sys.stderr.flush()
        sys.stderr.write("\n")
        sys.stderr.flush()

        resp = stream.get_final_message()
        msgs.append({"role": "assistant", "content": resp.content})

        for block in resp.content:
            if block.type in ("server_tool_use", "tool_use"):
                inp = block.input if isinstance(block.input, dict) else {}
                q = inp.get("query") or inp
                sys.stderr.write(f"→ {block.name}: {q!r}\n")
                sys.stderr.flush()

        if resp.stop_reason != "tool_use":
            log.info("done in %d step(s)", step + 1)
            return "".join(b.text for b in resp.content if b.type == "text").strip()

        results = []
        for block in resp.content:
            if block.type == "tool_use":
                output = _run_tool(block.name, block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
        if not results:
            break
        msgs.append({"role": "user", "content": results})

    raise RuntimeError(f"agentic loop hit max_steps={cfg.llm.max_steps} without finishing")


def run(
    topic: str,
    cfg: Config,
    *,
    dry_run: bool = False,
    instructions: str | None = None,
) -> tuple[Path, str] | str:
    slug = slugify(topic, replacements=_SLUG_REPLACEMENTS)
    target = cfg.output_dir / cfg.language / cfg.filename_format.format(
        date=date.today().isoformat(), slug=slug,
    )
    existing = _existing(cfg, slug, target)
    translate_from = None
    if existing:
        title = _title(existing[1])
        if title and title.strip().lower() != topic.strip().lower():
            raise ValueError(
                f"slug collision: {existing[0].name} is titled {title!r}, "
                f"not {topic!r}. Disambiguate with a more specific topic "
                f"(e.g. 'Mercury (planet)') or rename the existing file."
            )
        action = "updated"
        verb = "refining"
    else:
        translate_from = _translation_source(cfg, slug, target.parent)
        if translate_from:
            action = "translated"
            verb = f"translating from {translate_from[0].parent.name}"
        else:
            action = "wrote"
            verb = "researching"
    sys.stderr.write(f"{verb} {topic}...\n")
    sys.stderr.flush()
    prompt = _prompt(
        cfg,
        topic,
        existing=existing[1] if existing else None,
        translate_from=translate_from[1] if translate_from else None,
        source_lang=translate_from[0].parent.name if translate_from else None,
        instructions=instructions,
    )
    md = _agentic_loop(prompt, cfg)
    if not md:
        raise RuntimeError("model returned empty article")
    if dry_run:
        return md
    target.parent.mkdir(parents=True, exist_ok=True)
    if existing and existing[0] != target:
        existing[0].rename(target)
    target.write_text(md)
    return target, action
