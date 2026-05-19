from dataclasses import dataclass, field
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

    def create(self, **kwargs: Any) -> FakeResp:
        self.calls.append(kwargs)
        return self.responses.pop(0)


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
    path, action = gen.run("tidal locking", _cfg(tmp_path))
    assert isinstance(path, Path)
    assert path == tmp_path / "out" / "en" / "tidal-locking.md"
    assert action == "wrote"
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
    path1, action1 = gen.run("topic", c)
    path2, action2 = gen.run("topic", c)
    assert path1 == path2
    assert action1 == "wrote"
    assert action2 == "updated"
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
    path, action = gen.run("topic", _cfg(tmp_path))
    assert path == out / "en" / "topic.md"
    assert path.read_text() == "new content"
    assert not legacy.exists()
    assert action == "updated"
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "old content" in prompt


def test_migrates_pre_language_canonical_file(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    out.mkdir()
    legacy = out / "topic.md"
    legacy.write_text("old canonical content")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="new content")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    path, action = gen.run("topic", _cfg(tmp_path))
    assert path == out / "en" / "topic.md"
    assert path.read_text() == "new content"
    assert not legacy.exists()
    assert action == "updated"


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


def test_collision_skipped_when_title_in_different_script(tmp_path: Path, monkeypatch) -> None:
    ja_dir = tmp_path / "out" / "ja"
    ja_dir.mkdir(parents=True)
    existing = ja_dir / "buddhism.md"
    existing.write_text("---\ntitle: 仏教\n---\n\n既存の本文")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="改訂された本文")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    c = _cfg(tmp_path)
    c.language = "ja"
    path, action = gen.run("buddhism", c)
    assert path == existing
    assert action == "updated"
    assert path.read_text() == "改訂された本文"


def test_collision_check_skipped_for_legacy_files(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out" / "en"
    out.mkdir(parents=True)
    existing = out / "mercury.md"
    existing.write_text("just plain markdown, no frontmatter")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="new mercury content")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    path, action = gen.run("mercury", _cfg(tmp_path))
    assert path == existing
    assert path.read_text() == "new mercury content"
    assert action == "updated"


def test_translates_when_other_language_exists(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    source = en_dir / "topic.md"
    source.write_text("---\ntitle: Topic\n---\n\nEnglish body content here.")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="日本語の本文")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    c = _cfg(tmp_path)
    c.language = "ja"
    path, action = gen.run("topic", c)
    assert path == tmp_path / "out" / "ja" / "topic.md"
    assert action == "translated"
    assert path.read_text() == "日本語の本文"
    assert source.read_text() == "---\ntitle: Topic\n---\n\nEnglish body content here."
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "English body content here." in prompt
    assert "Translate an existing article" in prompt
    assert "`en`" in prompt


def test_refine_wins_over_translation(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    ja_dir = tmp_path / "out" / "ja"
    en_dir.mkdir(parents=True)
    ja_dir.mkdir(parents=True)
    (en_dir / "topic.md").write_text("---\ntitle: Topic\n---\n\nEnglish content")
    (ja_dir / "topic.md").write_text("---\ntitle: Topic\n---\n\n日本語の既存内容")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="改訂版")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    c = _cfg(tmp_path)
    c.language = "ja"
    path, action = gen.run("topic", c)
    assert path == ja_dir / "topic.md"
    assert action == "updated"
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "日本語の既存内容" in prompt
    assert "English content" not in prompt
    assert "Update an existing article" in prompt


def test_translation_picks_most_recent_source(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    fr_dir = tmp_path / "out" / "fr"
    en_dir.mkdir(parents=True)
    fr_dir.mkdir(parents=True)
    en_source = en_dir / "topic.md"
    fr_source = fr_dir / "topic.md"
    en_source.write_text("English content")
    fr_source.write_text("Contenu français")
    import os as _os
    _os.utime(en_source, (1_700_000_000, 1_700_000_000))
    _os.utime(fr_source, (1_800_000_000, 1_800_000_000))
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="日本語")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    c = _cfg(tmp_path)
    c.language = "ja"
    gen.run("topic", c)
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "Contenu français" in prompt
    assert "`fr`" in prompt
    assert "English content" not in prompt


def test_vault_links_appear_in_prompt(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "orbital-mechanics.md").write_text(
        "---\ntitle: Orbital Mechanics\n---\n\nbody"
    )
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="x")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    gen.run("tidal locking", _cfg(tmp_path))
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "# Existing articles in this vault" in prompt
    assert "[[orbital-mechanics]]" in prompt
    assert "Orbital Mechanics" in prompt


def test_vault_excludes_current_target(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "topic.md").write_text("---\ntitle: Topic\n---\n\nbody")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="refined")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    gen.run("topic", _cfg(tmp_path))
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "# Existing articles in this vault" not in prompt
    assert "`[[topic]]`" not in prompt


def test_empty_vault_omits_links_section(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="x")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    gen.run("topic", _cfg(tmp_path))
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "# Existing articles in this vault" not in prompt


def test_vault_falls_back_to_slug_when_no_title(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "other.md").write_text("just a body, no frontmatter")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="x")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    gen.run("topic", _cfg(tmp_path))
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "`[[other]]` — other" in prompt


def test_vault_only_includes_current_language(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "out" / "en").mkdir(parents=True)
    (tmp_path / "out" / "ja").mkdir(parents=True)
    (tmp_path / "out" / "en" / "foo.md").write_text("---\ntitle: Foo\n---\n\nbody")
    (tmp_path / "out" / "ja" / "bar.md").write_text("---\ntitle: Bar\n---\n\nbody")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="x")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    c = _cfg(tmp_path)
    c.language = "ja"
    gen.run("baz", c)
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "[[bar]]" in prompt
    assert "[[foo]]" not in prompt


def test_instructions_in_fresh_prompt(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="x")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    gen.run("topic", _cfg(tmp_path), instructions="focus on history")
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "User instructions for this run" in prompt
    assert "focus on history" in prompt


def test_instructions_in_refine_prompt(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "topic.md").write_text("existing english body")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="refined")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    gen.run("topic", _cfg(tmp_path), instructions="add recent developments")
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "existing english body" in prompt
    assert "Update an existing article" in prompt
    assert "User instructions for this run" in prompt
    assert "add recent developments" in prompt
    assert prompt.index("Update an existing article") < prompt.index("User instructions for this run")


def test_instructions_in_translate_prompt(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "topic.md").write_text("English source content")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="日本語")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    c = _cfg(tmp_path)
    c.language = "ja"
    gen.run("topic", c, instructions="prefer scientific Japanese conventions")
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "English source content" in prompt
    assert "Translate an existing article" in prompt
    assert "User instructions for this run" in prompt
    assert "prefer scientific Japanese conventions" in prompt
    assert prompt.index("Translate an existing article") < prompt.index("User instructions for this run")


def test_no_instructions_omits_section(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="x")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    gen.run("topic", _cfg(tmp_path))
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "User instructions for this run" not in prompt


def test_translation_skips_collision_check(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "mercury.md").write_text(
        "---\ntitle: Some Other Title\n---\n\nbody"
    )
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="ja translation")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    c = _cfg(tmp_path)
    c.language = "ja"
    path, action = gen.run("mercury", c)
    assert action == "translated"
    assert path == tmp_path / "out" / "ja" / "mercury.md"


def test_run_accepts_slug_override(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "llm.md").write_text("---\ntitle: Large Language Model\n---\n\nold body")
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="new body")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    path, action = gen.run("Large Language Model", _cfg(tmp_path), slug="llm")
    assert path == en_dir / "llm.md"
    assert action == "updated"
    assert path.read_text() == "new body"


def test_canonical_exists_true_when_file_present(tmp_path: Path) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "topic.md").write_text("body")
    assert gen.canonical_exists("topic", _cfg(tmp_path)) is True


def test_canonical_exists_false_when_absent(tmp_path: Path) -> None:
    assert gen.canonical_exists("topic", _cfg(tmp_path)) is False


def test_resolve_topic_empty_inventory_typo(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(
        type="text",
        text='{"kind":"typo","corrected_topic":"buddhism","reason":"common misspelling"}',
    )])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    res = gen.resolve_topic("buddism", _cfg(tmp_path))
    assert res.kind == "typo"
    assert res.corrected_topic == "buddhism"
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "(empty)" in prompt
    assert "buddism" in prompt


def test_resolve_topic_duplicate(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "llm.md").write_text("---\ntitle: Large Language Model\n---\n\nbody")
    fake = FakeClient([FakeResp(content=[FakeBlock(
        type="text",
        text='{"kind":"duplicate","matched_slug":"llm","reason":"common abbreviation"}',
    )])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    res = gen.resolve_topic("large language model", _cfg(tmp_path))
    assert res.kind == "duplicate"
    assert res.matched_slug == "llm"
    assert res.matched_title == "Large Language Model"
    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "llm — Large Language Model" in prompt


def test_resolve_topic_new(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "physics.md").write_text("---\ntitle: Physics\n---\n\nbody")
    fake = FakeClient([FakeResp(content=[FakeBlock(
        type="text", text='{"kind":"new","reason":"no overlap"}',
    )])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    res = gen.resolve_topic("tidal locking", _cfg(tmp_path))
    assert res.kind == "new"
    assert res.corrected_topic is None
    assert res.matched_slug is None


def test_resolve_topic_invalid_json_falls_back_to_new(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(type="text", text="not json at all")])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    res = gen.resolve_topic("topic", _cfg(tmp_path))
    assert res.kind == "new"
    assert "parse failed" in res.reason


def test_resolve_topic_duplicate_with_unknown_slug_falls_back(tmp_path: Path, monkeypatch) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "llm.md").write_text("---\ntitle: Large Language Model\n---\n\nbody")
    fake = FakeClient([FakeResp(content=[FakeBlock(
        type="text",
        text='{"kind":"duplicate","matched_slug":"made-up","reason":"hallucinated"}',
    )])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    res = gen.resolve_topic("topic", _cfg(tmp_path))
    assert res.kind == "new"
    assert "not in inventory" in res.reason


def test_resolve_topic_typo_without_correction_falls_back(tmp_path: Path, monkeypatch) -> None:
    fake = FakeClient([FakeResp(content=[FakeBlock(
        type="text", text='{"kind":"typo","reason":"missing field"}',
    )])])
    monkeypatch.setattr(gen.anthropic, "Anthropic", lambda: fake)
    res = gen.resolve_topic("topic", _cfg(tmp_path))
    assert res.kind == "new"


def test_title_returns_none_on_malformed_yaml_frontmatter(tmp_path: Path) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "broken.md").write_text("---\n\n```yaml\ntitle: Foo\n---\n\nbody")
    (en_dir / "ok.md").write_text("---\ntitle: Ok\n---\n\nbody")
    inv = gen._inventory(_cfg(tmp_path))
    assert inv == [("ok", "Ok")]


def test_inventory_strips_date_prefix(tmp_path: Path) -> None:
    en_dir = tmp_path / "out" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "2024-01-15_topic.md").write_text("---\ntitle: Topic\n---\n\nbody")
    (en_dir / "untitled.md").write_text("no frontmatter")
    inv = gen._inventory(_cfg(tmp_path))
    assert inv == [("topic", "Topic")]
