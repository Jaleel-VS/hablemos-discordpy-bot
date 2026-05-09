# Hablemos Bot — Documentation

Living documentation for the Hablemos Spanish-learning Discord bot.
These docs live **in this repository**; keep them in sync with the code
by updating the relevant file in the **same commit** as any behavior
change. See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the rules.

## Where to start

| If you want to … | Go to |
|------------------|-------|
| Understand the overall layout | [`architecture.md`](./architecture.md) |
| Look up a user command | [`commands.md`](./commands.md) |
| Look up an owner/admin command | [`admin.md`](./admin.md) |
| Understand the database | [`database.md`](./database.md) |
| Deploy or configure the bot | [`deployment.md`](./deployment.md) |
| Dig into one cog | [`cogs/`](./cogs/) |
| Diagnose a problem | [`playbook.md`](./playbook.md) |
| Edit these docs | [`CONTRIBUTING.md`](./CONTRIBUTING.md) |

## Per-cog docs

> Only a subset is filled in so far. New entries should follow the
> template in [`cogs/_template.md`](./cogs/_template.md).

- [Language League (`league_cog`)](./cogs/league.md)
- [Crossword (`crossword_cog`)](./cogs/crossword.md)
- [Introduce (`introduce_cog`)](./cogs/introduce.md)
- _TODO: admin, ask, conjugation, conversation, convo\_starter,
  database, dictation, dictionary, error\_handler, general, hangman,
  hol, interactions, intro, practice, practice\_test,
  quote\_generator, relay, spotify, summary, tasks, tickets, vocab,
  website\_manager_

## Relationship to `AGENTS.md`

`AGENTS.md` at the repo root is the **contract for coding agents**: code
style, patterns, git rules. These docs are the **map of the system** —
what exists, where it lives, why it works the way it does. An agent
reads both.
