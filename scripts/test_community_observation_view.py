from __future__ import annotations

from pathlib import Path

from community_life_echo import build_echo


def test_echo_accepts_community_observation_view(tmp_path: Path) -> None:
    view = {
        "community_table": [
            { "ts": "2026-08-13T10:00:00+00:00", "actor": "p-1", "actor_name": "伙伴", "text": "月亮" }
        ],
        "treasure_dir": [{"name": "moon.md", "text": "月亮"}],
    }
    result = build_echo(
        now=__import__("datetime").datetime(2026, 8, 13, 12, tzinfo=__import__("datetime").timezone.utc),
        hours=48,
        limit=2,
        observation_view=view,
    )
    assert result["read_only"] is True
    assert result["intersections"]
    assert result["intersections"][0]["status"] == "read_only_observation"
