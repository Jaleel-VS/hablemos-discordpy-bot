# Contributing to the docs

These docs are considered part of the code. The rule:

> **If a commit changes behavior (commands, schema, flows, config), it
> must also update the relevant doc in the same commit.**

That one rule is what keeps "living docs" alive. Everything else is
formatting.

## When to update

| Change | Update |
|--------|--------|
| Added / removed / renamed a command | [`commands.md`](./commands.md) or [`admin.md`](./admin.md), plus the cog's file under [`cogs/`](./cogs/) |
| Changed what a command does | Same as above |
| Added a cog | New file under [`cogs/`](./cogs/) from [`cogs/_template.md`](./cogs/_template.md) + add it to [`README.md`](./README.md) |
| Added / changed a DB table | [`database.md`](./database.md) and the owning cog doc |
| Added / changed an env var | [`deployment.md`](./deployment.md) |
| Changed architecture or conventions | [`architecture.md`](./architecture.md) and maybe `AGENTS.md` |
| Added a runbook-worthy failure mode | [`playbook.md`](./playbook.md) |

## Style

- **Concrete over exhaustive.** A real example beats a paragraph of
  prose. Show the command someone would actually type.
- **No dead promises.** If a feature isn't built yet, don't document it
  as if it is. Use `> TODO` blockquotes for known gaps; the next agent
  will find them with `grep -r TODO docs/`.
- **No marketing voice.** Describe what it does, how it behaves at the
  edges, and what it assumes about the environment.
- **Link, don't duplicate.** If `database.md` explains a table, other
  docs link to the section rather than re-explaining.
- **Keep IDs out.** Channel/guild/role IDs change per deployment and
  leak context. Refer to them by name ("the league guild", "the
  introductions channel") and let `config.py` resolve them at runtime.
- **Code blocks** for commands, SQL, and file paths. Use the language
  hint (`` ```python ``, `` ```sql ``) so GitHub renders them nicely.

## File conventions

- Every file ends with a single trailing newline.
- Headings use ATX (`#`), not underlines.
- Wrap prose around 100 chars where practical — readable in GitHub and
  in-editor.
- Link to files with relative paths (`./commands.md`, `../AGENTS.md`).

## Verifying

GitHub renders these pages natively — after pushing, open
`github.com/<owner>/<repo>/blob/main/docs/README.md` and click through.
No build step.
