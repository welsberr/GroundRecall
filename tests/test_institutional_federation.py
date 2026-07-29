from __future__ import annotations

import json
from pathlib import Path

from groundrecall.institutional_federation import (
    INSTITUTIONAL_FEDERATION_SCHEMA_VERSION,
    INSTITUTIONAL_POLICY_ACTIONS,
    INSTITUTIONAL_POLICY_FIXTURE_SCHEMA_VERSION,
    build_institutional_federation_capability_report,
)
from groundrecall import inspect as inspect_module
from groundrecall.inspect import inspect_store
from groundrecall.policy import PolicyDecisionPoint, PolicyDecisionValue, PolicyRequest


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "institutional_policy_cases.json"


def test_institutional_policy_fixture_covers_every_action() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == INSTITUTIONAL_POLICY_FIXTURE_SCHEMA_VERSION
    expected_actions = {(item["decision_point"], item["action"]) for item in INSTITUTIONAL_POLICY_ACTIONS}
    fixture_actions = {(item["decision_point"], item["action"]) for item in payload["cases"]}
    assert fixture_actions == expected_actions
    for case in payload["cases"]:
        request = PolicyRequest(
            decision_point=case["decision_point"],
            subject_id="fixture-subject",
            action=case["action"],
            scope_id="fixture-scope",
        )
        assert request.decision_point in PolicyDecisionPoint.__args__
        assert case["expected_decision"] in PolicyDecisionValue.__args__


def test_institutional_capability_report_is_deterministic_and_versioned() -> None:
    report = build_institutional_federation_capability_report()
    assert report == build_institutional_federation_capability_report()
    assert report["schema_version"] == INSTITUTIONAL_FEDERATION_SCHEMA_VERSION
    assert report["policy_action_count"] == len(INSTITUTIONAL_POLICY_ACTIONS)
    assert report["summary"] == {"implemented": 2, "partial": 0, "future": 9}

    compact = build_institutional_federation_capability_report(compact=True)
    assert compact["schema_version"] == INSTITUTIONAL_FEDERATION_SCHEMA_VERSION
    assert "capabilities" not in compact


def test_inspect_can_include_institutional_capability_report(tmp_path: Path) -> None:
    payload = inspect_store(tmp_path / "store", include_institutional_federation=True)
    assert payload["institutional_federation"]["schema_version"] == INSTITUTIONAL_FEDERATION_SCHEMA_VERSION
    assert payload["institutional_federation"]["summary"]["future"] == 9


def test_inspect_cli_can_emit_institutional_capability_report(tmp_path: Path, capsys) -> None:
    import sys

    original_argv = sys.argv
    try:
        sys.argv = [
            "groundrecall inspect",
            str(tmp_path / "store"),
            "--institutional-federation-summary",
        ]
        inspect_module.main()
    finally:
        sys.argv = original_argv
    output = capsys.readouterr().out
    assert INSTITUTIONAL_FEDERATION_SCHEMA_VERSION in output
    assert '"future": 9' in output
