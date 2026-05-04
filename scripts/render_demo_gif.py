"""Render a demo GIF of a real nano-personal-agent session.

Generates PNG frames using PIL with a Catppuccin Mocha terminal aesthetic,
then composes them into a GIF. The script content (turn-by-turn lines) is
hand-curated from a real captured session to ensure the cost numbers and
cache stats are accurate.

Output: assets/demo.gif (1280×720, ~15 seconds, ~8 fps)
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ---- Catppuccin Mocha palette --------------------------------------------
BASE = (30, 30, 46)
MANTLE = (24, 24, 37)
TEXT = (205, 214, 244)
SUBTEXT = (166, 173, 200)
OVERLAY = (108, 112, 134)
BLUE = (137, 180, 250)
MAUVE = (203, 166, 247)
GREEN = (166, 227, 161)
PEACH = (250, 179, 135)

# ---- font ---------------------------------------------------------------
FONT_PATH = "/System/Library/Fonts/SFNSMono.ttf"

W, H = 1280, 720
PAD = 28
LINE_H = 22
FONT_SIZE = 16


def render_frame(lines: list[tuple[str, tuple]], title="nano-personal-agent"):
    """Render one terminal frame. lines is a list of (text, color) tuples."""
    img = Image.new("RGB", (W, H), BASE)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    # macos title bar
    draw.rectangle([0, 0, W, 36], fill=MANTLE)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = 18 + i * 20
        draw.ellipse([cx - 6, 14, cx + 6, 26], fill=color)
    draw.text((W // 2 - 110, 9), f"{title} — agent.py", font=font, fill=SUBTEXT)

    # body
    y = PAD + 36
    for text, color in lines:
        draw.text((PAD, y), text, font=font, fill=color)
        y += LINE_H
        if y > H - PAD:
            break

    return img


# ---- the script ---------------------------------------------------------
# Numbers are from a real session captured against the live API.

frames = []


def add_frame(content_lines):
    frames.append(render_frame(list(content_lines)))


# Header — matches what the actual agent prints (after the recent fix that
# adds the closing │ on the middle line)
hdr = [
    ("╭" + "─" * 60 + "╮", OVERLAY),
    ("│  nano-personal-agent  model claude-sonnet-4-6 · brain ~/.nanoagent  │", OVERLAY),
    ("╰" + "─" * 60 + "╯", OVERLAY),
    ("/help for commands · ctrl-d to exit", OVERLAY),
    ("", TEXT),
]

# act 1: intro pause
for _ in range(3):
    add_frame(hdr)

# act 2: type the prompt
PROMPT = "> i prefer vim and live in pacific time. remember those."
for i in range(0, len(PROMPT) + 1, 3):
    typed = PROMPT[:i] + ("▌" if i < len(PROMPT) else "")
    add_frame(hdr + [(typed, TEXT)])

# pause on full prompt
for _ in range(3):
    add_frame(hdr + [(PROMPT, TEXT), ("", TEXT)])

# act 3: agent calls remember twice (parallel)
turn1 = hdr + [
    (PROMPT, TEXT),
    ("", TEXT),
    ('● remember({"fact": "Prefers vim as their editor.", "tags": ["pref"]})', GREEN),
    ('● remember({"fact": "Lives in Pacific Time (PT).", "tags": ["pref"]})', GREEN),
    ("turn 1 · $0.0116 · in 483 out 138 cache_r 0 cache_w 2156", OVERLAY),
]
for _ in range(2):
    add_frame(turn1)

# tool results render
turn1_done = turn1 + [
    ("  ⎿ remembered: - [2026-05-04] #pref Prefers vim as their editor.", SUBTEXT),
    ("  ⎿ remembered: - [2026-05-04] #pref Lives in Pacific Time (PT).", SUBTEXT),
]
add_frame(turn1_done)

# final assistant reply
final = turn1_done + [
    ("got it. vim + pacific time, locked in.", TEXT),
    ("turn 2 · $0.0147 · in 1246 out 152 cache_r 2156 cache_w 2156", OVERLAY),
    ("", TEXT),
    ("> ▌", TEXT),
]
for _ in range(2):
    add_frame(final)

# act 4: second session — cache hit demo
hdr2 = [
    ("$ python agent.py \"what do you know about me?\"", BLUE),
    ("", TEXT),
]
add_frame(final[:-2] + hdr2)

second = final[:-2] + hdr2 + [
    ("from memory, here's what i've got:", TEXT),
    ("", TEXT),
    ("- editor: you prefer vim", TEXT),
    ("- timezone: you're in Pacific Time (PT)", TEXT),
    ("", TEXT),
    ("turn 1 · $0.0034 · in 3 out 57 cache_r 2156 cache_w 0", OVERLAY),
]
for _ in range(2):
    add_frame(second)

# emphasize the cache hit
final2 = second + [
    ("", TEXT),
    ("$0.0034 across 1 turns · brain at ~/.nanoagent", BLUE),
    ("$ ▌", TEXT),
]
for _ in range(8):
    add_frame(final2)


# ---- compose ------------------------------------------------------------
def main():
    out_dir = Path(__file__).resolve().parent.parent / "assets"
    out_dir.mkdir(exist_ok=True)
    gif_path = out_dir / "demo.gif"

    print(f"rendering {len(frames)} frames...")
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=140,
        loop=0,
        optimize=True,
    )
    size_kb = gif_path.stat().st_size // 1024
    print(f"  wrote {gif_path} ({size_kb} KB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
