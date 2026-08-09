"""Reproducible synthetic review-backlog benchmark (RB8)."""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from statistics import median

from .review_backlog import aggregate_backlog
from .review_dashboard import dashboard_digest


def _fixture(root: Path, count: int) -> None:
    directory = root / "imports" / "synthetic"; directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({"import_id": "synthetic"}), encoding="utf-8")
    items = [{"queue_id": f"q-{i}", "candidate_type": "claim", "candidate_id": f"c-{i}", "status": "needs_review", "priority": 10 if i % 20 == 0 else 50, "release_level": "public"} for i in range(count)]
    (directory / "review_queue.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (directory / "artifacts.jsonl").write_text("", encoding="utf-8")


def run_benchmark(*, item_count: int = 1000, page_size: int = 50, repetitions: int = 5) -> dict:
    if item_count < 1 or page_size < 1 or repetitions < 1: raise ValueError("benchmark parameters must be positive")
    with tempfile.TemporaryDirectory(prefix="groundrecall-review-benchmark-") as temporary:
        root = Path(temporary); _fixture(root, item_count)
        aggregation = []; pagination = []
        for _ in range(repetitions):
            start = time.perf_counter(); digest = aggregate_backlog(root, maximum_release_level="public", limit=page_size); aggregation.append((time.perf_counter() - start) * 1000)
            start = time.perf_counter(); dashboard_digest(str(root), page_size=page_size); pagination.append((time.perf_counter() - start) * 1000)
    return {"schema_version": "groundrecall.review-backlog-benchmark.v1", "synthetic": True, "item_count": item_count, "page_size": page_size, "repetitions": repetitions, "aggregation_ms": {"median": median(aggregation), "min": min(aggregation), "max": max(aggregation)}, "dashboard_pagination_ms": {"median": median(pagination), "min": min(pagination), "max": max(pagination)}, "guardrails": ["synthetic fixture only", "metadata-only output", "timings are host/cache dependent", "not a cross-system performance comparison"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark synthetic GroundRecall review backlog aggregation.")
    parser.add_argument("--items", type=int, default=1000); parser.add_argument("--page-size", type=int, default=50); parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args(); print(json.dumps(run_benchmark(item_count=args.items, page_size=args.page_size, repetitions=args.repetitions), indent=2))
