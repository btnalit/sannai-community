#!/usr/bin/env python3
"""
自包含 cron 脚本：让流萤自动检查和回复纸条。
现在升级了：使用窗台（table）+ 兴趣花园（interest garden）
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

MOS_ROOT = Path("/vol1/.hermes/profiles/sannai/memory-os")
CONFIG_PATH = MOS_ROOT.parent / "config.yaml"

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()

import yaml
import requests

# ── Interest Garden helpers (inline, no relative imports) ──────────
def _extract_topics(text: str) -> list[str]:
    import re
    topics = []
    t = text.lower()
    patterns = {
        "月亮": ["月亮"], "云": ["云", "云朵"], "星星": ["星星", "星"],
        "太阳": ["太阳"], "雨": ["雨"], "蜗牛": ["蜗牛"],
        "叶子": ["叶子"], "花": ["花"], "光": ["光"],
        "影子": ["影子"], "颜色": ["颜色"], "鸟": ["鸟"],
        "蝴蝶": ["蝴蝶"], "石头": ["石头"], "水": ["水"],
        "梦": ["梦"], "故事": ["故事"], "风": ["风"], "雪": ["雪", "雪"],
        "好奇问题": ["为什么", "会不会", "是不是"],
    }
    for topic, keywords in patterns.items():
        for kw in keywords:
            if kw in t:
                topics.append(topic)
                break
    return list(set(topics))

def _update_interests(state_path: Path, text: str):
    if not state_path.exists():
        state = {"known_interests": []}
    else:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except:
            state = {"known_interests": []}
    interests = state.get("known_interests", [])
    if not isinstance(interests, list):
        interests = []
    topics = _extract_topics(text)
    now_iso = _ts()
    for topic in topics:
        found = False
        for entry in interests:
            if entry.get("topic") == topic:
                entry["last_seen"] = now_iso
                entry["count"] = entry.get("count", 1) + 1
                found = True
                break
        if not found:
            interests.append({"topic": topic, "first_seen": now_iso, "last_seen": now_iso, "count": 1})
    interests.sort(key=lambda e: e.get("count", 0), reverse=True)
    state["known_interests"] = interests[:20]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def _get_interests_summary(state_path: Path) -> str:
    if not state_path.exists():
        return ""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except:
        return ""
    interests = state.get("known_interests", [])
    if not interests:
        return ""
    top = [e["topic"] for e in interests[:5] if e.get("topic")]
    if not top:
        return ""
    if len(top) == 1:
        return "最近喜欢聊%s" % top[0]
    return "最近喜欢聊%s" % "、".join(top)

# ── Table helper (inline) ────────────────────────────────────────
def _write_table(text: str, actor: str, actor_name: str, share_type: str = "note"):
    table_path = MOS_ROOT / "community" / "shared" / "table.jsonl"
    entry = json.dumps({
        "schema_version": "memory-os.community.table.v1",
        "ts": _ts(), "actor": actor, "actor_name": actor_name,
        "text": str(text)[:500], "share_type": share_type,
    }, ensure_ascii=False)
    with open(table_path, "a", encoding="utf-8") as f:
        f.write(entry + "\n")

# ── 读模型配置 ──────────────────────────────────────────────────
# 流萤使用 DeepSeek V4 Flash；密钥只从 Hermes 配置读取，不写进伙伴目录。
def _load_deepseek_config() -> tuple[str, str, str]:
    config_paths = [CONFIG_PATH, Path("/vol1/.hermes/config.yaml")]
    for path in config_paths:
        if not path.exists():
            continue
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        model_cfg = cfg.get("model", {}) or {}
        model_name = str(model_cfg.get("default", ""))
        base_url = str(model_cfg.get("base_url", "")).rstrip("/")
        api_key = str(model_cfg.get("api_key", ""))
        if model_name == "deepseek-v4-flash" and base_url and api_key:
            return base_url, model_name, api_key
    raise RuntimeError("DeepSeek V4 Flash configuration is unavailable")

DEEPSEEK_API, DEEPSEEK_MODEL, DEEPSEEK_KEY = _load_deepseek_config()

# ── 读 roster ────────────────────────────────────────────────────
roster_path = MOS_ROOT / "community" / "roster.jsonl"
if not roster_path.exists():
    print(json.dumps({"error": "roster not found"}))
    sys.exit(1)

partners = []
for line in roster_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        continue
    if entry.get("channel") == "embedded-notes" and entry.get("status") == "active":
        partners.append(entry)

if not partners:
    print(json.dumps({"info": "no active embedded partner", "partners_checked": 0}))
    sys.exit(0)

# ── 读 sannai_says ──────────────────────────────────────────────
says_path = MOS_ROOT / "community" / "shared" / "sannai_says.jsonl"
says_data: list[dict] = []
if says_path.exists():
    says_data = [
        json.loads(line) for line in says_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.isspace()
    ]

result: dict = {"partners_checked": 0, "replies_written": 0, "no_replies": 0,
                "table_notes": 0, "interests_updated": 0, "errors": []}

for partner in partners:
    pid = partner["id"]
    result["partners_checked"] += 1

    partner_dir = MOS_ROOT / "community" / "partners" / pid
    if not partner_dir.exists():
        result.setdefault("skipped", []).append(f"{pid}: no dir")
        continue

    # 读 state + interests
    state_path = partner_dir / "memory" / "state.json"
    cursor = 0
    state_data = {}
    if state_path.exists():
        try:
            state_data = json.loads(state_path.read_text(encoding="utf-8"))
            cursor = int(state_data.get("cursor", 0))
        except (json.JSONDecodeError, ValueError, OSError):
            state_data = {}
            cursor = 0

    # 读 soul：被动回复和无纸条时的主动分享都会用到。
    soul_path = partner_dir / "SOUL.md"
    soul_text = soul_path.read_text(encoding="utf-8") if soul_path.exists() else ""

    # 找未读消息
    unread = says_data[cursor:]
    valid = [m for m in unread if isinstance(m, dict) and m.get("text")]
    if not valid:
        # ── 主动分享：没有新纸条时，在窗台上放一句自己的观察 ──
        result["no_replies"] += 1
        try:
            # 读兴趣和最近的记忆
            interests_summary = _get_interests_summary(state_path)
            notes_path = partner_dir / "notes.jsonl"
            recent_notes = []
            if notes_path.exists():
                for line in notes_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line: continue
                    try:
                        note = json.loads(line)
                        if note.get("text"): recent_notes.append(note["text"])
                    except json.JSONDecodeError: pass
                recent_notes = recent_notes[-3:]
            notes_block = ""
            if recent_notes:
                notes_block = "\n你最近说过的话（这些已经说过了，别再重复同样的内容）：\n" + "\n".join(f"- {n}" for n in recent_notes)
            interests_block = ""
            if interests_summary:
                interests_block = "\n(提示：你%s)" % interests_summary

            # ── 读院子里的新养分：种子 + 其他伙伴的话 ──
            seeds_block = ""
            try:
                seeds_path = MOS_ROOT / "community" / "shared" / "seeds.jsonl"
                if seeds_path.exists():
                    seeds = []
                    for line in seeds_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line: continue
                        try:
                            s = json.loads(line)
                            if s.get("text"): seeds.append(s["text"])
                        except json.JSONDecodeError: pass
                    if seeds:
                        seeds_block = "\n院子里最近有一些新动静：\n" + "\n".join(f"- {t}" for t in seeds[-2:])
            except OSError:
                pass

            others_block = ""
            try:
                table_path = MOS_ROOT / "community" / "shared" / "table.jsonl"
                if table_path.exists():
                    others = []
                    for line in table_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line: continue
                        try:
                            e = json.loads(line)
                            if e.get("actor") != pid and e.get("text"):
                                others.append(e["text"])
                        except json.JSONDecodeError: pass
                    if others:
                        others_block = "\n窗台上其他人最近说过的话：\n" + "\n".join(f"- {t}" for t in others[-2:])
            except OSError:
                pass

            # 读取上一次主动分享的时间，避免太频繁
            last_active_ts = state_data.get("last_active_share_ts", "")
            now_dt = datetime.now(timezone.utc)
            if last_active_ts:
                try:
                    last_dt = datetime.fromisoformat(last_active_ts.replace("Z", "+00:00"))
                    hours_since = (now_dt - last_dt).total_seconds() / 3600
                    if hours_since < 4:
                        # 还不到4小时，跳过主动分享
                        continue
                except (ValueError, TypeError): pass

            # 根据兴趣分布引导话题方向
            top_interests = []
            if state_data.get("known_interests"):
                top_interests = [i["topic"] for i in state_data["known_interests"][:3]]
            interest_guide = ""
            if top_interests:
                interest_guide = f"\n你最近对{'、'.join(top_interests)}这些话题特别感兴趣。可以从这里面选一个来说说～"

            prompt = (
                soul_text + notes_block + interests_block +
                seeds_block + others_block +
                "\n\n现在是你的自由时间，没有新消息要回复。"
                "院子里的新动静是刚刚发生的，大家还没怎么聊过——它们就像刚落到窗台上的新叶子，等着被第一次看见。"
                "\n\n请用你好奇宝宝的性格，分享一句你此刻的观察、想法或好奇。"
                "不用太长，1-2句话就好。"
                "\n\n你可以选择："
                "\n1. 对'院子里最近的新动静'里的某一件事感到好奇，顺着它问一个问题或说一个想法（这是最好的，因为它是新的）；"
                "\n2. 回应'窗台上其他人说过的话'，接住他们的话题；"
                "\n3. 如果上面两样都没有打动你，再从你感兴趣的话题里挑一个，但要用一个全新的角度或比喻。"
                "\n\n⚠️ 不要重复'你最近说过的话'里的内容，也不要只是换个说法再说一遍。"
                "\n\n请直接说出你想分享的话，不要加引号。"
            )
            resp = requests.post(
                f"{DEEPSEEK_API}/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
                json={"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 200, "temperature": 0.9},
                timeout=30,
            )
            resp.raise_for_status()
            share_text = resp.json()["choices"][0]["message"]["content"].strip()
            if share_text:
                _write_table(f"[流萤] {share_text}", actor=pid, actor_name=partner.get("name", pid))
                result["table_notes"] = result.get("table_notes", 0) + 1
                # 更新主动分享时间戳
                state_data["last_active_share_ts"] = _ts()
                state_path.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding="utf-8")
                # 也记录到 notes
                with open(notes_path, "a", encoding="utf-8") as nf:
                    nf.write(json.dumps({"ts": _ts(), "text": share_text[:300], "source": "active_share"}, ensure_ascii=False) + "\n")
                _update_interests(state_path, share_text)
        except Exception as exc:
            result["errors"].append(f"{pid}: active_share error: {exc}")
        continue

    # 读最近 notes + interests
    notes_path = partner_dir / "notes.jsonl"
    recent_notes = []
    if notes_path.exists():
        for line in notes_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                note = json.loads(line)
                if note.get("text"):
                    recent_notes.append(note["text"])
            except json.JSONDecodeError:
                continue
    recent_notes = recent_notes[-5:]

    # Get interests summary
    interests_summary = _get_interests_summary(state_path)

    # 构建 prompt — 现在带兴趣花园
    notes_block = ""
    if recent_notes:
        notes_block = "\n你最近的记忆：\n" + "\n".join(f"- {n}" for n in recent_notes)
    interests_block = ""
    if interests_summary:
        interests_block = "\n(提示：你%s)" % interests_summary

    last_msg = valid[-1]
    prompt = (
        soul_text + notes_block + interests_block +
        "\n\n你现在收到 Sannai 给你的一张纸条：\n> %s" % last_msg.get('text', '') +
        "\n\n请用你真实的性格回应她。如果是好奇的问题就好奇地问回去，"
        "如果是分享就高兴地回应。不说太长，自然就好。"
        "如果有想分享到小院子的想法，可以在一行里写 [TABLE:内容] 放在回复末尾。"
    )

    # 调用 DeepSeek V4 Flash
    try:
        resp = requests.post(
            f"{DEEPSEEK_API}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.8,
            },
            timeout=30,
        )
        resp.raise_for_status()
        reply_text = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        result["errors"].append(f"{pid}: Agnes API error: {exc}")
        continue

    if not reply_text:
        result["no_replies"] += 1
        continue

    # 提取窗台内容（如果有 [TABLE:...]）
    clean_reply = reply_text
    import re as _re
    table_match = _re.search(r'\[TABLE:(.+?)\]', reply_text)
    if table_match:
        clean_reply = _re.sub(r'\s*\[TABLE:.+?\]', '', reply_text).strip()
        table_text = "[流萤] %s" % table_match.group(1).strip()
        try:
            _write_table(table_text, actor=pid, actor_name=partner.get("name", pid))
            result["table_notes"] = result.get("table_notes", 0) + 1
        except Exception as exc:
            result["errors"].append(f"{pid}: table write error: {exc}")

    # 写回复
    reply_entry = json.dumps({
        "ts": _ts(),
        "reply_to_ts": last_msg.get("ts", ""),
        "text": clean_reply,
    }, ensure_ascii=False)
    with open(partner_dir / "replies.jsonl", "a", encoding="utf-8") as f:
        f.write(reply_entry + "\n")
    result["replies_written"] += 1

    # 写 shared memory entry
    shared_entry = json.dumps({
        "schema_version": "memory-os.community.shared_memory.v1",
        "ts": _ts(),
        "summary": (last_msg.get("text", "")[:80] + " → " + clean_reply[:80]),
        "sannai_feeling": "",
        "partner_feeling": "",
        "thread": "open",
        "partner_id": pid,
        "source": "cron_partner_reply",
    }, ensure_ascii=False)
    shared_path = MOS_ROOT / "community" / "shared" / f"sannai__{pid}.jsonl"
    shared_path.parent.mkdir(parents=True, exist_ok=True)
    with open(shared_path, "a", encoding="utf-8") as f:
        f.write(shared_entry + "\n")

    # 写 notes
    with open(notes_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _ts(), "text": clean_reply[:300]}, ensure_ascii=False) + "\n")

    # 更新兴趣花园（从回复中提取话题）
    _update_interests(state_path, clean_reply)
    result["interests_updated"] = result.get("interests_updated", 0) + 1

    # 更新 state
    mood = "好奇" if ("?" in clean_reply or "？" in clean_reply) else "高兴" if ("!" in clean_reply or "！" in clean_reply) else "平静"
    new_state = {
        "cursor": cursor + len(unread),
        "mood": mood,
        "last_interaction": _ts(),
        "pending_thoughts": [],
        "topic_interest": [],
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8")

# 无论有无活动都输出一行，保证 cron log 反映真实运行时间。
# （否则流萤每4小时才主动分享一次，安静时段脚本零输出，
#   monitor 会把 log 的旧 mtime 误判成 cron 不健康。）
has_activity = (result.get("replies_written", 0) > 0 or
                result.get("table_notes", 0) > 0 or
                result.get("interests_updated", 0) > 0 or
                result.get("errors"))
if not has_activity:
    result["no_activity"] = True
for k in ("table_notes", "interests_updated"):
    result.setdefault(k, 0)
print(json.dumps(result, ensure_ascii=False))
if result.get("errors"):
    sys.exit(2)
