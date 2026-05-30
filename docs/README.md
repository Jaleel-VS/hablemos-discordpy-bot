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

- [Admin (`admin_cog`)](./cogs/admin.md)
- [Ask (`ask_cog`)](./cogs/ask.md)
- [Conjugation (`conjugation_cog`)](./cogs/conjugation.md)
- [Conversation (`conversation_cog`)](./cogs/conversation.md)
- [Conversation Starter (`convo_starter_cog`)](./cogs/convo_starter.md)
- [Crossword (`crossword_cog`)](./cogs/crossword.md)
- [Database (`database_cog`)](./cogs/database.md)
- [Dictation (`dictation_cog`)](./cogs/dictation.md)
- [Dictionary (`dictionary_cog`)](./cogs/dictionary.md)
- [Error Handler (`error_handler_cog`)](./cogs/error_handler.md)
- [General (`general_cog`)](./cogs/general.md)
- [Hangman (`hangman_cog`)](./cogs/hangman.md)
- [Higher or Lower (`hol_cog`)](./cogs/hol.md)
- [Interactions (`interactions_cog`)](./cogs/interactions.md)
- [Intro (`intro_cog`)](./cogs/intro.md)
- [Introduce (`introduce_cog`)](./cogs/introduce.md)
- [Language League (`league_cog`)](./cogs/league.md)
- [Practice (`practice_cog`)](./cogs/practice.md)
- [Practice Test (`practice_test_cog`)](./cogs/practice_test.md)
- [Quote Generator (`quote_generator_cog`)](./cogs/quote_generator.md)
- [Relay (`relay_cog`)](./cogs/relay.md)
- [Spotify (`spotify_cog`)](./cogs/spotify.md)
- [Summary (`summary_cog`)](./cogs/summary.md)
- [Tasks (`tasks_cog`)](./cogs/tasks.md)
- [Tickets (`tickets_cog`)](./cogs/tickets.md)
- [Vocab (`vocab_cog`)](./cogs/vocab.md)
- [Website Manager (`website_manager_cog`)](./cogs/website_manager.md)
- [World Cup Predictions (`wcpredict_cog`)](./cogs/wcpredict.md)

## Relationship to `AGENTS.md`

`AGENTS.md` at the repo root is the **contract for coding agents**: code
style, patterns, git rules. These docs are the **map of the system** —
what exists, where it lives, why it works the way it does. An agent
reads both.
