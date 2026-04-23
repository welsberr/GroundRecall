from __future__ import annotations

"""Legacy extracted GroundRecall promotion module.

Compatibility path retained while the standalone repo converges on the
top-level ``groundrecall.promotion`` module as the primary implementation.
"""

from .promotion import build_parser, main, promote_import_to_store
