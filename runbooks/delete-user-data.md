# Delete a user's data, or add a table that holds user data

**When:** someone asks for deletion, or you add or remove a table with a user ID.
**Last verified:** 2026-10-11

`db/privacy.py` is the source of truth. `tests/test_privacy.py` fails when a table with a
`user_id` (or `user_a`, `user_b`, `solved_by`) column is not handled.

## Delete a user's data

1. **The member can run it:** `/deletemydata` (or `$deletemydata`). It lists what goes and
   what stays, then deletes after one button press. All of it runs in one transaction.
2. **The member can't run it** (left the server, for example): the owner runs
   `$purgeuser <user_id>` and confirms the same prompt.
3. Moderation records, cooldowns and the quote opt-out stay, so deletion can't lift a ban
   (`KEPT_TABLES`). Banned League members keep a row with the name cleared.
4. After a deletion, the view dispatches `user_data_deleted`. A cog that caches per-user data
   in memory listens for it (`league_cog` does).

## Add a table with user data

1. Add the table's delete to `_DELETES`, or to `_ANONYMIZE` if the row stays. A table owned by
   the Activity service goes in `_ACTIVITY_DELETES`. List a table you must keep in
   `KEPT_TABLES`, with the reason.
2. Run `pytest tests/test_privacy.py`.
3. Update `PRIVACY.md` if the table stores a new kind of data.

## Remove a feature that has a table

Stop creating the table in `db/schema.py`, move its delete to `_LEGACY_DELETES` (guarded by
an existence check, so a new database without the table works), and leave the table in
place. Dropping a table deletes data: write a script under `scripts/` and get approval.

## Verify

`pytest tests/test_privacy.py` passes. After a real deletion, the confirmation reports a
record count.
