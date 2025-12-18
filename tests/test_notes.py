from pathlib import Path

from groundhog.notes import format_notes, find_note_files


def test_format_notes(tmp_path: Path):
    file1 = tmp_path / "2025-01-01.md"
    file1.write_text("hello", encoding="utf-8")
    files = find_note_files(str(tmp_path))
    output = format_notes(files)
    assert "hello" in output
    assert "2025-01-01" in output
