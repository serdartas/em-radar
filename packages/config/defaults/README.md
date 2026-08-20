# Default signal pack

`default-pack.yaml` is the **source of truth** for the signals that EM Radar ships out of
the box.  Edit this file to change which signals are included in the default set, adjust
thresholds, or add new signals to the "Default signals" group.

## How seeding works

`apps/api/src/em_radar_api/startup.py` (`seed_default_signal_group`) imports this file on
every API start using the same `apply_signal_pack_import` pipeline that handles user
imports.  Seeding is **one-shot and idempotent**: it only runs when no group named
"Default signals" exists in the database.  Edits to this file therefore take effect on a
**fresh database** (delete the DB file and restart), not on an already-seeded one.

This is intentional: connector data is always rebuilt from connectors on the next sync, so
signal-pack changes can be tested by wiping the DB and restarting the API.

> **Warning — destructive operation.**  Deleting the database file also removes connection
> configurations, credentials, team definitions, cached canonical data, and report history.
> None of that state is rebuilt automatically.  Use this workflow only with a disposable
> development database; never against a configured instance you care about.

## Making changes

1. Edit `default-pack.yaml`.
2. Validate with `uv run pytest apps/api/tests/test_default_group_seeding.py`.
3. Wipe the local DB (`rm -f $EM_RADAR_DATABASE_PATH`) and restart the API to see the
   seeded result.
