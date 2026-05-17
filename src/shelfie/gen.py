import logging
import os
from datetime import date
from importlib.resources import files
from pathlib import Path

import anthropic
from slugify import slugify

from .cfg import Config
from .tools import X_SEARCH_SCHEMA, x_search

log = logging.getLogger(__name__)


def _prompt(cfg: Config, topic: str) -> str:
    template = (files("shelfie") / "prompt.md").read_text()
    return template.format(
        topic=topic,
        today=date.today().isoformat(),
        language=cfg.language,
        tone=cfg.tone,
    )


def _build_tools(cfg: Config) -> list[dict]:
    tools: list[dict] = [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": cfg.llm.max_searches,
    }]
    if cfg.enable_x:
        if not os.environ.get("X_BEARER_TOKEN"):
            log.warning("enable_x is true but X_BEARER_TOKEN is missing; x_search will return errors")
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

    final_text = ""
    for step in range(cfg.llm.max_steps):
        resp = client.messages.create(
            model=cfg.llm.model,
            max_tokens=cfg.llm.max_tokens,
            tools=tools,
            messages=msgs,
        )
        msgs.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            final_text = "".join(b.text for b in resp.content if b.type == "text")
            log.info("agentic loop done in %d step(s), stop_reason=%s", step + 1, resp.stop_reason)
            return final_text.strip()

        results = []
        for block in resp.content:
            if block.type == "tool_use":
                log.info("step %d: tool %s(%s)", step + 1, block.name, block.input)
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


def _write(markdown: str, topic: str, cfg: Config, force: bool) -> Path:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    name = cfg.filename_format.format(
        date=date.today().isoformat(),
        slug=slugify(topic),
    )
    out = cfg.output_dir / name
    if out.exists() and not force:
        raise FileExistsError(f"{out} exists (use --force to overwrite)")
    out.write_text(markdown)
    return out


def run(topic: str, cfg: Config, *, dry_run: bool = False, force: bool = False) -> Path | str:
    prompt = _prompt(cfg, topic)
    md = _agentic_loop(prompt, cfg)
    if not md:
        raise RuntimeError("model returned empty article")
    if dry_run:
        return md
    return _write(md, topic, cfg, force)
