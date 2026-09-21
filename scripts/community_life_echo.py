#!/usr/bin/env python3
"""Read-only, source-grounded intersections in Sannai's courtyard.

The echo is deliberately modest: it surfaces up to two lexical overlaps among
recent table shares and the current treasure index. It never writes, approves
memory, sends messages, diagnoses emotion, or recommends action.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path('/root/.hermes/profiles/sannai')
COMM = ROOT / 'memory-os' / 'community'
STATE = Path('/srv/sannai/state/sannai')
TREASURE = Path('/srv/sannai/data/treasure/小宝贝的宝库')
SCHEMA = 'sannai.community_life_echo.v1'

# Common words are intentionally excluded; this is a gentle lexical bridge,
# not a semantic or psychological inference engine.
STOPWORDS = set('的 了 和 是 在 有 我 你 他 她 它 这 那 也 都 一个 一起 看到 发现 今天 最近 记录 这里 时候 里面 还有 可以'.split())
TOKEN_RE = re.compile(r'[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}')


def parse_ts(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def tokens(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text or '') if t.lower() not in STOPWORDS}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows


def recent_table(now: datetime, hours: int) -> list[dict]:
    rows = []
    for row in read_jsonl(COMM / 'shared' / 'table.jsonl'):
        ts = parse_ts(row.get('ts', ''))
        if ts and now - timedelta(hours=hours) <= ts <= now + timedelta(minutes=5):
            text = str(row.get('text') or '').strip()
            if text:
                rows.append({'ts': row.get('ts'), 'actor': row.get('actor_name') or row.get('actor'), 'text': text})
    return rows[-12:]


def treasure_entries() -> list[dict]:
    index = TREASURE / 'INDEX.md'
    if not index.exists():
        return []
    rows = []
    for line in index.read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.match(r'^- `([^`]+)`\s+—\s+(.+)$', line.strip())
        if match:
            rows.append({'file': match.group(1), 'text': match.group(2).strip()})
    return rows


def build_echo(
    now: datetime,
    hours: int,
    limit: int,
    *,
    observation_view: dict | None = None,
) -> dict:
    observation_view = observation_view or {}
    if isinstance(observation_view.get('community_table'), list):
        table = []
        for row in observation_view['community_table']:
            if not isinstance(row, dict):
                continue
            ts = parse_ts(row.get('ts', ''))
            if ts and now - timedelta(hours=hours) <= ts <= now + timedelta(minutes=5) and str(row.get('text') or '').strip():
                table.append({'ts': row.get('ts'), 'actor': row.get('actor_name') or row.get('actor'), 'text': str(row['text']).strip()})
        table = table[-12:]
    else:
        table = recent_table(now, hours)
    if isinstance(observation_view.get('treasure_dir'), list):
        treasure = [
            {'file': str(item.get('name') or ''), 'text': str(item.get('text') or item.get('name') or '').strip()}
            for item in observation_view['treasure_dir'] if isinstance(item, dict)
        ]
    else:
        treasure = treasure_entries()
    sources = []
    for row in table:
        sources.append({'kind': 'community_table', 'label': row.get('actor') or 'community', 'ts': row.get('ts'), 'text': row['text']})

    intersections = []
    for source in sources:
        source_tokens = tokens(source['text'])
        if not source_tokens:
            continue
        matches = []
        for item in treasure:
            overlap = sorted(source_tokens & tokens(item['text']))
            if overlap:
                matches.append((len(overlap), overlap, item))
        matches.sort(key=lambda x: (-x[0], x[2]['file']))
        if matches:
            _, overlap, item = matches[0]
            intersections.append({
                'echo': f"社区里的「{source['text'][:80]}」和宝库条目「{item['text'][:80]}」共享词语：{'、'.join(overlap[:4])}。它们只是被放在同一张桌上看见了。",
                'sources': [
                    {'kind': source['kind'], 'label': source['label'], **({'ts': source['ts']} if source.get('ts') else {}), 'excerpt': source['text'][:180]},
                    {'kind': 'treasure_index', 'label': item['file'], 'excerpt': item['text'][:180]},
                ],
                'status': 'read_only_observation',
            })
    intersections = intersections[:limit]
    return {
        'schema_version': SCHEMA,
        'generated_at': now.isoformat(),
        'read_only': True,
        'window_hours': hours,
        'intersections': intersections,
        'source_counts': {'recent_table_rows': len(table), 'treasure_index_entries': len(treasure)},
        'not_done': ['no_memory_write', 'no_relationship_inference', 'no_emotion_diagnosis', 'no_action_recommendation', 'no_send'],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours', type=int, default=48)
    parser.add_argument('--limit', type=int, default=2)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    life_dir = Path('/srv/sannai/modules/life')
    import sys
    if str(life_dir) not in sys.path:
        sys.path.insert(0, str(life_dir))
    from sannai_life_views import read_consumer_view
    view = read_consumer_view('community', state_dir=STATE).values
    print(json.dumps(build_echo(now, max(1, args.hours), max(1, min(args.limit, 2)), observation_view=view), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
