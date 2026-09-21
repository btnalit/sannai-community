from pathlib import Path

from community_life_dashboard import build_dashboard


def test_dashboard_accepts_observation_view(tmp_path: Path) -> None:
    result = build_dashboard({
        "community_table": [{"id": "x"}],
        "state": {"awake": True, "mood": "quiet"},
        "treasure_dir": [{"name": "a.md"}],
    })
    assert result["read_only"] is True
    assert result["table_records"] == 1
    assert result["state_present"] is True
    assert result["state_keys"] == ["awake", "mood"]
    assert "state_files_present" not in result
