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
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MOS_ROOT = Path("/vol1/.hermes/profiles/sannai/memory-os")
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

def _make_auto_seed(now: datetime) -> tuple[str, str] | None:
    """生成一颗自动种子（月相），返回 (key, text)；已看过的就返回 None"""
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
