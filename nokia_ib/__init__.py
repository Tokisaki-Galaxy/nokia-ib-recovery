"""Parsers for Nokia Series 30+ phone backup files."""

try:
    from importlib.metadata import version as _package_version

    __version__ = _package_version("nokia-ib-recovery")
except Exception:  # pragma: no cover - package metadata is absent when run from source
    __version__ = "0.0.0"
