# Conversation Starter (`convo_starter_cog`)

Posts random bilingual questions to spark conversation.

## Commands

| Command | Description | Permissions | Cooldown |
|---|---|---|---|
| `$topic [category]` / `$top` | Post a random question. Defaults to `general`; accepts a category name or number. | None | 5s/user |
| `$lst` / `$list` | List every category and its numeric alias. | None | None |

Categories are case-insensitive:

| Name | Number | Description |
|---|---:|---|
| `general` | `1` | General questions |
| `phil` | `2` | Philosophical questions |
| `would` | `3` | Would-you-rather questions |
| `other` | `4` | Random questions |
| `cursed` | `5` | Cursed deals: amazing power, terrible catch |

Examples:

```text
$topic
$topic PHIL
$topic 5
```

An unknown category returns a link to `$lst` and does not consume the user's cooldown.
Runtime messages use the bot's configured prefix rather than assuming `$`.

## Language order

`CONVO_SPA_CHANNELS` is a comma-delimited list of channel IDs configured in
root [`config.py`](../../config.py):

- In a configured channel, the Spanish question is bold and appears first.
- In every other channel, the English question is bold and appears first.

Both languages are rendered in the embed description so long questions are not
restricted by Discord's shorter embed-title limit.

## Question data

[`questions.py`](../../cogs/convo_starter_cog/questions.py) is the single source
of truth for category names, numeric aliases, descriptions, and loading rules.
Each category has a UTF-8 CSV file under `convo_starter_data/`; every row must
contain exactly two non-empty columns in `(Spanish, English)` order.

All files are loaded and validated when the cog starts. Missing files,
empty categories, malformed rows, duplicate questions, or question pairs too
long for a Discord embed prevent the extension from loading and identify the
bad file and line in the startup log. Commands use that in-memory bank and
perform no filesystem I/O.

The Google Sheet linked by `$lst` is the editable source list. After updating a
CSV export, run:

```bash
pytest -q tests/test_convo_starter.py tests/test_convo_starter_questions.py
```
