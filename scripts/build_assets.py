"""Build share-ready PNGs for nano-personal-agent.

Outputs into assets/:
  hero.png          1600x900   the marquee — title + tagline + 6-line loop
  og.png            1280x640   GitHub social preview (Open Graph)
  vs-frameworks.png 1600x900   comparison table

Catppuccin Mocha + monospace.
"""
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib import rcParams

# Catppuccin Mocha
BASE     = "#1e1e2e"
MANTLE   = "#181825"
SURFACE  = "#313244"
TEXT     = "#cdd6f4"
SUBTEXT  = "#a6adc8"
OVERLAY  = "#6c7086"
BLUE     = "#89b4fa"
MAUVE    = "#cba6f7"
GREEN    = "#a6e3a1"
YELLOW   = "#f9e2af"
PEACH    = "#fab387"
RED      = "#f38ba8"

rcParams["font.family"] = "monospace"

OUT = Path(__file__).resolve().parent.parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)


def save(fig, name, dpi=140):
    p = OUT / name
    fig.savefig(p, dpi=dpi, bbox_inches="tight", facecolor=BASE, edgecolor="none")
    plt.close(fig)
    print(f"  wrote {p}")


def hero():
    """The marquee asset. 1600x900, drop-into-tweet ready."""
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    fig.patch.set_facecolor(BASE)
    ax.set_facecolor(BASE)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Title
    ax.text(50, 92, "nano-personal-agent",
            ha="center", color=BLUE, fontsize=36, fontweight="bold")
    ax.text(50, 86, "a personal AI agent in one python file",
            ha="center", color=SUBTEXT, fontsize=16, style="italic")

    # The loop panel
    panel = patches.FancyBboxPatch(
        (5, 35), 90, 42,
        boxstyle="round,pad=1.0", facecolor=MANTLE, edgecolor=SURFACE, lw=2)
    ax.add_patch(panel)

    code_lines = [
        ("while True:", TEXT),
        ("    r = client.messages.create(model=M, system=PERSONA_PLUS_MEMORY,", TEXT),
        ("                               messages=msgs, tools=TOOLS)", TEXT),
        ('    msgs.append({"role": "assistant", "content": r.content})', TEXT),
        ('    if r.stop_reason != "tool_use":', TEXT),
        ("        return r", TEXT),
        ('    msgs.append({"role": "user", "content": run_all_tools(r.content)})', TEXT),
    ]
    for i, (line, color) in enumerate(code_lines):
        ax.text(8, 71 - i * 5.0, line, color=color,
                fontsize=13, family="monospace", fontweight="bold")

    # Three pillars
    callouts = [
        (50, 28, "persona, memory, skills — three markdown files in ~/.nanoagent/", BLUE),
        (50, 22, "no vector db. cache is the database.", MAUVE),
        (50, 16, "fork someone's agent: git clone <their persona>", PEACH),
    ]
    for x, y, text, color in callouts:
        ax.text(x, y, text, ha="center", color=color, fontsize=15,
                family="monospace")

    # Footer
    ax.text(50, 7, "github.com/KeWang0622/nano-personal-agent",
            ha="center", color=OVERLAY, fontsize=12, family="monospace")
    ax.text(50, 3, "MIT licensed · works with Claude Sonnet 4.6",
            ha="center", color=OVERLAY, fontsize=11, family="monospace", style="italic")

    save(fig, "hero.png")


def og():
    """1280x640 social preview. Shorter, punchier, optimized for thumbnails."""
    fig, ax = plt.subplots(figsize=(12.8, 6.4), dpi=120)
    fig.patch.set_facecolor(BASE)
    ax.set_facecolor(BASE)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    ax.text(50, 80, "nano-personal-agent",
            ha="center", color=BLUE, fontsize=42, fontweight="bold")
    ax.text(50, 65, "a personal AI in one python file.",
            ha="center", color=TEXT, fontsize=20)
    ax.text(50, 55, "persona · memory · self-improving skills.",
            ha="center", color=SUBTEXT, fontsize=18)

    ax.plot([20, 80], [42, 42], color=MAUVE, lw=2)

    ax.text(50, 32, "no vector db.",
            ha="center", color=PEACH, fontsize=22, fontweight="bold")
    ax.text(50, 22, "the prompt cache is the database.",
            ha="center", color=PEACH, fontsize=18)

    ax.text(50, 8, "github.com/KeWang0622/nano-personal-agent",
            ha="center", color=OVERLAY, fontsize=13, family="monospace")

    save(fig, "og.png")


def vs_frameworks():
    """The comparison table for sharing in framework debates."""
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    fig.patch.set_facecolor(BASE)
    ax.set_facecolor(BASE)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    ax.text(50, 93, "PERSONAL AI AGENTS, COMPARED",
            ha="center", color=YELLOW, fontsize=22, fontweight="bold")
    ax.text(50, 88, "what each one teaches you, in May 2026",
            ha="center", color=SUBTEXT, fontsize=12, style="italic")

    cols = ["", "Hermes", "Letta", "mem0", "nanobot", "this repo"]
    col_x = [3, 22, 38, 52, 66, 84]

    rows = [
        ("LOC",                 ["~50K",   "~22K",      "~30K",   "~12K",   "**818**"]),
        ("one file?",           ["no",     "no",        "no",     "no",     "**yes**"]),
        ("storage",             ["sqlite", "postgres",  "sqlite", "sqlite", "**markdown**"]),
        ("vector db?",          ["yes",    "yes",       "yes",    "yes",    "**no**"]),
        ("persona file?",       ["no",     "no",        "no",     "no",     "**yes**"]),
        ("self-improving?",     ["auto",   "partial",   "no",     "no",     "**/reflect**"]),
        ("read in 10 min?",     ["no",     "no",        "no",     "no",     "**yes**"]),
        ("fork via git clone?", ["no",     "no",        "no",     "no",     "**yes**"]),
    ]

    for i, c in enumerate(cols):
        weight = "bold" if c else "normal"
        color = YELLOW if c == "this repo" else TEXT
        ax.text(col_x[i], 80, c, color=color, fontsize=12,
                fontweight=weight, family="monospace", ha="left")
    ax.plot([2, 98], [76, 76], color=SURFACE, lw=1)

    for r, (label, vals) in enumerate(rows):
        y = 71 - r * 7.0
        ax.text(col_x[0], y, label, color=SUBTEXT, fontsize=11,
                family="monospace", fontweight="bold")
        for i, v in enumerate(vals):
            color = YELLOW if "**" in v else SUBTEXT
            v_clean = v.replace("**", "")
            weight = "bold" if "**" in v else "normal"
            ax.text(col_x[i + 1], y, v_clean, color=color, fontsize=11,
                    family="monospace", fontweight=weight)

    ax.text(50, 8, "frameworks tell you WHAT TO TYPE.   this teaches you WHAT'S UNDERNEATH.",
            ha="center", color=PEACH, fontsize=13, fontweight="bold", family="monospace")
    ax.text(50, 3, "github.com/KeWang0622/nano-personal-agent",
            ha="center", color=OVERLAY, fontsize=10, family="monospace")

    save(fig, "vs-frameworks.png")


if __name__ == "__main__":
    print("building assets...")
    hero()
    og()
    vs_frameworks()
    print("done.")
