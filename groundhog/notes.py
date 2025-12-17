from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class DateFile:
    path: Path
    date_str: str


def find_note_files(notes_dir: str) -> List[DateFile]:
    root = Path(notes_dir)
    if not root.exists():
        return []

    files: List[DateFile] = []
    for entry in root.iterdir():
        if not entry.is_file():
            continue
        if not DATE_PATTERN.search(entry.name):
            continue
        date_part = entry.stem.split(".")[0]
        files.append(DateFile(path=entry.resolve(), date_str=date_part))
    files.sort(key=lambda f: f.date_str)
    return files


def format_notes(files: Iterable[DateFile]) -> str:
    output: list[str] = []
    for idx, df in enumerate(files, start=1):
        try:
            content = df.path.read_text(encoding="utf-8")
        except OSError:
            continue
        output.append(f"Note {idx} ({df.date_str})\n{content.strip()}")
    return "\n\n".join(output)


def recent_notes(notes_dir: str, limit: int) -> str:
    if limit <= 0:
        limit = 5
    files = find_note_files(notes_dir)
    if not files:
        return "No notes found."
    selected = files[-limit:]
    return format_notes(selected)


