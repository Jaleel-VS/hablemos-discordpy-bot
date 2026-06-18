# Architecture

A map of the code. For conventions (style, patterns, what to avoid), see
[`../AGENTS.md`](../AGENTS.md).

## Stack

- **Python 3.12+** (`match`, inline generics, PEP 604 unions).
- **discord.py 2.x** (`discord.ext.commands.Bot`, slash commands, UI
  views, persistent views).
- **PostgreSQL via `asyncpg`** — one connection pool owned by the bot,
  accessed through the `Database` class at `self.bot.db`.
- **Railway** for hosting, `Dockerfile` for the container.
- **Ruff** for linting (`ruff.toml`).

## Top-level layout

```
hablemos.py          Bot entrypoint, subclasses discord.ext.commands.Bot
base_cog.py          BaseCog that every cog inherits from
config.py            Settings dataclass loaded from env vars
logger.py            Logging setup
ruff.toml            Ruff config
db/                  Database module (mixin-per-domain)
cogs/<feature>_cog/  One directory per feature, auto-discovered
cogs/utils/          Shared helpers (embeds, rate limiters, etc.)
scripts/             Utility scripts, ad-hoc tools
docs/                This folder
AGENTS.md            Agent contract (code style, patterns, git rules)
```

## Bot entrypoint — `hablemos.py`

- Defines `class Hablemos(Bot)`.
- `setup_hook` connects the DB (with retry), loads all auto-discovered
  extensions, and skips anything in the "disabled cogs" set stored in
  the database.
- `on_ready` resolves the configured online/error channels and posts an
  "I'm online" message.
- `on_command_completion` / `on_app_command_completion` record usage to
  `command_metrics` for the metrics rollup.

## Cog loading

Cogs are **auto-discovered** by `cogs/utils/discovery.py`: any
`cogs/*_cog/main.py` with a `setup(bot)` function is loaded at startup.
Secondary cog classes (admin splits, etc.) are explicitly added inside
that `setup()` — for example `league_cog/main.py` also loads
`LeagueAdminCog` from `admin.py`.

To disable a cog at runtime without redeploying, use the database-backed
disabled-cogs set (`$cog disable <name>`).

## Database layer — `db/`

One `Database` class composed of mixins, one mixin per domain:

```
db/
  __init__.py        Database class + DatabaseMixin base
  schema.py          initialize_schema() — all CREATE TABLE / migrations
  <domain>.py        Query methods for one domain
```

- `self.bot.db` is the shared `Database` instance.
- All queries use the connection pool via the `_fetch` / `_fetchrow` /
  `_fetchval` / `_execute` helpers on `DatabaseMixin`.
- New tables go in `schema.py`. New query methods go in the appropriate
  mixin.
- Adding a new domain: create `db/<domain>.py` with a mixin class, then
  add it to the `Database` inheritance list in `db/__init__.py`.

See [`database.md`](./database.md) for the table / mixin map.

## Gemini deep module

Gemini-using cogs go through one shared module: `cogs/utils/gemini/`.
It owns the `genai.Client` instance, model resolution, rate limiting,
retry-on-5xx, and HTTP-code-aware error mapping. Cogs never construct
`genai.Client` themselves.

```
cogs/utils/gemini/
  __init__.py        Prompt[I, O] base, Gemini class, run() dispatcher
  errors.py          GeminiError + user_message_for(APIError)
```

- `bot.gemini` is a single `Gemini` instance built in `Hablemos.setup_hook`
  (after the DB connect). If `GEMINI_API_KEY` is unset, `bot.gemini = None`
  and Gemini-using cogs skip loading.
- Each Gemini-using cog declares its prompts in `cogs/<feature>_cog/prompts.py`
  as stateless singletons. A prompt is a `Prompt[I, O]` subclass with a
  `feature` slug, generation config, and `render` / `parse` methods.
- Calls look like `await self.bot.gemini.run(MY_PROMPT, inp)`. Failures
  raise `GeminiError`; cogs catch it and surface `e.user_message`
  directly to the user.
- Model resolution: `GEMINI_<FEATURE>_MODEL` → `GEMINI_DEFAULT_MODEL` →
  `gemini-3.5-flash`. Bump a model at deploy time without touching code.
- Retry policy: 5xx errors retry up to 3 times with exponential backoff;
  4xx errors surface immediately (404 is a config bug, 401/403 won't fix
  itself, 429 carries its own user-facing "try again in a minute" message).

> **Migration status.** `ask_cog` is the first cog on the new seam.
> `summary_cog`, `practice_cog`, and `conversation_cog` still use the
> legacy `cogs/utils/gemini_base.py` (`BaseGeminiClient` + per-cog
> subclasses) and will migrate one cog per PR.

## Configuration

- All env-driven values live in `config.py`'s `Settings` dataclass.
- Individual cogs may have their own `config.py` for cog-specific IDs
  and constants (e.g. `cogs/league_cog/config.py`).
- Never read `os.getenv` directly in a cog — use the helpers from the
  central `config.py` or a cog-local `config.py` module.

See [`deployment.md`](./deployment.md) for the full env var list.

## Interaction patterns

- **Slash commands** are registered per-guild (`guild_ids=[…]`) for
  instant sync when they're tied to a specific server; global commands
  sync manually via `$sync` (never in `on_ready`).
- **Persistent views** (buttons/selects that survive restarts) have
  `timeout=None`, stable `custom_id`s, and are registered once with
  `bot.add_view(...)`. Pattern: check `bot.persistent_views` to avoid
  stacking duplicates on cog reload.
- **On-message listeners** are used for incrementally-tracked state
  (league activity, crossword answers) rather than scanning history.

## Image rendering (Pillow)

Several cogs render PNGs with Pillow (`league_cog`, `quote_generator_cog`,
`crossword_cog`, `spotify_cog`). They share a **super-sample then
downsample** scheme for crisp text on HiDPI Discord clients: render the
whole canvas at an internal multiple of the display size, then
LANCZOS-downsample on save.

- `cogs/league_cog/league_helper/leaderboard_image_pillow.py` is the
  reference implementation. It defines `SCALE`, `OUTPUT_SCALE`, and
  `S = SCALE * OUTPUT_SCALE` (= 6), renders everything at `S`, then
  resizes to `OUTPUT_SCALE` (a 2x export) before saving.

> **Gotcha — `get_font` already multiplies by `S`.** The font helper
> (`_font`, aliased as `get_font`) computes `pt = size * S` internally.
> It only produces correctly-sized text on a canvas that is itself
> rendered at `S`. If you reuse `get_font` on a 1x canvas, every font
> comes out `S` (6x) too large while coordinates stay nominal — the
> layout jumbles (giant text overflowing small pedestals/cards). This
> bit `round_end_image.py`: the fix was to scale the whole canvas + all
> layout constants/offsets by `S` and downsample by `SCALE` at the end.
> When adding or refactoring a Pillow renderer that imports these
> helpers, scale **every** coordinate, size, radius, and offset by `S`,
> or don't use `get_font` at all (load `ImageFont.truetype` directly at
> literal sizes).

## Error handling

- `cogs/error_handler_cog/` posts command failures to a configured
  error channel.
- Cogs override `BaseCog.cog_command_error` for cog-level handling.
- Interaction callbacks use a decorator (`handle_interaction_errors` in
  `league_cog/main.py` and similar) to wrap ephemeral failure embeds.
- User-facing messages never leak raw exception strings; the traceback
  is logged server-side.

## What lives where — quick reference

| Concern | Location |
|---------|----------|
| New feature | New `cogs/<feature>_cog/` directory |
| Shared utility | `cogs/utils/` |
| Database table | `db/schema.py` + matching mixin |
| Env var | `config.py` Settings + `deployment.md` |
| Admin command | Separate class in the cog's `admin.py` |
| Persistent view | `views.py` inside the cog |
