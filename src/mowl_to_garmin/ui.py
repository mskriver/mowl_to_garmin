"""Terminal presentation helpers for the CLI."""

import os

import typer
from rich.console import Console
from rich.panel import Panel

SUMMARY_SEPARATOR_WIDTH = 70


def no_color():
    return os.environ.get("NO_COLOR") is not None


def _style(text, color):
    if no_color():
        return text
    return typer.style(text, fg=color)


def success(text):
    return _style(text, typer.colors.GREEN)


def error(text):
    return _style(text, typer.colors.RED)


def warning(text):
    return _style(text, typer.colors.YELLOW)


def error_panel(message):
    """Print an error panel matching typer's own error style."""
    Console(stderr=True).print(
        Panel(message, title="Error", border_style="red", title_align="left")
    )


def format_duration(seconds):
    if seconds < 1:
        return f"{seconds:.2f}s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs}s"


def format_summary(total, converted, failed):
    """Counts are only colored when they are above zero."""
    converted_str = success(str(converted)) if converted else str(converted)
    failed_str = error(str(failed)) if failed else str(failed)
    files = "file" if total == 1 else "files"
    return f"{total} {files}, {converted_str} converted, {failed_str} failed"


def print_summary(total, converted, failed):
    typer.echo("")
    typer.echo("=" * SUMMARY_SEPARATOR_WIDTH)
    typer.echo("Conversion Summary")
    typer.echo("-" * SUMMARY_SEPARATOR_WIDTH)
    typer.echo(format_summary(total, converted, failed))
    typer.echo("=" * SUMMARY_SEPARATOR_WIDTH)
