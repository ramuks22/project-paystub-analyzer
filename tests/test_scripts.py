import pytest
from scripts.extract_release_notes import extract_release_notes

CHANGELOG_CONTENT = """# Changelog

## [0.2.0] - 2026-03-01
### Added
- Feature A

## [0.1.0-alpha.1] - 2026-02-18
### Added
- Docker Support
- CLI Tools

### Changed
- Replaced legacy scripts

## [0.0.1] - 2025-01-01
- Initial
"""


@pytest.mark.unit
def test_extract_release_notes_exact_match(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(CHANGELOG_CONTENT, encoding="utf-8")

    notes = extract_release_notes("0.1.0-alpha.1", str(p))
    assert "### Added" in notes
    assert "- Docker Support" in notes
    assert "### Changed" in notes
    assert "Feature A" not in notes
    assert "## [0.0.1]" not in notes


@pytest.mark.unit
def test_extract_release_notes_with_v_prefix(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(CHANGELOG_CONTENT, encoding="utf-8")

    notes = extract_release_notes("v0.1.0-alpha.1", str(p))
    assert "- Docker Support" in notes


@pytest.mark.unit
def test_extract_release_notes_missing_version(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(CHANGELOG_CONTENT, encoding="utf-8")

    with pytest.raises(SystemExit):
        extract_release_notes("0.9.9", str(p))
