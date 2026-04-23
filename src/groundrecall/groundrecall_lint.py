from __future__ import annotations

"""Legacy extracted GroundRecall lint module.

Compatibility path retained while the standalone repo converges on the
top-level ``groundrecall.lint`` module as the primary implementation.
"""

from .lint import build_parser, lint_import_directory, main
