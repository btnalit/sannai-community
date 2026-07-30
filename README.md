# Sannai Community

Governed multi-partner roster and social/community feature layer, extracted
from [Hermes-Memory-OS](https://github.com/btnalit/Hermes-Memory-OS) so the
core memory/governance runtime doesn't need to carry it.

## What this is

A file-first, append-only layer for a Hermes "Sannai" profile to maintain a
roster of other agent/human "community partners", exchange bounded
shared-experience notes, leave notes on a shared "table" (窗台), track light
per-partner interests (兴趣花园), and run a cron-driven embedded partner-reply
loop.

## Layout

- `sannai_community/` — core modules (`community.py` roster contracts,
  `community_shared.py` shared-experience projection, `community_table.py`,
  `community_interest_garden.py`, `community_triggers.py`,
  `community_snapshot.py`, `community_partner_runtime.py`, `partner_create.py`).
  `jsonl_io.py` is a vendored copy of Hermes-Memory-OS's JSONL/JSON-state IO
  helpers (pure stdlib, no other internal dependency) — kept in sync manually
  if the upstream contract changes.
- `scripts/community_monitor.py` — status reporter (Track A cron health,
  reply counts, budget skips).
- `scripts/community_partner_reply.py` — self-contained cron script that
  drives one embedded partner's reply loop against a real model backend
  (currently hardcoded to an Agnes-compatible endpoint and to
  `/vol1/.hermes/profiles/sannai/memory-os`).

## Known implementation gaps (carried over as-is from extraction)

Recorded in Hermes-Memory-OS's stabilization checklist (Section BP, commit
`609bc40`) at the time of extraction, and intentionally not fixed as part of
the move — they are pre-existing behavior, not introduced by extraction:

- `community_partner_runtime.py`, `community_table.py`, and
  `community_interest_garden.py` have **zero live callers**. The actual
  production cron path (`scripts/community_partner_reply.py`) uses an
  inline-rewritten duplicate of this logic instead, which means: partner
  replies aren't rate-limited the way `community_table.write_to_table`
  enforces, the shared-write gating in `community_shared.py` is bypassed by
  the inline duplicate's direct file writes, and the inline `_extract_topics`
  keyword list has drifted from `community_interest_garden.py`'s.
- `community_snapshot.py`'s `unread_partner_replies` / `partner_reply_breakdown`
  fields are computed but have no current consumer.
- `community_table.py.write_to_table` and the inline duplicate in
  `community_partner_reply.py` both write with plain `open(path, "a")` rather
  than through the locked/gated primitives in `jsonl_io.py`.

None of this was repaired during extraction — extraction moved the code
as-is. Fixing the inline-vs-module drift is a legitimate follow-up but a
separate change from a repo split.

## Deployment

Production deployment automation (`scripts/deploy_community.py` in the old
repo, plus a CLI status subcommand and an install-time layout initializer)
was retired as part of this extraction rather than ported — it mixed
community files with core Hermes-Memory-OS files and assumed the old repo's
install layout, so porting it verbatim would have been misleading. The
already-deployed files on the `hermes-media` production host are untouched by
this extraction; there is no deploy tooling here yet. Build one when this
package actually needs independent deployment.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```
