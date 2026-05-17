from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from shelfie import cfg as cfg_mod
from shelfie import gen


@dataclass
class FakeBlock:
    type: str
    text: str = ""
    name: str = ""
    id: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class FakeResp:
    content: list[FakeBlock]
    stop_reason: str = "end_turn"


class FakeMessages:
    def __init__(self, responses: list[FakeResp]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs: Any) -> FakeResp:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[FakeResp]):
        self.messages = FakeMessages(responses)


def _cfg(tmp_path: Path, *, enable_x: bool = False) -> cfg_mod.Config:
    return cfg_mod.Config(output_dir=tmp_path / "out", enable_x=enable_x)


def test_run_single_step_writes(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="# Article\n\nbody [^1]")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    path = gen.run("tidal locking", _cfg(tmp_path))
    assert isinstance(path, Path)
    assert path.name.endswith("tidal-locking.md")
    assert "Article" in path.read_text()
    assert len(fake.messages.calls) == 1
    tools = fake.messages.calls[0]["tools"]
    assert tools[0]["name"] == "web_search"
    assert all(t["name"] != "x_search" for t in tools)


def test_run_dry_run(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="MD")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    out = gen.run("t", _cfg(tmp_path), dry_run=True)
    assert out == "MD"
    assert not (tmp_path / "out").exists()


def test_agentic_loop_with_x_tool(tmp_path: Path, monkeypatch) -> None:
    tool_use = FakeBlock(type="tool_use", name="x_search", id="abc", input={"query": "foo"})
    final = FakeBlock(type="text", text="# Done\n\nbody")
    fake = FakeClient([
        FakeResp(content=[tool_use], stop_reason="tool_use"),
        FakeResp(content=[final], stop_reason="end_turn"),
    ])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    monkeypatch.setattr(gen, "x_search", lambda q, limit=10: '[{"author":"alice","text":"hi"}]')
    path = gen.run("topic", _cfg(tmp_path, enable_x=True))
    assert isinstance(path, Path)
    assert len(fake.messages.calls) == 2
    second_msgs = fake.messages.calls[1]["messages"]
    tool_result_msg = next(
        m for m in second_msgs
        if m["role"] == "user" and isinstance(m["content"], list)
        and m["content"] and isinstance(m["content"][0], dict)
        and m["content"][0].get("type") == "tool_result"
    )
    assert tool_result_msg["content"][0]["tool_use_id"] == "abc"
    tools = fake.messages.calls[0]["tools"]
    assert any(t["name"] == "x_search" for t in tools)


def test_no_overwrite_without_force(tmp_path: Path, monkeypatch) -> None:
    def make_client() -> FakeClient:
        return FakeClient([FakeResp(content=[FakeBlock(type="text", text="x")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", make_client)
    c = _cfg(tmp_path)
    gen.run("topic", c)
    with pytest.raises(FileExistsError):
        gen.run("topic", c)
    gen.run("topic", c, force=True)


def test_max_steps_raises(tmp_path: Path, monkeypatch) -> None:
    tool_use = FakeBlock(type="tool_use", name="x_search", id="x", input={"query": "q"})
    fake = FakeClient([FakeResp(content=[tool_use], stop_reason="tool_use") for _ in range(3)])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    monkeypatch.setattr(gen, "x_search", lambda q, limit=10: "x")
    c = _cfg(tmp_path, enable_x=True)
    c.llm.max_steps = 3
    with pytest.raises(RuntimeError, match="max_steps"):
        gen.run("topic", c)


def test_empty_article_raises(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    with pytest.raises(RuntimeError, match="empty"):
        gen.run("topic", _cfg(tmp_path))
