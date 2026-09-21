# Sannai Community Life Echo

`community_life_echo.py` is a small, read-only observation layer for the courtyard.
It looks at time-windowed community table shares and the current treasure index,
then surfaces at most two explicit lexical intersections with their sources.
It does not use the undated life snapshot as evidence, so old words cannot be
mistaken for today's echo.

It is deliberately **not**:

- a daily KPI or report;
- a relationship judgment;
- an emotion diagnosis;
- an action recommendation;
- a memory writer or crystallizer;
- a sender.

The output has `status: read_only_observation` and lists its sources. Its runtime
timestamp means the schema is stable, not the bytes. It is safe to call manually
or from a future local, opt-in reflection view; no cron was added in this change.

Run:

```bash
python3 scripts/community_life_echo.py --hours 48 --limit 2
```
