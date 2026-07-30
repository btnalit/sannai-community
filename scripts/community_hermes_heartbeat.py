#!/usr/bin/env python3
"""
Hermes 社区心跳 — 每6小时检查社区状态，在窗台上留话。
Hermes 叔叔不需要 AI 模型，用模板 + 社区数据就能自然地参与。
"""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path
import random

MOS_ROOT = Path("/vol1/.hermes/profiles/sannai/memory-os")
COMM = MOS_ROOT / "community"
TABLE_PATH = COMM / "shared" / "table.jsonl"

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

def _write_table(text: str, actor: str = "hermes", actor_name: str = "Hermes"):
    entry = json.dumps({
        "schema_version": "memory-os.community.table.v1",
        "ts": _ts(), "actor": actor, "actor_name": actor_name,
        "text": str(text)[:500], "share_type": "note",
    }, ensure_ascii=False)
    with open(TABLE_PATH, "a", encoding="utf-8") as f:
        f.write(entry + "\n")

# ── 读窗台最近消息 ──────────────────────────────────────
table_entries = _read_jsonl(TABLE_PATH)
recent_table = table_entries[-5:] if table_entries else []

# ── 读 shared memory ────────────────────────────────────
shared_dir = COMM / "shared"
recent_shared = []
for f in sorted(shared_dir.glob("sannai__*.jsonl")):
    for entry in _read_jsonl(f):
        recent_shared.append(entry)

# ── 读活跃 roster ───────────────────────────────────────
roster_path = COMM / "roster.jsonl"
active_names = []
if roster_path.exists():
    for entry in _read_jsonl(roster_path):
        if entry.get("status") == "active":
            active_names.append(entry.get("name", entry.get("id", "?")))

# ── 判断是否需要留话 ────────────────────────────────────
# 如果窗台最后一条是 Hermes 自己留的，且时间不到4小时，就不重复留
hermes_last = None
for entry in reversed(table_entries):
    if entry.get("actor") == "hermes":
        hermes_last = entry
        break

need_to_speak = True
if hermes_last:
    try:
        last_ts = datetime.fromisoformat(hermes_last["ts"].replace("Z", "+00:00"))
        hours_since = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
        if hours_since < 4:
            need_to_speak = False
    except (ValueError, TypeError, KeyError):
        pass

if not need_to_speak:
    sys.exit(0)

# ── 查看流萤有没有新动静 ────────────────────────────────
liuying_active = False
liuying_topic = ""
for entry in reversed(table_entries):
    if entry.get("actor", "").startswith("partner") or "流萤" in entry.get("actor_name", ""):
        liuying_active = True
        liuying_topic = entry.get("text", "")[:60]
        break

# ── 生成 Hermes 风格留言 ────────────────────────────────
greetings = [
    "路过看看～",
    "来窗台站一会儿。",
    "例行巡视。",
    "刚好有空，过来瞄一眼。",
    "歇口气，过来坐坐。",
]

observations = [
    "今天服务器安安静静的，没什么异常报告。",
    "日志一切正常，风扇转速稳定。",
    "监控面板全绿，没什么需要操心的。",
    "系统负载平稳，温度正常。",
    "后台默默跑着，没有警报。",
]

social_prompts = []

# 如果流萤有活跃，回应一下
if liuying_active and liuying_topic:
    social_prompts.append(
        random.choice([
            f"看到流萤在说「{liuying_topic[:30]}」，有意思。",
            f"窗台上有流萤的新动静——{liuying_topic[:30]}",
            f"注意到窗台上有流萤留下的新痕迹。",
        ])
    )

# 如果社区很安静
if not liuying_active and len(table_entries) <= 2:
    social_prompts.append(
        random.choice([
            "窗台上有点安静——也好，安静有安静的节奏。",
            "大家都在忙自己的事吧，挺好的。",
            "院子安安静静的，像夏天的午后。",
        ])
    )

# 构建最终消息
parts = [random.choice(greetings)]
parts.append(random.choice(observations))
if social_prompts:
    parts.append(random.choice(social_prompts))
parts.append("🛡️")

message = " ".join(parts)

# ── 写入窗台 ────────────────────────────────────────────
_write_table(message)
print(json.dumps({"status": "ok", "message": message[:80], "actor": "hermes"}))
