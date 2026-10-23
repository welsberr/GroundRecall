import json

import pytest

from groundrecall.lede_brief_context import (
    ContextCheckpoint,
    ContextObservation,
    CoverageState,
    advise_context,
    load_ledebrief_package,
    write_checkpoint,
)


def _package(root):
    (root / "overview.md").write_text("# Overview\n\nAlpha.", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "source_id": "fixture",
                "source_version": "v1",
                "status": "candidate",
                "inventory": {"inventory_id": "inv-1", "units": [{"unit_id": "u1"}]},
                "artifacts": [{"document_id": "overview", "markdown": "# Overview"}],
            }
        ),
        encoding="utf-8",
    )


def test_load_package_separates_collection_required_and_loaded(tmp_path):
    _package(tmp_path)
    package, coverage = load_ledebrief_package(tmp_path, required_unit_ids=["u1"], loaded_unit_ids=["u1"])
    assert package.inventory_id == "inv-1"
    assert coverage.collection_unit_ids == ["u1"]
    assert coverage.loaded_status == "unconfirmed"


def test_load_package_rejects_missing_required_unit(tmp_path):
    _package(tmp_path)
    with pytest.raises(ValueError, match="absent"):
        load_ledebrief_package(tmp_path, required_unit_ids=["missing"])


def test_advice_recommends_checkpoint_when_headroom_is_negative():
    advice = advise_context(
        ContextObservation(current_input_tokens=95, context_capacity_tokens=100, projected_next_turn_tokens=10),
        CoverageState(required_unit_ids=["u1"]),
    )
    assert advice.action == "checkpoint-and-reduce"


def test_checkpoint_is_atomically_written(tmp_path):
    path = write_checkpoint(ContextCheckpoint(session_id="s1", objective="resume task"), tmp_path / "checkpoint.json")
    assert json.loads(path.read_text(encoding="utf-8"))["objective"] == "resume task"
