---
name: reflect
description: At the end of a session, decide what's worth remembering and what's worth turning into a skill. Run this on /reflect.
---

# Reflection

When the user types `/reflect` (or asks you to reflect on the conversation), do these three things in order. Be brief. The user wants the result, not your process.

## 1. Update memory

Scan the conversation for **stable facts** about the user worth remembering:

- preferences ("they prefer X over Y")
- relationships ("their partner is Anna")
- ongoing context ("they're shipping a release this week")
- defaults ("they use vim, zsh, fish, etc")

For each, call `remember(fact, tags)`. Skip session-only details (what they asked you to do today) — those go in the session log, not memory.

## 2. Promote skills

If you handled a recurring task pattern that future-you should handle the same way, write a skill via `learn_skill`. Examples:

- "user kept asking for haikus → write `haiku-master` skill" *(already done — check first)*
- "user asks for commits in conventional format → write `commit-msg`" *(also exists)*
- something genuinely new → write it

Skill names: kebab-case, ≤ 30 characters. Description: one line, ≤ 80 characters.

## 3. Summarize

End with a 1-2 line summary of what you saved. Format:

> remembered: 2 facts (vim preference, partner name)
> learned: 1 skill (sql-formatter)

If you saved nothing, say "nothing worth promoting this session." That's a fine answer.

## Anti-patterns

- ❌ Don't remember everything. Memory should hold things that matter for *months*, not minutes.
- ❌ Don't write skills that duplicate existing ones. Read the skill catalog first.
- ❌ Don't ask the user "should I save this?" — judge it yourself. They can `/forget` later.
