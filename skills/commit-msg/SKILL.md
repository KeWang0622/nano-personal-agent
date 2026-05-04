---
name: commit-msg
description: Write a Conventional Commit message from a description of changes. Lead with WHY, not WHAT.
---

# Commit Message Writer

When the user asks for a commit message, write a Conventional Commit.

## Format

```
<type>(<scope>): <subject>

<body — only if needed>
```

`<type>` is one of: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`, `build`, `ci`, `style`, `revert`.

## Subject line rules

- ≤ 70 characters.
- Imperative mood (`add`, `fix`, `rename` — not `added`, `fixes`, `renaming`).
- No trailing period.
- Lowercase first word after the colon.
- Lead with the WHY when it's non-obvious. *"fix(auth): clear session on tab close to prevent stale tokens"* beats *"fix(auth): update logout handler"*.

## When to add a body

Add a body only if the subject can't carry the whole story. The body explains:

- *why* (the user-visible problem this solves)
- *what changed* in shape (not a line-by-line diff — that's what `git diff` is for)
- *anything subtle* a future reader needs to understand the change

Wrap body lines at 72 chars. One blank line between subject and body.

## Anti-patterns

- ❌ `update code` — say what and why
- ❌ `fix bug` — say which bug
- ❌ `WIP` — squash before committing
- ❌ `refactor: cleanup` — describe the cleanup

## When the user only describes the change

Ask zero questions. Make a confident first attempt and offer to revise. Most users would rather edit your guess than answer your interview.
