"""Command line interface for mowl-to-garmin."""

import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from . import __version__, ui
from .fit import PRODUCTS, convert

DEFAULT_PRODUCT_NAME = "edge830"

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


def version_callback(value: bool) -> None:
    """Print version and exit when --version is passed."""
    if value:
        typer.echo(f"mowl-to-garmin, version {__version__}")
        raise typer.Exit()


def parse_product(value: str) -> int:
    product = PRODUCTS.get(value.lower())
    if product is not None:
        return product
    try:
        return int(value)
    except ValueError:
        names = ", ".join(PRODUCTS)
        raise typer.BadParameter(
            f"{value!r} is not a product id or one of: {names}"
        ) from None


def product_label(product: int) -> str:
    for name, number in PRODUCTS.items():
        if number == product:
            return f"Garmin {name} (product {product})"
    return f"Garmin product {product}"


def collect_files(paths: list[Path]) -> list[Path]:
    files = []
    for p in paths:
        if p.is_dir():
            files += sorted(f for f in p.glob("*.fit")
                            if not f.stem.endswith("_garmin"))
        else:
            files.append(p)
    return files


def _tolerate_legacy_encodings() -> None:
    # Emoji must not crash the tool on consoles that are not UTF-8 (old Windows)
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


Paths = Annotated[
    list[Path],
    typer.Argument(
        help=".fit files, or folders containing .fit files.",
        show_default=False,
        metavar="PATHS...",
    ),
]

Product = Annotated[
    str,
    typer.Option(
        "-p",
        "--product",
        help=f"Garmin product name ({', '.join(PRODUCTS)}) or numeric product id.",
        envvar="MOWL_TO_GARMIN_PRODUCT",
        metavar="NAME|ID",
        callback=lambda value: str(parse_product(value)),
    ),
]

Version = Annotated[
    bool,
    typer.Option(
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Display version number.",
    ),
]


@app.command()
def main(
    paths: Paths,
    product: Product = DEFAULT_PRODUCT_NAME,
    version: Version = False,
) -> None:
    """Make .fit files look like they were recorded on a Garmin device, so
    Garmin Connect calculates Training Effect / Training Load for them.

    Only the device fields are changed. Everything else - heart rate, power,
    cadence, laps, timestamps - is copied byte for byte. Converted files are
    written next to the originals as NAME_garmin.fit.
    """
    _tolerate_legacy_encodings()
    product_id = int(product)

    files = collect_files(paths)
    if not files:
        ui.error_panel("No .fit files found.")
        raise typer.Exit(1)

    start = time.monotonic()
    noun = "file" if len(files) == 1 else "files"
    typer.echo(f"\n🔄 Converting {len(files)} {noun} to {product_label(product_id)}...\n")

    ok = 0
    for f in files:
        try:
            new = convert(f.read_bytes(), product_id)
            dest = f.with_name(f.stem + "_garmin.fit")
            dest.write_bytes(new)
            typer.echo(f"✅ {f.name} → {dest.name}")
            ok += 1
        except Exception as e:
            typer.echo(f"❌ {f.name}: {ui.error(str(e))}")

    failed = len(files) - ok
    ui.print_summary(len(files), ok, failed)
    typer.echo(f"\nTotal runtime: {ui.format_duration(time.monotonic() - start)}")

    if failed:
        typer.echo(f"\n❌ {failed} out of {len(files)} {noun} failed to convert", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n✅ All files converted: {ok} out of {len(files)}")
    typer.echo("📤 Upload the *_garmin.fit files to Garmin Connect (web: Import Data).")


if __name__ == "__main__":
    app()
