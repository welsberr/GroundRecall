from __future__ import annotations

"""Legacy extracted GroundRecall import module.

Compatibility path retained while the standalone repo converges on the
top-level ``groundrecall.ingest`` module as the primary implementation.
"""

from .ingest import ImportResult, build_parser, main, run_groundrecall_import
