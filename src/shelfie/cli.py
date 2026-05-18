import logging
from pathlib import Path

import typer

from . import cfg as cfg_mod
from . import gen

app = typer.Typer(help="Build your own Wikipedia.")


@app.callback()
def _root() -> None:
    """shelfie"""


@app.command()
def add(
    topic: str = typer.Argument(..., help="Topic to write about."),
    config: Path | None = typer.Option(None, "--config", help="Path to shelfie.config.yaml"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print article to stdout."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Override output_dir."),
    language: str | None = typer.Option(None, "--language", help="Override language."),
    tone: str | None = typer.Option(None, "--tone", help="Override tone."),
    filename_format: str | None = typer.Option(None, "--filename-format", help="Override filename_format."),
    enable_x: bool | None = typer.Option(None, "--enable-x/--no-enable-x", help="Override enable_x."),
    model: str | None = typer.Option(None, "--model", help="Override llm.model."),
    max_tokens: int | None = typer.Option(None, "--max-tokens", help="Override llm.max_tokens."),
    max_searches: int | None = typer.Option(None, "--max-searches", help="Override llm.max_searches."),
    max_steps: int | None = typer.Option(None, "--max-steps", help="Override llm.max_steps."),
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    c = cfg_mod.load(config)
    if output_dir is not None:
        c.output_dir = output_dir
    if language is not None:
        c.language = language
    if tone is not None:
        c.tone = tone
    if filename_format is not None:
        c.filename_format = filename_format
    if enable_x is not None:
        c.enable_x = enable_x
    if model is not None:
        c.llm.model = model
    if max_tokens is not None:
        c.llm.max_tokens = max_tokens
    if max_searches is not None:
        c.llm.max_searches = max_searches
    if max_steps is not None:
        c.llm.max_steps = max_steps
    try:
        result = gen.run(topic, c, dry_run=dry_run)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e
    if dry_run:
        typer.echo(result)
    else:
        path, updated = result
        typer.echo(f"{'updated' if updated else 'wrote'} {path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
