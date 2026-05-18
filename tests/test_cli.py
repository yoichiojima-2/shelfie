from pathlib import Path

from typer.testing import CliRunner

from shelfie import cli, gen


def _config_file(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "shelfie.config.yaml"
    cfg_path.write_text(f"output_dir: {tmp_path / 'out'}\n")
    return cfg_path


def test_skips_resolver_when_canonical_exists(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out" / "en"
    out.mkdir(parents=True)
    (out / "topic.md").write_text("---\ntitle: topic\n---\n\nbody")

    def boom(*_a, **_kw):
        raise AssertionError("resolver must not be called when canonical exists")

    monkeypatch.setattr(gen, "resolve_topic", boom)
    calls: dict = {}

    def fake_run(topic: str, _cfg, **kwargs):
        calls["topic"] = topic
        calls["slug"] = kwargs.get("slug")
        return Path("/dummy"), "updated"

    monkeypatch.setattr(gen, "run", fake_run)
    result = CliRunner().invoke(cli.app, ["add", "topic", "--config", str(_config_file(tmp_path))])
    assert result.exit_code == 0, result.output
    assert calls["topic"] == "topic"
    assert calls["slug"] is None


def test_typo_redirect_on_yes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gen, "canonical_exists", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        gen,
        "resolve_topic",
        lambda *_a, **_kw: gen.Resolution(
            kind="typo", corrected_topic="buddhism", reason="common misspelling",
        ),
    )
    calls: dict = {}

    def fake_run(topic: str, _cfg, **kwargs):
        calls["topic"] = topic
        calls["slug"] = kwargs.get("slug")
        return Path("/dummy"), "wrote"

    monkeypatch.setattr(gen, "run", fake_run)
    result = CliRunner().invoke(
        cli.app,
        ["add", "buddism", "--config", str(_config_file(tmp_path))],
        input="y\n",
    )
    assert result.exit_code == 0, result.output
    assert "Did you mean 'buddhism'?" in result.output
    assert calls["topic"] == "buddhism"
    assert calls["slug"] is None


def test_typo_kept_on_no(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gen, "canonical_exists", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        gen,
        "resolve_topic",
        lambda *_a, **_kw: gen.Resolution(
            kind="typo", corrected_topic="buddhism", reason="common misspelling",
        ),
    )
    calls: dict = {}

    def fake_run(topic: str, _cfg, **kwargs):
        calls["topic"] = topic
        calls["slug"] = kwargs.get("slug")
        return Path("/dummy"), "wrote"

    monkeypatch.setattr(gen, "run", fake_run)
    result = CliRunner().invoke(
        cli.app,
        ["add", "buddism", "--config", str(_config_file(tmp_path))],
        input="n\n",
    )
    assert result.exit_code == 0, result.output
    assert calls["topic"] == "buddism"
    assert calls["slug"] is None


def test_duplicate_redirect_on_yes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gen, "canonical_exists", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        gen,
        "resolve_topic",
        lambda *_a, **_kw: gen.Resolution(
            kind="duplicate",
            matched_slug="llm",
            matched_title="Large Language Model",
            reason="abbreviation",
        ),
    )
    calls: dict = {}

    def fake_run(topic: str, _cfg, **kwargs):
        calls["topic"] = topic
        calls["slug"] = kwargs.get("slug")
        return Path("/dummy"), "updated"

    monkeypatch.setattr(gen, "run", fake_run)
    result = CliRunner().invoke(
        cli.app,
        ["add", "large-language-model", "--config", str(_config_file(tmp_path))],
        input="y\n",
    )
    assert result.exit_code == 0, result.output
    assert "'llm.md'" in result.output
    assert "Large Language Model" in result.output
    assert calls["topic"] == "Large Language Model"
    assert calls["slug"] == "llm"


def test_duplicate_kept_on_no(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gen, "canonical_exists", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        gen,
        "resolve_topic",
        lambda *_a, **_kw: gen.Resolution(
            kind="duplicate",
            matched_slug="llm",
            matched_title="Large Language Model",
        ),
    )
    calls: dict = {}

    def fake_run(topic: str, _cfg, **kwargs):
        calls["topic"] = topic
        calls["slug"] = kwargs.get("slug")
        return Path("/dummy"), "wrote"

    monkeypatch.setattr(gen, "run", fake_run)
    result = CliRunner().invoke(
        cli.app,
        ["add", "large-language-model", "--config", str(_config_file(tmp_path))],
        input="n\n",
    )
    assert result.exit_code == 0, result.output
    assert calls["topic"] == "large-language-model"
    assert calls["slug"] is None


def test_new_resolution_no_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gen, "canonical_exists", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        gen,
        "resolve_topic",
        lambda *_a, **_kw: gen.Resolution(kind="new", reason="no overlap"),
    )
    calls: dict = {}

    def fake_run(topic: str, _cfg, **kwargs):
        calls["topic"] = topic
        return Path("/dummy"), "wrote"

    monkeypatch.setattr(gen, "run", fake_run)
    result = CliRunner().invoke(
        cli.app,
        ["add", "tidal locking", "--config", str(_config_file(tmp_path))],
    )
    assert result.exit_code == 0, result.output
    assert "Did you mean" not in result.output
    assert "Refine that instead" not in result.output
    assert calls["topic"] == "tidal locking"
