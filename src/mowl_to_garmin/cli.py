"""Command line interface for mowl-to-garmin."""

import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from . import __version__, ui
from .fit import PRODUCTS, convert
from .vo2 import Estimate, estimate_vo2max, max_hr_from_age

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


Vo2 = Annotated[
    bool,
    typer.Option(
        "--vo2",
        help="Experimental: print a VO2 Max estimate from power and heart rate. "
        "Needs --weight and --max-hr (or --age). The output file is not changed.",
    ),
]

Weight = Annotated[
    float | None,
    typer.Option(
        "--weight",
        help="Body weight in kg, for --vo2.",
        envvar="MOWL_TO_GARMIN_WEIGHT",
        metavar="KG",
        min=20,
        max=300,
        show_default=False,
    ),
]

MaxHr = Annotated[
    int | None,
    typer.Option(
        "--max-hr",
        help="Max heart rate in bpm, for --vo2. Find it under heart rate zones "
        "in Garmin Connect or on your watch.",
        envvar="MOWL_TO_GARMIN_MAX_HR",
        metavar="BPM",
        min=100,
        max=240,
        show_default=False,
    ),
]

Age = Annotated[
    int | None,
    typer.Option(
        "--age",
        help="Age in years, used for --vo2 to estimate max heart rate when "
        "--max-hr is not given (less accurate).",
        envvar="MOWL_TO_GARMIN_AGE",
        metavar="YEARS",
        min=10,
        max=110,
        show_default=False,
    ),
]


def resolve_vo2_inputs(weight, max_hr, age):
    """Return (max_hr, missing, note) for --vo2."""
    note = None
    if max_hr is None and age is not None:
        max_hr = max_hr_from_age(age)
        note = (f"ℹ️  Max heart rate estimated from age as {max_hr} bpm; "
                "pass --max-hr for a more accurate VO2 Max")
    missing = []
    if weight is None:
        missing.append("weight")
    if max_hr is None:
        missing.append("max heart rate")
    return max_hr, missing, note


def vo2_suffix(raw, weight, max_hr):
    try:
        result = estimate_vo2max(raw, weight, max_hr)
    except Exception as e:  # never let the estimate break a conversion
        return f" · VO2 Max: not estimated ({e})"
    if isinstance(result, Estimate):
        return f" · VO2 Max est. {result.vo2max:.1f} (R² {result.r2:.2f}, {result.blocks} blocks)"
    return f" · VO2 Max: not enough data ({result.reason})"


@app.command()
def main(
    paths: Paths,
    product: Product = DEFAULT_PRODUCT_NAME,
    vo2: Vo2 = False,
    weight: Weight = None,
    max_hr: MaxHr = None,
    age: Age = None,
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

    if vo2:
        max_hr, missing, note = resolve_vo2_inputs(weight, max_hr, age)
        if missing:
            typer.echo(ui.warning(
                "⚠️  --vo2 needs --weight and --max-hr or --age "
                f"(missing: {', '.join(missing)}); skipping VO2 Max estimate\n"
            ), err=True)
            vo2 = False
        elif note:
            typer.echo(note + "\n")

    ok = 0
    for f in files:
        try:
            raw = f.read_bytes()
            new = convert(raw, product_id)
            dest = f.with_name(f.stem + "_garmin.fit")
            dest.write_bytes(new)
            suffix = vo2_suffix(raw, weight, max_hr) if vo2 else ""
            typer.echo(f"✅ {f.name} → {dest.name}{suffix}")
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
