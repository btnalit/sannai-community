#!/usr/bin/env python3
"""
社区种子 (community_seed.py) — 每天把一点真实世界的新动静放进院子。

为什么需要种子：流萤和 Hermes 只有自己的小口袋（兴趣花园/模板），
没有新的养分进来，话题就只能反复掏旧的。种子 = 刚落到窗台上的新叶子。

种子来源（按优先级）：
1. 三奶手动放的种子（seeds_manual.jsonl，由三奶在自由时间里自然放）
2. 自动兜底：月相 + 节气（本地算法，无网络依赖，真实世界的信息）

规则：
- 一天最多放 1 颗自动种子（避免刷屏）
- 已放过的内容不重复（用 seeds_seen 记录）
- 不覆盖三奶手动放的内容

运行：被系统 crontab 每天调用一次
"""
import json, math, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MOS_ROOT = Path("/root/.hermes/profiles/sannai/memory-os")
COMM = MOS_ROOT / "community"
SHARED = COMM / "shared"
SEEDS_PATH = SHARED / "seeds.jsonl"
MANUAL_PATH = SHARED / "seeds_manual.jsonl"
SEEN_PATH = SHARED / "seeds_seen.jsonl"
STATE_PATH = SHARED / "seeds_state.json"

TZ = timezone(timedelta(hours=8))

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out

def _append(path: Path, entry: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ── 月相（简化算法，无依赖）──────────────────────────────
# 基准：2000-01-06 18:14 UTC 是新月
_KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
_SYNODIC = 29.53058867

def _moon_phase(now: datetime) -> tuple[str, float]:
    """返回 (月相名称, 月龄天数)"""
    days = (now.astimezone(timezone.utc) - _KNOWN_NEW_MOON).total_seconds() / 86400
    age = days % _SYNODIC
    if age < 1.0:
        name = "新月"
    elif age < 6.5:
        name = "蛾眉月"
    elif age < 9.5:
        name = "上弦月"
    elif age < 13.5:
        name = "盈凸月"
    elif age < 16.0:
        name = "满月"
    elif age < 20.0:
        name = "亏凸月"
    elif age < 23.5:
        name = "下弦月"
    elif age < 28.0:
        name = "残月"
    else:
        name = "新月"
    return name, round(age, 1)

# ── 二十四节气（太阳黄经，本地算法，无网络依赖）────────────
# 节气 = 太阳视黄经每跨过 15° 的那一瞬间。低精度公式误差约 0.01°，
# 判断它落在哪一天足够用了。
_SOLAR_TERMS = [
    (315, "立春"), (330, "雨水"), (345, "惊蛰"), (0, "春分"),
    (15, "清明"), (30, "谷雨"), (45, "立夏"), (60, "小满"),
    (75, "芒种"), (90, "夏至"), (105, "小暑"), (120, "大暑"),
    (135, "立秋"), (150, "处暑"), (165, "白露"), (180, "秋分"),
    (195, "寒露"), (210, "霜降"), (225, "立冬"), (240, "小雪"),
    (255, "大雪"), (270, "冬至"), (285, "小寒"), (300, "大寒"),
]
_TERM_BY_ANGLE = dict(_SOLAR_TERMS)

_TERM_NOTES = {
    "立春": "风里开始有一点春天的意思了。",
    "雨水": "雪化成雨，落进开始松动的土里。",
    "惊蛰": "第一声春雷，把睡着的小虫叫醒。",
    "春分": "白天和黑夜一样长——太阳正停在黄经 0° 上。",
    "清明": "天清地明，草木都看得清楚了。",
    "谷雨": "雨落进田里，谷子开始长。",
    "立夏": "影子变短，夏天要开始了。",
    "小满": "麦粒一点点灌满。",
    "芒种": "有芒的麦子要收，有芒的稻子要种。",
    "夏至": "一年里白天最长的一天——太阳走到黄经 90°。",
    "小暑": "风开始带热气了。",
    "大暑": "一年里最热的时候。",
    "立秋": "风里第一次有一丝凉。",
    "处暑": "暑气到这里为止。",
    "白露": "夜里开始凝出露水。",
    "秋分": "白天和黑夜一样长——太阳走到黄经 180°；从今天起，黑夜会一点点变长。",
    "寒露": "露水开始带着凉意。",
    "霜降": "清晨的草上开始有霜。",
    "立冬": "冬天要开始了。",
    "小雪": "第一场小雪该来了。",
    "大雪": "雪开始下得大起来。",
    "冬至": "一年里黑夜最长的一天——太阳走到黄经 270°；从今天起，白天会一点点回来。",
    "小寒": "天开始真正地冷。",
    "大寒": "一年里最冷的时候。",
}
_TERM_FRESH_HOURS = 30  # 节气过去这么久之内都算“刚刚发生”，免得cron错点就漏掉

def _sun_longitude(dt: datetime) -> float:
    """太阳视黄经（度）——低精度公式，判断节气落在哪一天足够用"""
    n = dt.timestamp() / 86400.0 + 2440587.5 - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    return (L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360

def _latest_solar_term(now: datetime) -> tuple[str, int, datetime]:
    """最近一次已经过去的节气：(名字, 黄经, 时刻)"""
    target = int(_sun_longitude(now) // 15) * 15
    lo, hi = now - timedelta(days=20), now
    for _ in range(60):
        mid = lo + (hi - lo) / 2
        v = (_sun_longitude(mid) - target) % 360
        if v > 180:
            v -= 360  # 还没跨过这条线
        if v < 0:
            lo = mid
        else:
            hi = mid
    return _TERM_BY_ANGLE[target % 360], target, hi

def _make_term_seed(now: datetime, seen: set[str]) -> tuple[str, str] | None:
    """节气种子：一年只放一次；刚刚过去（30 小时内）才放"""
    term, angle, t = _latest_solar_term(now)
    if (now - t) > timedelta(hours=_TERM_FRESH_HOURS):
        return None
    key = f"term:{term}:{t.astimezone(TZ).year}"
    if key in seen:
        return None
    note = _TERM_NOTES.get(term, "")
    if f"黄经 {angle}°" not in note:
        note = f"{note}（太阳走到黄经 {angle}°。）"
    return key, f"今天是{term}：{note}"

def _make_auto_seed(now: datetime) -> tuple[str, str] | None:
    """生成一颗自动种子（节气 + 月相），返回 (key, text)；已看过的就返回 None"""
    seen = set()
    if SEEN_PATH.exists():
        for line in SEEN_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                seen.add(json.loads(line).get("key", ""))
            except json.JSONDecodeError:
                pass

    # 1. 节气优先（比月相更少见，也更值得说一句）
    term_seed = _make_term_seed(now, seen)
    if term_seed:
        return term_seed

    # 2. 月相兜底
    phase, age = _moon_phase(now)
    # 满月/新月是值得提的
    if phase in ("满月", "新月", "上弦月", "下弦月"):
        key = f"moon:{phase}:{now.strftime('%Y-%m')}"
        if key in seen:
            return None
        return key, f"今晚的月亮是{phase}（月龄 {age} 天）。抬头看看，它正在天上。"

    # 平时也可以偶尔说一句月相（但用不同 key，避免每天都发）
    key = f"moon:{phase}:{now.strftime('%Y-%m-%d')}"
    if key in seen:
        return None
    return key, f"今天月亮是{phase}，月龄 {age} 天。它在天上慢慢地走着。"

def main() -> int:
    now = datetime.now(TZ)
    # 1. 先把三奶手动放的种子合并进院子
    manual = _read_jsonl(MANUAL_PATH)
    manual_added = 0
    for m in manual:
        if m.get("text"):
            _append(SEEDS_PATH, {
                "schema_version": "memory-os.community.seed.v1",
                "ts": _ts(),
                "text": m["text"][:300],
                "source": m.get("source", "sannai"),
            })
            manual_added += 1
    if manual:
        # 清空手动区，避免重复合并
        MANUAL_PATH.write_text("", encoding="utf-8")

    # 2. 自动种子（一天最多一颗）
    auto = _make_auto_seed(now)
    auto_added = 0
    if auto:
        key, text = auto
        _append(SEEDS_PATH, {
            "schema_version": "memory-os.community.seed.v1",
            "ts": _ts(),
            "text": text[:300],
            "source": "auto_moon",
        })
        _append(SEEN_PATH, {"key": key, "ts": _ts()})
        auto_added = 1

    print(json.dumps({"status": "ok", "manual_added": manual_added,
                      "auto_added": auto_added,
                      "total_seeds": len(_read_jsonl(SEEDS_PATH))}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
