"""The skill file installed in ~/.claude/skills/2cpc/ (shared by install.py and the "skill outdated" check)."""
from pathlib import Path


def render_skill(here):
    here = Path(here)
    src = (here / "skill" / "SKILL.md").read_text(encoding="utf-8")
    return src.replace("{{CPC}}", (here / "cpc.py").as_posix()).replace("{{DOCS}}", (here / "docs" / "DSL.md").as_posix())
