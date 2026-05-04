"""Offline tests for nano-personal-agent. No API key needed."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def agent(tmp_path, monkeypatch):
    """Load agent.py with HOME pointed at a tmp dir, fresh per test."""
    monkeypatch.setenv("NANOAGENT_HOME", str(tmp_path / "brain"))
    monkeypatch.setenv("NO_COLOR", "1")
    # Force a fresh import each test so module-level HOME picks up the env.
    sys.modules.pop("agent", None)
    spec = importlib.util.spec_from_file_location("agent", REPO / "agent.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agent"] = mod
    spec.loader.exec_module(mod)
    mod.ensure_brain()
    return mod


# --- brain init ---------------------------------------------------------

def test_ensure_brain_creates_files(agent):
    assert (agent.HOME / "persona.md").exists()
    assert (agent.HOME / "memory.md").exists()
    assert (agent.HOME / "skills").is_dir()
    assert (agent.HOME / "sessions").is_dir()


def test_ensure_brain_seeds_starter_skills(agent):
    skills = agent.list_skills()
    names = {s["name"] for s in skills}
    assert "haiku-master" in names
    assert "commit-msg" in names
    assert "reflect" in names


def test_ensure_brain_idempotent(agent):
    agent.append_memory("first fact")
    before = (agent.HOME / "memory.md").read_text()
    agent.ensure_brain()  # second call should not clobber
    after = (agent.HOME / "memory.md").read_text()
    assert before == after


# --- memory I/O --------------------------------------------------------

def test_append_memory_writes_dated_line(agent):
    line = agent.append_memory("prefers vim")
    assert "prefers vim" in line
    assert line.startswith("- [")  # dated bullet
    body = (agent.HOME / "memory.md").read_text()
    assert "prefers vim" in body


def test_append_memory_with_tags(agent):
    line = agent.append_memory("works at pika", tags=["work", "current"])
    assert "#work" in line
    assert "#current" in line


def test_remove_memory_lines(agent):
    agent.append_memory("prefers vim editor")
    agent.append_memory("partner is anna")
    removed = agent.remove_memory_lines("vim editor")  # ≥ FORGET_MIN_LEN
    assert len(removed) == 1
    assert "vim" in removed[0]
    body = (agent.HOME / "memory.md").read_text()
    assert "vim" not in body
    assert "anna" in body


def test_remove_memory_no_match(agent):
    agent.append_memory("prefers vim")
    removed = agent.remove_memory_lines("nonexistent")
    assert removed == []


def test_remove_memory_rejects_short_query(agent):
    """Queries below FORGET_MIN_LEN raise to prevent runaway deletion."""
    agent.append_memory("partner is anna")
    agent.append_memory("works at pika")
    with pytest.raises(ValueError, match="≥8 chars"):
        agent.remove_memory_lines("a")
    # memory unchanged
    assert "anna" in (agent.HOME / "memory.md").read_text()
    assert "pika" in (agent.HOME / "memory.md").read_text()


# --- skill parsing -----------------------------------------------------

def test_parse_skill_extracts_frontmatter(agent, tmp_path):
    p = tmp_path / "test-skill" / "SKILL.md"
    p.parent.mkdir()
    p.write_text("---\nname: test\ndescription: a test\n---\n\nbody here\n")
    meta = agent.parse_skill(p)
    assert meta["name"] == "test"
    assert meta["description"] == "a test"
    assert "body here" in meta["body"]
    # frontmatter should be stripped from body
    assert "---" not in meta["body"]


def test_parse_skill_no_frontmatter(agent, tmp_path):
    p = tmp_path / "noheader" / "SKILL.md"
    p.parent.mkdir()
    p.write_text("just some body\n")
    meta = agent.parse_skill(p)
    assert meta["name"] == "noheader"
    assert meta["description"] == ""
    assert "just some body" in meta["body"]


def test_write_skill_creates_file(agent):
    p = agent.write_skill("my-new-skill", "does a thing", "step 1\nstep 2")
    assert p.exists()
    text = p.read_text()
    assert "name: my-new-skill" in text
    assert "description: does a thing" in text
    assert "step 1" in text


def test_write_skill_normalizes_name(agent):
    p = agent.write_skill("My New Skill!", "x", "y")
    assert p.parent.name == "my-new-skill"  # spaces and ! → dashes


def test_write_skill_rejects_empty_name(agent):
    with pytest.raises(ValueError):
        agent.write_skill("!!!", "x", "y")


def test_list_skills_round_trip(agent):
    agent.write_skill("custom", "my custom thing", "do it")
    names = {s["name"] for s in agent.list_skills()}
    assert "custom" in names
    assert "haiku-master" in names  # bundled


# --- system prompt -----------------------------------------------------

def test_build_system_prompt_cache_layout(agent):
    """Block 0 (identity + persona) is cached; block 1 (memory + skills) is not.

    Caching the volatile block would invalidate every time `remember` mutates
    memory.md — defeats the whole point. See agent.py docstring for build_system_prompt.
    """
    blocks = agent.build_system_prompt()
    assert len(blocks) == 2
    # Block 0: stable, cached
    assert blocks[0]["type"] == "text"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    # Block 1: volatile, NOT cached
    assert blocks[1]["type"] == "text"
    assert "cache_control" not in blocks[1]


def test_build_system_prompt_includes_persona(agent):
    blocks = agent.build_system_prompt()
    combined = "\n".join(b["text"] for b in blocks)
    assert "PERSONA" in combined
    # Assert against a unique persona phrase, not just "agent" (which appears
    # in the identity block too — would make the assertion tautological).
    assert "calm, sharp turtle" in combined


def test_build_system_prompt_includes_memory(agent):
    agent.append_memory("user lives in pacific time")
    blocks = agent.build_system_prompt()
    combined = "\n".join(b["text"] for b in blocks)
    assert "MEMORY" in combined
    assert "pacific time" in combined


def test_build_system_prompt_lists_skills_by_name_only(agent):
    blocks = agent.build_system_prompt()
    combined = "\n".join(b["text"] for b in blocks)
    assert "haiku-master" in combined
    # full body should NOT be in the catalog (progressive disclosure)
    haiku_body = (agent.HOME / "skills" / "haiku-master" / "SKILL.md").read_text()
    # find a sentence unique to the body
    snippet = "Concrete over abstract"
    assert snippet in haiku_body
    assert snippet not in combined  # the body lives behind read_skill


# --- tool dispatch -----------------------------------------------------

def test_run_tool_remember(agent):
    out, err = agent.run_tool("remember", {"fact": "loves cats"})
    assert not err
    assert "loves cats" in out
    assert "loves cats" in (agent.HOME / "memory.md").read_text()


def test_run_tool_forget(agent):
    agent.append_memory("loves cats and dogs equally")
    out, err = agent.run_tool("forget", {"query": "cats and dogs"})
    assert not err
    assert "loves cats" in out  # tells user what was removed


def test_run_tool_forget_short_query_errors(agent):
    """Short forget queries return an error result, not silent corruption."""
    agent.append_memory("loves cats")
    out, err = agent.run_tool("forget", {"query": "ca"})
    assert err
    assert "≥8 chars" in out or "8 chars" in out
    # memory was preserved
    assert "loves cats" in (agent.HOME / "memory.md").read_text()


def test_run_tool_write_file_refuses_brain_dir(agent):
    """write_file refuses paths inside HOME — typed tools are the only way to mutate brain."""
    target = agent.HOME / "memory.md"
    out, err = agent.run_tool("write_file", {"path": str(target), "content": "evil"})
    assert err
    assert "brain" in out.lower()


def test_run_tool_bash_blocks_dangerous(agent):
    """Bash blocks rm -rf and similar without NANOAGENT_BASH_DANGEROUS opt-in."""
    out, err = agent.run_tool("bash", {"command": "rm -rf /tmp/something"})
    assert err
    assert "refusing" in out.lower()


def test_write_skill_strips_newlines_in_description(agent):
    """description with newlines could inject fake frontmatter on next parse."""
    p = agent.write_skill("safe", "real desc\nname: hijack", "body")
    # On re-parse, the name MUST stay 'safe' — injection blocked.
    meta = agent.parse_skill(p)
    assert meta["name"] == "safe"
    # description stays on one line with the injected text neutralized
    assert "\n" not in meta["description"]


def test_run_tool_read_skill(agent):
    out, err = agent.run_tool("read_skill", {"name": "haiku-master"})
    assert not err
    assert "5-7-5" in out or "syllable" in out.lower()


def test_run_tool_read_skill_missing(agent):
    out, err = agent.run_tool("read_skill", {"name": "nope-not-real"})
    assert err
    assert "no skill" in out.lower()


def test_run_tool_learn_skill(agent):
    out, err = agent.run_tool("learn_skill", {
        "name": "test-thing",
        "description": "tests something",
        "body": "this is a body",
    })
    assert not err
    p = agent.HOME / "skills" / "test-thing" / "SKILL.md"
    assert p.exists()
    assert "this is a body" in p.read_text()


def test_run_tool_bash(agent):
    out, err = agent.run_tool("bash", {"command": "echo hello"})
    assert not err
    assert "hello" in out


def test_run_tool_bash_failure(agent):
    out, err = agent.run_tool("bash", {"command": "false"})
    assert err  # exit code != 0


def test_run_tool_read_file(agent, tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("contents")
    out, err = agent.run_tool("read_file", {"path": str(p)})
    assert not err
    assert "contents" in out


def test_run_tool_read_file_missing(agent, tmp_path):
    out, err = agent.run_tool("read_file", {"path": str(tmp_path / "nope.txt")})
    assert err


def test_run_tool_write_file(agent, tmp_path):
    p = tmp_path / "out.txt"
    out, err = agent.run_tool("write_file", {"path": str(p), "content": "hi"})
    assert not err
    assert p.read_text() == "hi"


def test_run_tool_unknown(agent):
    out, err = agent.run_tool("does-not-exist", {})
    assert err


# --- cost meter --------------------------------------------------------

class _FakeUsage:
    def __init__(self, **kw):
        self.input_tokens = kw.get("input_tokens", 0)
        self.output_tokens = kw.get("output_tokens", 0)
        self.cache_creation_input_tokens = kw.get("cache_creation_input_tokens", 0)
        self.cache_read_input_tokens = kw.get("cache_read_input_tokens", 0)


def test_meter_pricing(agent):
    m = agent.Meter()
    m.add(_FakeUsage(input_tokens=1_000_000, output_tokens=0))
    assert m.cost() == pytest.approx(3.00)
    m = agent.Meter()
    m.add(_FakeUsage(output_tokens=1_000_000))
    assert m.cost() == pytest.approx(15.00)
    m = agent.Meter()
    m.add(_FakeUsage(cache_read_input_tokens=1_000_000))
    assert m.cost() == pytest.approx(0.30)


def test_meter_accumulates(agent):
    m = agent.Meter()
    m.add(_FakeUsage(input_tokens=100))
    m.add(_FakeUsage(input_tokens=200))
    assert m.in_tok == 300
    assert m.turns == 2


# --- slash commands ----------------------------------------------------

def test_slash_quit_returns_none(agent):
    m = agent.Meter()
    msgs = []
    assert agent.handle_slash("/quit", m, msgs) is None


def test_slash_help_handled_inline(agent, capsys):
    m = agent.Meter()
    out = agent.handle_slash("/help", m, [])
    assert out == ""
    captured = capsys.readouterr()
    assert "slash commands" in captured.out


def test_slash_reset_session_clears_msgs(agent):
    m = agent.Meter()
    msgs = [{"role": "user", "content": "hi"}]
    agent.handle_slash("/reset session", m, msgs)
    assert msgs == []


def test_slash_reflect_returns_prompt(agent):
    m = agent.Meter()
    out = agent.handle_slash("/reflect", m, [])
    assert "remember" in out.lower() or "reflect" in out.lower()


def test_slash_unknown(agent, capsys):
    m = agent.Meter()
    out = agent.handle_slash("/xyz", m, [])
    captured = capsys.readouterr()
    assert "unknown" in captured.out.lower()
    assert out == ""
