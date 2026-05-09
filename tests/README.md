# Tests

Unit and integration tests for the bot's logic. No real Discord gateway,
no real PostgreSQL — the harness in `tests/crossword/conftest.py` stubs
both with plain Python objects that record calls so assertions can be
made against them.

## Running

```bash
pip install -r requirements-dev.txt
pytest                       # full suite
pytest tests/crossword/      # one cog
pytest -k race               # just the concurrency tests
pytest -x --tb=short         # stop on first failure, short trace
```

`pytest.ini` enables `asyncio_mode=auto`, so `async def test_...` is
picked up without any decorator.

## Layout

```
tests/
├── __init__.py
└── crossword/
    ├── __init__.py
    ├── conftest.py                 — fakes + fixtures (FakeBot, FakeDB, etc.)
    ├── test_normalize.py           — accent/punctuation normalization
    ├── test_grid.py                — grid generation + reduction math
    ├── test_try_solve.py           — CrosswordGame.try_solve
    ├── test_use_hint.py            — CrosswordGame.use_hint
    └── test_on_message.py          — full on_message flow + concurrency
```

## What's intentionally not tested

- Anything that requires a real Discord gateway (intents, sharding,
  slash command dispatch). These live in the framework, not our code.
- Anything that requires a real PostgreSQL. Query methods in `db/`
  should be covered separately with a docker-compose fixture if you
  ever want to go there; for now the cog tests stub `self.bot.db`.
- The Pillow rendering (`renderer.py`). It's hard to assert on a PNG
  meaningfully, and font availability is environment-dependent.

## Writing new cog tests

1. Copy `tests/crossword/conftest.py` as a template for a new
   `tests/<feature>_cog/conftest.py`.
2. Strip the `FakeBot` / `FakeDB` / `FakeChannel` down to the methods
   your cog actually calls — add more only when `AttributeError`
   tells you the cog needs them.
3. Never import a mocking library. A hand-rolled dataclass with a
   `sent: list[dict]` attribute is easier to reason about than a
   `MagicMock` that auto-generates attributes on demand.
4. For races, use `asyncio.gather(...)` on plain coroutines. The
   single-threaded event loop makes interleaving deterministic
   enough to catch most real lock bugs.
