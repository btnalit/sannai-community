# Sannai Community Life Dashboard

`community_life_dashboard.py` is a read-only projection of Sannai's little courtyard.

It reads the existing community roster/shared table, Sannai's `/srv/sannai/state/sannai/`
living-state directory, and the treasure chest index. It emits a stable-schema JSON
snapshot with a runtime timestamp for future local UI or daily reflection work.

Safety boundary:

- no identity or relationship writes;
- no Memory-OS approval or crystallization;
- no mailbox or Telegram sends;
- no cron/config/service mutation;
- no credentials are read.

Run:

```bash
python3 scripts/community_life_dashboard.py
```

This is intentionally a projection, not another canonical memory store.
