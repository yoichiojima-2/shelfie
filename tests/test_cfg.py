from pathlib import Path

import pytest

from shelfie import cfg as cfg_mod


def test_load_example(tmp_path: Path) -> None:
    src = Path(__file__).parent.parent / "example.yaml"
    dst = tmp_path / "shelfie.config.yaml"
    dst.write_text(src.read_text())
    c = cfg_mod.load(dst)
    assert c.language == "en"
    assert c.tone == "neutral"
    assert c.enable_x is False
    assert c.llm.model == "claude-opus-4-7"
    assert c.llm.max_searches == 10
    assert c.llm.max_steps == 20


def test_defaults() -> None:
    c = cfg_mod.Config()
    assert c.output_dir == Path("./articles")
    assert c.llm.max_tokens == 8000


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cfg_mod.load(tmp_path / "nope.yaml")
