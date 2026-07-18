"""IRT discrimination engine — optional PyMC dependency.

All PyMC imports are lazy. Core bench commands (run/compare/rescore) work
without PyMC installed. Only ``bench irt *`` commands require it.
"""

from __future__ import annotations


def _check_pymc() -> None:
    """Raise ``ImportError`` with install instructions if PyMC is missing."""
    try:
        import pymc  # noqa: F401
    except ImportError:
        raise ImportError(
            "PyMC is required for IRT analysis. "
            "Install with: pip install 'bench[irt]'"
        ) from None
