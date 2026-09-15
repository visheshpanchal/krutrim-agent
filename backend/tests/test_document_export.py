"""The `document-export` skill is guideline-only — no bundled converter script.
The model writes and runs the conversion itself (see SKILL.md), so there is no
script internals left to unit test; these just guard the skill's own contract.
"""

from __future__ import annotations

from krutrim_agent_management.config import settings

_SKILL_DIR = settings.common_skills_dir / "document-export"


def test_skill_frontmatter_loads_and_names_match_the_directory():
    from deepagents.middleware.skills import _parse_skill_metadata

    content = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    meta = _parse_skill_metadata(
        content, str(_SKILL_DIR / "SKILL.md"), "document-export"
    )
    assert meta is not None
    assert meta["name"] == "document-export"
    assert meta["description"]


def test_no_bundled_converter_script_ships_anymore():
    """The old `md_export.py` helper is gone by design — the skill now tells
    the model to write the conversion script itself each time."""
    assert not (_SKILL_DIR / "md_export.py").exists()


def test_skill_names_the_right_library_for_each_format():
    content = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "fpdf2" in content
    assert "python-docx" in content
    # PyPDF2/pypdf manipulate existing PDFs; they can't author a new one from
    # Markdown — the skill must steer the model away from reaching for them.
    assert "PyPDF2" in content


def test_skill_covers_the_install_then_execute_flow():
    content = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "pip install fpdf2" in content
    assert "pip install python-docx" in content
    assert "import fpdf" in content
    assert "import docx" in content
