"""Tests for the 24 solar terms (节气) support in scripts/community_seed.py.

The script is loaded as a module by path (it is a cron entry point, not part of
the package). Everything tested here is read-only — no seeds are written.
"""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "community_seed.py"
_spec = importlib.util.spec_from_file_location("community_seed", SCRIPT)
assert _spec is not None and _spec.loader is not None
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)

TZ = timezone(timedelta(hours=8))


def _cst(y, m, d, hh=8, mm=20):
    """cron 跑的时刻：每天 08:20 CST"""
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def test_autumn_equinox_2026_is_on_sep_23():
    name, angle, t = seed._latest_solar_term(_cst(2026, 9, 23))
    assert name == "秋分"
    assert angle == 180
    assert t.astimezone(TZ).strftime("%Y-%m-%d") == "2026-09-23"


def test_winter_solstice_2026_is_on_dec_22():
    name, angle, t = seed._latest_solar_term(_cst(2026, 12, 22))
    assert name == "冬至"
    assert angle == 270
    assert t.astimezone(TZ).strftime("%Y-%m-%d") == "2026-12-22"


def test_term_seed_fires_on_term_day():
    got = seed._make_term_seed(_cst(2026, 9, 23), seen=set())
    assert got is not None
    key, text = got
    assert key == "term:秋分:2026"
    assert text.startswith("今天是秋分")
    assert "180°" in text


def test_term_seed_is_not_repeated_within_the_year():
    assert seed._make_term_seed(_cst(2026, 9, 23), seen={"term:秋分:2026"}) is None


def test_term_seed_does_not_fire_when_the_term_is_long_gone():
    # 2026-09-21 距白露（9 月 7 日）已两周
    assert seed._make_term_seed(_cst(2026, 9, 21), seen=set()) is None


def test_term_seed_is_caught_next_morning_if_it_landed_after_cron():
    # 秋分时刻 08:16 刚好在 cron 08:20 之前；把 cron 想象得更晚一点也应抓得到
    got = seed._make_term_seed(_cst(2026, 9, 23, 23, 0), seen=set())
    assert got is not None and got[0] == "term:秋分:2026"


def test_sweep_2026_finds_all_24_terms_in_the_right_months():
    expected_month = {
        "小寒": 1, "大寒": 1, "立春": 2, "雨水": 2, "惊蛰": 3, "春分": 3,
        "清明": 4, "谷雨": 4, "立夏": 5, "小满": 5, "芒种": 6, "夏至": 6,
        "小暑": 7, "大暑": 7, "立秋": 8, "处暑": 8, "白露": 9, "秋分": 9,
        "寒露": 10, "霜降": 10, "立冬": 11, "小雪": 11, "大雪": 12, "冬至": 12,
    }
    found = {}
    day = datetime(2026, 1, 1, tzinfo=TZ)
    while day.year == 2026:
        got = seed._make_term_seed(day.replace(hour=8, minute=20), seen=set())
        if got:
            name = got[0].split(":")[1]
            found.setdefault(name, day.month)
        day += timedelta(days=1)

    assert set(found) == set(expected_month), f"missing: {set(expected_month) - set(found)}"
    for name, month in found.items():
        assert month == expected_month[name], f"{name} 落在 {month} 月，应该是 {expected_month[name]} 月"
