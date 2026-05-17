from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class LLMCfg(BaseModel):
    model: str = "claude-opus-4-7"
    max_tokens: int = 8000
    max_searches: int = 10
    max_steps: int = 20


class Config(BaseModel):
    output_dir: Path = Path("./articles")
    language: str = "en"
    tone: str = "neutral"
    filename_format: str = "{date}_{slug}.md"
    enable_x: bool = False
    llm: LLMCfg = Field(default_factory=LLMCfg)


def load(path: Path | None = None) -> Config:
    path = path or Path("shelfie.config.yaml")
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    load_dotenv()
    data = yaml.safe_load(path.read_text()) or {}
    return Config(**data)
