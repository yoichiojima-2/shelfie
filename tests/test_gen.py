from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from slugify import slugify

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


class FakeStream:
    def __init__(self, resp: FakeResp):
        self._resp = resp

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, *_a: Any) -> bool:
        return False

    @property
    def text_stream(self):
        for b in self._resp.content:
            if b.type == "text":
                yield b.text

    def get_final_message(self) -> FakeResp:
        return self._resp


class FakeMessages:
    def __init__(self, responses: list[FakeResp]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def stream(self, **kwargs: Any) -> FakeStream:
        self.calls.append(kwargs)
        return FakeStream(self.responses.pop(0))


class FakeClient:
    def __init__(self, responses: list[FakeResp]):
        self.messages = FakeMessages(responses)


def _cfg(tmp_path: Path, *, enable_x: bool = False) -> cfg_mod.Config:
    return cfg_mod.Config(output_dir=tmp_path / "out", enable_x=enable_x)


def _client_factory(monkeypatch, payloads: list[str]) -> list[FakeClient]:
    clients: list[FakeClient] = []

    def make() -> FakeClient:
        c = FakeClient([FakeResp(content=[FakeBlock(type="text", text=payloads[len(clients)])])])
        clients.append(c)
        return c

    monkeypatch.setattr(gen.anthropic, "Anthropic", make)
    return clients


def test_run_single_step_writes(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="# Article\n\nbody [^1]")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    path, updated = gen.run("tidal locking", _cfg(tmp_path))
    assert isinstance(path, Path)
    assert path == tmp_path / "out" / "en" / "tidal-locking.md"
    assert updated is False
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
    path, _ = gen.run("topic", _cfg(tmp_path, enable_x=True))
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


def test_update_in_place(tmp_path: Path, monkeypatch) -> None:
    _client_factory(monkeypatch, ["# Topic\n\nfirst", "# Topic\n\nsecond"])
    c = _cfg(tmp_path)
    path1, updated1 = gen.run("topic", c)
    path2, updated2 = gen.run("topic", c)
    assert path1 == path2
    assert updated1 is False
    assert updated2 is True
    assert path2.read_text() == "# Topic\n\nsecond"
    lang_dir = tmp_path / "out" / "en"
    assert [p.name for p in sorted(lang_dir.iterdir())] == ["topic.md"]


def test_update_passes_existing_into_prompt(tmp_path: Path, monkeypatch) -> None:
    clients = _client_factory(
        monkeypatch,
        ["# Topic\n\nfirst version content", "# Topic\n\nsecond version"],
    )
    c = _cfg(tmp_path)
    gen.run("topic", c)
    gen.run("topic", c)
    second_prompt = clients[1].messages.calls[0]["messages"][0]["content"]
    assert "first version content" in second_prompt
    assert "Update an existing article" in second_prompt


def test_migrates_legacy_dated_file(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    out.mkdir()
    legacy = out / "2024-01-01_topic.md"
    legacy.write_text("old content")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="new content")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    path, updated = gen.run("topic", _cfg(tmp_path))
    assert path == out / "en" / "topic.md"
    assert path.read_text() == "new content"
    assert not legacy.exists()
    assert updated is True
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "old content" in prompt


def test_migrates_pre_language_canonical_file(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    out.mkdir()
    legacy = out / "topic.md"
    legacy.write_text("old canonical content")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="new content")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    path, updated = gen.run("topic", _cfg(tmp_path))
    assert path == out / "en" / "topic.md"
    assert path.read_text() == "new content"
    assert not legacy.exists()
    assert updated is True


def test_dry_run_does_not_rename_legacy(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    out.mkdir()
    legacy = out / "2024-01-01_topic.md"
    legacy.write_text("old content")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="new content")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    result = gen.run("topic", _cfg(tmp_path), dry_run=True)
    assert result == "new content"
    assert legacy.exists()
    assert not (out / "en" / "topic.md").exists()


def test_language_subdir(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="x")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    c = _cfg(tmp_path)
    c.language = "ja"
    path, _ = gen.run("topic", c)
    assert path == tmp_path / "out" / "ja" / "topic.md"


def test_keeps_date_prefix_when_format_has_date(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="md")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    c = _cfg(tmp_path)
    c.filename_format = "{date}_{slug}.md"
    path, _ = gen.run("topic", c)
    assert path.name == f"{date.today().isoformat()}_topic.md"
    assert path.parent.name == "en"


def test_slug_replacements() -> None:
    r = gen._SLUG_REPLACEMENTS
    assert slugify("C++", replacements=r) == "c-plus-plus"
    assert slugify("C#", replacements=r) == "c-sharp"
    assert slugify("R&D", replacements=r) == "r-and-d"
    assert slugify("C", replacements=r) == "c"
    assert slugify("C++", replacements=r) != slugify("C", replacements=r)


def test_slug_collision_raises(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out" / "en"
    out.mkdir(parents=True)
    existing = out / "mercury.md"
    existing.write_text("---\ntitle: Mercury (planet)\n---\n\nplanet stuff")

    def boom() -> FakeClient:
        raise AssertionError("API must not be called on slug collision")

    monkeypatch.setattr(gen.anthropic, "Anthropic", boom)
    with pytest.raises(ValueError, match="slug collision"):
        gen.run("mercury", _cfg(tmp_path))
    assert existing.read_text() == "---\ntitle: Mercury (planet)\n---\n\nplanet stuff"


def test_collision_check_skipped_for_legacy_files(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out" / "en"
    out.mkdir(parents=True)
    existing = out / "mercury.md"
    existing.write_text("just plain markdown, no frontmatter")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="new mercury content")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    path, updated = gen.run("mercury", _cfg(tmp_path))
    assert path == existing
    assert path.read_text() == "new mercury content"
    assert updated is True
