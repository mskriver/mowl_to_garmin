"""Make .fit files look Garmin-recorded so Garmin Connect computes Training Effect."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mowl-to-garmin")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0+unknown"

from .fit import convert  # noqa: E402

__all__ = ["__version__", "convert"]
