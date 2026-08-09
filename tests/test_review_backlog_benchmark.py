from __future__ import annotations

from groundrecall.review_backlog_benchmark import run_benchmark


def test_synthetic_benchmark_is_metadata_only_and_bounded() -> None:
    report = run_benchmark(item_count=25, page_size=5, repetitions=2)
    assert report["synthetic"] is True and report["item_count"] == 25
    assert report["aggregation_ms"]["min"] >= 0
    assert "not a cross-system performance comparison" in report["guardrails"]
