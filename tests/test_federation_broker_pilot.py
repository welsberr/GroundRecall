from __future__ import annotations

from pathlib import Path

from groundrecall.federation_broker_pilot import run_synthetic_pilot


def test_two_participant_synthetic_broker_pilot_is_isolated_and_complete(tmp_path: Path) -> None:
    result = run_synthetic_pilot(tmp_path / "pilot")

    assert result["result"] == "passed"
    assert len(result["participants"]) == 2
    assert len(result["directions"]) == 2
    assert result["promoted"] is False
    assert result["live_compose_touched"] is False
    assert "SQLite backup and restore" in result["lifecycle_checks"]
    assert "service restart persistence" in result["lifecycle_checks"]
