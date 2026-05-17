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
    force: bool = typer.Option(False, "--force", help="Overwrite existing file."),
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    c = cfg_mod.load(config)
    result = gen.run(topic, c, dry_run=dry_run, force=force)
    if dry_run:
        typer.echo(result)
    else:
        typer.echo(f"wrote {result}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
