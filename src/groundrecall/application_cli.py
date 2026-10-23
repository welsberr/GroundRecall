"""Small model-free CLI client for the application read contract."""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .application_contract import SearchRequest
from .application_service import ApplicationReadService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groundrecall application-search",
        description="Search GroundRecall through the application read service.",
    )
    parser.add_argument("store_dir", help="Configured GroundRecall store directory")
    parser.add_argument("query", help="Text to search for")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument("--json", action="store_true", help="Shortcut for --format json")
    parser.add_argument("--scope", default="private", help="Permitted application scope")
    parser.add_argument("--limit", type=int, default=20, help="Maximum results (1-100)")
    parser.add_argument("--request-id", default=None, help="Optional correlation ID")
    return parser


def _human_output(response) -> str:
    lines = [
        f"GroundRecall search: {len(response.results)} result(s)"
        f" [scope={response.effective_scope}, generation={response.index_generation}]"
    ]
    for result in response.results:
        title = result.title or result.stable_id
        lines.append(f"- {title} ({result.kind})")
        if result.excerpt:
            lines.append(f"  {result.excerpt}")
        lines.append(f"  URL: {result.human_url}")
    for diagnostic in response.diagnostics:
        lines.append(f"diagnostic: {diagnostic}")
    return "\n".join(lines)


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        request = SearchRequest(
            query=args.query,
            scope=args.scope,
            limit=args.limit,
        )
    except Exception as exc:
        parser.error(str(exc))
    response = ApplicationReadService(args.store_dir).search(
        request,
        request_id=args.request_id,
    )
    if args.json or args.format == "json":
        print(json.dumps(response.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(_human_output(response))
    return 0


def main() -> None:
    run()


if __name__ == "__main__":
    main()
