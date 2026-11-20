"""Index-Reader: deterministic cable builder for Instrument Index workbooks.

Runs 100% locally. No network access, no AI engine: every result is produced
by the explicit rules in this package.
"""

from .config import VERSION

__version__ = VERSION
__all__ = ["__version__"]
