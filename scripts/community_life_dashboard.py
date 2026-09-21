#!/usr/bin/env python3
"""Read-only community life dashboard snapshot for Sannai.

It projects existing community, state, and treasure data without writing
identity, approving memory, sending messages, or mutating cron state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/root/.hermes/profiles/sannai')
COMM = ROOT / 'memory-os' / 'community'
STATE = Path('/srv/sannai/state/sannai')
TREASURE = Path('/srv/sannai/data/treasure/小宝贝的宝库')


def jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding='utf-8', errors='replace').splitlines() if line.strip())


def is_current_state_entry(path: Path) -> bool:
    name = path.name.lower()
    return not (
        name.startswith('.')
        or 'backup' in name
        or '.bak' in name
        or 'archive' in name
        or name.endswith('~')
    )


def build_dashboard(observation_view: dict | None = None) -> dict:
    if observation_view is not None:
        shared = observation_view.get('community_table', [])
        state = observation_view.get('state')
        treasure = observation_view.get('treasure_dir', [])
        return {
            'schema_version': 'sannai.community_life_snapshot.v1',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'read_only': True,
            'paths': {},
            'roster_records': 0,
            'table_records': len(shared) if isinstance(shared, list) else 0,
            'shared_memory_files': [],
            'state_present': isinstance(state, dict),
            'state_keys': sorted(state) if isinstance(state, dict) else [],
            'treasure_index_present': bool(treasure),
        }
    shared = COMM / 'shared'
    state_files = sorted(
        p.name for p in STATE.iterdir()
        if is_current_state_entry(p)
    ) if STATE.exists() else []
    out = {
        'schema_version': 'sannai.community_life_snapshot.v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'read_only': True,
        'paths': {'community': str(COMM), 'state': str(STATE), 'treasure': str(TREASURE)},
        'roster_records': jsonl_count(COMM / 'roster.jsonl'),
        'table_records': jsonl_count(shared / 'table.jsonl'),
        'shared_memory_files': sorted(p.name for p in shared.glob('*.jsonl')) if shared.exists() else [],
        'state_files_present': state_files,
        'treasure_index_present': (TREASURE / 'INDEX.md').is_file(),
    }
    return out


def main() -> None:
    import sys
    life_dir = Path('/srv/sannai/modules/life')
    if str(life_dir) not in sys.path:
        sys.path.insert(0, str(life_dir))
    from sannai_life_views import read_consumer_view
    view = read_consumer_view('community', state_dir=STATE).values
    print(json.dumps(build_dashboard(view), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
