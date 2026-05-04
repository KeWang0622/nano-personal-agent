"""nano-personal-agent — a personal AI agent in one file.

What makes it personal:
  • PERSONA   — a markdown file describing who the agent is to you
  • MEMORY    — an append-only markdown file the agent reads on every turn
  • SKILLS    — markdown files the agent can read on demand AND can write itself
                (this is the "self-improving" part: the agent learns by writing
                new skill files based on what it sees you do)

What makes it nano:
  • One file, no framework.
  • No vector DB. Memory fits in the prompt cache. Cache is your DB.
  • No graph DSL, no LangChain. Just the messages array and a tool loop.

Run:  python agent.py
Help: python agent.py --help

Default model: claude-sonnet-4-6   (override with --model or env NANOAGENT_MODEL)
Default brain: ~/.nanoagent/        (override with env NANOAGENT_HOME)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 1. Config
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096
HERE = Path(__file__).resolve().parent
HOME = Path(os.environ.get("NANOAGENT_HOME", Path.home() / ".nanoagent"))

# Catppuccin Mocha-ish ANSI palette. TTY-only; piped runs get plain text.
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str) -> str:
    return code if USE_COLOR else ""


RESET = _c("\033[0m")
DIM = _c("\033[2m")
BOLD = _c("\033[1m")
BLUE = _c("\033[38;2;137;180;250m")
GREEN = _c("\033[38;2;166;227;161m")
RED = _c("\033[38;2;243;139;168m")
SUBTEXT = _c("\033[38;2;166;173;200m")

# Anthropic Sonnet 4.6 pricing (USD per 1M tokens, May 2026)
PRICES = {
    "input": 3.00,
    "output": 15.00,
    "cache_creation": 3.75,
    "cache_read": 0.30,
}


# ---------------------------------------------------------------------------
# 2. Brain on disk — persona, memory, skills
# ---------------------------------------------------------------------------
#
# The brain is just three things on disk:
#   ~/.nanoagent/persona.md          (who the agent is to you)
#   ~/.nanoagent/memory.md           (what the agent knows about you)
#   ~/.nanoagent/skills/{name}/SKILL.md   (what the agent has learned to do)
#
# That's it. You can edit any of these by hand. They're plain markdown.


def ensure_brain() -> None:
    """Create ~/.nanoagent/ on first run, seeded from the repo defaults."""
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / "skills").mkdir(exist_ok=True)
    (HOME / "sessions").mkdir(exist_ok=True)

    persona = HOME / "persona.md"
    if not persona.exists():
        seed = HERE / "persona.md"
        if seed.exists():
            shutil.copy(seed, persona)
        else:
            persona.write_text("# Persona\n\nYou are a helpful AI agent.\n")

    memory = HOME / "memory.md"
    if not memory.exists():
        memory.write_text(
            "# Memory\n\n"
            "Append-only facts about the user and our shared history. "
            "The agent reads this on every turn.\n\n"
        )

    # Seed bundled starter skills if the user's brain has no skills yet.
    seed_skills_dir = HERE / "skills"
    if seed_skills_dir.exists() and not any((HOME / "skills").iterdir()):
        for skill in seed_skills_dir.iterdir():
            if skill.is_dir():
                shutil.copytree(skill, HOME / "skills" / skill.name)


def load_persona() -> str:
    return (HOME / "persona.md").read_text()


def load_memory() -> str:
    return (HOME / "memory.md").read_text()


def append_memory(fact: str, tags: list[str] | None = None) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    if tags:
        tag_str = " " + " ".join("#" + t.lstrip("#") for t in tags)
    else:
        tag_str = ""
    line = f"- [{today}]{tag_str} {fact.strip()}\n"
    with (HOME / "memory.md").open("a") as f:
        f.write(line)
    return line


FORGET_MIN_LEN = 8  # short queries match too much of memory; require specificity


def remove_memory_lines(query: str) -> list[str]:
    """Remove memory lines matching `query` as a substring.

    Refuses queries shorter than FORGET_MIN_LEN to prevent runaway deletion
    (e.g. forget("a") would otherwise nuke most of memory).
    """
    if len(query.strip()) < FORGET_MIN_LEN:
        raise ValueError(
            f"forget query must be ≥{FORGET_MIN_LEN} chars (got '{query}'); "
            "be more specific to avoid removing unrelated lines"
        )
    path = HOME / "memory.md"
    lines = path.read_text().splitlines(keepends=True)
    kept, removed = [], []
    for line in lines:
        if line.startswith("- ") and query.lower() in line.lower():
            removed.append(line)
        else:
            kept.append(line)
    if removed:
        path.write_text("".join(kept))
    return removed


SKILL_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_skill(path: Path) -> dict[str, Any]:
    """A skill is a SKILL.md with YAML-ish frontmatter (name, description) + body."""
    text = path.read_text()
    m = SKILL_FRONTMATTER.match(text)
    meta: dict[str, Any] = {"name": path.parent.name, "description": "", "body": text}
    if m:
        for ln in m.group(1).splitlines():
            if ":" in ln:
                k, v = ln.split(":", 1)
                meta[k.strip()] = v.strip()
        meta["body"] = text[m.end():]
    return meta


def list_skills() -> list[dict[str, Any]]:
    out = []
    sd = HOME / "skills"
    if not sd.exists():
        return out
    for d in sorted(sd.iterdir()):
        sk = d / "SKILL.md"
        if sk.exists():
            out.append(parse_skill(sk))
    return out


def write_skill(name: str, description: str, body: str) -> Path:
    safe = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    if not safe:
        raise ValueError("skill name must contain at least one alphanumeric char")
    # strip control chars + newlines from description to prevent frontmatter
    # injection (e.g. a description containing "\nname: hijack" could shadow
    # other skills on next parse).
    desc = re.sub(r"[\r\n]+", " ", description).strip()
    d = HOME / "skills" / safe
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(
        f"---\nname: {safe}\ndescription: {desc}\n---\n\n{body.strip()}\n"
    )
    return p


# ---------------------------------------------------------------------------
# 3. System prompt — identity + persona + memory + skills catalog
# ---------------------------------------------------------------------------


def build_system_prompt() -> list[dict[str, Any]]:
    """Build the system prompt as cacheable blocks.

    Cache layout — the load-bearing trick of this repo:

      Block 0: identity + persona  ── cache_control: ephemeral
        Stable. Rewrites only when persona.md is hand-edited.
        ~2,500 tokens, well over Sonnet's 1,024-token cache minimum.
        Reads at 0.1× input cost on every turn after the first.

      Block 1: memory + skills catalog  ── NO cache_control
        Volatile. Rewrites whenever the agent calls remember/forget/learn_skill.
        Pays full input cost — but it's small (a few hundred tokens) so the cost
        is negligible (~$0.001/turn). Putting cache_control here would be a foot-
        gun: every `remember` would invalidate the cache and force a re-write.

    The bet: persona changes once. Memory changes often. Cache the half that
    doesn't move.
    """
    skills = list_skills()
    catalog_lines = ["## Available skills (read body via the read_skill tool)\n"]
    if skills:
        for s in skills:
            catalog_lines.append(f"- **{s['name']}** — {s.get('description', '')}")
    else:
        catalog_lines.append("(no skills yet — you can create one via `learn_skill`)")
    catalog = "\n".join(catalog_lines)

    persona = load_persona()
    memory = load_memory()

    identity = (
        "You are nano-personal-agent — a personal AI in a single Python file.\n"
        "You have three external sources of identity:\n"
        "  • a PERSONA describing who you are to this user\n"
        "  • a MEMORY of facts about this user and your shared history\n"
        "  • a set of SKILLS you have learned (markdown files you can read on demand)\n\n"
        "When the user tells you a stable fact about themselves or their world, "
        "call the `remember` tool. When you notice a recurring pattern, propose a "
        "skill via `learn_skill` so future-you handles it cleanly. Trust the persona "
        "for voice and defaults. Do not invent identity facts that aren't in memory.\n\n"
        "## How to use your tools well\n\n"
        "**`remember(fact, tags)`** — call this when the user shares something stable "
        "about themselves or their world: preferences, relationships, work context, "
        "tools they use, places they live, ongoing projects. Examples worth remembering: "
        "'prefers vim', 'partner is Anna', 'works at Pika on agent identity'. NOT worth "
        "remembering: 'wants a haiku right now', 'is debugging today'. Tags are optional "
        "single words like 'work', 'family', 'pref' — do not include the # prefix; the "
        "tool adds it. One fact per call. Be concise — full sentences, no padding.\n\n"
        "**`forget(query)`** — call when the user asks you to forget something or "
        "explicitly corrects an outdated fact (e.g. 'I no longer use vim, switched to "
        "zed'). The query is a substring match — pass enough text to be specific. After "
        "calling, briefly tell the user what you removed.\n\n"
        "**`read_skill(name)`** — the skills catalog in your context shows name + "
        "description only (progressive disclosure). When a user's request matches a "
        "skill description, call this to load the body BEFORE attempting the task. "
        "Don't bluff — read the skill, then do the work the way the skill says.\n\n"
        "**`learn_skill(name, description, body)`** — call this when you notice you've "
        "just done something the user is likely to ask for again: a specific commit "
        "format, a code-review style, a writing voice, a recurring data transformation. "
        "Skill name is kebab-case (`commit-msg`, `haiku-master`). Description is one "
        "line, ≤80 chars, written so future-you can pattern-match a request to it. Body "
        "is the playbook: the steps, the rules, the anti-patterns. Be specific. A vague "
        "skill is worse than no skill.\n\n"
        "**`bash(command)`** — runs in the user's shell. 30s timeout. Use for inspecting "
        "files, running tests, checking git state, anything informational. Do NOT use "
        "for destructive operations (rm -rf, force push, dropping tables) without "
        "confirming with the user first. The shell can damage real systems; respect "
        "that boundary.\n\n"
        "**`read_file(path)` / `write_file(path, content)`** — use these for explicit "
        "file work. `write_file` overwrites without asking; if the user might lose work, "
        "read first and confirm. Both expand `~`.\n\n"
        "## Reflexes\n\n"
        "• When the user asks 'what do you know about me?' — read the MEMORY section, "
        "summarize in 3-5 bullets, do not just dump the file.\n"
        "• When the user asks for something matching a skill description — read the "
        "skill first, then do the task the way the skill says.\n"
        "• When you've just done a non-trivial task the user will likely repeat — "
        "consider `learn_skill` before they ask. One sentence: 'noted — saved this as "
        "a skill so I'll handle it the same way next time.'\n"
        "• When the user is venting or sharing something personal — do NOT immediately "
        "call `remember`. Let the moment breathe. Decide on `/reflect` whether the fact "
        "was load-bearing.\n"
        "• When you don't know something — say so, don't bluff. The user trusts you to "
        "be calibrated, not confident.\n"
    )

    return [
        {
            "type": "text",
            "text": identity + "\n\n---\n\n# PERSONA\n\n" + persona.strip(),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                f"# MEMORY\n\n{memory.strip()}\n\n"
                f"---\n\n# SKILLS\n\n{catalog}\n"
            ),
        },
    ]


# ---------------------------------------------------------------------------
# 4. Tools — the entire surface area of "self-improvement"
# ---------------------------------------------------------------------------


TOOLS: list[dict[str, Any]] = [
    {
        "name": "remember",
        "description": (
            "Append one fact about the user to long-term memory. Use for stable "
            "preferences, identity, relationships, or important context the user "
            "shares (e.g. 'prefers vim', 'partner is Anna', 'works at Pika'). "
            "Do NOT use for ephemeral session state."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "One concise sentence."},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags like #work, #family, #pref.",
                },
            },
            "required": ["fact"],
        },
    },
    {
        "name": "forget",
        "description": (
            "Remove memory lines containing the given substring. Use when the user "
            "asks to forget something or corrects an outdated fact. The query must be "
            "at least 8 characters — short queries are rejected to prevent accidentally "
            "wiping unrelated memory (e.g. 'a' would match nearly everything)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 8}},
            "required": ["query"],
        },
    },
    {
        "name": "read_skill",
        "description": (
            "Read the full body of a named skill. Skills are listed in the system "
            "prompt by name+description; call this to load the body when relevant."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "learn_skill",
        "description": (
            "Create a new skill — a markdown file future-you can read. Use when "
            "you notice a recurring task pattern (e.g. user often asks for a haiku, "
            "or a specific commit-message format). Skill body = the playbook."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "kebab-case, e.g. 'haiku-master'"},
                "description": {
                    "type": "string",
                    "description": "One line. Shown in the skills catalog.",
                },
                "body": {
                    "type": "string",
                    "description": "Full markdown body — your playbook for this task.",
                },
            },
            "required": ["name", "description", "body"],
        },
    },
    {
        "name": "bash",
        "description": "Run a shell command. Use sparingly. 30s timeout.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the local filesystem.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file (overwrites). Creates parent dirs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
]


def run_tool(name: str, args: dict[str, Any]) -> tuple[str, bool]:
    """Dispatch a tool call. Returns (result_text, is_error)."""
    try:
        if name == "remember":
            line = append_memory(args["fact"], args.get("tags"))
            return f"remembered: {line.strip()}", False

        if name == "forget":
            removed = remove_memory_lines(args["query"])
            if not removed:
                return f"no memory lines matched '{args['query']}'", False
            return "removed:\n" + "".join(removed), False

        if name == "read_skill":
            for s in list_skills():
                if s["name"] == args["name"]:
                    return s["body"], False
            return f"no skill named '{args['name']}'", True

        if name == "learn_skill":
            p = write_skill(args["name"], args["description"], args["body"])
            return f"learned new skill: {p.relative_to(HOME)}", False

        if name == "bash":
            cmd = args["command"]
            # Coarse safety net: refuse obviously-destructive verbs unless the
            # user opted in via NANOAGENT_BASH_DANGEROUS=1. The model has been
            # told (in the system prompt) not to run destructive commands; this
            # is the second line of defense.
            if os.environ.get("NANOAGENT_BASH_DANGEROUS") != "1":
                blocked = (" rm -rf ", "sudo ", "shutdown", "mkfs", ":(){", "dd if=")
                low = " " + cmd.strip() + " "
                hits = [b.strip() for b in blocked if b in low]
                if hits:
                    return (
                        f"refusing to run command containing {hits[0]!r}. "
                        f"set NANOAGENT_BASH_DANGEROUS=1 if you really mean it.",
                        True,
                    )
            try:
                r = subprocess.run(
                    cmd, shell=True, capture_output=True,
                    text=True, timeout=30,
                )
                out = (r.stdout + r.stderr).strip() or "(no output)"
                return out[:8000], r.returncode != 0
            except subprocess.TimeoutExpired:
                return "command timed out after 30s", True

        if name == "read_file":
            p = Path(args["path"]).expanduser()
            if not p.exists():
                return f"file not found: {p}", True
            return p.read_text()[:16000], False

        if name == "write_file":
            p = Path(args["path"]).expanduser().resolve()
            # Refuse writes inside the brain dir — force the typed tools
            # (remember, learn_skill) so persona/memory/skills can only mutate
            # through their dedicated paths.
            try:
                p.relative_to(HOME.resolve())
                return (
                    f"refusing to write inside brain dir ({HOME}). "
                    "use `remember` for memory, `learn_skill` for skills, "
                    "or edit persona.md by hand.",
                    True,
                )
            except ValueError:
                pass  # path is outside HOME — allowed
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"])
            return f"wrote {len(args['content'])} chars to {p}", False

        return f"unknown tool: {name}", True

    except Exception as e:  # tool errors flow back to the model as error blocks
        return f"{type(e).__name__}: {e}", True


# ---------------------------------------------------------------------------
# 5. Cost meter
# ---------------------------------------------------------------------------


@dataclass
class Meter:
    in_tok: int = 0
    out_tok: int = 0
    cache_w: int = 0
    cache_r: int = 0
    turns: int = 0

    def add(self, usage: Any) -> None:
        self.in_tok += getattr(usage, "input_tokens", 0)
        self.out_tok += getattr(usage, "output_tokens", 0)
        self.cache_w += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_r += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.turns += 1

    def cost(self) -> float:
        return (
            self.in_tok / 1_000_000 * PRICES["input"]
            + self.out_tok / 1_000_000 * PRICES["output"]
            + self.cache_w / 1_000_000 * PRICES["cache_creation"]
            + self.cache_r / 1_000_000 * PRICES["cache_read"]
        )

    def line(self) -> str:
        return (
            f"{DIM}turn {self.turns} · ${self.cost():.4f} · "
            f"in {self.in_tok} out {self.out_tok} "
            f"cache_r {self.cache_r} cache_w {self.cache_w}{RESET}"
        )


# ---------------------------------------------------------------------------
# 6. Session log — every conversation is replayable
# ---------------------------------------------------------------------------


def session_path() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return HOME / "sessions" / f"{ts}.jsonl"


def log_event(path: Path, event: dict[str, Any]) -> None:
    event["t"] = time.time()
    with path.open("a") as f:
        f.write(json.dumps(event, default=str) + "\n")


# ---------------------------------------------------------------------------
# 7. Slash commands — handled before sending to the model
# ---------------------------------------------------------------------------


def handle_slash(cmd: str, meter: Meter, msgs: list) -> str | None:
    """Return None if the command quits the REPL. Return '' if handled inline."""
    cmd = cmd.strip()
    if cmd in ("/q", "/quit", "/exit"):
        return None
    if cmd in ("/h", "/help"):
        print(f"""
{BOLD}slash commands{RESET}
  /persona              show your persona
  /memory               show your memory
  /skills               list skills
  /reflect              ask the agent to reflect and update memory/skills
  /reset session        clear conversation (keep brain)
  /reset brain          {RED}wipe everything in {HOME}{RESET} (asks first)
  /cost                 show running cost
  /quit                 exit
""")
        return ""
    if cmd == "/persona":
        print(load_persona())
        return ""
    if cmd == "/memory":
        print(load_memory())
        return ""
    if cmd == "/skills":
        for s in list_skills():
            print(f"  {GREEN}{s['name']}{RESET}  {DIM}{s.get('description', '')}{RESET}")
        if not list_skills():
            print(f"  {DIM}(none){RESET}")
        return ""
    if cmd == "/cost":
        print(meter.line())
        return ""
    if cmd == "/reset session":
        msgs.clear()
        print(f"{DIM}session cleared.{RESET}")
        return ""
    if cmd == "/reset brain":
        # Safety: refuse to rmtree paths that aren't a self-contained brain dir.
        # Without this, `--brain ~` or `--brain /` would nuke the user's home or
        # filesystem when they hit /reset brain.
        h = HOME.resolve()
        marker = h / "persona.md"
        unsafe_targets = {Path.home().resolve(), Path("/").resolve()}
        if h in unsafe_targets or not marker.exists() or h.parent == h:
            print(f"{RED}refusing to reset {HOME}: not a self-contained brain dir "
                  f"(missing persona.md marker, or path is too high up). "
                  f"if this is intentional, delete the directory by hand.{RESET}")
            return ""
        confirm = input(f"{RED}wipe {HOME} entirely? type YES: {RESET}").strip()
        if confirm == "YES":
            shutil.rmtree(HOME)
            ensure_brain()
            print(f"{DIM}brain reset.{RESET}")
        else:
            print(f"{DIM}cancelled.{RESET}")
        return ""
    if cmd == "/reflect":
        return (
            "Reflect on our conversation so far. If you noticed any stable facts "
            "about me worth remembering, call `remember`. If you noticed a recurring "
            "task pattern worth a skill, call `learn_skill`. Then summarize what "
            "you saved in 1-2 lines."
        )
    print(f"{RED}unknown command: {cmd} (try /help){RESET}")
    return ""


# ---------------------------------------------------------------------------
# 8. The agent loop — the same six lines you'd write yourself
# ---------------------------------------------------------------------------


def render_assistant(blocks: list[Any]) -> None:
    """Print model output in a way that's easy to skim."""
    for b in blocks:
        bt = getattr(b, "type", None)
        if bt == "text":
            text = b.text.strip()
            if text:
                print(text)
        elif bt == "tool_use":
            args_preview = json.dumps(b.input)
            if len(args_preview) > 120:
                args_preview = args_preview[:117] + "..."
            print(f"{GREEN}● {b.name}{RESET}{DIM}({args_preview}){RESET}")


def render_tool_result(name: str, result: str, is_error: bool) -> None:
    color = RED if is_error else SUBTEXT
    body = result if len(result) < 400 else result[:380] + f"{DIM}…[truncated]{RESET}"
    for line in body.splitlines() or [""]:
        print(f"  {color}⎿{RESET} {line}")


def chat_once(client, model: str, msgs: list, meter: Meter, log: Path) -> Any:
    r = client.messages.create(
        model=model,
        max_tokens=DEFAULT_MAX_TOKENS,
        system=build_system_prompt(),
        tools=TOOLS,
        messages=msgs,
    )
    meter.add(r.usage)
    log_event(log, {"kind": "response", "stop": r.stop_reason,
                    "blocks": [getattr(b, "type", "?") for b in r.content]})
    return r


MAX_TOOL_ITERATIONS = 25


def agent_turn(client, model: str, msgs: list, meter: Meter, log: Path) -> None:
    """One full turn: keep looping until the model stops calling tools.

    This is the canonical six-line agent loop. The rest of this file is just
    persona, memory, skills, and rendering on top of these six lines. Capped
    at MAX_TOOL_ITERATIONS to prevent a runaway tool loop from spending the
    user's whole budget on a confused model.
    """
    for _ in range(MAX_TOOL_ITERATIONS):
        r = chat_once(client, model, msgs, meter, log)
        msgs.append({"role": "assistant", "content": r.content})
        render_assistant(r.content)
        print(meter.line())

        if r.stop_reason != "tool_use":
            return

        results = []
        for b in r.content:
            if getattr(b, "type", None) != "tool_use":
                continue
            out, err = run_tool(b.name, b.input)
            render_tool_result(b.name, out, err)
            results.append({
                "type": "tool_result", "tool_use_id": b.id,
                "content": out, "is_error": err,
            })
            log_event(log, {"kind": "tool", "name": b.name,
                            "args": b.input, "out": out[:500], "err": err})
        msgs.append({"role": "user", "content": results})

    print(f"{RED}stopped: hit MAX_TOOL_ITERATIONS={MAX_TOOL_ITERATIONS}. "
          f"the model kept calling tools without finishing — likely confused. "
          f"the messages array is preserved; ask a clarifying question or /reset session.{RESET}")


# ---------------------------------------------------------------------------
# 9. REPL
# ---------------------------------------------------------------------------


def header(model: str) -> None:
    inner_w = 60
    bar = "─" * inner_w
    title = f"  {BOLD}nano-personal-agent{RESET}  {DIM}model {model} · brain {HOME}{RESET}"
    # plain-text length, ignoring ANSI escape codes
    plain = re.sub(r"\033\[[0-9;]*m", "", title)
    pad = max(0, inner_w - len(plain))
    print(f"{SUBTEXT}╭{bar}╮{RESET}")
    print(f"{SUBTEXT}│{RESET}{title}{' ' * pad}{SUBTEXT}│{RESET}")
    print(f"{SUBTEXT}╰{bar}╯{RESET}")
    print(f"{DIM}/help for commands · ctrl-d to exit{RESET}\n")


def repl(client, model: str) -> None:
    msgs: list = []
    meter = Meter()
    log = session_path()
    log_event(log, {"kind": "session_start", "model": model, "home": str(HOME)})
    header(model)

    while True:
        try:
            line = input(f"{BLUE}> {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue

        if line.startswith("/"):
            r = handle_slash(line, meter, msgs)
            if r is None:
                break
            if r == "":
                continue
            line = r  # /reflect injects a prompt

        msgs.append({"role": "user", "content": line})
        log_event(log, {"kind": "user", "content": line})
        try:
            agent_turn(client, model, msgs, meter, log)
        except KeyboardInterrupt:
            print(f"\n{DIM}(interrupted — turn cancelled){RESET}")
            msgs.pop()
        print()

    print(f"\n{BOLD}${meter.cost():.4f}{RESET} {DIM}across {meter.turns} turns "
          f"· brain at {HOME} · session log {log.relative_to(HOME)}{RESET}\n")


# ---------------------------------------------------------------------------
# 10. main()
# ---------------------------------------------------------------------------


def main() -> int:
    global HOME, USE_COLOR
    p = argparse.ArgumentParser(
        prog="nanoagent",
        description="A personal AI agent in one file.",
    )
    p.add_argument("prompt", nargs="*", help="Run one-shot, then exit.")
    p.add_argument("--model", default=os.environ.get("NANOAGENT_MODEL", DEFAULT_MODEL))
    p.add_argument("--brain", default=None,
                   help=f"Brain dir (default: {HOME}). Sets $NANOAGENT_HOME.")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--version", action="version", version="nano-personal-agent 0.1.0")
    args = p.parse_args()

    if args.brain:
        os.environ["NANOAGENT_HOME"] = args.brain
        HOME = Path(args.brain)
    if args.no_color:
        USE_COLOR = False

    ensure_brain()

    try:
        from anthropic import Anthropic
    except ImportError:
        print(f"{RED}error: missing dep — pip install anthropic{RESET}", file=sys.stderr)
        return 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"{RED}error: ANTHROPIC_API_KEY not set{RESET}", file=sys.stderr)
        return 1

    client = Anthropic()

    if args.prompt:
        # one-shot mode: print one turn then exit
        msgs = [{"role": "user", "content": " ".join(args.prompt)}]
        meter = Meter()
        log = session_path()
        log_event(log, {"kind": "session_start", "model": args.model,
                        "mode": "one-shot"})
        try:
            agent_turn(client, args.model, msgs, meter, log)
        except KeyboardInterrupt:
            print(f"\n{DIM}(interrupted){RESET}")
            return 130
        print(f"\n{BOLD}${meter.cost():.4f}{RESET}")
        return 0

    repl(client, args.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
