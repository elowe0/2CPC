#!/usr/bin/env python3
"""Install the 2CPC skill for Claude Code (user level): ~/.claude/skills/2cpc/SKILL.md"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 8):
        sys.exit("Python 3.8+ required")
    dest = Path.home() / ".claude" / "skills" / "2cpc"
    dest.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(HERE))
    from cpc.skill import render_skill
    (dest / "SKILL.md").write_text(render_skill(HERE), encoding="utf-8")
    print(f"OK skill installed: {dest / 'SKILL.md'}")


if __name__ == "__main__":
    main()
