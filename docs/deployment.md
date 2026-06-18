# Deployment & Configuration

The bot runs on **Railway**, containerized via the repo's `Dockerfile`.
PostgreSQL is a Railway add-on reachable via `DATABASE_URL`.

## Required environment variables

| Name | Purpose |
|---|---|
| `BOT_TOKEN` | Discord bot token. |
| `DATABASE_URL` | Postgres connection string (asyncpg-compatible). |

## Optional / defaulted environment variables

Defaults come from `config.py` (`load_settings`) or from a cog's own
`config.py` (`get_int_env`, `get_str_env`, etc.).

| Name | Default | Purpose |
|---|---|---|
| `PREFIX` | `$` | Command prefix. |
| `BOT_PLAYGROUND_GUILD_ID` | baked-in dev guild | Used for bot presence & error-channel resolution. |
| `ERROR_CHANNEL_ID` | baked-in | Where the error-handler posts tracebacks. |
| `ONLINE_CHANNEL_ID` | baked-in | Where the boot "I'm online" message goes. |
| `LEAGUE_GUILD_ID` | baked-in | The guild where the Language League runs. |
| `BOT_OWNER_ID` | baked-in | Owner ID for `@commands.is_owner()`. |
| `GEMINI_API_KEY` | unset | Optional; enables Gemini-backed features (quote generator, summary, etc.). |
| `GEMINI_ASK_MODEL` | `gemini-3.5-flash` | Gemini model id used by `$ask`. See [`./cogs/ask.md`](./cogs/ask.md). |
| `ENVIRONMENT` | `production` | Purely informational, printed on boot. |
| `WEBSITE_API_URL` | baked-in | Companion website API endpoint. |
| `CONVO_SPA_CHANNELS` | baked-in list | Conversation-starter channel allowlist. |
| `INTRO_CHANNEL_ID` | baked-in | Intro flow command channel. |
| `GENERAL_CHANNEL_ID` | baked-in | General chat channel. |
| `INTRO_WARN_CHANNEL_ID` | baked-in | Intro tracker warnings. |
| `INTRO_ALERT_CHANNEL_ID` | baked-in | Intro tracker alerts. |
| `WORLD_CUP_LOG_CHANNEL_ID` | baked-in | Channel for `/worldcup` and `/wcpredict` audit log embeds. |
| `WC_PREDICT_DEFAULT_DEADLINE_TS` | `0` | Optional fallback prediction lock time as a Unix epoch (seconds). `bot_settings.wc_predict.deadline_ts` overrides when set via `$wcpredict setdeadline`. |
| `ALMIGHTY_TRIGGER_CHANNEL_ID` | baked-in | Channel hosting the persistent Almighty submission button. |
| `ALMIGHTY_FEED_CHANNEL_ID` | baked-in | Channel where Almighty form submissions are posted. |
| `LANGEX_PANEL_CHANNEL_ID` | baked-in | Channel hosting the persistent language-exchange panel. |
| `LANGEX_FEED_CHANNEL_ID` | baked-in | Channel where language-exchange profile embeds are posted. |
| `LANGEX_AUDIT_CHANNEL_ID` | baked-in | Audit-log channel for language-exchange post/remove. |

> **Rule:** never hardcode a new guild/channel/role ID inside a cog.
> Add it to the relevant `config.py` (root or cog-local) with a
> sensible default and expose it via env var.

## Cog-specific config

Several cogs have their own `config.py` for feature-scoped constants:

- `cogs/league_cog/config.py` — `LEAGUE_GUILD_ID`, role IDs, rate
  limits, scoring constants, round configuration.
- `cogs/crossword_cog/config.py` — difficulty definitions, word-count
  range, timeout.
- `cogs/introduce_cog/config.py` — command channel, introductions
  channel, repost cooldown.
- _TODO: list the rest as they're documented._

## Boot sequence

1. `config.load_settings()` loads env vars.
2. `setup_logging()` configures the rotating-file + stdout handlers.
3. `Hablemos.__init__` creates the `Database` wrapper.
4. `setup_hook`:
    a. Connects the DB pool (with exponential backoff, up to 5
       retries).
    b. `initialize_schema` runs — idempotent `CREATE TABLE IF NOT
       EXISTS` and `ADD COLUMN IF NOT EXISTS`.
    c. Loads the "disabled cogs" set from DB.
    d. Auto-discovers every `cogs/*_cog/main.py` and loads it, skipping
       disabled ones.
5. `on_ready` posts the online message.

## Slash command syncing

Global slash commands are **not** auto-synced on boot. Run `$sync` as
the owner after a deploy that adds or changes global slash commands.
Guild-scoped slash commands (via `guild_ids=[…]`) sync instantly with
no command required.

## Logs

- Rotating file handler at `bot.log` (see `logger.py`).
- Stdout (captured by Railway's logs view).
- Per-module loggers via `logging.getLogger(__name__)`. Never
  `print()`.

### Querying Railway logs programmatically

Railway has no native log drain and only ~7 days of in-app retention.
To pull recent runtime logs into your terminal (grep/jq-friendly) use
`scripts/railway_logs.py`, which hits Railway's public GraphQL API:

```bash
export RAILWAY_TOKEN="..."            # railway.com/account/tokens (account token)

# Find your IDs (or use Cmd/Ctrl+K → Copy Service/Environment ID in the dashboard):
python scripts/railway_logs.py --discover

export RAILWAY_SERVICE_ID="..."
export RAILWAY_ENVIRONMENT_ID="..."

python scripts/railway_logs.py --limit 1000 | grep "poll failed"
python scripts/railway_logs.py --filter "@level:error" --json
```

It resolves the latest deployment automatically. The Railway GraphQL
schema shifts occasionally; if a field is rejected the script prints the
exact GraphQL error naming it, which makes the fix obvious. For
*persistent* searchable history, deploy the Locomotive sidecar to ship
logs to Axiom/BetterStack instead.

## Local development

> TODO: document the local workflow — `.env` file, running against a
> local Postgres, which commands to disable for dev, etc.
